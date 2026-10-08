# 검증

세 가지 도구로 확인한다. CI가 그중 둘을 묶어 돌린다.

| 도구 | 확인 |
| --- | --- |
| `tools/validate_linux.py` | 새 source 사본의 빌드, 전체 시험, 임시 설치, 설치된 `scribed --help` |
| `tools/daemon_differential.py`, `tools/old-lane/` | 구·신 daemon을 실제로 띄워 같은 입력의 결과 비교 |
| root `Dockerfile` | README 설치 순서를 따른 Rocky 9(digest 고정) root 빌드, 비교용 신버전 이미지 |
| `.github/workflows/validate.yml` | `docker-smoke`(root `Dockerfile` 빌드, `Log`, `docker stop` 뒤 종료 코드 0)와 `validator`(Rocky 9 검증 이미지에서 검증기). 아직 어디에서도 실행되지 않았다 |

실제 daemon 결과, component·모의 결과, 정적 검토, 미실행을 구분한다.
한 환경의 결과를 전체 호환성이나 운영 준비로 확대하지 않는다.

## 검증기 단계

준비와 변수는 [빌드](build.md#검증기)에 있다.

먼저 Git의 tracked·untracked(ignore 제외) 파일을 새 `build/`로 복사한다.
symlink·setuid 파일, Thrift 0.25.0이 아닌 compiler, 원본 Git object 누락은 거부한다.

| 단계 | 내용 |
| --- | --- |
| `configure` | `bootstrap.sh --prefix=/opt/scribe`와 prefix 경로 |
| `compiler-version`, `python-version` | 실제 compiler·Python 기록 |
| `clean`, `build` | `make clean`, `make -j2` |
| `tests` | `test/test_*.py` 전체. 실패·오류·건너뜀이 모두 0이고 230개 이상이어야 통과 |
| `install` | `make install DESTDIR=stage/` |
| `installed-help` | stage의 `scribed --help` |

- `--shared-rpc`는 `shared-elf`를 더해 9단계, HDFS는 `hdfs-elf`·`java-version`·`hdfs-local`을 더해 11단계다
- 처음 복사한 source 파일이나 Git 파일 목록(새 untracked 파일 포함)이 실행 중 바뀌거나 stage에 symlink가 있으면 실패한다
- source·생성 파일·설치 파일 manifest와 시험 수를 `validation.json`, `test-results.json`에 남긴다. 실패해도 `validation.json`에 `status: failed`와 오류를 남긴다
- `FB303_PREFIX/share/scribe-next/fb303-safety.json`은 있으면 기록하고 없으면 없다는 사실을 기록한다. 필수가 아니며 hash를 대조하지 않는다
- 시험에는 C++03 원본 component와의 일반 spool 교차 비교, ASan·UBSan component, loopback RPC, fb303 patch 회귀가 들어 있다
- LSan은 `test/test_hdfs_compat.py`의 component 하나에서만 켠다(`detect_leaks=1`). `test/test_ordinary_spool.py`의 ASan은 `detect_leaks=0`이다
- TSan은 어디에서도 실행하지 않는다. 전체 daemon sanitizer 결과가 아니다. 리뷰 수정과 함께 더한 store 시험도 ASan 아래에서 돌지 않는다(sanitizer 범위는 그대로)
- 신호 정지(SIGTERM·SIGINT 뒤 종료 코드 0)와 port 사용 중 종료 코드 1은 `test/test_scribe_api_compat.py`가 이번에 빌드한 실제 scribed로 확인한다. 설치본이나 Docker 이미지가 아니다. 같은 fixture는 `pthread_create`를 한 번 실패하게 감싸 동적 category 큐 생성 실패(`TRY_LATER`, `denied for store creation`, 모델 둘 중 둘째 실패 때 등록 되돌림)를 본다
- packaging 시험은 `SCRIBE_BUILD`의 임시 사본에서 install·uninstall을 돌린다
- 253개 중 약 108개는 scribed가 아니라 harness·검증 도구를 확인한다. daemon 수준의 근거는 구·신 비교 case와, scribed source로 만든 fixture 프로그램을 돌리는 시험이다
- 검증기 밖에서 `python3 -m unittest discover test`를 실행하면 준비된 prefix가 없는 module 대부분을 조용히 건너뛴다. 의미 있는 실행이 아니다
- 원본에서 물려받은 PHP 시험(`test/*.php`, `test/600buckets`, `test/simulatebackoff`, `test/resultChecker`)은 지금 상태로 실행할 수 없고 검증에 들어 있지 않다

## 구·신 daemon 비교

구버전은 공개 원본 `fcd294f`를 Thrift/fb303 0.9.0으로 빌드한 것이고, 신버전은 이 저장소의 빌드다.

- 두 lane을 별도 출력 폴더에서 순서대로 실행한다. 같은 폴더에 동시에 쓰지 않는다
- 요청 bytes, 응답 bytes와 값, 카운터, 파일 bytes, symlink, 종료 코드를 source에서 정한 기대값과 상대 lane에 비교한다
- payload·파일 이름·routing은 정규화하지 않는다. 폴더 나열 순서만 정렬한다
- 파일 관찰은 기한 있는 read-only poll이다. 입력이나 RPC를 더하지 않으며 timeout은 실패다
- 실패한 lane, 누락·손상된 evidence는 통과시키지 않는다

### 격리 요건

harness는 Docker, namespace, 권한, 의존성을 설정하지 않는다.
이미 격리한 환경에서 실행하며 다음을 확인한다.

- real·effective UID 65534, `/sys/class/net`에 `lo`만 있음, 출력은 checkout 밖 새 폴더, 쓸 port가 비어 있음
- client는 127.0.0.1에만 연결한다. 첫 RPC 전에 연결 socket inode가 소유한 child의 fd인지 확인한다
- child는 독립 session으로 띄우고, 실패하면 그 process group만 TERM·KILL하고 회수한다
- targets JSON 환경에 `LD_PRELOAD`·`LD_AUDIT`이 있으면 거부한다. 상속된 두 값과 ambient `LD_LIBRARY_PATH`는 child 환경에서 지운다
- host network, privileged, Docker socket mount로 guard를 통과시키지 않는다

### 실행

targets JSON은 lane마다 절대 경로 argv와 명시 환경을 준다.
harness가 `-c`와 새 설정을 붙인다.

```json
{
  "old": {"command": ["/old-lane/bin/scribed"], "environment": {"LD_LIBRARY_PATH": "/old-lane/lib"}},
  "modern": {"command": ["/usr/local/bin/scribed"], "environment": {}}
}
```

```sh
python3 -B tools/daemon_differential.py --run-isolated-daemons \
  --targets /prepared/targets.json --output /prepared/new-output --case <case> [--port <base>]
```

`--case` 기본값은 `file`이다.
spool·mixed-spool·game-profile·시나리오 case는 `--port`와 `--port+1`, mapping은 `--port`~`--port+3`을 쓴다.

## case

### 원본 계약 10개

- **file**: 정상 3개(NUL·LF·non-UTF-8·빈 payload 포함), 빈 `Log`, 빈 category, 미정의 category, getName·status·details·counters·version, oneway `shutdown`을 보낸다. 파일 9 bytes `4100420aff7461696c`와 `fixture_current`를 비교한다
- **stores**: null discard(ignored 3), multi fan-out(`report_success=all`, 두 file child와 null child), `categories=cat*` + `type=category`(catA 5, catB 4 bytes)를 한 batch로 본다. received good 9, ignored 6, bad 1, blank 1이다. worker 쪽 ignored counter 때문에 2초 뒤 읽는다
- **rotation**: `max_size=4`, `target_write_size=1`, `rotate_period=never`다. `currentSize > max_size` 회전으로 `_00000` 5 bytes, `_00001` 4 bytes가 된다. oneway `reinitialize` 뒤 `Z`가 `_00001`에 이어 써지고 빈 `_00002`가 생긴다
- **restart**: 첫 child를 SIGKILL(exit -9)하고 회수한 뒤 새 child가 같은 파일을 다시 연다. 빈 counter에서 `Z`를 `_00001`에 이어 써 최종 5/5/0 bytes가 된다
- **spool**: 송신 buffer(127.0.0.1 network primary, std file secondary)는 수신측 없이 spool 17 bytes `050000004100420aff040000007461696c`를 쓴다(WARNING, retries 1). 수신측을 띄우면 전체 replay 9 bytes, spool 삭제, `Z` 스트리밍 10 bytes, sent 3이다
- **mixed-spool**: spool 흐름을 구 송신 → 신 수신, 신 송신 → 구 수신으로 한다. 각 송신측은 자기가 쓴 spool을 읽는다
- **file-stores**: BucketStore(implicit `key_range` 20, bucket 2개, `remove_key`, delimiter 124), thriftfile framed·raw, multifile·thriftmultifile alias를 본다. framed event는 native uint32 길이 + payload이고 `chunk_size=16`이라 zero padding 포함 25 bytes다. 파일 9개, symlink 9개, received good 13이다. ThriftFileStore flush는 no-op이라 정상 종료 뒤에만 읽는다
- **fb303**: getOptions, 없는 getOption, NUL·0xff를 담은 setOption과 덮어쓰기, 없는 getCounter(0, key 생성 없음), getCounter·getCounters를 본다. 모르는 method의 `UNKNOWN_METHOD` exception 뒤 같은 연결로 `Log`·getStatus를 이어 간다. 요청 15, 응답 14다
- **mapping**: 직접 unpooled NetworkStore(bucket_id 1, TTL 5)다. A로 보냄 → mapping이 B로 바뀌어도 만료 전 A 유지 → 엄격 만료(`lastUpdated + ttl < now`) 뒤 B → refresh 예외에도 B 유지 → 회복 뒤 A다. A는 `413000ff` `41310a` `4132`, B는 `4230` `4231`을 받는다. bucket_id나 updater port가 없으면 warning과 static A fallback이며 mapping RPC가 없다
- **game-profile**: 게임 서버 설정 기능을 가상 설정 하나([template](../tools/daemon_game_profile.conf.template))에 모았다. prefix가 섞인 `categories=` 목록과 `type=multi` 아래 buffer 두 개, 연결 pool을 쓰는·안 쓰는 network primary와 `add_newlines=1` file secondary, `rotate_period=1h` file primary, 단독 prefix 모델, `category=default`, 줄 중간 `#` 주석, 기본 `new_thread_per_category`다. 시작 상태, batch 뒤 spool frame과 counter, 수신측 기동 뒤 replay와 spool 삭제를 비교한다. 수신 파일은 `msg\n\n`이고 빈 payload는 `0a0a`다. 파일 이름의 날짜는 TZ=UTC 실행일이며 자정을 넘기면 실패한다

### store 계약 3개 (2026-10-08)

리뷰 수정과 함께 더했다(`tools/daemon_store_case.py`). 기본 목록은 원본 계약 10개, 이 3개, 운영 시나리오 12개를 합친 25개다.

- **rotation-time**: `rotate_period=2s`(ROLL_OTHER), `check_interval=1`, `target_write_size=1`이다. `first`를 쓰고 시간 회전을 기다린 뒤 `second`를 쓴다. `fixture-<UTC 날짜>_00000`=`first`, `_00001`=`second`, `fixture_current` → `_00001`, received good 2다. 회전은 쓴 것이 없어도 주기 검사에서 시각이 `lastRollTime + 2` 이상이면 일어나므로 `second` 전에 빈 `_00001`이 먼저 생긴다. 첫 회전은 시작 뒤 1.4~2.0초에 관찰됐다. game-profile처럼 UTC 자정을 넘기면 실패한다
- **backpressure**: `max_queue_size=8`, `target_write_size=1000000`, `max_write_interval=3600`이라 큐가 빠지지 않는다. 9 bytes batch는 `OK`, 다음 `Log`는 `TRY_LATER`다. `fixture:denied for queue size` 1, `scribe_overall:denied for queue size` 1이고 거절된 메시지는 received good에 들지 않는다. 파일은 `shutdown`이 큐의 9 bytes를 flush할 때까지 비어 있다. 검사는 모든 category의 큐 payload bytes에 대한 `getSize() > max_queue_size`다
- **bucket-hash**: `key_hash`·`key_modulo` bucket store 두 개, `num_buckets=3`, `remove_key=yes`, `failure_bucket=failed`다([template](../tools/daemon_bucket_hash.conf.template)). bucket은 `djb2(key) % n + 1`이고 djb2는 h=5381, h=h*33+c mod 2^32다. x86-64의 `char`는 signed라 0x80 이상 byte는 c-256을 더한다(UTF-8 `café`는 bucket 3, unsigned였다면 1). `key_modulo`는 `atol`이라 숫자가 아닌 key `x`는 0 → bucket 1, `-1`은 2^64-1 → bucket 1이다. delimiter가 없거나 key가 비면 failure bucket이고, `remove_key`로 `|empty`는 `empty`로 저장된다. bucket 파일 8개를 구·신 bytes로 비교한다

### 운영 시나리오 12개

세 역할로 운영 흐름을 흉내 낸다.

- **송신측**: buffer store의 scribed다. primary는 수신측으로 보내는 unpooled network store, secondary는 spool 파일이다(`retry_interval=10`, `retry_interval_range=1`)
- **수신측**: 받은 로그를 file store(`add_newlines=0`)로 저장하는 scribed다
- **소비 클라이언트**: 수신 폴더를 읽기만 한다. 파일 목록과 크기·SHA256, `_current` 대상, 번호 순서로 이은 bytes를 본다

- **relay-stream, mixed-relay-stream**: 수신측(`category=default`, `max_size=4`)에 송신측이 `Log` 세 번을 relay한다. `fixture_00000` 5 bytes, `_00001` 10 bytes, `_00002` 1 byte가 차례로 생기고 `_current`가 마지막 파일로 옮겨 간다. 이은 내용은 보낸 순서와 같다. mixed는 구 송신 → 신 수신, 신 송신 → 구 수신이다
- **receiver-restart**: 첫 batch가 수신 파일에 보인 뒤 수신측을 fb303 `shutdown`으로 멈춘다. 송신측은 다음 batch를 spool하고(retries 1, 상태는 `ALIVE`), 같은 설정·폴더로 다시 띄운 수신측에 replay한다. 새 batch도 바로 전달되며 수신측은 같은 `_00000`에 이어 쓴다
- **receiver-crash**: receiver-restart와 같지만 수신측을 SIGKILL로 멈춘다. 송신측에서는 두 경우가 같아 보이며 기대값도 같다
- **receiver-stall**: 첫 batch가 수신 파일에 보인 뒤 수신측 프로세스 그룹을 SIGSTOP으로 멈춘다. 송신측은 다음 batch를 보낸 뒤 500 ms 응답 timeout으로 연결을 닫고 spool한다(retries 1, 상태는 `ALIVE`). SIGCONT 뒤 수신측은 socket 버퍼에 남은 그 batch를 기록하고, `retry_interval` 뒤 replay로 같은 batch가 한 번 더 저장된다(중복). 수신 파일은 첫 batch, 둘째 batch 두 번, `Z` 순서이고 received good 7, sent 5, retries 1이다
- **sender-restart-spool**: 수신측 없이 송신측이 spool 17 bytes를 쓰고 정상 종료한다. spool은 지워지지 않는다. 수신측을 띄우고 같은 spool 폴더로 송신측을 다시 띄우면 이전 프로세스의 spool을 replay한 뒤 스트리밍으로 돌아간다
- **mixed-sender-restart-spool**: 위 흐름에서 spool을 쓴 쪽과 읽는 쪽의 버전을 바꾼다(수신측은 신버전). 두 버전이 서로 쓴 일반 spool 파일을 디스크에서 읽는 유일한 daemon case다
- **throttle-retry**: 수신측 `max_msg_per_second=4`, 양쪽 `target_write_size=1`이다. 한 초 안에 메시지 2·2·1개를 보내면 다섯 번째가 `TRY_LATER`와 `denied for rate` 1이 된다. 송신측은 연결을 연 채 spool하고 `retry_interval` 뒤 replay한다. 수신 파일은 다섯 개가 순서대로다
- **mixed-receiver-restart, mixed-receiver-crash, mixed-receiver-stall, mixed-throttle-retry**: receiver-restart·receiver-crash·receiver-stall·throttle-retry를 구 송신 → 신 수신, 신 송신 → 구 수신으로 한다. 다시 띄운 수신측도 처음 수신측과 같은 버전이다. 기대값과 기준 시각은 바탕 case와 같다

- retry는 `now - lastOpenAttempt > 10`(정수 초)이다. 기준 시각부터 8초 안에 spool 관찰과 카운터 확인이 끝나야 하며 넘으면 실패한다
- 기준 시각은 receiver-restart·receiver-crash·receiver-stall·throttle-retry가 spool로 가는 마지막 입력을 보낸 시각, sender-restart-spool·mixed-sender-restart-spool과 spool·mixed-spool·game-profile이 송신측 daemon 시작 시각이다
- throttle-retry는 다음 초 경계 직후에 시작하고, `Z` 응답이 같은 정수 초가 아니면 실패한다
- replay·스트리밍 관찰 기한은 20초다. throttle-retry의 첫 두 스트리밍 관찰만 2초다

### performance

- 4 producer가 각각 1 KiB 메시지 4096개를 256개씩 묶어 보낸다. 먼저 256개 warm-up을 기록한다
- `num_thrift_server_threads=4`, `max_queue_size=33554432`, std FileStore `rotate_period=never`, `max_size=1000000000`이다
- old0 → modern0 → modern1 → old1 → old2 → modern2 순서로 3회씩 돌리고 중앙값을 쓴다
- ACK 처리량은 시작 gate부터 모든 batch가 `OK`일 때까지의 wall time이다. p95는 trial당 64개 batch 지연의 61번째 값이다
- 파일 기록 완료는 기대 크기가 보이는 첫 5 ms poll 관찰이다. fsync가 아니다
- daemon CPU는 `/proc/PID/stat`의 utime+stime, 메모리는 `VmHWM`이다
- 모든 `Log`는 `OK`여야 하고 재시도하지 않는다. 기록 뒤 누락·중복·변형·producer 내부 순서를 검사한다
- 합격 기준이 없는 서술적 측정이다. 구·신은 compiler·라이브러리·ABI가 달라 원인을 나누지 못한다

## 구버전 lane 재현

[tools/old-lane](../tools/old-lane/README.md)에 구버전 빌드와 비교 이미지 recipe, 세 명령이 있다.

- `Dockerfile.old`의 base는 2026-10-08에 조회한 `ubuntu:16.04` manifest-list digest(`sha256:1f1a2d56…`)로 고정한다. apt 패키지 버전은 고정하지 않는다. 그 전 실행은 `ubuntu:16.04` tag였다
- 2026-10-07 빌드 한 번에서 관찰한 버전은 GCC 5.4.0, Boost 1.58, libevent 2.0.21, OpenSSL 1.0.2g, autoconf 2.69, automake 1.15, libtool 2.4.6, bison 3.0.4다. recipe가 고정한 값이 아니다
- 공식 `thrift-0.9.0.tar.gz`는 `ADD --checksum`으로 SHA256 `71d129c49a2616069d9e7a93268cdba59518f77b3c41e763e09537cb3f3f0aac`를 검사한다. 같은 tar의 `contrib/fb303`을 쓴다
- 원본 변경은 `scribe-autotools.patch` 하나다. 중복 `AM_INIT_AUTOMAKE`를 `foreign -Wall 1.9.5 no-define` 한 번으로 합친다
- configure 변수 세 개를 준다. fb303 `CPPFLAGS=-I/opt/thrift-0.9.0/include`, Scribe `CPPFLAGS='-DHAVE_INTTYPES_H -DHAVE_NETINET_IN_H'`, `LIBS='-lboost_system -lboost_filesystem'`(Ubuntu `--as-needed` 때문)이다
- 실행 closure는 `/old-lane/bin/scribed`와 `/old-lane/lib`의 라이브러리다(위 빌드에서 7개). ldd·`--help`·SHA256·패키지 버전은 이미지 안 `/old-lane/manifest.txt`에 남기며 저장소에는 넣지 않았다
- `Dockerfile.runtime`은 root `Dockerfile` 이미지를 `scribe-next-modern:rocky9`라는 이름으로 받아 `/old-lane`을 더한다. [Docker 안내](docker.md#빌드)의 `scribe-next:local`에 이 tag를 붙여 쓴다. 구버전은 Rocky 9의 glibc·libstdc++ 위에서 돈다
- `run_differential.sh`는 기본 25개 case를 case마다 새 컨테이너(`--network none`, `--user 65534:65534`, `--cap-drop ALL`, no-new-privileges, 2 CPU, 2 GiB, 512 PIDs)에서 돌린다. 통과 판정과 결과 파일은 [old-lane 안내](../tools/old-lane/README.md)에 있다

## 비교가 증명하지 않는 것

- `OK`는 큐 수락이다. fsync, 전원 장애 durability, exactly-once를 보여 주지 않는다. SIGKILL은 첫 batch가 파일에 보인 뒤에만 보낸다
- 모든 replay는 한 번에 성공하는 `deleteOldest` 경로다. 부분 replay는 구·신이 [일부러 다르게](compatibility-policy.md#원본-오류-세-가지) 동작해 비교하지 않는다
- 신호 정지, 시작 실패의 종료 코드, `..` category도 구·신이 [일부러 다르다](compatibility-policy.md#운영-경계-2026-10-08). 구·신이 같아야 통과하는 비교로는 확인할 수 없다
- 반복 실패, 여러 송신측, 연결 pool 공유, `service_list`, `adaptive_backoff`, 빈 frame spool, disk full, 운영 설정·부하는 다루지 않는다
- receiver-stall의 응답 timeout 외의 응답 유실, malformed frame, 큰 frame, 시간 의존 backpressure는 daemon 비교에 없다
- 구버전은 Ubuntu 16.04 전체 userland가 아니라 비교 이미지의 Rocky 시스템 라이브러리 위에서 돈다
- 각 case를 한 번씩 실행했다. 반복 통계는 없다

## 이전 실행 기록 (2026-10-07 ~ 2026-10-08 `f2494d4`)

아래 세 절은 리뷰 수정(`85c24b5`·`c226849`·`ef1c137`) 전의 기록이다. 지금 코드와 다른 점은 다음과 같다.

- 그때 `examples/scribed.service`에는 fb303 `shutdown` frame을 보내고 프로세스 종료를 기다리는 Python `ExecStop`이 있었다. 기록의 `ExecStop` 확인은 그 옛 unit의 명령이다. 지금 unit에는 없고 systemd SIGTERM으로 멈춘다
- 그때 scribed는 SIGTERM을 처리하지 않았고, 시작 실패의 종료 코드는 0이었다
- 그때 root `Dockerfile`은 `rockylinux:9` tag를 쓰고 build 단계에서 CR을 지웠다. "CR 정리 확인"은 그 단계의 기록이다
- 그때 LF checkout을 얻으려고 `core.autocrlf=false`로 받았다. 지금은 `.gitattributes`가 LF를 정하므로 그 설정이 필요 없다([checkout 줄바꿈](build.md#checkout-줄바꿈))

### 최종 재검증 (2026-10-07)

아래 수치는 모두 `main` `9e8d775`(현대화 3단계까지 병합)에서 잰 한 번 실행의 값이다.
WSL Rocky 9.8(GCC 11.5, 20 core), Docker 29.8에서 이전 산출물을 모두 지우고 의존성부터 다시 만들었다.
그 뒤의 코드 변경(PR #63 `28a4d9a`, PR #65 `e4bb4cc`와 그 뒤 변경)은 이 실행으로 확인되지 않았다. 시험 수 240도 `9e8d775` 기준이다.

#### `0afe2b4`와 `acc7edd`의 재확인 (2026-10-07)

`main` `0afe2b4`와 이번 리뷰 수정 commit `acc7edd`를 같은 날 WSL Rocky 9.8의 Docker 29.8에서 다시 확인했다.
[빌드](build.md#rocky-linux-8과-9)의 recipe대로 만든 Rocky 9 검증 이미지(`rockylinux:9` digest, GCC 11.5, Thrift 0.25.0, patch한 fb303)에서, `core.autocrlf=false`로 받은 LF checkout을 `/validation-input`에 읽기 전용으로 mount해 검증기를 돌렸다.

- `0afe2b4`: 검증기 241 tests, 실패·오류·건너뜀 0, 통과. 구·신 비교와 Docker smoke는 하지 않았다
- `acc7edd`: 검증기 241 tests, 실패·오류·건너뜀 0, 통과. `fb303_safety_json`은 `present`, 파일 목록 재검사 통과. 이 실행의 패키징 시험이 `--record` 설치 기록과 `make uninstall`을 돌렸다
- `acc7edd`: [old-lane](../tools/old-lane/README.md)의 세 명령대로 구버전 이미지를 새로 만들고 17개 case를 돌려 모두 `exit=0`(performance 제외)
- `acc7edd`: 루트 `Dockerfile` 이미지 smoke — `Log` 응답 0, `demo_current` bytes `hello docker\n\n`. 그 컨테이너의 실제 scribed에 그때 unit의 `ExecStop` 명령을 실행해 `STATUS: STOPPING` 뒤 `scribe server exiting`, exit 0을 확인했다. `getStatus` 값과 port mount는 다시 보지 않았다
- 검증기 경고 목록은 `0afe2b4`·`acc7edd` 모두 0줄이었다(`9e8d775`의 30줄은 그때 환경의 값이다)

모두 한 번 실행한 값이다. 원시 결과는 저장소 밖 WSL home에 있고, 저장소 안의 근거는 이 문서와 PR 설명뿐이다. performance는 다시 재지 않았다.

원시 결과는 저장소 밖 WSL home에 두었고 저장소에 넣지 않았다.
저장소 안의 근거는 `42ef74e`(3단계, `9e8d775`와 같은 tree) commit 메시지가 적은 240 tests·실패·오류·건너뜀 0, 같은 경고 30줄, 구·신 17개 case 통과, Docker smoke 통과뿐이다.
설치 명령, performance, 이미지 크기 같은 나머지 수치는 저장소에서 다시 확인할 수 없다.

1. Thrift 0.25.0, Boost 1.83(C++03 기준용), patch한 fb303 0.25.0을 새 prefix에 다시 빌드
2. `tools/validate_linux.py` 실행
3. `tools/old-lane/Dockerfile.old`로 구버전 이미지 재빌드
4. 그때의 README(`9e8d775`, `git clone` 방식) 설치 명령을 깨끗한 `ubuntu:24.04`·`rockylinux:9` 컨테이너에서 실행. 그 README의 Ubuntu 패키지 목록에는 `curl`이 없었으며 이를 어떻게 처리했는지는 기록이 없다. 지금 README의 명령(`SCRIBE_SRC`, `curl` 추가, 기록 목록 기반 삭제)은 실행하지 않았다
5. root `Dockerfile`로 신버전 이미지, `Dockerfile.runtime`으로 비교 이미지 빌드
6. `run_differential.sh`로 기본 17개 case와 performance 실행
7. 신버전 이미지 smoke(기본 설정, `Log`, getStatus, `shutdown`)

| 항목 | 결과 |
| --- | --- |
| 검증기 | 8단계 통과, 240 tests(`9e8d775`의 시험 수), 실패·오류·건너뜀 0. Boost 링크 없음은 검증기 검사가 아니라 그 실행에서 따로 본 관찰이다 |
| 설치 명령 | Ubuntu 24.04(GCC 13.3.0), Rocky 9(GCC 11.5.0) 모두 `scribed --help`·`ldd` 통과, Boost 없음 |
| 구버전 이미지 | commit된 recipe로 재빌드 성공 |
| 구·신 비교 | 17개 case 모두 exit 0 |
| performance | 정확성 통과 |
| Docker smoke | 이미지 272 MB, `STATUS: ALIVE`, `Log` 응답 `OK`, `demo-2026-10-07_00000`에 `hello docker\n\n`, `shutdown` 뒤 종료 코드 0 |

`9e8d775` 빌드 log에서 센 경고성 출력 30줄은 다음과 같다.

- Thrift `config.h`의 `PACKAGE_VERSION`·`PACKAGE_STRING` 재정의 26줄
- `build_py: byte-compiling is disabled` 1줄. 컴파일러 경고가 아니라 검증기의 `PYTHONDONTWRITEBYTECODE`에 따른 Python 안내다
- `BufferStore::setNewRetryInterval`의 sign-compare 2줄
- `StoreQueue::getStatus` guard의 ignored-attributes 1줄. 그 guard는 `28a4d9a`에서 바뀌었고 지금 `getStatus`는 잠그지 않으므로 현재 코드에는 없는 경고다

| 지표 | 구버전 | 신버전 |
| --- | --- | --- |
| ACK 처리량 (msg/s) | 1,414,109 | 1,297,960 |
| ACK payload (MiB/s) | 1,381 | 1,268 |
| 파일 기록 완료 (MiB/s) | 957 | 895 |
| batch 지연 p95 (ms) | 1.24 | 1.21 |
| daemon CPU (s) | 0.04 | 0.04 |
| 최대 메모리 VmHWM (MiB) | 23.5 | 21.1 |

신버전 ACK 처리량은 구버전의 0.918배다.

### 재검증 (2026-10-08)

README 재작성과 함께 branch `docs/readme-rewrite-20261008`의 `f2494d4`(src는 `main` `e2fe61a`와 같고, 구·신 비교 case 5개를 더한 commit)를 WSL Rocky 9.8의 Docker 29.8에서 처음부터 다시 확인했다.
이전 이미지·clone·결과를 모두 지운 뒤 [빌드](build.md#rocky-linux-8과-9)의 recipe대로 Rocky 9 검증 이미지(`rockylinux/rockylinux@sha256:8101994…`, GCC 11.5, Thrift 0.25.0, patch한 fb303), root `Dockerfile` 이미지, [old-lane](../tools/old-lane/README.md)의 구버전 이미지와 비교 이미지를 새로 만들었다.
checkout은 `core.autocrlf=false`로 받은 LF clone이고, 비교 case의 `/validation-input`은 그 clone의 `git archive HEAD`다.
README의 [테스트 결과](../README.md#테스트-결과)는 performance 표와 시험 수 해석에 이 실행을 쓴다.

| 항목 | 결과 |
| --- | --- |
| 검증기 | 8단계 통과, 241 tests, 실패·오류·건너뜀 0, `status: passed` |
| 구·신 비교 | 기본 22개 case 모두 `exit=0`. 새 case `mixed-receiver-restart`·`mixed-receiver-crash`·`mixed-throttle-retry`·`receiver-stall`·`mixed-receiver-stall` 포함 |
| receiver-stall 관찰 | 네 lane 모두 `resumed` 단계에서 수신 파일이 첫 batch + 둘째 batch, `final_receiver`가 첫 batch + 둘째 batch 두 번 + `Z`로, 소스에서 정한 중복 기대값과 같았다 |
| performance | 정확성 통과. 아래 표 |
| Docker smoke | `Log(demo, "hello docker\n")` 응답 0, `getStatus` 2(`ALIVE`), `demo-2026-10-08_00000`에 `hello docker\n\n`, `demo_current` symlink. 컨테이너의 실제 scribed에 그때 unit의 `ExecStop` 명령을 `MAINPID=1`로 실행해 `STATUS: STOPPING` 뒤 `scribe server exiting`, 컨테이너 종료 코드 0 |

performance는 old0 → modern0 → modern1 → old1 → old2 → modern2 순서 3회의 중앙값이다.

| 지표 | 구버전 | 신버전 |
| --- | --- | --- |
| ACK 처리량 (msg/s) | 1,482,580 | 1,353,607 |
| ACK payload (MiB/s) | 1,448 | 1,322 |
| 파일 기록 완료 (MiB/s) | 989 | 925 |
| batch 지연 p95 (ms) | 1.19 | 1.46 |
| daemon CPU (s) | 0.03 | 0.04 |
| 최대 메모리 VmHWM (MiB) | 21.7 | 19.2 |

신버전 ACK 처리량은 구버전의 0.913배다(2026-10-07 `9e8d775`에서는 0.918배).
모두 한 번 실행한 값이고 원시 결과(`validation.json`, `test-results.json`, case별 `evidence/`, `comparison.json`)는 저장소 밖 WSL home에 있다.
설치·삭제 명령, systemd 아래의 실제 실행, HDFS, shared RPC, RPM은 이 실행에 없다.

## 리뷰 수정 뒤 재검증 (2026-10-08)

branch `fix/review-20261008`의 리뷰 수정(`85c24b5`·`c226849`·`ef1c137`)과 새 시험을 확인한 실행이다.
checkout은 통합 branch의 LF clone이다(`.gitattributes`로 LF이며 `core.autocrlf` 설정이 필요 없다).
WSL Rocky 9.8의 Docker 29.8에서 이미지를 모두 처음부터 다시 만들었다.
Rocky 9 digest에서 toolchain `scribe-next-rocky-toolchain:9`와 검증 이미지를, 고정한 `ubuntu:16.04` digest에서 구버전 `scribe-next-old-build:xenial`을, root `Dockerfile`에서 신버전 이미지를, 그리고 비교 이미지를 만들었다.

| 항목 | 결과 |
| --- | --- |
| 검증기 | 통합 branch 최종 commit에서 253 tests, 실패·오류·건너뜀 0, `status: passed`(241에서 12개 증가) |
| 구·신 비교 | 기본 25개 case 모두 `exit=0`. 새 case는 `rotation-time`·`backpressure`·`bucket-hash`([store 계약 3개](#store-계약-3개-2026-10-08)) |
| performance | 정확성 통과. ACK 처리량 구 1,501,101 msg/s·신 1,371,568 msg/s(0.914배), ACK payload 1,466·1,339 MiB/s, 파일 기록 완료 995·936 MiB/s, batch 지연 p95 1.25·1.35 ms, daemon CPU 0.04·0.04 s, VmHWM 20.9·21.2 MiB. 모두 3회 중앙값, 한 번의 실행 |
| Docker smoke | root `Dockerfile` 이미지. `docker stop` 뒤 `received signal 15, shutting down`, `STATUS: STOPPING`, `scribe server exiting`, 종료 코드 0, 큐에 있던 메시지가 `demo_current`에 남음. SIGINT는 `received signal 2` 뒤 종료 코드 0. port 사용 중이면 `Exception in main: Could not bind: Address already in use` 뒤 종료 코드 1 |
| 신호·종료 코드·`..` category | 검증기 안의 `test/test_scribe_api_compat.py`가 이번에 빌드한 실제 scribed로 신호 정지와 종료 코드 1을, store 시험이 `..` 거부와 `..x` 수락을 확인 |

이 실행에 없는 것: 설치·삭제 명령, systemd 아래 실제 실행, HDFS 빌드, `--shared-rpc` lane, RPM, Podman, CI workflow.

## P1·P2 수정 뒤 재검증 (2026-10-08)

branch `fix/review-p1-p2`의 commit `ab8ab27`(동적 category store 생성 실패의 `TRY_LATER` 전환과 등록 되돌림, 서버 publish를 Thrift `preServe()`로 이동)을 확인한 실행이다.
WSL Rocky 9.8의 Docker 29.8에서 toolchain·검증·구버전·신버전·비교 이미지를 모두 처음부터 다시 만들었다.

| 항목 | 결과 |
| --- | --- |
| 검증기 | `ab8ab27`에서 253 tests, 실패·오류·건너뜀 0, `status: passed`. 시험 수는 같고 `test_review_dynamic_category_queue_failure_rolls_back_and_defers`가 모델 1개·2개 subcase로 `TRY_LATER`·`denied for store creation`·등록 되돌림을 본다 |
| 구·신 비교 | 기본 25개 case 모두 `exit=0` |

이 실행에 없는 것: performance, Docker smoke, 설치·삭제 명령, systemd 아래 실제 실행, HDFS 빌드, `--shared-rpc` lane, RPM, Podman, CI workflow.
기동 직후 신호가 `preServe()` 전에 오는 창은 시험하지 않았다. 그때는 이전처럼 서버 정지를 건너뛰고 종료한다.

## 확인한 것과 하지 않은 것

확인한 것은 다음과 같다.

- `ab8ab27`의 검증기 253 tests와 구·신 비교 25개 case 모두 `exit=0`([P1·P2 수정 뒤 재검증](#p1p2-수정-뒤-재검증-2026-10-08))
- 통합 branch `fix/review-20261008` 최종 commit의 검증기 253 tests, Docker smoke(신호 정지·종료 코드 1), 구·신 비교 25개 case 모두 `exit=0`, performance 정확성 통과([리뷰 수정 뒤 재검증](#리뷰-수정-뒤-재검증-2026-10-08))
- `examples/scribed.service`의 `systemd-analyze verify`(unit 주석의 기록)
- `f2494d4`(src는 `e2fe61a`와 같음)의 검증기 241 tests, 구·신 비교 22개 case, performance, Docker smoke와 그때 unit의 `ExecStop`([재검증](#재검증-2026-10-08))
- `9e8d775`의 검증기 240 tests, 구·신 비교 17개 case, performance, 그때 README의 설치 순서 두 컨테이너, Docker 이미지
- `0afe2b4`의 검증기 241 tests; `acc7edd`의 검증기 241 tests, 구·신 비교 17개 case, Docker smoke와 그때 unit의 `ExecStop`([재확인](#0afe2b4와-acc7edd의-재확인-2026-10-07))
- 2026-10-05~06 서버에서 Ubuntu 16.04 전체 userland 위 구버전으로 file부터 mapping까지 9개 case와 performance 실행
- Rocky 8.10·9.8, Debian 13, Ubuntu 26.04.1의 빌드·시험(범위와 날짜는 [빌드](build.md#확인한-환경))
- HDFS local JNI와 single-DataNode([HDFS](hdfs.md))

하지 않은 것은 다음과 같다.

- 리뷰 수정 뒤 재검증 commit 뒤에 코드가 바뀌면 그 변경의 재검증
- `.github/workflows/validate.yml`의 두 job. 아직 어디에서도 실행되지 않았다
- 지금 README의 설치·삭제 명령. Rocky 9 삭제 확인은 저장소에 기록이 없고 Ubuntu 삭제는 하지 않았다
- `9e8d775`의 HDFS lane, Rocky 9 RPM, Rocky 8.10·Debian 13·Ubuntu 26.04.1 재검증. HDFS 빌드 규칙(`lib/native`, `JAVA_HOME`)과 `HdfsFile` 누수 수정 뒤의 HDFS 빌드
- 현대화 단계 뒤의 `--shared-rpc` lane. 마지막 실행은 2026-10-06이다([빌드](build.md#확인한-환경)). shared library의 `AM_CXXFLAGS` 수정도 이 lane으로 확인하지 않았다
- 지금 `examples/scribed.service`로 systemd 아래에서 실제 scribed를 띄운 실행. 지금 unit은 `systemd-analyze verify`만 했다. hardening(`CapabilityBoundingSet=`, `RestrictAddressFamilies`, `UMask=0027` 등)이 실제 실행과 network store 전송을 막지 않는지, Ubuntu·SELinux enforcing 환경은 보지 않았다
- 옛 unit의 `ExecStop`은 Docker 컨테이너의 실제 scribed에 대해서만 확인했고, 옛 unit 등록은 Rocky 9에서 shutdown frame을 받는 대체 listener로만 시험했다
- Podman에서의 RPM 검증 script 실행
- 설치한 Python client로 실제 `Log`를 보내는 시험
- GCC 14·15에서의 현대화 단계
- 반복 실행으로 보는 불안정성 통계
- [종료 시 exit 한 번](behaviour.md#종료할-때-exit를-한-번만) 수정의 회귀 시험
- 네트워크 중간 장애(패킷 유실·지연)의 흉내. daemon 비교의 네트워크 장애는 수신측 SIGKILL(연결 끊김)과 SIGSTOP(응답 없음)뿐이다
- 부분 replay, 신호 정지, 시작 실패 종료 코드, `..` category의 구·신 비교(의도적으로 다름)
- 원본 PHP 시험 묶음(지금 상태로 실행할 수 없음)
- 운영 설정·부하, 장기 운영, 상세 성능 비교
