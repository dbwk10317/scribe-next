# 호환성 정책

기준 원본 `fcd294faffd1e88af1643a3a8c2359c41713f7c2`. 결정 날짜는 절마다 적는다.

구→신·신→구 송수신과 기존 로그 소비 client의 계약을 우선한다.
로그의 분배·내용·파일 형식·전달·손실 집계·상태 조회를 바꾸던 semantic 수정은 2026-10-06 사용자 결정으로 원본의 정의된 동작으로 되돌렸다(PR #25).
그중 세 가지는 2026-10-07 승인으로 다시 고쳤다([원본 오류 세 가지](#원본-오류-세-가지)).
2026-10-08에는 정지·종료 코드·동적 category 이름의 [운영 경계](#운영-경계-2026-10-08)를 바꿨다.
되돌린 버그는 이 문서에 남기고, 고치는 새 옵션은 만들지 않는다.
UB·crash 방지와 빌드 이식은 유지한다. 원본 UB에는 보존할 정의된 결과가 없다.
사용자용 설명과 예시는 [고친 버그와 남긴 버그](behaviour.md)에 있다.

## 남긴 원본 버그

| 경로 | 원본 결과와 위험 |
| --- | --- |
| BucketStore copy | `remove_key`·`bucket_range`를 복사하지 않는다. key_range clone은 원본 bucket0 routing과 key 포함 bytes를 유지한다 |
| ThriftFileStore copy | `use_simple_file`을 복사하지 않아 clone은 framed다. 직접 설정한 simple store만 raw다 |
| NetworkStore copy | 원래 field만 복사한다. list·옵션·cache·ignore-error·dynamic updater를 상속하지 않아 전송 실패·warning이나 모델 endpoint 사용이 남는다. `listBased=true`는 복사하고 `serviceList`는 복사하지 않아 `loadFromList("")`가 빈 token 하나(host `""`, port 0)를 만들고, 연결이 실패해 `Failed to connect`가 된다 |
| BufferStore copy | `flush_streaming`·`buffer_bypass_max_ratio`를 복사하지 않는다. clone은 `flush_streaming=no`와 기본 비율로 동작해 replay 중 새 메시지가 spool을 거친다 |
| service_list pool key | 빈 pool key를 공유한다. 서로 다른 list가 첫 연결을 공유할 수 있다 |
| empty-only queue | payload byte 합이 0이면 주기 처리·종료 때 전달하지 않는다. `OK`·received여도 output·lost가 0일 수 있다 |
| 추가 bucket 검사 | 원본 literal pointer 길이 안의 suffix만 검사한다. `bucketN+1`을 새로 거절하지 않는다 |
| spool의 빈 frame | `add_newlines` 없는 secondary의 빈 메시지는 길이 0 frame이다. replay는 이를 EOF로 보고 앞부분만 보낸 뒤 파일을 지운다. 뒤 메시지는 전달되지 않고 lost가 늘지 않는다 |
| spool의 손상 frame | 짧은 header·orphan category도 정상 끝으로 처리한다. 정상 entry 뒤 payload가 잘리면 파일 전체 크기를 `bytes lost`로 센다 |
| 열린 spool 삭제 | `deleteOldest`는 writer를 닫지 않고 경로를 지운다. 이후 쓰기는 unlink된 inode로 갈 수 있다 |
| 긴 CLI 옵션 | `--config`·`--port`는 값을 받지 않는다. 원본이 `--config FILE`·`--port N`에서 NULL `optarg`를 읽던 UB는 `--config=FILE`과 같은 사용법 출력·종료 코드 0으로 대신한다. `-c`·`-p`는 같다. 이 NULL 경로의 회귀 시험은 없다 |
| `reinitialize` 설정 예외 | 기존 store를 먼저 멈춘 뒤 새 설정을 읽는다. port 없음, 잘못된 `num_thrift_server_threads` 같은 예외가 나면 다음 `reinitialize`까지 store 0개·`WARNING`이다. scribe-next 키 `thrift_max_frame_size`·`thrift_max_message_size`도 매번 읽고 검증하므로 잘못된 값이 같은 경로를 탄다([통신 크기 한도](#통신-크기-한도)) |

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

아래 [세 가지](#원본-오류-세-가지)는 승인된 호환성 예외다. [운영 경계](#운영-경계-2026-10-08)는 정지·종료 코드·동적 category 이름에서 원본과 결과가 다르다.
[안전·이식 수정](#안전이식-수정)은 정상 설정에서 결과가 같다.

### 원본 오류 세 가지

PR #25가 되돌린 수정 중 세 가지를 2026-10-07 사용자 승인으로 다시 넣었다(`8a93664`, PR #48).
분배와 파일 형식은 같지만, 그 조건에서는 전달 결과와 `lost`·`requeue` 카운터 값이 원본과 달라진다.
`8a93664` commit 메시지의 "delivery outcome을 바꾸지 않는다"는 틀렸다. 전달 결과·카운터가 달라진다는 정정은 `28a4d9a`(PR #63)에서 했다.
[남긴 원본 버그](#남긴-원본-버그) 표의 나머지 동작은 원본 그대로다.

#### 동적 목적지의 pooled close 순서

- `periodicCheck`가 새 endpoint를 대입하기 전에 close해 이전 key를 해제한다
- 원본은 `use_conn_pool=yes`에서 새 key를 해제했다. 이전 연결은 refcount가 남아 계속 열려 있었다
- 새 key를 이미 쓰던 다른 store가 있으면 그 연결이 닫혀 그 store의 다음 batch 한 번이 실패·requeue됐다. 없으면 `LOGIC ERROR` 진단만 남았다
- 원본에서 그 batch는 `must_succeed=yes`면 `requeue`, `no`면 `lost`로 세졌다. 이제 이전 연결만 닫히고 그 일시 실패가 없어 바로 전달된다. routing·파일 형식은 같다
- unpooled 경로는 원래 맞아 차이가 없다

#### service_list 재연결 후보

- `loadFromList`가 parse 전에 server 목록을 비운다
- 원본은 재연결마다 전체 목록을 덧붙였다. uptime에 따라 메모리가 늘었다
- 죽은 server를 open마다 K번(각 timeout) 시도해 failover가 점점 느려졌다
- 모든 entry가 같이 중복되므로 server 선택 확률은 1/N으로 같다
- service 기반 경로는 자체 cache로 갱신하며 바뀌지 않았다

#### StdFile partial replay

- `openTruncate`가 `out|trunc`로 연다. 원본 `out|app|trunc`는 열리지 않는다
- 원본은 primary가 replay batch 일부만 받으면(file·thriftfile primary, 일부 bucket만 실패한 bucket primary 등) `replaceOldest`가 항상 실패해 나머지를 `lost`로 세고 spool 파일을 지웠다
- 이제 나머지를 같은 frame 형식으로 spool에 다시 쓰고 다음 check에 재시도한다
- 전체 거절은 원래 계속 재시도했으므로 부분 실패도 같아진다. 원본이 `lost`로 세고 버리던 나머지가 이제 전달된다
- network primary는 batch를 all-or-nothing으로 보내 이 경로에 오지 않는다
- `lost`가 남은 entry 수만큼 줄고(대표 시험 2→0) 정상 frame의 `bytes lost`는 0 그대로다
- 손상된 끝부분이 있던 spool이면 truncate가 그 부분을 버린다. 그때 `readOldest`가 잰 손실을 `bytes lost`로 올린다(`85c24b5`). 원본은 `deleteOldest`에서 같은 값을 셌고, 그 전의 scribe-next는 이 경로에서 세지 않았다
- 그 손실 값은 잘린 끝부분이 아니라 spool 파일 전체 크기다. 짧은 읽기 뒤 `tellg`가 -1이라 `StdFile::calcLoss`가 `-fileSize()`로 대신한다. `deleteOldest`와 `replaceOldest`가 한 번만 센다(시험: 29 bytes 파일에서 6이 아니라 29)
- spool 파일이 지워지지 않고 남아 이후 전달된다
- `add_newlines=1`이면 기존 writer 규칙대로 다시 쓴 나머지에 LF가 한 번 더 붙는다
- 직접 호출한 `openTruncate`는 없는 파일도 만든다. FileStore는 `findOldestFile`로 먼저 확인한다
- 원자적 교체, crash·쓰기 실패 보존, exactly-once, durable ACK를 새로 약속하지 않는다

### 운영 경계 (2026-10-08)

2026-10-08 사용자 승인 운영 경계다. 아래 세 가지는 원본 동작을 지키는 이 정책의 예외로 고쳤다("일부러 남긴 버그 중 다시 볼 것도 처리해줘").
`c226849`에서 바꿨다. 로그의 분배·내용·파일 형식은 같고, 정지 결과·종료 코드·만들 수 있는 폴더가 원본과 다르다.
세 동작은 실제로 빌드한 scribed로 `test/test_scribe_api_compat.py`가 확인한다(설치본·Docker 이미지가 아니다). Docker 이미지의 신호·종료 코드 확인은 [검증](verification.md#리뷰-수정-뒤-재검증-2026-10-08)에 있다.

#### SIGTERM·SIGINT 정지

- main이 다른 thread를 만들기 전에 두 신호를 막는다. 이후 thread는 그 mask를 물려받는다
- `initialize()` 뒤에 시작한 `sigwait` thread가 신호를 받아 `received signal <n>, shutting down`을 남기고 fb303 `shutdown`과 같은 경로(store 정지·flush, 서버 정지)를 탄다. 종료 코드는 0이다
- 구성 중에 온 신호는 pending으로 남았다가 구성이 끝난 뒤 처리된다. 구성 중인 store를 멈추지 않는다
- 정지 중의 두 번째 신호는 받는 thread가 없어 무시된다. 마지막 수단은 SIGKILL이다
- `shutdown()`은 서버가 아직 publish되지 않았으면 서버 정지를 건너뛴다. `setServer`는 handler write lock 아래에서 publish한다
- 서버는 Thrift `preServe()`, 즉 `serve()`가 IO thread를 다 만든 뒤에 handler에 publish한다. 시작 중에 온 신호의 `stop()`이 서버 초기화와 경합하지 않는다
- 원본은 신호 처리 코드가 없어 flush 없이 끝났다. 그래서 Ctrl+C, `docker stop`, `systemctl stop`이 이제 큐를 처리한다
- 구버전은 그대로이므로 구버전 정지는 fb303 `shutdown`을 쓴다

#### 시작 실패의 종료 코드

- `scribe::stopServer(code)`는 처음 부른 쪽의 코드로 한 번만 `exit`한다
- startup에서 예외가 빠져나오면(listener bind 실패, 잘못된 `thrift_max_frame_size`·`thrift_max_message_size`) `Exception in main: ...` 뒤 종료 코드 1이다. 원본은 0이었다
- `shutdown` RPC와 신호는 0이다. 긴 CLI 옵션의 사용법 출력도 그대로 0이다
- store 설정 오류, 설정 파일 읽기 실패, port 없음은 그대로 프로세스가 남고 `WARNING`이다
- 그래서 systemd `Restart=on-failure`가 listener 실패를 다시 시도한다

#### 동적 category 이름의 상위 폴더 조각

- 위 승인에 든 보안 수정이다
- 원본 `createCategoryFromModel`의 이름 검사는 POSIX에서 아무것도 거르지 않았다. default·prefix 모델이 file·thriftfile 계열이면 원격 client가 `../x` 같은 category로 `file_path` 밖에 파일을 만들 수 있었다
- 이제 `/`로 나눈 조각 중 하나라도 정확히 `..`이면 거부한다. `[<category>] rejecting category with parent-directory component`를 남기고 그 메시지는 `received bad`다. `..x`처럼 조각 전체가 `..`이 아니면 받는다
- `/`가 든 category(예: `a/b`)는 원본 그대로다. file 모델에서 받아들여 `received good`이 되지만, 복사본은 `data/a/b/`를 열고 파일 경로는 `data/a/b/a/b_00000`이라 그 부모 폴더가 생기지 않아 아무것도 쓰지 못한다
- 설정에 직접 쓴 category와 `categories=` 목록은 이 검사를 거치지 않는다
- 인증·TLS는 여전히 없다. 신뢰하지 않는 client에 scribed를 노출하지 않는다

### 안전·이식 수정

비정상 종료, 미정의 동작, 빌드 이식 문제다.

| 수정 | 내용 |
| --- | --- |
| spool 읽기 버퍼 | malloc/delete[] 불일치 제거. nothrow new로 받은 `unique_ptr`이며 할당 실패의 손실 집계는 같다 |
| 종료 exit 단일화 | shutdown RPC thread의 `exit`와 main의 return이 static 소멸자를 동시에 돌던 crash를 막는다. 먼저 부른 쪽의 코드로 한 번만 끝난다. `shutdown` 뒤 종료 코드 0, `scribe server exiting`, store 정지 순서는 같다 |
| retry jitter 0 | `retry_interval_range=0`과 `adaptive_backoff`의 `max_random_offset=0`은 RNG 없이 jitter 0 |
| 알 수 없는 child store | 만들지 못한 child를 쓰지 않는다. bucket은 설정 오류와 `WARNING`, buffer는 기존 file fallback, category는 실패 상태다. multi는 status를 세우고 구성을 멈춘다. 앞서 만든 child는 계속 받고 전달하며, 뒤 child는 만들지 않는다. 잘못된 `report_success`나 child 0개인 multi는 메시지를 받되 전달하지도 lost로 세지도 않는다. 이런 모델에서 복사한 queue는 status를 복사하지 않아 `ALIVE`로 보인다(원본 그대로) |
| `list_default_port` 생략 | port 초기값 0 |
| 추가 bucket 검사 | `num_buckets` 6 이상의 범위 밖 읽기를 건너뛴다 |
| key_range bucket | `bucket_range`가 2^53보다 크면 double 반올림으로 `num_buckets + 1`이 나와 bucket vector 밖을 읽었다(원본도 같음). 결과를 마지막 bucket으로 자른다. 정상 입력의 routing은 같다(`85c24b5`) |
| 복사본의 StoreQueue 포인터 | 모델에서 복사한 store tree(buffer·bucket·multi·category child와 이후 category별 복사본)를 `Store::setStoreQueue`로 소유 queue에 다시 묶는다. `categories=` 모델 queue가 파괴돼도 dangling back-pointer가 남지 않는다(`85c24b5`). 그 포인터를 쓰는 `flush_streaming` 경로는 위 BufferStore copy 행대로 여전히 복사본에 오지 않는다 |
| HDFS delete | libhdfs 2·3-인자 API에 맞춘다([HDFS](hdfs.md#api-이식)) |
| HDFS handle | 소멸자는 열린 파일을 닫은 뒤 연결을 끊고, `openRead`는 이미 열린 파일을 거부한다(누수 수정, `c226849`) |
| `max_msg_per_second` | 초당 개수를 별도 mutex 아래에서 센다. 절반 초과 batch 예외는 원본대로다 |
| C++17 shuffle | 제거된 `random_shuffle`을 GNU forward Fisher–Yates `rand()` loop로 대체. 순서와 다음 `rand()`가 같다 |
| fb303 counter 잠금 | 할당 예외 뒤 counter 잠금이 남지 않게 patch([빌드](build.md#fb303-patch)) |

잠금·수명 정리도 정상 설정의 결과를 바꾸지 않는다.

- `Log`의 handler 잠금을 RAII로 소유해 예외에도 풀린다
- StoreQueue의 `msgMutex`·`cmdMutex`도 scope guard가 푼다. 큐 push의 할당 예외 뒤 mutex가 잠긴 채 남지 않는다. `test/cpp/queue_lock_exceptions.cpp`가 `addMessage`의 message push(`msgMutex`)와 `open()`의 명령 push(`cmdMutex`, `CMD_OPEN`)를 모두 확인한다
- 생성 뒤 `stop()` 없이 파괴되는 StoreQueue(handler 등록 중 할당 예외)는 소멸자가 `stopping`만 세우고 worker를 깨워 join한 뒤 mutex를 파괴한다. 명령 push 없이 `stop()`과 같은 종료 순서를 따르며, 정상 `stop()` 뒤에는 아무것도 하지 않는다
- 그 경로의 worker는 store를 한 번도 구성·open하지 않았으면 마지막 `close()`를 건너뛴다. 미구성 BufferStore의 `close()`는 null primary를 역참조하기 때문이다. 등록된 queue는 `stop()` 전에 언제나 `CMD_CONFIGURE`나 `CMD_OPEN`을 처리하므로 정상 종료의 `close()`는 같다. `test/cpp/queue_init_failures.cpp` step 6은 open 전 `close()`가 불리면 fixture가 abort해 이 경로를 확인한다
- Multi·Category `copy()`는 새 store를 먼저 `shared_ptr`에 맡기고 child를 복사한다. child 복사 예외에 부모·앞선 child가 새지 않는다. 예외 경로의 회귀 시험은 없다(`test/cpp/store_review_contracts.h`는 정상 copy만 본다)
- bucket updater는 예외에도 잠금을 풀고, Thrift `TException`을 기존 RPC 실패 경로로 처리한다. singleton 조회는 잠금 안에서 한다
- ConnPool의 send는 map → connection 순서로 잠근다. close는 map 아래에서 마지막 사용자의 connection을 잠근다
- ConnPool의 open은 map 잠금을 쥔 채 connection 잠금을 기다리지 않는다. send는 RPC 하나 내내 connection 잠금을 쥐므로, 기다리면 모든 key의 pool 작업이 멈췄다. map을 푼 뒤 그 connection 잠금만 쥐고 상태를 보고, map을 다시 잠가 entry가 같은지 확인한다. 그사이 닫히거나 바뀌었으면 처음부터 다시 판단한다(`c226849`)
- relay `send`는 batch 크기를 다 더한 뒤 wire limit을 한 번 검사한다. 결과와 로그 문구는 같다
- StoreQueue의 status 조회는 잠그지 않는다. worker는 첫 `CMD_CONFIGURE`나 `CMD_OPEN`(모델에서 복사한 queue는 `CMD_OPEN`만 받는다)으로 store를 구성·open한 뒤 atomic flag를 release로 세운다. 조회는 그 flag를 acquire로 본 뒤에만 store status를 읽고, 그 전에는 빈 문자열(상태 `ALIVE`로 집계)을 돌려준다
- 그래서 production에서는 미구성 BufferStore의 status에 닿지 않는다. 시험 등에서 미구성 BufferStore의 `getStatus`를 직접 부르면 `Buffer store is not configured`를 돌려준다(그 시험이 이 문구를 요구한다)
- worker의 `cmdMutex` 범위는 원본과 같다. status 조회가 구성이나 `periodicCheck`(spool replay·재연결)를 기다리지 않는다. 원본은 이 짧은 구성 창에서 잠금 없이 구성 중인 store를 읽었고, upstream BufferStore는 그때 null primary를 역참조했다
- 큐 byte 합과 `target_write_size`는 atomic snapshot으로 읽는다
- worker·mutex·cond 생성 실패는 만든 자원만 정리한 뒤 설정 오류가 된다
- 동적 category의 StoreQueue를 모델에서 만들지 못하면(thread·mutex 생성, 모델 copy 실패) `failed to create category store from model`을 남기고 그 batch에 `TRY_LATER`를 돌려주며 `denied for store creation`(category와 `scribe_overall`)을 센다. 앞선 모델로 만든 store는 멈추고 category 등록을 되돌려 다음 요청이 처음부터 다시 만든다. batch의 앞 메시지는 이미 큐에 들어가 재전송 때 중복될 수 있다(종료 중 `TRY_LATER`와 같다). `..` 거부는 그대로 `received bad`와 `OK`다
- 원본은 `pthread_create` 결과를 보지 않아 이 실패에서 로그가 조용히 사라졌다. 정의되지 않던 실패 경로를 정한 것이며 wire·IDL은 같다
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
- 시작할 때 값이 잘못되면 `Invalid Thrift wire limits; listener not started`를 남기고 시작에 실패한다(종료 코드 1, [운영 경계](#시작-실패의-종료-코드))
- 시작 때와 매 `reinitialize` 때 읽고 검증한다. 서버와 client에는 시작 때 값만 적용한다. `reinitialize`에서 값이 바뀌면 `Thrift wire-limit changes require restart`를 남기고 기존 값을 유지한다
- `reinitialize` 때 값이 잘못되면 설정 예외가 된다. 기존 store는 이미 멈춘 뒤라 다음 `reinitialize`까지 store 0개·`WARNING`이다([남긴 원본 버그](#남긴-원본-버그)의 `reinitialize` 행). 원본에 없던 키가 더한 실패 경로이며 고치지 않고 기록한다
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
