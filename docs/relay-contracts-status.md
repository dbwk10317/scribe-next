# NetworkStore·connection pool relay 계약 검증

2026-10-04 · 아래 실행은 base/main `32004a6a627723e081cedf7143323f3769cac220` 위의 당시 test-only 작업 트리 기준

이 relay 단계는 이후 구현 commit `5594efaae67e214880a31c755c0f5cb86cfc192a`와 [PR #3](https://github.com/dbwk10317/scribe-next/pull/3)를 거쳐 main `ddca67e6c3485459648e4cbc975d5dae9ddccfc2`에 반영됐다. 현재 review의 입력은 v13 main 인계이며 raw Ubuntu 기록도 포함한다. 아래 101개 시험과 production 무수정·static byte-identical 설명은 이전 relay 단계의 사실이다. 후속 review 수정본의 최종 clean build·sanitizer·전체 회귀·독립 검토 완료를 뜻하지 않는다.

관련 문서: [README](../README.md) · [manifest](relay-contracts-manifest.json) · [이전 loopback 검증](loopback-rpc-status.md)

## 범위

이전 수신 RPC fixture에서 outbound 경로로 범위를 확장했다. 실제 `NetworkStore`, `ConnPool`, `scribeConn`과 현재 generated client를 사용한다. 실패·재시도 시험은 단일 thread의 Python 표준 라이브러리 peer와 직접 `handleMessages()` 호출로 제어하며, 별도 정상 사례 하나에서 실제 handler→StoreQueue/network worker→다른 handler→FileStore worker까지 연결한다.

production 코드·IDL·build 규칙은 변경하지 않았다. 승인된 truncate 수정과 기존 ACK·retry·손실·중복 의미를 유지한다. 클라우드에서는 새 의존성을 설치하지 않고 기존 Debian 13·GCC 14.2·Boost 1.83·Thrift/fb303 0.25.0 도구와 source-matched production objects를 사용한다. fixture는 새로 컴파일하며 source·generated code·compiler dependency freshness 검사를 유지한다. 이 클라우드 단계의 새 full scribed clean build는 수행하지 않았다. 별도 Ubuntu v11 clean build는 아래에 구분한다.

## 실행 결과

당시 전체 relay suite는 기존89개와 새 relay10개·helper2개로 클라우드에서 **101개 통과, 실패0, skip0, 31.879초**다. 독립 검토에서도 relay10개(5.900초)와 helper2개가 통과했고, 기존 API Python 함수49개가 그대로이며 기존 다른 test modules도 바뀌지 않았음을 확인했다.

초기 focused 실행은 직접 relay9개를 통과했으나 새 worker fixture의 pre-validation에서 global handler를 준비하지 않은 setup 오류1개가 있었다. 시험 fixture의 초기화 순서만 고친 뒤 최종 focused10개(5.480초)와 위 전체 suite를 통과했다. 실패 로그도 증거에 보존한다. production 결함을 고친 단계가 아니다. 후속 Ubuntu 검증은 아래와 같이 완료했고 새 Mac suite는 아직 수행하지 않았다.

기존 응답 유실·prefix 모의 시험2개를 별도로 실행해 합성 peer3개, 실제 수신한 full request frame6개와 각 STATE 결과를 checkpoint의 relay evidence에 저장했다. 이 추가 실행을 고유 시험 수101개에 합산하지 않는다. 관측한 자식3개와 소유 socket은 모두 회수·종료됐다.

## Ubuntu v11 검증과 근거 출처

2026-10-04 상위 작업이 Mac executor를 통해 확인한 서버 실행 결과다. 실제 검증 대상은 Library **v11**, 1,266,714 bytes, SHA256 `48b76642c1e586ffcdb6f83028b1aee27a6144550398f37655df109783d7fd48`이며 base/main `32004a6` 위의 source/doc148개 작업 트리다.

- Ubuntu 26.04.1·GCC 15.2·Boost 1.83·Thrift/fb303 0.25.0의 새 clean build **5.980초**, 실제 `scribed --help` exit0
- 전체 suite **101 통과, 실패0, skip0, 21.889초**
- relay10개 × 5회 **50회 통과**. 반복을 고유 시험 수101개에 합산하지 않음
- kernel 관측 listener115개 모두 **127.0.0.1**, 소유 자식165개 회수, socket·pipe 닫힘 및 남은 시험 process/listener0
- 응답 유실 후 peer6/sent3, 모의 prefix AABC, pool 수명, dummy4096/4097 및 정상 two-worker 파일 bytes 확인
- source/doc148개, 기존 checkpoint, dpkg/APT 상태와 boot ID 불변. Mac main `32004a6` clean 유지

당시 v12 기록은 상위 작업이 검증한 요약만 보존했고 raw files를 받거나 직접 읽지 않은 상태였다. 보고된 evidence tar는 45,173 bytes, SHA256 `b9b8f647bcde1ad8da1da2a1a70813a28c94460650afc90aad5383c6fe3dfe59`다. 이 과거 tar 식별 정보와 v13에서 직접 확인한 unpacked records를 구분한다.

후속 **v13 main 인계에는 `ubuntu-relay-evidence/records/`의 raw files가 포함됐다**. archive `manifest.json`의 해당 72개 record를 실제 크기·SHA256과 대조했고 `ubuntu-relay-results.json`, `project-101-tests.log`, `relay-runtime-observations.json`, `timings.jsonl` 및 clean build/help log를 읽었다. 위 101PASS/0FAIL/0error/0skip(21.889초), clean build5.980초/help0, relay50회·listener115개·자식165개 결과를 확인했다. raw request frame43개도 포함돼 있으며 cloud frame6개와 별도다. `parent-verified-summary.json`과 저장소의 기존 relay manifest에 남은 raw 미수신 표시는 v12 기록 시점의 이력이지 v13의 현재 파일 유무가 아니다.

v13 입력은 `scribe-next-main-20261004.tar.gz`, 1,417,479 bytes, SHA256 `4a1dfa7e2e0a580870e15a15d4fe39599b48c7ad8d5260befd462e33149de7e4`이며 source/doc148개·archive manifest604개·로컬 bundle6 refs와 main을 검증했다. raw records는 v11 source의 서버 실행 근거다. v13 archive 전체나 이후 review source를 서버에서 다시 실행한 것으로 설명하지 않는다.

후속 checkpoint는 문서·evidence 갱신만 포함하고 구현·시험 bytes와 mode는 실제 검증한 v11과 같다. 문서 갱신 archive 전체를 서버에서 다시 실행한 것으로 설명하지 않는다. 실패 worker scheduler·공유 pool 동시 race·구 runtime/회사 동등성·성능·durability와 production main/startServer listener 기동은 여전히 미검증이다.

## 관찰한 계약

| 경계 | fixture가 판정하는 결과 |
| --- | --- |
| pooled/unpooled OK | category/message의 NUL·비UTF-8·개행 bytes와 전체 outgoing framed/non-versioned binary 요청이 독립 golden과 일치. caller batch는 그대로이며 성공한 entry 수만 `scribe_overall:sent`에 더함 |
| 빈 batch·binary reply | 빈 batch의 성공은 sent를 늘리지 않음. 같은 연결에서 non-versioned 및 versioned reply를 수락하되 outgoing 형식은 non-versioned로 유지 |
| fixed-host TRY_LATER | false, connection 유지, sent=0. 다음 명시적 호출이 같은 connection으로 전체 batch를 다시 전송 |
| 응답 유실 | peer가 A,B,C를 받은 뒤 reply 없이 닫음. 첫 call은 false/closed/sent=0. 다음 명시적 retry에서 새 connection으로 동일 A,B,C를 보내 OK이면 sent=3, peer가 관찰한 entry는 총6개 |
| 부분처리 모의 | downstream이 A만 처리한 것으로 모의 기록하고 TRY_LATER. 다음 전체 A,B,C 재시도로 모의 side effect가 A,A,B,C가 됨. 실제 Scribe의 STOPPING 부분수락 재현으로 해석하지 않음 |
| 실패 뒤 복구 | 무응답 timeout, 잘린 reply, oversized header-only reply, application exception에서 false/closed/sent 증가 없음. 다음 명시적 호출이 새 connection으로 성공 |
| pool 수명 | 같은 host:port를 쓰는 두 store가 한 accepted socket을 공유. 반복 open은 추가 ref를 만들지 않으며 한 owner의 반복 close 뒤 다른 owner가 같은 socket으로 송신. 마지막 close에서 EOF, 이후 open은 새 connection |
| dummy 경계 | message bytes 4096이면 payload만 전송. 6000-byte category는 이 합계에 포함하지 않음. 두 message 합계4097이면 empty Log가 먼저 나가고 OK 뒤 payload 전송. dummy TRY_LATER는 payload를 억제하며 다음 exact frame으로 이를 확인 |
| 실제 worker 연결 | 정상 batch의 upstream RPC ACK 뒤 정상 종료로 network worker를 join. downstream 수락 counter를 확인하고 downstream 정상 종료 뒤 실제 FileStore 출력 bytes 확인 |

`sent`는 관찰한 downstream OK의 entry 수이며 downstream 고유 처리 수나 영속 기록 완료 수가 아니다. 응답 유실 시험은 remote가 받은 bytes를 확인한 뒤 연결을 닫는다. 부분처리 시험의 prefix ledger는 제어된 downstream application 정책이다. IDL의 결과는 OK/TRY_LATER enum뿐이며 처리된 prefix 길이를 담지 않는다.

모든 재시도는 시험 driver가 한 번씩 명시적으로 요청한다. worker backoff·실패 queue drain·복구 scheduler를 이 결과로 통과시키지 않는다. pooled fatal 복구는 단일 owner에서 시험하며, 두 owner가 공유하는 connection의 동시 실패/race는 별도 미검증이다.

## 안전 경계와 결과 해석

Python peer는 `127.0.0.1:0`에 bind한 socket을 계속 보유하며 실제 주소·할당 port와 accepted 연결의 주소를 확인한다. C++ relay driver는 open 전에 fixed `127.0.0.1`, 유효 port, 정확히 500ms timeout을 검사하고 service/list/dynamic destination을 거절한다. 실제 worker 연결도 test-only native loopback server를 사용한다. production `main/startServer`의 wildcard listener 경로는 바꾸거나 실행하지 않는다.

직접 driver와 relay worker fixture에는 시험 전용 20초 alarm이 있고 scripted Python RelayPeer에도 20초 deadline이 있다. scripted peer의 각 socket·pipe 단계 대기는 남은 deadline과 최대3초로 제한한다. 실제 worker fixture의 Python owner는 기존 LoopbackProcess의 별도 readiness10초·RPC 수신3초·shutdown 전송 후 wait5초와 오류 cleanup의 terminate/kill 뒤 각 wait2초를 사용한다. 이 단계별 timeout과 child alarm을 전체 RPC/정상 종료 시간 보장으로 해석하지 않는다. C++ connect/send/receive timeout 500ms는 각 native socket 작업의 설정이며 전체 RPC가 정확히 500ms 안에 끝난다는 성능 보장이 아니다. cleanup은 소유 socket과 자식만 닫고 기존 terminate/kill/wait 경로를 사용한다. 전역 process-name kill은 쓰지 않는다.

큰 응답 시험은 4-byte 길이 header만 보내며 body를 만들거나 보내지 않는다. 관찰 결과는 실패·connection close·정상 재연결이다. Thrift source의 size check를 참고하되 allocator/RSS를 계측한 시험이나 일반 DoS 안전성 판정으로 확대하지 않는다. Python peer는 request body를 64KiB로 제한하며 helper unit 시험으로 제한 초과 header 뒤 body read가 없음을 확인한다. startup 진단 수집이 실패해도 listener·stdin/stdout을 닫고 소유 자식을 회수하는 helper 실패 경계도 별도 시험한다.

현재 합성 데이터와 고정 sequence만 검증했다. production traffic, 서비스 검색·list failover·동적 목적지, pool 동시성 stress, 전체 legacy client/server, 회사 fork, 10 store 전체, thriftfile, 성능·durability 및 full daemon sanitizer는 미검증이다. 정상 shutdown의 bytes 검사는 failed queue 전체 배출이나 full destructor/pool teardown·leak-free를 뜻하지 않는다. Gate A–D 전체는 열려 있다.

## 공개 원본 근거와 이전 검증

고정 upstream `fcd294faffd1e88af1643a3a8c2359c41713f7c2`의 `scribeConn::send` 본문은 당시 relay 단계 구현과 byte-identical이었다. 후속 review의 wire-size preflight가 추가된 현재 본문에 이 동일성 판정을 적용하지 않는다. 비교한 1813 bytes의 SHA256은 `4463a5a66e6f7e06a55ed37471d5681a187798ee243d7d930a3e4628c45cb0bc`다. 이 정적 비교는 원본의 결과 분기·counter·close 정책이 유지됐다는 근거이며, 구 Thrift runtime으로 원본 binary를 실행한 differential은 아니다.

이 relay 구현 단계의 입력은 Library v10, 1,234,290 bytes, SHA256 `3a4974f176412c98f78f6113b11a905c40a49972c9d794f9ab7562836737ba0f`다. source/doc142개·manifest485개·credential-free bundle5 refs와 main/bytes/mode/fsck를 확인했다. 이전 loopback 구현은 `cdf21648550c47e68626a90bab2ebf11a9c8cd9f`, [PR #2](https://github.com/dbwk10317/scribe-next/pull/2)를 거쳐 현재 main에 반영됐다.

v10에는 이전에 요약만 받은 v8 Ubuntu raw records도 들어 있다. 해당 hashes를 검증하고 89PASS/0FAIL/0skip(20.857초), clean build5.972초/help0, TCP50회·listener50개·자식55개 관측 기록을 읽었다. 이 raw evidence는 새 relay suite 실행 결과가 아니다. 이전 Mac 실행은 통과 method31개, unittest reported run32, skip5, error0이며 Linux integration pass89개와 합치지 않는다. 보고된 GitHub CI workflow/check/status는 없고 CI pass로 세지 않는다.

## 재현

```sh
export THRIFT_PREFIX=/absolute/prefix/thrift-0.25.0
export FB303_PREFIX=/absolute/prefix/fb303-0.25.0
export TOOLS_PREFIX=/absolute/workspace-tools/usr
export SCRIBE_BUILD=/absolute/source-matching-configured-built-copy
python3 -B -m unittest discover -s test -p 'test_scribe_api_compat.py' -k relay -v
python3 -B -m unittest discover -s test -p 'test_*.py' -v
git diff --check
```

당시 실행 수·시간·source/test/log hashes는 relay manifest에 기록한다. 이후 v13 raw server records의 파일 크기·SHA256은 인계 archive manifest와 구분한다. prerequisite/platform skip은 통과로 세지 않는다. source가 달라지면 새 build가 필요하며 기존 objects를 무검사 재사용하지 않는다. 엄격한 import 검사는 기존 의도된 15개 build/API 차이를 계속 실패로 표시한다. 원본 도입 commit `00826b8`의 별도105-path pass와 혼합하지 않는다.
