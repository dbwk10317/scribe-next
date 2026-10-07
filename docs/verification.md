# 검증

세 가지 도구로 확인한다.

| 도구 | 확인 |
| --- | --- |
| `tools/validate_linux.py` | 새 source 사본의 빌드, 전체 시험, 임시 설치, 설치된 `scribed --help` |
| `tools/daemon_differential.py`, `tools/old-lane/` | 구·신 daemon을 실제로 띄워 같은 입력의 결과 비교 |
| root `Dockerfile` | README 설치 순서와 같은 빌드, 비교용 신버전 이미지 |

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
| `tests` | `test/test_*.py` 전체. 실패·오류·건너뜀이 모두 0이고 150개 이상이어야 통과 |
| `install` | `make install DESTDIR=stage/` |
| `installed-help` | stage의 `scribed --help` |

- `--shared-rpc`는 `shared-elf`를 더해 9단계, HDFS는 `hdfs-elf`·`java-version`·`hdfs-local`을 더해 11단계다
- 실행 중 source가 바뀌거나 stage에 symlink가 있으면 실패한다
- source·생성 파일·설치 파일 manifest와 시험 수를 `validation.json`, `test-results.json`에 남긴다
- 시험에는 C++03 원본 component와의 일반 spool 교차 비교, ASan·UBSan component, loopback RPC, fb303 patch 회귀가 들어 있다
- LSan·TSan은 일부 component에서만 실행한다. 전체 daemon sanitizer 결과가 아니다

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
- `LD_PRELOAD`·`LD_AUDIT`은 거부하고 ambient `LD_LIBRARY_PATH`는 상속하지 않는다
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

### 운영 시나리오 7개

세 역할로 운영 흐름을 흉내 낸다.

- **송신측**: buffer store의 scribed다. primary는 수신측으로 보내는 unpooled network store, secondary는 spool 파일이다(`retry_interval=10`, `retry_interval_range=1`)
- **수신측**: 받은 로그를 file store(`add_newlines=0`)로 저장하는 scribed다
- **소비 클라이언트**: 수신 폴더를 읽기만 한다. 파일 목록과 크기·SHA256, `_current` 대상, 번호 순서로 이은 bytes를 본다

- **relay-stream, mixed-relay-stream**: 수신측(`category=default`, `max_size=4`)에 송신측이 `Log` 세 번을 relay한다. `fixture_00000` 5 bytes, `_00001` 10 bytes, `_00002` 1 byte가 차례로 생기고 `_current`가 마지막 파일로 옮겨 간다. 이은 내용은 보낸 순서와 같다. mixed는 구 송신 → 신 수신, 신 송신 → 구 수신이다
- **receiver-restart**: 첫 batch가 수신 파일에 보인 뒤 수신측을 fb303 `shutdown`으로 멈춘다. 송신측은 다음 batch를 spool하고(retries 1, 상태는 `ALIVE`), 같은 설정·폴더로 다시 띄운 수신측에 replay한다. 새 batch도 바로 전달되며 수신측은 같은 `_00000`에 이어 쓴다
- **receiver-crash**: receiver-restart와 같지만 수신측을 SIGKILL로 멈춘다. 송신측에서는 두 경우가 같아 보이며 기대값도 같다
- **sender-restart-spool**: 수신측 없이 송신측이 spool 17 bytes를 쓰고 정상 종료한다. spool은 지워지지 않는다. 수신측을 띄우고 같은 spool 폴더로 송신측을 다시 띄우면 이전 프로세스의 spool을 replay한 뒤 스트리밍으로 돌아간다
- **mixed-sender-restart-spool**: 위 흐름에서 spool을 쓴 쪽과 읽는 쪽의 버전을 바꾼다(수신측은 신버전). 두 버전이 서로 쓴 일반 spool 파일을 디스크에서 읽는 유일한 daemon case다
- **throttle-retry**: 수신측 `max_msg_per_second=4`, 양쪽 `target_write_size=1`이다. 한 초 안에 메시지 2·2·1개를 보내면 다섯 번째가 `TRY_LATER`와 `denied for rate` 1이 된다. 송신측은 연결을 연 채 spool하고 `retry_interval` 뒤 replay한다. 수신 파일은 다섯 개가 순서대로다

- retry는 `now - lastOpenAttempt > 10`(정수 초)이다. 마지막 실패 입력부터 8초 안에 spool 관찰과 카운터 확인이 끝나야 하며 넘으면 실패한다
- throttle-retry는 다음 초 경계 직후에 시작하고, `Z` 응답이 같은 정수 초가 아니면 실패한다
- replay·스트리밍 관찰은 각 20초 기한이다

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

- `Dockerfile.old`: digest 고정 `ubuntu:16.04`, GCC 5.4.0, Boost 1.58, libevent 2.0.21, OpenSSL 1.0.2g, autoconf 2.69, automake 1.15, libtool 2.4.6, bison 3.0.4다
- 공식 `thrift-0.9.0.tar.gz`는 `ADD --checksum`으로 SHA256 `71d129c49a2616069d9e7a93268cdba59518f77b3c41e763e09537cb3f3f0aac`를 검사한다. 같은 tar의 `contrib/fb303`을 쓴다
- 원본 변경은 `scribe-autotools.patch` 하나다. 중복 `AM_INIT_AUTOMAKE`를 `foreign -Wall 1.9.5 no-define` 한 번으로 합친다
- configure 변수 세 개를 준다. fb303 `CPPFLAGS=-I/opt/thrift-0.9.0/include`, Scribe `CPPFLAGS='-DHAVE_INTTYPES_H -DHAVE_NETINET_IN_H'`, `LIBS='-lboost_system -lboost_filesystem'`(Ubuntu `--as-needed` 때문)이다
- 실행 closure는 `/old-lane/bin/scribed`와 `/old-lane/lib`의 라이브러리 7개다. ldd·`--help`·SHA256·패키지 버전은 `/old-lane/manifest.txt`에 남긴다
- `Dockerfile.runtime`은 root `Dockerfile`로 만든 `scribe-next-modern:rocky9`에 `/old-lane`을 더한다. 구버전은 Rocky 9의 glibc·libstdc++ 위에서 돈다
- `run_differential.sh`는 기본 17개 case를 case마다 새 컨테이너(`--network none`, `--user 65534:65534`, `--cap-drop ALL`, no-new-privileges, 2 CPU, 2 GiB, 512 PIDs)에서 돌린다
- case별 `exit=0`이 통과다. performance는 case 이름을 붙여 따로 돌린다

## 비교가 증명하지 않는 것

- `OK`는 큐 수락이다. fsync, 전원 장애 durability, exactly-once를 보여 주지 않는다. SIGKILL은 첫 batch가 파일에 보인 뒤에만 보낸다
- 모든 replay는 한 번에 성공하는 `deleteOldest` 경로다. 부분 replay는 구·신이 [일부러 다르게](compatibility-policy.md#원본-오류-세-가지) 동작해 비교하지 않는다
- 반복 실패, 여러 송신측, 연결 pool 공유, `service_list`, `adaptive_backoff`, 빈 frame spool, disk full, 운영 설정·부하는 다루지 않는다
- 응답 유실, malformed frame, 큰 frame, 시간 의존 backpressure는 daemon 비교에 없다
- 구버전은 Ubuntu 16.04 전체 userland가 아니라 비교 이미지의 Rocky 시스템 라이브러리 위에서 돈다
- 각 case를 한 번씩 실행했다. 반복 통계는 없다

## 최종 재검증 (2026-10-07)

`main` `9e8d775`(현대화 3단계까지 병합) 기준이다.
WSL Rocky 9.8(GCC 11.5, 20 core), Docker 29.8에서 이전 산출물을 모두 지우고 의존성부터 다시 만들었다.
모든 수치는 이 한 번 실행의 값이다.

1. Thrift 0.25.0, Boost 1.83(C++03 기준용), patch한 fb303 0.25.0을 새 prefix에 다시 빌드
2. `tools/validate_linux.py` 실행
3. `tools/old-lane/Dockerfile.old`로 구버전 이미지 재빌드
4. README 설치 명령을 깨끗한 `ubuntu:24.04`·`rockylinux:9` 컨테이너에서 그대로 실행
5. root `Dockerfile`로 신버전 이미지, `Dockerfile.runtime`으로 비교 이미지 빌드
6. `run_differential.sh`로 기본 17개 case와 performance 실행
7. 신버전 이미지 smoke(기본 설정, `Log`, getStatus, `shutdown`)

| 항목 | 결과 |
| --- | --- |
| 검증기 | 8단계 통과, 240 tests, 실패·오류·건너뜀 0, staged scribed에 Boost 링크 없음 |
| 설치 명령 | Ubuntu 24.04(GCC 13.3.0), Rocky 9(GCC 11.5.0) 모두 `scribed --help`·`ldd` 통과, Boost 없음 |
| 구버전 이미지 | commit된 recipe로 재빌드 성공 |
| 구·신 비교 | 17개 case 모두 exit 0 |
| performance | 정확성 통과 |
| Docker smoke | 이미지 272 MB, `STATUS: ALIVE`, `Log` 응답 `OK`, `demo-2026-10-07_00000`에 `hello docker\n\n`, `shutdown` 뒤 종료 코드 0 |

컴파일 경고 30줄은 다음과 같다.

- Thrift `config.h`의 `PACKAGE_VERSION`·`PACKAGE_STRING` 재정의 26줄
- `build_py: byte-compiling is disabled` 1줄
- `BufferStore::setNewRetryInterval`의 sign-compare 2줄
- `StoreQueue::getStatus` guard의 ignored-attributes 1줄

| 지표 | 구버전 | 신버전 |
| --- | --- | --- |
| ACK 처리량 (msg/s) | 1,414,109 | 1,297,960 |
| ACK payload (MiB/s) | 1,381 | 1,268 |
| 파일 기록 완료 (MiB/s) | 957 | 895 |
| batch 지연 p95 (ms) | 1.24 | 1.21 |
| daemon CPU (s) | 0.04 | 0.04 |
| 최대 메모리 VmHWM (MiB) | 23.5 | 21.1 |

신버전 ACK 처리량은 구버전의 0.918배다.
원시 결과는 저장소 밖 WSL home에 두고 저장소에 넣지 않았다.

## 확인한 것과 하지 않은 것

확인한 것은 다음과 같다.

- 2026-10-07 최종 `main`의 검증기 240 tests, 구·신 비교 17개 case, performance, 설치 순서 두 컨테이너, Docker 이미지
- 2026-10-05~06 서버에서 Ubuntu 16.04 전체 userland 위 구버전으로 file부터 mapping까지 9개 case와 performance 실행
- Rocky 8.10·9.8, Debian 13, Ubuntu 26.04.1의 빌드·시험(범위와 날짜는 [빌드](build.md#확인한-환경))
- HDFS local JNI와 single-DataNode([HDFS](hdfs.md))

하지 않은 것은 다음과 같다.

- 최종 `main`의 HDFS lane, Rocky 9 RPM, Rocky 8.10·Debian 13·Ubuntu 26.04.1 재검증
- GCC 14·15에서의 현대화 단계
- 반복 실행으로 보는 불안정성 통계
- 부분 replay의 구·신 비교(의도적으로 다름)
- 운영 설정·부하, 장기 운영, 상세 성능 비교
