#!/usr/bin/env python3
"""Offline bounded spool report and fake-child checks; no actual daemon."""
import binascii,copy,importlib.util,json,signal,struct,tempfile,unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import Mock,patch
ROOT=Path(__file__).resolve().parents[1]
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
client=load('daemon_client_spool_test',ROOT/'tools/daemon_differential.py')
spool=load('daemon_spool_test',ROOT/'tools/daemon_spool_case.py')

class SpoolDifferentialTests(unittest.TestCase):
    def record(self,name,seq,fields=b'\0',value=None):
        oneway=name==b'shutdown'
        record={'method':name.decode(),'sequence':seq,'oneway':oneway,
                'request_hex':client.hexbytes(client.framed(name,seq,fields,oneway))}
        if oneway:return record
        if name==b'getVersion':result=b'\x0b\0\0'+client.string(b'2.2');value=client.hexbytes(b'2.2')
        elif name==b'getCounters':
            result=b'\x0d\0\0\x0b\x0a'+struct.pack('>i',len(value))
            for key,count in sorted(value.items()):result+=client.string(key.encode())+struct.pack('>q',count)
        else:result=b'\x08\0\0'+struct.pack('>i',value)
        body=client.string(name)+b'\x02'+struct.pack('>i',seq)+result+b'\0'
        record.update(value=value,reply_hex=client.hexbytes(struct.pack('>I',len(body))+body));return record

    def report(self):
        up=[self.record(b'getVersion',1),self.record(b'Log',2,client.log_fields(spool.ENTRIES),0),
            self.record(b'getCounters',3,value=spool.upstream_counters(2)),self.record(b'getStatus',4,value=5),
            self.record(b'getCounters',5,value=spool.upstream_counters(2,2)),self.record(b'getStatus',6,value=2),
            self.record(b'Log',7,client.log_fields([(b'fixture',b'Z')]),0),
            self.record(b'getCounters',8,value=spool.upstream_counters(3,3)),self.record(b'shutdown',9)]
        down=[self.record(b'getVersion',1),self.record(b'getStatus',2,value=2),self.record(b'getCounters',3,value={}),
              self.record(b'getCounters',4,value={'fixture:received good':3,'scribe_overall:received good':3}),self.record(b'shutdown',5)]
        return {'case':'spool','status':'passed','upstream':{'status':'passed','exit':0,'cleanup_exit':0,'records':up},
                'downstream':{'status':'passed','exit':0,'cleanup_exit':0,'records':down},
                'spooled':spool.outputs(client,spool.SPOOL,True),'replayed':spool.outputs(client,spool.PAYLOAD),
                'drained':{'files':[],'symlinks':[]},'streamed':spool.outputs(client,spool.PAYLOAD+b'Z'),
                'final_spool':{'files':[],'symlinks':[]},'final_downstream':spool.outputs(client,spool.PAYLOAD+b'Z')}

    def test_exact_nonempty_spool_frames_and_synthetic_full_replay(self):
        self.assertEqual(spool.SPOOL.hex(),'050000004100420aff040000007461696c')
        self.assertEqual(len(spool.SPOOL),17)
        config=(ROOT/'tools/daemon_spool.conf.template').read_text()
        self.assertIn('retry_interval=10\nretry_interval_range=1\n',config)
        report=self.report();result=spool.compare_lanes(client,report,copy.deepcopy(report))
        self.assertEqual(result['status'],'passed');self.assertTrue(all(result['checks'].values()))

    def test_consistently_wrong_counters_status_or_missing_phase_cannot_pass(self):
        for mutate in (lambda r:r.pop('drained'),lambda r:r.pop('final_downstream'),
                       lambda r:r['final_spool'].update(files=r['spooled']['files']),lambda r:r['upstream'].pop('cleanup_exit'),
                       lambda r:r['spooled']['files'][0].update(hex='00'),
                       lambda r:r['upstream']['records'].__setitem__(3,self.record(b'getStatus',4,value=2)),
                       lambda r:r['upstream']['records'].__setitem__(7,self.record(b'getCounters',8,value=spool.upstream_counters(2,3))),
                       lambda r:r['downstream']['records'][-1].update(reply_hex='00000000')):
            broken=self.report();mutate(broken)
            with self.assertRaises(ValueError):spool.compare_lanes(client,broken,copy.deepcopy(broken))

    def test_connection_ownership_failure_reaps_only_created_child(self):
        process=Mock(pid=42);conn=Mock()
        with tempfile.TemporaryDirectory() as directory,patch.object(client,'ROOT',directory), \
                patch.object(client,'TARGETS',{'old':{'command':['/unused/fake']}}), \
                patch.object(client,'network_check'),patch.object(client,'port_free'), \
                patch.object(spool.os,'listdir',return_value=['lo']), \
                patch.object(spool.subprocess,'Popen',return_value=process), \
                patch.object(client,'connect_owned',return_value=conn), \
                patch.object(client,'connection_owner',side_effect=ValueError('ownership')), \
                patch.object(client,'cleanup_process',return_value=-signal.SIGTERM) as cleanup:
            with self.assertRaisesRegex(ValueError,'ownership'):
                with spool.owned_daemon(client,'old','upstream','config',14630):self.fail('must not yield')
            cleanup.assert_called_once_with(process);conn.close.assert_called_once();conn.sendall.assert_not_called()
            result=json.loads((Path(directory)/'evidence/old/upstream/result.json').read_text())
            self.assertEqual(result['status'],'failed');self.assertEqual(result['cleanup_exit'],-signal.SIGTERM)

    def test_failed_spool_checkpoint_never_launches_downstream(self):
        roles=[]
        @contextmanager
        def owned(c,lane,role,config,port):
            roles.append(role);yield Mock(),Mock(),{'records':[],'started_at':0},'/unused'
        with tempfile.TemporaryDirectory() as directory,patch.object(client,'ROOT',directory), \
                patch.object(client,'port_free'),patch.object(spool,'owned_daemon',side_effect=owned), \
                patch.object(client,'call',side_effect=[client.hexbytes(b'2.2'),0]), \
                patch.object(spool,'wait_output',side_effect=ValueError('missing spool')):
            with self.assertRaisesRegex(ValueError,'missing spool'):spool.run_lane(client,'old')
            self.assertEqual(roles,['upstream'])

if __name__=='__main__':unittest.main()
