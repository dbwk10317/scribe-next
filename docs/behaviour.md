# 고친 버그와 남긴 버그

README의 [고친 원래 버그](../README.md#고친-원래-버그)와 [일부러 남겨 둔 원래 버그](../README.md#일부러-남겨-둔-원래-버그) 표에 있는 항목을 하나씩 설명합니다.
고치거나 남기기로 한 결정과 근거는 [호환성 정책](compatibility-policy.md)에 있습니다.

- [고친 원래 버그](#고친-원래-버그)
- [일부러 남겨 둔 원래 버그](#일부러-남겨-둔-원래-버그)
  - [먼저: 모델과 복사본](#먼저-모델과-복사본)
  - [그 밖에 원본 그대로인 주의점](#그-밖에-원본-그대로인-주의점)

## 고친 원래 버그

원본의 버그 가운데 로그의 분배·파일 형식을 바꾸지 않고 고칠 수 있는 것과, 사용자가 승인한 예외만 고쳤습니다.
각 항목은 왜 바꿨는지, 무엇을 기대할 수 있는지, 기존과 무엇이 다른지, 관련 설정 키, 예시 순서로 설명합니다.

### spool 읽기 버퍼의 해제 방식

- **왜 바꿨나.**
  buffer store[^buffer]가 spool 파일을 다시 읽을 때 쓰는 메모리를 받는 방법과 돌려주는 방법이 짝이 맞지 않았습니다.
  C++에서 이는 미정의 동작이며 메모리 손상으로 이어질 수 있습니다.
- **기대할 수 있는 것.**
  spool을 다시 읽을 때 이 문제로 인한 메모리 손상 위험이 없습니다.
- **기존과 달라진 점.**
  읽는 내용, 파일 형식, 손실 집계는 같습니다.
  메모리가 모자라 버퍼를 받지 못할 때의 손실 처리도 같습니다.
- **관련 설정 키.**
  `type=buffer`이고 `<secondary>`가 `type=file`(`fs_type=std`, 기본값)인 store입니다.
- **예시.**
  relay 서버가 30분 동안 내려가 spool이 쌓였다가 살아나면, buffer가 spool 파일을 읽어 다시 보냅니다.
  구버전은 그때마다 짝이 맞지 않게 메모리를 돌려줬고, 신버전은 바르게 돌려줍니다.

### retry_interval_range=0의 0 나누기

- **왜 바꿨나.**
  buffer는 재시도 간격에 무작위 값(jitter[^jitter])을 더하는데, 이 값을 범위로 나눈 나머지로 계산합니다.
  범위가 0이면 0으로 나누게 되어 비정상 종료할 수 있었습니다.
- **기대할 수 있는 것.**
  범위가 0이면 무작위 값 없이 `retry_interval` 간격으로 재시도합니다.
- **기존과 달라진 점.**
  범위가 1 이상인 정상 설정의 계산은 같습니다.
  `adaptive_backoff=yes`에 `max_random_offset=0`인 경우도 같은 방식으로 고쳤습니다.
- **관련 설정 키.**
  `retry_interval`, `retry_interval_range`, `adaptive_backoff`, `max_random_offset`.
- **예시.**
  `retry_interval=30`, `retry_interval_range=0`인 buffer의 primary가 연결에 실패했다고 합시다.
  구버전은 다음 재시도 시간을 계산하다 종료될 수 있습니다.
  신버전은 30초 뒤 다시 시도합니다(실제 시각은 `check_interval` 주기만큼 늦을 수 있음).

### 알 수 없는 bucket 하위 store 종류

- **왜 바꿨나.**
  bucket store의 하위 블록에 없는 store 종류를 쓰면, 구버전은 만들지 못한 빈 store를 그대로 써서 비정상 종료할 수 있었습니다.
- **기대할 수 있는 것.**
  설정 오류로 알려 주고 프로세스는 계속 떠 있습니다.
- **기존과 달라진 점.**
  `can't create store of type: netwrok` 같은 설정 오류를 남기고 fb303 상태가 `WARNING`이 됩니다.
  정상 종류를 쓴 bucket의 분배는 같습니다.
- **관련 설정 키.**
  bucket store의 하위 블록(`<bucket1>` 등) 안의 `type`.
- **예시.**
  `<bucket1>` 안에 `type=network`를 `type=netwrok`로 잘못 썼다면, 구버전은 종료될 수 있습니다.
  신버전은 위 오류와 `WARNING` 상태로 오타를 알려 줍니다.

### list_default_port가 없을 때의 port

- **왜 바꿨나.**
  `service_list`에 port 없이 서버 이름만 쓰고 `list_default_port`도 없으면, 구버전은 초기화하지 않은 메모리 값을 port로 썼습니다.
  실행할 때마다 어떤 port로 연결할지 알 수 없었습니다.
- **기대할 수 있는 것.**
  port를 0으로 정하므로 결과가 일정하게 연결 실패입니다.
- **기존과 달라진 점.**
  맞는 port를 자동으로 찾아 주지는 않습니다.
- **관련 설정 키.**
  `service_list`, `list_default_port`.
- **예시.**
  `service_list=relay-a.example relay-b.example`만 쓰면 신버전은 연결에 실패합니다.
  `relay-a.example:1463`처럼 port를 쓰거나 `list_default_port=1463`을 더하세요.

### 추가 bucket 검사의 범위 밖 읽기

- **왜 바꿨나.**
  `bucket0`…`bucketN`을 직접 정의하면 원본은 정의가 더 있는지 검사합니다.
  그런데 이 검사에는 [원본 결함](#추가-bucket-검사는-이름-대신-문자열-중간을-본다)이 있어, `num_buckets`가 6 이상이면 문자열 밖 메모리를 읽었습니다.
- **기대할 수 있는 것.**
  이 경우에도 미정의 동작 없이 시작합니다.
- **기존과 달라진 점.**
  신버전은 이때 검사를 건너뜁니다.
  구·신 모두 추가 bucket을 거부하지 않으므로 정상 분배는 같습니다.
- **관련 설정 키.**
  `num_buckets`, `bucket0`…`bucketN` 블록.
- **예시.**
  `num_buckets=8`로 `<bucket0>`부터 `<bucket8>`까지 정의한 설정을 읽을 때, 구버전은 범위 밖 메모리를 읽습니다.
  신버전은 그대로 시작하고, 로그 분배는 같습니다.

### HDFS 파일 삭제 함수

- **왜 바꿨나.**
  HDFS 라이브러리(libhdfs)의 파일 삭제 함수는 옛 판과 지금 판의 인자 수가 다릅니다.
  그대로는 지금의 libhdfs와 빌드되지 않습니다.
- **기대할 수 있는 것.**
  `fs_type=hdfs`를 쓰는 빌드가 옛 API와 지금 API 모두에 맞게 연결됩니다.
- **기존과 달라진 점.**
  지금 API에는 하위 항목까지 지우는 값(`recursive=1`)을 넘깁니다.
  삭제 결과를 확인하지 않고 로그만 남기는 원본 처리는 같습니다.
  HDFS 오류 처리 전체를 새로 고친 것은 아닙니다.
- **관련 설정 키.**
  `fs_type=hdfs`.
- **예시.**
  Hadoop 3.5의 libhdfs로 HDFS 저장 기능을 빌드하면 원본 소스는 컴파일되지 않지만, 신버전은 빌드됩니다.
  확인한 범위는 [HDFS 안내](hdfs.md)에 있습니다.

### 종료할 때 exit를 한 번만

- **왜 바꿨나.**
  fb303 `shutdown`을 받으면 그 요청을 처리하는 thread가 프로세스 종료를 시작합니다.
  같은 때 main thread도 서버가 멈춘 것을 보고 종료를 시작했습니다.
  두 곳이 동시에 종료 정리를 하면서 드물게 종료 중 비정상 종료(SIGSEGV)가 났습니다.
- **기대할 수 있는 것.**
  종료 정리는 한 번만 일어나고, 다른 쪽은 그 끝을 기다립니다.
  종료 코드는 먼저 종료를 시작한 쪽의 값입니다. [SIGTERM·SIGINT](#sigterm과-sigint로-정상-종료)도 같은 경로를 탑니다.
- **기존과 달라진 점.**
  `shutdown` 뒤의 종료 코드 0과 store를 멈추는 순서는 같습니다.
  원본도 같은 구조였으므로 같은 경쟁이 있을 수 있었습니다.
- **관련 설정 키.** 없습니다.
- **예시.**
  개발 중 구·신 비교 시험에서 신버전이 `shutdown` 뒤 SIGSEGV로 끝나는 것을 한 번 관찰했습니다.
  이 수정에는 그 경쟁을 재현하는 자동 시험이 없습니다.

### max_msg_per_second의 동시 계산

- **왜 바꿨나.**
  `max_msg_per_second`는 1초에 받을 메시지 수의 한도입니다.
  구버전은 여러 요청이 동시에 들어올 때 그 초의 개수를 잠금 없이 고쳤습니다.
  이는 미정의 동작이고, 한도보다 많이 받아들일 수 있었습니다.
- **기대할 수 있는 것.**
  동시에 들어오는 요청도 정확히 셉니다.
- **기존과 달라진 점.**
  요청이 하나씩 들어오면 결과가 같습니다.
  한도 근처에서 동시에 들어온 요청만 받는 개수가 다를 수 있습니다.
  한 요청의 메시지 수가 한도의 절반보다 많으면 항상 받는 [원본 예외](#max_msg_per_second의-절반-예외)는 그대로입니다.
- **관련 설정 키.**
  `max_msg_per_second`(기본 0 = 제한 없음).
- **예시.**
  `max_msg_per_second=1000`이고 그 초에 이미 900개를 받았는데, 100개짜리 요청 두 개가 동시에 들어왔다고 합시다.
  구버전은 둘 다 받을 수 있습니다(합계 1100).
  신버전은 하나를 받고, 다른 하나에는 `TRY_LATER`를 돌려주며 `denied for rate` 카운터를 올립니다.

### 동적 목적지 변경과 연결 pool

- **왜 바꿨나.**
  - `dynamic_config_type=thrift_bucket`인 network store는 bucket updater라는 별도 서버에 목적지를 묻고, 바뀌면 연결을 다시 엽니다.
  - `use_conn_pool=yes`이면 같은 `host:port`로 가는 연결 하나를 여러 store가 함께 쓰고, 사용자 수(refcount[^refcount])로 닫을 때를 정합니다.
  - 구버전은 주소를 새 값으로 먼저 바꾼 뒤 연결을 닫아서, 옛 목적지가 아니라 **새 목적지**의 사용자 수를 줄였습니다.
- **기대할 수 있는 것.**
  목적지가 바뀌면 옛 연결만 닫힙니다.
  같은 목적지를 쓰던 다른 store의 연결이 엉뚱하게 닫혀 batch[^batch]가 한 번 실패하는 일이 없습니다.
- **기존과 달라진 점.**
  - 분배·파일 내용은 같습니다.
  - 구버전에서 엉뚱하게 닫힌 연결 때문에 실패한 batch는 `must_succeed=yes`(기본값)면 다시 보내므로 최종 전달 결과도 같습니다.
  - 그 store가 `must_succeed=no`였다면 구버전은 그 batch를 버리고 `lost`로 셌으므로, 그 경우에는 최종 전달 결과와 `lost` 카운터가 달라집니다.
  - `use_conn_pool=no`(기본값)는 원래부터 자기 연결만 닫았으므로 차이가 없습니다.
  - 구버전이 남기던 `LOGIC ERROR` 진단 로그가 이 경우에는 나오지 않습니다.
- **관련 설정 키.**
  - `use_conn_pool=yes`와 `dynamic_config_type`입니다.
  - `bucket_updater_host`·`bucket_updater_port`(또는 `bucket_updater_service`)와 `bucket_updater_ttl`도 해당합니다.
    bucket updater에는 `bucket_updater_ttl`(기본 60초)마다 다시 묻고, 목적지 확인은 `check_interval`마다 합니다.
  - 모델 복사본은 [동적 조회 설정을 물려받지 않으므로](#network-복사본은-service_list와-동적-조회-설정을-물려받지-않는다) 직접 설정한 store만 해당합니다.
- **예시.**

  ```conf
  # game_purchase의 bucket1은 bucket updater가 알려 주는 서버로 보냅니다.
  <store>
    category=game_purchase
    type=bucket
    num_buckets=1
    bucket_type=key_hash
    delimiter=124

    <bucket0>
      type=file
      fs_type=std
      file_path=/var/log/scribed/purchase-unkeyed
      base_filename=game_purchase
    </bucket0>

    <bucket1>
      type=network
      use_conn_pool=yes
      dynamic_config_type=thrift_bucket
      bucket_updater_host=bucket-mapper.example
      bucket_updater_port=9090
      bucket_updater_ttl=60
    </bucket1>
  </store>

  # game_login은 relay-b.example로 고정 전송하며 같은 연결 pool을 씁니다.
  <store>
    category=game_login
    type=network
    remote_host=relay-b.example
    remote_port=1463
    use_conn_pool=yes
  </store>
  ```

  bucket updater가 `game_purchase` bucket1의 목적지를 `relay-a.example:1463`에서 `relay-b.example:1463`으로 바꾸면:

  | 항목 | 구버전 | 신버전 |
  | --- | --- | --- |
  | 사용자 수를 줄이는 연결 | `relay-b`(새 목적지) | `relay-a`(옛 목적지) |
  | `relay-a` 연결 | 계속 열려 있음 | 다른 사용자가 없으면 닫힘 |
  | `game_login`의 `relay-b` 연결 | 닫혀서 다음 batch 1회 실패 가능 | 영향 없음 |
  | 분배·내용 | 같음 | 같음 |
  | 실패한 batch의 최종 전달 | `must_succeed=yes`: 재전송, `no`: 손실(`lost`) | 실패 없음 |

  - 구버전에서 `game_login`의 연결이 닫히면 다음 batch 1회가 실패해 `requeue` 카운터로 집계되고 다시 연결됩니다.
  - `game_login`이 `must_succeed=no`였다면 그 batch는 `lost`로 집계되고 전달되지 않습니다.
  - 새 목적지를 쓰던 store가 없을 때 구버전은 다음 진단 로그를 남깁니다.

  ```text
  LOGIC ERROR: attempting to close connection <relay-b.example:1463> that connPool has no entry for
  ```

### service_list 재연결

- **왜 바꿨나.**
  - `service_list`를 쓰는 network store는 연결을 열 때마다 목록을 해석해 서버 후보를 만듭니다.
  - 구버전은 이전 후보를 비우지 않고 매번 전체 목록을 뒤에 덧붙였습니다.
  - 그래서 오래 돌수록 메모리가 늘고, 죽은 서버를 여러 번 시도해 다른 서버로 넘어가는(failover[^failover]) 시간이 점점 길어졌습니다.
- **기대할 수 있는 것.**
  재연결 횟수와 관계없이 후보는 목록에 쓴 서버 수만큼이고, 죽은 서버는 한 번만 시도합니다.
- **기존과 달라진 점.**
  구버전은 모든 후보가 똑같이 중복됐으므로, 각 서버가 선택될 확률은 구·신 모두 1/N으로 같습니다.
  `smc_service`를 쓰는 경로는 자체 cache로 목록을 갱신하므로 바뀌지 않았습니다.
- **관련 설정 키.**
  `service_list`, `list_default_port`, `timeout`.
  `use_conn_pool` 값과는 무관합니다.
- **예시.**

  ```conf
  <store>
    category=game_chat
    type=buffer
    retry_interval=30
    retry_interval_range=10

    <primary>
      type=network
      service_list=relay-a.example:1463 relay-b.example:1463 relay-c.example
      list_default_port=1463
      timeout=2000
    </primary>

    <secondary>
      type=file
      fs_type=std
      file_path=/var/log/scribed/spool
      base_filename=game_chat
      max_size=67108864
    </secondary>
  </store>
  ```

  `relay-c.example`이 내려간 상태에서 다섯 번째로 연결을 열 때(실패한 시도 포함)를 비교하면:

  | 항목 | 구버전 | 신버전 |
  | --- | --- | --- |
  | 서버 후보 목록 | 15개(세 서버가 5번씩 중복) | 3개 |
  | 한 번 열 때 `relay-c` 시도 | 최대 5번, 각각 최대 2초 | 최대 1번 |
  | 각 서버가 선택될 확률 | 1/3 | 1/3 |

  `timeout=2000`은 연결 시도 하나의 제한 시간(밀리초)입니다.

### buffer 재전송 일부 성공

- **왜 바꿨나.**
  - buffer store는 primary[^primary]에 보내지 못한 로그를 secondary spool에 모았다가, primary가 살아나면 spool 파일을 하나씩 다시 보냅니다(replay[^replay]).
  - primary가 그 묶음의 앞부분만 처리하고 실패하면, 남은 로그만 spool 파일에 다시 써야 합니다.
  - 그런데 구버전은 이 파일을 여는 방식이 잘못돼 항상 실패했고, 남은 로그를 `lost`로 세고 spool 파일을 지웠습니다(영구 손실).
- **기대할 수 있는 것.**
  남은 로그가 같은 형식으로 spool 파일에 다시 써지고, `retry_interval`이 지난 뒤 다시 보냅니다.
  전체 실패는 원래부터 계속 재시도했으므로, 일부 실패도 같은 방식이 된 것입니다.
- **기존과 달라진 점.**
  spool 파일 형식은 같아 구버전도 읽을 수 있습니다.
  secondary에 `add_newlines=1`이 있으면 기존 기록 규칙대로 다시 쓴 메시지 끝에 LF가 하나 더 붙습니다([같은 원인의 원본 동작](#buffer-secondary의-add_newlines는-재전송-때-줄바꿈을-하나-더-만든다)).
- **관련 설정 키.**
  - `type=buffer`이고 `<secondary>`가 `type=file`(`fs_type=std`, 기본값)인 경우
  - primary가 batch의 일부만 처리할 수 있는 store일 때
    - 대표적인 경우는 `type=file` primary가 쓰는 도중 실패하는 경우입니다(예: 디스크가 가득 참).
    - file store는 `max_write_size` 단위로 나눠 쓰므로, batch가 여러 단위에 걸치면 일부만 쓰일 수 있습니다.
    - `thriftfile`, `bucket`, `category`/`multifile` primary도 같은 경로를 탈 수 있습니다.
  - `type=network` primary는 batch를 통째로 성공하거나 실패하므로 해당하지 않습니다.
- **예시.**

  ```conf
  <store>
    category=game_purchase
    type=buffer
    buffer_send_rate=1
    retry_interval=30
    retry_interval_range=10

    <primary>
      type=file
      fs_type=std
      file_path=/var/log/scribed/data
      base_filename=game_purchase
      max_size=104857600
      add_newlines=1
    </primary>

    <secondary>
      type=file
      fs_type=std
      file_path=/var/log/scribed/spool
      base_filename=game_purchase
      max_size=10485760
    </secondary>
  </store>
  ```

  spool 파일 하나에 메시지 `m1`, `m2`, `m3`가 있고, 재전송 중 primary가 `m1`만 쓰고 실패한 경우:

  | 항목 | 구버전 | 신버전 |
  | --- | --- | --- |
  | 남은 `m2`, `m3` | 다시 쓰지 못함 | spool 파일에 다시 씀 |
  | `game_purchase:lost` 카운터 | +2 | 늘지 않음 |
  | spool 파일 | 삭제됨 | 남았다가 다음 재시도 때 전송 |
  | primary 파일의 최종 내용 | `m1`만, `m2`·`m3`는 영구 손실 | 재시도가 성공하면 `m2`·`m3`도 저장 |

  구버전은 이때 `Failed to open file <...> for writing and truncate` 로그를 남깁니다.
  정상 frame에서는 `bytes lost` 카운터가 구·신 모두 0입니다.
  spool 파일 끝이 [손상](compatibility-policy.md#남긴-원본-버그)돼 있었다면, 신버전은 남은 로그를 다시 쓰며 그 손상 부분을 버리고 spool을 읽을 때 잰 손실을 `bytes lost`로 셉니다.
  이 값은 잘린 끝부분이 아니라 spool 파일 전체 크기입니다(원본 계산 그대로). 예를 들어 29 bytes 파일이면 6 bytes가 잘렸어도 29를 셉니다.
  구버전은 파일을 지울 때 같은 값을 셌습니다. 2026-10-08 전의 신버전은 이 경로에서 세지 않고 버렸습니다.

### 모델 복사본의 큐 포인터

- **왜 바꿨나.**
  - 모델에서 복사한 store는 자기를 가진 store 큐(StoreQueue)를 가리키는 포인터를 갖습니다.
  - 원본은 복사본의 이 포인터를 새 큐로 바꾸지 않아, 복사본이 계속 **모델의 큐**를 가리켰습니다.
  - `new_thread_per_category=yes`에서 `categories=` 목록 모델의 큐는 구성이 끝나면 없어집니다. 그 뒤 복사본이 이 포인터를 쓰면 이미 해제된 메모리를 읽습니다(UB[^ub]).
- **기대할 수 있는 것.**
  복사본과 그 하위 store(buffer의 primary·secondary, bucket·multi·category의 하위 store, 나중에 만드는 category별 복사본)가 모두 자기 큐를 가리킵니다.
- **기존과 달라진 점.**
  지금 코드에서 이 포인터를 쓰는 곳은 buffer의 `flush_streaming` 경로뿐이고, 복사본은 그 값을 [물려받지 않으므로](#buffer-복사본은-flush_streaming과-buffer_bypass_max_ratio를-물려받지-않는다) 정상 설정의 결과는 같습니다.
  `flush_streaming`과 `buffer_bypass_max_ratio`를 복사하지 않는 원본 동작은 그대로입니다.
- **관련 설정 키.**
  `categories=`, `category=default`, prefix 모델, `new_thread_per_category`.
- **예시.**
  `categories=game_chat game_guild`인 `type=buffer` 모델은 시작할 때 두 복사본을 만들고 모델 큐를 없앱니다.
  신버전의 두 복사본은 각자 `game_chat`·`game_guild` 큐를 가리킵니다.

### key_range bucket 계산의 범위 밖 접근

- **왜 바꿨나.**
  `bucket_type=key_range`는 key를 `bucket_range`로 나눈 나머지를 실수(double)로 계산해 bucket 번호를 정합니다.
  `bucket_range`가 2^53보다 크면 반올림 때문에 번호가 `num_buckets + 1`이 될 수 있었고, 없는 bucket을 읽었습니다(UB).
- **기대할 수 있는 것.**
  계산 결과가 마지막 bucket을 넘으면 마지막 bucket(`num_buckets`)으로 보냅니다.
- **기존과 달라진 점.**
  정상 범위의 입력은 같은 bucket으로 갑니다. 달라지는 것은 원본이 범위 밖을 읽던 경우뿐입니다.
- **관련 설정 키.**
  `bucket_type=key_range`, `bucket_range`, `num_buckets`.
- **예시.**
  `bucket_range`가 2^53(약 9×10^15)보다 크고 key가 그 범위의 끝에 아주 가까우면, 원본은 없는 bucket을 읽을 수 있습니다.
  신버전은 그 key를 마지막 bucket에 씁니다.

### HDFS 파일 handle 정리

- **왜 바꿨나.**
  HDFS 파일 객체가 없어질 때 열린 파일을 닫지 않고 연결만 끊었고, 이미 열린 파일을 다시 읽기용으로 열면 앞의 handle을 잃었습니다(자원 누수).
- **기대할 수 있는 것.**
  객체가 없어질 때 열린 파일을 먼저 닫고 연결을 끊습니다. 이미 열린 파일의 읽기 열기는 거부합니다(쓰기 열기와 같은 처리).
- **기존과 달라진 점.**
  HDFS 파일의 내용과 이름은 같습니다. 이 수정 뒤 HDFS를 켠 빌드는 다시 확인하지 않았습니다([HDFS 안내](hdfs.md#api-이식)).
- **관련 설정 키.**
  `fs_type=hdfs`.
- **예시.**
  HDFS file store를 다시 구성하거나 닫을 때 열린 handle이 남지 않습니다.

### SIGTERM과 SIGINT로 정상 종료

- **왜 바꿨나.**
  원본에는 신호 처리 코드가 없어 SIGTERM이나 Ctrl+C(SIGINT)를 받으면 그 자리에서 끝났습니다.
  메모리 큐의 로그를 쓰지 않은 채 끝나므로 `systemctl stop`, `docker stop`, Ctrl+C로 로그를 잃을 수 있었습니다.
- **기대할 수 있는 것.**
  - 두 신호는 fb303 `shutdown`과 같은 순서로 처리합니다. store를 멈추고 큐를 처리한 뒤 서버를 멈추고 종료 코드 0으로 끝납니다.
  - 로그에 `received signal <번호>, shutting down`이 남습니다(SIGTERM은 15, SIGINT는 2).
  - 설정을 읽는 도중 받은 신호는 설정이 끝난 뒤 처리합니다.
  - 정지 중에 다시 받은 신호는 무시합니다. 끝나지 않으면 SIGKILL로 끝내야 합니다.
- **기존과 달라진 점.**
  - 정지 순서와 [정지의 예외](../README.md#4-정지)(재시도를 기다리던 묶음)는 fb303 `shutdown`과 같습니다.
  - SIGKILL, 전원 차단처럼 정리할 기회가 없는 종료는 그대로 큐의 로그를 잃을 수 있습니다([OK의 뜻](#ok는-메모리-큐에-받았다는-뜻이다)).
  - 구버전은 그대로이므로, 구버전 서버는 fb303 `shutdown`으로 멈춰야 합니다.
  - 2026-10-08 사용자 승인을 받아 바꾼 운영 경계입니다. 시작 실패의 종료 코드, `..` category 거부와 함께 승인됐습니다.
- **관련 설정 키.** 없습니다.
- **예시.**
  터미널에서 띄운 `scribed`를 Ctrl+C로 멈추면 `received signal 2, shutting down` 뒤 store가 닫히고 종료 코드 0으로 끝납니다.

### 시작 실패의 종료 코드

- **왜 바꿨나.**
  원본은 listener를 열지 못해 끝날 때도 종료 코드 0을 돌려줬습니다.
  그래서 systemd의 `Restart=on-failure` 같은 실패 감지가 동작하지 않았습니다.
- **기대할 수 있는 것.**
  - 시작 중 예외로 끝나면(port 사용 중, `thrift_max_frame_size=256M`처럼 잘못된 크기 한도 등) `Exception in main: ...`을 남기고 **종료 코드 1**로 끝납니다.
  - fb303 `shutdown`과 SIGTERM·SIGINT로 끝날 때는 0입니다.
- **기존과 달라진 점.**
  - store 설정 오류, 설정 파일을 읽지 못함, [`port` 없음](../README.md#2-시작)은 그대로 프로세스가 끝나지 않고 fb303 상태 `WARNING`으로 계속 떠 있습니다.
  - 그래서 종료 코드만으로는 모든 설정 오류를 알 수 없습니다. fb303 상태·카운터, 열린 port, 실제 파일로 감시하세요.
  - 긴 명령행 옵션의 사용법 출력 뒤 종료는 그대로 0입니다([긴 명령행 옵션](#긴-명령행-옵션은-값을-받지-못한다)).
  - 2026-10-08 사용자 승인을 받아 바꾼 운영 경계입니다.
- **관련 설정 키.**
  `port`, `thrift_max_frame_size`, `thrift_max_message_size`.
- **예시.**
  1463을 이미 다른 프로세스가 쓰고 있으면 신버전은 종료 코드 1로 끝나고, systemd 서비스는 `RestartSec`(예제 unit은 5초) 뒤 다시 시작합니다.

### 동적 category 이름의 상위 폴더 거부

- **왜 바꿨나.**
  - `category=default`나 prefix 모델은 처음 보는 category가 들어오면 그 이름으로 복사본을 만들고, file 계열 store는 `<file_path>/<category>/`에 씁니다.
  - 원본의 이름 검사는 아무것도 거르지 않아, 원격 client가 `../x` 같은 category로 `file_path` 밖에 파일을 만들 수 있었습니다.
  - 원본 동작을 지키는 정책의 예외로, 2026-10-08 사용자 승인을 받아 고친 보안 수정입니다(위 두 항목과 함께 승인된 운영 경계).
- **기대할 수 있는 것.**
  - 이름을 `/`로 나눈 조각 가운데 하나라도 `..`이면 그 category를 만들지 않습니다.
  - 로그 `[<category>] rejecting category with parent-directory component`를 남기고, 메시지는 정의하지 않은 category처럼 버려져 `received bad`가 늘어납니다.
- **기존과 달라진 점.**
  - `..a`, `a..b`처럼 조각 전체가 `..`이 아닌 이름은 받습니다.
  - `a/b`처럼 `/`가 든 이름도 받지만 원본 그대로 저장되지 않습니다. file 모델의 복사본은 `<file_path>/a/b/`를 열고 파일 경로는 `<file_path>/a/b/a/b_00000`이라, 그 부모 폴더가 생기지 않아 아무것도 쓰지 못합니다. 메시지는 `received good`으로 셉니다.
  - 설정 파일에 직접 쓴 category와 `categories=` 목록은 이 검사를 거치지 않습니다.
  - 인증·TLS가 없는 것은 그대로이므로, 신뢰하지 않는 client에 포트를 열지 마세요.
- **관련 설정 키.**
  `category=default`, prefix 모델(`category=game_*`).
- **예시.**
  `category=default` file 모델에 category `../etc`로 보내면 구버전은 `file_path`의 상위 폴더에 폴더와 파일을 만들 수 있습니다.
  신버전은 응답 `OK`를 돌려주되 저장하지 않고 `../etc:received bad`를 1 올립니다.

## 일부러 남겨 둔 원래 버그

기준은 [공개 Facebook Scribe 원본](https://github.com/facebookarchive/scribe/tree/fcd294faffd1e88af1643a3a8c2359c41713f7c2)입니다.

- **무엇을 남겼나.**
  아래 항목은 원본의 버그지만, 고치면 로그가 저장되는 위치·내용·형식, 전달 여부, 상태 조회 결과가 바뀝니다.
- **왜 남겼나.**
  그 결과를 읽는 기존 프로그램(적재·집계 job, 감시 도구)을 지키기 위해 **구버전과 신버전이 똑같이 동작하도록 남겨 두었습니다.**
  고치는 새 옵션도 추가하지 않았습니다.
- **남기지 않은 것.**
  `retry_interval_range=0`처럼 원본이 비정상 종료하던 경우는 남기지 않았습니다([고친 원래 버그](#고친-원래-버그)).
- **읽는 법.**
  각 항목은 어떤 동작인지, 왜 남겼는지, 무엇을 기대하면 되는지, 구·신 차이, 관련 설정 키, 예시 순서로 설명합니다.

### 먼저: 모델과 복사본

여러 항목에 나오는 "복사본"을 먼저 설명합니다.

- **모델.**
  `category=default`, `categories=a b c`, `category=game_*`(끝이 `*`인 prefix)로 쓴 `<store>`는 **모델**입니다.
- **복사본.**
  기본값 `new_thread_per_category=yes`에서는 실제로 로그를 처리하는 store가 category마다 만든 모델의 **복사본**입니다.
  `categories=`의 이름들은 시작할 때, `default`와 prefix는 그 category의 첫 로그가 들어올 때 복사됩니다.
- **복사본의 file store는 이름과 위치가 바뀝니다.**
  - `base_filename`은 무시되고 category 이름을 씁니다.
  - 파일은 `<file_path>/<category>/`에 생깁니다(`sub_directory`가 있으면 `<file_path>/<category>/<sub_directory>/`).
  - buffer의 primary·secondary, multi와 bucket의 하위 store도 각각 같은 규칙으로 복사됩니다.

```conf
<store>
  category=default
  type=file
  fs_type=std
  file_path=/var/log/scribed/data
  base_filename=ignored_name
  rotate_period=daily
  add_newlines=1
</store>
```

2026-10-07에 category `game_login`의 로그가 처음 들어오면 다음 파일이 생깁니다.

```text
/var/log/scribed/data/game_login/game_login-2026-10-07_00000
/var/log/scribed/data/game_login/game_login_current -> game_login-2026-10-07_00000
```

- 같은 설정을 `category=game_login`으로 직접 쓰면 `/var/log/scribed/data/ignored_name-2026-10-07_00000`이 됩니다(category 폴더 없음).
- `new_thread_per_category=no`이면 복사하지 않고 한 store가 모든 category를 받으므로, file store라면 `base_filename` 파일 하나에 모입니다.
- 복사본은 아래 항목처럼 일부 설정을 물려받지 않습니다.

| 항목 | 관련 설정 키 |
| --- | --- |
| [Bucket 복사본의 범위·key 제거](#bucket-복사본은-bucket_range와-remove_key를-물려받지-않는다) | `bucket_range`, `remove_key` |
| [추가 bucket 검사](#추가-bucket-검사는-이름-대신-문자열-중간을-본다) | `num_buckets`, `bucket0`…`bucketN` |
| [ThriftFile 복사본의 형식](#thriftfile-복사본은-use_simple_file을-무시한다) | `use_simple_file` |
| [Network 복사본의 목록·동적 조회](#network-복사본은-service_list와-동적-조회-설정을-물려받지-않는다) | `service_list` 등 6개 |
| [Buffer 복사본의 재전송 중 직접 전송](#buffer-복사본은-flush_streaming과-buffer_bypass_max_ratio를-물려받지-않는다) | `flush_streaming`, `buffer_bypass_max_ratio` |
| [빈 연결 key 공유](#service_list와-use_conn_pool은-빈-연결-key-하나를-같이-쓴다) | `service_list`, `use_conn_pool` |
| [빈 메시지만 든 큐](#빈-메시지만-든-큐는-전달되지-않는다) | `add_newlines`(영향) |
| [OK의 뜻](#ok는-메모리-큐에-받았다는-뜻이다) | 없음 |
| [긴 명령행 옵션](#긴-명령행-옵션은-값을-받지-못한다) | `--config`, `--port` |

### Bucket 복사본은 bucket_range와 remove_key를 물려받지 않는다

- **어떤 동작인가.**
  - bucket store 복사본은 `num_buckets`, `bucket_type`, `delimiter`와 하위 store를 복사하지만, `bucket_range`와 `remove_key`는 복사하지 않습니다.
  - 그래서 복사본에서는 `bucket_type=key_range`의 범위가 0이 되어 **모든 메시지가 bucket 0으로** 갑니다.
  - `remove_key=yes`여도 **key가 메시지에 남습니다.** `key_hash`·`key_modulo`는 분배는 맞지만, key가 남는 점은 같습니다.
- **왜 남겼나.**
  고치면 기존 복사본 로그가 다른 bucket 폴더로 옮겨 가고, 내용에서 key가 빠집니다.
  bucket 폴더별로 파일을 가져가거나, key가 붙은 형식을 파싱하는 프로그램이 다른 결과를 보게 됩니다.
- **무엇을 기대하면 되나.**
  `categories=`·`default`·prefix 모델로 만든 bucket store는 범위 분배와 key 제거를 하지 않는다고 보세요.
  범위 분배나 key 제거가 필요하면 `category=`로 직접 설정합니다.
- **구·신 차이.** 없습니다. 둘 다 같은 폴더에 같은 내용을 씁니다.
- **관련 설정 키.**
  모델 store의 `bucket_range`, `remove_key`(그리고 `bucket_type=key_range`).
- **예시.**

  ```conf
  <store>
    categories=game_score game_rank
    type=bucket
    num_buckets=2
    bucket_type=key_range
    bucket_range=20
    remove_key=yes
    delimiter=124
    bucket_subdir=shard

    <bucket>
      type=file
      fs_type=std
      file_path=/var/log/scribed/score
      base_filename=game_score_all
      add_newlines=1
    </bucket>
  </store>
  ```

  category `game_score`로 메시지 `15|hello`를 보내면(`delimiter=124`는 `|`):

  | 경우 | 선택되는 bucket | 저장 위치 | 저장 내용 |
  | --- | --- | --- | --- |
  | `category=game_score`로 직접 썼다면 | bucket 2 | `score/shard002/game_score_all_00000` | `hello\n` |
  | 위 설정의 실제 결과(복사본) | bucket 0 | `score/shard000/game_score/game_score_00000` | `15\|hello\n` |

  저장 위치는 `/var/log/scribed/` 아래입니다.
  직접 쓴 경우 key 15는 범위 20에서 `15 % 20 = 15`라 bucket 2로 가지만, 복사본은 범위가 0이라 bucket 0으로 갑니다.

### 추가 bucket 검사는 이름 대신 문자열 중간을 본다

- **어떤 동작인가.**
  - `bucket0`부터 `bucketN`까지 직접 정의하면, 원본은 `bucketN+1`이 더 있는지 검사하려고 합니다.
  - 하지만 계산 실수 때문에 이름 대신 **글자 `"bucket"`의 중간부터를 이름으로 찾습니다.**
    `num_buckets=1`이면 `cket`, 2이면 `ket`, 3이면 `et`, 4이면 `t`, 5이면 빈 이름을 찾습니다.
  - 그래서 `bucketN+1`을 정의해도 거부하지 않습니다.
- **왜 남겼나.**
  올바르게 고치면 지금까지 시작되던 설정이 `bucket store has too many buckets defined`로 거부됩니다.
  그러면 그 store 없이 `WARNING` 상태로 뜨게 됩니다.
- **무엇을 기대하면 되나.**
  `num_buckets`보다 많은 bucket 블록을 써도 오류가 나지 않지만, 넘치는 bucket은 로그를 받지 않습니다.
  필요한 bucket 수는 `num_buckets`로 정하고 실제 분배 결과를 확인하세요.
- **구·신 차이.**
  `num_buckets` 1~5에서는 같습니다.
  6 이상에서 구버전은 문자열 밖 메모리를 읽고(미정의 동작), 신버전은 [이 검사를 건너뜁니다](#추가-bucket-검사의-범위-밖-읽기).
  둘 다 거부하지 않습니다.
- **관련 설정 키.**
  `num_buckets`, `bucket0`…`bucketN` 블록.
- **예시.**

  ```conf
  <store>
    category=game_match
    type=bucket
    num_buckets=2
    bucket_type=key_hash
    delimiter=124

    <bucket0>
      type=file
      file_path=/var/log/scribed/match/unkeyed
      base_filename=game_match
    </bucket0>
    <bucket1>
      type=file
      file_path=/var/log/scribed/match/shard1
      base_filename=game_match
    </bucket1>
    <bucket2>
      type=file
      file_path=/var/log/scribed/match/shard2
      base_filename=game_match
    </bucket2>

    # num_buckets=2인데 하나 더 정의: 거부되지 않고, 로그도 받지 않습니다.
    <bucket3>
      type=file
      file_path=/var/log/scribed/match/shard3
      base_filename=game_match
    </bucket3>
  </store>
  ```

  설정은 정상으로 시작합니다(검사는 `ket`이라는 이름을 찾음).
  로그는 `unkeyed`, `shard1`, `shard2`로만 가고 `shard3`에는 쓰이지 않습니다.

### ThriftFile 복사본은 use_simple_file을 무시한다

- **어떤 동작인가.**
  - `type=thriftfile`에 `use_simple_file=1`(0이 아닌 값)을 주면 메시지 내용만 이어 쓰는 raw 형식으로 저장합니다.
  - 그런데 복사본은 이 값을 복사하지 않아, **길이 정보와 chunk 경계 padding이 붙은 framed 형식**으로 저장합니다.
  - category별 복사본을 쓰는 `thriftmultifile`도 같습니다.
- **왜 남겼나.**
  고치면 기존 reader가 읽던 framed 파일 자리에 raw 파일이 생깁니다.
  raw와 framed는 서로 다른 reader가 필요합니다.
- **무엇을 기대하면 되나.**
  모델로 만든 thriftfile 복사본은 항상 framed 형식입니다.
  framed 파일을 읽을 때는 writer와 같은 `chunk_size`를 써야 합니다.
- **구·신 차이.** 없습니다.
- **관련 설정 키.**
  모델 store의 `use_simple_file`, 그리고 읽을 때 맞춰야 하는 `chunk_size`.
- **예시.**

  ```conf
  <store>
    categories=game_chat game_guild
    type=thriftfile
    file_path=/var/log/scribed/tfile
    base_filename=chat_all
    use_simple_file=1
  </store>
  ```

  | 경우 | 저장 위치 | 형식 |
  | --- | --- | --- |
  | `category=game_chat`으로 직접 썼다면 | `/var/log/scribed/tfile/chat_all_00000` | raw |
  | 위 설정의 실제 결과(복사본) | `/var/log/scribed/tfile/game_chat/game_chat_00000` | framed |

- **함께 알아둘 점.**
  - 일반 spool 파일의 형식은 ThriftFile 형식과 별개입니다.
  - 이전 개발 버전이 raw 형식 복사본 파일을 이미 만들었다면 그 파일은 그대로 남습니다.
    지금 버전은 변환하지 않으므로, 같은 폴더에 서로 다른 형식의 파일이 있을 수 있습니다.
    reader를 고르거나 이전 버전으로 되돌리기 전에 실제 파일 형식을 확인하세요.
  - 길이 표시 4 bytes를 포함한 메시지가 `chunk_size`(기본 16,777,216 bytes)보다 크면 오류 로그만 남고 기록되지 않습니다.
    그런데도 Scribe 응답과 성공 집계는 성공으로 보일 수 있습니다(원본 처리 그대로).

### Network 복사본은 service_list와 동적 조회 설정을 물려받지 않는다

- **어떤 동작인가.**
  network store 복사본은 원래 필드인 `remote_host`, `remote_port`, `use_conn_pool`, `timeout`, `smc_service`와 "목록을 쓴다"는 표시만 복사합니다.
  다음 설정은 복사하지 않습니다.

  | 복사하지 않는 설정 | 복사본에서 생기는 일 |
  | --- | --- |
  | `service_list`, `list_default_port` | 목록 문자열이 빈 채로 목록 방식이 남음. 빈 문자열을 나눈 결과인 이름 없는 서버 하나(host `""`, port 0)에 연결을 시도해 `Failed to connect` |
  | `service_options`, `service_cache_timeout` | 기본값(cache 300초) |
  | `ignore_network_error` | 기본값(no) |
  | `dynamic_config_type`과 갱신 | 모델이 받아 둔 주소를 계속 씀 |

  그래서 **`service_list`를 쓰는 모델의 복사본은 구·신 모두 로그를 전달하지 못합니다.**
  예외는 모델이 `use_conn_pool=yes`이고, 직접 설정한 다른 `service_list` store가 [빈 연결 key](#service_list와-use_conn_pool은-빈-연결-key-하나를-같이-쓴다)로 연결을 열어 둔 경우입니다.
  이때는 그 연결(즉 그 store의 목록 서버)로 보냅니다.
- **왜 남겼나.**
  보완하면 전달되지 않던 로그가 갑자기 전달되거나 목적지가 바뀌고, 상태 조회 결과도 달라집니다.
  다음 서버의 데이터 양과 감시 도구가 보던 상태가 바뀝니다.
- **무엇을 기대하면 되나.**
  - `default`·category 모델로 network store를 쓸 때는 `remote_host`/`remote_port`를 쓰거나, category를 직접 설정하세요.
  - 그리고 실제 목적지와 fb303 상태를 확인하세요.
  - 공개 원본의 서비스 이름 조회(`smc_service`)는 항상 실패하는 예제 구현이므로, 실제 서비스 탐색이 된다고 가정하지 마세요.
- **구·신 차이.**
  없습니다. 직접 설정한 store의 동적 조회와 TTL 갱신은 원본대로 동작합니다.
- **관련 설정 키.**
  모델 store의 `service_list`, `list_default_port`, `service_options`, `service_cache_timeout`, `ignore_network_error`, `dynamic_config_type`.
- **예시.**

  ```conf
  <store>
    category=default
    type=buffer
    retry_interval=30
    retry_interval_range=10

    <primary>
      type=network
      service_list=relay-a.example:1463 relay-b.example:1463
      ignore_network_error=yes
    </primary>

    <secondary>
      type=file
      fs_type=std
      file_path=/var/log/scribed/spool
      base_filename=default_spool
      max_size=3000000
    </secondary>
  </store>
  ```

  - 처음 보는 category(예: `game_event`)가 들어올 때마다 복사본이 만들어지지만, 연결할 서버가 없습니다.
  - 로그는 `/var/log/scribed/spool/game_event/game_event_00000`, `_00001`, …에 계속 쌓입니다.
  - `game_event:retries` 카운터가 늘고, fb303 상태는 `WARNING`, 상세 설명은 `Failed to connect`입니다.
  - `ignore_network_error`가 적용되는 경우에도 실제 연결 실패가 성공으로 바뀌지는 않습니다.

### Buffer 복사본은 flush_streaming과 buffer_bypass_max_ratio를 물려받지 않는다

- **어떤 동작인가.**
  - buffer store 복사본은 재시도 간격·`replay_buffer`·adaptive backoff 설정은 복사하지만, `flush_streaming`과 `buffer_bypass_max_ratio`는 복사하지 않습니다.
  - 복사본은 `flush_streaming=no`와 기본 비율로 동작합니다.
  - 즉 spool을 재전송하는 동안 새로 들어온 로그는 primary로 바로 가지 않고 spool에 먼저 쓰인 뒤 순서대로 재전송됩니다.
- **왜 남겼나.**
  보완하면 재전송 중 로그가 primary에 도착하는 순서와 spool 파일의 내용이 달라집니다.
  원본 소스도 같은 구조였습니다.
- **무엇을 기대하면 되나.**
  `default`·category 모델에 `flush_streaming=yes`를 써도 복사본에는 적용되지 않습니다.
  꼭 필요하면 그 category를 직접 설정하세요.
- **구·신 차이.** 없습니다.
- **관련 설정 키.**
  모델 store의 `flush_streaming`, `buffer_bypass_max_ratio`.
- **예시.**
  `category=default`, `type=buffer`, `flush_streaming=yes`인 모델에서 `game_event` 복사본이 spool을 재전송하는 동안 새 `game_event` 로그가 들어오면, 그 로그는 primary로 바로 가지 않고 spool 뒤에 붙어 다음 재전송 때 갑니다.
  같은 설정을 `category=game_event`로 직접 쓰면 primary로 바로 갑니다.

### service_list와 use_conn_pool은 빈 연결 key 하나를 같이 쓴다

- **어떤 동작인가.**
  - `use_conn_pool=yes`인 연결은 이름(key)으로 공유됩니다.
  - `remote_host`/`remote_port`는 `host:port`, `smc_service`는 서비스 이름이 key인데, `service_list`는 **빈 문자열**이 key입니다.
  - 그래서 서로 다른 목록을 쓰는 store들이 **먼저 열린 연결 하나를 같이 씁니다.**
- **왜 남겼나.**
  연결을 목록마다 나누면 전송 대상, 연결 수, 서버 선택 비율이 바뀝니다.
- **무엇을 기대하면 되나.**
  `service_list`가 서로 다른 store에 `use_conn_pool=yes`를 함께 쓰면, 로그가 다른 목록의 서버로 갈 수 있습니다.
  서로 다른 목록을 쓴다면 실제 목적지를 확인하고, 원래 있던 옵션인 `use_conn_pool=no`(기본값)를 검토하세요.
- **구·신 차이.**
  없습니다. 재연결할 때 후보 목록이 늘어나던 문제는 따로 [고쳤습니다](#service_list-재연결).
- **관련 설정 키.**
  `service_list`, `use_conn_pool`.
- **예시.**

  ```conf
  <store>
    category=game_login
    type=network
    service_list=relay-a.example:1463 relay-b.example:1463
    use_conn_pool=yes
  </store>

  <store>
    category=game_chat
    type=network
    service_list=chat-relay-a.example:1463 chat-relay-b.example:1463
    use_conn_pool=yes
  </store>
  ```

  먼저 연결을 연 store의 목록 서버로 두 category가 모두 전송됩니다.
  예를 들어 `game_login`이 먼저 열었다면 `game_chat` 로그도 `relay-a.example`이나 `relay-b.example`로 갑니다.

### 빈 메시지만 든 큐는 전달되지 않는다

- **어떤 동작인가.**
  - store 큐는 쌓인 **메시지 내용의 총 byte 수**를 보고 처리할지를 정합니다.
  - 빈 메시지만 있으면 메시지가 있어도 총 크기가 0이라, 주기 처리 때나 종료할 때 전달하지 않습니다.
  - 서버는 이미 `OK`를 돌려주고 `received good` 카운터를 늘렸는데도, 파일은 비어 있고 `lost` 카운터도 0일 수 있습니다.
- **왜 남겼나.**
  고치면 `add_newlines=1`인 store에 빈 줄이 새로 저장되고 전달 횟수가 달라집니다.
  줄 단위로 읽는 프로그램이 새로운 빈 줄을 보게 됩니다.
- **무엇을 기대하면 되나.**
  - 빈 메시지만 보내는 용도(예: 살아 있음 신호)는 파일에 남지 않는다고 보세요.
  - 같은 큐에 비어 있지 않은 메시지가 함께 들어오면 그때는 빈 메시지도 함께 처리됩니다.
  - 메시지가 하나도 없는 `Log` 요청과는 다른 경우입니다.
- **구·신 차이.** 없습니다.
- **관련 설정 키.**
  특정 키는 없습니다. `add_newlines` 값에 따라 고쳤을 때의 결과가 달라집니다.
- **예시.**

  ```conf
  <store>
    category=game_heartbeat
    type=file
    fs_type=std
    file_path=/var/log/scribed/data
    base_filename=game_heartbeat
    add_newlines=1
  </store>
  ```

  클라이언트가 category `game_heartbeat`로 빈 메시지만 보내면 `OK`를 받고 `game_heartbeat:received good`가 늡니다.
  하지만 `/var/log/scribed/data/game_heartbeat_00000`은 비어 있습니다.
  같은 큐에 비어 있지 않은 메시지가 함께 들어오면, 그때 빈 메시지도 `\n`으로 저장됩니다.

### OK는 메모리 큐에 받았다는 뜻이다

- **어떤 동작인가.**
  - 서버의 `OK` 응답은 로그를 메모리 큐에 받았다는 뜻입니다.
  - 디스크 저장 완료, 다음 서버로의 전달, 중복 없는 전달을 뜻하지 않습니다.
  - 파일 `flush`도 디스크 기록을 강제하는 `fsync`[^fsync]와 다릅니다.
- **왜 남겼나.**
  응답의 뜻을 바꾸면 응답 시점과 처리량이 달라지고, 기존 클라이언트의 재시도 동작에 영향을 줍니다.
- **무엇을 기대하면 되나.**
  - `OK`를 받은 직후 프로세스가 갑자기 끝나면(SIGKILL, 전원 차단 등) 큐에 있던 로그는 남지 않을 수 있습니다.
  - 잃으면 안 되는 로그는 클라이언트 쪽 재전송이나 다른 보존 수단을 함께 생각하세요.
- **구·신 차이.**
  없습니다. 구버전과 신버전 모두 디스크 저장 보장(durable ACK), exactly-once, fsync를 약속하지 않습니다.
- **관련 설정 키.** 없습니다.
- **예시.**
  클라이언트가 메시지 100개를 보내 `OK`를 받은 직후 서버가 SIGKILL로 끝났다고 합시다.
  store thread가 아직 파일에 쓰지 않은 메시지는 구·신 모두 사라집니다.

### 긴 명령행 옵션은 값을 받지 못한다

- **어떤 동작인가.**
  - 원본은 `--config`와 `--port`를 **값을 받지 않는 옵션**으로 선언했습니다.
  - `--config=/etc/scribe/scribe.conf`처럼 쓰면 값을 받지 않는 옵션이라며 사용법만 출력하고 종료(코드 0)합니다.
  - `--config /etc/scribe/scribe.conf`처럼 쓰면 값이 옵션에 전달되지 않습니다.
    원본은 이때 없는 값을 읽어 결과가 정해지지 않았고(UB[^ub], 보통 비정상 종료), 신버전은 사용법을 출력하고 종료(코드 0)합니다.
- **왜 남겼나.**
  명령행 해석 결과도 바깥에서 보이는 동작이므로 긴 옵션이 값을 받지 않는 선언은 원본대로 둡니다.
  없는 값을 읽는 부분은 정해진 결과가 없는 미정의 동작이라 보존 대상이 아니며, 같은 사용법 출력으로 끝나게 했습니다.
- **무엇을 기대하면 되나.**
  항상 짧은 옵션 `-c`, `-p`를 쓰세요.
  옵션이 아닌 첫 인자도 설정 파일로 읽으며, 둘 다 없을 때의 [기본 설정 파일](../README.md#2-시작)은 원본과 같습니다.
- **구·신 차이.**
  `--config=값` 형태는 구·신 모두 사용법 출력 뒤 종료(코드 0)입니다.
  `--config 값` 형태는 구버전이 미정의 동작, 신버전은 사용법 출력 뒤 종료(코드 0)입니다.
- **관련 설정 키.**
  명령행 `--config`, `--port`.
- **예시.**

  ```sh
  scribed -c /etc/scribe/scribe.conf -p 1463
  # 옵션이 아닌 첫 인자도 설정 파일로 읽습니다.
  scribed /etc/scribe/scribe.conf
  ```

### 그 밖에 원본 그대로인 주의점

버그라기보다 원본 설계에서 나오는 동작이며, 구버전과 신버전이 같습니다.
기존 설정을 옮기거나 새로 쓸 때 확인하세요.

#### prefix는 가장 긴 것이 아니라 정렬 순서상 첫 번째가 이긴다

- **어떤 동작인가.**
  - 처음 보는 category는 ① 정확히 같은 이름의 store, ② prefix 모델, ③ `default` 모델 순서로 찾습니다.
  - prefix 모델은 byte 순서로 정렬한 목록에서 **처음 맞는 것**을 쓰며, 가장 길게 맞는 것을 고르지 않습니다.
  - `*`는 영문자·숫자·`_`·`-`보다 앞에 정렬되므로, 겹치는 prefix가 있으면 사실상 짧은 쪽이 이깁니다.
- **예시.**
  `game_*`와 `game_login_*`가 함께 있으면 `game_login_eu`는 `game_*`가 받습니다.

#### new_thread_per_category 기본값은 category마다 thread를 만든다

- **어떤 동작인가.**
  - 기본값 `new_thread_per_category=yes`(정확히 `no`라고 쓴 경우만 꺼짐)에서는 category마다 store 큐와 thread가 하나씩 생깁니다.
  - 각 store는 자기 파일을 열고, `use_conn_pool=no`(기본값)이면 network 연결도 따로 엽니다.
- **예시.**
  `category=default` 모델 하나로 category 300개를 받으면 store thread 300개와 열린 파일 300개 이상이 생깁니다.
- **주의.**
  값을 `no`로 바꾸면 출력 위치가 바뀌므로, 기존 설정의 값을 함부로 바꾸지 마세요.

#### buffer secondary의 add_newlines는 재전송 때 줄바꿈을 하나 더 만든다

- **어떤 동작인가.**
  - buffer의 secondary(spool)에 `add_newlines=1`을 두면, 붙인 LF가 spool frame 안에 함께 저장됩니다.
  - 재전송할 때 받는 쪽 file store에도 `add_newlines=1`이 있으면 `메시지\n\n`이 저장됩니다.
  - 장애 없이 바로 간 로그는 `메시지\n`이므로, **같은 로그가 spool을 거쳤는지에 따라 바이트가 달라집니다.**
- **예시.**

  ```text
  장애 없이 바로 전송:     받는 쪽 파일  6c 6f 67 69 6e 20 6f 6b 0a          "login ok\n"
  spool에 저장된 frame:                09 00 00 00 6c 6f 67 69 6e 20 6f 6b 0a  (길이 9, LF 포함)
  재전송 후 받는 쪽 파일:              6c 6f 67 69 6e 20 6f 6b 0a 0a       "login ok\n\n"
  ```

- **피하는 방법.**
  primary에만 `add_newlines=1`을 두고 secondary에는 두지 않으면 원본 [`examples/example1.conf`](../examples/example1.conf)와 같은 방식이 됩니다.
  이때는 재전송 후에도 `login ok\n` 하나만 저장됩니다.
- **주의.**
  운영 중인 설정을 바꾸면 이미 쌓인 spool의 LF는 그대로이므로, 다운스트림 영향을 먼저 확인하세요.

#### spool 파일 하나가 Log 요청 하나로 재전송된다

- **어떤 동작인가.**
  - buffer는 재전송할 때 **가장 오래된 spool 파일 하나를 통째로 읽어 Log 요청 하나**로 보냅니다.
  - `check_interval`마다 `buffer_send_rate`(기본 1)개 파일을 보내므로, secondary `max_size`가 재전송 요청 하나의 크기를 정합니다.
  - 요청이 [256 MiB 한도](../README.md#통신-크기-제한과-확인한-호환성)를 넘으면 그 파일과 뒤의 파일이 모두 멈춥니다.
- **받는 서버에 생기는 일.**
  - 받는 서버는 큐 크기를 요청을 넣기 **전에** 검사하므로, 큰 요청 하나는 받아들입니다.
  - 하지만 그동안 그 category의 큐가 `max_queue_size`를 넘어, 받는 서버의 모든 클라이언트가 `TRY_LATER`를 받을 수 있습니다.
- **권장.**
  받는 서버의 `max_queue_size`는 보내는 쪽 secondary `max_size`보다 넉넉히 크게 잡으세요.

  ```conf
  # 보내는 서버: secondary max_size=134217728 (128 MiB)
  # 받는 서버가 기본 max_queue_size=5000000(약 4.8 MiB)이면 재전송 요청 하나만으로 큐가 한도를 넘습니다.
  # 받는 서버 최상위 설정 예:
  max_queue_size=268435456
  ```

#### max_queue_size는 모든 category를 한꺼번에 본다

- **어떤 동작인가.**
  - `max_queue_size`(기본 5,000,000 bytes)는 store 큐 하나에 쌓여 아직 처리되지 않은 메시지 내용의 한도입니다.
  - 서버는 Log 요청을 넣기 전에 **모든 category의 모든 store 큐**를 검사합니다.
  - 하나라도 한도를 넘으면 요청에 든 category와 상관없이 요청 전체에 `TRY_LATER`를 돌려줍니다.
- **예시.**
  `game_replay`의 다음 서버가 느려 큐가 넘치면, `game_login`만 보내는 클라이언트도 `TRY_LATER`를 받습니다.
- **카운터.**
  이때 `denied for queue size` 카운터가 늘어나며, 클라이언트는 `TRY_LATER`를 받으면 다시 보내야 합니다.

#### max_msg_per_second의 절반 예외

- **어떤 동작인가.**
  - `max_msg_per_second`(기본 0 = 제한 없음)를 넘으면 요청 전체에 `TRY_LATER`를 돌려주고 `denied for rate` 카운터가 늘어납니다.
  - 단, **한 요청의 메시지 수가 한도의 절반보다 많으면 항상 받고, 그 초의 개수에도 세지 않습니다.**
    큰 요청을 계속 거절하면 그 요청은 영원히 들어올 수 없기 때문입니다.
- **예시.**
  한도가 1000이면 600개짜리 요청은 언제나 받습니다.

#### 주석 기호 #은 줄 어디에서나 동작한다

- **어떤 동작인가.**
  - 설정 파일에서 `#`은 줄 맨 앞이 아니어도 **그 뒤를 모두 주석으로 지웁니다.**
  - 그래서 값 안에 `#`을 쓸 수 없고, 앞뒤 공백과 탭은 지워집니다.
- **예시.**

  ```text
  설정 파일에 쓴 줄                      서버가 읽는 값
  max_size=1000000   # 1 MB              max_size=1000000
  file_path=/var/log/scribed/game#1      file_path=/var/log/scribed/game
  ```

#### use_conn_pool은 host와 port마다 TCP 연결 하나를 공유한다

- **어떤 동작인가.**
  - `use_conn_pool=yes`이면 같은 `host:port`로 보내는 network store들이 TCP 연결 하나를 함께 쓰고, 한 번에 한 store씩 보냅니다.
  - 기본값 `no`에서는 store(복사본 포함)마다 자기 연결을 엽니다.
- **주의.**
  key는 설정에 쓴 문자열 그대로라서, `relay-a.example:1463`과 그 서버의 IP로 쓴 값은 서로 다른 연결입니다.

#### check_interval이 회전 검사와 재시도 주기를 정한다

- **어떤 동작인가.**
  - `check_interval`(기본 5초, 0이면 1초)마다 각 store가 주기 작업을 합니다.
  - 시간 기반 회전 검사, buffer의 재연결 시도와 spool 재전송, 동적 목적지 확인이 모두 이 주기를 따릅니다.
- **예시.**
  `retry_interval=10`, `retry_interval_range=0`이면 "마지막 시도 후 10초 초과"를 5초마다 검사하므로, 실제로는 약 15초마다 재연결을 시도합니다.

#### 빈 메시지가 든 spool은 재전송이 중간에 멈출 수 있다

- **어떤 동작인가.**
  - secondary에 `add_newlines`가 없을 때 빈 메시지는 길이 0인 frame(`00 00 00 00`)으로 저장됩니다.
  - 재전송할 때 spool 읽기는 길이 0인 frame을 **파일 끝으로 여겨 멈추고**, 그때까지 읽은 메시지를 보낸 뒤 파일을 지웁니다.
  - 그 뒤의 메시지는 전달되지 않는데 `lost`·`bytes lost` 카운터는 늘지 않습니다.
- **예시.**

  ```text
  장애 중 spool에 쌓인 메시지 "a", "", "b" (add_newlines 없음)
    01 00 00 00 61 | 00 00 00 00 | 01 00 00 00 62
  재전송: "a"만 보내고 파일 삭제. "b"는 전달되지 않음
  ```

- **피하는 방법.**
  `add_newlines=1`이면 빈 메시지가 `0a` 한 byte로 저장되어 이 문제는 없지만, [줄바꿈이 하나 더 생깁니다](#buffer-secondary의-add_newlines는-재전송-때-줄바꿈을-하나-더-만든다).
  근거는 [호환성 정책](compatibility-policy.md#남긴-원본-버그)에 있습니다.

#### 그 밖의 주의점

- **설정 파서는 잘못된 설정을 모두 거부하지 않습니다.**
  준비되지 않은 store가 있어도 listener가 열리고 `OK`를 돌려줄 수 있습니다.
- **정의하지 않은 category의 로그는 버려집니다.**
  `received bad` 카운터가 늘어나고, category가 빈 로그는 `received blank category`로 셉니다.
  모델이 있어도 이름 조각이 `..`인 category는 [거부되어](#동적-category-이름의-상위-폴더-거부) 같은 카운터로 셉니다.
- **`TRY_LATER`[^trylater]는 보통 요청 전체를 받지 않았다는 뜻입니다.**
  다만 종료 중 처음 보는 category를 만드는 경우에는 앞 메시지 일부가 이미 큐에 들어간 뒤 돌아올 수 있습니다.
  클라이언트가 다시 보내면 그 일부는 중복될 수 있습니다. 원본과 같은 동작입니다.
- **`_current`의 형태.**
  일반 파일 저장에서는 symlink지만, HDFS에서는 경로를 담은 일반 파일입니다.
- **HDFS 저장은 spool 재전송을 지원하지 않습니다.**
  원본 HDFS의 파일 읽기와 닫힌 파일 잘라내기에는 제한이 남아 있습니다.

[^trylater]: TRY_LATER: `Log` 요청의 결과 값 중 하나로, "지금은 받을 수 없으니 나중에 다시 보내라"는 뜻입니다.
  클라이언트가 요청을 다시 보내야 합니다([예외](#그-밖의-주의점)).
[^ub]: UB(Undefined Behavior, 미정의 동작): C/C++ 표준이 결과를 정하지 않은 동작입니다.
  실행할 때마다 결과가 다르거나 비정상 종료할 수 있어, 원본과 "같은 결과"를 재현할 수 없습니다.
[^buffer]: buffer store: primary(주 목적지)로 보내다 실패하면 secondary(보조 저장소, 보통 spool 파일)에 모았다가, primary가 살아나면 다시 보내는 store입니다.
[^jitter]: jitter: 여러 서버가 같은 순간에 몰려 재시도하지 않도록, 재시도 시간에 더하는 작은 무작위 값입니다.
[^refcount]: refcount(참조 수): 하나의 자원(여기서는 TCP 연결)을 몇 곳에서 쓰고 있는지 세는 숫자입니다.
  0이 되면 아무도 쓰지 않는다고 보고 자원을 닫습니다.
[^batch]: batch: 여러 메시지를 한 번에 묶어 처리하거나 보내는 단위입니다.
[^failover]: failover: 연결하려던 서버가 응답하지 않을 때 목록의 다른 서버로 넘어가는 것입니다.
[^primary]: primary/secondary: buffer store 안의 두 하위 store입니다.
  primary는 평소 로그를 보내는 곳(보통 다음 Scribe 서버), secondary는 primary가 실패할 때 로그를 모아 두는 곳(보통 spool 파일)입니다.
[^replay]: replay(재전송): secondary에 모아 둔 로그를 primary가 살아난 뒤 다시 보내는 것입니다.
[^fsync]: fsync: 운영체제 메모리에 있는 파일 내용을 디스크에 실제로 기록하도록 강제하는 호출입니다.
  `flush`는 프로그램의 버퍼를 운영체제로 넘길 뿐이라, 전원이 꺼지면 내용이 사라질 수 있습니다.
