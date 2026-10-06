# 독립 리뷰 항목 수정과 검증

2026-10-06 정책 변경: 아래 승인·수정·측정은 당시 이력이다. 현재 기본 동작은 [원본 계약 우선 정책](legacy-compatibility-policy.md)을 따르며 route/byte/format/delivery/monitoring 변경은 되돌린다. 과거 raw 결과는 현재 검증으로 세지 않는다.

2026-10-05 · 최신 store 수정의 base/main `da74ec9`; 이전 독립 범위의 base `ddca67e`

관련 문서: [README](../README.md) · [이전 relay 기록](relay-contracts-status.md) · [manifest](review-fixes-manifest.json)

## 현재 store 수정과 검증

사용자의 미해결 항목 수정 요청에 따라, 이전에 제외한 다섯 store 결함을 수정했다. `store.cpp`의 bucket 이름 pointer arithmetic, 서로 다른 service_list의 빈 pool key 공유, 동적 목적지 변경 시 이전 owner 해제, NetworkStore 설정 복사, BucketStore의 remove_key/bucket_range 복사를 다룬다. 기본 list port를 0으로 초기화하고 재연결 시 server 목록 누적과 알 수 없는 bucket child type의 null dereference도 막았다. 동적 store의 복사본은 새 category를 조회하며 실패하면 설정된 static endpoint를 사용한다.

- [store 회귀](../test/store_review_contracts.py) 13개: 실제 파일 bytes·loopback 전송·공유 연결 수명·갱신 실패·복사된 category의 목적지를 확인한다. 처음 추가한 11개는 수정 전 각각 실패했고, 기존 sanitizer build의 bucket 경로에서는 실제 global-buffer-overflow를 재현했다.
- Ubuntu 26.04.1·GCC 15.2·Boost 1.83·Thrift/fb303 0.25.0에서 새 clean build·`scribed --help`와 전체 **137개 통과, 실패0, skip0, 23.739초**. 기존 prefix를 재사용하고 generated code와 production objects를 새로 빌드했다.
- 별도 새 ASan+UBSan build의 API suite **82개 통과, 실패0, skip0, 8.802초**. dependency libraries는 비계측이며 `detect_leaks=0`이다. 전체 daemon 누수·TSan 성공으로 확대하지 않는다.
- [기존 wire 시험](../test/review_limits_contracts.py)에 outgoing empty/multi-entry의 작은 frame/message 정확 경계와 invalid/omitted-limit reload를 추가했다. 고유 시험 수는 그대로 10개이며 subcase를 더해 세지 않는다.

동적 목적지 시험은 resolver 결과만 test module로 제어하고 production copy/periodicCheck/NetworkStore/ConnPool과 실제 TCP 연결을 실행한다. 실제 mapping TTL·service discovery·회사 old/new differential의 완료를 뜻하지 않는다. 후속 수정은 `codex/store-review-fixes`에서 검증했으며 원격 반영 상태는 Git 이력과 해당 PR을 따른다. 아래 manifest와 124/69개 기록은 PR #4 이전 단계의 근거로 유지한다.

## 이전 독립 범위

이전 독립 범위는 빈 payload queue drain, Git capability 진단, 실제 production server 생성 경로의 loopback 검증, retry jitter 0, C++17 shuffle, 유한 Thrift wire 한도와 build/이력 문서다. 당시 제외했던 다섯 store 결함은 위 후속 범위에서 처리했다. 회사 fork·실제 Thrift binary·설정 및 성능 baseline은 미확인이다. 사용자가 기억한 회사 Thrift 0.9.0은 추정이며 회사 운영 동등성을 선언하지 않는다.

- 새 clean C++17 compile/link와 실제 `scribed --help` exit0. GCC14에서 `_GLIBCXX_USE_DEPRECATED=0`을 함께 사용했다
- 이 새 build의 전체 프로젝트 **124 통과, 실패0, skip0, 34.375초**
- 별도 ASan+UBSan build의 실제 API/queue/store/loopback/relay/한도 **69 통과, 실패0, skip0, 13.304초**
- ASan/UBSan은 현재 Scribe production objects·generated code·fixture에 적용했다. 기존 dependency libraries는 비계측이며 `detect_leaks=0`이다. 전체 daemon 누수·TSan·회사 old/new differential 성공을 뜻하지 않는다
- 독립 검토에서 blocking correctness/scope 문제 없이 승인된 독립 범위의 인계가 가능하다고 판정했다. 별도 전체124개 재실행도33.166초/skip0으로 통과했다. 이후 PR #4/main `da74ec9`에 반영됐다

기존101개에 queue4, shared factory1, Git 진단1, retry/shuffle7, wire 정책10이 추가됐다. 반복·subcase를 고유 시험 수124에 더하지 않는다. 앞선 API67개 통과 후 mapping RPC와 작은 downstream 한도에서 spool 보존 시험을 추가해 최종 API69개가 됐다. 첫 mapping 시험의 counter 기대는 FACEBOOK 전용 통계 stub을 일반 counter로 오해한 fixture 오류였으며 해당 기대만 제거했다. 실패 log도 보존한다.

## 최소 수정

1. `StoreQueue::threadMember`: 작업 유무를 message-byte 합계가 아닌 실제 queue 비어 있음으로 판정. byte accounting·threshold·실패 batch 우선순위는 유지한다. 수정 전 빈 payload3개는 OK/received3에도 종료·주기 출력이 없었고 loss0이었다. 수정 후 실제 FileStore 경로의4개 시험/9개 경우가 통과하며5개 일반 대조군은 동일하다
2. `verify_upstream_import.py`: object 접근 전에 `git --no-lazy-fetch --no-replace-objects --version`으로 필수 safety option 지원을 검사한다. 오래된 Git을 missing object로 오진하지 않으며 unsafe fallback이나 자동 fetch는 추가하지 않았다. 회귀19개와 별도 pristine105-path 검사가 통과한다
3. `scribe::createServer`: production processor/protocol/thread/max_conn 구성을 공유한다. `startServer()`는 이 factory 뒤 serve를 호출하며 기본 listener는 기존 port-only 형식이다. 시험만 명시적127.0.0.1 transport를 제공한다. production CLI/main listener 전체 기동은 여전히 미실행이다
4. `BufferStore::setNewRetryInterval`: range/offset0이면 RNG draw 없이 jitter0을 적용한다. 실제 변경 전 두 modulo0 경로가 UBSan에서 재현됐고 변경 후8개 경우가 통과했다. 양수 jitter의 interval·RNG·cap·counter와 기존 base/min/max0 clamp 의미는 유지한다
5. `BucketStore::periodicCheck`: 제거된 random_shuffle 호출을 기존 GNU forward Fisher–Yates 순서의 rand loop로 대체한다.8개 크기×4개 seed×연속2회에서 실제 이전/이후 child 순서와 다음 rand가 동일하다. GNU libstdc++ 검증이며 Clang/libc++는 미설치·미실행이다

## 유한 wire 한도 정책

두 새 global 설정은 **serialized binary RPC payload bytes**를 사용하며 외부4-byte frame prefix를 제외한다.

```conf
thrift_max_frame_size=268435456
thrift_max_message_size=268435456
```

각 기본값은256MiB다. 설정은 엄격한 양의 decimal1..2147483647 bytes만 허용한다.0, 음수, +부호, 빈 값, hex, suffix, overflow는 잘못된 초기 정책으로 판정하며 server factory가 listener 구성을 거절한다. 이 신규 설정의 엄격 파싱을 기존 다른 설정의 변환 규칙으로 확대하지 않았다. 두 값은 서로 다를 수 있고, frame이 더 작든 message가 더 작든 작은 한도가 실제 수락 경계가 된다. recursion depth64는 유지한다.

설정은 startup-only다. 운영 reinitialize로 store 설정을 다시 읽어도 기존 server와 outbound clients의 wire 정책을 유지하며 변경하려면 restart가 필요하다는 log를 남긴다. live server/socket/input buffer가 서로 다른 정책으로 바뀌는 부분 reload는 하지 않는다. 양쪽 Scribe 및 mapping service의 유효 한도를 함께 확인해야 한다.

server 자체·accepted socket·별도 input TMemoryBuffer에 같은 TConfiguration을 적용한다. Thrift input factory는 기존 memory transport의 설정만 바꾸고 반환하며 새 framing을 덧붙이지 않는다. relay·mapping client는 socket과 framed transport 생성 시 동일한 명시적 설정을 사용한다. frame 한도만 올리거나 socket만 설정해 별도 input memory의100MiB budget이 남는 문제를 피했다. upstream Thrift를 패치하지 않았다.

relay Log 송신 전에는 non-strict wire size `21 + sum(15 + category bytes + message bytes)`를 검사한다. category·envelope overhead를 포함하며 frame/message 중 작은 값보다 크면 CONN_TRANSIENT를 반환한다. retained batch를 조용히 분할하거나 버리지 않고 sent를 늘리지 않는다. 기본 TFramedTransport::flush는 이 read 한도를 outbound에 강제하지 않으므로 relay의 명시적 검사가 필요하다. mapping client의 응답 read 한도는 적용하지만 모든 RPC의 outgoing serialized payload를 새로 제한하는 generic transport를 만들지는 않았다.

### 실제 경계 시험

- 기본256MiB−1과256MiB Log를 같은 TCP 연결에서 수락,256MiB+1 header는 해당 연결만 닫고 다른 client는 정상 동작
- 이전0.25 기본 설정의 실제 base fixture는20MiB+44-byte header를 거절하고 다른 client는 정상 동작했다. 이 이전 fixture는 duplicated test-only loopback 생성이며 현재의 shared production factory 검증과 구분한다
- 독립 frame128/message1024 및 frame1024/message128에서 작은 한도−1/동일/+1, 작은 frame 뒤 큰 frame의 반복 수락
- category88 bytes + message4 bytes의 serialized128-byte Log와 category overhead 초과
- 초기 invalid 값18개, default/override/INT_MAX 설정, 실제 input factory의 설정 identity, startup-only reload
- 실제 relay outgoing envelope/category 한도·reply frame/message 한도, input batch bytes/count/sent 보존
- 실제 mapping RPC client의 reply frame/message−1/동일/+1. NetworkStore 동적 목적지 전환·store copy·bucket routing 경로를 시험한 것은 아니다
- **20MiB(20,971,520-byte) oldest ordinary spool**을 실제 FileStore reader→BufferStore→NetworkStore→downstream worker/FileStore로 분할 없이 전달. 목적지 exact bytes·수락1/sent1·loss0·spool 삭제 확인
- downstream128-byte 한도에 거절된20MiB spool은 재시도 상태로 남고 원본 frame bytes·loss0·sent0을 유지

256MiB는 호환 후보로 승인한 유한 기본값이며 메모리 상한 보장이 아니다. per-connection read buffer·decoded strings·queue·relay copy와 동시 요청 때문에 RSS가 훨씬 커질 수 있다. 회사의 실제 큰 요청과 자원 예산에 맞춰 줄이거나 명시적으로 조절해야 한다.

**256MiB보다 큰 retained spool batch의 재전송 문제는 남는다.** FileStore는 oldest file 전체를 읽으며 max_write_size는 disk write threshold이고 max_size rotation은 쓰기 뒤 판정할 수 있다. 두 설정을 줄이는 것만으로 serialized frame size나 한 entry의 크기가 보장되지 않는다. byte 변환·silent batch split·무제한 허용을 추가하지 않았다. 작은 downstream 한도 또는 oversized retained batch는 계속 실패·재시도할 수 있다. 기존 ACK는 queue 수락이며 파일 완료/fsync가 아니다. sent는 downstream OK entry 수이며 unique durable 처리 수가 아니다. 이전 승인된 out|trunc 수정과 LF 재적용·crash/write-failure/unlink 위험은 유지한다.

### 공식 소스 근거와 미확정 사항

공식 [Thrift0.9.0 TNonblockingServer](https://github.com/apache/thrift/blob/0.9.0/lib/cpp/src/thrift/server/TNonblockingServer.h)의 기본 inbound frame은256MiB다. 같은 버전 [TFramedTransport](https://github.com/apache/thrift/blob/0.9.0/lib/cpp/src/thrift/transport/TBufferTransports.cpp)는 configured frame ceiling 없이 signed-negative size를 검사했다. 현대 [Thrift0.25.0 TConfiguration](https://github.com/apache/thrift/blob/v0.25.0/lib/cpp/src/thrift/TConfiguration.h)의 기본 frame16,384,000/message104,857,600 bytes를 명시적 정책으로 대체한 것이다. 회사 runtime이 이 공식0.9.0과 동일하다는 뜻은 아니다.

구 [0.9.0 PosixThreadFactory](https://github.com/apache/thrift/blob/0.9.0/lib/cpp/src/thrift/concurrency/PosixThreadFactory.h)는1MiB stack을 명시했다. 현0.25 std::thread는 OS/runtime 기본 stack을 사용하며8MiB라고 가정하지 않는다. timeout/NODELAY/receive retry defaults와 Scribe relay5000ms·linger 설정은 변경하지 않았다.

## 남은 항목과 실행 경계

- production CLI listener/main/startServer 전체 기동, namespace daemon 시험, 회사 old/new·HDFS/FACEBOOK/shared matrix, full worker failure scheduler/race·10 store/thriftfile·성능·운영은 미완료
- cloud/server의 network namespace 생성은 EPERM으로 거절됐으며 다른 flag·권한 변경으로 재시도하지 않았다. shared production factory의 explicit loopback transport coverage와 전체 CLI 기동 미검증을 구분한다
- oversized retained spool의 처리 정책과 전체 gate는 열려 있다. 위 후속 수정의 Ubuntu 137/82개 결과를 이전 source의 101/124/69개 결과와 합산하지 않는다

## 재현 및 서버 인계

아래124/69 기대값은 이전 독립 범위의 역사적 실행 기준이다. 후속 store stage는137/82였고, main `c3f3459` 이후 test-only ThriftFileStore는146개/새 focused9를 통과했고, 후속 승인된 copy 수정의 현재 재현 기대값은 [147개/focused10 기록](thriftfile-contracts-status.md)을 따른다. 서로 다른 source/stage의 시험 수를 합산하지 않는다.

기존 승인된 toolchain/dependency prefixes를 사용하고 새 설치·서비스 기동 없이 격리된 새 source copy에서 [README build recipe](../README.md)를 실행한다. 실제 production source가 현재 checkout과 일치해야 한다. generated code는 재생성하며 objects를 이전 checkpoint에서 복사하지 않는다.

```sh
# 실제 환경의 검증된 기존 prefix를 지정
export THRIFT_PREFIX=/absolute/prefix/thrift-0.25.0
export FB303_PREFIX=/absolute/prefix/fb303-0.25.0
export TOOLS_PREFIX=/absolute/tools/usr
export SCRIBE_BUILD=/absolute/new-source-matching-built-copy
python3 -B -m unittest discover -s test -p 'test_*.py' -v
python3 -B -m unittest discover -s test -p 'test_scribe_api_compat.py' -k wire_ -v
python3 -B -m unittest discover -s test -p 'test_scribe_api_compat.py' -k review_ -v
sh -n bootstrap.sh
git diff --check
```

전체124개/skip0을 확인하고 기본256MiB−1/동일/+1과20MiB spool 시험에 충분한 메모리를 확보한다. 실제 명령·source hashes·log·binary hash·효과적인 settings와 source unchanged 확인을 보존한다. sanitized lane은 CXX에 `-fsanitize=address,undefined -fno-sanitize-recover=all`, CXXFLAGS에 `-O1 -g -std=c++17 -fno-omit-frame-pointer`를 사용해 새 configure/build한다. API fixture는 configured CXX를 사용하므로 sanitizer 링크 flag도 이 경로로 전파된다. `ASAN_OPTIONS=detect_leaks=0:halt_on_error=1 UBSAN_OPTIONS=halt_on_error=1:print_stacktrace=1`로 API suite69개를 실행한다. 이 설정을 LSan 성공으로 보고하지 않는다.

checkpoint에는 credential-free Git bundle·source files/modes·tracked diff·이번 및 이전 raw evidence·복원/재검증 명령을 포함한다. dependency caches·executables·objects·runtime spool·인증 값·개인 Git 설정은 제외한다. 승인된 push/merge는 Mac executor의 source/hash/diff/test 확인 뒤 수행하며 cloud checkpoint 생성 자체를 원격 반영으로 설명하지 않는다.


## P1 dynamic-copy global-lock stall regression — 이전 수정 기록 (2026-10-06)

PR #25는 아래 copy-setting 수정과 one-shot lookup을 되돌렸다. 현재 clone은 원본 fields만 복사하며 초기 mapping 조회를 추가하지 않는다. 아래 재현·측정은 그 이전 수정본의 이력이다.

Base main `b0bfc89`. The approved NetworkStore copy-setting fix resolved the new
category synchronously while `createCategoryFromModel` held the handler write
lock. A blocked mapping resolver therefore stalled both the creating Log and an
unrelated existing-category Log. Cloud before-fix regression tests failed twice:
`resolver_entered=1 new_log_ready=0 existing_log_ready=0`, plus inline resolution.
The explicit resolver blocker stays blocked until the fixture releases it; the
post-fix checks require both Log calls to finish beforehand and keep OK queue
acceptance. This is an actual handler/worker fixture with a scripted resolver,
not a production-daemon outage or a latency benchmark.

At that stage, `NetworkStore::copy` preserved the approved configuration fields and static
fallback, marking a one-shot initial lookup. The worker's first open or preceding
periodic check performs it; failure keeps fallback without repeated lookup on
reopen, and ordinary periodic refresh remains. No compatibility-default decision,
previous copy/data-preservation fix or wire/ACK/retry policy was reverted at that stage.

Cloud and server each passed focused6 and full203 with failures/errors/skips0.
Server `/workspace/scribe-next-dynamic-copy-validation-20261005-NdPAFz` used fresh
source and the existing toolchain for eight clean build/test/DESTDIR/help steps;
source-copy, generated-code and dependency freshness checks stayed enabled.
The new staged binary SHA256 is
`c446b2ccbbb5885be1dd8c2a00c238d35f0ea2f2903f5d20e50b0b819434bbf9`;
build/stage bytes match. The old fcd294f/Thrift0.9 baseline was unchanged.

The existing actual direct/unpooled mapping case passed with that new binary:
A/cacheA/strict TTL5 B/failed-refresh-stillB/recoveryA, plus both missing-key static
fallbacks. Exact payload/wire/chronology, ordinary counts/status and six owned
child/listener cleanup matched; local raw replay reproduced comparison.json.
This lifecycle comparison is separate from the copied-category lock fixture.
A network-none/lo-only uid65534 task container had CPU2/RAM2GiB/PIDs128,
cap-drop ALL/no-new-privileges and no mounts/published ports. All32 current
operating IDs, including the separate LumaWeave task, remained unchanged; only
the owned stopped container and temporary snapshot were removed. An initial
preflight stopped before creating a container because its prior-batch count31
was stale; its diagnostic is retained with the final current-ID preservation.

This removes the new locking regression within the reviewed scope. It does not
settle compatibility-default policy, prove the full fault/config/platform matrix,
or add a benchmark, release/package/tag or service deployment. Input bundle26
lacked the separate pinned-upstream object; existing verified local baseline
objects were supplied explicitly without changing import-checker protections.

## Child-store null 방어 (2026-10-06)

Base main `fb310f6`(PR #28)에서 unknown child type이 Buffer primary/secondary,
Multi child, Category model의 null dereference를 일으키는 것을 실제 C++ fixture로
재현했다. 모델이 없는 Category의 message 경로도 같은 결함을 재현했다.
copy의 같은 null 조회는 코드에서 확인했으며 수정 후 clone의 실패·message 보존을 실행했다.
수정 전 전체 212개 시험은 새 회귀 한 개의 5개 subcase에서 실패했으며 error/skip은 0이었다.

생성 결과가 없으면 configure 호출을 건너뛰고, Buffer는 기존 file fallback을 사용한다.
Multi/Category는 실패 상태를 남기며 null child를 추가하지 않는다. 모델이 없는
Category와 그 clone은 기존 실패 경로에서 message bytes와 retry vector를 보존한다.
정상 설정, empty Multi/Category의 기존 open 결과, copy 설정, queue·loss·routing 정책은 바꾸지 않았다.

Ubuntu 26.04.1/GCC 15.2/Python 3.14.4, 새 Thrift compiler/runtime·fb303 0.25.0와
Boost 1.83을 task 전용으로 준비했다. 기존 validation driver의 새 source copy에서
configure·clean/build·전체 212개 시험(failure/error/skip 0)·DESTDIR install·설치된
scribed help가 통과했다. raw evidence는 checkout 밖 `batch2-before-ready`와
`batch2-after`에 보관했으며 후자의 validation manifest SHA256은
`ffe7711017077c0457a89f507dc4b5ca9e13596614b757ac884578f1ad487e66`이다.
이 결과는 비-HDFS/static lane이며 Rocky8/9, actual old/new production daemon 및
전체 fault matrix의 새 검증으로 확대하지 않는다.

## 비-HDFS stub의 null string 반환 방어 (2026-10-06)

Base main `104d4d0`(PR #29)의 비-HDFS `HdfsFile::getFrame`은 `return 0`으로
null C string에서 std::string을 생성했다. 실제 component fixture에서 새 회귀 한 개의
6개 subcase(길이 0/1/UINT_MAX, 일반 및 ASan+UBSan 실행)가 모두 std::logic_error와
abort로 실패했다. enabled-HDFS 구현을 호출하거나 수정한 결과는 아니다.

빈 std::string을 반환하도록 한 줄을 수정했다. stub의 openWrite/isOpen false와
HDFS 미지원 상태를 유지하며 프레임이나 저장 기능을 새로 구현하지 않는다.
수정 후 ordinary-spool component 13개가 failure/error/skip 0으로 통과했다.
현재 component의 ASan+UBSan 실행과 원본/현재 ordinary-spool 교차 reader 검사를
포함하며 LSan, 새 full daemon build 및 enabled-HDFS 검증은 포함하지 않는다.
raw evidence는 checkout 밖 `batch3-before.log`와 `batch3-after.log`에 보관했다.

## Updater 예외 잠금 해제와 Thrift 오류 처리 (2026-10-06)

Base main `621257e`(PR #30)에서 실제 updater RPC driver에 로컬 allocation 예외를
한 번 주입했다. 예외를 fixture가 회수한 뒤 cached mapping 조회가 잠금에 막히는
것을 재현했다. 소유한 IPv4 loopback peer의 protocol/application 오류 응답도
기존 실패 반환 대신 Thrift 예외가 호출자 밖으로 전달되는 것을 재현했다.
새 회귀는 2개이며 수정 전 전체 215개 중 3개 실패(한 시험과 다른 시험의 두 subcase),
error/skip 0이었다. GNU operator-new link wrapper는 이 단일-thread fixture에서만
한 번 실패를 주입하며 나머지 allocation은 원래 operator new로 전달한다.

수동 lock/unlock을 기존 Thrift Guard로 교체해 같은 scope를 unwind에서도 해제한다.
기존 transport/mapping 예외 처리는 유지하고 나머지 Thrift TException을 같은 RPC
실패 경로로 처리한다. bad_alloc 등 비-Thrift 예외는 삼키지 않는다. 정상 요청 bytes,
TTL·cache 삭제/갱신·counter 이름과 update 순서·routing·retry 정책을 바꾸지 않는다.

새 source copy의 configure·clean/build·전체 215개(failure/error/skip 0)·DESTDIR
install·installed help가 같은 Ubuntu/native dependency lane에서 통과했다.
실행은 로컬 fixture이며 새 production-daemon/old-new/HDFS/Rocky 결과가 아니다.
raw evidence는 checkout 밖 `batch4-before`와 `batch4-after`에 보관했다.

## Throttle 공유 상태 동기화 (2026-10-06)

Base main `6b5b270`(PR #31)의 Log는 handler read lock 아래 throttle의
lastMsgTime/numMsgLastSecond를 갱신했다. 실제 base-handler Log에 16개 local caller를
동시에 시작하고 test clock을 한 초로 고정했다. 수정 전 새 회귀의 rate=100 quota
검사가 실패했으며 전체 216개는 failure 1/error 0/skip 0이었다. 별도 ThreadSanitizer
실행은 throttleDeny의 numMsgLastSecond 접근에서 data race를 보고하고 exit 66이었다.

기존 handler lock을 write lock으로 넓히지 않고 별도 Thrift Mutex/Guard로 throttle
상태 계산만 보호했다. max_msg_per_second=0은 기존 빠른 경로를 유지한다.
정상 single-caller 경계, 큰 batch의 원본 half-limit 예외, counter 이름과 다음 초
reset을 유지한다. test spy의 received vector를 공유하지 않고 production base Log를
직접 호출하며 고정 clock은 GNU link wrapper/atomic test 값으로만 제공한다.

수정 후 새 configure·clean/build·전체 216개(failure/error/skip 0)·DESTDIR install·
installed help가 통과했다. 같은 local ThreadSanitizer fixture도 exit 0/경고 없이
통과했다. TSan은 handler/updater source를 별도 instrument한 제한된 실행이며 다른
production objects와 dependency는 instrument하지 않았다. 전체 daemon race 부재,
old/new production 동등성이나 benchmark 결과가 아니다. raw evidence는 checkout 밖
`batch5-before`, `batch5-after`, `batch5-before-tsan.log`, `batch5-after-tsan.log`다.
