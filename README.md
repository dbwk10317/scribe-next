# scribe-next

기존 Facebook Scribe의 외부 동작을 보존하면서 현대 Linux 환경으로 이식하는 C++ 프로젝트다. 프로젝트 이름은 `scribe-next`이며 실행 바이너리·서비스·CLI·설정 이름은 기존 `scribed` 계약을 유지한다.

현재 목표는 회사 자료 확보와 무관한 **공개 고정 upstream 기능 보존**이다.
확인된 Linux lane의 build MVP 완료 경계, 재사용 검증 진입점과 다음 old/new
우선순위는 [현재 Linux 검증 범위](docs/linux-build-mvp.md)를 따른다. 회사 gate를
다루는 아래 과거 기록은 현재 작업의 필수 조건으로 사용하지 않는다.

고정 upstream 도입 `00826b8` 이후 빌드 경계와 Thrift 0.25 API를 좁게 이식했다. 클라우드 Debian 13·GCC 14·C++17의 기본 비-HDFS C++ lane에서 **scribed clean compile/link와 CLI help 실행에 성공했다**. Thrift upstream C++ 시험 29개도 통과했다. 동일 source commit `96a7fc1`은 Ubuntu 26.04·GCC 15·Boost 1.83에서도 clean build, 프로젝트 38개 및 Thrift 29개 시험을 skip 없이 통과했다. [Ubuntu 검증 기록](docs/ubuntu-validation-20261004.md)을 따른다. 프로젝트 시험과 코드 변경 범위는 [API 이식 기록](docs/api-compat-status.md), 의존성 준비 이력은 [빌드 기록](docs/build-status.md)을 따른다. IDL·queue/store/spool 로직은 유지했으며 전체 platform matrix·old/new 행동 동등성·운영 승인을 완료한 상태는 아니다.

후속 클라우드 단계에서 **일반 spool component 양방향 비교·설정/라우팅을 포함한 55개 시험**이 통과했다. 원본 StdFile의 malloc/delete[] 오류를 재현하고 해제를 free로 맞췄다. 최신 결과와 실제 비교 범위는 [계약 검증 기록](docs/contracts-status.md)을 따른다. 동일 구현은 Ubuntu 26.04.1·GCC 15.2에서도 clean build·CLI help와 55개 시험(skip 0)을 통과했고, 제한된 StdFile reader의 LSan 활성 검증도 통과했다. 클라우드의 LSan ptrace 제약과 전체 daemon 누수 미검증은 별도로 유지한다. 이 후속 결과는 base `75c36bf`의 당시 미commit 작업 트리에서 측정했다. 현재 반영 상태는 Git 이력과 인계 manifest를 따른다.

main `ffc73ee` 이후 클라우드에서 실제 FileStore byte·replay 통합을 추가해 **70개 시험(skip 0)**을 통과했다. 기존 partial replay의 파일 교체 실패→미처리 메시지 손실을 재현했으며 production 수정은 적용하지 않았다. 이 수정 전 범위와 재현 결과는 [FileStore 기록](docs/filestore-contracts-status.md)을 따른다.

사용자 승인 후 openTruncate의 app flag만 제거한 수정본은 새 clean build·CLI help와 **74개 시험(skip 0)**을 통과했다. 부분 처리 뒤 남은 2개가 보존되고 다음 replay에서 전달됨을 확인했다. add_newlines 재적용과 남은 crash/write-failure/unlink 위험을 포함한 최신 상태는 [truncate 수정 기록](docs/truncate-fix-status.md)을 따른다. 동일 v5 구현은 Ubuntu 26.04.1·GCC 15.2에서도 새 clean build·CLI help와 74개 시험(skip 0)을 통과했다. 이 수정은 구현 commit `8baf6f3`과 [PR #1](https://github.com/dbwk10317/scribe-next/pull/1)을 거쳐 main `24692d6`에 반영됐다.

main `24692d6` 이후 production 변경 없이 실제 loopback TCP·RPC·worker·파일 출력 시험과 플랫폼/정리 경계 시험을 추가했다. 클라우드 89개 시험에 이어 동일 v8은 Ubuntu 26.04.1에서도 새 clean build·help와 89개 시험(skip 0), TCP 반복 50회를 통과했다. kernel에서 관측한 listener 50개는 모두 127.0.0.1이며 소유 자식 55개가 모두 회수됐다. 당시 v9에는 상위 작업 확인 요약만 포함했고, 이후 v10에서 해당 raw records를 수신·검증했다. 검증한 v8 해시와 범위는 [loopback 기록](docs/loopback-rpc-status.md)을 따른다. 이 fixture는 127.0.0.1 전용이며 production main/startServer·전체 daemon 또는 회사 동등성 검증과 구분한다. 이 loopback 변경은 구현 commit `cdf21648`과 [PR #2](https://github.com/dbwk10317/scribe-next/pull/2)를 거쳐 main `32004a6`에 반영됐다. v10 인계에는 당시 Ubuntu raw records와 Mac의 31개 통과·skip5/error0 기록도 포함됐다.

main `32004a6` 이후 실제 NetworkStore/ConnPool의 loopback relay bytes·OK/TRY_LATER·재연결·pool 수명·응답 유실 재시도를 검증했다. 실제 두-worker relay→FileStore 연결을 포함한 **101개 시험(skip0)**이 클라우드에서 통과했다. [최신 relay 기록](docs/relay-contracts-status.md)을 따른다. 동일 v11은 Ubuntu 26.04.1에서도 새 clean build·help와 101개 시험(skip0), relay 반복50회를 통과했고 관측한 listener115개가 모두127.0.0.1이며 자식165개가 회수됐다. 당시 v12는 상위 작업 검증 요약만 보존했으나, v13 main 인계에는 해당 Ubuntu raw records와 request frame 43개가 포함됐고 archive manifest의 크기·SHA256을 대조했다. 이 test-only 변경은 구현 commit `5594efaae67e214880a31c755c0f5cb86cfc192a`와 [PR #3](https://github.com/dbwk10317/scribe-next/pull/3)를 거쳐 main `ddca67e6c3485459648e4cbc975d5dae9ddccfc2`에 반영됐다. 새 Mac relay suite는 미실행이다. 위 101개는 이 이전 relay 단계의 시험 수이며 후속 review 수정본의 최종 결과가 아니다.

## 문서

- [제한 Linux build MVP·단일 재사용 검증·공개 원본 대조의 다음 단계](docs/linux-build-mvp.md)
- [전체 autotools build·staged install·Python 생성물 패키징](docs/python-packaging-status.md)
- [ThriftFileStore bytes·copy 수정·재열기와 보존 동작](docs/thriftfile-contracts-status.md)
- [ThriftFileStore copy 수정과 chunk/empty 보존 결정](docs/thriftfile-fix-options.md)
- [독립 리뷰 수정·유한 wire 한도·최종 검증](docs/review-fixes-status.md)
- [설계 및 호환성 계약](docs/design.ko.md)
- [세부 구현 계획과 검증 gate](docs/implementation.ko.md)
- [개발 에이전트 지침](AGENTS.md)
- [문서 출처·현재 결정·코드 도입 전략](docs/source-status.md)
- [빌드 경계 변경·검증·의존성 준비 상태](docs/build-status.md)
- [API 이식·실제 C++ build·제한된 시험](docs/api-compat-status.md)
- [Ubuntu 26.04 + Boost 1.83 재검증](docs/ubuntu-validation-20261004.md)
- [일반 spool·설정 계약·메모리 수정 이력](docs/contracts-status.md)
- [FileStore 통합·수정 전 손실 경로](docs/filestore-contracts-status.md)
- [truncate 수정·부분 replay 검증](docs/truncate-fix-status.md)
- [이전 loopback TCP·worker 검증](docs/loopback-rpc-status.md)
- [최신 relay·connection pool 검증](docs/relay-contracts-status.md)

설계와 구현 문서는 사용자 지정 Library Markdown을 바탕으로 공개 upstream과 목표 Thrift의 정적 검토를 반영한 작업 문서다. 원본 파일명·버전·SHA256, 검토한 고정 소스와 미검증 범위는 출처 문서에 남겼다.

## 목표와 미확정 사항

기준은 [facebookarchive/scribe](https://github.com/facebookarchive/scribe)의 공개 SHA `fcd294faffd1e88af1643a3a8c2359c41713f7c2`다. `scribe.thrift`와 `bucketupdater.thrift`, framed binary와 경로별 strict 설정, fb303, byte 보존, 메모리 큐 ACK, queue/batch/thread·종료·재시도, 10 store, 동적 목적지 갱신과 파일·설정·라우팅·spool 계약을 지킨다. durable ACK, exactly-once, 새 transport, 전면 재작성은 목표에 포함하지 않는다.

Linux는 대상 OS다. C++17과 Thrift 0.25.0은 클라우드 Debian 13 및 Ubuntu 26.04의 제한된 C++ lane에서 빌드가 확인된 검증 후보이며 전체 운영 채택을 뜻하지 않는다. 회사 fork SHA와 패치, 실측 baseline, 실제 config/client/store 사용, Linux 배포판과 GCC/Clang·의존성 버전은 미확인이다. 회사 운영 동등성은 이 자료와 승인된 판정 기준 없이 선언하지 않는다.

## 검증된 Linux C++ 빌드 recipe

아래는 기존 Debian/Ubuntu 비-HDFS·C++17 lane의 bootstrap/configure·generate·clean build·help 명령 형태다. [build manifest](docs/build-manifest.json)의 `command_templates.scribe_configure`와 v13 인계의 `ubuntu-relay-evidence/records/ubuntu-relay-results.json`에 실제 확장 명령·flags·결과가 있다. Thrift compiler/runtime과 fb303는 동일 0.25.0으로 이미 준비된 prefix를 사용한다. Autoconf·Automake·Libtool·Boost system/filesystem·libevent도 필요하며 자동 설치하지 않는다.

`SCRIBE_BUILD`는 bootstrap.sh와 전체 source가 있는 새 격리 사본이다. 아래 절대경로를 실제 승인된 경로로 바꾸고, rootless 도구를 쓰면 검증된 process-local toolchain 환경을 먼저 적용한다. multiarch include/library 디렉터리도 실제 설치 위치를 명시한다.

```sh
export TOOLS_PREFIX=/absolute/tools/usr
export TOOLS_LIBDIR="$TOOLS_PREFIX/lib/x86_64-linux-gnu"
export THRIFT_PREFIX=/absolute/prefix/thrift-0.25.0
export FB303_PREFIX=/absolute/prefix/fb303-0.25.0
export SCRIBE_BUILD=/absolute/fresh-scribe-source-copy
export SCRIBE_PREFIX=/absolute/scribe-install-prefix
export PATH="$THRIFT_PREFIX/bin:$TOOLS_PREFIX/bin:$PATH"

cd "$SCRIBE_BUILD"
CPPFLAGS="-I$TOOLS_PREFIX/include -I$TOOLS_PREFIX/include/x86_64-linux-gnu" \
CXXFLAGS="-O2 -std=c++17" \
LDFLAGS="-L$TOOLS_LIBDIR -L$THRIFT_PREFIX/lib -L$FB303_PREFIX/lib -Wl,-rpath,$TOOLS_LIBDIR -Wl,-rpath,$THRIFT_PREFIX/lib" \
./bootstrap.sh --prefix="$SCRIBE_PREFIX" \
  --with-thriftpath="$THRIFT_PREFIX" \
  --with-fb303path="$FB303_PREFIX" \
  --with-boost="$TOOLS_PREFIX" \
  --with-boost-system=boost_system \
  --with-boost-filesystem=boost_filesystem
make -C src thriftstyle
make -C src clean
make -C src -j2
src/scribed --help
```

Thrift/fb303 include 경로와 compiler는 각 `--with-...path`와 기존 build 규칙으로 연결된다. Boost macro의 library-name 탐지에 맡기지 않고 검증된 두 library 이름을 명시한다. 이 lane은 RPC 정적 library·공유 Thrift runtime이며 HDFS·FACEBOOK lane, root 전체 make/Python packaging과 설치·서비스 기동 검증을 포함하지 않는다. 위 recipe의 과거 성공을 후속 수정본의 새 clean build 완료로 설명하지 않는다.

`CFLAGS`와 `CXXFLAGS`는 각각 미지정일 때만 기존 opt/debug 기본값(`-Wall -O3`/`-Wall -g`)을 적용한다. 명시한 사용자 값과 명시적인 빈 값은 덮어쓰지 않는다. 따라서 C++17, sanitizer, 최적화 flag는 caller가 완전히 정하며, `--disable-opt`도 명시한 flags를 대신 바꾸지 않는다. 두 IDL에는 constants가 없어 0.25.0 generator가 빈 `*_constants.cpp`를 만들지 않는다. static/shared source 목록에서 그 요구만 뺐으며 IDL·wire를 바꾸거나 빈 파일을 수동 생성하지 않았다.

## Thrift 입력 한도와 thread 경계

후속 review 작업 트리의 전역 설정 `thrift_max_frame_size`, `thrift_max_message_size`는 각각 기본 **268435456 bytes(256 MiB)**다. 각 값은 1–2147483647의 양의 십진수 byte count만 허용한다. 0·음수·부호·숫자 뒤 문자는 허용하지 않는다. 초기 설정 오류는 listener 생성을 막는다. listener port처럼 startup-only이며 재초기화로 변경하려면 restart가 필요하고 live server/client는 기존 값을 유지한다.

server와 accepted socket, 별도 input-memory transport/protocol, relay 및 bucket-mapping client에 같은 설정을 적용한다. 한도는 outer 4-byte frame prefix를 제외한 직렬화 RPC payload 기준이다. outgoing relay Log는 frame/message 한도의 작은 값으로 category와 envelope overhead까지 preflight하고 초과 batch를 보내지 않는다. caller batch는 그대로 두고 transient failure를 반환하며 자동 분할·drop은 하지 않는다. 보관된 oversized spool batch나 한 entry의 처리 정책은 여전히 별도 결정이 필요하다. 이 256 MiB는 유한한 호환성 후보 기본값이며 회사 old-runtime 동등성이나 메모리 안전 상한을 보장하지 않는다. 후속 독립 범위 수정본은 새 clean build·help, 전체124개/skip0, 별도 ASan+UBSan API69개/skip0과 독립 검토를 통과했다. 이전 단계에서 제외된 store 5건과 기본 list port·잘못된 bucket child type을 후속 수정했다. Ubuntu 새 clean build·help, 전체137개/skip0과 별도 ASan+UBSan API82개/skip0을 통과했다. resolver 결과를 제어한 동적 목적지 시험과 실제 mapping TTL·회사 동등성 미검증을 구분하며 [최신 기록](docs/review-fixes-status.md)을 따른다.

Thrift 0.9.0 `PosixThreadFactory`의 기본 stack은 명시적인 **1 MiB**다. 0.25.0 `ThreadFactory`는 `std::thread`를 사용하므로 stack은 OS/runtime 기본값을 따르며 **8 MiB로 가정하지 않는다**. worker 수와 detached 설정을 맞춘 것만으로 stack footprint·scheduler·종료 동등성을 선언하지 않는다. 회사의 0.9.0 사용은 사용자 기억에 따른 잠정 정보이며 확정 deployment metadata가 아니다. [API 이식 기록](docs/api-compat-status.md)의 역사적 defaults와 현재 review 설정을 구분한다.

## 첫 개발 작업과 다음 단계

기준 main `c3f3459`는 [PR #5](https://github.com/dbwk10317/scribe-next/pull/5)의 store 수정이 반영된 기준이다. 앞선 test-only ThriftFileStore 관찰은 cloud·Ubuntu에서146개/skip0과 focused ASan+UBSan9개/skip0을 통과했다. 사용자 승인 뒤 copy의 `useSimpleFile`만 보존한 후속 작업 트리는 새 cloud clean build·help, **전체147개/skip0과 focused ASan+UBSan10개/skip0**을 통과했다. simple1/2 copy는 raw 형식을 유지하며 기존 framed clone 파일은 보존하고 새 suffix에 기록한다. chunk 초과와 empty의 기존 Thrift 처리·성공 집계는 사용자 결정대로 유지한다. [실측·미완료 범위](docs/thriftfile-contracts-status.md)와 [승인 범위·보존 결정](docs/thriftfile-fix-options.md)을 따른다. 동일 production·test 소스의 새 Ubuntu clean build/help와 전체147개/skip0·focused ASan+UBSan10개/skip0도 통과했다. 회사/구 runtime 동등성과 운영 배포는 별도 미완료 범위다.

1. 회사 fork·설정·운영 기준과 Linux toolchain matrix를 확인한다. 회사 자료가 없으면 공개 upstream 이식 범위와 회사 호환성 미확정 상태를 구분한다.
2. 고정 SHA의 원본 tree와 `LICENSE`·파일별 고지는 도입했다. upstream에는 `NOTICE`가 없다. 118개 upstream commit은 별도 로컬 `refs/remotes/upstream/baseline`에 보존했으며 프로젝트 이력과의 merge·원격 반영은 아직 하지 않았다. 출처와 검증 절차는 [현재 상태](docs/source-status.md)를 따른다.
3. 재현 가능한 old binary를 확보하고 기존 PHP 시험을 격리 환경에 맞춘다. `make check`는 이 suite를 실행하지 않는다. 두 RPC·10 store·동적 라우팅·양방향 relay/spool fixture와 설정 inventory를 만든다.
4. 작은 PR로 의존성·빌드 경계, Thrift/fb303 API, 기존 파일 transport와 spool 호환, 제한된 C++ 정리 순으로 진행한다. Thrift 0.25.0의 `TFileTransport`를 먼저 재사용·검증한다. 원본의 메모리 결함은 외부 계약과 구분해 재현 시험이 있는 별도 수정으로 다룬다.

**수정되지 않은 원본 도입 commit `00826b8f0ac9288944e7ae56844f926dd654f0bb`의 별도 checkout**에서 소스 도입 검증을 재현할 수 있다. Python 3와 `--no-lazy-fetch`·`--no-replace-objects` 두 옵션을 모두 지원하는 Git, 로컬에 보존된 고정 upstream object가 필요하다. 현재 검증기는 object를 읽기 전에 `git --no-lazy-fetch --no-replace-objects --version`으로 capability를 검사한다. 원본 도입 checkout의 당시 검증기에는 이 후속 probe가 없으므로 아래 첫 명령으로 Git capability를 먼저 확인한다. 미지원 Git은 upstream object 누락과 구분해 실패하며 보호 옵션을 제거하거나 자동 fetch하는 fallback은 없다. 현재 작업 트리의 의도된 build/API 파일 수정은 이 엄격한 검증기에서 실패로 표시되며, 이를 숨기는 예외를 추가하지 않았다.

```sh
git --no-lazy-fetch --no-replace-objects --version
python3 -B test/verify_upstream_import.py
python3 -B -m unittest discover -s test -p 'test_verify_upstream_import.py' -v
```

Git capability 확인 뒤 검증기는 작업 트리 내용·Git 실행 권한·ignore 누락을 검사한다. unittest 명령은 임시 checkout에서 변조·누락·symlink·ignore·Git object 실패와 실제 staging을 시험한다. 작업 트리의 stage/commit이나 네트워크 fetch는 하지 않는다. 현재 빌드 경계 변경과 원본 검증기의 회귀 시험은 아래 명령으로 실행한다. 실제 autotools 또는 명시한 dependency prefix가 없으면 해당 통합/생성 시험을 명시적으로 skip하며 성공으로 세지 않는다. 전체 최신 시험에 필요한 THRIFT_PREFIX·FB303_PREFIX·SCRIBE_BUILD·TOOLS_PREFIX와 실제 결과는 [relay 기록](docs/relay-contracts-status.md)을 따른다.

```sh
python3 -B -m unittest discover -s test -p 'test_*.py' -v
sh -n bootstrap.sh
```

원본 Scribe build 명령은 [upstream README](README)에 있다. 의존성·초기 compile 실패는 [빌드 기록](docs/build-status.md), 후속 clean compile/link 성공은 [API 이식 기록](docs/api-compat-status.md)에 분리했다. 구현 문서의 전체 검증 예시는 성공한 recipe로 간주하지 않는다. 기존 PHP suite는 `make check`에 연결돼 있지 않으며 고정 포트·삭제 경로·프로세스 종료를 먼저 격리해야 한다. Gate A–D는 모두 미통과 상태다.

## 소스와 배포 관례

현재 구현은 승인된 클라우드 작업 사본에서 이어가며, 검증된 변경의 동기화와 승인된 작업 브랜치 commit·push는 Mac checkout에서 수행한다. GitHub 허브는 사용자 승인 범위에 따라 `dbwk10317/scribe-next` 비공개 저장소로 관리한다. 봉구서버의 Ubuntu 26.04.1에서 격리된 소스 도입 검사 105개 경로와 회귀 시험 18개가 통과했다. 상세 환경과 검증한 checkpoint는 [서버 검증 기록](docs/source-status.md#봉구서버의-격리-import-검증)을 따른다. 첫 checkpoint는 commit 전 작업 트리로 검증했으며, 검증된 도입 변경은 `codex/upstream-baseline`의 `00826b8f0ac9288944e7ae56844f926dd654f0bb`로 반영했다. 후속 build/API 변경은 같은 브랜치의 `96a7fc1868639dcf4d479c0d94ab0886fb2776d3`로 승인된 commit/push를 완료했고, [Ubuntu 격리 빌드 검증](docs/ubuntu-validation-20261004.md)도 수행했다. main merge·후속 push·서버 검증·배포는 각각 승인 범위와 검증 gate를 확인한 뒤 진행한다. Scribe 서비스 기동·배포는 수행하지 않았다.

## 라이선스와 출처

공개 upstream은 [Apache License 2.0](https://raw.githubusercontent.com/facebookarchive/scribe/fcd294faffd1e88af1643a3a8c2359c41713f7c2/LICENSE)을 제공한다. 원본 [LICENSE](LICENSE), README와 파일별 copyright·attribution을 보존했다. 고정 upstream tree에 `NOTICE`는 없다. 첫 도입에서는 `.gitignore`에만 표시된 프로젝트 규칙을 덧붙였다. 후속 `bootstrap.sh`, `configure.ac`, `acinclude.m4`, `src/Makefile.am`의 빌드 경계 수정은 파일과 [변경 기록](docs/build-status.md)에 표시했다. 후속 C++ API 경계의 변경과 기존 Boost 포인터 이름 한정은 [API 기록](docs/api-compat-status.md)에 표시했다. IDL·wire/spool 형식과 기존 upstream 시험 소스는 유지한다. 각 단계의 제한된 production 수정과 보존·미검증 계약은 해당 기록에 구분한다. 이후 StdFile 할당·해제 오류의 최소 수정은 [계약 검증 기록](docs/contracts-status.md)에 분리했다. 이 안내로 개인 또는 회사의 새 저작권·배포 권한을 주장하지 않는다. 후속 수정에도 변경 사실을 표시한다. 회사 fork의 공개·배포 권한은 Apache 2.0 여부와 별도로 확인한다.
