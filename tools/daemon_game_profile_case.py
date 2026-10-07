"""Bounded synthetic game-server feature profile: copied multi/buffer relay, prefixes, default."""
from __future__ import print_function
import binascii, hashlib, os, struct, time

TEMPLATE=os.path.join(os.path.dirname(os.path.abspath(__file__)),'daemon_game_profile.conf.template')
LOGIN,SESSION,METRICS,EXT,OTHER=b'fixture-login',b'fixture-session',b'fixture-metrics-cpu',b'ext-alpha',b'fixture-other'
STARTED=(LOGIN,SESSION)               # explicit categories= names: copied and opened at startup
LOCAL=(LOGIN,SESSION,METRICS)         # multi copies: store1 local file primary
RELAYED=(LOGIN,SESSION,METRICS,EXT)   # store0 unpooled copies + pooled ext-* copy
PHASES=('startup','spooled','replayed','drained','final_upstream','final_downstream')

# Absolute upstream getCounters values; each delta is the difference of two phases.
# retries: new_thread_per_category=yes, so every category handled here is
# StoreQueue(model, category) -> Store::copy (scribe_server.cpp configureStoreCategory for
# explicit names at startup, createCategoryFromModel for prefix/default at Log time).
# Each copied BufferStore whose NetworkStore primary cannot connect enters
# changeState(DISCONNECTED) from open(), which counts '<category>:retries' once.
# store1/default have file primaries and never count. Copies retry only after
# now-lastOpenAttempt > retry_interval=10 (range 1: 1/2=0, rand()%1=0), so a
# downstream ready inside the 8 s window keeps every count at one.
STARTUP={'fixture-login:retries':1,'fixture-session:retries':1,'scribe_overall:retries':2}
# Log: addMessage counts received good per category and overall (3 login + 1 each for
# session, metrics prefix, ext-* and default). The blank entry only counts overall
# 'received blank category'. received bad stays absent: the default model catches
# every unknown nonblank category in createNewCategory.
SPOOLED={'fixture-login:received good':3,'fixture-session:received good':1,
         'fixture-metrics-cpu:received good':1,'ext-alpha:received good':1,
         'fixture-other:received good':1,'scribe_overall:received good':7,
         'scribe_overall:received blank category':1,
         'fixture-login:retries':1,'fixture-session:retries':1,'fixture-metrics-cpu:retries':1,
         'ext-alpha:retries':1,'scribe_overall:retries':4}
# Replay: scribeConn::send counts overall 'sent' per OK Log (3+1+1+1 spooled messages;
# empty payload survives as "\n" because the secondary frame includes add_newlines).
REPLAYED=dict(SPOOLED,**{'scribe_overall:sent':6})
DOWNSTREAM={'fixture-login:received good':3,'fixture-session:received good':1,
            'fixture-metrics-cpu:received good':1,'ext-alpha:received good':1,
            'scribe_overall:received good':6}


def entries(c):
    # c.PAYLOADS keeps NUL/LF/0xff plus an empty entry in one nonzero-byte login queue.
    return ([(LOGIN,p) for p in c.PAYLOADS]+[(SESSION,b'S1'),(METRICS,b'cpu=7'),
            (EXT,b'ext\x00x'),(OTHER,b'other'),(b'',b'blank-discard')])


def messages(c,category):
    return [p for name,p in entries(c) if name==category]


def snapshot(c,files,links):
    return {'files':[{'path':p,'bytes':len(d),'hex':c.hexbytes(d),'sha256':hashlib.sha256(d).hexdigest()}
                     for p,d in sorted(files.items())],
            'symlinks':[{'path':p,'target':t} for p,t in sorted(links.items())]}


def upstream_outputs(c,date,phase):
    """Expected upstream tree. Copies replace base_filename/file_path with the category
    (FileStoreBase::copyCommon); rotate_period=1h is ROLL_OTHER, so non-buffer names get
    -YYYY-MM-DD and _current omits it. Buffer secondaries force ROLL_NEVER/no symlink."""
    files={};links={}
    for cat in (STARTED if phase=='startup' else LOCAL):
        name=cat.decode();dated='%s-%s_00000'%(name,date)
        # store1 primary add_newlines=1 receives the batch directly: STREAMING already.
        files['local/%s/%s'%(name,dated)]=b'' if phase=='startup' else b''.join(m+b'\n' for m in messages(c,cat))
        links['local/%s/%s_current'%(name,name)]=dated
    if phase=='startup':
        # store0 opened its secondary for DISCONNECTED; store1 deleted its empty secondary
        # on the first periodicCheck (SENDING_BUFFER -> STREAMING).
        for cat in STARTED:files['relay-spool/%s/%s_00000'%(cat.decode(),cat.decode())]=b''
        return snapshot(c,files,links)
    name=OTHER.decode();dated='%s-%s_00000'%(name,date)
    files['default/%s/%s'%(name,dated)]=b''.join(messages(c,OTHER))  # add_newlines=0
    links['default/%s/%s_current'%(name,name)]=dated
    if phase=='spooled':
        for cat in RELAYED:
            # Buffer file frame: native little-endian uint32 of message+"\n".
            data=b''.join(struct.pack('<I',len(m)+1)+m+b'\n' for m in messages(c,cat))
            files['%s/%s/%s_00000'%('ext-spool' if cat==EXT else 'relay-spool',cat.decode(),cat.decode())]=data
    return snapshot(c,files,links)


def downstream_outputs(c):
    files={};links={}
    for cat in RELAYED:
        name=cat.decode()
        # readOldest returns message+"\n"; downstream add_newlines=1 appends one more.
        files['%s/%s_00000'%(name,name)]=b''.join(m+b'\n\n' for m in messages(c,cat))
        links['%s/%s_current'%(name,name)]=name+'_00000'
    return snapshot(c,files,links)


def phase_outputs(c,date):
    up=upstream_outputs(c,date,'drained');down=downstream_outputs(c)
    return {'startup':upstream_outputs(c,date,'startup'),'spooled':upstream_outputs(c,date,'spooled'),
            'replayed':down,'drained':up,'final_upstream':up,'final_downstream':down}


def specification(c):
    version=c.hexbytes(b'2.2')
    return {'upstream':[(b'getName',b'\0',c.hexbytes(b'Scribe')),(b'getVersion',b'\0',version),
                        (b'getStatus',b'\0',2),(b'getStatusDetails',b'\0',''),(b'getCounters',b'\0',STARTUP),
                        (b'Log',c.log_fields([]),0),(b'Log',c.log_fields(entries(c)),0),
                        # ext-* BufferStore reports its primary "Failed to connect"; MultiStore
                        # has no getStatus override, so only the ext copy makes WARNING.
                        (b'getCounters',b'\0',SPOOLED),(b'getStatus',b'\0',5),
                        (b'getCounters',b'\0',REPLAYED),(b'getStatus',b'\0',2),(b'shutdown',b'\0',None)],
            'downstream':[(b'getVersion',b'\0',version),(b'getStatus',b'\0',2),(b'getCounters',b'\0',{}),
                          (b'getCounters',b'\0',DOWNSTREAM),(b'shutdown',b'\0',None)]}


def downstream_config(c,path):
    with open(c.TEMPLATE) as f:config=f.read()
    # Ordinary file template as a default model: one copied FileStore per relayed category.
    for old,new in (('category=fixture','category=default'),('add_newlines=0','add_newlines=1')):
        if old not in config:raise ValueError('downstream template changed')
        config=config.replace(old,new)
    return config.replace('@PORT@',str(c.PORT+1)).replace('@SEPARATE_TEMP_OUTPUT@',path)


def run_lane(c,helpers,lane):
    date=time.strftime('%Y-%m-%d',time.gmtime())  # daemons run with TZ=UTC
    up_path=os.path.join(c.ROOT,lane+'-game-profile');down_path=os.path.join(c.ROOT,lane+'-game-downstream')
    os.makedirs(up_path);os.makedirs(down_path)
    with open(TEMPLATE) as f:
        up_config=f.read().replace('@PORT@',str(c.PORT)).replace('@DOWNSTREAM_PORT@',str(c.PORT+1)).replace('@SEPARATE_TEMP_OUTPUT@',up_path)
    down_config=downstream_config(c,down_path)
    # Both ports must be absent before any upstream retry can contact downstream.
    c.port_free(c.PORT);c.port_free(c.PORT+1)
    result={'case':'game-profile','lane':lane,'utc_date':date,'status':'failed'}
    result_path=os.path.join(c.ROOT,'evidence',lane,'game-profile-result.json')
    os.makedirs(os.path.dirname(result_path));c.save_json(result_path,result)
    spec=specification(c);expected=phase_outputs(c,date)
    def step(conn,directory,records,role,seq):
        name,fields,wanted=spec[role][seq-1]
        if c.call(conn,name,seq,fields,directory,records)!=wanted:
            raise ValueError('game-profile %s %d/%s differs'%(role,seq,name.decode()))
    with helpers.owned_daemon(c,lane,'upstream',up_config,c.PORT) as upstream:
        unused,conn,up,directory=upstream;records=up['records'];result['upstream']=up
        def window():
            remaining=8-(time.time()-up['started_at'])
            if remaining<=0:raise ValueError('downstream missed first-retry readiness window')
            return remaining
        # Read-only gate: startup copies opened (retries counted) and store1 is STREAMING.
        result['startup']=helpers.wait_output(c,up_path,expected['startup'],window())
        for seq in range(1,8):step(conn,directory,records,'upstream',seq)
        result['spooled']=helpers.wait_output(c,up_path,expected['spooled'],window())
        c.save_json(result_path,result)
        for seq in (8,9):step(conn,directory,records,'upstream',seq)
        with helpers.owned_daemon(c,lane,'downstream',down_config,c.PORT+1,window()) as downstream:
            unused,dc,down,dd=downstream;dr=down['records'];result['downstream']=down
            for seq in (1,2,3):step(dc,dd,dr,'downstream',seq)
            window()
            result['replayed']=helpers.wait_output(c,down_path,expected['replayed'])
            result['drained']=helpers.wait_output(c,up_path,expected['drained'])
            c.save_json(result_path,result)
            for seq in (10,11):step(conn,directory,records,'upstream',seq)
            step(dc,dd,dr,'downstream',4)
            helpers.shutdown(c,upstream,12);helpers.shutdown(c,downstream,5)
    for phase,path in (('final_upstream',up_path),('final_downstream',down_path)):
        files,links=c.output_snapshot(path);result[phase]={'files':files,'symlinks':links}
    if result['final_upstream']!=expected['final_upstream'] or result['final_downstream']!=expected['final_downstream']:
        c.save_json(result_path,result);raise ValueError('shutdown changed game-profile outputs')
    result['status']='passed';c.save_json(result_path,result)
    return result


def compare_lanes(c,old,new):
    spec=specification(c);checks={}
    for lane in (old,new):
        if lane.get('case')!='game-profile' or lane.get('status')!='passed':raise ValueError('incomplete game-profile lane')
        for phase,wanted in phase_outputs(c,lane.get('utc_date')).items():
            if lane.get(phase)!=wanted:raise ValueError('missing or wrong game-profile phase '+phase)
        for role,requests in spec.items():
            part=lane.get(role) or {};records=part.get('records',[])
            if part.get('status')!='passed' or part.get('exit')!=0 or part.get('cleanup_exit')!=0 or len(records)!=len(requests):
                raise ValueError('incomplete game-profile child')
            for seq,(name,fields,wanted) in enumerate(requests,1):
                r=records[seq-1];oneway=name==b'shutdown'
                if r['method']!=name.decode() or r['sequence']!=seq or r.get('oneway')!=oneway or r['request_hex']!=c.hexbytes(c.framed(name,seq,fields,oneway)):
                    raise ValueError('game-profile request differs')
                if oneway:
                    if 'reply_hex' in r:raise ValueError('oneway game-profile shutdown has reply')
                    continue
                wire=binascii.unhexlify(r['reply_hex'])
                if len(wire)<4 or not 0<len(wire)-4<=c.MAX_REPLY or struct.unpack('>I',wire[:4])[0]!=len(wire)-4:
                    raise ValueError('invalid game-profile reply frame')
                if c.parse_reply(wire[4:],name,seq)!=r.get('value') or r.get('value')!=wanted:
                    raise ValueError('game-profile reply value differs')
    # Dated file names are not normalized: lanes on different UTC dates fail.
    checks['utc-date']=old['utc_date']==new['utc_date']
    for role,requests in spec.items():
        for seq,(name,unused,unused_value) in enumerate(requests,1):
            a=old[role]['records'][seq-1];b=new[role]['records'][seq-1]
            checks['%s-request-%d'%(role,seq)]=a['request_hex']==b['request_hex']
            if name not in (b'getVersion',b'shutdown'):checks['%s-reply-%d'%(role,seq)]=a['reply_hex']==b['reply_hex']
    for phase in PHASES:checks[phase]=old[phase]==new[phase]
    return {'case':'game-profile','status':'passed' if all(checks.values()) else 'failed','checks':checks,
            'scope':'bounded synthetic copy/multi/buffer/prefix/default profile with full relay replay; no bucket, thriftfile, service_list, dynamic config, partial replay or durability claim'}
