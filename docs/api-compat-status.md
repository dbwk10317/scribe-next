# Thrift 0.25 API 이식과 실제 scribed 빌드

2026-10-04 · 아래 클라우드 측정은 base `00826b8f0ac9288944e7ae56844f926dd654f0bb`의 당시 미commit·미push 작업 트리 기준. 이후 동일 변경을 `96a7fc1868639dcf4d479c0d94ab0886fb2776d3`로 반영했으며 [Ubuntu 재검증](ubuntu-validation-20261004.md)을 완료했다.

관련 문서: [README](../README.md) · [이전 의존성/빌드 단계](build-status.md) · [manifest](build-manifest.json) · [구현 계획](implementation.ko.md)

> 이 문서는 API 이식 단계의 38개 시험과 source 상태 기록이다. 후속 일반 spool·설정 시험과 StdFile 메모리 수정은 [최신 계약 기록](contracts-status.md)을 따른다. 아래의 file.cpp qualification-only 설명과 sanitizer 미실행은 이 이전 단계 기준이다.

## 현재 결과와 범위

클라우드 Debian 13 x86_64, GCC 14.2.0, C++17, Thrift compiler/runtime 0.25.0, fb303 0.25.0, Boost 1.83.0과 libevent 2.1.13의 **기본 비-HDFS C++ lane에서 scribed clean compile/link가 성공했다**. 두 RPC는 정적 library이며 Thrift runtime은 공유 library를 링크한다. `scribed --help`는 exit 0과 기존 usage를 출력했다. 이 실행에서 기존 fd-limit 요청이 거부됐다는 경고도 기록했다. 시스템 설정은 변경하지 않았다.

프로젝트 집중 시험 결과는 아래 검증 절에 기록한다. 기존 Thrift upstream C++ 29개 통과는 이전 단계의 별도 결과이며 이번 프로젝트 시험 수에 합치지 않는다. 운영 Scribe daemon·외부 network·서버·배포는 실행하지 않았다. HDFS, FACEBOOK 비공개 lane, shared RPC/완전 정적 dependency, root 전체 make와 Python packaging, PHP suite는 아직 검증하지 않았다.

단일 lane 성공은 Gate A의 일부 근거다. 승인된 전체 platform/feature matrix가 없으므로 Gate A 전체 완료로 표시하지 않는다. Gate B–D의 old/new wire·10 store·동적 목적지·양방향 spool/relay·fault·성능·운영 동등성은 미통과다.

## 최소 코드 변경

- `env_default.h/.cpp`: 제거된 PosixThreadFactory 대신 현재 ThreadFactory를 사용하고 서버 transport 객체를 생성자에 전달. `numThriftServerThreads > 1` 분기, 요청 worker 수, start 순서, max_conn/overload 정책, false/false binary factory와 단일 I/O thread 기본값 유지
- `compat_mutex.h`: 제거된 ReadWriteMutex/RWGuard의 실제 사용 부분만 `scribe::concurrency`에 구현. 기존 POSIX 기본 rwlock, default read/명시적 write guard, recursive read와 non-atomic release→write 획득 유지. init/destroy assert와 lock 호출의 기존 POSIX 전달 정책을 유지하며 새 예외 정책을 넣지 않음
- `scribe_server`, `conf`, `conn_pool`, `dynamic_bucket_updater`: Thrift 생성 API에 전달되는 handler/processor/server/socket/transport/protocol/client 소유권만 std::shared_ptr로 이식. Boost/std 포인터를 raw pointer로 서로 감싸거나 별도 control block을 만들지 않음
- `store.cpp`, `store_queue.cpp`, `file.cpp`: C++17의 std::shared_ptr와 생긴 이름 충돌을 막기 위해 기존 포인터를 boost::shared_ptr로 한정했을 뿐. baseline과 정규화 비교해 알고리즘 차이 없음 확인. store/queue/file header와 두 IDL은 baseline bytes와 동일
- `src/Makefile.am`: `--as-needed` 환경에서 object보다 먼저 오던 Boost library가 제거돼 생긴 실제 undefined-reference를 재현. dependency library를 consumer 뒤 LDADD로 이동하고 새 header를 배포 목록에 포함

생성 코드를 손으로 수정하지 않았고 store 종류를 제외하거나 TFileTransport를 재구현하지 않았다. `TFileTransport`, `TSimpleFileTransport`와 기존 chunk/flush/event-buffer 호출은 그대로 compile된다. compile 성공은 파일 형식·flush·양방향 replay 동등성 증거가 아니다.

기존 global handler→server→processor→handler strong ownership cycle은 이번 변경 전부터 있었다. shutdown 구조나 ownership 전체를 함께 재설계하지 않았다.

## protocol 기록 정정

고정 upstream의 서버 factory, bucket mapping client와 **relay client 모두 strictRead=false/strictWrite=false를 명시한다**. `conn_pool.cpp`의 `protocol->setStrict(false, false)`가 실제 근거다. relay가 생성자 기본값에 의존한다던 이전 문서를 정정했으며 세 production 호출은 유지했다. 이는 설정 변경이 아닌 이전 정적 검토 오류 정정이다.

## 검증

최종 프로젝트 suite는 **38개 통과, skip 0**이다. 동일 명령으로 실제 재실행했으며 mutex는 각 mode를 assertions on/off로 총 12회 실행했다.

- 원본 검증기 회귀 18개, build 경계 10개, 실제 IDL 생성 1개
- 실제 POSIX mutex 시험 6개: 동시 reader, writer 배타성, recursive read, 예외 scope 해제, non-atomic read/write 전환, noncopyability. assertions on/off 각각 실행. sleep 기반 음성 판정 대신 실제 pthread contention probe 사용
- 실제 Scribe handler/생성 client/processor와 CLI 3개: 독립 조립한 framed non-strict Log request/OK response golden, NUL·비UTF-8 bytes 동일성, 빈/혼합 batch ACK, unknown/blank category counters, 선택한 fb303 method, oneway reinitialize 무응답, null worker drain·stopStores와 STOPPING의 TRY_LATER
- 실제 source clean build와 CLI help, `git diff --check`, 소스 범위 대조. 최종 binary 992,808 bytes, SHA256 `54415714f92c7f9ea0bbc42889570792e9e7da9f0fb8c2515f23a7eae9d328f2`

`test/verify_upstream_import.py`는 변경하지 않았다. 현재는 네 build 파일과 11개 C++ 경로의 의도된 content mismatch, 총 15개만 보고하며 exit 1이다. 원본 105-path PASS는 별도 clean base에서 재현한다. 새 wrapper·시험·문서는 upstream 원본에 없는 추가 경로다. 이 구분을 숨기기 위해 checker 예외를 추가하지 않는다.

재실행 시 승인된 dependency/tool prefix를 먼저 준비한다. 자동 설치하지 않는다.

```sh
export THRIFT_PREFIX=/absolute/prefix/thrift-0.25.0
export FB303_PREFIX=/absolute/prefix/fb303-0.25.0
export SCRIBE_BUILD=/absolute/isolated-scribe-build
export TOOLS_PREFIX=/absolute/workspace-tools/usr
# rootless 도구를 사용했다면 검증된 process-local toolchain 환경도 적용
python3 -B -m unittest discover -s test -p 'test_*.py' -v
sh -n bootstrap.sh
git diff --check
```

Scribe configure recipe는 manifest의 scribe_configure를 사용하며 이후 `make -C "$SCRIBE_BUILD/src" clean`과 `make -C "$SCRIBE_BUILD/src" -j2`를 실행했다. 실제 command와 초기 실패/최종 성공 log는 checkpoint에 포함한다. 의존성 caches·binaries·test keys·인증 정보는 포함하지 않는다.

## 명시적으로 남은 동등성 위험

1. Thrift 0.25의 기본 frame=16,384,000 bytes, message=104,857,600 bytes, recursion depth=64 보호 한도는 그대로다. 0.5.0 framed reader에는 같은 configurable frame ceiling이 없었으므로 큰 batch/mapping reply는 다른 결과가 가능하다. 보호를 무조건 해제하지 않는다. Scribe README는 Thrift >=0.5.0만 요구하므로 0.5.0은 역사적 비교점이지 회사의 확정 old runtime이 아니다
2. 현재 ThreadFactory의 detached=true와 worker 수는 맞지만 std::thread에는 구 PosixThreadFactory의 1 MiB stack/policy/priority 설정 API가 없다. 0.5.0은 scheduling inheritance를 명시하지 않아 실제 실행 정책도 baseline 확인이 필요하다. 메모리 footprint·scheduler·종료 동등성을 선언하지 않는다
3. 기존 pthread StoreQueue thread/join, lock 순서, 시간 단위, 메모리 ACK/재시도·spool 형식은 재설계하지 않았다. 정확한 old binary와 환경을 확보해 양방향 동작 시험을 수행해야 한다
4. PACKAGE_* 재정의, 오래된 std::strstream 등 기존 경고를 기록했으며 일괄 정리는 하지 않았다. 원본 StdFile 메모리 결함의 sanitizer 재현/수정도 별도 단계다

근거: [Thrift 0.5 mutex header](https://raw.githubusercontent.com/apache/thrift/0.5.0/lib/cpp/src/concurrency/Mutex.h), [POSIX 구현](https://raw.githubusercontent.com/apache/thrift/0.5.0/lib/cpp/src/concurrency/Mutex.cpp), [구 factory](https://raw.githubusercontent.com/apache/thrift/0.5.0/lib/cpp/src/concurrency/PosixThreadFactory.h), [현 factory](https://raw.githubusercontent.com/apache/thrift/v0.25.0/lib/cpp/src/thrift/concurrency/ThreadFactory.h), [현 input 한도](https://raw.githubusercontent.com/apache/thrift/v0.25.0/lib/cpp/src/thrift/TConfiguration.h)
