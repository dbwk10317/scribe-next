# 첫 actual-daemon old/new 비교의 재사용 harness

2026-10-05 · base main `fc3767bc4b44646e3eb232d65aa77ae47447d5fa`

## 실제 선행 결과와 이번 범위

공개 원본 `fcd294f` + Thrift/fb3030.9.0 daemon과 현재0.25 daemon을 각각의
runtime/ABI로 실제 실행한 첫 synthetic batch가 성공했다. 원본에는 승인된
autotools 한 줄 build-only patch만 적용됐고 현대화 production patch를 덮지 않았다.
현재 daemon binary SHA256은 `7142824130803f679ac7986bba1309413a1728e32924fdb5e7fa86d94e43c6f5`다.
당시 검증 source621dfd와 현재main의 production26개 bytes는 같았다.

두 lane의 요청9개와 비교한 응답7개 bytes가 일치했고 getVersion은 양쪽2.2였다.
getName/status/details/counters, 빈 Log, 정상3개(NUL/LF/non-UTF8 및 빈 payload
포함), 빈 category와 미정의 category 각각1개, oneway shutdown을 실행했다.
counter delta가 같고 파일9 bytes `4100420aff7461696c` 및
fixture_current → fixture_00000도 같았다. 양쪽 exit0과 listener 회수를 확인했다.
Docker는 networknone/lo-only/noports/nomount/uid65534/resource limits로 실행했고
기존 운영30개 container ID는 유지했다. 이것은 한 batch의 원본 대조다.

이번 변경은 당시 stdlib Python2/3 client/config를 tools/daemon_differential.py로
정리한 것이다. C++/IDL/store/배포 변경은 없다. source evidence archive SHA256은
`a9aeceba8c5d653c223b55d0ae30f33b83ae7e43b7a1288b91d546d5432db67f`다.
test/fixtures/first_daemon_differential에는 두 lane에서 실제 같았던 요청9/응답8
파일과 개인 경로·PID·command를 제외한 expected report만 보존한다. getVersion
raw 응답도 replay하지만 byte-equality 항목7개와 별도 identity 확인을 구분한다.
원본 실행 로그/개인 절대경로는 저장소에 넣지 않는다.

## 실제 실행은 별도 opt-in

이 도구는 Docker/namespace/dependency/권한을 설정하지 않는다. 이미 승인된
격리 환경을 준비한 뒤 old/modern의 절대 executable argv와 명시적 환경을 받는다.
modern은 필요하면 이미 검증한 loader + --inhibit-cache/--library-path argv를
command에 넣고 마지막에 scribed binary를 둔다. harness가 -c와 새 config를 붙인다.
LD_PRELOAD/LD_AUDIT injection은 거부하고 ambient LD_LIBRARY_PATH는 상속하지 않는다.

```json
{
  "old": {
    "command": ["/prepared/old/bin/scribed"],
    "environment": {"LD_LIBRARY_PATH": "/prepared/old/thrift/lib:/prepared/old/fb303/lib"}
  },
  "modern": {
    "command": ["/prepared/modern/lib/ld-linux-x86-64.so.2", "--inhibit-cache", "--library-path", "/prepared/modern/lib", "/prepared/modern/bin/scribed"],
    "environment": {}
  }
}
```

```sh
python tools/daemon_differential.py --run-isolated-daemons \
  --targets /prepared/targets.json --output /prepared/new-comparison-output
```

## null/multi/category의 작은 추가 case

같은 guard와 실제 old/modern argv를 사용해 `--case stores`를 선택한다. 기본
`--case file`은 앞선 검증 입력/출력을 유지한다. stores case는 하나의 daemon
config/batch로 세 정상 경로를 함께 대조하며 production 코드를 바꾸지 않는다.

- null category discard: 동일 payload3개를 수락하고 ignored3, 파일 없음
- multi category fanout: report_success=all, 두 file child에 각각 동일9bytes를
  기록하고 null child의 ignored3도 확인
- categories=cat* + type=category: new_thread_per_category=no로 실제 CategoryStore를
  사용한다. model FileStore를 catA/catB로 clone해 각각5/4bytes에 분리한다
- 전체 정상9개, blank/unknown 각1개. received good9, ignored6, bad1, blank1을
  per-category/overall counters와 함께 확인

예상 상대 파일은 left/left_00000, right/right_00000,
category/catA/catA_00000, category/catB/catB_00000이며 각 current symlink도 대조한다.
manifest의 directory enumeration 순서만 정렬하고 payload/파일명/라우팅은
정규화하지 않는다. Worker-side ignored counters 때문에 양쪽에 같은2초 settle
구간을 둔 뒤 counter8을 읽는다. 추가 poll RPC는 보내지 않으며9개 공통 요청을
그대로 비교한다. 느린 환경에서 아직 미처리면 expected delta 불일치로 실패하고
raw 기록을 확인한다; timeout을 성공으로 바꾸거나 store 동작을 수정하지 않는다.

이 case의 offline2개는 source 호출 경로를 읽어 정한 예상 routing/bytes/counters와
비교기의 누락 branch/case 거부를 확인하는 **synthetic expectations**다. 앞선 실제
file wire fixture17개와 구분하며 실제 stores old/new 성공으로 세지 않는다.
후속 서버에서 기존 compiled production bytes/hash를 확인하고 전체162개 시험
failure/error/skip0 및 actual stores 비교1회를 통과했다. 공통 요청9/비교 응답7,
received9/ignored6, 네 파일 bytes/네 symlink와 양쪽 shutdown exit0이 일치했다.
첫 RPC 전 owned child socket inode 검사, runtime30개 hash와 private loader/help,
실제 networknone/uid65534/resource 제한 및 운영30개 container ID 보존도 확인했다.
고정2초 settle을 변경하지 않았고 새 clean build는 수행하지 않았다.
전체 suite는 기존160+새2=162, focused는 기존7+새2=9다.

기존 승인된 empty-only queue drain 수정은 별도 예외로 유지한다. Null/multi는
nonempty 마지막 payload와 함께 전송하고 category도 마지막 정상 payload를
nonempty로 두어 이 정상 case를 empty-only scheduler 대조로 확대하지 않는다.
free/truncate, bucket/network 설정·copy, ThriftFileStore copy와 oversized/empty
보존 정책도 별도 이력이다. 이번 정상 세 store case는 그 결함 경로를 새로
수정하거나 fault/retry·부분 fan-out·전체 clone 동등성까지 검증하지 않는다.

real/effective uid65534와 /sys/class/net의 lo-only, 새 checkout 밖 output, 사전 포트 비점유를
검사한다. 두 lane은 별도 output에서 순서대로 실행한다. client는127.0.0.1만
연결한다. 첫 RPC 전에 /proc의 established socket inode가 소유한 child PID의
fd인지 대조하며 확인할 수 없으면 요청을 보내지 않는다. child는 독립 session으로
실행하고 실패 시 그 session의 process group만 TERM/KILL하고 child를 wait한다.
stream/socket도 닫는다. 다른 process/group을 이름으로 찾아 종료하지 않는다.
기존 listener를 사용하거나 종료하지 않는다. 실제 Docker noports/nomount/limits와
networknone 상태는 외부 실행자가 별도로 확인해야 한다. host network, privileged,
Docker socket mount나 namespace/security 우회로 guard를 통과시키지 않는다.

출력은 evidence/{old,modern}/의 request/reply bytes, daemon stdout/stderr,
start/result.json과 evidence/comparison.json이다. 실제 command/path/PID는 이
consumer-local evidence에만 기록한다. 파일·counter·request sequence가 누락되거나
손상됐거나 실패한 lane이면 비교를 통과시키지 않는다.

## 이번 cloud 검증과 다음 순서

cloud에서는 새 actual daemon을 실행하지 않는다. namespace 제약을 우회하지 않고
검증된 wire/report replay, 잘못된 evidence 거부, isolation/port guard, fake child의
protocol 실패 cleanup/session kill fallback/연결 소유권만 독립 unittest로 검사한다. 이7개는 live daemon 성공 횟수가
아니다. 후속 서버 재검증에서 같은 source의 전체160개 시험이 failure/error/skip0으로
통과했다. 기존 compiled production과 source bytes를 확인하고 새 harness를 승인된
networknone 컨테이너에서 한 번 실행했다. 두 lane 모두 첫 RPC 전에 owned child의
소켓 inode를 확인했고 요청9/비교 응답7, version2.2, counter/file/symlink 및
shutdown exit0 비교가 통과했다. old/new runtime30개(바이너리 포함)의 hash와 loader/help를 확인했으며 운영30개 container ID도 유지됐다.
새 clean build는 수행하지 않았고, old/new runtime/ABI 차이는 유지했다.

남은 coverage는 spool/relay의 부분 실패·응답 유실·재시도 경계다. 이번 정상 null/multi/category batch의 통과를 전체10 store, bucket
mapping, 모든 fb303 method, old/new 양방향 spool 및 성능 완료로 확대하지 않는다.
기존 승인된 bug-fix 차이는 명시하며 oversized/empty 처리 보존 결정도 유지한다.


## 크기 회전과 reinitialize case

같은 opt-in 명령에 --case rotation을 지정한다. 기존 file template에서
max_size=4/target_write_size=1만 바꾼다. rotate_period=never를 유지하여
시각·날짜 경계에 의존하지 않는다. 첫 Log는 기존 binary5/tail4 payload를
순서대로 보내며 strict currentSize > max_size 회전으로 fixture_00000=5바이트,
fixture_00001=4바이트와 current→00001을 기대한다. 다음 oneway reinitialize와
동일 connection의 getStatus(ALIVE) 응답 뒤 같은 파일 상태를 확인한다. 마지막
Z 한 바이트는 재열린00001에 append되어5바이트가 되고00002 빈 파일로 회전한다.
최종 current→00002와 수신 good3 카운터가 기준이다.

두 lane은 요청13개/비교 응답10개(버전 응답 제외), 중간·최종 파일 세 snapshot,
카운터 및 shutdown exit0을 대조한다. 최대10초의 파일 관찰은 정확한 예상
bytes/suffix/link 준비를 기다릴 뿐 입력이나 RPC를 추가하지 않는다. timeout은
실패이며 정기 회전·일반 프로세스 restart·장애 복구까지 통과했다고 해석하지 않는다.
production 수정과 신규 dependency는 없다. Cloud에서는 synthetic report와
fake snapshot readiness/실패만 검사한다. 후속 서버에서 같은 source의 전체164개
시험 failure/error/skip0과 실제 rotation case1회를 통과했다. 요청13/비교 응답10,
초기 good2/최종 good3 및 세 snapshot의 bytes/link와 양쪽 shutdown exit0이 일치했다.
각 snapshot의 최대10초 read-only 관찰과 정확한 기대값을 유지했다. owned child
socket inode 검사, runtime30개 hash/private loader/help, 실제 networknone/uid65534
및 기존 resource 제한을 확인했고 운영30개 container ID는 유지됐다. 기존 matching
compiled production을 재사용했고 새 clean build는 수행하지 않았다. Focused offline
시험은 기존9+새2=11이며 실제 daemon 실행 횟수와 구분한다.
승인된 empty-only/truncate/copy 예외와 oversized/empty 정책은 유지한다.


## 실제 process crash/restart case

--case restart는 각 lane의 첫 child가 binary5/tail4를 기록하여 파일5/4바이트와
current→00001 준비를 확인한 후, 소유권을 검증한 독립 session에만 SIGKILL을
보낸다. 그 child의 exit -9, process-group 회수와 listener 해제를 확인한 뒤
같은 lane 전용 output에 새 child를 실행한다. 첫 종료는 shutdown RPC가 아니다.
첫 stage의 요청8개/비교 응답7개와 수신 good2를 기록한다.

새 process는 기록 전 같은5/4바이트 파일을 그대로 재열고 fresh getCounters가
빈 map인 것을 확인한다. Z 한 바이트를 보내 기존00001에 append한 뒤
최종5/5/0바이트/current→00002와 새 process 수신 good1, shutdown exit0을
대조한다. 두 번째 stage는 요청9개/비교 응답7개이며 각 새 연결마다 owned child
socket 검증을 다시 수행한다. 실패한 첫 stage 뒤에는 다음 child를 시작하지 않는다.

이는 관찰된 사용자 공간 flush 이후 process 실패에서 ordinary FileStore를
재개하는 제한된 계약이다. fsync/power-loss durability, 미처리 queue 유실 복구,
파일 손상 복구나 spool/relay 재시도는 포함하지 않는다. approved bug-fix 차이와
ThriftFileStore oversized/empty 보존 결정도 유지한다. Cloud 검증은 synthetic
phase evidence와 fake 실패 orchestration이다. 후속 서버에서 전체166개 시험
failure/error/skip0과 실제 restart case1회를 통과했다. 양쪽 첫 stage의 요청8/비교
응답7·good2·파일5/4와 SIGKILL exit-9/reap/port 회수를 확인했다. 새 child의
빈 초기 counter와 기존 파일5/4, 요청9/비교 응답7·append 뒤5/5/0 및 current00002,
good1/shutdown exit0도 일치했다. 각 connection의 owned socket 검사, runtime30개
hash/private loader/help와 실제 networknone/uid65534/resource 제한을 유지했으며
운영30개 container ID는 그대로였다. C++/header/IDL38개(production24/fixture14)는
기존 matching build와 동일했고 새 clean build는 하지 않았다. Focused offline
13개는 실제 실행 횟수와 구분한다. production source/새 dependency 변경은 없다.


## downstream 비가동 → ordinary spool 전체 replay

--case spool은 각 lane에서 별도 upstream/downstream 두 owned child를 사용하며
--port와 --port+1 모두 unprivileged/미점유인지 검사한다. 기존 isolation/socket
소유권/session cleanup은 양쪽에 적용한다. upstream은 exact fixture BufferStore,
고정127.0.0.1 NetworkStore primary와 std FileStore secondary다. downstream은
기존 ordinary file template이다. relay가 처음 연결할 때 downstream은 없다.

binary5/tail4 두 nonempty 메시지를 보내 Log=OK 후 spool_00000의 정확한17바이트
050000004100420aff040000007461696c를 관찰한다. header는 각각 little-endian
uint32 길이이며 metadata/category frame/newline/padding/symlink가 없다.
초기 WARNING5/수신2/retries1을 기록한다. downstream을 띄운 뒤 전체 replay9바이트,
spool 삭제, upstream sent2/ALIVE2를 확인하고 Z를 streaming하여 downstream10바이트,
양쪽 수신3와 upstream sent3을 확인한다. upstream→downstream 순서로 shutdown하여
각 exit0/회수와 listener 해제를 검사하며 종료 후 spool 빈 상태와 최종10바이트를 다시 대조한다. 요청은 upstream9/downstream5,
version 응답 제외 비교 응답은7/3이다.

원본의 rand()%retryIntervalRange는0에 정의되지 않으므로 승인된 zero-range
bug-fix 예외를 정상 동등성 기대에 섞지 않는다. range=1은 integer1/2=0와
rand()%1=0으로 양쪽 모두 고정 retry_interval=10을 준다. 최초 실패 재접속 이전
준비를 보장하기 위해 upstream launch부터 downstream status/counter 준비까지
8초 미만이어야 한다. 초과는 raw 단계/child 오류와 함께 실패하며 retries 차이를
삭제·정규화하지 않는다. 초기 spool은8초, replay/streaming 준비 관찰은 각20초 이내 정확한 bytes/link/delete를
기다릴 뿐 추가 RPC/input을 보내지 않는다. 느린 환경에서는 기한을 실패로 보고한다.

이 작은 full-success replay는 deleteOldest 경로이며 승인된 partial replay
replaceOldest/openTruncate 수정은 실행하지 않는다. relay ACK는 queue 수락이며
fsync/power-loss 또는 exactly-once 보장은 아니다. empty frame/oversized chunk와
256MiB 초과 retry 계약도 바꾸거나 검증한 것으로 확대하지 않는다. production과
dependency 변경은 없다. cloud는 synthetic report/가짜 child 실패 회수와 spool
준비 실패 시 downstream 기동 차단을 검증한다. 후속 서버에서 전체170개 시험
failure/error/skip0과 실제 spool case1회를 통과했다. 공통 client의 upstream
요청9/비교 응답7 및 downstream 요청5/비교 응답3, spool17→replay9→stream10,
retries1/received3/sent3와 WARNING5→ALIVE2가 일치했다. 두 child를 정상 종료·
회수한 후에도 spool 빈 상태와 최종10바이트를 확인했다. 각 connection의 owned
socket 검사와 runtime30개 hash/private loader/help, 실제 networknone/uid65534
및 resource 제한을 유지했으며 운영30개 container ID는 그대로였다. 초기8초 및
replay/streaming20초 한도와 정확한 기대값을 바꾸지 않았다. C++/header/IDL38개
(production24/fixture14)는 기존 matching build와 동일했고 새 clean build는 없다.
Focused offline17개는 실제 daemon 실행 횟수와 구분한다. consumer raw path/PID
정보는 commit하지 않는다.
