#!/usr/bin/env python3
"""Offline option/counter/exception batch replay; never starts a daemon."""
import binascii,copy,importlib.util,struct,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
client=load('fb303_client_test',ROOT/'tools/daemon_differential.py')
case=load('fb303_case_test',ROOT/'tools/daemon_fb303_case.py')

class Fb303OfflineTests(unittest.TestCase):
    def body(self,name,seq,value,exception=False):
        if exception:
            fields=b'\x0b\0\x01'+client.string(binascii.unhexlify(value['message_hex']))+b'\x08\0\x02'+struct.pack('>i',value['type'])
        elif value is None:fields=b''
        elif name in (b'getOption',):fields=b'\x0b\0\0'+client.string(binascii.unhexlify(value))
        elif name in (b'getOptions',b'getCounters'):
            kind=11 if name==b'getOptions' else 10
            fields=b'\x0d\0\0\x0b'+bytes([kind])+struct.pack('>i',len(value))
            for key,item in sorted(value.items()):
                fields+=client.string(binascii.unhexlify(key) if kind==11 else key.encode())
                fields+=client.string(binascii.unhexlify(item)) if kind==11 else struct.pack('>q',item)
        elif name==b'getCounter':fields=b'\x0a\0\0'+struct.pack('>q',value)
        else:fields=b'\x08\0\0'+struct.pack('>i',value)
        return client.string(name)+bytes([3 if exception else 2])+struct.pack('>i',seq)+fields+b'\0'

    def report(self):
        records=[]
        for seq,(name,fields,value,exception) in enumerate(case.specification(client),1):
            oneway=name==b'shutdown'
            r={'method':name.decode(),'sequence':seq,'oneway':oneway,'request_hex':client.hexbytes(client.framed(name,seq,fields,oneway))}
            if exception:r['exception']=True
            if not oneway:
                body=self.body(name,seq,value,exception)
                r.update(value=value,reply_hex=client.hexbytes(struct.pack('>I',len(body))+body))
            records.append(r)
        files,links=client.expected_outputs('file')
        return {'case':'fb303','status':'passed','exit':0,'cleanup_exit':0,'records':records,'files':files,'symlinks':links}

    def test_binary_option_state_single_counter_and_exception_recovery_replay(self):
        report=self.report();result=case.compare_lanes(client,report,copy.deepcopy(report))
        self.assertEqual(result['status'],'passed');self.assertTrue(all(result['checks'].values()))
        self.assertEqual(report['records'][2]['value'],{client.hexbytes(case.MISSING):''})
        self.assertEqual(report['records'][4]['value'],client.hexbytes(b'one\0\xff'))
        self.assertEqual(report['records'][8]['value'],{})
        self.assertEqual(report['records'][9]['value']['type'],1)
        self.assertEqual(len(report['records']),15)

    def test_wrong_void_map_exception_types_headers_or_trailing_bytes_rejected(self):
        bodies=[self.body(b'setOption',4,None),self.body(b'getOptions',7,{client.hexbytes(case.KEY):client.hexbytes(case.SECOND)}),
                self.body(case.UNKNOWN,10,case.specification(client)[9][2],True)]
        for body,name,seq,exception in ((bodies[0],b'setOption',4,False),(bodies[1],b'getOptions',7,False),(bodies[2],case.UNKNOWN,10,True)):
            parse=client.parse_application_exception if exception else client.parse_reply
            parse(body,name,seq)
            for broken in (body[:-1],body+b'\0',body[:4]+b'x'+body[5:]):
                with self.assertRaises(ValueError):parse(broken,name,seq)
        duplicate=client.string(b'getOptions')+b'\x02'+struct.pack('>i',7)+b'\x0d\0\0\x0b\x0b'+struct.pack('>i',2)
        duplicate+=(client.string(case.KEY)+client.string(b'value'))*2+b'\0'
        with self.assertRaises(ValueError):client.parse_reply(duplicate,b'getOptions',7)
        for method,wrong_kind in ((b'getOptions',10),(b'getCounters',11)):
            wrong_map=client.string(method)+b'\x02'+struct.pack('>i',7)+b'\x0d\0\0\x0b'+bytes([wrong_kind])+struct.pack('>i',0)+b'\0'
            with self.assertRaises(ValueError):client.parse_reply(wrong_map,method,7)
        bad_exception=client.string(case.UNKNOWN)+b'\x03'+struct.pack('>i',10)+b'\x0a\0\x02'+struct.pack('>q',1)+b'\0'
        with self.assertRaises(ValueError):client.parse_application_exception(bad_exception,case.UNKNOWN,10)

    def test_corrupt_or_semantically_wrong_report_cannot_pass(self):
        for mutate in (lambda r:r['records'].pop(),lambda r:r.pop('cleanup_exit'),lambda r:r['files'].pop(),
                       lambda r:r['records'][9].update(exception=False),lambda r:r['records'][3].update(oneway=True),
                       lambda r:r['records'][12].update(value={})):
            broken=self.report();mutate(broken)
            with self.assertRaises(ValueError):case.compare_lanes(client,broken,copy.deepcopy(broken))
        wrong=self.report();value={'type':2,'message_hex':case.specification(client)[9][2]['message_hex']}
        body=self.body(case.UNKNOWN,10,value,True)
        wrong['records'][9].update(value=value,reply_hex=client.hexbytes(struct.pack('>I',len(body))+body))
        with self.assertRaises(ValueError):case.compare_lanes(client,wrong,copy.deepcopy(wrong))

if __name__=='__main__':unittest.main()
