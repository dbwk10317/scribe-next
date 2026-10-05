# scribe-next 세부 구현 문서

2026년 10월 4일 · 개발자 작업 분할 및 검증 계획

관련 문서: [설계와 호환성 계약](design.ko.md) · [저장소 안내](../README.md)

## 개요

설계 문서의 호환성 계약을 고정한 뒤, 빌드 복구와 리팩토링을 분리한다. 첫 upstream 도입과 제한된 빌드·Thrift API 경계를 수행했다. 도입 검증은 [출처 기록](source-status.md#첫-소스-도입-검증-2026-10-04), 의존성·초기 실패는 [빌드 기록](build-status.md), scribed clean compile/link 이력은 [API 이식 기록](api-compat-status.md), 이후 ordinary spool·config/routing 55개 시험과 메모리 수정은 [계약 검증 기록](contracts-status.md)을 따른다. 초기 build/API 단계에서 IDL·queue/store/spool 알고리즘과 기존 시험 소스를 유지했으며 후속 승인된 production 수정은 각 단계의 전후 검증과 구분한다. 운영 daemon 기동·배포·회사 baseline 동등성 판정은 수행하지 않았다.

기준 SHA는 `fcd294faffd1e88af1643a3a8c2359c41713f7c2`다. 제안 후보는 C++17과 Thrift 0.25.0이며 목표 OS는 Linux다. 클라우드 Debian 13·GCC 14와 봉구서버 Ubuntu 26.04.1·GCC 15.2에서 Boost 1.83·Thrift 0.25의 기본 비-HDFS C++17 build와 당시 계약 시험 55개를 통과했다. 후속 loopback suite는 cloud·Ubuntu 각89개 통과이고, 최신 fixed-host relay suite는 cloud·Ubuntu 각101개 통과이며 아래 실행 기록을 따른다. 회사 승인 배포판·toolchain·feature matrix는 미확정이다. 프로젝트 이름 scribe-next와 기존 실행 바이너리·서비스·설정 이름을 구분하고, 호환성에 영향을 주는 이름 변경은 하지 않는다. 각 단계는 작은 review 단위로 진행하고 앞 단계의 완료 조건을 통과한 뒤 다음으로 넘어간다.

## 작업 0 upstream 도입과 운영 기준 확보

현재 상태: 고정 원본 105개 경로 도입과 로컬 upstream 이력 보존, 재현 가능한 import 검증은 완료했다. 회사 차이 목록·승인된 platform matrix·old binary·baseline manifest는 미확보이므로 작업 0 전체 완료가 아니다. 프로젝트와 upstream 이력의 merge·원격 반영은 미실행이다.

별도 도입 변경으로 고정 upstream tree·경로·이력과 고지를 보존한다. 도입 변경에 이식 코드를 섞지 않는다. 회사 fork SHA, upstream 대비 diff, compiler 및 link flags, dependency 버전·패치·라이선스, service unit, 실행 옵션, config 전체, 환경변수, filesystem 및 spool 위치를 수집한다. secrets는 제거하고 설정 key와 구조는 남긴다. client 언어·생성 compiler·protocol/transport 설정, health-check와 fb303 query, HDFS·동적 bucket mapping·서비스 디스커버리 사용 여부를 포함한다. 공개판 `getService()`는 항상 실패하므로 회사 환경 구현 없이 서비스 이름 기반 경로의 동등성을 가정하지 않는다.

기존 실행 binary의 해시와 재현 가능한 build recipe를 고정한다. 정상, burst, category 폭증, relay outage, disk full 및 shutdown 조건의 baseline을 확보한다. category 수·batch 크기·fan-out·장애 지속 시간을 통제하고 throughput, p50/p95/p99 latency, CPU, RSS, thread 수, queue bytes, lost/requeue/retry counter, spool 증가량, 복구 시간과 종료 시간을 기록한다. 지표별 허용 차이와 측정 반복 횟수는 운영팀 승인을 받아 확정한다.

완료 조건은 회사와 upstream의 차이 목록, 승인된 platform matrix 및 baseline manifest이다. 회사 자료가 없으면 upstream 이식 작업만 가능하며 회사 호환성 gate는 열린 상태로 남긴다.

## 작업 1 계약 fixture 만들기

대상은 `if/scribe.thrift`, `if/bucketupdater.thrift`, `src/scribe_server.cpp`, `src/store_queue.cpp`, `src/store.cpp`, `src/file.cpp`, `src/env_default.cpp`, `src/dynamic_bucket_updater.cpp`, `src/network_dynamic_config.cpp`, 설정 파서 `src/conf.cpp`와 sample config 파일이다. `src/conf.cpp`의 key 조회·값 변환과 store별 configure 호출을 연결해 기본값, 잘못된 값 처리와 부모 설정 상속을 목록화한다. sample config 목록과 include 관계는 고정 SHA의 전체 tree에서 완성한다.

old binary로 요청·응답 byte fixtures, store 출력 및 spool fixtures를 생성하고 SHA256과 생성 조건을 보존한다. 빈 batch, 빈/미정의 category discard 뒤 OK, exact/prefix/default와 겹치는 prefix의 map 첫 일치, NUL·비ASCII·개행 포함 message, 중복 category, 다중 store, 큐 제한 직전·일치·초과, 수락 뒤 제한을 넘기는 거대 batch를 넣는다. 요청과 무관한 category의 과부하도 거절을 유발하는지 비교한다. status, counter 및 호출 응답을 같이 기록한다. nondeterministic timestamp·random retry는 허용된 필드만 정규화하고 payload나 category는 정규화하지 않는다.

두 번째 RPC는 old/new mapping client·server 양방향 wire와 예외를 비교하고 TTL 만료, 갱신 실패, 빈 mapping, 누락 bucket, 목적지 변경·재연결과 counter를 검증한다. host/port 직접 지정과 회사 서비스 이름 조회 경로를 구분한다. 정적 bucket hash fixture만으로 동적 갱신을 통과시키지 않는다.

기존 PHP `test/testsuite.php`와 설정 fixture를 먼저 조사한다. 고정 포트·임시 경로·프로세스 종료 대상과 PHP/Thrift client 의존성을 격리 환경에 맞추고 시험별 assertion·실패 exit를 확인한다. root 실행을 기본으로 복사하지 않는다. `make check`에는 PHP suite 실행 연결이 없고 `lib/py/Makefile.am`의 `check-local`은 `all`에 의존할 뿐이므로 별도 명시적 실행이 필요하다.

완료 조건은 독립된 old/new process에 같은 입력을 넣고 반환·bytes·관찰 가능한 side effect를 비교할 수 있는 harness다. helper framework나 production 추상화를 추가하지 않는다. 기존 test driver가 있으면 먼저 재사용한다.

## 작업 2 최신 Thrift 빌드와 빌드 경계 복구

대상은 `configure.ac`, `bootstrap.sh`, `Makefile.am`, `src/Makefile.am`, dependency 탐지 m4 및 generated code 생성 규칙이다. 확인한 configure.ac는 Boost system/filesystem과 Thrift·fb303 경로 및 optional HDFS 설정을 가지고 있다. 실제 link 목록과 bootstrap 도구는 구현 전에 해당 파일 원문에서 확인한다.

먼저 공식 Thrift 0.25.0 release와 checksum을 고정하고, 목표 Linux에서 compiler와 필요한 C++ runtime을 빌드·검증한다. 이 의존성 build가 통과한 뒤 Scribe build를 연결한다. compiler/runtime 버전을 일치시키고 prefix와 include/link 경로를 명시한다. libthriftnb와 libevent 포함 여부, pthread linkage, fb303 header/library, HDFS feature off/on을 각각 확인한다. [검증된 Linux recipe](../README.md#검증된-linux-c-빌드-recipe)의 명시적 Boost library 이름과 dependency/include/link prefix를 사용하고 CFLAGS/CXXFLAGS의 사용자 값·빈 값을 보존한다. constants가 없는 두 IDL의 생성 결과에 없는 빈 constants source만 build 목록에서 제외하며 생성 파일을 손으로 만들지 않는다. compiler flag는 C++17 후보로 고정하고 target Thrift의 요구 표준과 충돌하면 문서의 결정을 갱신한다. compiler warning은 기록하되 모든 경고를 한번에 수정하지 않는다.

두 IDL의 field와 method를 변경하지 않고 목표 compiler로 다시 생성한다. v0.25.0의 `cpp:pure_enums`로 두 IDL을 실제 생성했고, Thrift/fb303 및 두 RPC 정적 library의 C++17 build·링크 smoke를 통과했다. 이후 기본 비-HDFS C++ lane의 scribed clean compile/link도 통과했으며 old/new wire·runtime 동등성은 미검증이다. 기존 generator option과 generated signature를 비교하며 generated files를 손으로 고치지 않는다. old language client가 의존하는 설치·패키지 위치도 보존한다.

완료 조건은 청결한 격리 환경에서 목표 Thrift의 compiler/runtime 빌드와 필요한 library 탐지가 성공하고, build manifest에 compiler, dependency hash, flags와 generated diff가 남는 것이다. 이때 Scribe를 최초 compile해 API·링크 오류를 분류한다. Scribe 전체 compile/link 통과는 작업 3과 4의 경계 수정 후 Gate A에서 판정한다. 의존성 build 성공만으로 wire·runtime 호환성을 선언하지 않는다.

## 작업 3 Thrift와 fb303 API 맞추기

대상은 `src/common.h`, `src/env_default.h/.cpp`, `src/scribe_server.cpp`, `src/conn_pool.cpp`, `src/dynamic_bucket_updater.h/.cpp`, `src/network_dynamic_config.h/.cpp`, generated interface를 사용하는 `src/store.cpp` 및 각 모듈의 관련 header다. 고정 SHA의 include graph를 따라 수정 범위를 좁히고 선언과 구현을 함께 검토한다.

목표 release의 TProcessor, protocol factory, socket/server transport, TNonblockingServer, ThreadManager와 thread factory constructor를 대조한다. port를 직접 받던 서버 생성부를 목표 server transport 객체 경계에 맞춘다. Boost shared_ptr에서 std::shared_ptr로 바뀐 boundary와 Boost를 사용하는 fb303 `setServer()`의 소유권을 함께 이식하고 중복 control block을 만들지 않는다. framed binary와 서버·mapping client의 명시적 strict=false/false를 보존한다. relay client도 원본의 `setStrict(false, false)`를 그대로 유지한다. 기본값 의존이라는 이전 기록은 실제 source와 달라 정정했다. 목표 release의 frame/message limit, timeout과 예외 default도 목록화한다. 후속 review 작업 트리의 전역 `thrift_max_frame_size`·`thrift_max_message_size`는 각각 기본 256 MiB의 양의 십진수 startup-only 한도로 server/socket/input-memory와 두 client에 일관되게 적용한다. outgoing relay 초과 batch는 preflight에서 transient failure로 반환하고 자동 분할·drop하지 않는다. 회사 동등성과 oversized spool 정책은 미확정이다. Thrift 0.9.0의 명시적 1 MiB thread stack과 0.25 std::thread의 OS/runtime 기본값을 구분하며 8 MiB라고 가정하지 않는다. 후속 수정본의 최종 검증을 완료한 것으로 세지 않는다.

fb303는 동일 0.25.0 release로 실제 build·workspace 설치를 통과했다. 운영 method·lifecycle과 기존 client 대비 호환성은 아직 별도 확인 항목이다. 현재 FacebookBase 사용, status/details/counters, reinitialize/shutdown 및 기타 상속 method를 mapping한다. 기존 라이브러리가 목표 runtime에서 동작하면 유지한다. 기존 `PosixThreadFactory`·`ReadWriteMutex` 사용부는 현재 concurrency wrapper 안에서 필요한 부분만 대체하고 lock 순서·scope를 비교한다. worker queue의 pthread 동작은 그대로 둔다.

완료 조건은 old/new client와 relay 네 방향 테스트, bucket mapping 양방향 호출·갱신, fb303 전체 method 비교 및 server lifecycle 비교 통과다. server 종류를 blocking으로 바꾸거나 fb303를 없애는 방법으로 컴파일 오류를 회피하지 않는다.

## 작업 4 파일 transport와 spool 호환

대상은 `src/file.h/.cpp`, `src/store.h/.cpp`의 FileStore 및 ThriftFileStore와 multifile 계열이다. std::filesystem은 기존 Boost 경로·예외·filename 처리와 동등성이 확인된 사용 지점만 바꾼다. v0.25.0의 `TFileTransport`·`TSimpleFileTransport` 및 chunk/flush/event buffer 설정 API를 먼저 사용해 비교한다. API·형식 차이가 재현된 부분만 호환 처리하며 transport 삭제를 전제로 재구현하거나 모든 I/O를 새 interface로 감싸지 않는다.

일반 spool은 길이 field의 endian·폭, category 별도 frame, zero frame, truncated header/payload, 손상 길이 처리와 EOF 의미를 검증한다. thriftfile은 원본 transport의 기록 단위·메타데이터·복구 규칙을 별도로 fixture화한다. ordinary file 출력은 byte-for-byte로 비교하고 이름·rotation·symlink는 file tree manifest로 비교한다.

완료 조건은 old-write/new-read 및 new-write/old-read가 ordinary spool과 thriftfile 모두에서 통과하는 것이다. 같은 spool 동시 writer는 테스트에서도 금지한다. reader가 corruption을 다르게 처리하면 호환성 이슈로 남기고 배포 gate를 열지 않는다.

### 제한된 ThriftFileStore 현재 관찰

main `c3f3459` 이후 test-only 관찰은 default TFileTransport와 use_simple_file의 bytes, chunk padding, 실제 reader, close/reopen/suffix와 copy 설정을9개 시험으로 확인했고 cloud·Ubuntu146개/skip0과 focused ASan+UBSan9개/skip0을 통과했다. 후속 승인된 copy의 useSimpleFile 한 필드 수정과 legacy 파일 보존 회귀를 추가한 작업 트리는 새 cloud clean build/help·전체147개/skip0·focused ASan+UBSan10개/skip0을 통과했다. 기존 framed 파일은 유지하고 새 suffix에 설정된 raw mode를 기록한다. chunk 초과와 empty의 기존 transport 처리·반환·성공 집계는 사용자 결정대로 유지한다. 같은 production·test 소스는 새 Ubuntu clean build/help·전체147개/skip0·focused ASan+UBSan10개/skip0도 통과했다. 위 old/new 양방향 완료 조건은 미통과다. [현재 기록](thriftfile-contracts-status.md)과 [승인 범위·동작 보존 결정](thriftfile-fix-options.md)을 따른다.

### 원본 메모리 결함의 별도 검증

고정 upstream의 [StdFile 소스](https://github.com/facebookarchive/scribe/blob/fcd294faffd1e88af1643a3a8c2359c41713f7c2/src/file.cpp#L65)에서 `readNext()`가 malloc으로 할당한 inputBuffer를 소멸자가 delete[]로 해제하는 오류를 ASan으로 재현했다. 후속 별도 변경에서 해제만 free로 맞추고, 공개 원본 C++03 component 대 현재 C++17 component의 양방향 frame bytes·EOF·손상 입력 결과와 현재 ASan/UBSan 통과를 확인했다. [현재 계약 기록](contracts-status.md)을 따른다. 클라우드 LeakSanitizer는 ptrace 제약으로 미검증이며, 별도 Ubuntu에서는 37-byte 양성 대조와 제한된 reader의 LSan 활성 9개 시험을 통과했다. 전체 daemon 누수 검사나 full old Scribe/Thrift runtime 비교는 아니다. 미정의 동작을 호환 계약으로 보존하지 않고 빌드 복구나 일괄 RAII 정리와 분리했다.

### 후속 FileStore 실행 기록

main `ffc73ee` 이후 실제 FileStore의 write_category/add_newlines bytes, readOldest·deleteOldest·replaceOldest와 제한된 BufferStore replay를 검증했다. 전체 cloud 70개 시험이 통과했지만, 기존 app|trunc 실패 및 partial replay의 lost/delete 경로도 재현됐다. 시험 통과를 결함 해결로 해석하지 않으며 production 수정은 별도 승인·전후 검증으로 분리한다. [최신 FileStore 기록](filestore-contracts-status.md)을 따른다.

### 승인된 truncate 최소 수정

사용자가 재현된 부분 replay 손실을 예외적으로 수정하도록 승인한 뒤 StdFile openTruncate에서 app flag만 제거했다. cloud·Ubuntu의 새 clean build와 각 74개 시험에서 남은 2개 보존·다음 replay를 확인했다. 추가 LF 재적용은 기존 옵션 의미대로 남겨 검증했고, 원자적 교체·crash/write-failure 보장을 추가하지 않았다. 최신 근거와 남은 위험은 [수정 기록](truncate-fix-status.md)을 따른다.

### Loopback RPC 실행 경계

main `24692d6` 이후 native Thrift server에 127.0.0.1 전용 test transport를 넣어 실제 processor/handler/worker와 파일 bytes를 검증한다. production main/startServer의 wildcard bind는 변경·실행하지 않았다. v8은 cloud·Ubuntu 각 89개 시험을 통과했으며 Ubuntu에서는 새 clean build·help와 TCP 10개 × 5회, kernel 관측 listener 50개 모두 127.0.0.1 및 소유 자식 55개 회수를 확인했다. 당시 v9는 상위 작업이 검증한 요약으로 기록했고, 이후 v10 인계에서 해당 raw records를 수신·검증했다. 프레임·운영 RPC·재초기화·정상 종료와 오류 cleanup의 최신 실행 범위는 [loopback 기록](loopback-rpc-status.md)을 따른다. 전체 old/new runtime·network relay·실패 queue drain과 운영 승인 gate를 대신하지 않는다.

### Relay·connection pool 실행 경계

main `32004a6` 이후 production 변경 없이 실제 NetworkStore/ConnPool의 fixed-loopback bytes·응답·pool 수명·명시적 retry를 시험했다. 응답 유실 뒤 peer6개 수신/sent3, 모의 downstream prefix 처리 뒤 A,A,B,C를 기록하며 의미를 바꾸지 않았다. 정상 두-worker relay→FileStore와 기존89개를 포함한 cloud·Ubuntu 각101개 시험을 통과했다. Ubuntu v11은 새 clean build·help와 relay 반복50회·loopback/자식 회수도 통과했다. 당시 v12는 상위 작업 요약만 보존했으며 이후 v13에서 raw records·request frame43개를 수신·검증했다. relay 구현 `5594efaae67e214880a31c755c0f5cb86cfc192a`는 PR #3/main `ddca67e6c3485459648e4cbc975d5dae9ddccfc2`에 반영됐다. 이 101개는 그 이전 relay 단계의 수이며 현재 review의 최종 시험 수가 아니다. 새 Mac 검증, 실제 worker 실패 scheduler·service/list/dynamic failover·동시 pool race·full old/new runtime과 성능은 미검증이다. 상세 근거는 [relay 기록](relay-contracts-status.md)을 따른다.

## 작업 5 제한된 현대 C++ 정리

작업 3과 4가 통과한 모듈만 대상으로 null 표현, explicit ownership, 지역 RAII 및 제거된 API를 정리한다. RAII로 바꾸는 경우 lock 획득·해제 지점과 예외 경로를 before/after 비교한다. raw backlink는 소유자가 아니므로 무조건 shared_ptr로 바꾸지 않는다. container 교체, hash 교체, time 기준 교체, batching 변경, move를 통한 shared batch 소유권 변경은 별도 증거 없이 수행하지 않는다.

완료 조건은 각 변경이 이식 목적에 연결되고 differential test가 계속 통과하는 것이다. 관련 없는 dead code, formatting 및 module 분리는 별도 작업으로 미룬다. CMake 전환은 이 단계 뒤 선택 단계로 분리하고 기존 install·feature matrix와 비교한다.

## 모듈별 구현 경계

| 모듈 | 구현 시 허용 변경 | 유지할 계약 |
| --- | --- | --- |
| if/scribe.thrift·if/bucketupdater.thrift와 생성 코드 | 동일 IDL의 목표 compiler 재생성 | method, field ID, enum 값, namespace, 예외 |
| configure.ac와 Makefile 규칙 | 의존성 탐지, flag, 생성·링크 순서 | feature 선택, 설치 산출물과 경로 |
| src/env_default.h/.cpp와 common.h | 목표 Thrift 생성자·타입·동시성 경계 | nonblocking server, framed binary, lock 의미와 환경 조회 |
| src/scribe_server.cpp | generated interface 및 fb303 연결 | Log 반환, 라우팅, 운영 API |
| src/store_queue.cpp | 컴파일에 필요한 최소 타입 변경 | 큐 크기, lock 순서, batch와 종료 |
| src/store.cpp | Thrift·파일 API 사용 지점 호환 | 10 store, 상태 전이, 기본값 |
| src/conn_pool.cpp | client·transport 생성 경계 | pool 재사용, 재연결, 예외와 timeout |
| src/dynamic_bucket_updater.h/.cpp·network_dynamic_config.h/.cpp | mapping client의 Thrift API 경계 | TTL, 실패·빈 응답·목적지 변경, counter와 서비스 조회 |
| src/file.cpp | 필요한 API 호환과 별도 메모리 결함 수정 | bytes, framing, rotation, flush |
| src/conf.cpp | 필요한 컴파일 오류만 수정 | 파싱, 값 변환, 오류·상속 의미 |

새 파일이 필요하면 책임과 기존 파일에 둘 수 없는 이유를 PR에 적는다. 테스트 harness 외의 공용 framework나 대규모 디렉터리 재편을 기본 작업으로 만들지 않는다.

## store별 검증 분할

| store | 최소 fixture 및 판정 대상 |
| --- | --- |
| file | byte 출력, newline, meta record, size/time rotation, filename, `_current` symlink |
| buffer | DISCONNECTED/SENDING_BUFFER/STREAMING 전이, primary 실패, replay, flush_streaming, retry 및 fallback |
| network | OK/TRY_LATER/transport exception, reconnect, pool 재사용, timeout, dummy Log와 동적 목적지 갱신 |
| bucket | delimiter, hash 입력, bucket 수 및 경계, 대상 선택과 출력 bytes; 동적 mapping 조합은 별도 fixture |
| thriftfile | 기존 transport bytes, file rotation, old/new reader 호환 |
| null | discard와 반환·counter 의미 |
| multi | 복수 하위 store 성공·부분 실패와 순서 |
| category | category별 하위 store 생성과 parent config 상속 |
| multifile | 다중 category 파일 경로·이름·분배 |
| thriftmultifile | 다중 category와 thriftfile 형식의 결합 |

표는 전체 store별 목표 검증 범위다. 일부 ordinary FileStore·relay와 제한된 ThriftFileStore 관찰은 후속 기록대로 실행했지만 표 전체를 통과하지 않았다. 모든 설정 key를 constructor 기본값과 configure 파싱에 연결하는 inventory가 추가로 필요하다. 사용되지 않는 store도 upstream 지원 범위를 유지하므로 compile 및 fixture coverage에서 제외하지 않는다.

## 검증 계획

Golden test는 고정 request/response bytes, output files와 spool을 비교한다. Differential test는 old/new를 별도 디렉터리와 port에서 실행해 동일 입력을 넣고 return code, counters, routing과 output을 비교한다. wire message sequence ID와 timestamp 차이는 명시한 규칙으로만 처리한다. 구체적 ordering guarantee는 baseline에서 관찰한 범위로 정의하며 전역 순서를 새로 약속하지 않는다.

Fault test는 relay disconnect 전후, response loss 후 재시도, partial write, disk full, permission denied, corrupted spool, config reload 실패, STOPPING 중 category 생성, SIGTERM 및 강제 종료를 포함한다. ACK 이후 강제 종료 손실이나 재시도 중복을 새 버전에서 숨기지 않는다. shutdown 후 잔여 queue와 spool, counters 및 재기동 결과를 기록한다. fsync 또는 exactly-once 기대를 fixture에 넣지 않는다.

Performance test는 승인된 normal/burst/outage workload를 동일 장비에서 old/new 교대로 반복한다. category 수·batch 크기·fan-out·장애 지속 시간을 명시하고 category별 worker 생성 비용을 측정한다. Release 최적화 조건과 dependency version 차이를 manifest에 남기고 throughput·latency·CPU·RSS·thread 수·queue·recovery를 보고한다. sanitizer build는 correctness 보조이며 성능 판정에 사용하지 않는다. ASan/UBSan과 가능한 TSan lane을 분리하고 기존 race가 발견되면 known issue와 수정 승인 경계를 기록한다.

## 제안 검증 명령

아래는 전체 빌드 복구·행동 검증을 위해 격리 checkout에 맞춰 조정할 예시이며 전체 성공 recipe가 아니다. 이미 수행한 dependency/부분 build와 실패한 전체 compile은 [빌드 기록](build-status.md)을 따른다. 소스 도입 검증의 실제 명령과 결과는 [현재 상태](source-status.md#첫-소스-도입-검증-2026-10-04)에 별도로 기록한다. `bootstrap.sh`가 autoreconf 뒤 configure를 호출하므로 configure 인자를 함께 전달한다. 실제 toolchain에서 요구 도구·옵션을 확인하며 dependency 설치 및 실제 service 실행 권한은 별도다.

```sh
git rev-parse HEAD
git diff --stat fcd294faffd1e88af1643a3a8c2359c41713f7c2
thrift --version
c++ --version
pkg-config --modversion libevent
rg -n 'boost::shared_ptr|TNonblockingServer|ThreadFactory|TFileTransport' src
rg -n 'DEFAULT_|getString|getUnsigned|flush_streaming' src
CXXFLAGS='-O2 -std=c++17' ./bootstrap.sh \
  --with-thriftpath="$THRIFT_PREFIX" \
  --with-fb303path="$FB303_PREFIX"
make -j2
make check
```

현재 upstream의 `make check`는 PHP suite를 실행하지 않는다. 위 명령의 성공을 행동 검증으로 간주하지 말고, 격리 경로·포트·프로세스 대상으로 조정한 기존 PHP driver를 명시적으로 실행한다. 새 harness는 기존 harness가 부족할 때 최소로 만든다. 실제 연결한 driver로 golden, old/new matrix, fault 및 performance workload를 실행하고 결과 JSON·bytes·file manifest와 해시를 보존한다. 종료나 장애 주입 명령은 production 대상에 실행하지 않는다.

## 완료와 배포 gate

Gate A는 platform/feature matrix의 compile·link 성공이다. Gate B는 두 IDL, wire, fb303, 설정, 10 store와 동적 목적지 갱신 differential 통과다. Gate C는 양방향 spool·relay, fault와 종료 결과가 승인된 계약에 맞는 것이다. Gate D는 회사 baseline 기반 성능과 운영 기준 승인이며 그 뒤 canary 배포·롤백 실행 권한을 받는다. 원본 메모리 결함의 재현·수정 검증은 별도 변경으로 연결하고 미검증 상태를 숨기지 않는다. 어느 gate도 현재 통과하지 않았다.

배포 runbook에는 old artifact 해시, 신규 artifact 해시, dependency manifest, spool writer 소유자, canary route, traffic 중지 절차, rollback threshold 및 담당자를 채운다. 역호환 spool 검증 실패, 새로운 loss/duplicate 양상, 운영 API 차이 또는 승인 성능 기준 초과 시 rollout을 멈춘다. 구현 PR은 목적별로 build, API, file transport, 제한된 refactor 순으로 나누고 각 PR에 실제 수행한 검증만 쓴다.

## 근거 상태와 남은 확인

고정 upstream 전체 tree와 Thrift v0.25.0 tree를 별도 checkout에서 확보하고 두 IDL, handler·queue·store·파일 경로, 동적 bucket 갱신, 기존 PHP driver·build 연결, 목표 Thrift의 주요 C++ 경계를 정적으로 대조했다. 모든 source 경로의 동작이나 전체 header를 검증한 것은 아니다. 설정 파서의 경로는 `src/conf.cpp`다. 전체 key·기본값·파싱·상속의 연결 관계는 구현 전 inventory로 완성한다. Thrift/fb303·Scribe RPC library build와 초기 전체 compile 실패는 [빌드 기록](build-status.md), 후속 성공과 현재 범위는 [API 이식 기록](api-compat-status.md)에 남겼다. 제한된 StdFile component ASan/UBSan·양방향 frame 비교와 config/routing 55개 시험의 cloud·Ubuntu 결과 및 Ubuntu reader LSan 성공은 [최신 기록](contracts-status.md)에 추가했다. Scribe 운영 daemon, PHP suite, 전체 sanitizer/LeakSanitizer, full old/new·성능 시험은 미실행이다. 고정 commit과 근거 범위는 [출처 기록](source-status.md)을 따른다.

설계 문서의 링크를 evidence entrypoint로 사용한다. 구현 시 각 계약에 source path·symbol·line, fixture ID, old 결과, new 결과, 검증 command, timestamp와 reviewer를 연결한다. upstream 사실, 요청에서 제공된 보존 조건, 구현 제안 및 회사 확인이 필요한 항목을 ledger에서 구분한다. 실패와 미실행도 보존한다.

karpathy-guidelines와 ponytail의 가정 명시·최소 변경·기존 구현 재사용 지침을 적용했다. 불필요한 rewrite, 전체 Boost 제거, 새 추상화와 즉시 CMake 전환을 작업에 넣지 않았다. Apache 2.0 attribution, 변경 표시와 dependency 고지 검토는 release gate에 포함하고 회사 코드 공개 권한은 별도 확인한다.

## 주요 근거

- [공개 upstream 기준 SHA](https://github.com/facebookarchive/scribe/tree/fcd294faffd1e88af1643a3a8c2359c41713f7c2)
- [설정 파서 conf.cpp](https://github.com/facebookarchive/scribe/blob/fcd294faffd1e88af1643a3a8c2359c41713f7c2/src/conf.cpp)
- [Apache Thrift 공식 다운로드](https://thrift.apache.org/download)
- [Thrift v0.25.0 fb303 IDL](https://raw.githubusercontent.com/apache/thrift/v0.25.0/contrib/fb303/if/fb303.thrift)
- [Apache License 2.0](https://www.apache.org/licenses/LICENSE-2.0)

Thrift 버전 근거는 2026년 10월 4일 확인했다. 파일별 동작 근거는 함께 제공하는 설계 문서의 고정 SHA 링크를 사용한다.
