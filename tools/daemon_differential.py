#!/usr/bin/env python
"""Opt-in first-batch actual-daemon comparison; stdlib, Python2/3.

Requires an already isolated lo-only environment and uid65534. This tool never
sets up Docker, namespaces, privileges, dependencies or deployment.
"""
from __future__ import print_function
import argparse, binascii, errno, hashlib, json, os, signal, socket, stat, struct, subprocess, sys, time, traceback
ROOT = None
PORT = 14630
TARGETS = None
TEMPLATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'daemon_differential.conf.template')
MAX_REPLY = 262144
PAYLOADS = [b'A\x00B\n\xff', b'', b'tail']
METHODS = ['getName','getVersion','getStatus','getStatusDetails','getCounters','Log','Log','getCounters','shutdown']
EXPECTED_DELTA = {'fixture:received good':3,'scribe_overall:received good':3,'unknown:received bad':1,'scribe_overall:received bad':1,'scribe_overall:received blank category':1}

def hexbytes(data):
    return binascii.hexlify(data).decode('ascii')

def save_json(path, obj):
    with open(path, 'w') as f:
        json.dump(obj, f, indent=2, sort_keys=True)
        f.write('\n')

def string(data):
    return struct.pack('>i', len(data)) + data

def framed(name, seq, fields=b'\0', oneway=False):
    body = string(name) + struct.pack('>B', 4 if oneway else 1) + struct.pack('>i', seq) + fields
    return struct.pack('>I', len(body)) + body

def log_fields(entries):
    body = b'\x0f\x00\x01\x0c' + struct.pack('>i', len(entries))
    for category, payload in entries:
        body += b'\x0b\x00\x01' + string(category) + b'\x0b\x00\x02' + string(payload) + b'\0'
    return body + b'\0'

class Cursor(object):
    def __init__(self, data):
        self.data, self.offset = data, 0
    def take(self, n):
        if n < 0 or n > len(self.data) - self.offset:
            raise ValueError('invalid/truncated reply')
        result = self.data[self.offset:self.offset+n]; self.offset += n
        return result
    def number(self, fmt):
        return struct.unpack(fmt, self.take(struct.calcsize(fmt)))[0]
    def string(self):
        return self.take(self.number('>i'))
    def value(self, kind):
        if kind == 8: return self.number('>i')
        if kind == 10: return self.number('>q')
        if kind == 11: return hexbytes(self.string())
        if kind == 13:
            key_kind, val_kind, count = self.number('>B'), self.number('>B'), self.number('>i')
            if (key_kind,val_kind) != (11,10) or not 0 <= count <= 10000:
                raise ValueError('unexpected/unbounded map')
            result = {}
            for unused in range(count):
                key = self.string().decode('ascii')
                if key in result: raise ValueError('duplicate counter')
                result[key] = self.number('>q')
            return result
        raise ValueError('unexpected result field type %d' % kind)

def parse_reply(body, name, seq):
    c = Cursor(body)
    if (c.string(),c.number('>B'),c.number('>i')) != (name,2,seq):
        raise ValueError('reply header mismatch')
    kind = c.number('>B')
    expected_kind = {b'getName':11,b'getVersion':11,b'getStatus':8,b'getStatusDetails':11,b'getCounters':13,b'Log':8}[name]
    if kind != expected_kind: raise ValueError('unexpected method result type')
    if kind == 0: value = None
    else:
        if c.number('>h') != 0: raise ValueError('missing success field')
        value = c.value(kind)
        if c.number('>B') != 0: raise ValueError('unexpected extra result')
    if c.offset != len(body): raise ValueError('trailing reply bytes')
    return value

def recv_exact(conn, size):
    data = b''
    while len(data) < size:
        part = conn.recv(size-len(data))
        if not part: raise ValueError('unexpected EOF')
        data += part
    return data

def call(conn, name, seq, fields, directory, records, oneway=False):
    request = framed(name,seq,fields,oneway)
    filename = '%02d-%s' % (seq,name.decode('ascii'))
    with open(os.path.join(directory,filename+'.request.bin'),'wb') as f: f.write(request)
    item = {'method':name.decode('ascii'),'sequence':seq,'request_hex':hexbytes(request),'oneway':oneway}
    records.append(item)
    conn.sendall(request)
    if oneway: return None
    prefix = recv_exact(conn,4); size = struct.unpack('>I',prefix)[0]
    if not 0 < size <= MAX_REPLY: raise ValueError('unbounded reply frame')
    body = recv_exact(conn,size)
    with open(os.path.join(directory,filename+'.reply.bin'),'wb') as f: f.write(prefix+body)
    item['reply_hex'] = hexbytes(prefix+body)
    item['value'] = parse_reply(body,name,seq)
    return item['value']

def network_check():
    if os.getuid() != 65534 or os.geteuid() != 65534:
        raise ValueError('comparison must run as real/effective uid65534')
    if sorted(os.listdir('/sys/class/net')) != ['lo']:
        raise ValueError('network isolation changed')

def port_free():
    try:
        check = socket.create_connection(('127.0.0.1',PORT),timeout=0.3)
    except socket.error as error:
        if error.errno == errno.ECONNREFUSED: return
        raise
    check.close()
    raise ValueError('test port already has a listener; no process was stopped')

def connection_owner(pid,conn):
    """Verify this established server-side socket is an fd of the owned PID."""
    local=conn.getpeername();remote=conn.getsockname()
    def endpoint(address,ipv6):
        ip,port=address
        packed=socket.inet_pton(socket.AF_INET6,'::ffff:'+ip) if ipv6 else socket.inet_aton(ip)
        words=[packed[i:i+4][::-1] for i in range(0,len(packed),4)]
        return hexbytes(b''.join(words)).upper()+':%04X'%port
    deadline=time.time()+3
    while True:
        fdroot='/proc/%d/fd'%pid
        inodes=set()
        for fd in os.listdir(fdroot):
            try: target=os.readlink(os.path.join(fdroot,fd))
            except OSError as error:
                if error.errno == errno.ENOENT: continue
                raise
            if target.startswith('socket:['): inodes.add(target[8:-1])
        for name,ipv6 in (('tcp',False),('tcp6',True)):
            with open('/proc/%d/net/%s'%(pid,name)) as f:
                for line in f:
                    fields=line.split()
                    if len(fields)>9 and fields[3]=='01' and fields[1]==endpoint(local,ipv6) and fields[2]==endpoint(remote,ipv6):
                        if fields[9] in inodes: return fields[9]
        if time.time()>=deadline: raise ValueError('cannot verify connected socket ownership; no RPC sent')
        time.sleep(0.01)

def group_exists(pgid):
    try: os.killpg(pgid,0)
    except OSError as error:
        if error.errno == errno.ESRCH: return False
        raise
    return True

def cleanup_process(process):
    # Popen setsid created this session; never select a process/group by name.
    if group_exists(process.pid):
        try: os.killpg(process.pid,signal.SIGTERM)
        except OSError as error:
            if error.errno != errno.ESRCH: raise
        deadline=time.time()+2
        while group_exists(process.pid) and time.time()<deadline: time.sleep(0.01)
        if group_exists(process.pid):
            try: os.killpg(process.pid,signal.SIGKILL)
            except OSError as error:
                if error.errno != errno.ESRCH: raise
    code=process.wait()
    if group_exists(process.pid): raise ValueError('owned session remains after cleanup')
    return code

def run_lane(lane):
    network_check()
    directory = os.path.join(ROOT,'evidence',lane); output = os.path.join(ROOT,lane+'-output')
    os.makedirs(directory); os.makedirs(output)
    with open(TEMPLATE) as f:
        config=f.read().replace('@SEPARATE_TEMP_OUTPUT@',output).replace('@PORT@',str(PORT))
    config_path=os.path.join(ROOT,lane+'.conf')
    with open(config_path,'w') as f: f.write(config)
    env=os.environ.copy();env.pop('LD_PRELOAD',None);env.pop('LD_AUDIT',None)
    env['LC_ALL']='C';env['TZ']='UTC'
    env.pop('LD_LIBRARY_PATH',None)
    env.update(TARGETS[lane].get('environment',{}))
    command=TARGETS[lane]['command'] + ['-c',config_path]
    result={'lane':lane,'command':command,'uid':os.getuid(),'interfaces':os.listdir('/sys/class/net'),'records':[]}
    save_json(os.path.join(directory,'start.json'),result)
    process=None;conn=None
    with open(os.path.join(directory,'daemon.stdout'),'wb') as stdout, open(os.path.join(directory,'daemon.stderr'),'wb') as stderr:
        try:
            port_free()
            with open(os.devnull,'rb') as stdin:
                process=subprocess.Popen(command,env=env,stdin=stdin,stdout=stdout,stderr=stderr,preexec_fn=os.setsid)
            result['pid']=process.pid
            deadline=time.time()+10
            while True:
                if process.poll() is not None: raise ValueError('daemon exited before readiness')
                try:
                    conn=socket.create_connection(('127.0.0.1',PORT),timeout=0.3);break
                except socket.error:
                    if time.time() >= deadline: raise ValueError('readiness timeout')
                    time.sleep(0.05)
            conn.settimeout(3)
            if conn.getpeername() != ('127.0.0.1',PORT): raise ValueError('wrong peer')
            result['owned_connection_inode']=connection_owner(process.pid,conn)
            records=result['records']
            for seq,name in enumerate([b'getName',b'getVersion',b'getStatus',b'getStatusDetails',b'getCounters'],1):
                call(conn,name,seq,b'\0',directory,records)
            if records[2]['value'] != 2: raise ValueError('fb303 not ALIVE')
            if call(conn,b'Log',6,log_fields([]),directory,records) != 0: raise ValueError('empty Log not OK')
            entries=[(b'fixture',p) for p in PAYLOADS]+[(b'',b'blank-discard'),(b'unknown',b'unknown-discard')]
            if call(conn,b'Log',7,log_fields(entries),directory,records) != 0: raise ValueError('batch not OK')
            after=call(conn,b'getCounters',8,b'\0',directory,records)
            before=records[4]['value']
            delta={key:after.get(key,0)-before.get(key,0) for key in set(before)|set(after)}
            delta={key:value for key,value in delta.items() if value}
            if delta != EXPECTED_DELTA: raise ValueError('counter delta differs: %r' % delta)
            result['counter_delta']=delta
            call(conn,b'shutdown',9,b'\0',directory,records,oneway=True)
            conn.close();conn=None
            deadline=time.time()+10
            while process.poll() is None and time.time()<deadline: time.sleep(0.05)
            if process.poll() is None: raise ValueError('shutdown timeout')
            result['exit']=process.returncode
            if process.returncode != 0: raise ValueError('shutdown exit not zero')
            files=[];links=[]
            for path,dirs,names in os.walk(output):
                for name in sorted(names):
                    full=os.path.join(path,name);relative=os.path.relpath(full,output)
                    if os.path.islink(full): links.append({'path':relative,'target':os.readlink(full)})
                    elif os.path.isfile(full):
                        with open(full,'rb') as f: data=f.read()
                        files.append({'path':relative,'bytes':len(data),'hex':hexbytes(data),'sha256':hashlib.sha256(data).hexdigest()})
            result['files']=files;result['symlinks']=links
            if len(files)!=1 or files[0]['hex']!=hexbytes(b''.join(PAYLOADS)):
                raise ValueError('file bytes differ from accepted payloads')
            port_free()
            result['status']='passed'
        except BaseException:
            result['status']='failed';result['error']=traceback.format_exc()
            raise
        finally:
            if conn: conn.close()
            try:
                if process: result['cleanup_exit']=cleanup_process(process)
            except BaseException:
                result['status']='failed';result['cleanup_error']=traceback.format_exc()
                raise
            finally:
                save_json(os.path.join(directory,'result.json'),result)
    return result

def compare_lanes(old,new):
    for lane in (old,new):
        if lane.get('status') != 'passed' or len(lane.get('records',[])) != 9:
            raise ValueError('incomplete or failed lane')
        if [r['method'] for r in lane['records']] != METHODS:
            raise ValueError('unexpected RPC sequence')
        if [r['sequence'] for r in lane['records']] != list(range(1,10)):
            raise ValueError('unexpected sequence IDs')
        if lane['counter_delta'] != EXPECTED_DELTA:
            raise ValueError('unexpected counter delta')
        for record in lane['records']:
            seq=record['sequence'];name=record['method'].encode('ascii')
            fields=b'\0'
            if seq == 6: fields=log_fields([])
            if seq == 7: fields=log_fields([(b'fixture',p) for p in PAYLOADS]+[(b'',b'blank-discard'),(b'unknown',b'unknown-discard')])
            if record.get('oneway') != (seq==9) or record['request_hex'] != hexbytes(framed(name,seq,fields,seq==9)):
                raise ValueError('unexpected first-batch request')
            if seq != 9:
                wire=binascii.unhexlify(record['reply_hex'])
                if len(wire)<4 or struct.unpack('>I',wire[:4])[0] != len(wire)-4 or not 0<len(wire)-4<=MAX_REPLY:
                    raise ValueError('invalid recorded reply frame')
                if parse_reply(wire[4:],name,seq) != record['value']:
                    raise ValueError('recorded reply/value mismatch')
            elif 'reply_hex' in record:
                raise ValueError('oneway shutdown must not record a response')
        expected_data=b''.join(PAYLOADS)
        if lane['files'] != [{'path':'fixture_00000','bytes':len(expected_data),'hex':hexbytes(expected_data),'sha256':hashlib.sha256(expected_data).hexdigest()}]:
            raise ValueError('unexpected first-batch output file')
        if lane['symlinks'] != [{'path':'fixture_current','target':'fixture_00000'}]:
            raise ValueError('unexpected first-batch symlink')
    checks={}
    for a,b in zip(old['records'],new['records']):
        checks['request-%d'%a['sequence']]=a['request_hex']==b['request_hex']
        if a['method'] not in ('getVersion','shutdown'):
            checks['reply-%d'%a['sequence']]=a['reply_hex']==b['reply_hex']
    checks['counter-delta']=old['counter_delta']==new['counter_delta']
    checks['files']=old['files']==new['files']
    checks['symlinks']=old['symlinks']==new['symlinks']
    checks['exit']=old['exit']==new['exit']==0
    checks['versions']=old['records'][1]['value']==new['records'][1]['value']==hexbytes(b'2.2')
    result={'status':'passed' if all(checks.values()) else 'failed','checks':checks,'old_version_hex':old['records'][1]['value'],'modern_version_hex':new['records'][1]['value'],'python':sys.version,'scope':'bounded synthetic production daemon differential; distinct old/new userlands/ABIs'}
    return result

def main():
    global ROOT, PORT, TARGETS
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-isolated-daemons',action='store_true',help='explicitly opt in to launching the two supplied targets')
    parser.add_argument('--targets',required=True,help='JSON with old/modern command arrays and explicit environment maps')
    parser.add_argument('--output',required=True,help='new directory outside this checkout')
    parser.add_argument('--port',type=int,default=14630)
    args=parser.parse_args()
    if not args.run_isolated_daemons: parser.error('actual daemon execution requires --run-isolated-daemons')
    network_check()
    if not 1024 <= args.port <= 65535: parser.error('use an unprivileged TCP port')
    PORT=args.port
    ROOT=os.path.abspath(args.output)
    source=os.path.realpath(os.path.join(os.path.dirname(__file__),'..'))
    if os.path.lexists(ROOT) or os.path.realpath(ROOT).startswith(source+os.sep) or os.path.realpath(ROOT)==source:
        parser.error('output must be new and outside the checkout')
    with open(args.targets) as f: TARGETS=json.load(f)
    if set(TARGETS) != set(['old','modern']): parser.error('supply exactly old and modern targets')
    for lane in ('old','modern'):
        target=TARGETS[lane]
        command=target.get('command')
        if not isinstance(command,list) or not command or any((not isinstance(a,type(u'')) and not isinstance(a,str)) or not a or '\0' in a for a in command):
            parser.error('target command must be a nonempty string array')
        for executable in (command[0],command[-1]):
            if not os.path.isabs(executable) or not os.path.isfile(executable) or not os.access(executable,os.X_OK):
                parser.error('command must start with an executable and end with an absolute daemon binary')
            if os.stat(executable).st_mode & (stat.S_ISUID|stat.S_ISGID): parser.error('setuid/setgid targets are forbidden')
        environment=target.get('environment',{})
        if not isinstance(environment,dict) or any(k in environment for k in ('LD_PRELOAD','LD_AUDIT')):
            parser.error('explicit environment must not inject preload/audit libraries')
        for key,value in environment.items():
            if not isinstance(key,(str,type(u''))) or not isinstance(value,(str,type(u''))) or not key or '=' in key or '\0' in key+value:
                parser.error('environment requires valid string key/value entries')
    port_free()
    os.makedirs(ROOT);os.makedirs(os.path.join(ROOT,'evidence'))
    old=run_lane('old');new=run_lane('modern')
    result=compare_lanes(old,new)
    save_json(ROOT+'/evidence/comparison.json',result)
    if result['status']!='passed': raise ValueError('old/new comparison differed')
    print(json.dumps(result,sort_keys=True))

if __name__=='__main__': main()
