# ThriftFileStore copy 수정과 동작 보존 결정

2026-10-06 정책 변경: 아래 승인·수정·측정은 당시 이력이다. 현재 기본 동작은 [원본 계약 우선 정책](legacy-compatibility-policy.md)을 따르며 route/byte/format/delivery/monitoring 변경은 되돌린다. 과거 raw 결과는 현재 검증으로 세지 않는다.

2026-10-05 · [실측과 범위](thriftfile-contracts-status.md)

## 승인한 copy 수정

사용자는 copy에서 `use_simple_file` 설정을 보존하는 최소 수정과 회귀 검증을 승인했다. 범위는 `ThriftFileStore::copy`에서 기존 `flushFrequencyMs`/`msgBufferSize`처럼 `useSimpleFile` 값을 복사하는 한 필드다. default0은 기존 native-event output을 사용하고, simple1/2의 새 copy는 source와 같은 raw mode를 사용한다. live transport는 공유하지 않는다. path·category·chunk·flush/buffer·suffix와 다른 store의 처리 규칙은 그대로다.

이미 default 형식으로 기록된 clone 파일은 raw로 변환하거나 덮어쓰지 않는다. 정상 open은 다음 suffix의 새 파일을 만들므로 같은 category directory에 기존 framed 파일과 이후 raw 파일이 함께 남을 수 있다. consumer는 각 파일 세대의 기존 형식을 구분해야 한다. 이번 수정은 future copy 설정 보존이며 기존 데이터 자동 변환이나 운영 배포가 아니다.

회귀 검증은 default source/copy의 동일 framed bytes, simple1/2 source/copy의 동일 raw bytes, closed clone·별도 경로·다른 설정 보존을 확인한다. legacy clone 파일의 bytes를 유지하고 다음 suffix에 raw output을 기록한 뒤 실제 reader로 읽는다. 수정 전 관찰과 수정 후 회귀 결과는 [현재 기록](thriftfile-contracts-status.md)에 구분한다.

## Chunk 초과와 empty는 기존 Thrift 처리 유지

사용자는 청크보다 큰 메시지도 기존처럼 Thrift transport에 넘기고 동작을 유지하도록 결정했다. 새 실패 파일·자동 분할·추가 재시도·lost 계측·enqueue 전 거절은 적용하지 않는다. empty event도 이번 단계에서 새 정책으로 바꾸지 않는다.

default TFileTransport의 `payload + 4-byte header > chunk_size` 경로는 비동기 writer가 오류 로그 후 해당 event를 생략한다. 같은 길이는 이 조건으로 거절하지 않는다. Scribe는 정상 반환한 write를 성공으로 집계하고 `true`를 반환하므로 해당 생략에 대한 queue 재시도나 lost 카운터가 생기지 않는다. 기본 chunk16,777,216의 nonempty payload 경계는16,777,212 bytes이며 network256MiB 제한과 별개다. simple mode는 이 event framing/chunk 검사를 거치지 않는다. [Thrift0.9.0 writer](https://github.com/apache/thrift/blob/0.9.0/lib/cpp/src/thrift/transport/TFileTransport.cpp#L444-L450)와 [Thrift0.25.0 writer](https://github.com/apache/thrift/blob/0.25.0/lib/cpp/src/thrift/transport/TFileTransport.cpp#L405-L412)에 같은 조건이 있다. 0.9.0은 소스 확인이며 구 runtime 실행 결과가 아니다.

기존 tiny 시험의 chunk8/payload9 성공 반환·성공 집계·출력0과 empty의 성공 집계·event 생략 기대를 유지한다. 이는 유실 문제가 해결됐다는 뜻이 아니라 사용자가 선택한 보존 동작이다. 새 counter나 durable ACK를 주장하지 않는다.

## 단순 false 변경을 적용하지 않는 이유

기존 `Store::handleMessages`는 false일 때 vector에 미처리분만 남기는 계약이다. StoreQueue의 기본 `must_succeed=true`는 실패 batch를 새 batch보다 먼저 재시도한다. BufferStore도 남은 메시지를 secondary에 저장하거나 미처리 suffix로 replay 파일을 교체한다.

- `[정상 A, oversized X, 정상 B]`에서 A를 enqueue한 뒤 전체를 false로 재시도하면 A가 중복될 수 있다
- A를 제거하고 `[X,B]`를 반환해도 동일 설정에서 permanent-invalid X가 B와 새 queue의 진행을 막을 수 있다
- 전체 batch를 사전 검사해 false로 반환하는 방식도 X가 있는 한 전진하지 못한다
- `must_succeed=no`에서는 false로 반환한 정상 suffix까지 lost 처리될 수 있다

이는 source 계약에서의 추론이며 새 failure-loop/혼합 batch fault 시험을 실행했다는 주장이 아니다. 앞선 문서의 실패 보존·추가 계측 후보는 이번에 채택하지 않았다. 일반 retained spool256MiB 초과 해결과 회사 old/new·전체 CLI·운영 gate는 계속 별도 미완료 항목이다.
