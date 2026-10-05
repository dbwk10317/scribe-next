#!/usr/bin/env python3
"""Offline fixed-profile metrics/record integrity; never launches a daemon."""
import copy,hashlib,importlib.util,json,math,struct,tempfile,unittest
from pathlib import Path
from unittest.mock import Mock,patch
from contextlib import contextmanager
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parents[1]
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
client=load('performance_client_test',ROOT/'tools/daemon_differential.py')
perf=load('performance_case_test',ROOT/'tools/daemon_performance_case.py')

class PerformanceOfflineTests(unittest.TestCase):
    def record(self,name,seq,value=None):
        oneway=name==b'shutdown';r={'method':name.decode(),'sequence':seq,'oneway':oneway,'request_hex':client.hexbytes(client.framed(name,seq,b'\0',oneway))}
        if oneway:return r
        if name==b'getVersion':fields=b'\x0b\0\0'+client.string(b'2.2');value=client.hexbytes(b'2.2')
        elif name==b'getCounters':
            fields=b'\x0d\0\0\x0b\x0a'+struct.pack('>i',len(value))
            for key,count in sorted(value.items()):fields+=client.string(key.encode())+struct.pack('>q',count)
        else:fields=b'\x08\0\0'+struct.pack('>i',value)
        body=client.string(name)+b'\x02'+struct.pack('>i',seq)+fields+b'\0'
        r.update(value=value,reply_hex=client.hexbytes(struct.pack('>I',len(body))+body));return r

    def batch(self,producer,first,seq):
        wire=client.framed(b'Log',seq,client.log_fields([(b'fixture',perf.payload(producer,i)) for i in range(first,first+perf.BATCH)]))
        return {'producer':producer,'first':first,'sequence':seq,'count':perf.BATCH,'request_bytes':len(wire),'request_sha256':hashlib.sha256(wire).hexdigest(),
                'reply_hex':self.record(b'Log',seq,0)['reply_hex'],'latency_seconds':0.01}

    def trial(self,lane,index):
        records=[self.record(b'getVersion',1),self.record(b'getStatus',2,2),self.record(b'getCounters',3,{}),
                 self.record(b'getCounters',5,perf.counters(perf.WARMUP)),self.record(b'getCounters',6,perf.counters(perf.TOTAL+perf.WARMUP)),self.record(b'shutdown',7)]
        return {'lane':lane,'trial':index,'status':'passed','producer_owned_inodes':['1','2','3','4'],'child':{'status':'passed','exit':0,'cleanup_exit':0,'records':records},
                'warmup':self.batch(0,0,4),'producers':[{'status':'passed','records':[self.batch(p,(perf.WARMUP if p==0 else 0)+i*perf.BATCH,i+1) for i in range(perf.MESSAGES//perf.BATCH)]} for p in range(perf.PRODUCERS)],
                'file':{'bytes':(perf.TOTAL+perf.WARMUP)*perf.SIZE,'records':perf.TOTAL+perf.WARMUP,'producer_counts':[perf.MESSAGES+perf.WARMUP]+[perf.MESSAGES]*3,'raw_sha256':'0'*64},
                'usage_before':{'cpu_ticks':10,'clock_ticks_per_second':100,'vmhwm_kib':1000},'usage_after':{'cpu_ticks':20,'clock_ticks_per_second':100,'vmhwm_kib':2000},
                'daemon_cpu_seconds':0.1,'vmhwm_kib':2000,'client_cpu_seconds':0.2,
                'ack_seconds':1,'file_complete_seconds':2,'batch_latency_p95_seconds':0.01,'batch_latency_count':64,
                'ack_messages_per_second':perf.TOTAL,'ack_payload_mib_per_second':16,'complete_payload_mib_per_second':8}

    def test_fixed_inventory_rejects_loss_duplicate_reorder_or_changed_bytes(self):
        records=[perf.payload(0,0),perf.payload(1,0),perf.payload(0,1),perf.payload(2,0),perf.payload(3,0)]
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'data';path.write_bytes(b''.join(records))
            verified=perf.verify_file(path,warmup=1,messages=1)
            self.assertEqual(verified['producer_counts'],[2,1,1,1]);self.assertEqual(verified['records'],5)
            for values in (records[:-1],records+[records[0]],[records[2],records[1],records[0]]+records[3:],records[:-1]+[records[-1][:-1]+b'z']):
                path.write_bytes(b''.join(values))
                with self.assertRaises(ValueError):perf.verify_file(path,warmup=1,messages=1)

    def test_percentile_and_synthetic_measurement_are_descriptive_not_threshold(self):
        self.assertEqual(perf.percentile95(list(range(1,65))),61)
        order=[('old',0),('modern',0),('modern',1),('old',1),('old',2),('modern',2)]
        trials=[self.trial(lane,index) for lane,index in order]
        summary=perf.summarize(client,trials)
        self.assertEqual(summary['status'],'passed');self.assertIn('no threshold',summary['verdict'])
        self.assertEqual(summary['modern_over_old_ack_ratio'],1)
        trials[0],trials[1]=trials[1],trials[0]
        with self.assertRaisesRegex(ValueError,'alternating'):perf.summarize(client,trials)

    def test_corrupt_wire_counts_duration_or_cleanup_cannot_pass(self):
        source=self.trial('old',0)
        for mutate in (lambda r:r['child'].pop('cleanup_exit'),lambda r:r['producers'][1]['records'][0].update(request_sha256='0'*64),
                       lambda r:r['child']['records'].__setitem__(4,self.record(b'getCounters',6,perf.counters(perf.TOTAL))),
                       lambda r:r.update(producer_owned_inodes=['1']*4),lambda r:r.update(ack_seconds=float('nan')),lambda r:r.update(batch_latency_count=63),lambda r:r['file'].update(producer_counts=[1,2,3,4])):
            broken=copy.deepcopy(source);mutate(broken)
            with self.assertRaises(ValueError):perf.validate_trial(client,broken)
        wrong_file=copy.deepcopy(source['file']);wrong_file['raw_sha256']='f'*64
        with patch.object(client,'ROOT','/unused'),patch.object(perf,'verify_output',return_value=wrong_file):
            with self.assertRaisesRegex(ValueError,'persisted'):perf.validate_trial(client,source,verify_output_files=True)


    def test_producer_failure_closes_all_clients_joins_threads_and_exits_owned_context(self):
        process=Mock(pid=42);clients=[Mock(),Mock()];cleanup=[]
        @contextmanager
        def owned(c,lane,role,config,port):
            try:yield process,Mock(),{'records':[]},'/unused'
            finally:cleanup.append(process)
        helpers=SimpleNamespace(owned_daemon=owned,shutdown=Mock())
        def batch(c,conn,producer,first,seq,prepared=None):
            if seq==4:return {'latency_seconds':0.01}
            if producer==0:raise ValueError('injected producer failure')
            return {'latency_seconds':0.01}
        existing_threads=set(perf.threading.enumerate())
        with tempfile.TemporaryDirectory() as directory,patch.object(client,'ROOT',directory), \
                patch.object(perf,'PRODUCERS',2),patch.object(perf,'MESSAGES',1), \
                patch.object(perf,'BATCH',1),patch.object(perf,'WARMUP',1),patch.object(perf,'TOTAL',2), \
                patch.object(client,'call',side_effect=[client.hexbytes(b'2.2'),2,{},perf.counters(1)]), \
                patch.object(client,'network_check'),patch.object(client,'connect_owned',side_effect=clients), \
                patch.object(client,'connection_owner',side_effect=['101','102']), \
                patch.object(perf,'wait_size'),patch.object(perf,'process_usage',return_value={}), \
                patch.object(perf,'batch_record',side_effect=batch):
            with self.assertRaisesRegex(ValueError,'producer failed'):perf.run_trial(client,helpers,'old',0)
        for conn in clients:conn.shutdown.assert_called_once();conn.close.assert_called_once()
        self.assertEqual(cleanup,[process]);helpers.shutdown.assert_not_called()
        self.assertEqual(set(perf.threading.enumerate()),existing_threads)

    def test_failed_trial_stops_alternating_run_before_next_launch(self):
        with patch.object(perf,'run_trial',side_effect=ValueError('owned connection failed')) as trial:
            with self.assertRaisesRegex(ValueError,'owned connection'):perf.run_comparison(client,None)
            trial.assert_called_once_with(client,None,'old',0)

if __name__=='__main__':unittest.main()
