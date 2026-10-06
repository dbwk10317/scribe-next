# Loopback TCP RPC·worker·파일 출력 검증

이 문서는 v8 시험·v9 요약 기록 당시의 범위를 보존한다. 이후 PR #2로 main `32004a6`에 반영됐고 v10 인계에서 당시 Ubuntu raw records를 수신·검증했다. 아래 미commit/raw 미수신 표현은 그 기록 시점의 상태다. 최신 test-only 후속 작업은 [relay 기록](relay-contracts-status.md)을 따른다.

2026-10-04 · base/main `24692d6c310588a9bd5d33ef3d203a5313dea6c5` · 후속 클라우드 작업 트리, 미commit·미push

관련 문서: [README](../README.md) · [manifest](loopback-rpc-manifest.json) · [이전 truncate 수정](truncate-fix-status.md)

## 범위와 결과

production 코드·IDL·build 규칙을 바꾸지 않고, 실제 TCP framing부터 generated processor·당시 scribeHandler·StoreQueue/FileStore worker까지 이어지는 **test-only loopback server**를 추가했다. 당시 승인된 truncate 수정과 LF·ACK·loss/retry 의미를 유지했다. 현재 truncate 동작은 [원본 계약 우선 정책](legacy-compatibility-policy.md)을 따른다. 고정 원본 Scribe/Thrift daemon과의 differential이나 회사 운영 동등성을 완료한 것은 아니다.

클라우드에서는 기존 승인된 Debian 13·GCC 14.2·Boost 1.83·Thrift/fb303 0.25.0 도구만 사용한다. 기존 source-matched production objects를 재사용하되 각 실행에서 source·generated code·object dependency freshness를 검사하고 새 C++ fixture를 컴파일한다. 이번 클라우드 단계에서 전체 scribed clean build·패키지 설치는 수행하지 않았다. 별도 Ubuntu clean build 결과는 아래에 구분한다.

전체 최신 suite는 이전 74개 + TCP 계약 10개 + 플랫폼 분류 2개 + harness 실패 경계 3개로 클라우드에서 **89개 통과, skip 0, 31.040초**다. 상세 hash와 명령은 [manifest](loopback-rpc-manifest.json)에 기록한다. cleanup 보강 전 동일 TCP 10개를 5회 반복한 50회 호출도 통과했다. 반복 호출을 새 시험 수로 합산하지 않는다.

## Ubuntu v8 검증과 근거 출처

2026-10-04 상위 작업이 Mac executor를 통해 확인한 서버 결과를 반영했다. 검증 대상은 Library checkpoint **v8**, 1,116,597 bytes, SHA256 `896e553ce6791fad8c02a7f4bdafdb1b87bb601d83940b86218f6528d509315d`다. base/main은 위 `24692d6`이며 source/doc 142개를 담은 commit 전 작업 트리다.

- Ubuntu 26.04.1·GCC 15.2·Boost 1.83·Thrift/fb303 0.25.0의 새 clean build **5.972초**, 실제 `scribed --help` exit 0
- 전체 suite **89 통과, 실패 0, skip 0, 20.857초**
- 동일 TCP 10개 × 5회 **50회 통과**. 이 반복을 전체 suite의 고유 시험 수에 더하지 않음
- kernel 관측 listener 50개 모두 **127.0.0.1**, 소유한 자식 55개 모두 회수, 남은 시험 PID·listener 없음
- source/doc 142개, 기존 v4/v5와 evidence, dpkg/APT 상태 및 boot ID 불변. Mac main `24692d6`도 clean 유지

**이 기록은 상위 작업이 검증한 요약 보고다. 이 클라우드에서 새 서버 raw files를 수신하거나 직접 읽지는 않았다.** Mac의 `ubuntu-results/records/ubuntu-loopback-results.json`, `project-89-tests.log`, `tcp-process-observations.json`과 evidence tar 33,972 bytes·SHA256 `cc9535a08c475735f9b4277745abd283d744ab7cc5d373bcff6efd4827639cf2`가 보고된 근거다. 이 새 tar/raw logs는 현재 checkpoint에 포함하지 않고, 요약과 보고된 식별 정보만 보존한다. 이전 단계의 raw logs와 구분한다.

후속 checkpoint는 이 결과를 문서·evidence에 기록하는 변경뿐이며 구현·시험 bytes와 mode는 실제 검증한 v8과 동일하다. 문서 갱신본 archive 전체를 서버에서 다시 실행했다고 주장하지 않는다. clean build·help 성공 및 test-only loopback 시험은 production main/startServer의 listener 기동, 전체 legacy/회사 동등성, 성능·durability 검증으로 확대하지 않는다.

## Loopback과 production daemon의 차이

`test/cpp/loopback_rpc.h`는 변경하지 않은 handler, generated processor와 native `TNonblockingServer`를 사용하되 transport를 `TNonblockingServerSocket("127.0.0.1", 0)`으로 직접 구성한다. OS가 정한 port를 `preServe` 시점에 조회하고 실제 `getsockname`의 IPv4 주소가 127.0.0.1인지, port가 `getListenPort()`와 같은지 확인한 뒤 READY를 출력한다. 먼저 port를 골라 닫고 다시 여는 경합 방식은 쓰지 않는다. 환경변수나 외부 입력으로 bind 주소를 바꾸지 않는다.

handler config의 양수 port는 기존 초기화 조건을 만족하기 위한 값이며, fixture의 실제 port는 별도다. 현재 production main→handler 초기화→`scribe::startServer`의 port-only wildcard listener 기동 경로는 **실행하지 않았다**. 기존 실제 `scribed --help` smoke는 전체 suite에서 다시 실행했다. production bind 정책에 옵션·hook·정책 변경을 추가하지 않는다. 실제 RPC/worker 동작과 production startup 경계의 미검증 범위를 구분한다.

ThreadManager의 현재 1-thread/no-manager와 3-thread/manager 구성 분기를 시험한다. 이는 선택한 두 구성의 동작 확인이며 동시 부하·성능·자원 동등성 검증은 아니다. max_conn 설정 전달 코드는 재사용하지만 overload 동작 자체는 이번 시험 범위가 아니다.

## TCP 계약 10개

1. 1/3 worker 구성에서 NUL·비UTF-8·개행을 가진 Log의 OK, 빈 batch, 빈/미등록 category discard, fb303 getName/getVersion/getStatus/getStatusDetails/getCounter(s), 정상 shutdown 후 실제 파일 bytes
2. header와 body를 나눠 send하고 완전한 frame 전 응답이 없음을 관찰한 뒤 정상 처리. TCP packet 분할 방식이나 개별 syscall 경계를 통제했다고 주장하지 않음
3. 한 send에 두 frame을 이어 넣고 같은 연결의 sequence ID·응답과 해당 입력의 파일 순서 확인. 다른 연결 사이의 전역 ordering 보장은 아님
4. versioned binary 요청을 받아도 현재 false/false factory의 non-versioned reply를 유지
5. 알 수 없는 method에 application error를 반환하고 같은 연결의 다음 유효 요청 처리
6. 불완전한 frame 도중 client가 연결을 닫아도 다른 client의 요청 처리
7. 4-byte oversized frame header만 보내 해당 연결의 EOF/RST와 다른 client 정상 처리 확인. 거대 body나 부하를 생성하지 않음
8. 실제 oneway reinitialize가 기존 store를 중지하고 새 파일 설정을 적용. 기존 loopback 연결은 유지하며 config port 변경을 production startup bind 검증으로 해석하지 않음
9. 잘못된 config에서 READY 전에 종료하고 자식 process를 회수
10. 의도적으로 client 시험이 실패했을 때 실행한 자식 PID만 terminate/필요 시 kill 후 wait하고 파일 descriptor 정리

Python 표준 라이브러리의 socket/struct만으로 IDL에 따른 request와 예상 reply를 독립 구성한다. generated Python client나 새 Thrift package를 설치하지 않았다. 응답 frame은 256 KiB로 제한하고 길이·field·STOP·남은 bytes를 검사한다. 요청/응답 sequence와 string bytes를 정규화하지 않는다.

## 프로세스 수명과 안전 경계

자식 하나를 직접 소유하고 spawn 뒤 readiness 대기 10초, connect/send socket timeout 최대 3초, response frame 수신 전체 3초, shutdown 전송 뒤 자식 wait 5초, 오류 정리의 terminate/kill 뒤 각 wait 2초로 제한한다. 이 값은 각 단계의 제한이며 연결·전송·응답을 합친 RPC 전체나 shutdown 전체가 3초/5초라는 뜻은 아니다. stderr는 임시 파일로 보내 pipe backpressure를 피한다. 실패 시 PID/name 검색·전역 kill을 쓰지 않는다. 새 process를 회수한 뒤 임시 디렉터리를 정리한다.

검토에서 startup 오류 뒤 stderr 수집 자체가 실패하면 cleanup을 건너뛸 수 있는 harness 경계를 찾아 보강했다. diagnostic 수집은 best-effort이며 finally에서 cleanup한다. 별도 3개 unit 시험은 (a) 진단 실패에도 terminate/wait, (b) 종료 timeout의 kill/wait, (c) 큰 응답을 body read 전에 거절하는 경계를 mock으로 확인한다. 이 mocked fallback 시험과 실제 TCP process 실패 시험을 구분한다.

정상 종료에는 실제 oneway fb303 shutdown을 사용한다. handler가 stopStores·server stop을 수행한 뒤 기존 `stopServer()`가 exit(0)한다. 건강한 선택 batch의 파일 출력·flush/close와 자식 exit는 확인했지만 C++ stack unwinding·Thrift pool/destructor 정리·누수 없음·failed queue 전체 drain·crash durability를 증명하지 않는다. ACK는 여전히 메모리 큐 수락 경로다.

## GNU --wrap 플랫폼 분류

main 인계에 포함된 이전 Mac 실행은 26개 통과, GNU `--wrap`와 Apple ld의 비호환으로 class setup error 1개, dependency skip 4개였다. Linux 74개 성공과 이를 혼합하지 않는다.

`test_mutex_compat.py`의 contention instrumentation lane을 Linux-only로 명시해 non-Linux에서는 g++ 호출 전 이유를 적고 skip한다. Linux의 실제 pthread wrapper·6개 행동 시험·assertions/NDEBUG 실행은 그대로이며 compiler 오류를 skip으로 바꾸지 않는다. 두 새 unit 시험은 Darwin 조건의 명시적 skip과 Linux compile 실패가 RuntimeError인 것을 모의로 검증한다. 이번 수정 후 Mac 전체 suite를 실제 재실행한 것은 아니다. skip은 실행 성공이 아니다.

## 재현과 근거

```sh
# 기존 승인된 process-local toolchain 적용
export THRIFT_PREFIX=/absolute/prefix/thrift-0.25.0
export FB303_PREFIX=/absolute/prefix/fb303-0.25.0
export TOOLS_PREFIX=/absolute/workspace-tools/usr
export SCRIBE_BUILD=/absolute/source-matching-configured-built-copy
python3 -B -m unittest discover -s test -p 'test_scribe_api_compat.py' -k loopback -v
python3 -B -m unittest discover -s test -p 'test_*.py' -v
git diff --check
```

prefix 부재는 명시적 skip으로 처리되며 전체 성공으로 세지 않는다. 오래된 source/object·generated code는 거절한다. 현재 production source는 이전 검증 build와 동일하여 재사용 가능하지만, source가 달라지면 먼저 다시 build해야 한다.

checkpoint에는 합성 입력 하나의 실제 request frame, 관찰한 response body·counter response body, 정상 종료 후 파일 bytes와 hash를 별도 예제로 보존한다. reply 예제는 검증한 4-byte transport header를 제거한 body임을 명시하며 complete-frame 파일로 부르지 않는다. 실제 사용자 데이터나 운영 traffic은 사용하지 않는다.

새 TCP suite의 위 Ubuntu 검증은 완료했으며, 다른 OS와 전체 daemon·old/new RPC·relay·bucket mapping·thriftfile·10 store·fault/부하 검증은 남아 있다. 이전 74개 cloud/Ubuntu 증거와 raw logs는 과거 source에 귀속하여 보존한다. 이전 reader sanitizer 결과를 새 TCP/worker 전체 sanitizer 결과로 확대하지 않는다. Thrift upstream 29개는 이번에 재실행하거나 89개에 합산하지 않았다. Gate A–D 전체는 미완료이고 후속 push/merge/deploy는 이번 완료 범위에 포함하지 않는다.
