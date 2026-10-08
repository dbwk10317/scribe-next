"""Bounded downstream-off disk spool/full replay case for daemon_differential."""
from contextlib import contextmanager
import binascii, hashlib, os, struct, subprocess, time, traceback

ENTRIES=[(b'fixture',b'A\x00B\n\xff'),(b'fixture',b'tail')]
SPOOL=b''.join(struct.pack('<I',len(value))+value for category,value in ENTRIES)
PAYLOAD=b''.join(value for category,value in ENTRIES)

def outputs(c,data,spool=False):
    name='spool_00000' if spool else 'fixture_00000'
    files=[{'path':name,'bytes':len(data),'hex':c.hexbytes(data),'sha256':hashlib.sha256(data).hexdigest()}]
    return {'files':files,'symlinks':[] if spool else [{'path':'fixture_current','target':name}]}

def wait_output(c,path,expected,timeout=20):
    deadline=time.time()+timeout
    while True:
        try:
            files,links=c.output_snapshot(path)
            actual={'files':files,'symlinks':links}
        except OSError as error:
            if error.errno!=c.errno.ENOENT: raise
            actual=None
        if actual==expected: return actual
        if time.time()>=deadline: raise ValueError('spool/replay output differs: %r' % actual)
        time.sleep(0.05)

@contextmanager
def owned_daemon(c,lane,role,config,port,readiness_timeout=10,target_lane=None):
    target_lane=lane if target_lane is None else target_lane
    c.network_check();c.port_free(port)
    directory=os.path.join(c.ROOT,'evidence',lane,role);os.makedirs(directory)
    config_path=os.path.join(c.ROOT,lane+'-'+role+'.conf')
    with open(config_path,'w') as f:f.write(config)
    target=c.TARGETS[target_lane];env=os.environ.copy()
    for key in ('LD_PRELOAD','LD_AUDIT','LD_LIBRARY_PATH'):env.pop(key,None)
    env.update({'LC_ALL':'C','TZ':'UTC'});env.update(target.get('environment',{}))
    command=target['command']+['-c',config_path]
    result={'lane':lane,'target_lane':target_lane,'role':role,'command':command,'uid':os.getuid(),
            'interfaces':os.listdir('/sys/class/net'),'records':[],'status':'failed'}
    c.save_json(os.path.join(directory,'start.json'),result)
    process=None;conn=None
    with open(os.path.join(directory,'daemon.stdout'),'wb') as stdout,open(os.path.join(directory,'daemon.stderr'),'wb') as stderr:
        try:
            result['started_at']=time.time()
            with open(os.devnull,'rb') as stdin:
                process=subprocess.Popen(command,env=env,stdin=stdin,stdout=stdout,stderr=stderr,start_new_session=True)
            result['pid']=process.pid
            conn=c.connect_owned(process,port,readiness_timeout)
            result['owned_connection_inode']=c.connection_owner(process.pid,conn)
            yield process,conn,result,directory
        except BaseException:
            result['error']=traceback.format_exc();result['status']='failed';raise
        finally:
            if conn:conn.close()
            try:
                if process:result['cleanup_exit']=c.cleanup_process(process)
                c.port_free(port)
            except BaseException:
                result['status']='failed';result['cleanup_error']=traceback.format_exc();raise
            finally:c.save_json(os.path.join(directory,'result.json'),result)

def shutdown(c,session,sequence):
    process,conn,result,directory=session
    c.call(conn,b'shutdown',sequence,b'\0',directory,result['records'],oneway=True)
    deadline=time.time()+10
    while process.poll() is None and time.time()<deadline:time.sleep(0.05)
    if process.poll() is None or process.returncode!=0:raise ValueError('spool daemon shutdown failed')
    result['exit']=process.returncode;result['status']='passed'

def upstream_counters(count,sent=0):
    counters={'fixture:retries':1,'scribe_overall:retries':1,
              'fixture:received good':count,'scribe_overall:received good':count}
    if sent:counters['scribe_overall:sent']=sent
    return counters

def run_lane(c,lane,downstream_lane=None):
    downstream_lane=lane if downstream_lane is None else downstream_lane
    spool_path=os.path.join(c.ROOT,lane+'-spool');down_path=os.path.join(c.ROOT,lane+'-downstream')
    os.makedirs(spool_path);os.makedirs(down_path)
    with open(os.path.join(os.path.dirname(__file__),'daemon_spool.conf.template')) as f:
        up_config=f.read().replace('@PORT@',str(c.PORT)).replace('@DOWNSTREAM_PORT@',str(c.PORT+1)).replace('@SEPARATE_TEMP_OUTPUT@',spool_path)
    with open(c.TEMPLATE) as f:
        down_config=f.read().replace('@PORT@',str(c.PORT+1)).replace('@SEPARATE_TEMP_OUTPUT@',down_path)
    # Both ports must be absent before any upstream retry can contact downstream.
    c.port_free(c.PORT);c.port_free(c.PORT+1)
    result={'case':'spool' if downstream_lane==lane else 'mixed-spool',
            'lane':lane,'downstream_lane':downstream_lane,'status':'failed'}
    result_path=os.path.join(c.ROOT,'evidence',lane,'spool-result.json')
    os.makedirs(os.path.dirname(result_path));c.save_json(result_path,result)
    with owned_daemon(c,lane,'upstream',up_config,c.PORT) as upstream:
        process,conn,up,directory=upstream;records=up['records'];result['upstream']=up
        c.call(conn,b'getVersion',1,b'\0',directory,records)
        if c.call(conn,b'Log',2,c.log_fields(ENTRIES),directory,records)!=0:raise ValueError('spool Log not OK')
        result['spooled']=wait_output(c,spool_path,outputs(c,SPOOL,True),timeout=8)
        c.save_json(result_path,result)
        if c.call(conn,b'getCounters',3,b'\0',directory,records)!=upstream_counters(2):raise ValueError('initial spool counters differ')
        if c.call(conn,b'getStatus',4,b'\0',directory,records)!=5:raise ValueError('offline relay not WARNING')
        remaining=8-(time.time()-up['started_at'])
        if remaining<=0:raise ValueError('downstream missed first-retry readiness window')
        with owned_daemon(c,lane,'downstream',down_config,c.PORT+1,remaining,target_lane=downstream_lane) as downstream:
            unused,dc,down,dd=downstream;dr=down['records'];result['downstream']=down
            c.call(dc,b'getVersion',1,b'\0',dd,dr)
            if c.call(dc,b'getStatus',2,b'\0',dd,dr)!=2:raise ValueError('downstream not ALIVE')
            if c.call(dc,b'getCounters',3,b'\0',dd,dr)!={}:raise ValueError('downstream counters not fresh')
            if time.time()-up['started_at']>=8:raise ValueError('downstream missed first-retry readiness window')
            result['replayed']=wait_output(c,down_path,outputs(c,PAYLOAD))
            result['drained']=wait_output(c,spool_path,{'files':[],'symlinks':[]})
            c.save_json(result_path,result)
            if c.call(conn,b'getCounters',5,b'\0',directory,records)!=upstream_counters(2,2):raise ValueError('replay counters differ')
            if c.call(conn,b'getStatus',6,b'\0',directory,records)!=2:raise ValueError('relay did not recover ALIVE')
            if c.call(conn,b'Log',7,c.log_fields([(b'fixture',b'Z')]),directory,records)!=0:raise ValueError('streaming Log not OK')
            result['streamed']=wait_output(c,down_path,outputs(c,PAYLOAD+b'Z'))
            c.save_json(result_path,result)
            if c.call(conn,b'getCounters',8,b'\0',directory,records)!=upstream_counters(3,3):raise ValueError('streaming counters differ')
            if c.call(dc,b'getCounters',4,b'\0',dd,dr)!={'fixture:received good':3,'scribe_overall:received good':3}:raise ValueError('downstream counters differ')
            shutdown(c,upstream,9);shutdown(c,downstream,5)
    files,links=c.output_snapshot(spool_path);result['final_spool']={'files':files,'symlinks':links}
    files,links=c.output_snapshot(down_path);result['final_downstream']={'files':files,'symlinks':links}
    if result['final_spool']!={'files':[],'symlinks':[]} or result['final_downstream']!=outputs(c,PAYLOAD+b'Z'):
        c.save_json(result_path,result);raise ValueError('shutdown changed spool/replay outputs')
    result['status']='passed'
    c.save_json(result_path,result)
    return result

def compare_lanes(c,old,new,case='spool'):
    if case not in ('spool','mixed-spool'):raise ValueError('unknown spool comparison case')
    expected={'upstream':[(b'getVersion',b'\0'),(b'Log',c.log_fields(ENTRIES)),(b'getCounters',b'\0'),(b'getStatus',b'\0'),
                          (b'getCounters',b'\0'),(b'getStatus',b'\0'),(b'Log',c.log_fields([(b'fixture',b'Z')])),(b'getCounters',b'\0'),(b'shutdown',b'\0')],
              'downstream':[(b'getVersion',b'\0'),(b'getStatus',b'\0'),(b'getCounters',b'\0'),(b'getCounters',b'\0'),(b'shutdown',b'\0')]}
    values={'upstream':[c.hexbytes(b'2.2'),0,upstream_counters(2),5,upstream_counters(2,2),2,0,upstream_counters(3,3)],
            'downstream':[c.hexbytes(b'2.2'),2,{}, {'fixture:received good':3,'scribe_overall:received good':3}]}
    snapshots={'spooled':outputs(c,SPOOL,True),'replayed':outputs(c,PAYLOAD),'drained':{'files':[],'symlinks':[]},'streamed':outputs(c,PAYLOAD+b'Z'),'final_spool':{'files':[],'symlinks':[]},'final_downstream':outputs(c,PAYLOAD+b'Z')}
    checks={}
    for lane,upstream_lane,downstream_lane in ((old,'old','modern'),(new,'modern','old')):
        if lane.get('case')!=case or lane.get('status')!='passed':raise ValueError('incomplete spool lane')
        if case=='mixed-spool':
            if lane.get('lane')!=upstream_lane or lane.get('downstream_lane')!=downstream_lane:
                raise ValueError('mixed spool direction differs')
            for role,target_lane in (('upstream',upstream_lane),('downstream',downstream_lane)):
                part=lane[role]
                command=c.TARGETS[target_lane]['command']+['-c',os.path.join(c.ROOT,upstream_lane+'-'+role+'.conf')]
                if part.get('target_lane')!=target_lane or part.get('command')!=command:
                    raise ValueError('mixed spool target identity differs')
        for phase,wanted in snapshots.items():
            if lane.get(phase)!=wanted:raise ValueError('missing or wrong spool/replay phase '+phase)
        for role,requests in expected.items():
            part=lane[role];records=part['records']
            if part.get('status')!='passed' or part.get('exit')!=0 or part.get('cleanup_exit')!=0 or len(records)!=len(requests):raise ValueError('incomplete spool child')
            for seq,(name,fields) in enumerate(requests,1):
                r=records[seq-1];oneway=name==b'shutdown'
                if r['method']!=name.decode() or r['sequence']!=seq or r.get('oneway')!=oneway or r['request_hex']!=c.hexbytes(c.framed(name,seq,fields,oneway)):raise ValueError('spool request differs')
                if oneway:
                    if 'reply_hex' in r:raise ValueError('oneway spool shutdown has reply')
                else:
                    wire=binascii.unhexlify(r['reply_hex'])
                    if len(wire)<4 or not 0<len(wire)-4<=c.MAX_REPLY or struct.unpack('>I',wire[:4])[0]!=len(wire)-4:raise ValueError('invalid spool reply frame')
                    if c.parse_reply(wire[4:],name,seq)!=r['value'] or r['value']!=values[role][seq-1]:raise ValueError('spool reply value differs')
    for role,requests in expected.items():
        for seq,(name,unused) in enumerate(requests,1):
            a=old[role]['records'][seq-1];b=new[role]['records'][seq-1]
            checks[role+'-request-%d'%seq]=a['request_hex']==b['request_hex']
            if name not in (b'getVersion',b'shutdown'):checks[role+'-reply-%d'%seq]=a['reply_hex']==b['reply_hex']
    for phase in snapshots:checks[phase]=old[phase]==new[phase]
    result={'case':case,'status':'passed' if all(checks.values()) else 'failed','checks':checks,
            'scope':'bounded absent downstream/full ordinary spool replay/streaming; no partial replay or durability claim'}
    if case=='mixed-spool':
        result['directions']=[{'upstream':'old','downstream':'modern'},{'upstream':'modern','downstream':'old'}]
        result['target_commands']={lane:c.TARGETS[lane]['command'] for lane in ('old','modern')}
        result['scope']='bounded mixed old/modern relay with same-version ordinary spool writer/replay; no cross-version spool-reader, partial replay or durability claim'
    return result
