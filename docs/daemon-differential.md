# 첫 actual-daemon old/new 비교의 재사용 harness

2026-10-05 · base main `fc3767bc4b44646e3eb232d65aa77ae47447d5fa`

아래 단계별 binary·source·승인 설명은 당시 이력이다. 현재 empty-only drain·truncate·copy의 동작은 PR #25 이후 [원본 계약 우선 정책](legacy-compatibility-policy.md)을 따른다. 과거 성공을 현재 검증으로 합산하지 않는다.

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

당시 승인된 empty-only queue drain 수정은 별도 예외로 유지했다. Null/multi는
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
당시 승인된 empty-only/truncate/copy 예외와 oversized/empty 정책은 유지했다.


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

이 작은 full-success replay는 deleteOldest 경로이며 당시 승인된 partial replay
replaceOldest/openTruncate 수정은 실행하지 않았다. relay ACK는 queue 수락이며
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


## 남은 file-backed store 묶음

--case file-stores는 같은9요청/7비교응답 driver로 13개 nonempty entry를
보낸다. exact category BucketStore는 implicit <bucket>의 key_range(20,2 buckets),
remove_key=yes와 delimiter124를 사용한다. 5|binary5→b001,15|ends\n→b002,
no-key→failed이며 key/delimiter 제거 후 각 file bytes를 비교한다. numbered
bucket0..N의 원본 pointer arithmetic 결함과 BucketStore 외부 copy 설정 차이는
이 정상 config에서 실행하지 않는다.

직접 thriftfile의 framed0/raw1 두 인스턴스와 multifile/thriftmultifile aliases를
같이 검사한다. aliases는 fan-out이 아니라 CategoryStore 모델의 per-category
파일 생성이다. wildcard 공유 queue(new_thread_per_category=no) 아래 mfA/mfB와
tmfA/tmfB를 나누고 child directory/basename과 상대 current link를 대조한다.
당시 framed thriftmultifile은 use_simple_file=0이므로 raw-copy 수정의 차이가 없었다.
직접 raw thriftfile은 copy를 호출하지 않는다.

framed binary5/ends\n은 각각 native uint32 length+5 bytes의9바이트 event다.
chunk_size=16이므로 둘 사이7개 zero padding을 포함한25바이트가 기준이다.
확인한 Linux x86_64 lane의 native length는 little-endian이며 RPC frame의
big-endian과 구분한다. raw 파일은 원문10바이트, Z category의 framed 파일은
5바이트다. 총9개 파일·9개 relative link·수신 good13을 정확히 대조하며 model
파일, 메타 출력이나 다른 suffix를 허용하지 않는다. ThriftFileStore flush는
production no-op이므로 authoritative snapshot은 정상 shutdown과 child exit0
뒤에만 읽는다. 기록 시간이나 고정 pause로 flush 완료를 추정하지 않는다.

온라인 구 writer 조회는 실패했으나 후속 서버에서 이미 검증한 공식 Thrift0.9 tar
(SHA256 71d129c49a2616069d9e7a93268cdba59518f77b3c41e763e09537cb3f3f0aac)의
lib/cpp/src/thrift/transport/TFileTransport.cpp와 보존 build source가 byte 단위로
같음을 확인했다. write의 native eventLen 4-byte memcpy와 writerThread의
chunk 경계 zero padding을 읽었고 실제 old/new에서 위25/5바이트가 일치했다.
원문 source SHA256은 f31c0b97210a826e838dcddf225e55fc805896258ac22aafa67b35bd0f86d14c다.

Cloud는 synthetic wire/report와 oracle을 검사했고 후속 서버에서 전체172개
시험 failure/error/skip0과 실제 file-stores case1회를 통과했다. 요청9/비교 응답7,
received13, 정상 child exit0 뒤 파일9/상대 symlink9와 정확한 bytes가 일치했다.
owned socket 검사, runtime30개 hash/private loader/help와 networknone/uid65534/
resource 제한을 유지했고 운영30개 container ID는 그대로였다. C++/header/IDL38개
(production24/fixture14)는 matching build와 동일하며 새 clean build는 하지 않았다.
Focused offline19개는 실제 daemon 실행 횟수와 구분한다. 전체10종의 제한된
정상 config가 확인됐지만 모든 설정/fault branch나 완료 gate 통과는 아니다. 지원 현황은 [현재 Linux/store 범위](linux-build-mvp.md#공개-원본-store와-optional-지원-현황)를 따른다.


## 공개 fixed-profile 성능 baseline

--case performance는 기존 Python3 client와 owned-daemon helper로 한 profile만
측정한다. 각 새 process는 num_thrift_server_threads=4,max_queue_size=33554432,
std FileStore/never/max_size=1000000000을 공유한다. 256개 warm-up record가
파일에 flush된 것을 확인한 뒤 4 producer가 각각4096개1024-byte 메시지를
256개 batch로 전송한다. measured payload는16MiB/16384 entries, trial당64 RPC다.
64개 request packet 생성·hash(약17MiB client 메모리)는 timer 전에 끝낸다.
각 producer connection도 첫 RPC 전 owned PID socket inode를 확인한다.

old0→modern0→modern1→old1→old2→modern2, 각3회면 끝낸다. 매번 새 process/파일이지만
warm-up 뒤의 warm workload다. startup/cold-start 성능을 측정하지 않으며 OS page
cache를 drop하거나 CPU affinity/quota·서비스·보안 설정을 바꾸지 않는다.
여섯 파일은 measured96MiB+warm-up1.5MiB=97.5MiB이며 bounded control/log metadata가
추가된다. 실행자는 기존 container resource 배정과 현재 운영 부하를 읽기로
확인·기록한다. 관찰한 부하 변동은 숨기지 않는다.

- ACK 처리량: synchronized gate부터 모든 measured batch가 OK로 응답할 때까지
  time.monotonic wall time. 메시지/초와 application payload MiB/초이며 wire
  throughput이 아니다. client thread/send/parse/bookkeeping도 포함한다
- p95: 각 trial의64개 send→parse ACK client wall latency를 정렬해
  nearest-rank ceil(0.95×64)=61번째 값. warm-up·packet encoding/hash는 제외한다
- 파일 완료: 같은 시작점부터 기대 file size가 보이는 첫5ms interval 관찰까지.
  실제 완료 시점의 관찰 상한이며 write/fsync durability latency가 아니다
- client CPU: measured 시작부터 file-size 관찰까지 time.process_time delta
- daemon CPU: 같은 구간 전후 owned /proc/PID/stat의 utime+stime delta를
  SC_CLK_TCK로 나눈 값. coarse kernel ticks이며 종료 전에 읽는다
- RSS: owned /proc/PID/status VmHWM의 kB(KiB). 시작/warm-up까지 포함한 process
  lifetime high-water through completion이며 구간 delta나 가상 stack 크기가 아니다

모든 measured Log는 OK여야 하고 retry하지 않는다. collective producer timeout은
30초/socket3초이며 실패 시 gate를 해제하고 SHUT_RDWR/close·bounded join 뒤 기존
owned process/session cleanup을 수행한다. 32MiB queue는 이번 전체 payload와
category bytes보다 크고 high max_size는 크기 회전을 피한다. 이는 메모리/RSS의
엄격 상한이 아니다. default backpressure 성능이나 모든 store mix를 대표하지 않는다.

payload 앞8바이트는 producer/순번이며 나머지 binary tail도 정확히 검사한다.
종료/회수 뒤 파일을 streaming으로 읽어 누락·중복·변형·producer 내부 reorder를
거부하고 expected counter, regular file/current link와 SHA를 대조한다. producer간
interleaving은 Thrift thread scheduling에 따라 달라져 raw file hash가 같아야 한다고
요구하지 않는다. 실제 summary 직전 retained raw outputs도 다시 검증한다.
measured packet은 전체 raw/hex를 기록하지 않고 재현 recipe·SHA·reply bytes를
보존해 observer I/O를 timer에 넣지 않는다. consumer raw files는 commit하지 않는다.

각 lane3개 값의 median/min/max와 modern/old ACK ratio만 기술한다. 미리 임의
성능 합격 threshold를 넣지 않는다. 같은 container/resources라도 compiler,
Thrift/fb303/Boost/libc와 ABI가 달라 원인 격리는 불가능하다. client/loopback와
filesystem/page-cache 영향도 포함한다. ACK는 queue 수락이고 fsync/exactly-once가
아니다. cloud의 synthetic/fake tests는 측정 코드 검증이며 실제 수치가 아니다.
2026-10-05 서버의 실제 여섯 trial은 지정 순서 그대로 실행됐다. 서버 전체177개,
Mac 집중24개 시험은 failure/error/skip0이다. 모든 measured ACK는 OK, 매 trial
received16640, 정확한 binary record16640·producer 내부 순서·regular file/상대
current link, child exit/reap/port 해제를 확인했다. 실제 consumer raw97.5MiB는
서버 private evidence에 보존하며 저장소에 넣지 않았다. container exit0/OOM없음,
운영 container30개의 ID는 전후 동일했다. production/fixture C++·header·IDL38개와
기존 두 daemon binary는 그대로이며 새 clean build는 하지 않았다.

아래 값은 각 lane3개 trial의 **중앙값 [최소, 최대]**다. 임의 합격 threshold가
없는 descriptive baseline이며 correctness PASS를 성능 PASS로 해석하지 않는다.

| 측정 | old | modern |
| --- | --- | --- |
| ACK messages/s | 1519392 [1409687,1526618] | 1894796 [1554360,1976483] |
| ACK payload MiB/s | 1483.781 [1376.647,1490.838] | 1850.387 [1517.930,1930.159] |
| 파일 크기 완료 관찰 payload MiB/s | 1479.891 [1373.915,1487.904] | 1164.109 [1021.776,1192.822] |
| batch ACK p95 ms | 1.092 [0.947,1.503] | 1.069 [1.031,1.343] |
| daemon CPU s | 0.030 [0.030,0.030] | 0.030 [0.020,0.030] |
| client CPU s | 0.004278 [0.003817,0.004417] | 0.004509 [0.004249,0.006657] |
| process VmHWM KiB | 13832 [10572,14080] | 21144 [20024,23880] |

modern/old 중앙값 비율은 ACK1.2471, 파일 완료 관찰0.7866, VmHWM1.5286다.
파일 완료 관찰 처리량의21.3% 감소와 RSS high-water의52.9% 증가는 raw 관찰
차이로 보존한다. 성능 합격이나 퇴보를 판정하지 않는다. 사용자는 프로젝트가
어느 정도 완성된 뒤 상세 성능 비교를 진행하기로 결정했다. 현재 단계에서는
추가 run·원인 분석·tuning을 하지 않고 원본 기능 완성 작업을 이어간다.
파일 완료는5ms poll의 관찰 상한이고 각 workload는 짧으므로 원인을 격리하거나
지속 처리량·최대 처리량을 입증하지 않는다. 추가 run·tuning은 하지 않았다.

측정 직전 host18 logical CPUs,2초 busy9.55%,load0.39/0.30/0.37,
MemAvailable61.24GB와 disk free661.04GB를 읽었고 다른 build process는 없었다.
기존 network-none task container의 CPU2/RAM2GiB/PIDs128·uid65534를 유지했다.
호스트 부하 변동, filesystem/page cache와 관찰 간격의 영향을 배제하지 않는다.
기존 container에는 Python3가 없어 host의 기존 Python3.14.4 표준 runtime만
private 경로로 복사했다. 705개 runtime 파일 bytes/hash를 확인하고 matching
private loader/lib를 사용했으며 시스템 패키지·설정은 바꾸지 않았다. 동일
client를 양 lane에 사용했지만 old GCC5.4/Boost1.58/Thrift0.9와 modern
GCC15.2/Boost1.83/Thrift0.25의 ABI/userland 차이는 남는다. CPU는0.01초 ticks,
RSS는 startup/warmup 포함 lifetime high-water다. durable ACK·fsync·Gate D 또는
운영 배포 승인으로 확대하지 않는다.


## fb303 option/counter와 unknown-method 회복 묶음

--case fb303는 같은 owned child/legacy framed binary helper로 한15-RPC batch를
보낸다. fresh getOptions{},미존재 getOption의 빈 값 삽입,getOptions map,
setOption→binary getOption→overwrite→getOptions를 확인한다. option key/value는
embedded NUL/0xff를 포함하며 map key/value는 helper JSON에서 hex로 보존한다.
setOption은 oneway가 아닌 일반 void REPLY(STOP만 있는 result)다.
미존재 getCounter는0을 반환하지만 counter map에는 새 key를 만들지 않아야 한다.
그뒤 존재하는 counter의 i64 getter와 전체 map을 같은 입력 수2로 대조한다.

compat_unknown은 T_EXCEPTION header3/UNKNOWN_METHOD type1/message를 비교하고
같은 연결에서 정상 Log2개/getStatus(ALIVE)와 shutdown을 이어간다. 원본과 현대
exception message/field 표현이 다르면 실패 원시 기록으로 보고하고 production을
임의로 고치지 않는다. 새 decoder는 void·map<string,string>·i64와 명시 exception만
지원하고 map element type/중복/길이·count·field ID/header/trailing bytes를 거부한다.
기존 getCounters map<string,i64> 타입 검사는 옵션 map과 별도로 유지한다.

공통 정상 config는 num_thrift_server_threads=2,max_msg_per_second=0으로
원본의 rate-disable 경로를 확인한다. stdout/config metadata와 final raw9바이트
fixture_00000/current link,exit0·child 회수·listener 해제를 기록한다. 요청15개 중
shutdown만 oneway이며 비교 응답14개다. unknown method는 대표 application error
이지 malformed frame/모든 error/config 거절 경로 시험이 아니다. 원본 throttle은
limit의 절반보다 큰 batch를 우회 허용하므로 작은 limit+큰 batch를 곧바로
TRY_LATER로 기대하지 않는다. 시간 의존 rate-denial/backpressure는 이 batch에 없다.

RPC256MiB·retained spool 한도,zero-range modulo·copy·truncate 승인 예외와
empty/oversized 정책은 이전대로 분리한다. 상세 성능 비교·추가 run·tuning은 계속
보류하며 이번 cloud는 synthetic parser/report만 검증한다. 실제 old/new fb303
결과는 후속 서버 actual case1회에서 PASS로 확인됐다. 서버 전체180개와 Mac
집중27개 시험은 failure/error/skip0이다. old/modern의 요청15개·응답14개가
byte 단위로 일치했고 binary option state·counter2·UNKNOWN_METHOD exception 뒤
동일 연결 Log/getStatus와 raw9바이트/상대 link가 일치했다. old PID19/modern PID23은
각 exit0/cleanup0이며 owned listener·socket 검사와 child 회수가 통과했다.
기존 runtime30개 hash/private loader/help·network-none/uid65534·CPU2/RAM2GiB/
PIDs128을 유지했고 운영30개 container ID는 전후 동일했다. production/fixture
C++·header·IDL38개와 matching binary는 그대로이며 새 clean build는 하지 않았다.
이는 대표 fb303/wire error와 rate-disabled 정상 config 범위이며 malformed
frame·시간 경계·큰 frame·zero-range 승인 예외나 전체 API 완료가 아니다.

## Dynamic mapping/TTL batch

Base main59748b1; `--case mapping` is prepared for the same explicit old/modern
command/environment targets and already isolated uid65534/lo-only container.
It reuses the owned-daemon/framed client helpers and three retained stdlib
loopback listeners: mapping RPC, Log/OK destination A and destination B.
No additional dependency, production code, pooling policy, malformed/huge-frame
case or benchmark is introduced. The bounded actual old/new run passed below.

The direct NetworkStore has bucket_id=1, thrift_bucket mapping, TTL5,
use_conn_pool=no and target_write_size=1. A direct/unpooled store avoids requiring
old bucket/copy and approved pooled endpoint-close bugs to match. Fixed ports are
base (Scribe), base+1 (A), base+2 (B), base+3 (mapping), so base must be<=65532.

Same five application payloads per lane:
1. A0/NUL/ff goes to A after initial mapping
2. After the stub changes to B, A1/newline still goes to cached A with no new
   fetch, inside a guarded pre-expiry window
3. After an observed strict TTL expiry fetch, B0 goes to B
4. After an expired refresh returns the declared BucketStoreMappingException,
   B1 still goes to the existing B endpoint
5. After observed successful recovery, A2 goes to A

Expected ordered bytes: A receives `413000ff`, `41310a`, `4132`; B receives
`4230`, `4231`. The public updater erases its category cache before refresh;
failed resolution does not alter the already-open NetworkStore destination.
Recovery fetches again because the cache is absent. The original expiry rule is
`lastUpdated + ttl < now`, not >=. The merged raw trace records mode controls,
requests/replies and wall/monotonic times; replay checks phase ordering, raw
cache/fetch evidence and strict expiry rather than trusting summary metadata.
Every send must converge to its ordinary received/sent counters and ALIVE status.
Mapping-specific stats are compiled under FACEBOOK and unavailable in public
`env_default`; they are not fabricated as observable counters.

Two additional fresh-child configs omit bucket_id or bucket_updater_port while
retaining a static A endpoint. The original warning/module-disable/static-fallback
must occur, one payload must reach A, and no mapping RPC may happen. Invalid
configuration is not reinterpreted as universal startup rejection.

All mapping/relay wire data remains raw. Diagnostic counter polls and repeated
failed refresh calls can vary with scheduling; only their valid observed states,
source-defined phase/data results and cleanup determine equivalence. No payload
normalization or synthetic clock replacement occurs. A late cache-proof window
fails diagnostically, rather than being relabelled as a pass.

Run using the existing command, changing only the case:

```sh
python3 -B tools/daemon_differential.py --run-isolated-daemons \
  --targets /absolute/verified/old-modern-targets.json \
  --output /absolute/new/mapping-evidence --case mapping --port 14630
```

Three fresh Scribe children per lane run sequentially, never concurrent writers.
Peers bound their tiny frames, idle-read polling, observation waits and thread
joins. Owned Scribe cleanup uses the existing TERM/KILL/reap path; each listener
must be gone afterward. Initial/final failed mapping results, active case/error,
partial peers and daemon logs persist on every failure. A passed daemon shutdown
alone cannot substitute for a passed mapping case.

### Actual server result (2026-10-05)

Base main59748b1, five test/tool/document files; production C++/headers/IDL/build
files unchanged. Server full201 and Mac focused7 passed, failures/errors/skips0.
The actual `--case mapping --port14630` comparison passed all three scenarios in
both old fcd294f/Thrift0.9 and modern Thrift0.25 lanes. TTL received/sent5 and
ALIVE2; each missing-key fallback received/sent1 and ALIVE2. A received the exact
three payloads/9 bytes and B two/4 bytes in the TTL case. Both fallbacks received
A0/4 bytes at A with no mapping RPC. Each valid trace contained A/B/fail/A mapping
responses (four fetches here); cached fetch count was1 before/after, elapsed
0.078534s old and0.076305s modern. Scheduling-dependent counts remain diagnostic.
Local replay of every ingress/peer record and merged chronology reproduced the
canonical comparison; raw results, configs, stdout/stderr and timing are retained.

Server evidence root: `/workspace/scribe-next-mapping-validation-20261005-qH2K7c`;
`actual-evidence/run/evidence/{old,modern}/mapping-result.json`, peer records and
`comparison.json`, plus `actual-summary.json`. The normal old binary SHA256 is
`929d9bf5e323c72b4770ef546559e721e3485140482afc198e2785c1d0460d8b`;
modern is `7142824130803f679ac7986bba1309413a1728e32924fdb5e7fa86d94e43c6f5`.
Thirty existing daemon/runtime files and705 private Python3 runtime files were
hash/size verified. Modern loader resolution stayed private; help passed. These
are reused verified artifacts, not a new clean build or HDFS binary comparison.

One new owned container used a private local snapshot of the stopped trusted
Ubuntu16 baseline task, preserving its existing dependency closure and target
command/environment arrays. The snapshot is derived from the trusted task, not
an unmodified official image. Runtime: Docker network-none, only lo, uid65534,
all capabilities dropped, no-new-privileges, no mounts/published ports, CPU2,
RAM/swap2GiB and PIDs128. Ports14630–14633 stayed internal. All six child exits,
cleanup exits and peer cleanup passed; container exit0, no timeout/OOM. Operating
31 container IDs were unchanged. The owned stopped container and temporary image
were removed after raw evidence verification; the original baseline stayed stopped.

This closes the named direct/unpooled mapping cache/TTL/failure/recovery and two
static-fallback observations. It does not establish the full dynamic config,
race, pooling, company fork, platform/feature or malformed-input matrix. No
production policy, retry/loss/ACK semantics, deployment or performance claim changes.
