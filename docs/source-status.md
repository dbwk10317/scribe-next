# 문서 출처와 현재 결정

## 기준 문서

2026-10-04 사용자 지정 최신 Library 파일을 Mac의 실제 파일로 가져왔다. Library가 반환한 버전은 두 파일 모두 `0`이다. 아래 SHA256은 상대 링크 추가 전 원본 bytes 기준이다. 이전 Mac 문서를 대체 원본으로 사용하지 않았다.

| 역할 | 원본 파일명 | 저장소 경로 |
| --- | --- | --- |
| 설계 | scribe-next-설계문서.md | [design.ko.md](design.ko.md) |
| 구현 계획 | scribe-next-세부구현문서.md | [implementation.ko.md](implementation.ko.md) |

- 설계 원본 SHA256: `ecabaf7b48b535ae6f7e348631dbfce35a5020665e3a2fc868dd36cba76f296a`
- 구현 원본 SHA256: `66e13598a2d5a38d99f4437de53f1e04d7f23e89231247ba44db5bff33cd4488`

저장소 사본은 원본을 바탕으로 상대 링크와 아래 고정 source의 정적 검토를 반영한 작업 문서다. 위 해시는 Library 원본 식별용이며 현재 수정본의 해시가 아니다. 현재 문서에는 두 번째 RPC·동적 라우팅, 목표 Thrift API, 원본 메모리 결함과 시험 실행 경계를 반영했다. source 열람은 build·runtime 검증으로 승격되지 않는다.

## 현재 결정과 열려 있는 항목

| 구분 | 상태 |
| --- | --- |
| 확정 방향 | Linux 대상, 기존 Scribe 동작 보존, 기존 구조·autotools 우선, 작은 PR 단위의 단계적 이식 |
| 공개 기준 | [facebookarchive/scribe](https://github.com/facebookarchive/scribe), SHA `fcd294faffd1e88af1643a3a8c2359c41713f7c2` |
| 제안 후보 | C++17, Thrift 0.25.0; 요구 표준과 주요 API는 정적 확인, 실제 build·runtime 채택은 미확정 |
| 미확인 | 회사 fork·patch·production config·client/store/HDFS 사용, 실측 baseline, 배포판·compiler·dependency matrix |
| 저장소 상태 | loopback 구현은 PR #2/main `32004a6`에 반영. v10 인계의 당시 Ubuntu raw records를 확인했다. 후속 test-only NetworkStore/ConnPool·명시적 retry와 실제 두-worker relay→FileStore를 포함한 cloud·Ubuntu 각101개 시험 통과(skip0), Ubuntu v11 새 clean build·help·relay 반복50회·loopback/자식 회수는 상위 작업 검증 요약으로 기록, 새 raw files 미수신. 미commit·미push. [최신 relay 기록](relay-contracts-status.md), 이전 [loopback](loopback-rpc-status.md)·[truncate 수정](truncate-fix-status.md) 참조 |
| 검증 gate | A 기본 cloud·Ubuntu C++ lane compile/link는 성공, 전체 platform/feature matrix 미완료. B/C는 제한된 API·config/routing·ordinary StdFile component와 실제 FileStore byte/replay와 test-only loopback TCP 및 fixed-host relay/connection pool의 제한된 계약만 완료. production main/startServer와 전체 daemon 동등성은 미검증. 잘못된 truncate mode만 승인 수정; crash/write-failure/unlink 위험은 남음. 두 RPC old/new·10 store·동적 갱신·thriftfile/relay/fault/종료와 D 회사 성능·운영은 미완료 |
| 작업 환경·원격·배포 | 클라우드에서 구현, 검증된 변경은 Mac에서 동기화해 승인된 `codex/upstream-baseline` 브랜치로 반영. GitHub `dbwk10317/scribe-next` 비공개 유지. 봉구서버 import 검증 통과. main 반영 상태는 Git 이력 참조. Scribe 서비스 기동·배포 미실행 |

## upstream 코드 도입 전략

첫 코드 도입에서 고정 공개 SHA와 tree를 확인하고 원본 source 경로·라이선스·파일 mode를 보존했다. 원본 `.gitignore`의 bytes 뒤에 프로젝트 추가 규칙만 붙였다. 118개 upstream commit은 `refs/remotes/upstream/baseline`에 별도로 보존했고 현재 프로젝트 이력과 merge하지 않았다. 최종 이력 통합·원격 반영 방식은 별도 확인 후 선택한다. 재현 가능한 old binary와 격리된 기존 PHP driver·fixture를 먼저 확보하며 도입만 하는 변경과 이식 변경을 분리한다. 최신 branch를 임의 build 입력으로 삼거나 generated code를 수동 수정하지 않는다.

첫 도입의 기준 commit/tree·원본 내용·출처 고지 확인은 완료했다. 회사 대비 차이·승인된 Linux matrix·계약 fixture와 실행 baseline은 다음 단계에 남아 있다. 실제 검증 결과는 구현 시 source path·symbol·fixture·old/new 결과에 연결한다. 회사 자료가 없으면 공개 upstream 작업과 회사 호환성 미확정을 분명히 구분한다.

## 첫 소스 도입 검증 2026-10-04

아래 검증은 프로젝트 base `739eda4ed5b02fca5663c1c30d310e2370472873` 위의 commit 전 도입 작업 트리를 대상으로 했다. Mac에서 시작한 소스 도입을 승인된 클라우드 Linux 사본에서 이어갔다. 이전 파일의 SHA256, 113개 파일의 bytes·mode와 Git bundle 무결성을 확인한 뒤 복원했으며 인증 정보나 Git 개인 설정은 옮기지 않았다.

| 항목 | 실제 결과 |
| --- | --- |
| upstream commit | `fcd294faffd1e88af1643a3a8c2359c41713f7c2` |
| upstream tree | `b4bf10438c6c3086a0e2dd78a6e4db659e49fbca` |
| 원본 경로 | 105개: 104개는 bytes·Git mode 그대로, `.gitignore`는 원본 prefix 뒤에 프로젝트 규칙 추가 |
| upstream 이력 | 118개 commit을 별도 로컬 `refs/remotes/upstream/baseline`에 보존. 프로젝트와 merge하지 않음 |
| 고지 | `LICENSE`·원본 `README`·파일별 copyright·m4 고지 보존. upstream 전체 tree에 `NOTICE` 없음 |
| import 검증 | 105개 경로의 내용·Git 실행 bit·파일 종류·부모 경로 및 Git ignore 노출 검사 통과 |
| 실패·회귀 시험 | 18개 unittest 통과. 원본 코드·서비스·네트워크를 실행하지 않는 임시 checkout 시험 |
| 소스 누락 방지 | `test/resultChecker/makefile`의 정확한 ignore 예외 추가. `core.ignorecase=false/true`에서 모든 원본 경로의 실제 staging 시험 통과 |
| Git 무결성 | 복원한 이력의 `git fsck --full` 통과 |
| 실제 서버 import 검증 | 봉구서버의 Ubuntu 26.04.1에서 동일한 105개 경로 검사·18개 회귀 시험 통과. 아래 별도 기록 참조 |
| Scribe build·runtime | 실행하지 않음. 클라우드의 build prerequisites 부재는 아래 기록 참조. Gate A–D 미통과 |

재실행 명령은 저장소 root 기준이다.

```sh
git rev-parse refs/remotes/upstream/baseline
git rev-parse 'fcd294faffd1e88af1643a3a8c2359c41713f7c2^{tree}'
git fsck --full
python3 -B test/verify_upstream_import.py
python3 -B -m unittest discover -s test -p 'test_verify_upstream_import.py' -v
```

검증기는 고정 object만 사용하며 Git replacement와 lazy fetch를 비활성화한다. 기준 object가 없으면 실패하고 명시적 획득 명령을 안내한다. 네트워크 접근을 자체 실행하지 않는다. 아직 upstream ref를 원격에 반영하지 않았으므로 프로젝트만 새로 clone한 환경에 해당 object가 있다고 가정하지 않는다. 아래 명령은 필요할 때 별도로 실행할 **재현 준비 절차**이며 이번 클라우드 작업에서는 실행하지 않았다. 이번 복원은 검증된 로컬 bundle을 사용했다.

```sh
git fetch https://github.com/facebookarchive/scribe.git \
  fcd294faffd1e88af1643a3a8c2359c41713f7c2:refs/remotes/upstream/baseline
```

실패 사례는 source bytes 변경·파일 누락, owner 실행 bit 추가/제거, 파일/부모 디렉터리 symlink, 원본 ignore 규칙·appendix marker 변경, makefile 예외 누락·새 source ignore, 기준 object 누락·tree 불일치를 포함한다. 정상·프로젝트 추가 ignore·Git replacement 무시도 시험한다. Git mode는 owner 실행 bit로 판정한다. 두 ignorecase 설정의 결과는 Git 패턴 매칭 검증이며 실제 Mac filesystem을 시험한 결과는 아니다. 원래 작업 트리의 index는 변경하지 않으며, 현재 stage/commit/publication의 정확성이나 root 문서의 내용, Scribe의 행동 동등성을 증명하지 않는다. 후속 staging 시 staged diff·경로·mode를 별도로 검토해야 한다.

### 클라우드 Linux 사전 점검

실행 환경은 Debian GNU/Linux 13 (trixie) x86_64이며 회사 승인 target matrix가 아니다.

| 확인한 도구 | 결과 |
| --- | --- |
| GCC C++ | 14.2.0 (Debian 14.2.0-19) |
| Python | 3.12.14 |
| Git | 2.52.0; import 검증은 `--no-lazy-fetch` 지원 필요 |
| GNU Make | 4.4.1 |
| pkg-config | 1.8.1 |
| autotools | `autoreconf`, `autoconf`, `automake`, `aclocal`, `libtoolize`가 PATH에 없음 |
| Thrift·PHP | `thrift`, `php`가 PATH에 없음 |
| 개발 의존성 | 확인한 표준 include 위치에 Boost·libevent·Thrift·fb303 header가 없고, `pkg-config --modversion libevent` 실패 |

원본 `README`, `bootstrap.sh`, `configure.ac`, `src/Makefile.am`, `lib/py/Makefile.am`을 읽고 위 prerequisites를 확인했다. `bootstrap.sh`·Scribe compile/link·PHP suite는 실행하지 않았다. 설치, 다른 dependency version 대체, system 설정 변경 또는 서버 접근으로 이 제약을 우회하지 않았다. 다음 빌드 단계에서 승인된 dependency/compiler 버전·prefix·hash를 고정한 격리 환경을 준비해야 한다. 이 도입 checkpoint는 현대 C++·Thrift API 이식이나 원본 메모리 결함을 수정하지 않는다.

### 봉구서버의 격리 import 검증

2026-10-04 승인된 서버 검증에서 첫 checkpoint를 기존 서비스 checkout과 분리한 사용자 소유 검증 경로에 복원했다. 아래 결과는 그 실행 보고를 반영한 기록이다. 클라우드 import 확인과 구분하며 회사 운영 baseline이나 Scribe compile/link 증거로 확대하지 않는다.

| 항목 | 서버 실행 결과 |
| --- | --- |
| 검증한 checkpoint | `scribe-next-milestone-1-20261004.tar.gz`의 첫 버전 |
| 검증한 archive SHA256 | `7f567523927306eba32a32c561fea2eff2becce22371a8f1d43d1764909c5a23` |
| OS·kernel | Ubuntu 26.04.1, kernel `7.0.0-34` |
| 검증 도구 | Git 2.53.0, Python 3.14.4 |
| 원본 경로 검사 | 105개 경로 통과 |
| 회귀 시험 | 18개 통과 |
| 복원·Git 검사 | bundle 검증, `git fsck --full`, `git diff --check` 통과 |
| 작업 상태 | HEAD `739eda4ed5b02fca5663c1c30d310e2370472873` 유지, staged 변경 없음 |
| 수행하지 않은 항목 | dependency 설치, Scribe 전체 build·runtime, 서비스 기동·배포, Gate A–D |

서버에서 검증한 소스·검증기·시험 코드는 이번 결과 기록 후에도 동일하다. 후속 checkpoint는 이 서버 결과를 설명하는 문서와 복원 기록만 갱신했다. 업데이트된 archive 전체를 서버에서 다시 실행한 것으로 주장하지 않는다. 검증된 변경의 Mac 동기화·작업 branch commit·push는 별도 사용자 승인 범위이며 main merge나 다음 변경의 push까지 승인된 것은 아니다.

## 정적 검토의 근거 범위

검토 기준일은 2026-10-04다. 공개 upstream `fcd294faffd1e88af1643a3a8c2359c41713f7c2`와 Thrift v0.25.0의 commit `27e8a425ffb498e190df3a12e239326bf5ba9ed6` 전체 tree를 별도 checkout에서 확보했다. 주요 경계의 source 링크와 채택 방향은 [설계의 의존성 전략](design.ko.md#의존성-전략)과 [근거 목록](design.ko.md#근거와-적용한-원칙)에 둔다.

두 번째 RPC와 동적 routing, PHP suite의 build 미연결, 목표 파일 transport·fb303 C++ source의 존재와 API 경계를 정적으로 확인했다. 원본 `StdFile`의 할당·해제 불일치는 [실제 재현·최소 수정·component 비교](contracts-status.md)를 완료했다. 코드 도입과 import 회귀 시험은 위 기록대로 실행했다. 후속 의존성·RPC library build와 초기 compile 실패는 [빌드 기록](build-status.md), 최신 성공과 제한된 시험은 [API 이식 기록](api-compat-status.md)에 구분했다. Scribe daemon 실행, PHP suite, 전체 old/new wire·spool differential, 전체 sanitizer/LeakSanitizer와 성능 시험은 미실행이다. 제한된 StdFile 양방향 비교·ASan/UBSan 및 Ubuntu reader LSan 성공은 [최신 계약 기록](contracts-status.md)의 범위로 한정한다. 이전 단계의 raw logs는 checkpoint의 해당 evidence에 보존한다. v8 loopback 서버 결과는 당시 [별도 기록](loopback-rpc-status.md)에 상위 작업 요약으로 반영했고 이후 v10 인계에서 raw records를 수신·검증했다. 새 relay v11의 서버 실행은 상위 작업 확인 요약으로 반영했으며 그 raw records는 아직 미수신이다. 검증한 archive와 실제 범위는 [최신 기록](relay-contracts-status.md)을 따른다. 임시 dependency checkout과 빌드 산출물은 저장소에 포함하지 않는다.

## 라이선스 경계

공개 기준 SHA의 [upstream LICENSE](https://raw.githubusercontent.com/facebookarchive/scribe/fcd294faffd1e88af1643a3a8c2359c41713f7c2/LICENSE)는 Apache License 2.0이다. 현재 저장소에 원본 `LICENSE`와 파일별 copyright·attribution을 포함했다. 고정 전체 tree에 `NOTICE`는 없음을 확인했다. 원본 도입 commit에서는 104개 파일의 bytes와 Git mode가 동일하고 `.gitignore`만 원본 bytes 뒤에 명시된 프로젝트 규칙을 추가했다. 후속 네 build 파일 변경은 [빌드 기록](build-status.md)에 별도로 남겼으며 이후 C++ API 경계의 변경은 [API 이식 기록](api-compat-status.md)에 남긴다. IDL과 기존 시험 소스는 동일하며 queue/store/spool 로직은 유지한다. 향후 변경·배포 시 고지를 유지하며 변경 파일에 변경 사실을 표시한다. 의존성 고지도 검토한다. 이 기록은 개인·회사 저작권의 새 주장이나 회사 fork 공개 권한을 부여하지 않는다.
