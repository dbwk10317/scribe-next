import hashlib,json,os,pathlib,socket,subprocess,sys,tempfile,time

def run(command):
    result=subprocess.run(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,universal_newlines=True,timeout=60)
    if result.returncode:
        raise RuntimeError('{}: {}: {}'.format(command,result.returncode,result.stdout+result.stderr))
    return result.stdout.strip()

if not any(pathlib.Path(p).is_file() for p in ("/.dockerenv","/run/.containerenv")) or os.getuid()!=0:
    raise SystemExit("Run only as root inside the owned Docker or Podman test container")

# Reuse independent original-IDL wire expectations, without installed clients.
import loopback_rpc as tcp


def fixture_snapshot(root):
    return {str(p.relative_to(root)): {'sha256': hashlib.sha256(p.read_bytes()).hexdigest(),
            'mode': p.stat().st_mode, 'uid': p.stat().st_uid, 'gid': p.stat().st_gid}
            for p in (root / 'scribe.conf', root / 'data/received_00000')}


def daemon_round(root, payloads, expected_output):
    stderr=root / 'daemon.stderr'
    with stderr.open('ab') as log:
        process=subprocess.Popen(['/opt/scribe-next-dev/bin/scribed', '-c', str(root / 'scribe.conf')],
                                 cwd=str(root), stdin=subprocess.DEVNULL, stdout=log, stderr=log)
        try:
            deadline=time.monotonic()+10
            while True:
                assert process.poll() is None, stderr.read_text()
                try:
                    connection=socket.create_connection(('127.0.0.1',1463),timeout=1)
                    break
                except ConnectionRefusedError:
                    if time.monotonic()>=deadline:
                        raise AssertionError('installed daemon startup deadline')
                    time.sleep(0.02)
            with connection:
                assert connection.getpeername()==('127.0.0.1',1463)
                # The namespace contains only this test's owned daemon; verify its socket inode.
                inodes=set()
                for p in pathlib.Path('/proc/{}/fd'.format(process.pid)).iterdir():
                    try:
                        inodes.add(os.readlink(str(p)))
                    except FileNotFoundError:
                        pass  # Other descriptors may close while the daemon is running.
                socket_ids={x[8:-1] for x in inodes if x.startswith('socket:[')}
                listeners=[line.split() for line in pathlib.Path('/proc/net/tcp').read_text().splitlines()[1:]]
                assert any(row[1].endswith(':05B7') and row[3]=='0A' and row[9] in socket_ids for row in listeners)
                connection.sendall(tcp.message(b'getStatus',1))
                assert tcp.receive_frame(connection)==tcp.reply(b'getStatus',1,tcp.result_i32(2))
                connection.sendall(tcp.message(b'Log',2,tcp.log_fields([(b'accepted',v) for v in payloads])))
                assert tcp.receive_frame(connection)==tcp.reply(b'Log',2,tcp.result_i32(0))
                connection.sendall(tcp.message(b'getCounter',3,tcp.string_argument(b'accepted:received good')))
                assert tcp.receive_frame(connection)==tcp.reply(b'getCounter',3,tcp.result_i64(len(payloads)))
                connection.sendall(tcp.message(b'shutdown',4,oneway=True))
                code=process.wait(timeout=10)
                assert code==0, stderr.read_text()
            data=(root / 'data/received_00000').read_bytes()
            assert data==expected_output,(data,expected_output)
            return {'log_reply':'OK','received_good':len(payloads),'shutdown_exit':code,
                    'output_hex':data.hex(),'output_sha256':hashlib.sha256(data).hexdigest()}
        except BaseException:
            sys.stderr.write(stderr.read_text(errors='replace')[-65536:])
            raise
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill(); process.wait(timeout=2)


def reinstall_fixture(package):
    with tempfile.TemporaryDirectory(prefix='scribe-installed-rpm-') as directory:
        root=pathlib.Path(directory)
        (root / 'scribe.conf').write_text('port=1463\nnum_thrift_server_threads=2\n'
            '<store>\ncategory=accepted\ntype=file\nfile_path='+str(root / 'data')+'\n'
            'base_filename=received\nrotate_period=never\ncreate_symlink=no\nadd_newlines=0\n'
            'target_write_size=1000000\nmax_write_interval=3600\n</store>\n')
        first=(b'A\x00B\n\xff\xc3\xa9', b'before\n')
        before=daemon_round(root,first,b''.join(first))
        snapshot=fixture_snapshot(root)
        run(['rpm','-U','--replacepkgs',package])
        assert run(['rpm','-V','scribe-next-dev'])==''
        assert fixture_snapshot(root)==snapshot
        after=daemon_round(root,(b'tail\x00\xff\n',),b''.join(first)+b'tail\x00\xff\n')
        return {'same_rpm_reinstall':'passed','config_and_log_bytes_mode_owner_preserved':True,
                'before':before,'after':after,'fixture_only':True}


package=sys.argv[1]
expected=json.loads(pathlib.Path('/expected-licenses.json').read_text())
name=run(['rpm','-qp','--queryformat','%{NAME}',package])
assert name=='scribe-next-dev'
files=run(['rpm','-qpl',package]).splitlines()
scripts=run(['rpm','-qp','--scripts',package]);assert not scripts,scripts
requires=run(['rpm','-qp','--requires',package])
provides=run(['rpm','-qp','--provides',package])
run(['rpm','-i',package])
assert run(['rpm','-V',name])==''
license_base=next(x for x in files if x.endswith('/licenses/fb303/LICENSE')).rsplit('/licenses/fb303/LICENSE',1)[0]
licenses=[]
for suffix,digest in sorted(expected.items()):
    p=pathlib.Path(license_base)/suffix
    actual=hashlib.sha256(p.read_bytes()).hexdigest()
    assert actual==digest,(str(p),actual,digest)
    licenses.append({'path':str(p),'sha256':actual})
assert '/opt/scribe-next-dev/bin/scribed' in files
assert all(x.startswith('/opt/scribe-next-dev/') or x=='/opt/scribe-next-dev' or x.startswith(license_base+'/') or x==license_base or x.startswith('/usr/lib/.build-id/') or x=='/usr/lib/.build-id' for x in files),files
build_ids=[pathlib.Path(x) for x in files if x.startswith('/usr/lib/.build-id/') and pathlib.Path(x).is_symlink()]
assert len(build_ids)==3
assert all(str(p.resolve()).startswith('/opt/scribe-next-dev/') for p in build_ids)
ldd=run(['ldd','/opt/scribe-next-dev/bin/scribed']);assert 'not found' not in ldd,ldd
for line in ldd.splitlines():
    assert 'libboost_' not in line,line
    if 'libthrift' in line:
        assert '/opt/scribe-next-dev/deps/' in line,line
help_text=run(['/opt/scribe-next-dev/bin/scribed','--help'])
assert help_text
daemon_reinstall=reinstall_fixture(package)
run(['rpm','-e',name])
assert not pathlib.Path('/opt/scribe-next-dev').exists()
assert not pathlib.Path(license_base).exists()
assert all(not p.is_symlink() and not p.exists() for p in build_ids)
q=subprocess.run(['rpm','-q',name],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
assert q.returncode!=0
result={'release':pathlib.Path('/etc/rocky-release').read_text().strip(),
    'status':'passed','package_sha256':hashlib.sha256(pathlib.Path(package).read_bytes()).hexdigest(),
    'requires':requires,'provides':provides,'scripts':scripts,'files':files,
    'licenses':licenses,'ldd':ldd,'installed_help':help_text,
    'rpm_install':'passed','rpm_verify':'passed','license_hashes':'passed','rpm_remove':'passed',
    'package_dirs_after_remove':'absent','loader_environment':os.environ.get('LD_LIBRARY_PATH'),
    'host_rpm_operations':False,'installed_daemon_reinstall':daemon_reinstall,'scope':'development daemon only, non-HDFS/static RPC; installed loopback Log/counter/shutdown, same-RPM reinstall and fixed-file append; no service or old/new differential'}
print(json.dumps(result,indent=2))
