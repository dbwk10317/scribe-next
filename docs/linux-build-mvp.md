# 제한 Linux build MVP와 재사용 검증

> 현재 상태(2026-10-06): 원본 계약 복원 [PR #25](https://github.com/dbwk10317/scribe-next/pull/25)는 병합됐으며 확인한 main은 `87b3ab3342715f8f831ad4bbef8d1b39420ee74a`이다.
> 아래의 미반영·실패·승인 예외·시험 수는 각 단계의 당시 기록이다. 현재 정책과 지원 범위는 [README](../README.md)와 [호환성 정책](legacy-compatibility-policy.md)을 따른다.

2026-10-05 · 단계별 검증 이력, 최초 base `621dfd1`

현재 사용법과 완료 경계는 [README](../README.md)와
[첫 현대화 closeout](first-modern-version.md)을 따른다. 아래 초기 scope/시험 수와
당시 미검증 문장은 이력이며, 후속 실제 HDFS/mapping/shared 결과로 현재 상태를 갱신했다.

## 현재 목표와 완료 경계

현재 목표는 공개 Facebook Scribe `fcd294faffd1e88af1643a3a8c2359c41713f7c2`의
기능·설정·wire·파일/store 동작을 보존하는 현대 Linux 이식이다. 회사 fork,
회사 config와 회사 성능 기준은 현재 범위 밖이며 자료 요청이나 완료의 필수
조건으로 사용하지 않는다. 이전 문서의 회사 gate는 당시 계획의 이력이다.

**build MVP**는 아래 확인된 lane의 새 source copy에서 기존 autotools 전체
compile/link, 현재 회귀 시험(skip0), DESTDIR 설치와 설치된 scribed help가
성공하는 것이다. 공개 원본의 전체 기능 동등성 완료나 배포 승인을 뜻하지 않는다.

- Linux x86_64: Debian13/GCC14.2와 Ubuntu26.04.1/GCC15.2
- C++17, Thrift compiler/runtime와 fb3030.25.0, Boost1.83
- 기존 env_default·비-HDFS·정적 Scribe/BucketMapping RPC library lane
- 기존 caller 제공 dependency prefix, autotools, libevent와 setuptools
- Python3.12.14/setuptools84와 Python3.14.4/setuptools78.1.1의 actual
  site-packages/dist-packages 설치 경로

이 baseline main의 전체150개와 focused Python3개, root build/staged install/help는
cloud·Ubuntu에서 통과했다. 앞선147개, v23의147PASS+setupERROR1,
그뒤 수정본150PASS를 같은 결과로 합치지 않는다. 원본10 store의 code는
보존하지만 모든 store의 old/new runtime 동등성을 이150개로 주장하지 않는다.
당시 HDFS·sharedRPC·다른 platform lane은 미검증이었다. 후속 shared cloud·서버 검증은
아래 별도 기록을 따르며 HDFS/다른 platform과 shared actual old/new runtime 범위는 남는다.

## 단일 재사용 진입점

새 framework 대신 tools/validate_linux.py가 기존 bootstrap, make clean/build,
unittest discovery/runner, Makefile install과 설치된 scribed --help를 호출한다.
명령/exit/log, source HEAD와 전체 source bytes/mode/hash, compiler/Python 버전,
caller 입력·실제 configure flags, 시험 counts와 설치 파일 manifest를 새 폴더에
기록한다. 기존 폴더·checkout 내부 출력·누락한 prefix를 거부한다. 시험은
실패/error/skip이 모두0이고 기존 baseline150개 이상이 실행돼야 통과한다.
당시 wrapper 입력경계3개를 포함한 suite는153개였으며 해당 단계에서 반복/subcase를 더하지 않았다.

해당 단계 wrapper와 입력경계 시험의 동일 bytes는 cloud Debian13/GCC14.2 및
Ubuntu26.04.1/GCC15.2에서 각각 새 출력 디렉터리로 실행했다. configure,
compiler/Python 버전 확인, clean/build, 전체153개 시험(failure/error/skip0),
staged install과 설치된 scribed help의8단계가 모두 exit0이었다. Ubuntu는
wrapper를1회 실행했으며 staged11개·generated37개 파일과 dependency39개
기록을 검증했고 관찰한 loopback listener·자식 프로세스가 남지 않았다.
cloud의 앞선 실패 기록과 최종 cloud-validation-4 통과를 구분한다.
근거는 인계v28 `scribe-next-linux-build-mvp-validated-20261005.tar.gz`
(SHA256 `41a7236582f4629ce9c03e3fd4723f7460c2e83107d1414bab934c56f03fa7ee`)의
cloud-validation-4 및 ubuntu-mvp-evidence 원시 기록이다. 이 결과 설명은
실행 뒤 추가했으며 검증된 wrapper·시험 코드는 변경하지 않았다.

이미 준비한 승인된 toolchain 환경을 적용한 뒤 기존 절대경로만 지정한다.
THRIFT_PYTHON_SOURCE는 matching Thrift0.25.0 source의 lib/py/src 디렉터리다.

```sh
export THRIFT_PREFIX=/absolute/existing/thrift-0.25.0
export FB303_PREFIX=/absolute/existing/fb303-0.25.0
export TOOLS_PREFIX=/absolute/existing/tools/usr
export THRIFT_PYTHON_SOURCE=/absolute/existing/thrift-0.25.0/lib/py/src
python3 -B tools/validate_linux.py --output /absolute/new-validation-directory
```

출력은 build/, stage/, logs/, home/, test-results.json, validation.json이다.
source checkout/Git baseline object가 있어야 기존 import 회귀도 실행할 수 있다.
CFLAGS/CXXFLAGS/CPPFLAGS/LDFLAGS의 명시값과 빈 값은 덮어쓰지 않으며 미지정
CXXFLAGS만 C++17 기본 recipe를 적용한다. 사용자 변경 flags의 결과는 그 flags로
기록하고 확인되지 않은 다른 표준/platform 지원으로 확대하지 않는다.
이 작은 staged validation lane은 PYTHON_SETUPUTIL_ARGS와 inherited make overrides를
거부한다. --record 등의 별도 출력이 DESTDIR 밖에 쓰이는 것을 막으며 원래
Makefile의 일반 install 기능 자체를 바꾸지는 않는다. process-local HOME을
output/home로 분리하고 추가 Python config를 거부하며 안전한 빈 record 인자를
명시한다. 기존 interpreter 설치의 setuptools를 사용하고 사용자별 build/install
config는 소비하지 않는다. 원래 HOME/config 파일을 수정하지 않는다.
의존성 자동 설치·download·서비스/daemon 기동·시스템 설치·sudo·보안/네트워크
변경·원격 push는 수행하지 않는다. C++ prefix `/opt/scribe`와 Python prefix
`/usr`의 실제 install 대상은 언제나 새 output의 DESTDIR(stage/) 아래다.

## 공개 원본 기능 보존의 다음 우선순위

1. 공개 고정 source와 공식 구 Thrift runtime의 재현 가능한 독립 baseline을
   확정해 두 RPC/운영 API·설정·10 store와 spool/relay의 old/new 대조를 진행한다.
   임의 회사 버전을 가정하지 않고 baseline에 적용한 build-only patch도 공개한다.
   새 dependency/runtime 설치는 별도 실행 권한을 확인한다
2. 실제 CLI/main/startServer 전체 경로를 허용된 격리 환경에서 검증한다.
   현 cloud/server의 namespace EPERM을 flag/권한/security 변경으로 우회하지 않는다
3. 동일 upstream workload에서 queue/retry/shutdown과 성능 차이를 측정한다.
   단순히 component 시험 수를 늘리는 것을 기능 보존 완료로 삼지 않는다

기존 승인된 free/truncate/store/copy 수정과 유한 RPC256MiB 후보의 차이는
각 근거 기록에 유지한다. oversized/empty Thrift 처리·반환/집계는 사용자의
보존 결정대로 유지하며 새 retry/failure-file/drop 정책을 추가하지 않는다.
회사 자료 없이도 위 공개 원본 대조를 계속할 수 있다. 현재 build MVP와 전체
원본 동등성·운영 배포를 구분하며 서비스를 올리는 권한을 추정하지 않는다.


## 공개 원본 store와 optional 지원 현황

2026-10-05, base main4017060 이후 전체172개 시험/skip0과 아래 actual old/new
case가 서버에서 확인됐다. 공개 fcd294f+명시 build-only patch/Thrift0.9.0과
현대 C++17/Thrift0.25.0을 별도 userland에서 대조했다. 회사 자료는 gate가 아니다.
아래 PASS는 해당 작은 config/입력/관찰 범위이며 모든 기능 동등성 선언이 아니다.
10종 모두 제한된 actual 정상 case가 확인됐지만 전체 option/fault matrix·HDFS·
성능·완료 gate를 통과했다는 뜻은 아니다.

| Store/backend | 보존·기존 시험 | 실제 production old/new daemon 대조 |
| --- | --- | --- |
| file | std file bytes/설정/worker 계약 | PASS: batch, strict 크기 회전, reinitialize, owned process crash/restart append |
| buffer | ordinary spool reader/full·partial replay 계약 | PASS: downstream 비가동→framed spool17→full replay→streaming |
| network | fixed/list/dynamic relay·copy component 계약 | PASS: 고정 loopback 목적지, 비가동/재연결과 full batch ACK/sent |
| null | ignored/drop 계약 | PASS: 수신과 ignored3 |
| multi | child order/fan-out 및 failure component 계약 | PASS: 두 file+null, 파일과 ignored3 |
| category | per-category clone/파일 분리 계약 | PASS: 두 category 파일·링크·수신 카운터 |
| bucket | route·copy 및 승인 결함 회귀 | PASS: implicit exact key_range(20,2)/remove_key, 정상 두 bucket와 failure bucket |
| thriftfile | raw/framed·chunk/empty/oversized·copy/reopen component 계약 | PASS: 직접 raw10/framed25, chunk padding, 정상 종료 뒤 bytes/link |
| multifile | 보존된 CategoryStore→FileStore alias | PASS: 두 실제 category raw10/1 bytes·별도 path/link |
| thriftmultifile | 보존된 CategoryStore→ThriftFileStore alias | PASS: framed 두 category25/5 bytes·별도 path/link |
| optional HDFS | configure --enable-hdfs 및 HdfsFile.cpp/libhdfs/libjvm 경로 보존 | cloud·서버 enable build/local JNI PASS; 서버 single-DN 정상 distributed storage/restart append PASS, fault/역사 binary는 미검증 |
| shared RPC | 원본 --disable-static 선택 보존 | cloud·서버 clean compile/link·183 tests·DESTDIR·stage-loader help PASS; actual old/new shared daemon은 미검증 |
| 다른 platform | 기존 선택 기능·source 보존 | 미검증: 현재 확인 lane은 Linux x86_64 |

응답 유실·TRY_LATER·fault/retry component 근거와 실제 daemon case를 구분한다.
이 표의 당시 결과는 actual 응답 유실/부분 replay, mapping/TTL 변경, HDFS, 전체
option matrix와 넓은 workload 비교를 포함하지 않았다. 후속 PR21 mapping과 modern
HDFS 정상 결과는 아래와 현재 README에 따로 반영됐다. 기존 승인된 free/truncate·bucket
OOB/copy·network 설정·ThriftFile raw-copy 수정은 old 버그를 재현해 같음을
요구하지 않는 명시 예외다. oversized/empty Thrift 정책과256MiB 초과 retained
spool 재시도 경계도 그대로 남는다. ACK를 durable/exactly-once 보장으로 확대하지 않는다.


## 초기 후보의 검증 경계와 당시 다음 우선순위

초기 후보는 공개 fcd294f 기반의 **Linux x86_64·비-HDFS/static 범위**였다. release/tag나
서비스 배포를 이 문서로 수행하지 않는다. 확인된 build/staged install/help,
기존 framed binary/fb303,10종 limited 정상 daemon case와 ordinary spool/relay,
크기 회전·reinitialize·process 재개는 근거가 있다. 전체 option/fault/platform
matrix가 완료된 호환 릴리즈라고 표현하지 않는다.

동일 공개 synthetic workload의 [fixed 성능 baseline](daemon-differential.md#공개-fixed-profile-성능-baseline)은
서버에서 old/modern 각3회 실행됐고 correctness와 전체177개 시험/skip0이 통과했다.
ACK payload 중앙값은 old1483.781/modern1850.387MiB/s지만 파일 크기 완료 관찰은
old1479.891/modern1164.109MiB/s, VmHWM은13832/21144KiB다. 완료 관찰 처리량
감소와 RSS 증가는 미판정 raw 관찰로 보존한다. 사용자는 프로젝트가 어느 정도
완성된 뒤 상세 성능 비교를 진행하기로 결정했으며 성능 합격·퇴보를 판정하지 않는다.
측정은 짧은 warm workload와5ms completion poll, 별도 toolchain/ABI/userland의
제한을 갖는다. 현재 추가 run·원인 분석·tuning 없이 원본 기능 완성 작업을
이어간다. 성능 gate 통과나 운영 배포 승인으로 확대하지 않는다.

그다음 우선순위는 actual wire/error와 주요 config/backpressure 계약, dynamic
mapping/TTL·응답 유실/부분 replay fault를 적절한 묶음으로 대조하는 것이다.
그뒤 optional HDFS/shared와 넓은 workload/platform은 필요한 기존 runtime 및
실행 권한을 확인해 별도 lane으로 다룬다. 미설치 환경을 보안 우회로 만들지 않는다.

명시된 허용 차이는 [truncate/free](truncate-fix-status.md), [bucket/network 및
retry-zero 회귀](review-fixes-status.md), [ThriftFile raw-copy](thriftfile-contracts-status.md)
등 사용자가 승인한 수정뿐이다. 원본의 오류 응답·ACK·empty/oversized drop/count,
retry·파일 의미를 새 정책으로 바꾸지 않는다. 유한 RPC256MiB 후보와 그보다 큰
retained spool 재전송 경계는 별도 제한으로 남는다. 이 경계와 optional 미검증을
사용자에게 숨기지 않으며 회사 baseline을 필수 gate로 되살리지 않는다.


현재 기능 보존의 후속 확인 묶음은 [fb303 option/counter와 unknown-method](daemon-differential.md#fb303-optioncounter와-unknown-method-회복-묶음)이다.
option state/void/string-map/i64와 application exception 뒤 연결 재사용, 원본의
rate-disable 정상 config를 확인했다. 서버 전체180개 시험/skip0과 actual case1회에서
old/new 요청15·응답14·수신2·raw9바이트/상대 link·정상 종료/회수가 일치했다.
malformed frame·시간 의존 rate denial·전체 config 거절이나 profiler API까지
완료했다고 확대하지 않는다. 상세 성능 비교 보류 결정은 유지한다.


## 원본 shared RPC 선택과 실제 사용 경계

원본 switch는 --disable-static이며 --disable-shared라는 이전 source comment와
혼동하지 않는다. tools/validate_linux.py의 --shared-rpc 한 option이 이 switch만
전달한다. default/static mode와 production build 규칙·C++·두 IDL은 바꾸지 않는다.
configured LTYPE(.a/.so)을 정확히 확인하고 test fixture도 해당 library와
shared per-target object/.Po 이름을 따른다. missing/ambiguous/다른 suffix나
selected library가 scribed보다 새로워 재링크가 필요한 경우를 거부한다.

수정 전 원본 shared configure/clean/build는 성공했다. static object 이름을
고정한 API test는 setupERROR/0 tests였고 default loader의 help는 libscribe.so
미탐색으로127이었다. consumer-local build/src를 loader 경로에 주면 같은
binary help0이었다. 이 결과를 production build 실패로 세지 않는다.

cloud 최종 --shared-rpc run은9단계와183개 시험(failure/error/skip0), staged
11개 파일·scribed help0을 통과했다. 두 shared RPC library는 build와 stage
bytes가 같고 scribed DT_NEEDED 및 GNU loader trace로 실제 stage/opt/scribe/lib의
두 .so를 읽는 것을 확인했다. staged help는 stage cwd와 stage+prepared dependency
LD_LIBRARY_PATH만 사용해 build/src를 빌리지 않는다. 이 경로는 process-local이며
ldconfig/시스템 설치·서비스·권한 변경은 하지 않는다. 일반 배포 때도 두 RPC .so와
matching Thrift/Boost 등 loader closure를 함께 제공해야 하며 SDK 절대경로가
자동으로 어느 머신에서나 유효해지는 것은 아니다. 후속 서버는 기존 승인된
Thrift/fb303/Boost/tool prefix로 새 --shared-rpc output의9단계·183개 시험
(failure/error/skip0)·DESTDIR11개 파일·staged help0을 재현했다. 두 RPC .so의
build/stage bytes·SHA256과 actual loader init trace를 독립 확인했고 설치 help는
build/src 경로를 사용하지 않았다. production/fixture C++·header·IDL38개는 기존
matching source와 같고 production build 규칙·기본 static 선택은 바꾸지 않았다.
서버 실행 container는 시작·종료31개로 모든 ID가 동일했고 이전 운영30개도
그대로 포함됐다. 새 install·ldconfig·시스템 library 교체·권한/서비스 변경이나
daemon 기동·benchmark는 하지 않았다. shared daemon의 actual old/new 전체 대조는
아직 별도 결과가 필요하다.

초기 비-HDFS/static 후보와 후속 shared·modern HDFS 검증을 구분한다.
version/tag는 아직 지정하지 않았으며 현재 지원 표는 README를 따른다.
당시 남은 다음 확인 범위는 후속 HDFS 및 PR21 mapping/config 기록으로 제한된
정상 경로가 닫혔다. 전체 기능 동등성 선언은 여전히 하지 않는다. 아래 목록은
당시 계획이며 현재 미완료 필수 테스트 목록이 아니다.

1. 선택한 HDFS header/native API compile/link와 실제 저장·읽기/파일 동작
2. 실제 dynamic mapping/TTL·대표 config 거절 및 backpressure/error·부분 replay
   차이를 public baseline/승인 예외에 맞춰 정리
3. 지원할 shared/platform·설치 loader 경계와 재현/롤백 문서 확인

HDFS source와 configure --enable-hdfs/--with-hadooppath, HdfsFile.cpp/libhdfs/libjvm
경로는 보존됐다. 당시 cloud에는 Java21 JRE/libjvm이 있으나 Hadoop hdfs.h/libhdfs/client jars가
없어 아직 build·runtime 증거가 없다. javac/JNI development headers도 없으며
native client를 source-build할지 prebuilt를 사용할지 선택한 뒤 필요성을 판단한다.
원본 hdfsDelete의2-argument 호출 등 C API signature를 선택한 공식 header와 먼저
대조해야 한다. JRE 존재만으로 Hadoop/JNI 호환이나 cluster 접근을 가정하지 않는다.
다음 HDFS 단계는 공식 runtime/version·native/jar/classpath/loader 및 제한된 filesystem
대상을 정한 뒤 필요한 취득·실행 권한을 별도로 확인한다. 지금 추가 설치나 service
기동을 하지 않고 회사 자료를 gate로 삼거나 optional 기능을 삭제하지 않는다.
상세 성능 비교·추가 benchmark/tuning 보류도 유지한다.

## Optional HDFS client port

The subsequent [HDFS compatibility record](hdfs-compatibility.md) preserves the
historical recursive delete API across two/three-argument libhdfs. At that stage,
official Hadoop3.5/JDK21 local JNI was a bounded client/build check. The later
single-DN distributed result is recorded below; historical binary equivalence remains open.

The same port subsequently passed server default clean eight-step validation with
185 tests/skip0, separate HDFS-enabled full compile/link, staged install/help0 and
the bounded local JNI fixture. Official JRE/Hadoop were verified and privately
extracted; distributed HDFS was unverified at that local-only stage. The original
ignored delete return and closed-handle truncate append were preserved. That stage
started no cluster or service; the subsequent isolated distributed result follows.

The subsequent single-DataNode case passed in an approved disposable
network-none/nonroot container: exact binary9→10 bytes, regular marker, fresh
counters2/1, live DataNode/safemode OFF, healthy distributed blocks and full owned
cleanup. Server194 tests/skip0 passed using the unchanged matching build.
[Actual scope and command](hdfs-compatibility.md#single-datanode-distributed-check)
record the seeded-directory precondition, first hostname failure and successful
localhost retry. This is source-defined modern validation, not historical binary
equivalence, a distributed fault/permissions matrix or a performance claim.

The [first modern-version boundary](first-modern-version.md) records the closed
named dynamic-mapping/config scope separately from optional deeper matrices.
The modern single-DN HDFS case is now recorded PASS; historical HDFS binary
comparison, delete/fault/permission/replication coverage remain declared limits.

## 검증용 Git 이력 준비

검증기는 현재 Git checkout과 고정 원본의 commit object를 함께 사용한다.
ZIP 다운로드나 현재 파일만 복사한 폴더로는 전체 검증을 실행할 수 없다.
원본 object가 없는 일반 checkout은 최초 준비 시 공식 upstream에서 명시적으로 가져온다.
검증기 자체는 보호 옵션을 제거하거나 원본 이력을 자동으로 fetch하지 않는다.

```sh
git --no-replace-objects --no-lazy-fetch --version && \
git fetch https://github.com/facebookarchive/scribe.git fcd294faffd1e88af1643a3a8c2359c41713f7c2:refs/remotes/upstream/baseline && \
git --no-replace-objects --no-lazy-fetch cat-file -e 'fcd294faffd1e88af1643a3a8c2359c41713f7c2^{commit}'
```

이미 원본 object가 있는 작업 사본은 fetch할 필요가 없다.
첫 명령이 옵션 미지원으로 실패하면 두 보호 옵션을 지원하는 Git을 준비하고 진행한다.
GitHub 프로젝트 checkout만으로 원본 object가 항상 포함된다고 가정하지 않는다.

## 수동 빌드 예제

자동 검증 대신 기존 autotools를 직접 실행할 때의 예제다. 아래 의존성 경로는
README의 빠른 시작과 같이 이미 준비한 실제 설치 위치를 사용한다.
설치는 별도 `DESTDIR`에서 확인하며 공유 RPC·HDFS는 해당 옵션과 라이브러리를 따로 준비한다.

```sh
export SCRIBE_BUILD=/absolute/fresh/source-copy
export TOOLS_LIBDIR="$TOOLS_PREFIX/lib/x86_64-linux-gnu"
cd "$SCRIBE_BUILD"
CPPFLAGS="-I$TOOLS_PREFIX/include -I$TOOLS_PREFIX/include/x86_64-linux-gnu" \
CXXFLAGS="-O2 -std=c++17 -D_GLIBCXX_USE_DEPRECATED=0" \
LDFLAGS="-L$TOOLS_LIBDIR -L$THRIFT_PREFIX/lib -L$FB303_PREFIX/lib -Wl,-rpath,$TOOLS_LIBDIR -Wl,-rpath,$THRIFT_PREFIX/lib -Wl,-rpath,$FB303_PREFIX/lib" \
sh ./bootstrap.sh --prefix=/opt/scribe \
  --with-thriftpath="$THRIFT_PREFIX" --with-fb303path="$FB303_PREFIX" \
  --with-boost="$TOOLS_PREFIX" --with-boost-system=boost_system \
  --with-boost-filesystem=boost_filesystem
make clean
make -C src thriftstyle
make -j2
src/scribed --help
```

이 예제에서 flags는 호출자가 정하는 값이다. bootstrap은 이미 지정한
`CFLAGS`/`CXXFLAGS`의 값과 빈 값을 덮어쓰지 않는다.
shared RPC는 기존 `--disable-static` 선택을 사용하며 설치된 두 RPC `.so`와
그 의존성을 실행 프로세스에서 찾을 수 있게 해야 한다. 기본 static RPC 빌드도
모든 의존성을 포함하는 완전 정적 실행 파일은 아니다.
HDFS의 `--enable-hdfs --with-hadooppath=...`, libhdfs/libjvm와 classpath는
[HDFS 안내](hdfs-compatibility.md)를 따른다.
