"""Bounded real dynamic mapping/TTL case; public source expectations, no fixes."""
from __future__ import print_function
import binascii, os, socket, struct, threading, time, traceback

TTL=5
PAYLOADS=[b'A0\0\xff',b'A1\n',b'B0',b'B1',b'A2']
FAILURE=b'fixture mapping unavailable'
clock=getattr(time,'monotonic',time.time)


def header(c,body,name):
    cursor=c.Cursor(body)
    if (cursor.string(),cursor.number('>B'))!=(name,1):raise ValueError('unexpected peer method/type')
    return cursor,cursor.number('>i')


def mapping_request(c,body):
    cursor,seq=header(c,body,b'getMapping')
    if cursor.take(3)!=b'\x0b\0\x01' or cursor.string()!=b'fixture' or cursor.take(1)!=b'\0' or cursor.offset!=len(body):
        raise ValueError('mapping category/IDL fields differ')
    return seq


def log_request(c,body):
    cursor,seq=header(c,body,b'Log')
    if cursor.take(4)!=b'\x0f\0\x01\x0c':raise ValueError('unexpected Log fields')
    count=cursor.number('>i')
    if not 1<=count<=8:raise ValueError('unexpected tiny Log count')
    entries=[]
    for unused in range(count):
        if cursor.take(3)!=b'\x0b\0\x01':raise ValueError('category field differs')
        category=cursor.string()
        if cursor.take(3)!=b'\x0b\0\x02':raise ValueError('message field differs')
        payload=cursor.string()
        if category!=b'fixture' or payload not in PAYLOADS or cursor.take(1)!=b'\0':raise ValueError('peer payload differs')
        entries.append(payload)
    if cursor.take(1)!=b'\0' or cursor.offset!=len(body):raise ValueError('trailing Log fields')
    return seq,entries


def reply(c,name,seq,fields):
    body=c.string(name)+b'\x02'+struct.pack('>i',seq)+fields+b'\0'
    return struct.pack('>I',len(body))+body


def mapping_reply(c,seq,mode,port):
    if mode=='fail':
        fields=b'\x0c\0\x01\x0b\0\x01'+c.string(FAILURE)+b'\x08\0\x02'+struct.pack('>i',1)+b'\0'
    else:
        fields=b'\x0d\0\0\x08\x0c'+struct.pack('>ii',1,1)+b'\x0b\0\x02'+c.string(b'127.0.0.1')+b'\x08\0\x03'+struct.pack('>i',port)+b'\0'
    return reply(c,b'getMapping',seq,fields)


def config(c,port_a,port_mapping,missing=None):
    values=[('port',c.PORT),('num_thrift_server_threads',2),('max_msg_per_second',0),('check_interval',1)]
    text=''.join('%s=%s\n'%item for item in values)+'<store>\ncategory=fixture\ntype=network\n'
    settings=[('remote_host','127.0.0.1'),('remote_port',port_a),('dynamic_config_type','thrift_bucket'),
              ('bucket_id',1),('bucket_updater_host','127.0.0.1'),('bucket_updater_port',port_mapping),
              ('bucket_updater_ttl',TTL),('use_conn_pool','no'),('timeout',1000),
              ('target_write_size',1),('max_write_interval',1),('retry_interval_range',1)]
    return text+''.join('%s=%s\n'%item for item in settings if item[0]!=missing)+'</store>\n'


class Peers(object):
    """Three retained loopback listeners; independent IDL replies, one role/thread."""
    def __init__(self,c):
        self.c=c;self.mode='A';self.stop=threading.Event();self.lock=threading.Lock()
        self.records=[];self.errors=[];self.listeners={};self.connections=[];self.threads=[]
        self.ports={'A':c.PORT+1,'B':c.PORT+2,'mapping':c.PORT+3}
    def __enter__(self):
        self.c.network_check()
        try:
            for role,port in self.ports.items():
                self.c.port_free(port)
                listener=socket.socket();listener.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
                listener.bind(('127.0.0.1',port));listener.listen(4);listener.settimeout(.2)
                self.listeners[role]=listener
                worker=threading.Thread(target=self.serve,args=(role,listener));worker.daemon=True
                self.threads.append(worker);worker.start()
            return self
        except BaseException:
            self.__exit__(None,None,None);raise
    def __exit__(self,kind,error,tb):
        self.stop.set()
        for conn in list(self.connections)+list(self.listeners.values()):
            try:conn.shutdown(socket.SHUT_RDWR)
            except socket.error:pass
            conn.close()
        for thread in self.threads:
            thread.join(3)
            if thread.is_alive():raise ValueError('owned peer thread did not stop')
        for port in self.ports.values():self.c.port_free(port)
        if not kind:self.check()
    def check(self):
        if self.errors:raise ValueError('peer failed: '+repr(self.errors))
    def snapshot(self):
        with self.lock:return [dict(record) for record in self.records]
    def set_mode(self,mode):
        with self.lock:
            start=len(self.records);self.mode=mode
            self.records.append({'role':'control','mode':mode,'wall':time.time(),'monotonic':clock()})
        return start
    def wait(self,predicate,timeout=12):
        until=clock()+timeout
        while True:
            self.check();records=self.snapshot()
            value=predicate(records)
            if value:return value
            if clock()>=until:raise ValueError('peer observation deadline: '+repr(records))
            time.sleep(.01)
    def serve(self,role,listener):
        try:
            while not self.stop.is_set():
                try:conn,address=listener.accept()
                except socket.timeout:continue
                if address[0]!='127.0.0.1':raise ValueError('non-loopback peer')
                with self.lock:self.connections.append(conn)
                try:
                    conn.settimeout(3)
                    while not self.stop.is_set():
                        conn.settimeout(.2)
                        try:first=conn.recv(4)
                        except socket.timeout:continue
                        if not first:break
                        conn.settimeout(3)
                        size_bytes=first+self.c.recv_exact(conn,4-len(first))
                        size=struct.unpack('>I',size_bytes)[0]
                        if not 0<size<=65536:raise ValueError('unexpected bounded fixture frame')
                        body=self.c.recv_exact(conn,size)
                        record={'role':role,'request_hex':self.c.hexbytes(size_bytes+body)}
                        try:
                            if role=='mapping':
                                seq=mapping_request(self.c,body)
                                with self.lock:mode=self.mode
                                response=mapping_reply(self.c,seq,mode,self.ports.get(mode,0));record['mode']=mode
                            else:
                                seq,entries=log_request(self.c,body)
                                response=reply(self.c,b'Log',seq,b'\x08\0\0'+struct.pack('>i',0))
                                record['payloads_hex']=[self.c.hexbytes(value) for value in entries]
                            conn.sendall(response)
                            record['reply_hex']=self.c.hexbytes(response)
                            with self.lock:
                                record.update(wall=time.time(),monotonic=clock());self.records.append(record)
                        except BaseException as error:
                            with self.lock:
                                record.update(error=repr(error),wall=time.time(),monotonic=clock());self.records.append(record)
                            raise
                finally:
                    conn.close()
                    with self.lock:self.connections.remove(conn)
        except BaseException as error:
            if not self.stop.is_set():
                with self.lock:self.errors.append(repr(error))


def counters(count):
    return {'fixture:received good':count,'scribe_overall:received good':count,'scribe_overall:sent':count}


def exercise(c,helpers,lane,peers,missing=None):
    role=missing or 'ttl';result={'case':role,'status':'failed','ports':dict(peers.ports)}
    with helpers.owned_daemon(c,lane,role,config(c,peers.ports['A'],peers.ports['mapping'],missing),c.PORT) as session:
        process,conn,daemon,directory=session;seq=[0]
        def call(name,fields=b'\0'):
            seq[0]+=1;return c.call(conn,name,seq[0],fields,directory,daemon['records'])
        if call(b'getVersion')!=c.hexbytes(b'2.2'):raise ValueError('version differs')
        count=[0]
        def send(index,destination):
            payload=PAYLOADS[index]
            if call(b'Log',c.log_fields([(b'fixture',payload)]))!=0:raise ValueError('Log not accepted')
            count[0]+=1
            peers.wait(lambda records:any(r['role']==destination and c.hexbytes(payload) in r.get('payloads_hex',[]) for r in records),3)
            until=clock()+3
            while call(b'getCounters')!=counters(count[0]):
                if clock()>=until:raise ValueError('ordinary counters differ')
                time.sleep(.01)
            if call(b'getStatus')!=2:raise ValueError('normal/retained destination is not ALIVE')
        if missing:
            send(0,'A')
            if any(r['role']=='mapping' for r in peers.snapshot()):raise ValueError('invalid dynamic config performed mapping RPC')
        else:
            initial=peers.wait(lambda records:next((r for r in records if r['role']=='mapping' and r['mode']=='A'),None))
            send(0,'A');before=len([r for r in peers.snapshot() if r['role']=='mapping'])
            peers.set_mode('B');send(1,'A')
            if clock()-initial['monotonic']>=TTL-1:raise ValueError('cache proof missed guarded pre-expiry window')
            if len([r for r in peers.snapshot() if r['role']=='mapping'])!=before:raise ValueError('cached use fetched mapping again')
            result['cache_observed']=True
            result['cache_proof']={'before_fetches':before,'after_fetches':len([r for r in peers.snapshot() if r['role']=='mapping']),
                                   'elapsed':clock()-initial['monotonic'],'ttl':TTL}
            mapped=peers.wait(lambda records:next((r for r in records if r['role']=='mapping' and r['mode']=='B'),None))
            if int(mapped['wall'])<=int(initial['wall'])+TTL:raise ValueError('mapping changed before source-defined TTL expiry')
            send(2,'B')
            start=peers.set_mode('fail')
            peers.wait(lambda records:any(r['role']=='mapping' and r['mode']=='fail' for r in records[start:]))
            send(3,'B')
            start=peers.set_mode('A')
            peers.wait(lambda records:any(r['role']=='mapping' and r['mode']=='A' for r in records[start:]),5)
            send(4,'A')
        result['counters']=counters(count[0]);result['status_value']=2
        helpers.shutdown(c,session,seq[0]+1)
    result.update(status='passed',exit=daemon['exit'],cleanup_exit=daemon['cleanup_exit'],records=daemon['records'])
    if missing:
        logs=b''.join(open(os.path.join(directory,'daemon.'+name),'rb').read() for name in ('stdout','stderr'))
        warning=b'Missing bucket_id' if missing=='bucket_id' else b'bucket_updater_host and bucket_updater_port is needed'
        if warning not in logs:raise ValueError('original dynamic configuration warning missing')
        result['warning']=warning.decode('ascii')
    result['peers']=peers.snapshot()
    return result


def run_lane(c,helpers,lane):
    result={'case':'mapping','status':'failed','scenarios':[]}
    directory=os.path.join(c.ROOT,'evidence',lane)
    if not os.path.isdir(directory):os.makedirs(directory)
    path=os.path.join(directory,'mapping-result.json');c.save_json(path,result)
    try:
        for missing in (None,'bucket_id','bucket_updater_port'):
            result['active_case']=missing or 'ttl';peers=Peers(c)
            try:
                with peers:item=exercise(c,helpers,lane,peers,missing)
            finally:
                c.save_json(os.path.join(directory,(missing or 'ttl')+'-peers.json'),
                            {'records':peers.snapshot(),'errors':list(peers.errors),'ports':peers.ports})
            item['peer_cleanup']=True;result['scenarios'].append(item)
        result['status']='passed';validate(c,result)
    except BaseException:
        result['status']='failed';result['error']=traceback.format_exc();raise
    finally:c.save_json(path,result)
    return result


def validate_rpc(c,scenario,missing):
    records=scenario.get('records',[]);payloads=[PAYLOADS[0]] if missing else PAYLOADS
    seen=0;shutdown=False;converged=False;status_seen=False
    for index,r in enumerate(records,1):
        name=r['method'].encode('ascii');oneway=name==b'shutdown'
        if r.get('sequence')!=index or r.get('oneway')!=oneway or r.get('exception',False):raise ValueError('RPC metadata differs')
        if name==b'Log':
            if seen>=len(payloads) or (seen and not status_seen):raise ValueError('extra Log/missing prior checkpoints')
            converged=False;status_seen=False
            fields=c.log_fields([(b'fixture',payloads[seen])]);seen+=1
        elif name in (b'getVersion',b'getCounters',b'getStatus',b'shutdown'):fields=b'\0'
        else:raise ValueError('unexpected mapping-case RPC')
        if r['request_hex']!=c.hexbytes(c.framed(name,index,fields,oneway)):raise ValueError('RPC request differs')
        if oneway:
            if index!=len(records) or 'reply_hex' in r or not status_seen:raise ValueError('shutdown is not final oneway/checkpoints incomplete')
            shutdown=True;continue
        wire=binascii.unhexlify(r['reply_hex'])
        if struct.unpack('>I',wire[:4])[0]!=len(wire)-4:raise ValueError('RPC reply length differs')
        value=c.parse_reply(wire[4:],name,index)
        if value!=r.get('value'):raise ValueError('RPC value metadata differs')
        if name==b'getVersion' and (index!=1 or value!=c.hexbytes(b'2.2')):raise ValueError('version differs')
        if name==b'Log' and value!=0:raise ValueError('Log ACK differs')
        if name==b'getStatus':
            if value!=2 or not converged:raise ValueError('status/counter convergence differs')
            status_seen=True
        if name==b'getCounters':
            expected={'fixture:received good':seen,'scribe_overall:received good':seen}
            sent=value.get('scribe_overall:sent',0)
            if not max(0,seen-1)<=sent<=seen:raise ValueError('sent counter differs')
            if sent:expected['scribe_overall:sent']=sent
            if value!=expected or status_seen:raise ValueError('received counter/key/order differs')
            if value==counters(seen):converged=True
    if not records or records[0]['method']!='getVersion' or seen!=len(payloads) or not shutdown:raise ValueError('incomplete RPC trace')


def validate_timeline(c,scenario,missing):
    records=scenario['peers']
    if any('wall' not in r or 'monotonic' not in r for r in records):raise ValueError('peer timing evidence missing')
    if any(records[i]['monotonic']>records[i+1]['monotonic'] for i in range(len(records)-1)):raise ValueError('peer trace is not chronological')
    if missing:
        if any(r['role'] in ('mapping','control') for r in records):raise ValueError('fallback used mapping/control')
        return
    # The same merged raw trace must prove causality, not independent endpoint lists.
    state='initial';initial=None;latest_b=None;fetches=0;cached=None;failed=False
    for r in records:
        role=r['role']
        if role=='mapping':
            mode=r['mode'];fetches+=1
            if state=='initial' and mode=='A' and initial is None:initial=r
            elif state=='cached' and mode=='B':
                if int(r['wall'])<=int(initial['wall'])+TTL:raise ValueError('B fetch before strict TTL expiry')
                latest_b=r;state='mapped_b'
            elif state in ('failure','b1') and mode=='fail':
                if not failed and int(r['wall'])<=int(latest_b['wall'])+TTL:raise ValueError('failed refresh before strict TTL expiry')
                failed=True
            elif state in ('mapped_b','b0') and mode=='B':
                if int(r['wall'])<=int(latest_b['wall'])+TTL:raise ValueError('repeated B fetch before strict TTL expiry')
                latest_b=r
            elif state=='recovery' and mode=='fail':pass # a request already in flight when control changed
            elif state=='recovery' and mode=='A':state='mapped_a'
            elif state=='done' and mode=='A':pass
            else:raise ValueError('mapping reply outside its observed phase')
        elif role=='control':
            if state=='a0' and r['mode']=='B':state='cache_pending'
            elif state=='b0' and r['mode']=='fail':state='failure'
            elif state=='b1' and r['mode']=='A':state='recovery'
            else:raise ValueError('mapping control outside its observed phase')
        elif role in ('A','B'):
            values=r['payloads_hex']
            expected={'initial':('A',PAYLOADS[0],'a0'),'cache_pending':('A',PAYLOADS[1],'cached'),
                      'mapped_b':('B',PAYLOADS[2],'b0'),'failure':('B',PAYLOADS[3],'b1'),
                      'mapped_a':('A',PAYLOADS[4],'done')}
            if state not in expected:raise ValueError('relay delivery outside its observed phase')
            destination,payload,next_state=expected[state]
            if role!=destination or values!=[c.hexbytes(payload)] or (state=='initial' and initial is None) or (state=='failure' and not failed):raise ValueError('relay phase payload/destination differs')
            if state=='cache_pending':
                if fetches!=1 or not 0<=r['monotonic']-initial['monotonic']<TTL-1:raise ValueError('raw cache evidence missing/late')
                cached=r
            state=next_state
        else:raise ValueError('unknown peer trace role')
    if state!='done' or cached is None:raise ValueError('incomplete phase trace')
    proof=scenario.get('cache_proof',{})
    if proof.get('before_fetches')!=1 or proof.get('after_fetches')!=1 or proof.get('ttl')!=TTL or not cached['monotonic']-initial['monotonic']<=proof.get('elapsed',TTL)<TTL-1:raise ValueError('cache metadata conflicts with raw trace')


def validate(c,result):
    if result.get('case')!='mapping' or result.get('status')!='passed' or len(result.get('scenarios',[]))!=3:raise ValueError('incomplete mapping lane')
    canonical=[]
    for scenario,missing in zip(result['scenarios'],(None,'bucket_id','bucket_updater_port')):
        count=1 if missing else 5
        if scenario.get('case')!=(missing or 'ttl') or scenario.get('status')!='passed' or scenario.get('exit')!=0 or scenario.get('cleanup_exit')!=0 or scenario.get('peer_cleanup') is not True or scenario.get('counters')!=counters(count) or scenario.get('status_value')!=2:
            raise ValueError('incomplete mapping scenario')
        if scenario.get('ports')!={'A':c.PORT+1,'B':c.PORT+2,'mapping':c.PORT+3}:raise ValueError('peer ports differ')
        validate_rpc(c,scenario,missing)
        validate_timeline(c,scenario,missing)
        routed={'A':[],'B':[]};modes=[]
        for record in scenario['peers']:
            if record['role']=='control':continue
            request=binascii.unhexlify(record['request_hex']);body=request[4:]
            if struct.unpack('>I',request[:4])[0]!=len(body):raise ValueError('peer frame length differs')
            if record['role']=='mapping':
                seq=mapping_request(c,body);mode=record['mode']
                if mode not in ('A','B','fail'):raise ValueError('mapping mode differs')
                if record['reply_hex']!=c.hexbytes(mapping_reply(c,seq,mode,scenario['ports'].get(mode,0))):raise ValueError('mapping reply/IDL/port differs')
                if not modes or modes[-1]!=mode:modes.append(mode)
            elif record['role']=='control':continue
            elif record['role'] in routed:
                seq,entries=log_request(c,body)
                if record['payloads_hex']!=[c.hexbytes(value) for value in entries] or record['reply_hex']!=c.hexbytes(reply(c,b'Log',seq,b'\x08\0\0'+struct.pack('>i',0))):raise ValueError('relay wire differs')
                routed[record['role']]+=entries
            else:raise ValueError('peer role differs')
        expected={'A':[PAYLOADS[0]] if missing else [PAYLOADS[0],PAYLOADS[1],PAYLOADS[4]],'B':[] if missing else [PAYLOADS[2],PAYLOADS[3]]}
        if routed!=expected or modes!=([] if missing else ['A','B','fail','A']):raise ValueError('source-defined mapping route/phase differs')
        if not missing:
            proof=scenario.get('cache_proof',{})
            if scenario.get('cache_observed') is not True or proof.get('before_fetches')!=1 or proof.get('after_fetches')!=1 or proof.get('ttl')!=TTL or not 0<=proof.get('elapsed',TTL)<TTL-1:raise ValueError('cache evidence missing/late')
        canonical.append({'case':scenario['case'],'routed':{key:[c.hexbytes(value) for value in values] for key,values in routed.items()},'mapping_phases':modes,'counters':scenario['counters'],'status':2})
    return canonical


def compare_lanes(c,old,new):
    a,b=validate(c,old),validate(c,new)
    if a!=b:raise ValueError('old/new dynamic mapping observations differ')
    return {'status':'passed','case':'mapping','checks':{'source_expected_routing':True,'cache_ttl_failure_recovery':True,'static_fallback_configs':True,'owned_cleanup':True},'scenarios':a,
            'limits':'unpooled direct store; public mapping-specific stats unavailable; repeated refresh calls retained raw, scheduler-dependent count not an equality verdict'}
