"""Bounded fb303 option/counter and unknown-method case; no production changes."""
from __future__ import print_function
import binascii,os,struct
MISSING=b'compat_missing'
KEY=b'compat_key\0\xff'
UNKNOWN=b'compat_unknown'
FIRST=b'one\0\xff'
SECOND=b'two\n'
ENTRIES=[(b'fixture',b'A\0B\n\xff'),(b'fixture',b'tail')]

def arguments(c,*values):
    return b''.join(b'\x0b'+struct.pack('>h',index)+c.string(value) for index,value in enumerate(values,1))+b'\0'


def specification(c):
    empty={c.hexbytes(MISSING):''};options={c.hexbytes(MISSING):'',c.hexbytes(KEY):c.hexbytes(SECOND)}
    good={'fixture:received good':2,'scribe_overall:received good':2}
    return [(b'getOptions',b'\0',{},False),
            (b'getOption',arguments(c,MISSING),'',False),
            (b'getOptions',b'\0',empty,False),
            (b'setOption',arguments(c,KEY,FIRST),None,False),
            (b'getOption',arguments(c,KEY),c.hexbytes(FIRST),False),
            (b'setOption',arguments(c,KEY,SECOND),None,False),
            (b'getOptions',b'\0',options,False),
            (b'getCounter',arguments(c,MISSING),0,False),
            (b'getCounters',b'\0',{},False),
            (UNKNOWN,b'\0',{'type':1,'message_hex':c.hexbytes(b"Invalid method name: '"+UNKNOWN+b"'")},True),
            (b'Log',c.log_fields(ENTRIES),0,False),
            (b'getCounter',arguments(c,b'fixture:received good'),2,False),
            (b'getCounters',b'\0',good,False),
            (b'getStatus',b'\0',2,False),
            (b'shutdown',b'\0',None,False)]


def run_lane(c,helpers,lane):
    output=os.path.join(c.ROOT,lane+'-fb303');os.makedirs(output)
    with open(c.TEMPLATE) as f:
        config=f.read().replace('@PORT@',str(c.PORT)).replace('@SEPARATE_TEMP_OUTPUT@',output)
    config='num_thrift_server_threads=2\n'+config.replace('max_msg_per_second=2000000','max_msg_per_second=0')
    with helpers.owned_daemon(c,lane,'fb303',config,c.PORT) as session:
        unused,conn,result,directory=session;result['case']='fb303'
        for seq,(name,fields,wanted,exception) in enumerate(specification(c)[:-1],1):
            actual=c.call(conn,name,seq,fields,directory,result['records'],exception=exception)
            if actual!=wanted:raise ValueError('fb303 value differs at %d/%s: %r'%(seq,name,actual))
        helpers.shutdown(c,session,15)
    result['files'],result['symlinks']=c.output_snapshot(output)
    expected_files,expected_links=c.expected_outputs('file')
    # This case has two nonempty payloads, the existing file case also contains an empty entry.
    if result['files']!=expected_files or result['symlinks']!=expected_links:raise ValueError('fb303 recovery file differs')
    c.save_json(os.path.join(c.ROOT,'evidence',lane,'fb303-result.json'),result)
    return result


def compare_lanes(c,old,new):
    checks={}
    for lane in (old,new):
        records=lane['records']
        if lane.get('case')!='fb303' or lane.get('status')!='passed' or lane.get('exit')!=0 or lane.get('cleanup_exit')!=0 or len(records)!=15:raise ValueError('incomplete fb303 lane')
        for seq,(name,fields,wanted,exception) in enumerate(specification(c),1):
            r=records[seq-1];oneway=name==b'shutdown'
            if r['method']!=name.decode() or r['sequence']!=seq or r.get('oneway')!=oneway or r.get('exception',False)!=exception or r['request_hex']!=c.hexbytes(c.framed(name,seq,fields,oneway)):raise ValueError('fb303 request differs')
            if oneway:
                if 'reply_hex' in r:raise ValueError('oneway fb303 shutdown has reply')
            else:
                wire=binascii.unhexlify(r['reply_hex'])
                if len(wire)<4 or not 0<len(wire)-4<=c.MAX_REPLY or struct.unpack('>I',wire[:4])[0]!=len(wire)-4:raise ValueError('invalid fb303 reply frame')
                value=c.parse_application_exception(wire[4:],name,seq) if exception else c.parse_reply(wire[4:],name,seq)
                if value!=wanted or r.get('value')!=value:raise ValueError('fb303 reply/value differs')
        files,links=c.expected_outputs('file')
        if lane['files']!=files or lane['symlinks']!=links:raise ValueError('fb303 output differs')
    for a,b in zip(old['records'],new['records']):
        checks['request-%d'%a['sequence']]=a['request_hex']==b['request_hex']
        if a['method']!='shutdown':checks['reply-%d'%a['sequence']]=a['reply_hex']==b['reply_hex']
    checks['files']=old['files']==new['files'];checks['symlinks']=old['symlinks']==new['symlinks']
    return {'case':'fb303','status':'passed' if all(checks.values()) else 'failed','checks':checks,
            'scope':'option state, single/map counters, unknown-method recovery, rate-disabled positive config; no rate/backpressure timing or invalid frame claim'}
