#!/usr/bin/env python
"""Opt-in actual-daemon old/new comparison (17 cases plus performance); stdlib, Python2/3.

Requires an already isolated lo-only environment and uid65534. This tool never
sets up Docker, namespaces, privileges, dependencies or deployment.
"""
from __future__ import print_function
import argparse, binascii, errno, hashlib, json, os, signal, socket, stat, struct, subprocess, sys, time, traceback
ROOT = None
PORT = 14630
TARGETS = None
CASE = 'file'
TEMPLATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'daemon_differential.conf.template')
MAX_REPLY = 262144
PAYLOADS = [b'A\x00B\n\xff', b'', b'tail']
METHODS = ['getName','getVersion','getStatus','getStatusDetails','getCounters','Log','Log','getCounters','shutdown']
SCENARIO_CASES = ('relay-stream','mixed-relay-stream','receiver-restart','receiver-crash','sender-restart-spool','mixed-sender-restart-spool','throttle-retry')
EXPECTED_DELTA = {'fixture:received good':3,'scribe_overall:received good':3,'unknown:received bad':1,'scribe_overall:received bad':1,'scribe_overall:received blank category':1}

def case_data(case):
    if case == 'file':
        return ([(b'fixture',p) for p in PAYLOADS]+[(b'',b'blank-discard'),(b'unknown',b'unknown-discard')],
                EXPECTED_DELTA, {'fixture_00000':b''.join(PAYLOADS)})
    if case == 'file-stores':
        first=PAYLOADS[0];second=b'ends\n'
        event=lambda value:struct.pack('=I',len(value))+value
        framed=event(first)+b'\0'*7+event(second) # two 9-byte events in 16-byte chunks
        entries=[(b'bucket',b'5|'+first),(b'bucket',b'15|'+second),(b'bucket',b'no-key')]
        entries += [(category,value) for category in (b'thrift',b'rawthrift') for value in (first,second)]
        entries += [(b'mfA',first),(b'mfB',b'Z'),(b'mfA',second),
                    (b'tmfA',first),(b'tmfB',b'Z'),(b'tmfA',second)]
        delta={'bucket:received good':3,'thrift:received good':2,'rawthrift:received good':2,
               'mfA:received good':2,'mfB:received good':1,'tmfA:received good':2,
               'tmfB:received good':1,'scribe_overall:received good':13}
        files={'bucket/failed/data_00000':b'no-key','bucket/b001/data_00000':first,
               'bucket/b002/data_00000':second,'thrift/data_00000':framed,
               'rawthrift/data_00000':first+second,'multifile/mfA/mfA_00000':first+second,
               'multifile/mfB/mfB_00000':b'Z','thriftmultifile/tmfA/tmfA_00000':framed,
               'thriftmultifile/tmfB/tmfB_00000':event(b'Z')}
        return entries,delta,files
    if case in ('restart-before','restart-after'):
        entries=[(b'fixture',p) for p in (PAYLOADS[0],PAYLOADS[2])] if case=='restart-before' else [(b'fixture',b'Z')]
        count=len(entries)
        files={'fixture_00000':PAYLOADS[0],'fixture_00001':PAYLOADS[2]}
        if case=='restart-after': files.update({'fixture_00001':PAYLOADS[2]+b'Z','fixture_00002':b''})
        return entries,{'fixture:received good':count,'scribe_overall:received good':count},files
    if case == 'rotation':
        return ([(b'fixture',PAYLOADS[0]),(b'fixture',PAYLOADS[2])],
                {'fixture:received good':3,'scribe_overall:received good':3},
                {'fixture_00000':PAYLOADS[0],'fixture_00001':PAYLOADS[2]+b'Z','fixture_00002':b''})
    if case != 'stores': raise ValueError('unknown comparison case')
    entries=[(b'discard',p) for p in PAYLOADS]+[(b'fanout',p) for p in PAYLOADS]
    entries += [(b'catA',b''),(b'catB',PAYLOADS[2]),(b'catA',PAYLOADS[0]),
                (b'',b'blank-discard'),(b'unknown',b'unknown-discard')]
    delta={'discard:received good':3,'fanout:received good':3,'catA:received good':2,
           'catB:received good':1,'scribe_overall:received good':9,
           'discard:ignored':3,'fanout:ignored':3,'scribe_overall:ignored':6,
           'unknown:received bad':1,'scribe_overall:received bad':1,
           'scribe_overall:received blank category':1}
    files={'left/left_00000':b''.join(PAYLOADS),'right/right_00000':b''.join(PAYLOADS),
           'category/catA/catA_00000':PAYLOADS[0],'category/catB/catB_00000':PAYLOADS[2]}
    return entries,delta,files

def expected_outputs(case):
    files=[];links=[]
    for path,data in sorted(case_data(case)[2].items()):
        files.append({'path':path,'bytes':len(data),'hex':hexbytes(data),'sha256':hashlib.sha256(data).hexdigest()})
        parent,name=os.path.split(path)
        link={'path':os.path.join(parent,name.rsplit('_',1)[0]+'_current'),'target':name}
        links=[item for item in links if item['path']!=link['path']]
        links.append(link)
    return files,links

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
    def value(self, kind, map_value_kind=None):
        if kind == 8: return self.number('>i')
        if kind == 10: return self.number('>q')
        if kind == 11: return hexbytes(self.string())
        if kind == 13:
            key_kind, val_kind, count = self.number('>B'), self.number('>B'), self.number('>i')
            if key_kind!=11 or val_kind not in (10,11) or (map_value_kind is not None and val_kind!=map_value_kind) or not 0 <= count <= 10000:
                raise ValueError('unexpected/unbounded map')
            result = {}
            for unused in range(count):
                raw_key=self.string()
                key=raw_key.decode('ascii') if val_kind==10 else hexbytes(raw_key)
                if key in result: raise ValueError('duplicate counter')
                result[key] = self.number('>q') if val_kind==10 else hexbytes(self.string())
            return result
        raise ValueError('unexpected result field type %d' % kind)

def parse_reply(body, name, seq):
    c = Cursor(body)
    if (c.string(),c.number('>B'),c.number('>i')) != (name,2,seq):
        raise ValueError('reply header mismatch')
    kind = c.number('>B')
    expected_kind = {b'getName':11,b'getVersion':11,b'getStatus':8,b'getStatusDetails':11,b'getCounters':13,b'getCounter':10,b'getOption':11,b'getOptions':13,b'setOption':0,b'Log':8}[name]
    if kind != expected_kind: raise ValueError('unexpected method result type')
    if kind == 0: value = None
    else:
        if c.number('>h') != 0: raise ValueError('missing success field')
        value = c.value(kind,11 if name==b'getOptions' else 10)
        if c.number('>B') != 0: raise ValueError('unexpected extra result')
    if c.offset != len(body): raise ValueError('trailing reply bytes')
    return value

def parse_application_exception(body,name,seq):
    c=Cursor(body)
    if (c.string(),c.number('>B'),c.number('>i'))!=(name,3,seq):raise ValueError('exception header mismatch')
    fields={}
    while True:
        kind=c.number('>B')
        if kind==0:break
        field=c.number('>h')
        if field in fields or (field,kind) not in ((1,11),(2,8)):raise ValueError('unexpected exception field')
        fields[field]=c.value(kind)
    if set(fields)!=set((1,2)) or c.offset!=len(body):raise ValueError('incomplete/trailing exception')
    return {'message_hex':fields[1],'type':fields[2]}

def recv_exact(conn, size):
    data = b''
    while len(data) < size:
        part = conn.recv(size-len(data))
        if not part: raise ValueError('unexpected EOF')
        data += part
    return data

def call(conn, name, seq, fields, directory, records, oneway=False, exception=False):
    if oneway and exception:raise ValueError('oneway call cannot expect exception reply')
    request = framed(name,seq,fields,oneway)
    filename = '%02d-%s' % (seq,name.decode('ascii'))
    with open(os.path.join(directory,filename+'.request.bin'),'wb') as f: f.write(request)
    item = {'method':name.decode('ascii'),'sequence':seq,'request_hex':hexbytes(request),'oneway':oneway}
    if exception:item['exception']=True
    records.append(item)
    conn.sendall(request)
    if oneway: return None
    prefix = recv_exact(conn,4); size = struct.unpack('>I',prefix)[0]
    if not 0 < size <= MAX_REPLY: raise ValueError('unbounded reply frame')
    body = recv_exact(conn,size)
    with open(os.path.join(directory,filename+'.reply.bin'),'wb') as f: f.write(prefix+body)
    item['reply_hex'] = hexbytes(prefix+body)
    item['value'] = parse_application_exception(body,name,seq) if exception else parse_reply(body,name,seq)
    return item['value']

def network_check():
    if os.getuid() != 65534 or os.geteuid() != 65534:
        raise ValueError('comparison must run as real/effective uid65534')
    if sorted(os.listdir('/sys/class/net')) != ['lo']:
        raise ValueError('network isolation changed')

def port_free(port=None):
    port=PORT if port is None else port
    try:
        check = socket.create_connection(('127.0.0.1',port),timeout=0.3)
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

def connect_owned(process,port,timeout=10):
    deadline=time.time()+timeout
    while True:
        if process.poll() is not None: raise ValueError('daemon exited before readiness')
        try:
            conn=socket.create_connection(('127.0.0.1',port),timeout=0.3);break
        except socket.error:
            if time.time()>=deadline: raise ValueError('readiness timeout')
            time.sleep(0.05)
    conn.settimeout(3)
    if conn.getpeername()!=('127.0.0.1',port):
        conn.close();raise ValueError('wrong peer')
    return conn

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

def output_snapshot(output):
    files=[];links=[]
    for path,dirs,names in os.walk(output):
        dirs.sort()
        for name in sorted(names):
            full=os.path.join(path,name);relative=os.path.relpath(full,output)
            if os.path.islink(full): links.append({'path':relative,'target':os.readlink(full)})
            elif os.path.isfile(full):
                with open(full,'rb') as f: data=f.read()
                files.append({'path':relative,'bytes':len(data),'hex':hexbytes(data),'sha256':hashlib.sha256(data).hexdigest()})
    files.sort(key=lambda item:item['path']);links.sort(key=lambda item:item['path'])
    return files,links

def rotation_outputs(final=False):
    files,links=expected_outputs('rotation')
    if not final:
        files=files[:2]
        files[1].update(bytes=4,hex=hexbytes(PAYLOADS[2]),sha256=hashlib.sha256(PAYLOADS[2]).hexdigest())
        links[0]['target']='fixture_00001'
    return files,links

def rotation_snapshot(output,final=False):
    files,links=rotation_outputs(final)
    deadline=time.time()+10
    while True:
        try: actual=output_snapshot(output)
        except OSError as error:
            # FileStore replaces _current during rotation/reopen.
            if error.errno!=errno.ENOENT: raise
            actual=None
        if actual==(files,links): return {'files':actual[0],'symlinks':actual[1]}
        if time.time()>=deadline: raise ValueError('rotation snapshot differs: %r' % (actual,))
        time.sleep(0.05)

def run_lane(lane,restart_stage=None):
    if CASE=='restart' and restart_stage is None:
        before=run_lane(lane,'restart-before')
        after=run_lane(lane,'restart-after')
        return {'lane':lane,'case':'restart','status':'passed','before':before,'after':after}
    case=restart_stage or CASE
    network_check()
    directory = os.path.join(ROOT,'evidence',lane,restart_stage) if restart_stage else os.path.join(ROOT,'evidence',lane); output = os.path.join(ROOT,lane+'-output')
    os.makedirs(directory)
    if restart_stage=='restart-after':
        if not os.path.isdir(output) or os.path.islink(output): raise ValueError('missing owned first-stage output')
    else: os.makedirs(output)
    template=TEMPLATE if case in ('file','rotation','restart-before','restart-after') else os.path.join(os.path.dirname(TEMPLATE),'daemon_file_stores.conf.template' if case=='file-stores' else 'daemon_stores.conf.template')
    with open(template) as f:
        config=f.read().replace('@SEPARATE_TEMP_OUTPUT@',output).replace('@PORT@',str(PORT))
    if case in ('rotation','restart-before','restart-after'): config=config.replace('max_size=1000000','max_size=4').replace('target_write_size=16384','target_write_size=1')
    config_path=os.path.join(ROOT,lane+'.conf')
    with open(config_path,'w') as f: f.write(config)
    env=os.environ.copy();env.pop('LD_PRELOAD',None);env.pop('LD_AUDIT',None)
    env['LC_ALL']='C';env['TZ']='UTC'
    env.pop('LD_LIBRARY_PATH',None)
    env.update(TARGETS[lane].get('environment',{}))
    command=TARGETS[lane]['command'] + ['-c',config_path]
    result={'lane':lane,'case':case,'command':command,'uid':os.getuid(),'interfaces':os.listdir('/sys/class/net'),'records':[]}
    save_json(os.path.join(directory,'start.json'),result)
    process=None;conn=None
    with open(os.path.join(directory,'daemon.stdout'),'wb') as stdout, open(os.path.join(directory,'daemon.stderr'),'wb') as stderr:
        try:
            port_free()
            with open(os.devnull,'rb') as stdin:
                process=subprocess.Popen(command,env=env,stdin=stdin,stdout=stdout,stderr=stderr,preexec_fn=os.setsid)
            result['pid']=process.pid
            conn=connect_owned(process,PORT)
            result['owned_connection_inode']=connection_owner(process.pid,conn)
            records=result['records']
            for seq,name in enumerate([b'getName',b'getVersion',b'getStatus',b'getStatusDetails',b'getCounters'],1):
                call(conn,name,seq,b'\0',directory,records)
            if records[2]['value'] != 2: raise ValueError('fb303 not ALIVE')
            if restart_stage=='restart-after':
                result['after_restart']=rotation_snapshot(output)
                if records[4]['value']!={}: raise ValueError('fresh process counters not reset')
            if call(conn,b'Log',6,log_fields([]),directory,records) != 0: raise ValueError('empty Log not OK')
            entries,expected_delta,unused=case_data(case)
            if call(conn,b'Log',7,log_fields(entries),directory,records) != 0: raise ValueError('batch not OK')
            # Same bounded pause on both lanes; NullStore ignored counters are worker-side.
            if case=='stores': time.sleep(2)
            if case=='rotation': result['before_reinitialize']=rotation_snapshot(output)
            if restart_stage: result['before_stop']=rotation_snapshot(output,restart_stage=='restart-after')
            after=call(conn,b'getCounters',8,b'\0',directory,records)
            if case=='rotation':
                initial_delta={key:after.get(key,0)-records[4]['value'].get(key,0) for key in set(after)|set(records[4]['value'])}
                initial_delta={key:value for key,value in initial_delta.items() if value}
                if initial_delta!={'fixture:received good':2,'scribe_overall:received good':2}: raise ValueError('initial rotation counter delta differs')
                call(conn,b'reinitialize',9,b'\0',directory,records,oneway=True)
                if call(conn,b'getStatus',10,b'\0',directory,records)!=2: raise ValueError('reinitialize not ALIVE')
                result['after_reinitialize']=rotation_snapshot(output)
                if call(conn,b'Log',11,log_fields([(b'fixture',b'Z')]),directory,records)!=0: raise ValueError('post-reinitialize Log not OK')
                result['after_append']=rotation_snapshot(output,final=True)
                after=call(conn,b'getCounters',12,b'\0',directory,records)
            before=records[4]['value']
            delta={key:after.get(key,0)-before.get(key,0) for key in set(before)|set(after)}
            delta={key:value for key,value in delta.items() if value}
            if delta != expected_delta: raise ValueError('counter delta differs: %r' % delta)
            result['counter_delta']=delta
            if restart_stage=='restart-before':
                # This PID/session was created and socket ownership checked above.
                if process.poll() is not None: raise ValueError('child exited before injected crash')
                os.killpg(process.pid,signal.SIGKILL)
            else: call(conn,b'shutdown',13 if case=='rotation' else 9,b'\0',directory,records,oneway=True)
            conn.close();conn=None
            deadline=time.time()+10
            while process.poll() is None and time.time()<deadline: time.sleep(0.05)
            if process.poll() is None: raise ValueError('shutdown timeout')
            result['exit']=process.returncode
            expected_exit=-signal.SIGKILL if restart_stage=='restart-before' else 0
            if process.returncode != expected_exit: raise ValueError('unexpected child exit')
            files,links=output_snapshot(output)
            result['files']=files;result['symlinks']=links
            expected_files,expected_links=expected_outputs(case)
            if files!=expected_files or links!=expected_links:
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

def compare_lanes(old,new,case='file'):
    if case=='restart':
        for lane in (old,new):
            if lane.get('case')!='restart' or lane.get('status')!='passed': raise ValueError('incomplete restart lane')
        phases={phase:compare_lanes(old[phase],new[phase],target) for phase,target in (('before','restart-before'),('after','restart-after'))}
        return {'case':'restart','status':'passed' if all(p['status']=='passed' for p in phases.values()) else 'failed','phases':phases}
    methods=METHODS if case!='rotation' else METHODS[:8]+['reinitialize','getStatus','Log','getCounters','shutdown']
    if case=='restart-before': methods=METHODS[:8]
    for lane in (old,new):
        if lane.get('status') != 'passed' or len(lane.get('records',[])) != len(methods):
            raise ValueError('incomplete or failed lane')
        if [r['method'] for r in lane['records']] != methods:
            raise ValueError('unexpected RPC sequence')
        if [r['sequence'] for r in lane['records']] != list(range(1,len(methods)+1)):
            raise ValueError('unexpected sequence IDs')
        if lane.get('case','file') != case: raise ValueError('comparison case mismatch')
        if lane['counter_delta'] != case_data(case)[1]:
            raise ValueError('unexpected counter delta')
        for record in lane['records']:
            seq=record['sequence'];name=record['method'].encode('ascii')
            fields=b'\0'
            if seq == 6: fields=log_fields([])
            if seq == 7: fields=log_fields(case_data(case)[0])
            if case=='rotation' and seq==11: fields=log_fields([(b'fixture',b'Z')])
            oneway=record['method'] in ('shutdown','reinitialize')
            if record.get('oneway') != oneway or record['request_hex'] != hexbytes(framed(name,seq,fields,oneway)):
                raise ValueError('unexpected recorded request')
            if not oneway:
                wire=binascii.unhexlify(record['reply_hex'])
                if len(wire)<4 or struct.unpack('>I',wire[:4])[0] != len(wire)-4 or not 0<len(wire)-4<=MAX_REPLY:
                    raise ValueError('invalid recorded reply frame')
                if parse_reply(wire[4:],name,seq) != record['value']:
                    raise ValueError('recorded reply/value mismatch')
            elif 'reply_hex' in record:
                raise ValueError('oneway shutdown/reinitialize must not record a response')
        expected_files,expected_links=expected_outputs(case)
        if lane['files'] != expected_files:
            raise ValueError('unexpected output file')
        if lane['symlinks'] != expected_links:
            raise ValueError('unexpected output symlink')
    if case=='file-stores':
        for lane in (old,new):
            if lane['records'][2]['value']!=2 or any(lane['records'][i]['value']!=0 for i in (5,6)):
                raise ValueError('file store ALIVE/Log OK result differs')
            before=lane['records'][4]['value'];after=lane['records'][7]['value']
            delta={key:after.get(key,0)-before.get(key,0) for key in set(before)|set(after)}
            if {key:value for key,value in delta.items() if value}!=case_data(case)[1]:
                raise ValueError('recorded file store counters differ')
    if case in ('restart-before','restart-after'):
        for lane in (old,new):
            expected_exit=-signal.SIGKILL if case=='restart-before' else 0
            if lane.get('cleanup_exit')!=expected_exit: raise ValueError('restart cleanup not confirmed')
            if lane['records'][2]['value']!=2 or any(lane['records'][i]['value']!=0 for i in (5,6)):
                raise ValueError('restart ALIVE/Log OK result differs')
            expected_files,expected_links=expected_outputs(case)
            if lane.get('before_stop')!={'files':expected_files,'symlinks':expected_links}: raise ValueError('missing crash/restart phase bytes')
            before=lane['records'][4]['value'];after=lane['records'][7]['value']
            delta={key:after.get(key,0)-before.get(key,0) for key in set(before)|set(after)}
            if {key:value for key,value in delta.items() if value}!=case_data(case)[1]: raise ValueError('recorded restart counter delta differs')
            if case=='restart-after':
                files,links=rotation_outputs(False)
                if before!={} or lane.get('after_restart')!={'files':files,'symlinks':links}: raise ValueError('restart did not preserve files/reset counters')
    checks={}
    for a,b in zip(old['records'],new['records']):
        checks['request-%d'%a['sequence']]=a['request_hex']==b['request_hex']
        if a['method'] not in ('getVersion','shutdown','reinitialize'):
            checks['reply-%d'%a['sequence']]=a['reply_hex']==b['reply_hex']
    if case=='rotation':
        for lane in (old,new):
            if lane['records'][9]['value']!=2 or lane['records'][10]['value']!=0:
                raise ValueError('reinitialize status or append Log result differs')
            before=lane['records'][4]['value']
            for index,count in ((7,2),(11,3)):
                after=lane['records'][index]['value']
                delta={key:after.get(key,0)-before.get(key,0) for key in set(before)|set(after)}
                delta={key:value for key,value in delta.items() if value}
                if delta!={'fixture:received good':count,'scribe_overall:received good':count}:
                    raise ValueError('recorded rotation counter delta differs')
        for phase in ('before_reinitialize','after_reinitialize','after_append'):
            expected_files,expected_links=rotation_outputs(phase=='after_append')
            expected={'files':expected_files,'symlinks':expected_links}
            if old.get(phase)!=expected or new.get(phase)!=expected: raise ValueError('missing or wrong rotation phase '+phase)
            checks[phase]=old[phase]==new[phase]
    checks['counter-delta']=old['counter_delta']==new['counter_delta']
    checks['files']=old['files']==new['files']
    checks['symlinks']=old['symlinks']==new['symlinks']
    checks['exit']=old['exit']==new['exit']==(-signal.SIGKILL if case=='restart-before' else 0)
    checks['versions']=old['records'][1]['value']==new['records'][1]['value']==hexbytes(b'2.2')
    result={'status':'passed' if all(checks.values()) else 'failed','case':case,'checks':checks,'old_version_hex':old['records'][1]['value'],'modern_version_hex':new['records'][1]['value'],'python':sys.version,'scope':'bounded synthetic production daemon differential; distinct old/new userlands/ABIs'}
    return result

def main():
    global ROOT, PORT, TARGETS, CASE
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-isolated-daemons',action='store_true',help='explicitly opt in to launching the two supplied targets')
    parser.add_argument('--targets',required=True,help='JSON with old/modern command arrays and explicit environment maps')
    parser.add_argument('--output',required=True,help='new directory outside this checkout')
    parser.add_argument('--port',type=int,default=14630)
    parser.add_argument('--case',choices=('file','stores','rotation','restart','spool','mixed-spool','file-stores','performance','fb303','mapping','game-profile')+SCENARIO_CASES,default='file')
    args=parser.parse_args()
    if not args.run_isolated_daemons: parser.error('actual daemon execution requires --run-isolated-daemons')
    network_check()
    if not 1024 <= args.port <= 65535: parser.error('use an unprivileged TCP port')
    PORT=args.port
    CASE=args.case
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
    if CASE in ('spool','mixed-spool','game-profile')+SCENARIO_CASES:
        if PORT==65535: parser.error('%s case requires two unprivileged ports'%CASE)
        port_free(PORT+1)
    if CASE=='mapping':
        if PORT>65532:parser.error('mapping case requires four unprivileged ports')
        for port in (PORT+1,PORT+2,PORT+3):port_free(port)
    os.makedirs(ROOT);os.makedirs(os.path.join(ROOT,'evidence'))
    if CASE in ('spool','mixed-spool'):
        import daemon_spool_case
        old=daemon_spool_case.run_lane(sys.modules[__name__],'old','modern' if CASE=='mixed-spool' else None)
        new=daemon_spool_case.run_lane(sys.modules[__name__],'modern','old' if CASE=='mixed-spool' else None)
        result=daemon_spool_case.compare_lanes(sys.modules[__name__],old,new,CASE)
    elif CASE=='fb303':
        import daemon_fb303_case,daemon_spool_case
        old=daemon_fb303_case.run_lane(sys.modules[__name__],daemon_spool_case,'old')
        new=daemon_fb303_case.run_lane(sys.modules[__name__],daemon_spool_case,'modern')
        result=daemon_fb303_case.compare_lanes(sys.modules[__name__],old,new)
    elif CASE=='mapping':
        import daemon_mapping_case,daemon_spool_case
        old=daemon_mapping_case.run_lane(sys.modules[__name__],daemon_spool_case,'old')
        new=daemon_mapping_case.run_lane(sys.modules[__name__],daemon_spool_case,'modern')
        result=daemon_mapping_case.compare_lanes(sys.modules[__name__],old,new)
    elif CASE=='game-profile':
        import daemon_game_profile_case,daemon_spool_case
        old=daemon_game_profile_case.run_lane(sys.modules[__name__],daemon_spool_case,'old')
        new=daemon_game_profile_case.run_lane(sys.modules[__name__],daemon_spool_case,'modern')
        result=daemon_game_profile_case.compare_lanes(sys.modules[__name__],old,new)
    elif CASE in SCENARIO_CASES:
        import daemon_scenario_case,daemon_spool_case
        old=daemon_scenario_case.run_lane(sys.modules[__name__],daemon_spool_case,CASE,'old')
        new=daemon_scenario_case.run_lane(sys.modules[__name__],daemon_spool_case,CASE,'modern')
        result=daemon_scenario_case.compare_lanes(sys.modules[__name__],old,new,CASE)
    elif CASE=='performance':
        import daemon_performance_case,daemon_spool_case
        result=daemon_performance_case.run_comparison(sys.modules[__name__],daemon_spool_case)
    else:
        old=run_lane('old');new=run_lane('modern')
        result=compare_lanes(old,new,CASE)
    save_json(ROOT+'/evidence/comparison.json',result)
    if result['status']!='passed': raise ValueError('old/new comparison differed')
    print(json.dumps(result,sort_keys=True))

if __name__=='__main__': main()
