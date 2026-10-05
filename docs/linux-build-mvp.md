# 제한 Linux build MVP와 재사용 검증

2026-10-05 · main `621dfd1655b5233ff9cff931fb38c33f67c49613` 이후

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
HDFS·sharedRPC·다른 platform lane은 기존 기능을 제거하지 않은 미검증 범위다.

## 단일 재사용 진입점

새 framework 대신 tools/validate_linux.py가 기존 bootstrap, make clean/build,
unittest discovery/runner, Makefile install과 설치된 scribed --help를 호출한다.
명령/exit/log, source HEAD와 전체 source bytes/mode/hash, compiler/Python 버전,
caller 입력·실제 configure flags, 시험 counts와 설치 파일 manifest를 새 폴더에
기록한다. 기존 폴더·checkout 내부 출력·누락한 prefix를 거부한다. 시험은
실패/error/skip이 모두0이고 기존 baseline150개 이상이 실행돼야 통과한다.
새 wrapper 입력경계3개를 포함한 현재 suite는153개이며 반복/subcase를 더하지 않는다.

현재 wrapper와 입력경계 시험의 동일 bytes는 cloud Debian13/GCC14.2 및
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
