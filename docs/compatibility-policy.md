# 호환성 정책

2026-10-06 사용자 결정 · 기준 원본 `fcd294faffd1e88af1643a3a8c2359c41713f7c2`.

구→신·신→구 송수신과 기존 로그 소비 client의 계약을 우선한다.
로그의 분배·내용·파일 형식·전달·손실 집계·상태 조회를 바꾸던 semantic 수정은 원본의 정의된 동작으로 되돌렸다(PR #25).
그 버그는 이 문서에 남기고, 고치는 새 옵션은 만들지 않는다.
UB·crash 방지와 빌드 이식은 유지한다. 원본 UB에는 보존할 정의된 결과가 없다.
사용자용 설명과 예시는 README의 [일부러 남겨 둔 원래 버그](../README.md#일부러-남겨-둔-원래-버그)에 있다.

## 남긴 원본 버그

| 경로 | 원본 결과와 위험 |
| --- | --- |
| BucketStore copy | `remove_key`·`bucket_range`를 복사하지 않는다. key_range clone은 원본 bucket0 routing과 key 포함 bytes를 유지한다 |
| ThriftFileStore copy | `use_simple_file`을 복사하지 않아 clone은 framed다. 직접 설정한 simple store만 raw다 |
| NetworkStore copy | 원래 field만 복사한다. list·옵션·cache·ignore-error·dynamic updater를 상속하지 않아 전송 실패·warning이나 모델 endpoint 사용이 남는다 |
| service_list pool key | 빈 pool key를 공유한다. 서로 다른 list가 첫 연결을 공유할 수 있다 |
| empty-only queue | payload byte 합이 0이면 주기 처리·종료 때 전달하지 않는다. `OK`·received여도 output·lost가 0일 수 있다 |
| 추가 bucket 검사 | 원본 literal pointer 길이 안의 suffix만 검사한다. `bucketN+1`을 새로 거절하지 않는다 |
| spool의 빈 frame | `add_newlines` 없는 secondary의 빈 메시지는 길이 0 frame이다. replay는 이를 EOF로 보고 앞부분만 보낸 뒤 파일을 지운다. 뒤 메시지는 전달되지 않고 lost가 늘지 않는다 |
| spool의 손상 frame | 짧은 header·orphan category도 정상 끝으로 처리한다. 정상 entry 뒤 payload가 잘리면 파일 전체 크기를 `bytes lost`로 센다 |
| 열린 spool 삭제 | `deleteOldest`는 writer를 닫지 않고 경로를 지운다. 이후 쓰기는 unlink된 inode로 갈 수 있다 |
| 긴 CLI 옵션 | `--config`·`--port`는 값을 받지 않는다 |
| 시작 실패 | 종료 코드는 0이다 |

되돌림의 영향은 다음과 같다.

- copy의 초기 mapping 조회를 없앴다. 직접 설정한 dynamic store의 TTL·refresh는 그대로다
- 기존 로그 파일을 변환·삭제하지 않는다
- 되돌리기 전 중간 수정본이 raw clone 파일을 남겼다면 그대로 남는다
- 같은 폴더에 framed와 raw 파일이 섞일 수 있으므로 reader·rollback 전에 파일 세대를 확인한다

## ThriftFile chunk 초과와 empty

2026-10-05 결정으로 원본 처리를 유지한다.

- default `TFileTransport`는 `payload + 4-byte header > chunk_size`인 event를 비동기 writer가 오류 로그 뒤 생략한다. 같은 길이는 통과한다
- Scribe는 정상 반환한 write를 성공으로 세고 `true`를 반환한다. 생략에 대한 재시도·lost 카운터는 없다
- 기본 chunk 16,777,216에서 nonempty payload 경계는 16,777,212 bytes다. 통신 크기 한도와 별개다
- simple mode는 이 framing·chunk 검사를 거치지 않는다
- empty event도 성공으로 세고 기록하지 않는다
- Thrift [0.9.0](https://github.com/apache/thrift/blob/0.9.0/lib/cpp/src/thrift/transport/TFileTransport.cpp#L444-L450)과 [0.25.0](https://github.com/apache/thrift/blob/0.25.0/lib/cpp/src/thrift/transport/TFileTransport.cpp#L405-L412) writer에 같은 조건이 있다(0.9.0은 source 확인)

`false`를 반환하게 바꾸지 않는 이유는 다음과 같다.

- `handleMessages`의 `false`는 미처리분만 vector에 남기는 계약이다. 기본 `must_succeed=true`는 실패 batch를 먼저 재시도한다
- `[A, 초과 X, B]`에서 A를 쓴 뒤 전체를 `false`로 돌리면 A가 중복된다
- `[X, B]`만 돌려도 X가 계속 실패해 B와 이후 큐가 막힌다
- batch 전체를 미리 거절해도 X가 있는 한 진행하지 못한다
- `must_succeed=no`에서는 정상 suffix까지 lost가 된다

이는 source 계약에서 한 추론이며 혼합 batch fault 시험을 실행한 것은 아니다.

## 고친 동작

정상 설정의 분배·파일 형식·전달 결과는 바꾸지 않는다.

### 원본 오류 세 가지

PR #25가 되돌린 수정 중 분배·파일 형식·전달 결과를 바꾸지 않는다고 리뷰로 확인한 세 가지다.
[남긴 원본 버그](#남긴-원본-버그) 표의 나머지 동작은 원본 그대로다.

#### 동적 목적지의 pooled close 순서

- `periodicCheck`가 새 endpoint를 대입하기 전에 close해 이전 key를 해제한다
- 원본은 `use_conn_pool=yes`에서 새 key를 해제했다. 이전 연결은 refcount가 남아 계속 열려 있었다
- 새 key를 이미 쓰던 다른 store가 있으면 그 연결이 닫혀 그 store의 다음 batch 한 번이 실패·requeue됐다. 없으면 `LOGIC ERROR` 진단만 남았다
- 이제 이전 연결만 닫히고 그 일시 실패가 없다. routing·파일 내용·전달은 같다
- unpooled 경로는 원래 맞아 차이가 없다

#### service_list 재연결 후보

- `loadFromList`가 parse 전에 server 목록을 비운다
- 원본은 재연결마다 전체 목록을 덧붙였다. uptime에 따라 메모리가 늘었다
- 죽은 server를 open마다 K번(각 timeout) 시도해 failover가 점점 느려졌다
- 모든 entry가 같이 중복되므로 server 선택 확률은 1/N으로 같다
- service 기반 경로는 자체 cache로 갱신하며 바뀌지 않았다

#### StdFile partial replay

- `openTruncate`가 `out|trunc`로 연다. 원본 `out|app|trunc`는 열리지 않는다
- 원본은 file primary가 replay batch 일부만 받으면 `replaceOldest`가 항상 실패해 나머지를 lost로 세고 spool 파일을 지웠다
- 이제 나머지를 같은 frame 형식으로 spool에 다시 쓰고 다음 check에 재시도한다
- 전체 거절은 원래 계속 재시도했으므로 부분 실패도 같아진다
- network primary는 batch를 all-or-nothing으로 보내 이 경로에 오지 않는다
- `lost`가 남은 entry 수만큼 줄고(대표 시험 2→0) 정상 frame의 `bytes lost`는 0 그대로다
- spool 파일이 지워지지 않고 남아 이후 전달된다
- `add_newlines=1`이면 기존 writer 규칙대로 다시 쓴 나머지에 LF가 한 번 더 붙는다
- 직접 호출한 `openTruncate`는 없는 파일도 만든다. FileStore는 `findOldestFile`로 먼저 확인한다
- 원자적 교체, crash·쓰기 실패 보존, exactly-once, durable ACK를 새로 약속하지 않는다

### 안전·이식 수정

비정상 종료, 미정의 동작, 빌드 이식 문제다.

| 수정 | 내용 |
| --- | --- |
| spool 읽기 버퍼 | malloc/delete[] 불일치 제거. nothrow new로 받은 `unique_ptr`이며 할당 실패의 손실 집계는 같다 |
| 종료 exit 단일화 | shutdown RPC thread의 `exit`와 main의 return이 static 소멸자를 동시에 돌던 crash를 막는다. 종료 코드 0, `scribe server exiting`, store 정지 순서는 같다 |
| retry jitter 0 | `retry_interval_range=0`과 `adaptive_backoff`의 `max_random_offset=0`은 RNG 없이 jitter 0 |
| 알 수 없는 child store | 만들지 못한 child를 쓰지 않는다. bucket은 설정 오류와 `WARNING`, buffer는 기존 file fallback, multi·category는 실패 상태 |
| `list_default_port` 생략 | port 초기값 0 |
| 추가 bucket 검사 | `num_buckets` 6 이상의 범위 밖 읽기를 건너뛴다 |
| HDFS delete | libhdfs 2·3-인자 API에 맞춘다([HDFS](hdfs.md#api-이식)) |
| `max_msg_per_second` | 초당 개수를 별도 mutex 아래에서 센다. 절반 초과 batch 예외는 원본대로다 |
| C++17 shuffle | 제거된 `random_shuffle`을 GNU forward Fisher–Yates `rand()` loop로 대체. 순서와 다음 `rand()`가 같다 |
| fb303 counter 잠금 | 할당 예외 뒤 counter 잠금이 남지 않게 patch([빌드](build.md#fb303-patch)) |

잠금·수명 정리도 결과를 바꾸지 않는다.

- `Log`의 handler 잠금을 RAII로 소유해 예외에도 풀린다
- bucket updater는 예외에도 잠금을 풀고, Thrift `TException`을 기존 RPC 실패 경로로 처리한다. singleton 조회는 잠금 안에서 한다
- ConnPool의 send·reopen은 map → connection 순서로 잠근다
- 구성 중인 store의 status 조회는 worker의 `cmdMutex`로 직렬화한다
- 큐 byte 합과 `target_write_size`는 atomic snapshot으로 읽는다
- worker·mutex·cond 생성 실패는 만든 자원만 정리한 뒤 설정 오류가 된다
- 설정 트리의 부모 참조는 weak다. `reinitialize`마다 이전 설정이 남지 않는다
- MultiStore의 `report_success` 초기값은 미지정 기본값 `SUCCESS_ALL`이다
- HDFS emulated link의 임시 객체와 handle을 실패 경로에서도 닫는다. 비-HDFS stub의 `getFrame`은 빈 문자열을 돌려준다

## 통신 크기 한도

Thrift 0.25.0의 기본 한도(frame 16,384,000 bytes, message 104,857,600 bytes)는 원본이 받던 큰 요청을 거절한다.
그래서 두 전역 설정을 두고 기본값을 256 MiB로 정했다.

| 키 | 기본값 | 허용 값 |
| --- | --- | --- |
| `thrift_max_frame_size` | 268435456 | 1 ~ 2147483647 |
| `thrift_max_message_size` | 268435456 | 1 ~ 2147483647 |

- 기준은 serialized binary RPC payload bytes이며 앞의 4-byte 길이는 빼고 센다
- 두 값이 다르면 작은 쪽이 실제 한도다. recursion depth 64는 그대로다
- 값은 양의 십진수만 받는다. `0`, 음수, `+`, 빈 값, 16진수, 단위, overflow는 잘못된 값이다
- 잘못된 값이면 `Invalid Thrift wire limits; listener not started`를 남기고 시작에 실패한다(종료 코드 0)
- 시작할 때만 읽는다. `reinitialize`는 `Thrift wire-limit changes require restart`를 남기고 기존 값을 유지한다
- server, accepted socket, 별도 input memory buffer, relay client, mapping client에 같은 값을 적용한다
- relay는 보내기 전 `21 + Σ(15 + category bytes + message bytes)`를 계산한다
- 한도를 넘으면 `Relay Log exceeds configured wire limit <N> bytes`를 남기고 일시 실패로 처리한다. 나누거나 버리지 않고 `sent`도 늘리지 않는다
- buffer 아래면 spool 파일을 지우지 않고 재시도한다. 가장 오래된 파일부터 보내므로 뒤 spool도 멈춘다

한계는 다음과 같다.

- 0.9.0 `TNonblockingServer`의 기본 inbound frame은 256 MiB였고 `TFramedTransport`에는 상한이 없었다. 256 MiB는 무제한 원본 호환을 보장하지 않는다
- 메모리 상한이 아니다. 연결별 read buffer, decode한 문자열, 큐, relay 복사 때문에 RSS가 훨씬 커질 수 있다
- 256 MiB를 넘는 retained spool batch는 계속 실패·재시도한다
- `max_write_size`나 `max_size`를 줄이는 것만으로는 요청 크기가 보장되지 않는다. 계산 예는 README의 [통신 크기 제한](../README.md#통신-크기-제한과-확인한-호환성)에 있다

## 검증 경계

- exact routing·payload, framed clone bytes와 실제 reader, 일반 spool의 구·신 bytes와 loss·counter, 작은 양방향 relay를 각각 확인한다
- 실제 daemon 결과와 component·모의 결과를 구분한다. 결과는 [검증](verification.md)에 있다
- 정상 종료한 구 daemon의 framed 파일을 신 reader로 읽었다(2026-10-06)
- 신 production clone(`use_simple_file=1` 모델)의 파일을 GCC 5.4·C++03·Thrift 0.9 reader로 읽었다. 둘 다 event 2개, 10 bytes `4100420aff656e64730a`
- 일반 spool component 시험은 두 writer·두 reader의 bytes와 원래 truncate·loss 결과를 확인한다
- 작은 대표 RPC의 양방향 성공을 모든 크기·언어 runtime 호환으로 확대하지 않는다
- Python 3/Thrift 0.25 client package는 서버 이식과 별개다. 기존 Python 2 client 환경에 덮어 설치하지 않는다

## 남은 한계와 결정

- 전체 dynamic·설정·store 옵션·fault matrix, 응답 유실·부분 replay의 daemon 시험
- historical HDFS binary, HDFS 빈 폴더·삭제·권한·복제·다중 DataNode 장애
- 구·신 shared daemon 전체 비교, Linux 외 플랫폼
- IDL·wire와 Python 3 packaging 밖의 구 언어 client 조합. 원본 예제 helper는 모두 현대화하지 않았다
- 상세 성능·원인 분석·tuning, 전체 daemon leak·TSan·장기 운영 시험
- 256 MiB를 넘는 retained spool 재시도, ThriftFile empty·chunk 초과 처리

남은 결정은 version·tag와 release artifact, 의존성·ABI·고지를 묶은 배포 패키지, 서비스 배포와 rollback 검증, 상세 성능 비교 시점이다.
