"""One fixed opt-in public old/new FileStore workload; Python3 monotonic client.

Reports measurements, not a performance pass threshold or durable-ACK promise.
"""
import errno,hashlib,math,os,stat,struct,sys,threading,time,traceback
PRODUCERS=4
MESSAGES=4096
BATCH=256
WARMUP=256
SIZE=1024
REPEATS=3
TOTAL=PRODUCERS*MESSAGES
TAIL=b'A\0B\n\xff'*203+b'x'


def payload(producer,index):
    return struct.pack('>II',producer,index)+TAIL


def prepare_batch(c,producer,first,sequence):
    entries=[(b'fixture',payload(producer,i)) for i in range(first,first+BATCH)]
    wire=c.framed(b'Log',sequence,c.log_fields(entries))
    return wire,hashlib.sha256(wire).hexdigest()


def batch_record(c,conn,producer,first,sequence,prepared=None):
    wire,digest=prepare_batch(c,producer,first,sequence) if prepared is None else prepared
    started=time.monotonic();conn.sendall(wire)
    prefix=c.recv_exact(conn,4);size=struct.unpack('>I',prefix)[0]
    if not 0<size<=c.MAX_REPLY:raise ValueError('unbounded performance reply')
    body=c.recv_exact(conn,size);value=c.parse_reply(body,b'Log',sequence)
    elapsed=time.monotonic()-started
    if value!=0:raise ValueError('performance Log not OK; no retry applied')
    return {'producer':producer,'first':first,'sequence':sequence,'count':BATCH,
            'request_bytes':len(wire),'request_sha256':digest,
            'reply_hex':c.hexbytes(prefix+body),'latency_seconds':elapsed}


def counters(count):
    return {'fixture:received good':count,'scribe_overall:received good':count}


def process_usage(pid):
    with open('/proc/%d/stat'%pid) as f:fields=f.read().rsplit(')',1)[1].split()
    ticks=int(fields[11])+int(fields[12]);hz=os.sysconf('SC_CLK_TCK')
    with open('/proc/%d/status'%pid) as f:
        for line in f:
            if line.startswith('VmHWM:'):
                parts=line.split()
                if len(parts)!=3 or parts[2]!='kB':raise ValueError('unexpected VmHWM units')
                return {'cpu_ticks':ticks,'clock_ticks_per_second':hz,'vmhwm_kib':int(parts[1])}
    raise ValueError('owned process VmHWM unavailable')


def wait_size(path,size,process):
    deadline=time.monotonic()+10
    while True:
        if process.poll() is not None:raise ValueError('daemon exited before file completion')
        try:actual=os.path.getsize(path)
        except OSError as error:
            if error.errno!=errno.ENOENT:raise
            actual=0
        if actual==size:return
        if actual>size or time.monotonic()>=deadline:raise ValueError('performance file size differs')
        time.sleep(0.005)


def verify_file(path,warmup=WARMUP,messages=MESSAGES):
    next_index=[0]*PRODUCERS;digest=hashlib.sha256();count=0
    with open(path,'rb') as f:
        while True:
            data=f.read(SIZE)
            if not data:break
            if len(data)!=SIZE:raise ValueError('partial performance record')
            producer,index=struct.unpack('>II',data[:8])
            if producer>=PRODUCERS or index!=next_index[producer] or data[8:]!=TAIL:
                raise ValueError('performance record lost, duplicated, reordered or changed')
            next_index[producer]+=1;count+=1;digest.update(data)
    expected=[messages+warmup]+[messages]*(PRODUCERS-1)
    if next_index!=expected:raise ValueError('incomplete producer inventory')
    return {'bytes':count*SIZE,'records':count,'producer_counts':next_index,'raw_sha256':digest.hexdigest()}


def percentile95(values):
    return sorted(values)[int(math.ceil(0.95*len(values)))-1]


def run_trial(c,helpers,lane,index):
    output=os.path.join(c.ROOT,lane+'-performance-%d'%index);os.makedirs(output)
    with open(c.TEMPLATE) as f:config=f.read().replace('@PORT@',str(c.PORT)).replace('@SEPARATE_TEMP_OUTPUT@',output)
    config=config.replace('max_size=1000000','max_size=1000000000')
    config='num_thrift_server_threads=4\nmax_queue_size=33554432\n'+config
    path=os.path.join(output,'fixture_00000');result={'lane':lane,'trial':index,'status':'failed'}
    with helpers.owned_daemon(c,lane,'performance-%d'%index,config,c.PORT) as session:
        process,control,child,directory=session;records=child['records'];result['child']=child
        if c.call(control,b'getVersion',1,b'\0',directory,records)!=c.hexbytes(b'2.2'):raise ValueError('unexpected daemon version')
        if c.call(control,b'getStatus',2,b'\0',directory,records)!=2:raise ValueError('performance daemon not ALIVE')
        if c.call(control,b'getCounters',3,b'\0',directory,records)!={}:raise ValueError('performance counters not fresh')
        result['warmup']=batch_record(c,control,0,0,4)
        wait_size(path,WARMUP*SIZE,process)
        if c.call(control,b'getCounters',5,b'\0',directory,records)!=counters(WARMUP):raise ValueError('warmup counters differ')
        prepared=[[prepare_batch(c,producer,(WARMUP if producer==0 else 0)+number*BATCH,number+1) for number in range(MESSAGES//BATCH)] for producer in range(PRODUCERS)]
        connections=[];threads=[];batches=[None]*PRODUCERS;gate=threading.Event();result['producer_owned_inodes']=[]
        try:
            for producer in range(PRODUCERS):
                c.network_check();conn=c.connect_owned(process,c.PORT)
                connections.append(conn);result['producer_owned_inodes'].append(c.connection_owner(process.pid,conn))
            def worker(producer):
                try:
                    gate.wait();items=[];offset=WARMUP if producer==0 else 0
                    for number in range(MESSAGES//BATCH):
                        items.append(batch_record(c,connections[producer],producer,offset+number*BATCH,number+1,prepared[producer][number]))
                    batches[producer]={'status':'passed','records':items}
                except BaseException:batches[producer]={'status':'failed','error':traceback.format_exc()}
            for producer in range(PRODUCERS):
                thread=threading.Thread(target=worker,args=(producer,));thread.daemon=True;thread.start();threads.append(thread)
            usage_before=process_usage(process.pid);client_cpu=time.process_time();started=time.monotonic();gate.set()
            for thread in threads:thread.join(max(0,30-(time.monotonic()-started)))
            if any(thread.is_alive() for thread in threads):raise ValueError('bounded performance workload timed out')
            ack_elapsed=time.monotonic()-started
            if any(item is None or item['status']!='passed' for item in batches):raise ValueError('performance producer failed: %r'%batches)
            wait_size(path,(TOTAL+WARMUP)*SIZE,process)
            complete_elapsed=time.monotonic()-started;client_cpu=time.process_time()-client_cpu
            usage_after=process_usage(process.pid)
        finally:
            gate.set()
            for conn in connections:
                try:conn.shutdown(c.socket.SHUT_RDWR)
                except OSError as error:
                    if error.errno not in (errno.EBADF,errno.ENOTCONN,errno.EPIPE,errno.ECONNRESET):raise
                finally:conn.close()
            for thread in threads:thread.join(3)
            if any(thread.is_alive() for thread in threads):raise ValueError('owned performance client thread not reclaimed')
        if c.call(control,b'getCounters',6,b'\0',directory,records)!=counters(TOTAL+WARMUP):raise ValueError('performance counters differ')
        latencies=[item['latency_seconds'] for producer in batches for item in producer['records']]
        result.update(producers=batches,usage_before=usage_before,usage_after=usage_after,
                      ack_seconds=ack_elapsed,file_complete_seconds=complete_elapsed,
                      client_cpu_seconds=client_cpu,daemon_cpu_seconds=(usage_after['cpu_ticks']-usage_before['cpu_ticks'])/usage_after['clock_ticks_per_second'],
                      vmhwm_kib=usage_after['vmhwm_kib'],batch_latency_p95_seconds=percentile95(latencies),batch_latency_count=len(latencies),
                      ack_messages_per_second=TOTAL/ack_elapsed,ack_payload_mib_per_second=TOTAL*SIZE/1048576/ack_elapsed,
                      complete_payload_mib_per_second=TOTAL*SIZE/1048576/complete_elapsed)
        helpers.shutdown(c,session,7)
    result['file']=verify_output(output)
    result['status']='passed';c.save_json(os.path.join(c.ROOT,'evidence',lane,'performance-%d.json'%index),result)
    return result


def verify_output(output):
    path=os.path.join(output,'fixture_00000')
    if sorted(os.listdir(output))!=['fixture_00000','fixture_current'] or not stat.S_ISREG(os.lstat(path).st_mode) or not os.path.islink(os.path.join(output,'fixture_current')) or os.readlink(os.path.join(output,'fixture_current'))!='fixture_00000':raise ValueError('unexpected performance output inventory')
    return verify_file(path)


def validate_trial(c,result,verify_output_files=False):
    if result.get('status')!='passed' or not 0<=result.get('trial',-1)<REPEATS:raise ValueError('incomplete performance trial')
    child=result['child']
    if child.get('status')!='passed' or child.get('exit')!=0 or child.get('cleanup_exit')!=0:raise ValueError('performance child cleanup incomplete')
    requests=[(b'getVersion',1),(b'getStatus',2),(b'getCounters',3),(b'getCounters',5),(b'getCounters',6),(b'shutdown',7)]
    values=[c.hexbytes(b'2.2'),2,{},counters(WARMUP),counters(TOTAL+WARMUP)]
    if len(child['records'])!=len(requests):raise ValueError('missing performance control RPC')
    for i,(name,seq) in enumerate(requests):
        r=child['records'][i];oneway=name==b'shutdown'
        if r['method']!=name.decode() or r['sequence']!=seq or r.get('oneway')!=oneway or r['request_hex']!=c.hexbytes(c.framed(name,seq,b'\0',oneway)):raise ValueError('performance control request differs')
        if oneway:
            if 'reply_hex' in r:raise ValueError('oneway performance shutdown has reply')
        else:
            if r.get('value')!=values[i]:raise ValueError('performance control value differs')
            validate_reply(c,r['reply_hex'],name,seq,values[i])
    inodes=result['producer_owned_inodes']
    if len(inodes)!=PRODUCERS or len(set(inodes))!=PRODUCERS or any(not isinstance(v,str) or not v.isdigit() for v in inodes):raise ValueError('missing producer socket ownership evidence')
    warmup=result['warmup'];validate_batch(c,warmup,0,0,4)
    if len(result['producers'])!=PRODUCERS:raise ValueError('missing performance producer')
    latencies=[]
    for producer,part in enumerate(result['producers']):
        if part.get('status')!='passed' or len(part['records'])!=MESSAGES//BATCH:raise ValueError('incomplete producer')
        offset=WARMUP if producer==0 else 0
        for number,record in enumerate(part['records']):
            validate_batch(c,record,producer,offset+number*BATCH,number+1);latencies.append(record['latency_seconds'])
    expected=[MESSAGES+WARMUP]+[MESSAGES]*(PRODUCERS-1)
    file=result['file']
    if file['bytes']!=(TOTAL+WARMUP)*SIZE or file['records']!=TOTAL+WARMUP or file['producer_counts']!=expected or len(file['raw_sha256'])!=64:raise ValueError('performance file inventory differs')
    if verify_output_files:
        output=os.path.join(c.ROOT,result['lane']+'-performance-%d'%result['trial'])
        if verify_output(output)!=file:raise ValueError('persisted performance output differs')
    for key in ('ack_seconds','file_complete_seconds','batch_latency_p95_seconds'):
        if not isinstance(result[key],(int,float)) or not math.isfinite(result[key]) or result[key]<=0:raise ValueError('invalid performance duration')
    if result['file_complete_seconds']<result['ack_seconds'] or result['batch_latency_count']!=len(latencies) or result['batch_latency_p95_seconds']!=percentile95(latencies):raise ValueError('performance timing summary differs')
    for key,seconds in (('ack_messages_per_second','ack_seconds'),('ack_payload_mib_per_second','ack_seconds'),('complete_payload_mib_per_second','file_complete_seconds')):
        expected_rate=(TOTAL if key=='ack_messages_per_second' else TOTAL*SIZE/1048576)/result[seconds]
        if result[key]!=expected_rate:raise ValueError('performance rate differs')
    before=result['usage_before'];after=result['usage_after']
    if after['clock_ticks_per_second']<=0 or before['cpu_ticks']<0 or before['vmhwm_kib']<0 or before['clock_ticks_per_second']!=after['clock_ticks_per_second'] or after['cpu_ticks']<before['cpu_ticks'] or after['vmhwm_kib']<before['vmhwm_kib']:raise ValueError('invalid process usage')
    if result['daemon_cpu_seconds']!=(after['cpu_ticks']-before['cpu_ticks'])/after['clock_ticks_per_second'] or result['vmhwm_kib']!=after['vmhwm_kib'] or not math.isfinite(result['client_cpu_seconds']) or result['client_cpu_seconds']<0:raise ValueError('usage summary differs')


def validate_reply(c,hexwire,name,seq,value):
    wire=bytes.fromhex(hexwire)
    if len(wire)<4 or not 0<len(wire)-4<=c.MAX_REPLY or struct.unpack('>I',wire[:4])[0]!=len(wire)-4 or c.parse_reply(wire[4:],name,seq)!=value:raise ValueError('performance reply differs')


def validate_batch(c,record,producer,first,seq):
    entries=[(b'fixture',payload(producer,i)) for i in range(first,first+BATCH)]
    wire=c.framed(b'Log',seq,c.log_fields(entries))
    if (record['producer'],record['first'],record['sequence'],record['count'],record['request_bytes'],record['request_sha256'])!=(producer,first,seq,BATCH,len(wire),hashlib.sha256(wire).hexdigest()):raise ValueError('performance batch recipe differs')
    validate_reply(c,record['reply_hex'],b'Log',seq,0)
    if not math.isfinite(record['latency_seconds']) or record['latency_seconds']<=0:raise ValueError('invalid batch latency')


def summarize(c,trials,verify_output_files=False):
    if len(trials)!=REPEATS*2:raise ValueError('incomplete repeated baseline')
    metrics={};expected_order=[('old',0),('modern',0),('modern',1),('old',1),('old',2),('modern',2)]
    if [(t['lane'],t['trial']) for t in trials]!=expected_order:raise ValueError('non-alternating performance order')
    for trial in trials:validate_trial(c,trial,verify_output_files)
    for lane in ('old','modern'):
        selected=[t for t in trials if t['lane']==lane];metrics[lane]={}
        for key in ('ack_messages_per_second','ack_payload_mib_per_second','complete_payload_mib_per_second','batch_latency_p95_seconds','daemon_cpu_seconds','client_cpu_seconds','vmhwm_kib'):
            values=sorted(t[key] for t in selected);metrics[lane][key]={'median':values[1],'min':values[0],'max':values[2],'samples':REPEATS}
    return {'case':'performance','status':'passed','verdict':'correctness verified; descriptive measurement only, no threshold',
            'workload':{'producers':PRODUCERS,'messages_per_producer':MESSAGES,'payload_bytes':SIZE,'batch_entries':BATCH,'warmup_entries':WARMUP,'measured_entries':TOTAL,'repeats':REPEATS},
            'measurement':{'timer':'time.monotonic','latency':'preencoded packet send/parse ACK client wall time; total rate includes thread/bookkeeping, excludes preparation/hash','p95':'nearest-rank ceil(0.95*N), N=64 batches per trial',
                           'client_cpu':'time.process_time during measured window','daemon_cpu':'owned /proc/PID/stat utime+stime / SC_CLK_TCK','rss':'owned /proc/PID/status VmHWM kB (KiB), lifetime high-water through completion including startup/warmup',
                           'completion':'visible final file size then post-shutdown exact record validation; no fsync',
                           'scope':'same resource allocation, separate old/new userlands/toolchains/ABIs; causes not isolated'},
            'metrics':metrics,'modern_over_old_ack_ratio':metrics['modern']['ack_payload_mib_per_second']['median']/metrics['old']['ack_payload_mib_per_second']['median'],
            'trial_order':expected_order,'python':sys.version}


def run_comparison(c,helpers):
    if not hasattr(time,'monotonic') or not hasattr(time,'process_time'):raise ValueError('performance client requires existing Python3 monotonic/process_time')
    trials=[]
    for index in range(REPEATS):
        for lane in (('old','modern') if index%2==0 else ('modern','old')):
            trials.append(run_trial(c,helpers,lane,index))
    return summarize(c,trials,verify_output_files=True)
