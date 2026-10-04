# scribe-next

기존 Facebook Scribe의 외부 동작을 보존하면서 현대 Linux 환경으로 이식하는 C++ 프로젝트다. 프로젝트 이름은 `scribe-next`이며 실행 바이너리·서비스·CLI·설정 이름은 기존 `scribed` 계약을 유지한다.

고정 upstream 도입 `00826b8` 이후 빌드 경계와 Thrift 0.25 API를 좁게 이식했다. 클라우드 Debian 13·GCC 14·C++17의 기본 비-HDFS C++ lane에서 **scribed clean compile/link와 CLI help 실행에 성공했다**. Thrift upstream C++ 시험 29개도 통과했다. 동일 source commit `96a7fc1`은 Ubuntu 26.04·GCC 15·Boost 1.83에서도 clean build, 프로젝트 38개 및 Thrift 29개 시험을 skip 없이 통과했다. [Ubuntu 검증 기록](docs/ubuntu-validation-20261004.md)을 따른다. 프로젝트 시험과 코드 변경 범위는 [API 이식 기록](docs/api-compat-status.md), 의존성 준비 이력은 [빌드 기록](docs/build-status.md)을 따른다. IDL·queue/store/spool 로직은 유지했으며 전체 platform matrix·old/new 행동 동등성·운영 승인을 완료한 상태는 아니다.

후속 클라우드 단계에서 **일반 spool component 양방향 비교·설정/라우팅을 포함한 55개 시험**이 통과했다. 원본 StdFile의 malloc/delete[] 오류를 재현하고 해제를 free로 맞췄다. 최신 결과와 실제 비교 범위는 [계약 검증 기록](docs/contracts-status.md)을 따른다. 동일 구현은 Ubuntu 26.04.1·GCC 15.2에서도 clean build·CLI help와 55개 시험(skip 0)을 통과했고, 제한된 StdFile reader의 LSan 활성 검증도 통과했다. 클라우드의 LSan ptrace 제약과 전체 daemon 누수 미검증은 별도로 유지한다. 이 후속 결과는 base `75c36bf`의 당시 미commit 작업 트리에서 측정했다. 현재 반영 상태는 Git 이력과 인계 manifest를 따른다.

## 문서

- [설계 및 호환성 계약](docs/design.ko.md)
- [세부 구현 계획과 검증 gate](docs/implementation.ko.md)
- [개발 에이전트 지침](AGENTS.md)
- [문서 출처·현재 결정·코드 도입 전략](docs/source-status.md)
- [빌드 경계 변경·검증·의존성 준비 상태](docs/build-status.md)
- [API 이식·실제 C++ build·제한된 시험](docs/api-compat-status.md)
- [Ubuntu 26.04 + Boost 1.83 재검증](docs/ubuntu-validation-20261004.md)
- [최신 일반 spool·설정 계약·메모리 수정](docs/contracts-status.md)

설계와 구현 문서는 사용자 지정 Library Markdown을 바탕으로 공개 upstream과 목표 Thrift의 정적 검토를 반영한 작업 문서다. 원본 파일명·버전·SHA256, 검토한 고정 소스와 미검증 범위는 출처 문서에 남겼다.

## 목표와 미확정 사항

기준은 [facebookarchive/scribe](https://github.com/facebookarchive/scribe)의 공개 SHA `fcd294faffd1e88af1643a3a8c2359c41713f7c2`다. `scribe.thrift`와 `bucketupdater.thrift`, framed binary와 경로별 strict 설정, fb303, byte 보존, 메모리 큐 ACK, queue/batch/thread·종료·재시도, 10 store, 동적 목적지 갱신과 파일·설정·라우팅·spool 계약을 지킨다. durable ACK, exactly-once, 새 transport, 전면 재작성은 목표에 포함하지 않는다.

Linux는 대상 OS다. C++17과 Thrift 0.25.0은 클라우드 Debian 13 및 Ubuntu 26.04의 제한된 C++ lane에서 빌드가 확인된 검증 후보이며 전체 운영 채택을 뜻하지 않는다. 회사 fork SHA와 패치, 실측 baseline, 실제 config/client/store 사용, Linux 배포판과 GCC/Clang·의존성 버전은 미확인이다. 회사 운영 동등성은 이 자료와 승인된 판정 기준 없이 선언하지 않는다.

## 첫 개발 작업과 다음 단계

1. 회사 fork·설정·운영 기준과 Linux toolchain matrix를 확인한다. 회사 자료가 없으면 공개 upstream 이식 범위와 회사 호환성 미확정 상태를 구분한다.
2. 고정 SHA의 원본 tree와 `LICENSE`·파일별 고지는 도입했다. upstream에는 `NOTICE`가 없다. 118개 upstream commit은 별도 로컬 `refs/remotes/upstream/baseline`에 보존했으며 프로젝트 이력과의 merge·원격 반영은 아직 하지 않았다. 출처와 검증 절차는 [현재 상태](docs/source-status.md)를 따른다.
3. 재현 가능한 old binary를 확보하고 기존 PHP 시험을 격리 환경에 맞춘다. `make check`는 이 suite를 실행하지 않는다. 두 RPC·10 store·동적 라우팅·양방향 relay/spool fixture와 설정 inventory를 만든다.
4. 작은 PR로 의존성·빌드 경계, Thrift/fb303 API, 기존 파일 transport와 spool 호환, 제한된 C++ 정리 순으로 진행한다. Thrift 0.25.0의 `TFileTransport`를 먼저 재사용·검증한다. 원본의 메모리 결함은 외부 계약과 구분해 재현 시험이 있는 별도 수정으로 다룬다.

**수정되지 않은 원본 도입 commit `00826b8f0ac9288944e7ae56844f926dd654f0bb`의 별도 checkout**에서 소스 도입 검증을 재현할 수 있다. Python 3와 `--no-lazy-fetch`를 지원하는 Git, 로컬에 보존된 고정 upstream object가 필요하다. 현재 작업 트리의 의도된 build/API 파일 수정은 이 엄격한 검증기에서 실패로 표시되며, 이를 숨기는 예외를 추가하지 않았다.

```sh
python3 -B test/verify_upstream_import.py
python3 -B -m unittest discover -s test -p 'test_verify_upstream_import.py' -v
```

첫 명령은 작업 트리 내용·Git 실행 권한·ignore 누락을 검사한다. 두 번째는 임시 checkout에서 변조·누락·symlink·ignore·Git object 실패와 실제 staging을 시험한다. 작업 트리의 stage/commit이나 네트워크 fetch는 하지 않는다. 현재 빌드 경계 변경과 원본 검증기의 회귀 시험은 아래 명령으로 실행한다. 실제 autotools 또는 명시한 dependency prefix가 없으면 해당 통합/생성 시험을 명시적으로 skip하며 성공으로 세지 않는다. 전체 최신 시험에 필요한 THRIFT_PREFIX·FB303_PREFIX·SCRIBE_BUILD·TOOLS_PREFIX와 실제 결과는 [계약 검증 기록](docs/contracts-status.md)을 따른다.

```sh
python3 -B -m unittest discover -s test -p 'test_*.py' -v
sh -n bootstrap.sh
```

원본 Scribe build 명령은 [upstream README](README)에 있다. 의존성·초기 compile 실패는 [빌드 기록](docs/build-status.md), 후속 clean compile/link 성공은 [API 이식 기록](docs/api-compat-status.md)에 분리했다. 구현 문서의 전체 검증 예시는 성공한 recipe로 간주하지 않는다. 기존 PHP suite는 `make check`에 연결돼 있지 않으며 고정 포트·삭제 경로·프로세스 종료를 먼저 격리해야 한다. Gate A–D는 모두 미통과 상태다.

## 소스와 배포 관례

현재 구현은 승인된 클라우드 작업 사본에서 이어가며, 검증된 변경의 동기화와 승인된 작업 브랜치 commit·push는 Mac checkout에서 수행한다. GitHub 허브는 사용자 승인 범위에 따라 `dbwk10317/scribe-next` 비공개 저장소로 관리한다. 봉구서버의 Ubuntu 26.04.1에서 격리된 소스 도입 검사 105개 경로와 회귀 시험 18개가 통과했다. 상세 환경과 검증한 checkpoint는 [서버 검증 기록](docs/source-status.md#봉구서버의-격리-import-검증)을 따른다. 첫 checkpoint는 commit 전 작업 트리로 검증했으며, 검증된 도입 변경은 `codex/upstream-baseline`의 `00826b8f0ac9288944e7ae56844f926dd654f0bb`로 반영했다. 후속 build/API 변경은 같은 브랜치의 `96a7fc1868639dcf4d479c0d94ab0886fb2776d3`로 승인된 commit/push를 완료했고, [Ubuntu 격리 빌드 검증](docs/ubuntu-validation-20261004.md)도 수행했다. main merge·후속 push·서버 검증·배포는 각각 승인 범위와 검증 gate를 확인한 뒤 진행한다. Scribe 서비스 기동·배포는 수행하지 않았다.

## 라이선스와 출처

공개 upstream은 [Apache License 2.0](https://raw.githubusercontent.com/facebookarchive/scribe/fcd294faffd1e88af1643a3a8c2359c41713f7c2/LICENSE)을 제공한다. 원본 [LICENSE](LICENSE), README와 파일별 copyright·attribution을 보존했다. 고정 upstream tree에 `NOTICE`는 없다. 첫 도입에서는 `.gitignore`에만 표시된 프로젝트 규칙을 덧붙였다. 후속 `bootstrap.sh`, `configure.ac`, `acinclude.m4`, `src/Makefile.am`의 빌드 경계 수정은 파일과 [변경 기록](docs/build-status.md)에 표시했다. 후속 C++ API 경계의 변경과 기존 Boost 포인터 이름 한정은 [API 기록](docs/api-compat-status.md)에 표시했다. IDL·queue/store/spool 형식과 기존 upstream 시험 소스는 그대로다. 이후 StdFile 할당·해제 오류의 최소 수정은 [계약 검증 기록](docs/contracts-status.md)에 분리했다. 이 안내로 개인 또는 회사의 새 저작권·배포 권한을 주장하지 않는다. 후속 수정에도 변경 사실을 표시한다. 회사 fork의 공개·배포 권한은 Apache 2.0 여부와 별도로 확인한다.
