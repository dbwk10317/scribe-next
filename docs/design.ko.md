# scribe-next 설계 문서

2026년 10월 4일 · 개발 및 운영 검토용 · 제안 상태

관련 문서: [세부 구현 계획](implementation.ko.md) · [저장소 안내](../README.md)

## 개요

scribe-next는 기존 Scribe의 구조와 외부 동작을 유지하면서 최신 Thrift 및 현대 Linux 환경에서 빌드할 수 있도록 이식하는 프로젝트다. 프로젝트 이름은 scribe-next로 정하되 기존 바이너리, 서비스, IDL namespace, 설정 key와 설치 경로의 이름은 호환성 검증 없이 바꾸지 않는다. 먼저 빌드와 의존성 경계만 복구하고, 동작 비교가 통과한 뒤 오래된 C++ 표현을 작은 변경으로 정리한다. 처리 구조, 저장 형식, 전달 보장, 성능 정책을 새로 설계하지 않는다.

이 문서는 공개 upstream SHA `fcd294faffd1e88af1643a3a8c2359c41713f7c2`를 기준으로 한다. 타깃 OS는 Linux로 확정됐다. 회사 fork, 실제 설정, 운영 부하, Linux 배포판과 toolchain 버전은 제공되지 않았다. 현재 목표는 공개 원본 기능 보존이며 회사 자료는 범위 밖이다. 아래 계약은 upstream 기준이고 최신 완료 범위는 [Linux/store 지원 현황](linux-build-mvp.md#공개-원본-store와-optional-지원-현황)을 따른다. 공개 소스 정적 검토와 고정 tree 도입 뒤 제한된 build/API 경계를 이식했다. Thrift/fb303 및 기본 비-HDFS C++ lane의 scribed clean compile/link가 클라우드에서 성공했다. 초기 build/API 단계에서 IDL·queue/store/spool 로직과 기존 시험 소스를 유지했으며 후속 승인된 production 수정은 단계별 기록으로 분리한다. API 시험 이력은 [API 이식 기록](api-compat-status.md), 최신 ordinary spool·설정 계약과 메모리 수정은 [계약 기록](contracts-status.md), 의존성 준비·초기 실패는 [빌드 기록](build-status.md), 도입 검증은 [출처 기록](source-status.md#첫-소스-도입-검증-2026-10-04)을 따른다. 초기 설계 이후 격리 production old/new daemon의 제한된 정상·재열기·실패 복구 대조를 진행했다. 동일 조건 성능과 전체 option matrix는 미검증이다.

## 범위와 비목표

1차 범위는 IDL 생성, Thrift C++ API 및 fb303 연결, autotools 의존성 탐지, 현대 컴파일러 오류의 최소 수정이다. 2차 범위는 소유권과 타입 표현을 현대적으로 정리하고 제거된 의존 API를 동일 의미의 호환 구현으로 대체하는 것이다.

Rust나 Go 재작성, 비동기 런타임 교체, thread pool 재설계, lock-free queue, 새로운 저장소 플러그인 체계, 설정 언어 변경, TLS나 인증 추가, durable ACK, exactly-once 보장은 범위 밖이다. 보안·데이터 손실 결함을 발견하면 별도 이슈로 기록하고 외부 계약을 바꿀 때 호환성 변경 승인을 받는다. 미정의 동작 자체를 보존 대상으로 삼지는 않는다. 원본 결함은 재현 시험과 외부 영향 비교를 갖춘 별도 수정으로 다루며 이식 변경에 숨기지 않는다.

## 기존 구조

`if/scribe.thrift`의 서비스가 fb303 운영 API를 상속하고, C++ handler가 Log 요청을 category별 StoreQueue로 전달한다. 큐 worker는 batch를 store에 넘기며 실패 메시지와 주기 작업을 처리한다. store 계층은 출력, relay, buffering 및 분배를 담당한다. 설정 파서는 `src/conf.cpp`에 있으며, 서버 구성과 플랫폼 기능은 `src/env_default.cpp`, 네트워크 연결은 `src/conn_pool.cpp`, 파일 I/O는 `src/file.cpp`에 위치한다.

이 흐름과 기존 클래스 경계를 보존한다. 현재 Store factory를 그대로 사용하고 새 registry나 adapter framework를 만들지 않는다. Thrift에 직접 닿는 선언과 생성 코드에서 필요한 타입만 우선 바꾼다.

`if/bucketupdater.thrift`의 `BucketStoreMapping.getMapping()`과 `src/dynamic_bucket_updater.cpp`, `src/network_dynamic_config.cpp`도 기본 빌드에 포함된다. 이 두 번째 RPC와 동적 목적지 갱신을 정적 bucket 분배와 별도로 보존한다. 공개판 `env_default.cpp`의 서비스 이름 조회 `getService()`는 항상 실패하므로, 회사에서 해당 기능을 사용하면 회사 환경 구현과 설정을 baseline에 포함해야 한다.

## 호환성 계약

### 요청과 응답

`Log(1: list<LogEntry> messages)`를 유지한다. LogEntry의 field 1은 category 문자열, field 2는 message 문자열이며 enum 값은 OK=0, TRY_LATER=1이다. namespace, field ID, requiredness, method 이름, fb303 상속과 예외 표현을 임의 변경하지 않는다. 문자열은 기존 byte sequence를 보존하며 UTF-8 정규화나 newline 보정을 하지 않는다.

네트워크는 framed binary를 유지한다. `env_default.cpp`의 서버 factory와 `dynamic_bucket_updater.cpp`의 mapping client는 strictRead=false/strictWrite=false를 명시한다. `conn_pool.cpp`의 relay client도 `setStrict(false, false)`를 명시하므로 그대로 유지한다. relay가 기본값에 의존한다던 이전 정적 검토는 고정 source 대조로 정정했다. old client → new server, new client → old server 및 old/new relay 조합을 모두 검증한다. serializer wire 비교와 request/response 의미 비교는 함께 수행한다.

OK는 메모리 큐 수락 경로의 응답이며 영속 저장 완료가 아니다. 빈 category 및 route를 찾지 못한 category를 버려도 OK가 될 수 있다. 한 store의 큐가 제한을 초과하면 해당 요청과 무관한 category도 TRY_LATER가 될 수 있다. 종료 중 동적 category 생성 경로에서 일부 메시지가 이미 큐에 들어간 뒤 TRY_LATER가 반환될 가능성과 재시도 중복을 보존한다. 성공을 원자적 durable transaction으로 설명하지 않는다.

### 큐와 시간

기본 target_write_size=16384 bytes, max_write_interval=1초를 유지한다. 큐 크기는 message bytes 기준인 현재 계산을 동결한다. 기존 큐, mutex, condition variable, worker 수, command 처리 순서, 실패 batch 우선 처리, must_succeed, retry, flush_streaming 및 종료 동작을 초기 단계에서 유지한다. chrono 또는 std::thread 도입은 시간 기준과 wakeup 의미를 바꿀 수 있으므로 빌드 복구에 필요하지 않으면 유보한다.

큐 제한은 요청을 넣기 전에 전체 category의 큐를 검사하고 `size > max_queue_size`일 때 거절한다. 경계와 같은 크기 및 한 번에 제한을 넘기는 batch를 별도 fixture로 둔다. 이 설정은 프로세스 RSS의 엄격한 상한이 아니다. 기본 `new_thread_per_category=true`에서 category가 증가하면 worker·메모리 비용도 증가하므로 category 수와 thread 수를 성능 비교에 포함한다.

### 저장과 라우팅

file, buffer, network, bucket, thriftfile, null, multi, category, multifile, thriftmultifile의 10 store와 설정 이름을 보존한다. exact category, prefix 및 default routing, hash 결과, bucket 경계, fan-out 순서, 파일명, rotation 조건, newline, meta 출력, `_current` symlink, 설정 상속 및 기본값을 계약으로 기록한다. prefix는 정렬된 map에서 처음 일치한 항목을 선택하며 longest-prefix match로 바꾸지 않는다. 동적 목적지의 TTL 만료, 갱신 실패·빈 응답·목적지 변경과 counter도 비교한다. std::hash 또는 filesystem의 경로 정규화로 기존 결과를 대체하지 않는다.

일반 replay buffer는 4 byte little-endian 길이와 payload를 사용한다. write_category 사용 시 category와 newline은 별도 프레임이다. ThriftFileStore의 transport 형식은 일반 replay framing과 구분한다. Thrift 0.25.0의 `TFileTransport`와 `TSimpleFileTransport`를 먼저 사용해 형식·flush·복구 동작을 검증한다. 호환 차이가 확인된 지점만 좁게 수정하며 통합 새 포맷을 만들지 않는다.

현재 [원본 계약 우선 정책](legacy-compatibility-policy.md)에 따라 ThriftFileStore clone은 `useSimpleFile`을 복사하지 않고 원본의 framed 형식을 유지한다. 직접 설정한 simple store의 raw 형식과 구분하며 기존 파일은 변환하지 않는다. [이전 copy 수정 기록](thriftfile-contracts-status.md)은 당시 실행 이력이다. chunk 초과·empty의 원본 처리·반환·성공 집계도 유지한다. 대표 reader 성공을 전체 old/company 양방향 호환이나 crash durability로 확대하지 않는다.

구 버전이 만든 spool을 신 버전이 읽고 신 버전 spool을 구 버전이 읽을 수 있어야 한다. 같은 spool 경로에 두 프로세스가 동시에 쓰지 않는다. 원본 stream flush는 fsync가 아니며 이번 이식은 crash durability를 추가하지 않는다. 오류와 재시도에 의한 손실·중복의 기존 가능성을 운영 설명에 남긴다.

### 설정과 운영

CLI의 -p, -c, positional config 경로, port 설정의 우선순위, 프로세스 exit 동작과 fb303 method/counter/status/details를 유지한다. 모든 설정 key와 기본값·파싱·잘못된 값 처리·부모 상속을 inventory로 만든다. 회사 서비스 등록, health check, log 수집, permission, ulimit, timezone와 locale은 제공된 운영 자료로 대조한다. 현대 플랫폼에 없는 OS 기능을 만날 때만 좁은 호환 처리를 한다.

## 의존성 전략

Thrift 0.25.0을 첫 검증 후보로 제안한다. 2026년 10월 4일 확인한 공식 다운로드 페이지는 이를 2026년 9월 30일 발표된 최신 안정판으로 표시한다. compiler와 C++ runtime은 동일 버전으로 고정하고 해시, 옵션, 생성 결과를 기록한다. upstream 최신 브랜치를 빌드 입력으로 사용하지 않는다.

Thrift v0.25.0의 commit `27e8a425ffb498e190df3a12e239326bf5ba9ed6`에서 아래 경계를 정적으로 확인했다. 이 정적 검토 자체는 compile·link 또는 runtime 호환성의 증거가 아니다. 후속 실제 dependency/부분 build 결과와 미통과 범위는 [빌드 기록](build-status.md)을 따른다.

| 경계 | 확인한 상태와 이식 방향 |
| --- | --- |
| C++ 표준·생성 옵션 | 최소 C++11, CMake 기본값 11, `cpp:pure_enums` 지원. C++17 후보와 요구 표준은 충돌하지 않음. 후속 dependency/RPC library build는 통과, 기본 비-HDFS C++ lane의 scribed compile/link 통과, 전체 matrix 미완료 |
| 파일 transport | `TFileTransport`·`TSimpleFileTransport`가 빌드 목록에 있고 `setChunkSize`·`setFlushMaxUs`·`setEventBufferSize`도 존재. 재구현보다 기존 API와 bytes 비교 우선 |
| fb303 | IDL과 C++ `FacebookBase`가 존재하며 `setServer()`는 Boost shared_ptr 사용. 현대 Thrift의 std shared_ptr 경계와 소유권을 함께 검토 |
| 서버·동시성 | `TNonblockingServer`는 port 대신 서버 transport 객체를 받음. `ThreadFactory`와 좁은 POSIX read/write wrapper로 이식. stack·limit·운영 동등성은 추가 검증 필요 |

fb303의 source 존재만으로 header/library 설치·운영 method 호환성을 선언하지 않는다. 기존 구현의 빌드 경계부터 검증하고 필요한 부분만 수정한다.

autotools, Thrift 및 libthriftnb, libevent, pthread, fb303 연결을 우선 유지한다. optional HDFS는 공개 원본의 별도 build/runtime lane에서 검증해야 하며 조용히 제거하지 않는다. Boost 의존성은 2026-10-07 승인된 현대화 2단계에서 제거했다. scribed는 Boost 라이브러리를 링크하지 않으며, 빌드할 때 Thrift 0.25.0과 그 header가 요구하는 Boost header만 필요하다([개발 지침](../AGENTS.md) 참고). CMake 전환은 의존성 이식과 행동 변경에서 분리한 후속 선택 작업이다. 기존 운영 install 경로가 동등하게 유지되어야 한다.

## 현대화 경계와 제안값

C++17을 프로젝트 표준 후보로 제안한다. C++20 이상의 기능은 현재 목표에 필요하지 않다. 대상 Thrift가 더 높은 표준을 요구하면 해당 release의 실제 build 요구를 근거로 재결정한다. Linux를 주 검증 대상으로 확정한다. 봉구서버의 Ubuntu 26.04.1에서 첫 소스 도입 검사 후 GCC 15.2·Boost 1.83·Thrift 0.25의 기본 비-HDFS C++17 clean build와 당시 계약 시험 55개를 통과했다. 후속 v8의 Ubuntu clean build·help와 89개 test-only loopback 포함 시험 결과 및 근거 출처는 [최신 loopback 기록](loopback-rpc-status.md)을 따른다. 이는 확인한 lane의 결과이며 전체 platform/feature matrix를 대신하지 않는다. 확인한 Linux/compiler lane과 미검증 optional 범위를 최신 지원 현황에 기록한다. Windows 지원 확대는 POSIX I/O와 symlink 계약을 포함하는 별도 범위다. 특정 OS·컴파일러를 최신이라고 주장하지 않는다.

shared_ptr 전환은 generated interface와 Thrift constructor boundary에서 시작한다. Boost와 std 포인터가 서로 같은 객체의 별도 control block을 만들지 않도록 소유권 연결부를 함께 수정한다. 2026-10-07 승인에 따라 내부 포인터의 std 일괄 치환과 전역 handler 의존 제거(context 주입)는 별도 PR로 진행한다([개발 지침](../AGENTS.md) 참고). raw StoreQueue backlink의 소유권 변경은 하지 않는다. 새로운 thread API를 적용할 때 현재 concurrency wrapper에 필요한 부분만 맞추고 lock 순서와 scope는 유지한다. 파일 transport는 기존 구현의 API와 byte format을 비교한 뒤 호환에 필요한 변경만 선택한다.

## 결정과 미확정 사항

확정 방향은 두 단계 이식, 기존 구조 유지, IDL 및 spool 불변, 초기 concurrency 동결, 기존 autotools 우선이다. 제안값은 C++17과 Thrift 0.25.0이다. 다음 검증은 공개 고정 baseline의 남은 store/운영 API·optional HDFS·동일 조건 workload에 집중한다. 회사 fork/config 자료를 완료 조건으로 요구하지 않는다.

성능 동등성은 같은 machine, compiler 옵션, filesystem, client, payload/category 분포, category 수, batch 크기, fan-out, 지속 시간과 장애 지속 조건에서 측정한다. throughput, latency 분포, CPU, RSS, thread 수, queue peak, retry, loss 및 recovery 시간을 비교한다. 허용 차이는 공개 원본 baseline과 명시된 사용자 승인 예외로 관리한다. 이 문서는 임의 성능 수치나 무손실을 보장하지 않는다.

## 위험과 대응

generated API 변경은 wire golden과 양방향 client 검증으로 막는다. pointer·thread API 변경은 lifetime 및 종료 경로 검증으로 막는다. filesystem 대체는 bytes, filenames와 symlink 비교로 막는다. timeout과 frame size 기본값 차이는 목표 Thrift의 실제 defaults를 조사하고 기존 효과를 명시적으로 구성해 막는다. 동시성 결함과 입력 한계가 새 컴파일러에서 드러나면 sanitizer 보고와 기존 결과를 함께 검토하며 호환성 정책 결정을 별도로 남긴다.

원본 `StdFile`의 할당·해제 불일치는 [별도 재현·최소 수정](contracts-status.md)을 완료했다. component 범위의 bytes/ASan/UBSan 및 Ubuntu reader LSan 성공과 전체 runtime·daemon 누수 검증을 구분한다. 클라우드 LSan은 ptrace 제약으로 미검증이다. 기존 PHP suite는 `make check`에 연결되어 있지 않으므로 명시적이고 격리된 실행 없이 계약 검증을 통과한 것으로 보지 않는다.

## 배포와 롤백

회사가 검증 완료를 승인한 후 별도 실행 권한으로 canary를 시작한다. 구 바이너리, 설정, 의존성 및 spool snapshot을 보존한다. replay 검증은 production spool 복사본에서 수행하고 동일 spool을 공동 사용하지 않는다. 제한된 relay 경로에서 관찰 후 비율을 올린다. 허용된 성능·오류 기준 초과, 파일 format 차이 또는 운영 API 차이를 롤백 trigger로 정한다.

롤백은 신규 트래픽 중지, 현재 프로세스 종료, spool writer가 없는지 확인, snapshot 및 잔여 spool 상태 기록, 구 버전 재기동 순서다. ACK 이후 메모리 잔여분이 durable하다고 가정하지 않는다. 기존 spool의 역호환이 검증되지 않으면 배포를 시작하지 않는다.

## 라이선스

원본 Apache License 2.0 및 copyright·attribution을 유지한다. 배포 시 LICENSE를 포함하고 NOTICE가 있으면 필요한 고지를 보존한다. 변경 파일에 변경 사실을 표시하고 의존성 라이선스 및 고지를 inventory에 포함한다. Apache 2.0은 회사 fork를 공개할 권한을 대신하지 않는다. 회사 코드 공개·배포 권한은 별도로 확인한다.

## 근거와 적용한 원칙

공개 upstream의 다음 파일을 정적으로 열람했다. 구현 단계에서는 각 계약과 실제 검증 결과를 근거 기록에 연결한다.

- [scribe.thrift](https://raw.githubusercontent.com/facebookarchive/scribe/fcd294faffd1e88af1643a3a8c2359c41713f7c2/if/scribe.thrift) · [scribe_server.cpp](https://raw.githubusercontent.com/facebookarchive/scribe/fcd294faffd1e88af1643a3a8c2359c41713f7c2/src/scribe_server.cpp)
- [store_queue.cpp](https://raw.githubusercontent.com/facebookarchive/scribe/fcd294faffd1e88af1643a3a8c2359c41713f7c2/src/store_queue.cpp) · [store.cpp](https://raw.githubusercontent.com/facebookarchive/scribe/fcd294faffd1e88af1643a3a8c2359c41713f7c2/src/store.cpp)
- [file.cpp](https://raw.githubusercontent.com/facebookarchive/scribe/fcd294faffd1e88af1643a3a8c2359c41713f7c2/src/file.cpp) · [env_default.cpp](https://raw.githubusercontent.com/facebookarchive/scribe/fcd294faffd1e88af1643a3a8c2359c41713f7c2/src/env_default.cpp)
- [conn_pool.cpp](https://raw.githubusercontent.com/facebookarchive/scribe/fcd294faffd1e88af1643a3a8c2359c41713f7c2/src/conn_pool.cpp) · [conf.cpp](https://github.com/facebookarchive/scribe/blob/fcd294faffd1e88af1643a3a8c2359c41713f7c2/src/conf.cpp)
- [configure.ac](https://raw.githubusercontent.com/facebookarchive/scribe/fcd294faffd1e88af1643a3a8c2359c41713f7c2/configure.ac) · [Thrift 공식 release 정보](https://thrift.apache.org/download)
- [Thrift v0.25.0 fb303 IDL](https://raw.githubusercontent.com/apache/thrift/v0.25.0/contrib/fb303/if/fb303.thrift) · [Apache License 2.0](https://www.apache.org/licenses/LICENSE-2.0)
- [bucketupdater.thrift](https://github.com/facebookarchive/scribe/blob/fcd294faffd1e88af1643a3a8c2359c41713f7c2/if/bucketupdater.thrift) · [dynamic_bucket_updater.cpp](https://github.com/facebookarchive/scribe/blob/fcd294faffd1e88af1643a3a8c2359c41713f7c2/src/dynamic_bucket_updater.cpp) · [network_dynamic_config.cpp](https://github.com/facebookarchive/scribe/blob/fcd294faffd1e88af1643a3a8c2359c41713f7c2/src/network_dynamic_config.cpp)
- [upstream 빌드 목록](https://github.com/facebookarchive/scribe/blob/fcd294faffd1e88af1643a3a8c2359c41713f7c2/src/Makefile.am) · [PHP 시험 실행기](https://github.com/facebookarchive/scribe/blob/fcd294faffd1e88af1643a3a8c2359c41713f7c2/test/testsuite.php) · [check-local](https://github.com/facebookarchive/scribe/blob/fcd294faffd1e88af1643a3a8c2359c41713f7c2/lib/py/Makefile.am)
- [Thrift C++ 표준 기본값](https://github.com/apache/thrift/blob/27e8a425ffb498e190df3a12e239326bf5ba9ed6/build/cmake/DefineCMakeDefaults.cmake) · [C++ 요구·API 변경](https://github.com/apache/thrift/blob/27e8a425ffb498e190df3a12e239326bf5ba9ed6/lib/cpp/README.md) · [pure_enums generator](https://github.com/apache/thrift/blob/27e8a425ffb498e190df3a12e239326bf5ba9ed6/compiler/cpp/src/thrift/generate/t_cpp_generator.cc)
- [TFileTransport](https://github.com/apache/thrift/blob/27e8a425ffb498e190df3a12e239326bf5ba9ed6/lib/cpp/src/thrift/transport/TFileTransport.h) · [Thrift C++ 빌드 목록](https://github.com/apache/thrift/blob/27e8a425ffb498e190df3a12e239326bf5ba9ed6/lib/cpp/CMakeLists.txt) · [FacebookBase](https://github.com/apache/thrift/blob/27e8a425ffb498e190df3a12e239326bf5ba9ed6/contrib/fb303/cpp/FacebookBase.h) · [TNonblockingServer](https://github.com/apache/thrift/blob/27e8a425ffb498e190df3a12e239326bf5ba9ed6/lib/cpp/src/thrift/server/TNonblockingServer.h)

karpathy-guidelines와 ponytail의 지침을 적용해 가정을 명시하고, 기존 구현을 우선 재사용하며, 필요한 경계만 수정하도록 설계했다. 각 작업은 관찰 가능한 완료 조건을 갖고, 기능을 추가하기 위한 추상화나 전면 재작성은 도입하지 않는다.
