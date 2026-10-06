# 원본 계약 우선 정책

2026-10-06 · 공개 원본 `fcd294faffd1e88af1643a3a8c2359c41713f7c2`.
사용자는 신→구/구→신 송수신과 기존 로그 소비 client의 계약을 우선하도록
이전 semantic bugfix 승인을 변경했다. 새 옵션을 만들지 않고 원본의 정의된
기본 결과를 보존한다. 이전 수정·검증 raw는 Git/Library 이력에 남긴다.

## 되돌리는 동작과 남는 원본 버그

| 경로 | 원본 기본 결과와 알려진 위험 |
| --- | --- |
| BucketStore copy | remove_key/bucket_range를 복사하지 않는다. key_range clone은 원본 bucket0 routing·key 포함 bytes를 유지한다 |
| ThriftFileStore copy | simple source도 clone은 default framed transport다. 직접 설정한 simple store는 raw다. 기존 framed suffix를 보존하고 다음 clone suffix도 framed로 기록한다 |
| NetworkStore copy | 원본 endpoint/service flags 등 원래 fields만 복사한다. list/options/cache/ignore-error/dynamic updater를 새로 상속하지 않아 template category의 전송 실패·warning 또는 모델 endpoint 사용이 남는다 |
| service_list pool/reopen | 빈 pool key 공유 및 후보 누적을 보존한다. 서로 다른 list가 첫 연결을 공유하거나 재연결 후보 가중치가 바뀔 수 있다 |
| dynamic pooled endpoint 변경 | 원본은 새 endpoint를 대입한 뒤 해당 key를 close한다. 다른 owner의 refcount/연결을 줄이거나 missing-key 진단을 남길 수 있다. shared_ptr 객체 관리와 원본 pool-key 선택은 구분한다 |
| empty-only queue | payload byte 합계0이면 periodic/shutdown에 전달하지 않는다. ACK/received에도 output/lost0일 수 있다. nonempty가 섞인 batch와 빈 Log 요청은 별개다 |
| StdFile partial replay | out|app|trunc의 정의된 open 실패를 유지한다. primary가 prefix를 처리한 뒤 남은 suffix를 교체하지 못하면 기존 loss 집계·spool 삭제가 발생한다. 보존·exactly-once·durable ACK를 약속하지 않는다 |
| extra bucket 설정 | 원본 literal pointer의 길이 안 suffix 검사만 안전하게 유지한다. bucketN+1을 새로 거절하지 않는다. literal 밖 offset은 검사하지 않아 UB를 만들지 않는다 |

copy의 초기 mapping 조회를 제거하므로 P1의 resolve-on-open flag도 필요 없다.
직접 configure된 dynamic store의 기존 TTL/refresh는 유지한다. 기존 로그 파일을
변환·삭제하지 않는다. 이미 이전 수정본이 기록한 raw clone 파일이 있다면 이번
되돌림이 그 파일을 framed로 바꾸지 않으므로 reader/rollback 전에 파일 세대를
확인해야 한다. 같은 directory에 서로 다른 형식이 있을 수 있다.

## 유지하는 안전·이식 경계

malloc/delete[] 불일치의 free, retry modulo0 guard, 알 수 없는 bucket child의
null guard, omitted list_default_port의 초기값0, C++17 GNU shuffle 순서와 API/
HDFS arity 이식은 유지한다. 원본 UB/crash에는 보존할 정의된 값이 없다.
원본 ThriftFile empty/oversized delegate/drop/log/success 정책은 유지한다.

두 IDL과 strictRead=false/strictWrite=false는 그대로다. 기존 256MiB 유한
frame/message 한도는 무제한 원본 호환을 보장하지 못하는 별도 한계다.
작은 대표 RPC의 양방향 성공을 전체 크기·언어 runtime 호환으로 확대하지 않는다.
Python3/Thrift0.25 생성 package는 서버 포팅과 별개이며 기존 Python2/client
runtime에 강제 업그레이드하거나 동일 이름 package를 덮어 설치하지 않는다.

## 검증 경계

기존 source-linked fixture의 기대값을 원본으로 교정한다. exact routing/payload,
framed clone bytes와 실제 reader, ordinary spool old/new bytes 및 loss/counter,
작은 양방향 relay를 각각 확인한다. 실제 서버 결과와 offline/component 결과를
구분하며 완료 수치는 해당 checkpoint 기록을 따른다. 성능 비교는 보류한다.


## 이번 서버 검증 (2026-10-06)

Base main6abb3a8의 원본 계약 복원 source는 서버의 새 clean validation8단계,
전체205·focused legacy15·ordinary spool12를 failure/error/skip0으로 통과했다.
source-copy/generated-code/object freshness와 DESTDIR/help 검사를 유지했다.
새 binary SHA256은 `0f2e5e569597daba56039c1b1e5757139a7000547d4dd5761c68723e09203f1f`다.
서버 근거는 `/workspace/scribe-next-legacy-validation-20261006-5Rujt7`에 보존했다.

실제 old0.9/modern0.25 file-stores와 mixed-spool 구→신·신→구가 통과했다.
후자는 각 upstream의 자기 spool write/replay와 반대 runtime으로의 relay이며
서로 다른 daemon의 disk spool을 직접 교차 읽은 시험은 아니다. 별도 ordinary
component는 두 writer/두 reader의 bytes와 원래 truncate/loss 결과를 확인했다.
정확한 payload/wire/counters/status, owned socket inode·child/listener 회수와
raw replay 결과를 확인했으며 작은 대표 입력을 전체 호환으로 확대하지 않는다.

정상 close된 old daemon framed 파일은 modern reader로, use_simple_file=1의
실제 modern production clone(kind=tfile,use_simple_file=0)은 GCC5.4/C++03/
Thrift0.9 reader로 읽었다. 각 결과는 events2/bytes10과 exact
`4100420aff656e64730a`다. read-call count가 event 수와 같은 것은 이 두5-byte
입력의 범위다. 최초 old compile의 전역 uint 타입 미선언 실패는 raw로 유지했고,
시험 reader에 stdint.h 한 줄을 Thrift header 앞에 추가한 뒤 compile/link/read를
통과했다. official header/API/runtime는 수정하지 않았다. 이 include 단계에서는
기존 production/source와 성공 binary 해시를 재검증하고 reader만 다시 compile했다.
전체205나 daemon 비교를 새로 반복한 결과로 기록하지 않는다.

network-none/lo-only·uid65534·cap-drop ALL·no-new-privileges·CPU2/RAM2GiB/PIDs128,
no mounts/published ports의 owned 작업 container/image만 제거했다. 운영32개 ID와
기존 stopped baseline은 보존했다. 새로운 옵션, 거대 frame 검증, benchmark,
패키지/tag/release·서비스 배포는 하지 않았다. 과거 raw clone 파일 세대를 자동
변환하거나 임의 downgrade의 안전성을 보장하지 않는다.
