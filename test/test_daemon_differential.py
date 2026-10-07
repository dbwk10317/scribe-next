#!/usr/bin/env python3
"""Offline first-batch replay and fake-process safety; never starts a daemon."""

import binascii
from contextlib import contextmanager
import copy
import errno
import importlib.util
import io
import json
from pathlib import Path
import socket
import signal
import struct
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("daemon_differential", ROOT / "tools/daemon_differential.py")
client = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(client)
SPOOL_SPEC = importlib.util.spec_from_file_location("daemon_spool_case", ROOT / "tools/daemon_spool_case.py")
spool = importlib.util.module_from_spec(SPOOL_SPEC)
SPOOL_SPEC.loader.exec_module(spool)
GAME_SPEC = importlib.util.spec_from_file_location("daemon_game_profile_case", ROOT / "tools/daemon_game_profile_case.py")
game = importlib.util.module_from_spec(GAME_SPEC)
GAME_SPEC.loader.exec_module(game)
FIXTURES = ROOT / "test/fixtures/first_daemon_differential"


class DaemonDifferentialOfflineTests(unittest.TestCase):
    def report(self):
        return json.loads((FIXTURES / "expected.json").read_text())

    def test_verified_wire_and_report_replay(self):
        report = self.report()
        for record in report["records"]:
            name = "%02d-%s" % (record["sequence"], record["method"])
            self.assertEqual((FIXTURES / (name + ".request.bin")).read_bytes(),
                             binascii.unhexlify(record["request_hex"]))
            if not record["oneway"]:
                wire = (FIXTURES / (name + ".reply.bin")).read_bytes()
                self.assertEqual(wire, binascii.unhexlify(record["reply_hex"]))
                self.assertEqual(client.parse_reply(wire[4:], record["method"].encode(), record["sequence"]),
                                 record["value"])
        result = client.compare_lanes(report, copy.deepcopy(report))
        self.assertEqual(result["status"], "passed")
        self.assertTrue(all(result["checks"].values()))

    def test_missing_or_corrupted_evidence_cannot_pass(self):
        old = self.report()
        for mutate in (lambda r: r["records"].pop(),
                       lambda r: r["records"][0].update(reply_hex="00000000"),
                       lambda r: r["records"][0].update(value="wrong"),
                       lambda r: r["records"][8].update(reply_hex="00000000"),
                       lambda r: r.update(files=[])):
            changed = copy.deepcopy(old)
            mutate(changed)
            with self.assertRaises(ValueError):
                client.compare_lanes(old, changed)

    def test_isolation_failure_never_launches_a_process(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "new"
            args = ["harness", "--run-isolated-daemons", "--targets", "never-read.json", "--output", str(output)]
            for uid,euid,interfaces in ((1000,1000,["lo"]), (65534,0,["lo"]), (65534,65534,["lo","eth0"])):
                with patch.object(sys, "argv", args), patch.object(client.os, "getuid", return_value=uid), \
                        patch.object(client.os, "geteuid", return_value=euid), \
                        patch.object(client.os, "listdir", return_value=interfaces), patch.object(client.subprocess, "Popen") as launch:
                    with self.assertRaises(ValueError):
                        client.main()
                    launch.assert_not_called()
                    self.assertFalse(output.exists())

    def test_port_occupancy_or_permission_error_is_not_free(self):
        conn = Mock()
        with patch.object(client.socket, "create_connection", return_value=conn):
            with self.assertRaises(ValueError):
                client.port_free()
            conn.close.assert_called_once()
        with patch.object(client.socket, "create_connection", side_effect=socket.error(errno.EACCES, "denied")):
            with self.assertRaises(socket.error):
                client.port_free()
        with patch.object(client.socket, "create_connection", side_effect=socket.error(errno.ECONNREFUSED, "refused")):
            client.port_free()

    def test_protocol_failure_closes_files_and_reaps_only_owned_child(self):
        process = Mock(pid=42, returncode=None)
        process.poll.side_effect = lambda: process.returncode
        process.wait.side_effect = lambda: process.returncode
        conn = Mock()
        conn.getpeername.return_value = ("127.0.0.1", client.PORT)
        conn.recv.return_value = struct.pack(">I", client.MAX_REPLY + 1)
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(client, "ROOT", directory), \
                patch.object(client, "TARGETS", {"old": {"command": ["/unused/fake-daemon"]}}), \
                patch.object(client, "network_check"), patch.object(client, "port_free"), \
                patch.object(client, "connection_owner", return_value="123"), \
                patch.object(client, "group_exists", side_effect=[True,False,False,False]), \
                patch.object(client.os, "killpg", side_effect=lambda pid,sig: setattr(process,"returncode",-15)) as kill, \
                patch.object(client.os, "getuid", return_value=65534), \
                patch.object(client.os, "listdir", return_value=["lo"]), \
                patch.object(client.subprocess, "Popen", return_value=process) as launch, \
                patch.object(client.socket, "create_connection", return_value=conn):
            with self.assertRaisesRegex(ValueError, "unbounded reply frame"):
                client.run_lane("old")
            kill.assert_called_once_with(42,signal.SIGTERM)
            process.wait.assert_called_once()
            conn.close.assert_called_once()
            for name in ("stdin", "stdout", "stderr"):
                self.assertTrue(launch.call_args.kwargs[name].closed)
            report = json.loads((Path(directory) / "evidence/old/result.json").read_text())
            self.assertEqual(report["status"], "failed")
            self.assertEqual(report["cleanup_exit"], -15)

    def test_owned_session_kill_fallback_also_covers_descendants(self):
        process = Mock(pid=42)
        process.wait.return_value = -9
        alive = [True]
        def signal_group(pid,sig):
            if sig==signal.SIGKILL: alive[0]=False
        with patch.object(client,"group_exists",side_effect=lambda pid: alive[0]), \
                patch.object(client.os,"killpg",side_effect=signal_group) as kill, \
                patch.object(client.time,"time",side_effect=[0,3]):
            self.assertEqual(client.cleanup_process(process),-9)
        self.assertEqual(kill.call_args_list,[unittest.mock.call(42,signal.SIGTERM),unittest.mock.call(42,signal.SIGKILL)])
        process.wait.assert_called_once()

    def test_connected_socket_must_be_owned_by_target_pid(self):
        conn = Mock()
        conn.getpeername.return_value = ("127.0.0.1",client.PORT)
        conn.getsockname.return_value = ("127.0.0.1",40000)
        local = "0100007F:%04X" % client.PORT
        remote = "0100007F:%04X" % 40000
        tcp = "header\n0: %s %s 01 0 0 0 65534 0 123\n" % (local,remote)
        def table(path):
            return io.StringIO(tcp if str(path).endswith("/tcp") else "header\n")
        with patch.object(client.os,"listdir",return_value=["3"]), \
                patch.object(client.os,"readlink",return_value="socket:[123]"), \
                patch("builtins.open",side_effect=table):
            self.assertEqual(client.connection_owner(42,conn),"123")
        with patch.object(client.os,"listdir",return_value=["3"]), \
                patch.object(client.os,"readlink",return_value="socket:[999]"), \
                patch("builtins.open",side_effect=table), \
                patch.object(client.time,"time",side_effect=[0,4]):
            with self.assertRaisesRegex(ValueError,"ownership"):
                client.connection_owner(42,conn)
        conn.sendall.assert_not_called()

    def test_three_store_case_has_explicit_routing_bytes_and_ignore_counts(self):
        entries,delta,unused=client.case_data('stores')
        self.assertEqual([c for c,p in entries],
                         [b'discard']*3+[b'fanout']*3+[b'catA',b'catB',b'catA',b'',b'unknown'])
        self.assertEqual(delta['scribe_overall:received good'],9)
        self.assertEqual((delta['discard:ignored'],delta['fanout:ignored'],delta['scribe_overall:ignored']),
                         (3,3,6))
        files,links=client.expected_outputs('stores')
        self.assertEqual({f['path']:f['hex'] for f in files},
                         {'left/left_00000':'4100420aff7461696c','right/right_00000':'4100420aff7461696c',
                          'category/catA/catA_00000':'4100420aff','category/catB/catB_00000':'7461696c'})
        self.assertEqual(len(links),4)
        fields=client.log_fields(entries)
        self.assertEqual(struct.unpack('>i',fields[4:8])[0],11)

    def test_synthetic_store_report_checks_all_fanout_outputs_and_case_identity(self):
        # Synthetic expectations only: first real store-case execution belongs to the server.
        report=self.report();report['case']='stores'
        entries,delta,unused=client.case_data('stores')
        report['counter_delta']=delta
        report['files'],report['symlinks']=client.expected_outputs('stores')
        report['records'][6]['request_hex']=client.hexbytes(client.framed(b'Log',7,client.log_fields(entries)))
        fields=b'\x0d\x00\x00\x0b\x0a'+struct.pack('>i',len(delta))
        for key,value in sorted(delta.items()):
            fields+=client.string(key.encode())+struct.pack('>q',value)
        fields+=b'\0'
        body=client.string(b'getCounters')+b'\x02'+struct.pack('>i',8)+fields
        report['records'][7].update(reply_hex=client.hexbytes(struct.pack('>I',len(body))+body),value=delta)
        self.assertEqual(client.compare_lanes(report,copy.deepcopy(report),'stores')['status'],'passed')
        with self.assertRaisesRegex(ValueError,'case mismatch'):
            client.compare_lanes(report,copy.deepcopy(report),'file')
        broken=copy.deepcopy(report);broken['files'].pop()
        with self.assertRaisesRegex(ValueError,'output file'):
            client.compare_lanes(broken,copy.deepcopy(broken),'stores')

    def counter_record(self,seq,count):
        values={'fixture:received good':count,'scribe_overall:received good':count}
        fields=b'\x0d\x00\x00\x0b\x0a'+struct.pack('>i',2)
        for key,value in sorted(values.items()):
            fields+=client.string(key.encode())+struct.pack('>q',value)
        body=client.string(b'getCounters')+b'\x02'+struct.pack('>i',seq)+fields+b'\0'
        return {'method':'getCounters','sequence':seq,'oneway':False,'value':values,
                'request_hex':client.hexbytes(client.framed(b'getCounters',seq)),
                'reply_hex':client.hexbytes(struct.pack('>I',len(body))+body)}

    def rotation_report(self):
        report=self.report();report['case']='rotation'
        entries,delta,unused=client.case_data('rotation')
        report['counter_delta']=delta
        report['files'],report['symlinks']=client.expected_outputs('rotation')
        records=report['records'][:8]
        records[6]['request_hex']=client.hexbytes(client.framed(b'Log',7,client.log_fields(entries)))
        records[7]=self.counter_record(8,2)
        for seq,method,oneway,value in ((9,'reinitialize',True,None),(10,'getStatus',False,2),
                                         (11,'Log',False,0),(13,'shutdown',True,None)):
            fields=client.log_fields([(b'fixture',b'Z')]) if seq==11 else b'\0'
            record={'method':method,'sequence':seq,'oneway':oneway,
                    'request_hex':client.hexbytes(client.framed(method.encode(),seq,fields,oneway))}
            if not oneway:
                body=client.string(method.encode())+b'\x02'+struct.pack('>i',seq)+b'\x08\x00\x00'+struct.pack('>i',value)+b'\0'
                record.update(value=value,reply_hex=client.hexbytes(struct.pack('>I',len(body))+body))
            if seq==13: records.append(self.counter_record(12,3))
            records.append(record)
        report['records']=records
        for phase in ('before_reinitialize','after_reinitialize','after_append'):
            files,links=client.rotation_outputs(phase=='after_append')
            report[phase]={'files':files,'symlinks':links}
        return report

    def test_rotation_case_checks_threshold_reopen_append_and_phase_evidence(self):
        report=self.rotation_report()
        self.assertEqual(client.compare_lanes(report,copy.deepcopy(report),'rotation')['status'],'passed')
        self.assertEqual([f['bytes'] for f in report['files']],[5,5,0])
        for mutate in (lambda r:r.pop('after_reinitialize'),
                       lambda r:r['before_reinitialize']['files'][1].update(hex='00'),
                       lambda r:r['records'][8].update(oneway=False),
                       lambda r:r['records'][10].update(request_hex='00'),
                       lambda r:r['records'].__setitem__(7,self.counter_record(8,1)),
                       lambda r:r['records'].__setitem__(11,self.counter_record(12,2))):
            broken=copy.deepcopy(report);mutate(broken)
            with self.assertRaises(ValueError): client.compare_lanes(broken,report,'rotation')

    def test_rotation_snapshot_waits_for_exact_bytes_and_fails_closed(self):
        expected=client.rotation_outputs(False)
        with patch.object(client,'output_snapshot',side_effect=[OSError(errno.ENOENT,'replaced symlink'),([],[]),expected]), \
                patch.object(client.time,'sleep'):
            self.assertEqual(client.rotation_snapshot('/unused'),{'files':expected[0],'symlinks':expected[1]})
        with patch.object(client,'output_snapshot',return_value=([],[])), \
                patch.object(client.time,'time',side_effect=[0,11]):
            with self.assertRaisesRegex(ValueError,'rotation snapshot'):
                client.rotation_snapshot('/unused')
        with patch.object(client,'output_snapshot',side_effect=OSError(errno.EACCES,'denied')):
            with self.assertRaises(OSError): client.rotation_snapshot('/unused')

    def test_crash_restart_preserves_disk_bytes_and_resets_process_counters(self):
        rotation=self.rotation_report()
        before=copy.deepcopy(rotation);before['case']='restart-before'
        before['records']=before['records'][:8]
        before['counter_delta']=client.case_data('restart-before')[1]
        before['files'],before['symlinks']=client.expected_outputs('restart-before')
        before['before_stop']={'files':before['files'],'symlinks':before['symlinks']}
        before['exit']=before['cleanup_exit']=-signal.SIGKILL
        after=copy.deepcopy(before);after['case']='restart-after';after['exit']=after['cleanup_exit']=0
        after['counter_delta']=client.case_data('restart-after')[1]
        after['files'],after['symlinks']=client.expected_outputs('restart-after')
        after['before_stop']={'files':after['files'],'symlinks':after['symlinks']}
        after['after_restart']=before['before_stop']
        after['records'][6]['request_hex']=client.hexbytes(client.framed(b'Log',7,client.log_fields([(b'fixture',b'Z')])))
        after['records'][7]=self.counter_record(8,1)
        after['records'].append(self.report()['records'][8])
        report={'case':'restart','status':'passed','before':before,'after':after}
        self.assertEqual(client.compare_lanes(report,copy.deepcopy(report),'restart')['status'],'passed')
        for mutate in (lambda r:r['before'].update(exit=0),
                       lambda r:r['after'].pop('after_restart'),
                       lambda r:r['before'].pop('cleanup_exit'),
                       lambda r:r['after']['after_restart']['files'][1].update(hex='00'),
                       lambda r:r['after']['records'][4].update(value={'old:ignored':1})):
            broken=copy.deepcopy(report);mutate(broken)
            try: result=client.compare_lanes(broken,report,'restart')
            except ValueError: continue
            self.assertEqual(result['status'],'failed')

        for phase,index in (('before',2),('before',5),('before',6),('after',2),('after',6)):
            broken=copy.deepcopy(report);record=broken[phase]['records'][index]
            wire=binascii.unhexlify(record['reply_hex'])
            record.update(value=1,reply_hex=client.hexbytes(wire[:-5]+struct.pack('>i',1)+wire[-1:]))
            with self.assertRaisesRegex(ValueError,'ALIVE/Log'):
                client.compare_lanes(broken,copy.deepcopy(broken),'restart')

    def test_restart_orchestration_cannot_start_second_process_after_first_failure(self):
        # Exercise real orchestration with fake process; no daemon/namespace setup.
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(client,'ROOT',directory),patch.object(client,'CASE','restart'), \
                patch.object(client,'TARGETS',{'old':{'command':['/unused/fake']}}), \
                patch.object(client,'network_check'),patch.object(client.os,'listdir',return_value=['lo']), \
                patch.object(client,'port_free',side_effect=ValueError('occupied')), \
                patch.object(client.subprocess,'Popen') as launch:
            with self.assertRaisesRegex(ValueError,'occupied'): client.run_lane('old')
            launch.assert_not_called()
            self.assertTrue((Path(directory)/'evidence/old/restart-before/result.json').exists())
            self.assertFalse((Path(directory)/'evidence/old/restart-after').exists())

    def test_file_store_family_oracles_cover_routing_raw_event_padding_and_aliases(self):
        entries,delta,files=client.case_data('file-stores')
        self.assertEqual(len(entries),13);self.assertTrue(all(payload for category,payload in entries))
        self.assertEqual(delta['scribe_overall:received good'],13)
        self.assertEqual(files['bucket/b001/data_00000'],b'A\0B\n\xff')
        self.assertEqual(files['bucket/b002/data_00000'],b'ends\n')
        self.assertEqual(files['bucket/failed/data_00000'],b'no-key')
        self.assertEqual(files['thrift/data_00000'].hex(),'050000004100420aff0000000000000005000000656e64730a')
        self.assertEqual(files['rawthrift/data_00000'],b'A\0B\n\xffends\n')
        self.assertEqual(files['thriftmultifile/tmfA/tmfA_00000'],files['thrift/data_00000'])
        self.assertEqual(len(files),9);self.assertEqual(len(client.expected_outputs('file-stores')[1]),9)
        config=(ROOT/'tools/daemon_file_stores.conf.template').read_text()
        self.assertIn('bucket_type=key_range\nbucket_range=20\n',config)
        self.assertIn('<bucket>\ntype=file',config);self.assertNotIn('<bucket0>',config)
        self.assertIn('categories=tmf*\ntype=thriftmultifile',config)

    def test_synthetic_file_store_report_rejects_missing_bytes_and_wrong_wire_counts(self):
        report=self.report();report['case']='file-stores'
        entries,delta,unused=client.case_data('file-stores')
        report['counter_delta']=delta;report['files'],report['symlinks']=client.expected_outputs('file-stores')
        report['records'][6]['request_hex']=client.hexbytes(client.framed(b'Log',7,client.log_fields(entries)))
        fields=b'\x0d\x00\x00\x0b\x0a'+struct.pack('>i',len(delta))
        for key,value in sorted(delta.items()):fields+=client.string(key.encode())+struct.pack('>q',value)
        body=client.string(b'getCounters')+b'\x02'+struct.pack('>i',8)+fields+b'\0'
        report['records'][7].update(value=delta,reply_hex=client.hexbytes(struct.pack('>I',len(body))+body))
        self.assertEqual(client.compare_lanes(report,copy.deepcopy(report),'file-stores')['status'],'passed')
        for mutate in (lambda r:r['files'].pop(),lambda r:r['symlinks'].pop(),
                       lambda r:r['files'][0].update(hex='00'),
                       lambda r:r['records'].__setitem__(7,self.counter_record(8,13))):
            broken=copy.deepcopy(report);mutate(broken)
            with self.assertRaises(ValueError):client.compare_lanes(broken,copy.deepcopy(broken),'file-stores')

    def mixed_spool_report(self,upstream,downstream):
        report={'case':'mixed-spool','lane':upstream,'downstream_lane':downstream,'status':'passed'}
        requests={
            'upstream':[(b'getVersion',None),(b'Log',0),(b'getCounters',spool.upstream_counters(2)),
                        (b'getStatus',5),(b'getCounters',spool.upstream_counters(2,2)),(b'getStatus',2),
                        (b'Log',0),(b'getCounters',spool.upstream_counters(3,3)),(b'shutdown',None)],
            'downstream':[(b'getVersion',None),(b'getStatus',2),(b'getCounters',{}),
                          (b'getCounters',{'fixture:received good':3,'scribe_overall:received good':3}),
                          (b'shutdown',None)]}
        for role,target in (('upstream',upstream),('downstream',downstream)):
            records=[]
            for seq,(name,value) in enumerate(requests[role],1):
                fields=client.log_fields(spool.ENTRIES if seq==2 else [(b'fixture',b'Z')]) if name==b'Log' else b'\0'
                oneway=name==b'shutdown'
                record={'method':name.decode(),'sequence':seq,'oneway':oneway,
                        'request_hex':client.hexbytes(client.framed(name,seq,fields,oneway))}
                if not oneway:
                    if name==b'getVersion':
                        result=b'\x0b\0\0'+client.string(b'2.2');value=client.hexbytes(b'2.2')
                    elif name==b'getCounters':
                        result=b'\x0d\0\0\x0b\x0a'+struct.pack('>i',len(value))
                        for key,count in sorted(value.items()):result+=client.string(key.encode())+struct.pack('>q',count)
                    else:result=b'\x08\0\0'+struct.pack('>i',value)
                    body=client.string(name)+b'\x02'+struct.pack('>i',seq)+result+b'\0'
                    record.update(value=value,reply_hex=client.hexbytes(struct.pack('>I',len(body))+body))
                records.append(record)
            report[role]={'target_lane':target,'command':['/unused/'+target,'-c','/unused/'+upstream+'-'+role+'.conf'],
                          'records':records,'status':'passed','exit':0,'cleanup_exit':0}
        for phase,data,framed in (('spooled',spool.SPOOL,True),('replayed',spool.PAYLOAD,False),
                                 ('streamed',spool.PAYLOAD+b'Z',False),('final_downstream',spool.PAYLOAD+b'Z',False)):
            report[phase]=spool.outputs(client,data,framed)
        report.update(drained={'files':[],'symlinks':[]},final_spool={'files':[],'symlinks':[]})
        return report

    def test_mixed_spool_requires_both_directions_commands_and_exact_replay_evidence(self):
        targets={lane:{'command':['/unused/'+lane]} for lane in ('old','modern')}
        old=self.mixed_spool_report('old','modern');new=self.mixed_spool_report('modern','old')
        with patch.object(client,'ROOT','/unused'),patch.object(client,'TARGETS',targets):
            result=spool.compare_lanes(client,old,new,'mixed-spool')
            self.assertEqual(result['status'],'passed')
            self.assertEqual(result['directions'],[{'upstream':'old','downstream':'modern'},
                                                   {'upstream':'modern','downstream':'old'}])
            self.assertIn('no cross-version spool-reader',result['scope'])
            for mutate in (lambda r:r.update(case='spool'),lambda r:r.update(downstream_lane='old'),
                           lambda r:r['downstream'].update(target_lane='old'),
                           lambda r:r['downstream']['command'].__setitem__(0,'/unused/old'),
                           lambda r:r['replayed'].update(files=spool.outputs(client,b'tailA\0B\n\xff')['files']),
                           lambda r:r['upstream'].pop('cleanup_exit')):
                broken=copy.deepcopy(old);mutate(broken)
                with self.assertRaises(ValueError):spool.compare_lanes(client,broken,new,'mixed-spool')
            with self.assertRaises(ValueError):spool.compare_lanes(client,new,old,'mixed-spool')

    def test_spool_and_opt_in_mixed_spool_dispatch_keep_existing_port_guards(self):
        for case,downstream_lanes in (('spool',(None,None)),('mixed-spool',('modern','old'))):
            with self.subTest(case=case),tempfile.TemporaryDirectory() as directory:
                targets=Path(directory)/'targets.json'
                targets.write_text(json.dumps({lane:{'command':[sys.executable]} for lane in ('old','modern')}))
                args=['harness','--run-isolated-daemons','--targets',str(targets),'--output',str(Path(directory)/'new'),'--case',case]
                with patch.object(sys,'argv',args),patch.dict(sys.modules,{client.__name__:client,'daemon_spool_case':spool}), \
                        patch.object(client,'network_check') as isolation,patch.object(client,'port_free') as ports, \
                        patch.object(client,'ROOT'),patch.object(client,'PORT'),patch.object(client,'CASE'),patch.object(client,'TARGETS'), \
                        patch.object(spool,'run_lane',side_effect=[{'lane':'old'},{'lane':'modern'}]) as run, \
                        patch.object(spool,'compare_lanes',return_value={'status':'passed'}) as compare, \
                        patch('builtins.print'),patch.object(client.subprocess,'Popen') as launch:
                    client.main()
                    isolation.assert_called_once_with();launch.assert_not_called()
                    self.assertEqual(ports.call_args_list,[unittest.mock.call(),unittest.mock.call(14631)])
                    self.assertEqual(run.call_args_list,[unittest.mock.call(client,'old',downstream_lanes[0]),
                                                        unittest.mock.call(client,'modern',downstream_lanes[1])])
                    compare.assert_called_once_with(client,{'lane':'old'},{'lane':'modern'},case)

    def test_mixed_downstream_keeps_socket_ownership_and_owned_child_cleanup(self):
        process=Mock(pid=42);conn=Mock()
        targets={'old':{'command':['/unused/old']},'modern':{'command':['/unused/modern'],'environment':{'TARGET':'modern'}}}
        with tempfile.TemporaryDirectory() as directory,patch.object(client,'ROOT',directory),patch.object(client,'TARGETS',targets), \
                patch.object(client,'network_check') as isolation,patch.object(client,'port_free') as ports, \
                patch.object(spool.os,'listdir',return_value=['lo']), \
                patch.object(spool.subprocess,'Popen',return_value=process) as launch, \
                patch.object(client,'connect_owned',return_value=conn), \
                patch.object(client,'connection_owner',side_effect=ValueError('ownership')), \
                patch.object(client,'cleanup_process',return_value=-signal.SIGTERM) as cleanup:
            with self.assertRaisesRegex(ValueError,'ownership'):
                with spool.owned_daemon(client,'old','downstream','config',14631,target_lane='modern'):
                    self.fail('ownership failure must not yield')
            isolation.assert_called_once_with()
            self.assertEqual(ports.call_args_list,[unittest.mock.call(14631),unittest.mock.call(14631)])
            self.assertEqual(launch.call_args.args[0],['/unused/modern','-c',directory+'/old-downstream.conf'])
            self.assertEqual(launch.call_args.kwargs['env']['TARGET'],'modern')
            cleanup.assert_called_once_with(process);conn.close.assert_called_once();conn.sendall.assert_not_called()
            result=json.loads((Path(directory)/'evidence/old/downstream/result.json').read_text())
            self.assertEqual((result['lane'],result['target_lane'],result['cleanup_exit']),('old','modern',-signal.SIGTERM))

    def game_record(self,name,seq,fields,value):
        oneway=name==b'shutdown'
        record={'method':name.decode(),'sequence':seq,'oneway':oneway,
                'request_hex':client.hexbytes(client.framed(name,seq,fields,oneway))}
        if oneway:return record
        if isinstance(value,dict):
            result=b'\x0d\0\0\x0b\x0a'+struct.pack('>i',len(value))
            for key,count in sorted(value.items()):result+=client.string(key.encode())+struct.pack('>q',count)
        elif isinstance(value,str):result=b'\x0b\0\0'+client.string(binascii.unhexlify(value))
        else:result=b'\x08\0\0'+struct.pack('>i',value)
        body=client.string(name)+b'\x02'+struct.pack('>i',seq)+result+b'\0'
        record.update(value=value,reply_hex=client.hexbytes(struct.pack('>I',len(body))+body))
        return record

    def game_report(self,date='2026-10-07'):
        # Synthetic expectations only: no real old/new game-profile execution is recorded.
        report={'case':'game-profile','lane':'old','utc_date':date,'status':'passed'}
        for role,requests in game.specification(client).items():
            report[role]={'status':'passed','exit':0,'cleanup_exit':0,
                          'records':[self.game_record(name,seq,fields,value)
                                     for seq,(name,fields,value) in enumerate(requests,1)]}
        report.update(copy.deepcopy(game.phase_outputs(client,date)))
        return report

    def test_game_profile_config_bytes_links_and_counters_are_explicit(self):
        config=(ROOT/'tools/daemon_game_profile.conf.template').read_text()
        for text in ('max_msg_per_second=2000000\n','max_queue_size=10000000\n','check_interval=1\n',
                     'categories=fixture-login fixture-session fixture-metrics-*\ntype=multi\n',
                     'category=ext-*\ntype=buffer\n','category=default\ntype=buffer\n',
                     'max_size=1000000 #1M\n','rotate_period=1h\nadd_newlines=1\n','use_conn_pool=yes\n'):
            self.assertIn(text,config)
        for absent in ('new_thread_per_category','report_success','retry_interval_range=0','service_list',
                       'dynamic_config_type','type=bucket','type=thriftfile'):
            self.assertNotIn(absent,config)
        self.assertEqual(config.count('use_conn_pool'),1)
        self.assertEqual(config.count('retry_interval=10\nretry_interval_range=1\n'),4)
        self.assertEqual(config.count('base_filename=thisisoverwritten\n'),6)
        down_config=game.downstream_config(client,'/unused')
        self.assertIn('category=default\n',down_config);self.assertIn('add_newlines=1\n',down_config)
        self.assertEqual([p for c,p in game.entries(client) if c==b'fixture-login'],client.PAYLOADS)
        spooled={f['path']:f['hex'] for f in game.upstream_outputs(client,'2026-10-07','spooled')['files']}
        self.assertEqual(spooled,{
            'relay-spool/fixture-login/fixture-login_00000':'060000004100420aff0a010000000a050000007461696c0a',
            'relay-spool/fixture-session/fixture-session_00000':'0300000053310a',
            'relay-spool/fixture-metrics-cpu/fixture-metrics-cpu_00000':'060000006370753d370a',
            'ext-spool/ext-alpha/ext-alpha_00000':'0600000065787400780a',
            'local/fixture-login/fixture-login-2026-10-07_00000':'4100420aff0a0a7461696c0a',
            'local/fixture-session/fixture-session-2026-10-07_00000':'53310a',
            'local/fixture-metrics-cpu/fixture-metrics-cpu-2026-10-07_00000':'6370753d370a',
            'default/fixture-other/fixture-other-2026-10-07_00000':'6f74686572'})
        drained=game.upstream_outputs(client,'2026-10-07','drained')
        self.assertEqual(len(drained['files']),4);self.assertFalse([f for f in drained['files'] if 'spool' in f['path']])
        self.assertIn({'path':'local/fixture-login/fixture-login_current','target':'fixture-login-2026-10-07_00000'},
                      drained['symlinks'])
        startup=game.upstream_outputs(client,'2026-10-07','startup')
        self.assertEqual([(f['path'],f['bytes']) for f in startup['files']],
                         [('local/fixture-login/fixture-login-2026-10-07_00000',0),
                          ('local/fixture-session/fixture-session-2026-10-07_00000',0),
                          ('relay-spool/fixture-login/fixture-login_00000',0),
                          ('relay-spool/fixture-session/fixture-session_00000',0)])
        down=game.downstream_outputs(client)
        self.assertEqual({f['path']:f['hex'] for f in down['files']},{
            'fixture-login/fixture-login_00000':'4100420aff0a0a0a0a7461696c0a0a',
            'fixture-session/fixture-session_00000':'53310a0a',
            'fixture-metrics-cpu/fixture-metrics-cpu_00000':'6370753d370a0a',
            'ext-alpha/ext-alpha_00000':'65787400780a0a'})
        self.assertIn({'path':'ext-alpha/ext-alpha_current','target':'ext-alpha_00000'},down['symlinks'])
        self.assertEqual(game.STARTUP,{'fixture-login:retries':1,'fixture-session:retries':1,'scribe_overall:retries':2})
        delta={k:v-game.STARTUP.get(k,0) for k,v in game.SPOOLED.items() if v!=game.STARTUP.get(k,0)}
        self.assertEqual(delta,{'fixture-login:received good':3,'fixture-session:received good':1,
                                'fixture-metrics-cpu:received good':1,'ext-alpha:received good':1,
                                'fixture-other:received good':1,'scribe_overall:received good':7,
                                'scribe_overall:received blank category':1,'fixture-metrics-cpu:retries':1,
                                'ext-alpha:retries':1,'scribe_overall:retries':2})
        self.assertEqual(set(game.REPLAYED)-set(game.SPOOLED),{'scribe_overall:sent'})
        self.assertEqual(game.REPLAYED['scribe_overall:sent'],game.DOWNSTREAM['scribe_overall:received good'])

    def test_synthetic_game_profile_report_passes_and_rejects_mutations(self):
        old=self.game_report();new=copy.deepcopy(old);new['lane']='modern'
        result=game.compare_lanes(client,old,new)
        self.assertEqual(result['status'],'passed');self.assertTrue(all(result['checks'].values()))
        self.assertEqual((len(old['upstream']['records']),len(old['downstream']['records'])),(12,5))
        self.assertEqual(sum(k.startswith('upstream-reply') for k in result['checks']),10)
        self.assertEqual(sum(k.startswith('downstream-reply') for k in result['checks']),3)
        wrong=dict(game.SPOOLED,**{'scribe_overall:retries':5})
        for mutate in (lambda r:r.update(case='spool'),
                       lambda r:r['replayed']['files'].pop(),
                       lambda r:r['upstream']['records'].__setitem__(7,self.game_record(b'getCounters',8,b'\0',wrong)),
                       lambda r:next(f for f in r['replayed']['files'] if f['path'].startswith('fixture-login/'))
                                .update(hex='4100420aff0a0a7461696c0a'),
                       lambda r:r['startup']['files'].pop(),
                       lambda r:r['upstream']['records'][8].update(reply_hex='00000000'),
                       lambda r:r['downstream'].pop('cleanup_exit'),
                       lambda r:r.update(utc_date='2026-10-08')):
            broken=copy.deepcopy(old);mutate(broken)
            with self.assertRaises(ValueError):game.compare_lanes(client,broken,new)
        # Dated names are compared raw: consistent lanes from different UTC dates fail.
        self.assertEqual(game.compare_lanes(client,old,self.game_report('2026-10-08'))['status'],'failed')

    def test_game_profile_failed_spool_checkpoint_never_launches_downstream(self):
        roles=[]
        @contextmanager
        def owned(c,lane,role,config,port,*rest):
            roles.append(role);yield Mock(),Mock(),{'records':[],'started_at':client.time.time()},'/unused'
        values=[value for name,fields,value in game.specification(client)['upstream'][:7]]
        with tempfile.TemporaryDirectory() as directory,patch.object(client,'ROOT',directory), \
                patch.object(client,'port_free'),patch.object(spool,'owned_daemon',side_effect=owned), \
                patch.object(client,'call',side_effect=values), \
                patch.object(spool,'wait_output',side_effect=[{},ValueError('missing spool')]):
            with self.assertRaisesRegex(ValueError,'missing spool'):game.run_lane(client,spool,'old')
        self.assertEqual(roles,['upstream'])

    def test_game_profile_dispatch_keeps_isolation_and_two_port_guards(self):
        with tempfile.TemporaryDirectory() as directory:
            targets=Path(directory)/'targets.json'
            targets.write_text(json.dumps({lane:{'command':[sys.executable]} for lane in ('old','modern')}))
            args=['harness','--run-isolated-daemons','--targets',str(targets),'--output',str(Path(directory)/'new'),'--case','game-profile']
            modules={client.__name__:client,'daemon_spool_case':spool,'daemon_game_profile_case':game}
            with patch.object(sys,'argv',args),patch.dict(sys.modules,modules), \
                    patch.object(client,'network_check') as isolation,patch.object(client,'port_free') as ports, \
                    patch.object(client,'ROOT'),patch.object(client,'PORT'),patch.object(client,'CASE'),patch.object(client,'TARGETS'), \
                    patch.object(game,'run_lane',side_effect=[{'lane':'old'},{'lane':'modern'}]) as run, \
                    patch.object(game,'compare_lanes',return_value={'status':'passed'}) as compare, \
                    patch('builtins.print'),patch.object(client.subprocess,'Popen') as launch:
                client.main()
                isolation.assert_called_once_with();launch.assert_not_called()
                self.assertEqual(ports.call_args_list,[unittest.mock.call(),unittest.mock.call(14631)])
                self.assertEqual(run.call_args_list,[unittest.mock.call(client,spool,'old'),unittest.mock.call(client,spool,'modern')])
                compare.assert_called_once_with(client,{'lane':'old'},{'lane':'modern'})


if __name__ == "__main__":
    unittest.main()
