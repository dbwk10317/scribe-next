# StdFile truncate 열기 수정과 부분 replay 보존

2026-10-04 · base/main `ffc73ee268a8a3430e57464f460bdf3556c983bb` · 아래 측정은 당시 미commit·미push 작업 트리 기준. 이후 구현 `8baf6f3`·PR #1을 거쳐 main `24692d6`에 반영

관련 문서: [README](../README.md) · [수정 manifest](truncate-fix-manifest.json) · [수정 전 70개 characterization](filestore-contracts-status.md)

> 이 문서는 이전 truncate 수정·74개 검증 기록이다. main 반영 뒤 test-only TCP/worker 검증은 [최신 loopback 기록](loopback-rpc-status.md)을 따른다.

## 수정과 승인 범위

기존 손실 경로를 재현해 설명한 뒤 사용자가 이 결함에 한해 원본의 loss/retry 결과가 달라지는 수정을 승인했다. production 변경은 `src/file.cpp:StdFile::openTruncate`에서 **`out | app | trunc` → `out | trunc`** 한 곳과 변경 설명 주석뿐이다. 새 저장 형식·BufferStore 상태 전이·ACK·큐·retry 정책·newline 정규화·원자적 파일 교체를 추가하지 않았다.

수정 전 Library checkpoint v4와 별도 작업 사본을 보존했다. 그 archive SHA256은 `4c0e3ef52281a78ad4ec282200ecb17b163a793cca8d2034ebb2bf61f94c8f9e`다. 현재 결과는 그 증거와 구분되는 후속 수정본이다. 원본을 실패하는 그대로 실행하는 component 시험을 없애거나 원본 소스를 고치지 않았다.

## 실제 결과

승인된 기존 클라우드 Debian 13·GCC 14.2·Boost 1.83·Thrift/fb303 0.25.0에서 새 source copy의 기본 비-HDFS C++17 configure/clean compile/link와 `scribed --help`가 성공했다. **전체 프로젝트 74개 시험, skip 0, 30.409초**가 통과했다. help 실행에는 기존 `setrlimit` 경고가 남았지만 exit 0으로 사용법이 출력됐다. 이 경고를 해결하거나 OS limit을 바꾸지 않았다. 이전 70개에서 변경되는 예상값을 명시적으로 갱신하고, 후속 replay·개행 재적용 2개 및 직접 truncate 실패/생성 경계 2개를 추가했다.

| 관찰 | 고정 원본/수정 전 | 수정본에서 확인한 결과 |
| --- | --- | --- |
| 기존 파일의 direct openTruncate | false, bytes 유지 | true, 정상적으로 길이 0으로 truncate |
| 없는 경로의 direct openTruncate | false, 파일 없음 | true, 빈 파일 생성 가능. FileStore의 missing-oldest 검사는 계속 false이며 파일을 만들지 않음 |
| directory를 파일로 truncate | 실패 | 실패, sentinel 파일 그대로 |
| FileStore replaceOldest | false, 원래 bytes 유지 | true, oldest에 미처리 bytes만 기록, newer 파일 보존, 호출자 vector 보존 |
| 3개 중 1개만 primary 처리 | 남은 2개 교체 실패→lost=2·삭제 | 남은 2개 frame bytes 잔존, lost=0·retries=1·DISCONNECTED |
| 그 뒤 primary 정상 수락 | 수정 전 경로에서 남은 파일 소실 | 남은 2개만 다음 replay에 전달, 총 3개 수락, lost=0·STREAMING, 성공 후 파일 삭제 |

Raw upstream `fcd294faffd1e88af1643a3a8c2359c41713f7c2`의 StdFile C++03 component와 현재 C++17 component는 같은 Boost 1.83으로 비교한다. **full legacy Scribe/Thrift daemon 비교가 아니다.** FileStore/BufferStore 시험은 실제 production object를 사용하고, primary의 부분/정상 수락만 시험 대역으로 제어한다. 실제 `changeState(SENDING_BUFFER)`로 secondary를 열며 재연결 준비를 명시적으로 정한다. 연결/재시도 시간·network·queue scheduling의 실측을 주장하지 않는다.

다음 replay 전의 잔존 파일을 `remaining.bin`으로 관찰한 뒤 두 번째 전달 bytes와 누적 수락 bytes/counter/최종 file tree를 독립 예상값에 대조한다. 이 한 시나리오에서 총 3개가 중복 없이 수락됐다는 사실을 exactly-once·durable ACK·일반 장애 보장으로 확대하지 않는다.

## 수정본 v5의 Ubuntu 검증

2026-10-04 12:16 UTC의 별도 검증 보고에서 Ubuntu 26.04.1·GCC 15.2·Boost 1.83·Thrift/fb303 0.25.0의 **새 clean C++17 비-HDFS build(5.981초), CLI help, 프로젝트 74개/skip 0(20.493초)** 성공을 확인했다. 대상은 `scribe-next-truncate-fix-20261004.tar.gz` v5, 950,361 bytes, SHA256 `ef8feb42f957cb80c0b992155c58c3533c756f9ea19384dcdd13bcd5c9eb4385`다. 수정 전 v4의 70개 characterization과 구분한다.

실제 부분 replay에서 3개 중 1개 수락 후 2개가 파일에 남고, 후속 replay가 그 2개를 수락하여 총 3개·lost=0인 결과를 확인했다. 원본 component의 truncate 실패도 유지됐다. 추가 LF·write/crash·비원자적 교체·실제 교체 실패 시 lost/delete·열린 writer unlink 위험은 그대로 남으며, 이 성공으로 보장 범위를 확대하지 않는다.

- 검증한 `src/file.cpp` SHA256: `8090e835bde4bfcd0b3bf9c5a1dedcc294572eab4fb6148c8c45cc66252b8012` (현재 클라우드 bytes와 일치)
- 보고된 서버 `scribed` SHA256: `27bbdeab1c5a40398419e6d8fb58e6a44ec4090ee6206763399cbfa3fa3b5163` (클라우드 binary와 다른 환경의 산출물)
- source/doc 136개·manifest 322개 보존, v4 보존 및 dpkg/APT/boot 상태 변경 없음이 보고됨

근거는 확인된 별도 서버 실행 요약이다. raw log tar는 31,448 bytes, SHA256 `47501d46b2e228080d7e1f7c1debeac17bf5d2c3fe0a879c023ac57245a3b644`로 보고됐지만 이번 클라우드에는 가져오지 않았으며 bytes·내용·해시를 직접 검증했다고 주장하지 않는다. 자세한 서버 명령·추가 측정치를 추정하지 않는다.

이번 갱신은 문서와 검증/복원 기록만 바꾼다. 구현·시험 bytes와 mode는 서버가 검증한 v5와 동일하며, 문서를 갱신한 archive 전체를 서버에서 다시 실행한 것으로 기록하지 않는다. 후속 commit/push/merge는 아직 수행하지 않았다.

## add_newlines의 명시적 결과

`add_newlines=1`로 이미 LF가 붙은 message를 읽고 교체할 때 기존 writer는 LF를 다시 하나 붙인다. 예를 들어 미처리 `two\n`은 재기록 후 `two\n\n`이 된다. 실제 category frame을 포함한 시험에서 binary/빈 category는 보존되고, 다음 replay의 message에는 이 추가 LF가 남는 것을 확인했다. 첫 번째 시도에서 수락된 message에는 재기록이 일어나지 않는다.

이것은 현재 writer의 옵션 적용을 그대로 사용하는 결과다. 수정은 기존에 열리지 않던 교체 경로를 가능하게 하며, 동시에 이 옵션의 재적용이 실제로 관찰될 수 있게 한다. LF를 제거하거나 기존 LF를 감지해 생략하는 별도 의미 변경은 하지 않았다. 사용 설정을 확인하고 이 차이를 검토해야 하며 회사 운영본의 동등성은 미확인이다.

## 남은 위험과 미검증 범위

- **Atomic replace·rollback 없음:** truncate가 먼저 기존 bytes를 지운다. 그 뒤 write 실패나 프로세스/장비 중단에는 원래 contents가 이미 사라질 수 있다. temp-file/rename/fsync·복구 설계를 추가하지 않았다
- **실패 정책 유지:** 실제 교체 실패 시 BufferStore의 lost/delete 경로는 남아 있다. 이번 수정은 잘못된 open mode로 정상 교체도 항상 실패하던 원인을 제거한다
- **지연 I/O 오류 미보장:** StdFile::write의 stream 상태 검사는 close/flush 단계의 오류를 replaceOldest에 전달하는 보장이 아니다. 정상 I/O 시험 통과를 disk-full·write/flush/close 실패 주입 성공으로 쓰지 않는다
- **열린 writer unlink 별도:** deleteOldest가 열린 writer를 unlink한 뒤 후속 write가 성공처럼 보일 수 있는 기존 characterization 시험은 계속 통과한다. 그 정책은 수정하지 않았다
- zero frame·orphan category·짧은 header와 기존 loss accounting의 한계도 그대로다
- stream flush는 fsync가 아니고 OK는 영속 저장 확인이 아니다. 회사 fork·실제 config·baseline을 확인하지 않았으며 성능·운영 승인을 뜻하지 않는다

## 재실행·증거

```sh
# 기존 승인 toolchain의 process-local 환경 적용
export THRIFT_PREFIX=/absolute/prefix/thrift-0.25.0
export FB303_PREFIX=/absolute/prefix/fb303-0.25.0
export TOOLS_PREFIX=/absolute/workspace-tools/usr
export SCRIBE_BUILD=/absolute/fixed-source-configured-built-copy
python3 -B -m unittest discover -s test -p 'test_*.py' -v
git diff --check
sh -n bootstrap.sh
```

이전 build copy의 file.cpp는 이제 달라지므로 재사용하면 fixture가 거절한다. 수정 source로 다시 build해야 한다. 이번 실제 configure/build 명령과 binary/source/test/log hashes는 manifest에 기록한다. 기존 byte golden·원본 ASan 오류/수정 reader ASan·UBSan 시험도 재실행했다. 전체 FileStore/BufferStore object를 instrument한 sanitizer build는 아니고, 클라우드 LSan은 ptrace 제약으로 제외한다. 이전 Ubuntu reader LSan 결과와 현재 수정본을 혼동하지 않는다.

수정본 v5는 위의 별도 Ubuntu 검증에서 새 clean build·74개 시험을 통과했다. 수정 전 v4는 별도 Ubuntu 서버에서 **70개/skip 0, 20.241초**를 통과한 별도 Ubuntu 검증 보고를 확인했다. 이 실행은 기존 production build object와 새 fixture를 사용한 characterization이며 새 clean build가 아니고, 기존 손실/unlink를 예상대로 재현한 결과다. source/doc 134개와 manifest 314개 보존 보고를 받았다. 해당 raw log tar의 전달된 SHA256은 `79b914877561f646a3f49c7db2868e8bd7c7df68100a74b5dceaf683b44a21cd`이며 이번 클라우드에서는 bytes를 가져오거나 직접 검증하지 않았다. 이전 55개 raw logs는 별도로 보존한다. 이들 결과는 각 source에 귀속된다. Thrift upstream 29개는 이번에 재실행하거나 74개에 합치지 않았다. strict upstream 검사에서 기존 15개 경로 차이는 그대로이며 file.cpp의 새 내용 차이를 숨기지 않는다. Gate A 전체 matrix 및 B/C 전체 legacy RPC·10 store·thriftfile·relay·fault/종료, D 회사 성능·운영 gate는 미완료다. commit/push/merge는 이번 클라우드 수정 완료에 포함하지 않는다.
