import hashlib,json,os,pathlib,subprocess,sys

def run(command):
    result=subprocess.run(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,universal_newlines=True,timeout=60)
    if result.returncode:
        raise RuntimeError('{}: {}: {}'.format(command,result.returncode,result.stdout+result.stderr))
    return result.stdout.strip()

if not pathlib.Path("/.dockerenv").is_file() or os.getuid()!=0:
    raise SystemExit("Run only as root inside the owned Docker test container")

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
assert len(build_ids)==6
assert all(str(p.resolve()).startswith('/opt/scribe-next-dev/') for p in build_ids)
ldd=run(['ldd','/opt/scribe-next-dev/bin/scribed']);assert 'not found' not in ldd,ldd
for line in ldd.splitlines():
    if 'libboost_' in line or 'libthrift' in line:
        assert '/opt/scribe-next-dev/deps/' in line,line
help_text=run(['/opt/scribe-next-dev/bin/scribed','--help'])
assert help_text
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
    'host_rpm_operations':False,'scope':'development daemon only, non-HDFS/static RPC; installed help, no service or actual daemon differential'}
print(json.dumps(result,indent=2))
