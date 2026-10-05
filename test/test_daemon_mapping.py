#!/usr/bin/env python3
"""Offline IDL/state/report checks for the bounded mapping case; no daemons."""
import binascii,copy,importlib.util,struct,unittest,json,tempfile
from unittest import mock
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
c=load('mapping_client_test',ROOT/'tools/daemon_differential.py')
m=load('mapping_case_test',ROOT/'tools/daemon_mapping_case.py')


def rpc_reply(name,seq,value):
    if name==b'getVersion':fields=b'\x0b\0\0'+c.string(b'2.2')
    elif name==b'getCounters':
        fields=b'\x0d\0\0\x0b\x0a'+struct.pack('>i',len(value))
        for key,item in sorted(value.items()):fields+=c.string(key.encode())+struct.pack('>q',item)
    else:fields=b'\x08\0\0'+struct.pack('>i',value)
    return m.reply(c,name,seq,fields)


class MappingOfflineTests(unittest.TestCase):
    def scenario(self,missing=None):
        result={'case':missing or 'ttl','status':'passed','exit':0,'cleanup_exit':0,'peer_cleanup':True,
                'status_value':2,'ports':{'A':c.PORT+1,'B':c.PORT+2,'mapping':c.PORT+3},'records':[],'peers':[]}
        entries=m.PAYLOADS[:1] if missing else m.PAYLOADS
        def call(name,fields,value=None,oneway=False):
            seq=len(result['records'])+1
            r={'method':name.decode(),'sequence':seq,'oneway':oneway,'request_hex':c.hexbytes(c.framed(name,seq,fields,oneway))}
            if not oneway:r.update(value=value,reply_hex=c.hexbytes(rpc_reply(name,seq,value)))
            result['records'].append(r)
        call(b'getVersion',b'\0',c.hexbytes(b'2.2'))
        for count,payload in enumerate(entries,1):
            call(b'Log',c.log_fields([(b'fixture',payload)]),0)
            call(b'getCounters',b'\0',m.counters(count));call(b'getStatus',b'\0',2)
        call(b'shutdown',b'\0',oneway=True)
        result['counters']=m.counters(len(entries))
        def mapping(mode,t):
            request=c.framed(b'getMapping',0,b'\x0b\0\x01'+c.string(b'fixture')+b'\0')
            result['peers'].append({'role':'mapping','mode':mode,'request_hex':c.hexbytes(request),
                'reply_hex':c.hexbytes(m.mapping_reply(c,0,mode,result['ports'].get(mode,0))),'monotonic':t,'wall':100+t})
        def control(mode,t):
            result['peers'].append({'role':'control','mode':mode,'monotonic':t,'wall':100+t})
        def delivery(role,index,t):
            payload=m.PAYLOADS[index];request=c.framed(b'Log',0,c.log_fields([(b'fixture',payload)]))
            result['peers'].append({'role':role,'request_hex':c.hexbytes(request),'payloads_hex':[c.hexbytes(payload)],
                'reply_hex':c.hexbytes(m.reply(c,b'Log',0,b'\x08\0\0'+struct.pack('>i',0))),'monotonic':t,'wall':100+t})
        if missing:delivery('A',0,.1)
        else:
            result['cache_observed']=True;result['cache_proof']={'before_fetches':1,'after_fetches':1,'elapsed':1.0,'ttl':m.TTL}
            mapping('A',0);delivery('A',0,.1);control('B',.2);delivery('A',1,.3)
            mapping('B',6);delivery('B',2,6.1);control('fail',6.2)
            mapping('fail',12);mapping('fail',12.05);delivery('B',3,12.1)
            control('A',12.2);mapping('A',12.3);delivery('A',4,12.4)
        return result
    def report(self):
        return {'case':'mapping','status':'passed','scenarios':[self.scenario(key) for key in (None,'bucket_id','bucket_updater_port')]}

    def test_mapping_request_and_both_official_reply_shapes(self):
        request=c.framed(b'getMapping',7,b'\x0b\0\x01'+c.string(b'fixture')+b'\0')
        self.assertEqual(m.mapping_request(c,request[4:]),7)
        normal=m.mapping_reply(c,7,'A',14631)
        expected=b'\x0d\0\0\x08\x0c'+struct.pack('>ii',1,1)+b'\x0b\0\x02'+c.string(b'127.0.0.1')+b'\x08\0\x03'+struct.pack('>i',14631)+b'\0'
        self.assertEqual(normal,m.reply(c,b'getMapping',7,expected))
        error=b'\x0c\0\x01\x0b\0\x01'+c.string(m.FAILURE)+b'\x08\0\x02'+struct.pack('>i',1)+b'\0'
        self.assertEqual(m.mapping_reply(c,7,'fail',0),m.reply(c,b'getMapping',7,error))

    def test_cached_route_failure_recovery_and_static_fallback_replay(self):
        report=self.report();result=m.compare_lanes(c,report,copy.deepcopy(report))
        self.assertEqual(result['status'],'passed')
        self.assertEqual(result['scenarios'][0]['mapping_phases'],['A','B','fail','A'])
        self.assertEqual(result['scenarios'][0]['routed']['B'],[c.hexbytes(b'B0'),c.hexbytes(b'B1')])
        self.assertEqual(result['scenarios'][1]['mapping_phases'],[])

    def test_direct_unpooled_configs_omit_only_named_dynamic_key(self):
        normal=m.config(c,14631,14633)
        self.assertIn('use_conn_pool=no\n',normal);self.assertIn('bucket_id=1\n',normal)
        self.assertNotIn('type=bucket\n',normal)
        for key in ('bucket_id','bucket_updater_port'):
            text=m.config(c,14631,14633,key)
            self.assertNotIn(key+'=',text);self.assertIn('remote_port=14631\n',text)
            self.assertEqual(text,normal.replace(next(line+'\n' for line in normal.splitlines() if line.startswith(key+'=')),''))

    def test_phase_order_and_raw_ttl_timestamps_cannot_be_replaced_by_metadata(self):
        for mutate in (lambda r:r['scenarios'][0]['peers'].sort(key=lambda x:x['role']!='mapping'),
                       lambda r:r['scenarios'][0]['peers'][4].update(wall=105),
                       lambda r:r['scenarios'][0]['peers'][7].update(wall=111),
                       lambda r:r['scenarios'][0]['peers'][3].update(monotonic=4.5),
                       lambda r:r['scenarios'][0]['peers'].pop(2)):
            broken=self.report();mutate(broken)
            with self.assertRaises(ValueError):m.compare_lanes(c,broken,copy.deepcopy(broken))

    def test_raw_counter_and_status_checkpoints_are_mandatory(self):
        broken=self.report()
        records=[r for r in broken['scenarios'][0]['records'] if r['method'] not in ('getCounters','getStatus')]
        for seq,r in enumerate(records,1):
            r['sequence']=seq
            for key in ('request_hex','reply_hex'):
                if key not in r:continue
                wire=binascii.unhexlify(r[key]);offset=4+4+len(r['method'])+1
                r[key]=c.hexbytes(wire[:offset]+struct.pack('>i',seq)+wire[offset+4:])
        broken['scenarios'][0]['records']=records
        with self.assertRaises(ValueError):m.compare_lanes(c,broken,copy.deepcopy(broken))

    def test_lane_failure_reason_and_partial_peer_evidence_are_persisted(self):
        previous=c.ROOT
        try:
            with tempfile.TemporaryDirectory() as directory, mock.patch.object(m,'Peers') as peers, \
                 mock.patch.object(m,'exercise',side_effect=ValueError('missing warning fixture')):
                c.ROOT=directory;peer=peers.return_value;peer.snapshot.return_value=[];peer.errors=[];peer.ports={}
                with self.assertRaisesRegex(ValueError,'missing warning fixture'):m.run_lane(c,None,'old')
                result=json.loads((Path(directory)/'evidence/old/mapping-result.json').read_text())
                self.assertEqual(result['status'],'failed');self.assertIn('missing warning fixture',result['error'])
                self.assertEqual(result['active_case'],'ttl')
                self.assertTrue((Path(directory)/'evidence/old/ttl-peers.json').is_file())
        finally:c.ROOT=previous

    def test_wrong_routes_mapping_reply_cache_or_cleanup_cannot_pass(self):
        mutations=[lambda r:r['scenarios'][0]['peers'][0].update(reply_hex=c.hexbytes(m.mapping_reply(c,0,'A',1))),
                   lambda r:r['scenarios'][0]['cache_proof'].update(elapsed=m.TTL),
                   lambda r:r['scenarios'][0]['cache_proof'].update(after_fetches=2),
                   lambda r:r['scenarios'][0].update(peer_cleanup=False),
                   lambda r:r['scenarios'][0]['records'].pop(),
                   lambda r:r['scenarios'][1]['peers'].append(copy.deepcopy(r['scenarios'][0]['peers'][0])),
                   lambda r:r['scenarios'][0]['peers'][-1].update(role='B')]
        for mutate in mutations:
            broken=self.report();mutate(broken)
            with self.assertRaises(ValueError):m.compare_lanes(c,broken,copy.deepcopy(broken))

if __name__=='__main__':unittest.main()
