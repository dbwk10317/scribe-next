# FileStore byte·replay 통합 계약과 기존 손실 경로

2026-10-04 · base/main `ffc73ee268a8a3430e57464f460bdf3556c983bb` · 아래 측정은 당시 미commit·미push 작업 트리의 수정 전 characterization 기준. 현재 반영 상태는 Git 이력과 인계 manifest를 따른다

관련 문서: [README](../README.md) · [manifest](filestore-contracts-manifest.json) · [이전 55개 계약·메모리 수정](contracts-status.md)

> 이 문서는 수정 전 checkpoint v4의 70개 characterization 기록이다. 사용자 승인 후 적용한 최소 수정과 74개 시험은 [후속 수정 기록](truncate-fix-status.md)을 따른다.

## 결과

**production 코드 변경 없이 프로젝트 70개 시험, skip 0을 통과했다.** 이전 55개에 실제 FileStore/BufferStore 통합 14개와 raw upstream/current StdFile `openTruncate` 비교 1개를 추가했다. 통합 fixture는 기존 실제 Scribe object·generated code·Thrift/fb303 0.25.0을 사용하며 source bytes 및 object dependency freshness 검사를 통과해야 실행된다. 새 C++ fixture는 매번 컴파일한다. 기존 cloud build의 production source가 현재 main과 동일하므로 object를 재사용했으며, 이번 단계에서 전체 scribed clean build를 다시 수행했다고 주장하지 않는다.

클라우드 Debian 13·GCC 14.2·Boost 1.83의 승인된 기존 도구만 사용했다. 파일 생성·교체·삭제는 시험별 임시 디렉터리 안에서만 수행한다. Scribe daemon·socket·실제 서비스·회사 spool을 사용하지 않는다. 설정/counter를 위한 실제 handler의 null-store worker는 초기화 후 join하고, 파일 동작은 동기적으로 직접 호출한다.

70개 통과는 **현행 동작의 명시적 관찰값과 일치**한다는 뜻이다. 아래 손실 결함을 해결했거나 원하는 동작으로 승인했다는 뜻은 아니다. 결함 수정 시 의도·전후 결과·허용 차이를 따로 검토하고 해당 회귀 예상값도 함께 갱신한다.

## 새 FileStore 통합 14개

1. 일반 출력의 `write_category`×`add_newlines` 네 조합: NUL·비UTF-8·빈 payload·기존 LF를 가진 입력의 전체 bytes와 상대 `_current` symlink
2. framed buffer의 동일 네 조합: category+LF 별도 frame과 message frame의 독립 little-endian golden 및 실제 `readOldest` 복원
3. multi-category buffer의 category 기록 강제, chunk padding·scheduled rotation 비활성화
4. close/reopen 뒤 같은 suffix에 append하고 실제 replay에서 두 메시지 유지
5. 기존 output vector 뒤에 append, category frame 미사용 시 configured fallback category 적용
6. category의 마지막 byte를 LF 검증 없이 제거하는 현행 동작; 빈 category·binary category와 message LF 보존
7. zero frame·짧은 header·orphan category에서 replay가 멈춘 뒤 delete되지만 bytes-lost가 증가하지 않는 사례
8. 정상 frame `abc` + 길이 5/body `xy`의 13-byte 파일: `abc`는 전달되지만 삭제 시 bytes-lost=13, 다음 정상 파일에서 중복 집계하지 않음
9. numeric oldest suffix 선택과 무관한 파일 보존
10. 기존 파일 `replaceOldest` 실패 반환, 원래 bytes와 요청 vector 보존, writer 재open
11. 대상 파일이 없는 read/delete/replace: read output 보존·성공, replace=false, 임의 파일 생성 없음
12. 열린 writer를 `deleteOldest`로 unlink한 뒤 isOpen=true, 후속 write=true여도 경로가 복원되지 않는 현행 동작
13. 실제 BufferStore `periodicCheck`의 성공 replay→삭제→STREAMING
14. primary가 3개 중 1개만 처리한 뒤 false를 반환하는 경우: 실제 파일 교체 실패→미처리 2개 loss 집계→삭제→DISCONNECTED

BufferStore 시험은 기존 protected primary/secondary 연결 지점을 가진 test subclass를 사용한다. primary만 성공/부분 처리를 정해진 결과로 반환하며, secondary는 실제 FileStore다. production의 periodicCheck·read·replace·delete·counter·상태 전이를 그대로 실행한다. 실제 `changeState(SENDING_BUFFER)`로 secondary를 연 시작점에서 검사하므로 연결·시간 기반 재시도 스케줄링이나 queue/ACK timing을 검증한 것은 아니다. 남은 입력을 만드는 primary 동작은 Store interface의 부분 처리 계약에 맞춘 시험 대역이다.

Python golden은 production serializer를 호출하지 않고 `struct.pack('<I', length)` 및 literal byte payload로 만든다. 입력의 LF를 제거하거나 정상화하지 않는다. `add_newlines=1`은 이미 LF로 끝나는 message에도 LF를 하나 더 붙이며 reader는 이를 제거하지 않는다. 빈 message는 옵션이 꺼지면 zero frame으로 replay를 멈추고, 켜지면 LF 한 byte로 읽힌다.

## 재현한 손실 결함과 수정 경계

### 1. app|trunc 열기 실패와 partial replay 손실

`src/file.cpp:StdFile::openTruncate`는 `out | app | trunc`를 사용한다. 기존 공개 upstream C++03 component와 현재 C++17 component를 같은 GCC 14.2/Boost 1.83로 실행한 결과, 둘 다 openTruncate=false/isOpen=false이며 기존 파일 bytes는 그대로였다. 이 시험은 원문 upstream 세 파일을 로컬 고정 Git object에서 그대로 컴파일한다. full legacy Scribe/Thrift daemon 비교가 아니다.

현재 `FileStore::replaceOldest`는 실패 뒤에도 writer를 다시 연다. `BufferStore::periodicCheck`의 부분 처리 경로는 교체 실패 시 미처리 메시지 수를 `lost`에 더하고 oldest 파일을 삭제한다. 실제 secondary 파일에 3개를 넣고 primary가 1개를 처리하도록 한 시험에서 **lost=2, retries=1, DISCONNECTED, 파일 삭제**를 재현했다. 정상 입력으로 가능한 기존 손실 경로이며 이번 현대 API 이식이 새로 만든 차이는 아니다. 회사 fork에도 같은 구현이 있는지는 미확인이다.

최소 수정 후보는 `app`만 제거하여 `out | trunc`로 여는 것이다. 성공 시 미처리 메시지를 재기록할 수 있지만 관찰되는 loss/retry 결과가 달라지므로 별도 승인·전후 시험 대상으로 둔다. 이번 characterization checkpoint에는 적용하지 않았다.

그 수정만으로 atomic replace나 durability가 생기지는 않는다. truncate 뒤 write 실패·프로세스 중단에는 기존 bytes가 이미 사라질 수 있고, BufferStore의 교체 실패 시 loss/delete 정책도 남는다. 기존 `add_newlines=1` 재기록의 추가 LF 효과도 확인해야 한다. 임시 파일/rename/fsync·장애 복구 설계는 별도 범위이며 이 한 줄 수정의 효과로 약속하지 않는다.

### 2. 열린 writer의 unlink

`deleteOldest`는 writer를 close하지 않고 pathname을 삭제한다. 같은 파일을 열어 둔 직접 FileStore 시험에서 isOpen과 후속 handleMessages가 모두 true였으나 파일 경로는 사라진 채였다. 쓰기가 unlinked inode를 향할 수 있는 별도 위험이며 위 mode 수정으로 모두 해결되지는 않는다. 현재 이 결과도 그대로 기록했으며 자동으로 close/reopen 정책을 바꾸지 않았다.

### 3. 손상·zero 입력과 accounting

zero frame/orphan category/짧은 header는 성공 종료처럼 취급되어 뒤 bytes가 전달되지 않으면서도 loss counter가 0일 수 있다. 반대로 일부 정상 entry를 읽은 뒤 잘린 payload가 있으면 전체 파일 크기가 bytes-lost로 집계될 수 있다. 기존 반환·삭제·counter 결과를 가시화했으며 이를 정확한 실제 손실량·무손실 보장으로 설명하지 않는다.

## 실행과 근거

```sh
# 기존 승인된 process-local toolchain을 적용한 뒤
export THRIFT_PREFIX=/absolute/prefix/thrift-0.25.0
export FB303_PREFIX=/absolute/prefix/fb303-0.25.0
export TOOLS_PREFIX=/absolute/workspace-tools/usr
export SCRIBE_BUILD=/absolute/source-matching-configured-built-copy
python3 -B -m unittest discover -s test -p 'test_scribe_api_compat.py' -k filestore -v
python3 -B -m unittest discover -s test -p 'test_ordinary_spool.py' -v
python3 -B -m unittest discover -s test -p 'test_*.py' -v
git diff --check
```

prefix가 없는 통합 시험은 skip이므로 70개 성공으로 세지 않는다. 고정 upstream object가 없으면 baseline 시험은 실패하며 자동 fetch하지 않는다. 파일/reader 경계의 이전 ASan·UBSan 시험은 전체 suite 안에서 재실행됐지만, 새 FileStore/BufferStore 전체 object는 sanitizer-instrumented build가 아니다. 클라우드 LSan의 ptrace 제약과 이전 Ubuntu의 제한된 reader LSan 성공은 구분한다.

이전 main 인계에는 실제 Ubuntu contracts raw logs가 포함되어 이번에 hash/size/mode를 확인해 보존했다. 이는 이전 55개 시험과 reader 9개 LSan 검증의 자료이며, **새 70개 suite를 Ubuntu에서 실행한 증거는 아니다**. 이전 contracts 문서/manifest의 당시 보고·미수신 상태는 역사 기록으로 유지한다. Thrift upstream 29개도 이번에 재실행하거나 70개에 합산하지 않았다.

이번 변경은 시험·문서만이며 IDL·queue/store/spool production source와 build 규칙은 main base와 동일하다. strict upstream 검사는 기존 15개 차이만 보고한다. 원본 import PASS와 현재 기능 회귀를 혼동하지 않는다. Gate A 전체 matrix, full old/new RPC·10 store·thriftfile·network relay·crash/retry/shutdown, 회사 성능·운영 gate는 여전히 미완료다.
