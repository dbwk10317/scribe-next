# 일반 spool·설정 계약과 StdFile 메모리 수정

2026-10-04 · base `75c36bfe6472cdf238c18d1dcc53e91a44a5d832` · 아래 측정은 당시 미commit·미push 후속 작업 트리 기준. 현재 반영 상태는 Git 이력과 인계 manifest를 따른다.

관련 문서: [README](../README.md) · [계약 manifest](contracts-manifest.json) · [이전 API 이식](api-compat-status.md) · [이전 Ubuntu 검증](ubuntu-validation-20261004.md)

> 이 문서는 이전 55개 단계의 측정 기록이다. main 반영 후 추가한 실제 FileStore 통합·기존 손실 경로는 [후속 기록](filestore-contracts-status.md)을 따른다.

## 결과와 구분

이번 단계의 production 변경은 `src/file.cpp` 소멸자의 **delete[] → free 한 곳**이다. `readNext()`의 malloc 할당과 맞추며 주위 동작·프레임·오류 처리·큐·store 알고리즘을 바꾸지 않았다. 원본의 정상 3-byte frame 읽기 뒤 소멸에서 AddressSanitizer의 alloc-dealloc-mismatch를 재현했고, 수정 후 같은 출력과 정상 소멸을 확인했다.

현재 클라우드 Debian 13·GCC 14.2·Boost 1.83·Thrift 0.25의 기존 도구만 사용했다. 새 source copy의 기본 비-HDFS C++ configure/clean compile/link가 성공했다. 프로젝트 전체 시험은 **55개 통과, skip 0**: 이전 38 + 설정/라우팅 8 + ordinary spool 9다. 설정 fixture의 기존 3개를 포함한 집중 실행은 11개다. 동시성 시험의 12회 assertions/NDEBUG 실행을 별도 test 수로 중복 계산하지 않는다.

후속 Ubuntu 26.04.1·GCC 15.2·Boost 1.83·Thrift/fb303 0.25.0 검증에서도 동일 구현의 clean C++17 비-HDFS build·CLI help와 **55개 시험, skip 0**이 통과했다. 아래 서버 기록은 담당 작업의 결과를 상위 작업에서 확인한 보고이며, 이 클라우드 작업에서 서버 raw log를 직접 열람한 결과는 아니다. Thrift upstream 29개 성공은 이전 `96a7fc1` 단계의 별도 기록이며 이번 55개에 합산하거나 재실행한 것으로 쓰지 않는다. 이번 갱신은 문서·검증 기록만 바꾸며 구현·시험 코드를 바꾸지 않는다.

## Ubuntu 후속 검증 2026-10-04

검증 대상은 `scribe-next-contracts-20261004.tar.gz`의 Library 버전 1, SHA256 `20e61f4b78d64a0fc2606a0af5afd67a515c528b398259b94e6ff76c25f55dbc`다. base는 `75c36bfe6472cdf238c18d1dcc53e91a44a5d832`이며 당시 미commit 작업 트리를 검증했다.

| 항목 | 상위 작업에서 확인한 서버 실행 보고 |
| --- | --- |
| 환경 | Ubuntu 26.04.1, GCC 15.2, Boost 1.83, Thrift compiler/runtime·fb303 0.25.0 |
| build | clean C++17 기본 비-HDFS compile/link 및 CLI help 성공 |
| 프로젝트 suite | 55개 통과, skip 0, 20.210초. ordinary spool 9개와 신규 config/routing 8개 포함 |
| 원본 오류 재현 | malloc/delete[] alloc-dealloc-mismatch, exit 1 |
| 수정본 address/undefined 검사 | ASan·UBSan exit 0, 원본과 읽은 stdout 동일 |
| LSan 양성 대조 | 의도한 37-byte 누수를 37 bytes로 검출, exit 1 |
| LSan 활성 spool 검증 | `detect_leaks=1` 상태에서 ordinary spool 9개 통과, skip 0 |
| 보존 확인 | 검증한 131개 source/doc 파일 변경 없음, dpkg/APT 상태 변경 없음, 추가 설치·push 없음 |

서버의 LSan 성공은 제한된 instrumented StdFile reader fixture 범위다. 전체 daemon·thread·의존성이 leak-free라는 결과가 아니며, 아래 클라우드 ptrace 제약을 소급해서 해결한 것도 아니다. 같은 9개를 LSan 활성 상태로 다시 실행한 결과는 suite 55개에 더하지 않는다.

근거 수준은 **상위 작업이 확인해 전달한 서버 결과 요약**이다. 별도 서버 log tar는 16,198 bytes, SHA256 `330ed75bbb79b651dea3cf125d89fc394b31473a38612ae301c2d15208822860`로 보고됐지만 이번 클라우드 checkpoint로 가져오거나 내용·해시를 직접 검증하지 않았다. 이 값은 전달된 식별 metadata이며 raw log 근거를 보유했다는 뜻이 아니다. 상세 서버 명령·binary hash·추가 timing을 추정하지 않는다.

이번 결과 기록 후에는 문서와 manifest/복원 안내만 달라진다. 구현·시험 bytes는 검증한 버전 1과 같지만, 갱신된 archive 전체를 서버에서 다시 실행한 것으로 주장하지 않는다. 후속 commit/push와 Gate A–D 전체 완료는 별도다.

## 실제 baseline과 비교의 한계

ordinary spool 시험은 고정 공개 SHA `fcd294faffd1e88af1643a3a8c2359c41713f7c2`의 `file.cpp`, `file.h`, `HdfsFile.h`를 로컬 Git object에서 원문 그대로 꺼낸다. Git replacement와 lazy fetch를 끄고 network fetch를 하지 않는다. baseline 세 파일에 패치를 적용하지 않으며 C++03으로 빌드한다. 현재 소스는 C++17로 빌드한다. 둘 다 같은 승인 Boost 1.83과 C++ file stream을 사용한다.

양쪽의 test-only `common.h`는 필요한 include와 no-op 진단 함수만 제공한다. Thrift/server 선언·실제 logger는 포함하지 않는다. 따라서 **공개 원본 StdFile component 대 현재 StdFile의 양방향 format/reader 비교**이며 구 Thrift runtime·구 Scribe daemon·회사 환경의 old/new 검증은 아니다. 전체 구 바이너리는 아직 없다. 소스 식별 hash와 명령은 manifest에 둔다.

legacy 기능 비교에서는 파일을 close하고 결과를 flush한 뒤 `_exit(0)`으로 process를 끝내 원본 소멸자의 이미 확인된 미정의 동작과 format 관찰을 분리한다. 이 종료 방식은 baseline 기능 fixture에만 쓰며 현재 reader는 정상 소멸한다. 별도 sanitizer 시험은 baseline도 정상 소멸시켜 **원래 실패가 실제로 발생해야** 통과한다. 실패를 숨기거나 allocation 검사를 끄지 않는다.

## ordinary spool 9개 계약

- 길이는 4-byte little-endian. 0, 1, 255, 256, 65536, 0x01020304, UINT32_MAX의 header를 독립 `struct.pack('<I', ...)`와 대조. 큰 숫자는 header만 생성하고 그 크기를 할당하지 않음
- NUL·비UTF-8·개행이 있는 category 모양 frame과 payload frame을 각각 기록. 원본 writer→현재 reader 및 현재 writer→원본 reader 모두 일치하고 전체 파일 bytes도 독립 golden과 일치
- openWrite의 append가 기존 frame 뒤에 붙는 결과 확인. writer가 같은 파일을 동시에 쓰지 않음
- empty 및 1–3-byte 잘린 header는 0을 반환하고 출력 문자열을 그대로 둠
- zero frame은 0을 반환. 호출자가 명시적으로 readNext를 다시 부르면 뒤 frame을 읽을 수 있으나, 일반 replay의 0 종료를 바꾸지 않음
- 잘린 payload는 이전 output을 유지. 단독 6-byte 파일은 -6, 정상 7-byte frame 뒤 잘린 6-byte가 있으면 -13을 반환하는 기존 손실 계산을 보존
- INT_MAX 길이 거절은 header 뒤 tail이 없으면 0, 3-byte tail이 있으면 -3. 0을 항상 정상 EOF 증거로 해석하지 않음. 다른 거대/손상 길이를 모두 검증한 것은 아님
- 65535/65536/65537와 1,048,577-byte payload로 초기 버퍼·확장·큰 버퍼 즉시 해제 경계를 확인. 최대 StdFile inputBuffer 할당은 약 1.1 MiB로 제한 (hex 출력·비교 문자열의 메모리는 별도)
- 별도의 ASan 원본 실패/현재 성공 및 읽은 bytes 일치 회귀

이는 `StdFile` frame component 범위다. 실제 `FileStore::writeMessages/readOldest`의 write_category/add_newlines 조합·rotation·symlink·failure/retry·writer crash까지 통과했다는 뜻은 아니다. thriftfile의 `TFileTransport` 형식은 전혀 다른 검증 항목이며 이번 시험에 포함하지 않았다.

## sanitizer 결과와 환경 제약

실제 production include 경로로 컴파일한 작은 재현기와 격리 component fixture 모두 malloc/delete[] 불일치를 확인했다. `free()` 수정 뒤 AddressSanitizer의 allocation/bounds 검사와 UndefinedBehaviorSanitizer가 통과했다. 모든 reader 입력 fixture를 현재 sanitizer reader로도 실행한다.

LeakSanitizer는 이 클라우드 실행 환경에서 ptrace 호환 불가 fatal error를 내므로 별도 미검증이다. 최종 시험은 `ASAN_OPTIONS=halt_on_error=1:alloc_dealloc_mismatch=1:detect_leaks=0`, `UBSAN_OPTIONS=halt_on_error=1:print_stacktrace=1`을 사용한다. leak 검사 제외를 숨기지 않으며 allocation mismatch는 계속 켜 둔다. 최초 LSan 환경 실패와 최종 address/undefined 검사를 log로 구분했다. 이 클라우드 결과는 전체 daemon·의존성·thread에 대한 sanitizer 또는 leak-free 보장이 아니다. 별도 Ubuntu 서버에서는 위 양성 대조와 제한된 reader의 LSan 활성 검증을 통과했다.

## 설정·라우팅 8개 계약

실제 현재 `StoreConf`, handler와 null-store worker를 사용한다. source-copy/생성물 일치·object freshness를 확인한 기존 memory-only fixture를 확장했다. 별도 old-runtime 실행이 없는 **독립 예상값 기반 현재 계약 시험**이다.

- 공백/tab trim, inline # comment, CR byte 보존, 마지막 중복 값, 빈 key/value, 누락 getter의 output 불변
- int/unsigned의 base-0 hex·octal, unsigned-long-long의 decimal, 부분 숫자와 garbage 입력을 허용하는 기존 변환
- nested store, getAllStores append 및 map lexical 순서 (`store10`이 `store2`보다 앞), 독립 serialization golden
- 명시적 parent 설정, `type::key` 상속·global fallback, 직접 값/빈 값 우선, type/category/categories의 비상속
- 잘못된/불일치/닫히지 않은 tag와 duplicate 처리의 기존 permissiveness, parse 재사용 시 merge, missing-file 예외
- constructor port와 config port 우선순위, worker/queue/max_conn 기본값·override. `main` 전체 CLI parsing 시험은 아님
- 잘못된 설정의 WARNING/no-store 상태에서도 route 없는 메시지는 OK로 discard될 수 있음과 counter 확인. WARNING을 TRY_LATER로 바꾸지 않음
- exact가 prefix보다 우선, 정렬된 첫 prefix가 긴 prefix보다 먼저 선택되는 동작, default, 중복 목적지 fan-out, 메시지당 received-good 계산과 빈 category discard. routing case를 별도로 20회 연속 실행해 통과

모든 설정 key inventory, queue-limit timing, 두 RPC의 old/new wire, network relay·bucket TTL, 10 store 전체·fault·종료·성능은 아직 별도 작업이다. 기존 ACK/loss/retry 의미를 강화하거나 바꾸지 않는다. Gate A–D 전체 미완료 상태는 유지한다.

## 재실행

승인된 기존 도구·dependency prefix를 먼저 준비한다. 일반 spool 시험에는 로컬 고정 upstream object와 GCC sanitizer runtime, Boost 1.83 개발 prefix가 필요하다. C++03 baseline이 다른 Boost 버전에서도 빌드된다고 가정하지 않는다.

```sh
export THRIFT_PREFIX=/absolute/prefix/thrift-0.25.0
export FB303_PREFIX=/absolute/prefix/fb303-0.25.0
export TOOLS_PREFIX=/absolute/workspace-tools/usr
export SCRIBE_BUILD=/absolute/current-source-scribe-build
# 필요한 process-local autotools/library 환경 적용 후
python3 -B -m unittest discover -s test -p 'test_*.py' -v
sh -n bootstrap.sh
git diff --check
```

prefix가 없는 통합 시험은 명시적으로 skip하며 55개 성공으로 세지 않는다. 필요한 Git object가 없으면 baseline 시험은 실패하고 자동 획득하지 않는다. 이번 source를 독립 build copy에 넣고 기존 configure recipe로 먼저 빌드해야 API fixture의 source/freshness 검증을 통과한다.

엄격한 upstream import 검사는 기존 의도된 15개 경로 차이만 여전히 보고한다. 이번 production 수정은 이미 달라졌던 `src/file.cpp` 안이므로 경로 수는 증가하지 않는다. checker를 완화하지 않았다. 원본 import PASS와 현재 회귀·format 검증을 구분한다.
