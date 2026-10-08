# 설계

공개 Facebook Scribe [`fcd294f`](https://github.com/facebookarchive/scribe/tree/fcd294faffd1e88af1643a3a8c2359c41713f7c2)를 현대 Linux에서 빌드하는 이식판의 설계다.
지키기로 한 원본 버그와 안전 수정은 [호환성 정책](compatibility-policy.md)에 있다.

## 목표

기존 구조와 외부 계약을 유지한 채 Thrift 0.25.0과 C++17로 빌드한다.
먼저 빌드와 의존성 경계만 복구하고, 동작 비교가 통과한 뒤 오래된 C++ 표현을 작은 변경으로 정리한다.
처리 구조, 저장 형식, 전달 보장, 성능 정책은 새로 설계하지 않는다.
실행 파일, 서비스, IDL namespace, 설정 key, 설치 경로의 이름은 바꾸지 않는다.
대상은 Linux x86_64다. 회사 fork·설정·성능 자료는 범위 밖이다.

## 범위와 비목표

범위는 다음과 같다.

- IDL 재생성, Thrift C++ API와 fb303 연결, autotools 의존성 탐지, 현대 컴파일러 오류의 최소 수정
- 제거된 의존 API를 같은 의미의 표준 구현으로 대체
- 소유권·잠금 표현의 제한된 정리

비목표는 다음과 같다.

- 다른 언어 재작성, 비동기 runtime 교체, thread pool 재설계, lock-free queue
- 새 store plugin 체계, 설정 언어 변경, TLS·인증
- durable ACK, exactly-once, fsync 보장
- build system 교체(CMake 전환은 하지 않았다)

UB 자체는 보존 대상이 아니다.
원본 결함 수정은 재현 시험과 외부 영향 비교를 갖춘 별도 변경으로 하고 이식 변경에 섞지 않는다.

## 보존한 구조

`if/scribe.thrift`의 서비스는 fb303 API를 상속한다.
handler는 `Log` 요청을 category별 StoreQueue로 넘긴다.
큐 worker는 batch를 store에 넘기고 실패 batch와 주기 작업을 처리한다.
store 계층은 출력, relay, buffering, 분배를 맡는다.

| 위치 | 역할 |
| --- | --- |
| `src/scribe_server.cpp` | handler, fb303, 라우팅 |
| `src/store_queue.cpp` | category별 큐와 worker |
| `src/store.cpp` | 10 store |
| `src/conf.cpp` | 설정 파서 |
| `src/env_default.cpp` | 서버 구성, 플랫폼 기능 |
| `src/conn_pool.cpp` | relay 연결 |
| `src/file.cpp` | 파일 I/O |

기존 Store factory를 쓰고 새 registry·adapter framework를 만들지 않는다.

`if/bucketupdater.thrift`의 `BucketStoreMapping.getMapping()`, `src/dynamic_bucket_updater.cpp`, `src/network_dynamic_config.cpp`도 기본 빌드에 들어간다.
이 두 번째 RPC와 동적 목적지 갱신은 정적 bucket 분배와 따로 보존한다.
공개판 `env_default.cpp`의 `getService()`는 항상 실패한다.
서비스 이름 조회를 쓰려면 그 환경의 구현이 따로 필요하다.

## 호환성 계약

### 요청과 응답

- `Log(1: list<LogEntry> messages)`를 유지한다. field 1은 category, field 2는 message, `OK=0`, `TRY_LATER=1`이다
- 두 IDL의 method, field ID, enum, requiredness, namespace, 예외, fb303 상속을 바꾸지 않는다
- category·message bytes를 UTF-8로 정규화하거나 줄바꿈을 보정하지 않는다
- framed binary를 유지한다. server factory, mapping client, relay client 모두 strictRead=false/strictWrite=false를 명시한다
- `OK`는 메모리 큐 수락이다. 빈 category나 route가 없는 category를 버려도 `OK`일 수 있다
- 한 store의 큐가 한도를 넘으면 요청과 무관한 category도 `TRY_LATER`가 될 수 있다
- 종료 중 동적 category 생성에서 일부가 큐에 들어간 뒤 `TRY_LATER`가 나올 수 있다. 재시도 중복도 원본대로다

### 큐와 시간

- 기본 `target_write_size=16384` bytes, `max_write_interval=1`초를 유지한다
- 큐 크기는 message bytes 합이다. 요청을 넣기 전 전체 category 큐를 검사해 `size > max_queue_size`면 거절한다
- 이 한도는 RSS 상한이 아니다
- 기본 `new_thread_per_category=yes`는 category마다 worker를 만든다
- mutex, condition variable, worker 수, command 순서, 실패 batch 우선, `must_succeed`, retry, `flush_streaming`, 종료 동작을 유지한다
- 시간 기준과 wakeup 의미가 바뀔 수 있어 StoreQueue의 pthread·조건 변수는 그대로 둔다
- StoreQueue의 status 조회는 원본처럼 잠그지 않는다. worker가 첫 구성·open을 마치기 전에는 빈 문자열을 돌려준다
- handler 등록 전에 파괴되는 StoreQueue는 소멸자가 worker를 멈추고 join한다. 구성·open하지 않은 store는 닫지 않는다
- 두 동작의 세부는 [정책](compatibility-policy.md#안전이식-수정)에 있다

### 저장과 라우팅

- file, buffer, network, bucket, thriftfile, null, multi, category, multifile, thriftmultifile의 10 store와 설정 이름을 유지한다
- exact·prefix·default routing, hash, bucket 경계, fan-out 순서, 파일 이름, rotation, newline, meta 출력, `_current` symlink, 상속, 기본값을 유지한다
- prefix는 정렬된 map에서 처음 일치한 항목이 이긴다. longest-prefix로 바꾸지 않는다
- `std::hash`나 filesystem 경로 정규화로 기존 결과를 대체하지 않는다
- 일반 spool은 4-byte little-endian 길이와 payload다. `write_category`면 category와 LF가 별도 frame이다
- ThriftFile은 Thrift 0.25.0 `TFileTransport`·`TSimpleFileTransport`를 그대로 쓰며 일반 spool framing과 구분한다
- ThriftFile clone 형식과 chunk 초과·empty 처리는 [정책](compatibility-policy.md)대로 원본을 따른다
- 구버전 spool을 신버전이, 신버전 spool을 구버전이 읽을 수 있어야 한다
- 같은 data·spool 경로에 두 프로세스가 동시에 쓰지 않는다. 기존 파일을 자동 변환·삭제하지 않는다
- stream flush는 fsync가 아니다. 이식은 crash durability를 더하지 않는다

### 설정과 운영

- CLI `-p`, `-c`, 위치 인자 설정 경로를 유지한다. 설정의 `port`가 `-p`보다 우선한다
- 프로세스 종료 코드와 fb303 method·counter·status·details를 유지한다
- 설정 key, 기본값, 파싱, 잘못된 값 처리, 부모 상속을 유지한다
- 현대 플랫폼에 없는 OS 기능을 만날 때만 좁은 호환 처리를 한다
- 새 설정 key는 `thrift_max_frame_size`, `thrift_max_message_size` 두 개다([통신 크기 한도](compatibility-policy.md#통신-크기-한도))

## 의존성

| 의존성 | 결정 |
| --- | --- |
| Thrift | compiler·C++ runtime 모두 0.25.0. 공식 archive와 SHA256 고정 |
| fb303 | 같은 Thrift source의 `contrib/fb303`에 프로젝트 patch 적용 |
| libevent, pthread | 배포판 것 |
| Boost | header만. scribed는 Boost 라이브러리를 링크하지 않는다 |
| build | 기존 autotools |
| HDFS | 선택 기능. 제거하지 않는다 |

Thrift 0.25.0 경계에서 정한 것은 다음과 같다.

- 두 IDL은 `cpp:pure_enums`로 생성한다. 생성 결과에 없는 빈 `*_constants.cpp`는 build 목록에서 뺐다
- `TNonblockingServer`는 port 대신 server transport 객체와 `ThreadFactory`를 받는다
- 0.25에서 사라진 Thrift `ReadWriteMutex`는 POSIX read-write lock을 감싼 좁은 wrapper(`src/compat_mutex.h`)로 대신한다. 호출 지점의 잠금 범위는 그대로다
- 기본 frame·message 한도가 원본 시절과 달라 설정으로 명시한다
- 0.9.0은 thread stack 1 MiB를 명시했지만 0.25의 `std::thread`는 OS 기본값을 쓴다. 8 MiB라고 가정하지 않는다
- timeout, NODELAY, relay 5000 ms·linger 설정은 바꾸지 않았다

자세한 의존성 준비는 [빌드](build.md)에 있다.

## 현대화 경계

2026-10-07 사용자 승인으로 아래 단계를 이 순서대로 각각 별도 PR로 진행했다.
각 단계가 지킨 기준과 완료 조건은 [AGENTS.md](../AGENTS.md#작고-검증-가능한-변경)에 있다.
확인 수치는 각 commit 메시지에 적힌 것이며 원시 결과는 저장소에 없다.
구·신 비교 case는 1·2단계 때 10개였고 3단계 때 17개였다.

| 단계 | 내용 | 상태 |
| --- | --- | --- |
| 1 | 내부 `boost::shared_ptr`/`weak_ptr`를 `std::shared_ptr`/`weak_ptr`로 | 완료(PR #55, `72212c0`). Rocky 9.8 검증기 236 tests, 구·신 10개 case |
| 2 | Boost 라이브러리 제거. `boost::filesystem`은 `std::filesystem`, `boost::split`은 같은 결과의 자체 함수 | 완료(PR #58, `1e66160`). Rocky 9.8·8.10 검증기 236 tests, 구·신 10개 case |
| 3 | store·queue·connection pool·config·bucket updater에 `ScribeContext` 주입 | 완료(PR #59, `42ef74e`). Rocky 9.8 검증기 240 tests, 구·신 17개 case |
| - | StoreQueue thread·조건 변수의 `std::thread` 전환 | 보류 |

- 3단계 뒤 전역 `g_Handler`는 Thrift 서버 구성(`main`, `scribe::createServer`)에만 남는다
- 서버 하나에 context 하나이므로 값·카운터·연결 공유 범위는 같다
- raw StoreQueue backlink의 소유권은 바꾸지 않았다. clone이 모델 queue를 가리키는 원본 문제는 [정책](compatibility-policy.md#남긴-원본-버그)의 "clone의 StoreQueue 포인터" 행에 있다
- 자체 분리 함수가 Boost 1.58·1.83의 `boost::split`과 1,921,600개 입력에서 같은 결과를 냈다는 것은 `1e66160` commit 메시지의 기록이다. 그 비교 프로그램과 결과는 저장소에 없어 다시 실행할 수 없다
- 파일 함수 실패 시 진단 로그 문구만 표준 라이브러리 표현으로 바뀔 수 있다
- GCC 8은 `std::filesystem`에 `-lstdc++fs`가 필요하며 configure가 확인해 붙인다

## 근거

- [scribe.thrift](https://github.com/facebookarchive/scribe/blob/fcd294faffd1e88af1643a3a8c2359c41713f7c2/if/scribe.thrift) · [bucketupdater.thrift](https://github.com/facebookarchive/scribe/blob/fcd294faffd1e88af1643a3a8c2359c41713f7c2/if/bucketupdater.thrift)
- [store_queue.cpp](https://github.com/facebookarchive/scribe/blob/fcd294faffd1e88af1643a3a8c2359c41713f7c2/src/store_queue.cpp) · [store.cpp](https://github.com/facebookarchive/scribe/blob/fcd294faffd1e88af1643a3a8c2359c41713f7c2/src/store.cpp) · [conf.cpp](https://github.com/facebookarchive/scribe/blob/fcd294faffd1e88af1643a3a8c2359c41713f7c2/src/conf.cpp)
- [Thrift 공식 다운로드](https://thrift.apache.org/download) · [Thrift 0.25.0 C++ 요구](https://github.com/apache/thrift/blob/27e8a425ffb498e190df3a12e239326bf5ba9ed6/lib/cpp/README.md) · [fb303 IDL](https://raw.githubusercontent.com/apache/thrift/v0.25.0/contrib/fb303/if/fb303.thrift)
