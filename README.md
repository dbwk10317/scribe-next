# scribe-next

**기존 Facebook Scribe를 최신 Linux에서 빌드하고 실행할 수 있도록 옮기는 프로젝트입니다.**
Scribe의 로그 수집 구조, 설정 형식, Thrift 통신과 저장 파일 형식을 유지하는 것이 목표입니다.
실행 파일 이름도 기존과 같은 `scribed`입니다.

원본과 새 서버를 섞어 쓰는 전송과 파일 읽기를 대표적인 조건에서 비교했습니다.
모든 설정과 장애 상황에서 완전히 같거나 운영 환경에서 충분히 검증됐다는 뜻은 아닙니다.
현재 지원 범위와 남아 있는 원본 버그는 아래에서 설명합니다.

## 목차

- [유지하는 기능](#유지하는-기능)
- [지원 환경](#지원-환경)
- [빠른 시작](#빠른-시작)
- [기존 설정과 클라이언트 사용](#기존-설정과-클라이언트-사용)
- [업데이트와 되돌리기](#업데이트와-되돌리기)
- [관련 문서](#관련-문서)
- [라이선스](#라이선스)
- [별첨: 원본 버그와 호환성](#별첨-원본-버그와-호환성)

## 유지하는 기능

- 기존 Thrift IDL, 요청·응답 형식과 fb303 상태 조회 API
- category별 로그 분배, 파일 저장, 다른 Scribe 서버로의 전송
- 파일로 임시 보관한 로그의 재전송, 파일 회전과 다시 열기
- `file`, `buffer`, `network`, `bucket`, `null`, `multi`, `category`, `thriftfile`, `multifile`, `thriftmultifile` 저장 방식
- 기존 설정 이름, 파일 이름, 줄바꿈 처리와 `_current` 파일 표시

서버의 `OK` 응답은 로그를 메모리 큐에 받았다는 뜻입니다.
디스크 저장 완료나 중복 없는 전달을 보장하지 않습니다. 파일 `flush`도 `fsync`와 다릅니다.

## 지원 환경

실제로 빌드와 실행을 확인한 환경입니다.

| 항목 | 확인한 환경 |
| --- | --- |
| 운영체제 | Linux x86_64: Debian 13, Ubuntu 26.04.1; Rocky 8.10 / 9.8 기본 빌드·임시 설치 |
| C++ | C++17, GCC 8.5 / 11.5 / 14.2 / 15.2 |
| 통신 라이브러리 | Thrift compiler와 C++ runtime 0.25.0, 이에 맞춰 준비한 fb303 |
| 기타 빌드 도구 | Boost 1.83의 system/filesystem, libevent, pthread, make, autoconf, automake, libtool, Git |
| Python 설치 검사 | Python 3.12 / 3.14, setuptools와 해당 Thrift/fb303 Python runtime |
| 선택 기능 | 공유 RPC 라이브러리, Hadoop 3.5/libhdfs와 JDK 17을 사용하는 HDFS |

Rocky의 기본 비-HDFS/static 검증은 각 218개 시험과 임시 설치까지 확인했습니다.
[Rocky 빌드 안내](docs/rocky-build.md)의 별도 준비 조건을 따르세요.
Rocky의 daemon 전용 [개발 RPM](docs/rocky-rpm.md)은 격리 설치·송수신·정상 종료·동일 RPM 재설치·제거까지 확인했습니다.
Rocky shared RPC는 source 빌드·218개 회귀·임시 설치 loader까지 확인했습니다.
Rocky HDFS, 서로 다른 RPM 버전 간 upgrade와 운영 배포는 아직 검증하지 않았습니다.

HDFS는 하나의 DataNode로 구성한 테스트에서 파일 쓰기·다시 열어 추가 쓰기와
Hadoop client로 저장 내용을 읽는 것을 확인했습니다.
과거 libhdfs와의 완전한 동등성이나 권한·복제·여러 DataNode의 장애 처리는 확인하지 않았습니다.
Mac과 Windows를 Scribe 서버의 지원 환경으로 확인한 것은 아닙니다.
다른 compiler·의존성 조합과 상세 성능 비교도 별도 확인이 필요합니다.
랜덤 재시도·서버 후보 shuffle 순서는 GNU 구현을 기준으로 확인했습니다.
다른 C++ 표준 라이브러리에서 같은 순서를 보장한 것은 아닙니다.

## 빠른 시작

### 1. 의존성 준비

위 빌드 도구와 Thrift/fb303를 먼저 준비해야 합니다. 프로젝트가 자동으로 설치하지는 않습니다.
검증기는 Git 이력과 원본 비교용 커밋을 사용하므로 ZIP 대신 Git checkout을 준비하세요.
필요한 원본 이력과 Git 옵션은 [Git 준비 안내](docs/linux-build-mvp.md#검증용-git-이력-준비)를 참고하세요.
일반 clone에는 원본 commit object가 없을 수 있습니다. 프로젝트 폴더에서 먼저 확인하고,
없을 때만 공식 원본을 명시적으로 가져옵니다. 첫 명령이 실패하면 두 보호 옵션을 지원하는 Git을 준비하세요.

```sh
git --no-replace-objects --no-lazy-fetch --version && \
{ git --no-replace-objects --no-lazy-fetch cat-file -e 'fcd294faffd1e88af1643a3a8c2359c41713f7c2^{commit}' || \
  git fetch https://github.com/facebookarchive/scribe.git fcd294faffd1e88af1643a3a8c2359c41713f7c2:refs/remotes/upstream/baseline; } && \
git --no-replace-objects --no-lazy-fetch cat-file -e 'fcd294faffd1e88af1643a3a8c2359c41713f7c2^{commit}'
```

이미 원본 object가 있으면 fetch를 생략합니다. 검증기는 보호 옵션과 필요한 원본 object를
빌드 전에 검사하며 자동으로 fetch하지 않습니다.
**Thrift compiler와 C++ runtime은 같은 버전을 사용하세요.**
fb303도 해당 compiler로 생성하고 빌드한 것을 사용해야 합니다.
Python 설치 전에는 autotools로 Makefile을 만들고 matching compiler로 Python package를 재생성해야 합니다.
수동 configure는 명시적 `PYTHON`을 보존하며, 지정하지 않으면 `python3`, `python` 순서로 찾습니다.

아래 경로를 이미 준비한 의존성의 실제 위치로 바꿉니다.
`TOOLS_PREFIX`에는 Boost와 libevent 등이 들어 있는 공통 설치 경로를 지정합니다.
별도의 도구 환경을 쓴다면 compiler와 autotools도 그 환경에서 실행되도록 먼저 설정하세요.

```sh
export THRIFT_PREFIX=/absolute/path/to/thrift-0.25.0
export FB303_PREFIX=/absolute/path/to/fb303-prefix
export TOOLS_PREFIX=/absolute/path/to/tools/usr
export THRIFT_PYTHON_SOURCE=/absolute/path/to/thrift-0.25.0/lib/py/src
```

### 2. 빌드와 설치 확인

프로젝트 폴더에서 실행합니다. 출력 경로는 프로젝트 밖에 있는 **아직 없는 폴더**여야 합니다.
상위 폴더는 미리 존재해야 합니다.

```sh
python3 -B tools/validate_linux.py --output "$PWD/../scribe-validation"
```

이 명령은 새 작업 폴더에서 설정, 전체 빌드, 테스트, 임시 설치와 `scribed --help`를 확인합니다.
시스템에 설치하거나 서버를 자동으로 시작하지 않습니다.
생성된 실행 파일은 `../scribe-validation/stage/opt/scribe/bin/scribed`에 있습니다.
실행할 때도 빌드에 사용한 의존성 라이브러리를 찾을 수 있어야 합니다.

공유 RPC 라이브러리를 확인하려면 새로운 출력 경로에 `--shared-rpc`를 붙입니다.
기본 빌드도 모든 의존성을 실행 파일에 넣는 완전 정적 빌드는 아닙니다.

```sh
python3 -B tools/validate_linux.py --shared-rpc --output "$PWD/../scribe-validation-shared"
```

수동 autotools 빌드, 공유 라이브러리 경로와 HDFS 빌드 설정은
[빌드 안내](docs/linux-build-mvp.md)와 [HDFS 안내](docs/hdfs-compatibility.md)를 참고하세요.

### 3. 설정 파일 만들기

아래는 `demo` category의 로그를 본인 소유 폴더에 저장하는 작은 예제입니다.
각 메시지 뒤에 줄바꿈을 하나 추가합니다.

```sh
export SCRIBE_DATA="$HOME/scribe-data"
export SCRIBE_CONFIG="$HOME/scribe-demo.conf"
mkdir -p "$SCRIBE_DATA"
cat > "$SCRIBE_CONFIG" <<EOF_CONFIG
port=1463
max_msg_per_second=2000000
check_interval=1
<store>
category=demo
type=file
fs_type=std
file_path=$SCRIBE_DATA
base_filename=demo
rotate_period=never
max_size=1048576
add_newlines=1
write_category=no
write_meta=no
write_stats=no
create_symlink=yes
target_write_size=1
max_write_interval=1
</store>
EOF_CONFIG
```

다른 category도 받으려면 기존 설정에 맞게 `<store>`를 추가하세요.
이 예제에서 지정하지 않은 category는 원본 규칙에 따라 버려질 수 있습니다.

### 4. 실행

```sh
../scribe-validation/stage/opt/scribe/bin/scribed -c "$SCRIBE_CONFIG"
```

`scribed`는 실행한 터미널에 연결된 상태로 동작합니다. 예제는 포트를 localhost에만 제한하지 않습니다.
실행 환경의 접근 범위를 확인한 뒤 기동하세요. 서비스 등록이나 자동 배포는 제공하지 않습니다.
설정의 `port`가 명령행 `-p`보다 우선합니다. `-c`와 `-p` 형태를 사용하세요.

프로세스가 시작됐다는 것만으로 로그 저장이 정상이라고 판단하지 마세요.
fb303 상태·상세 설명·수신 카운터와 실제 저장 파일을 함께 확인해야 합니다.

## 기존 설정과 클라이언트 사용

기존 `<store>` 설정을 출발점으로 쓸 수 있습니다.
[원본 설정 예제](examples/example1.conf)의 파일·임시 보관 경로와 포트를 본인 환경에 맞게 바꾸세요.
기존 보조 스크립트에 들어 있는 공유 `/tmp` 경로나 root 실행 가정을 그대로 따라갈 필요는 없습니다.
원본 [README](README)와 [examples 안내](examples/README)는 역사적 자료입니다.
없는 `example2.conf`·`README.BUILD` 안내 대신 실제 `example2client.conf`·`example2central.conf`와
현재 빌드 안내를 따르세요. 구 Python/PHP 스크립트의 현대 runtime 호환성을 보장하지 않습니다.

원본 시험 설정도 그대로 보존합니다. `test/scribe.conf.bucketupdater.central`은 `<bucket3>`를
`</bucket2>`로 닫고, `scribehtest`의 `lzo_compression`·`lzo_block_size`·`sync_interval`과
`simpletest`의 `send_buffer`는 현재 코드가 읽지 않습니다. 예제를 그대로 운영 설정으로 쓰지 마세요.

원본 IDL과 framed binary 통신을 유지하며 구 서버→새 서버와 새 서버→구 서버 전송을 비교했습니다.
원본 버그 때문에 로그의 분배·내용·형식·전달 결과가 달라지던 수정은 되돌렸습니다.
그 버그와 설정상 주의점은 [별첨](#별첨-원본-버그와-호환성)에 정리했습니다.

**기존 클라이언트를 함께 업그레이드하도록 요구하지 않습니다.**
다만 사용 중인 모든 언어·Thrift 버전 조합을 검증한 것은 아닙니다.
이 저장소에서 생성·설치하는 Python package는 Thrift 0.25용 Python3 client입니다.
원본 Python2 client나 구 Thrift Python runtime의 대체품으로 검증하지 않았습니다.
이름이 같은 `scribe` package를 기존 client 환경에 덮어 설치하지 말고,
별도 Python 가상환경이나 설치 경로에서 맞는 Thrift/fb303 runtime과 사용하세요.
`bucketupdater` Python package 설치와 구 Python/PHP 예제 전체의 현대화는 포함하지 않습니다.

## 업데이트와 되돌리기

운영 배포와 실제 복구 절차를 검증한 것은 아닙니다. 전환 전에 다음을 준비하세요.

1. 이전 실행 파일, 의존성 라이브러리, 설정과 검증 기록을 한 묶음으로 보관합니다
2. 기존 writer를 종료한 뒤 데이터와 임시 보관 파일을 보존합니다
3. 구·신 서버가 같은 파일에 동시에 쓰지 않도록 합니다
4. 별도 폴더에서 작은 로그의 전송·읽기·상태를 확인한 뒤 전환을 결정합니다

실행 파일만 되돌려도 이미 손실된 메시지가 복구되거나 저장 파일 형식이 바뀌지는 않습니다.
특히 이전 개발 버전이 만든 raw 형식 복사본 파일은 현재 버전이 자동으로 변환하지 않습니다.
[파일 형식 주의점](#thriftfile-복사본의-rawframed-형식)을 확인하세요.

## 관련 문서

| 문서 | 내용 |
| --- | --- |
| [빌드 안내](docs/linux-build-mvp.md) | 의존성 경로, 빌드·임시 설치와 지원 범위 |
| [호환성 정책](docs/legacy-compatibility-policy.md) | 원본 동작을 유지하기로 한 결정과 남는 버그 |
| [실제 구·신 서버 비교](docs/daemon-differential.md) | 전송, 저장, 재시작과 테스트 방법 |
| [HDFS 안내](docs/hdfs-compatibility.md) | 선택 기능의 빌드·실행 범위와 제한 |
| [Python 설치 기록](docs/python-packaging-status.md) | 설치 경로와 생성 client의 지원 범위 |
| [첫 버전의 지원 범위](docs/first-modern-version.md) | 확인한 기능과 아직 확인하지 않은 사항 |
| [설계](docs/design.ko.md) / [구현 계획](docs/implementation.ko.md) | 원본 구조와 개발 방향 |
| [개발 지침](AGENTS.md) | 코드 변경과 검증 시 지킬 규칙 |

세부 실행 결과와 과거 단계별 기록은 관련 문서와 보관된 원시 결과를 참고하세요.
README에는 실행 이력을 모두 나열하지 않습니다.

## 라이선스

[Apache License 2.0](LICENSE)을 따릅니다. 원본 Facebook Scribe의 저작권과 고지를 보존합니다.
재배포할 때는 LICENSE, 변경 파일의 수정 고지와 필요한 원본 고지를 포함해야 합니다.
의존성 라이브러리도 함께 배포한다면 각 라이브러리의 LICENSE/NOTICE를 따로 확인하세요.
현재 빌드·임시 설치 검사가 완성된 배포 패키지나 의존성 고지 목록을 대신하지는 않습니다.

## 별첨: 원본 버그와 호환성

기준은 [공개 Facebook Scribe 원본](https://github.com/facebookarchive/scribe/tree/fcd294faffd1e88af1643a3a8c2359c41713f7c2)입니다.
현재 방침은 **구·신 서버를 섞어 쓰고 기존 로그 소비 프로그램을 그대로 사용하는 것**을 우선합니다.
로그의 분배, 내용, 파일 형식, 전달·손실 처리와 상태 조회 결과를 바꾸는 수정은 되돌렸습니다.
프로그램이 잘못된 메모리를 읽거나 비정상 종료할 수 있는 문제는 안전하게 막았습니다.
되돌린 버그를 다시 고치는 새 옵션은 추가하지 않았습니다.

설정의 `store`는 로그를 어디로, 어떤 방식으로 내보낼지 정하는 블록입니다.
원본은 `default`나 여러 category에 적용하는 설정을 복사해 별도의 store를 만들기도 합니다.
아래에서 “복사본” 문제는 이렇게 만든 store와 직접 설정한 store의 동작이 다른 경우를 말합니다.

### 안전하게 고친 문제와 빌드 호환성

| 원본 문제 | 현재 처리와 사용자 영향 |
| --- | --- |
| 파일 읽기 버퍼를 `malloc`으로 만들고 `delete[]`로 해제 | `free`로 맞췄습니다. 메모리 오류를 막고 정상 로그의 내용·파일 형식은 유지합니다 |
| 재시도 시간의 랜덤 범위를 0으로 설정하면 나머지 연산에서 오류 | `retry_interval_range=0` 또는 `max_random_offset=0`일 때 랜덤 오프셋을 더하지 않습니다. 정상 범위의 재시도 계산은 유지합니다 |
| 알 수 없는 bucket 하위 store 종류를 설정하면 null을 사용 | 잘못된 종류를 설정 오류로 처리합니다. 원래 비정상 종료할 수 있던 경우이며 정상 종류의 분배는 바꾸지 않습니다 |
| service list의 기본 port를 지정하지 않으면 초기화되지 않은 값을 사용 | 초기값을 0으로 정했습니다. 명시한 port는 그대로 사용합니다. 정상 목적지를 자동으로 찾아주는 수정은 아니므로 host:port 또는 `list_default_port`를 지정하세요 |
| bucket 추가 설정 검사에서 문자열 밖 메모리를 읽을 수 있음 | 문자열 안에서 정의된 원본 검사만 유지하고 범위 밖 접근은 생략합니다. 정상 bucket 분배를 유지하며 새로 초과 bucket을 거부하지 않습니다 |
| 빌드 호환성: 구 libhdfs와 현대 libhdfs의 파일 삭제 함수 인자 수가 다름 | 기존 API와 현대 API에 맞게 연결했습니다. 현대 API에는 `recursive=1`을 넘기며 원본의 결과 무시·로그 처리도 유지합니다. HDFS 전체 오류 처리까지 새로 고친 것은 아닙니다 |

### 호환성을 위해 남겨 둔 문제

#### Bucket 복사본의 분배와 키 제거

원본은 category별로 bucket store를 복사할 때 `bucket_range`와 `remove_key`를 복사하지 않습니다.
직접 설정한 store에서는 적용되는 값이 복사본에서는 기본 동작으로 바뀔 수 있습니다.
예를 들어 `bucket_type=key_range`, `bucket_range=20`, `remove_key=yes`, `delimiter=124`로
`15|hello`를 보내도 복사본에서는 bucket0으로 가고 `15|`가 남을 수 있습니다.

설정대로 동작하게 고치면 기존 로그의 저장 위치와 내용이 달라집니다.
기존 프로그램이 어떤 파일의 어떤 내용을 읽는지 유지하기 위해 원본대로 남겼습니다.
`default`나 여러 category에 쓰는 모델 설정에서는 실제 복사본의 출력 위치와 키 포함 여부를 확인하세요.

#### 추가 bucket 설정이 제대로 검사되지 않는 문제

명시적으로 `bucket0`부터 `bucketN`까지 정의할 때, 원본의 추가 bucket 검사식은
이름을 붙이지 않고 문자열의 중간부터 읽습니다. 예를 들어 `num_buckets=1`이면
`bucket2`가 아니라 `cket`을 찾습니다. 앞서 설명한 범위 밖 메모리 접근은 막았지만
이름을 올바르게 검사하도록 고치면 원래 시작되던 설정을 새로 거부하게 됩니다.

그래서 범위 안의 원본 검사만 유지하며 추가 `bucketN+1`을 새로 거부하지 않습니다.
추가 정의가 자동으로 분배 대상이 되는 것은 아닙니다.
필요한 `bucket0`부터 `bucketN`까지의 정의와 실제 분배 결과를 확인하세요.

#### ThriftFile 복사본의 raw/framed 형식

`use_simple_file=1` 또는 `2`인 직접 설정 store는 메시지 내용만 저장하는 raw 형식입니다.
그런데 원본의 `ThriftFileStore` 복사본은 이 설정을 복사하지 않아 길이 정보가 붙은 framed 형식으로 기록합니다.
`thriftmultifile`처럼 category별 복사본을 쓰는 경우도 주의해야 합니다.

이 설정을 복사하도록 고치면 기존 reader가 읽던 framed 파일 대신 raw 파일이 생깁니다.
따라서 원본 복사본의 framed 형식을 유지합니다. raw와 framed는 서로 다른 reader가 필요합니다.
framed 파일에는 청크 경계의 padding도 있으므로 reader는 writer와 같은 `chunk_size`를 사용해야 합니다.
원본 일반 임시 보관 파일의 형식도 ThriftFile 형식과 별개입니다.

이전 개발 버전이 raw 형식 복사본 파일을 이미 만들었다면 그 파일은 그대로 남습니다.
현재 버전으로 바꿔도 변환하지 않으며, 같은 폴더에 서로 다른 형식의 파일이 있을 수 있습니다.
reader 선택과 이전 버전으로의 전환 전에 실제 파일 형식을 확인하세요.
빈 메시지나 청크보다 큰 메시지에 대한 원본 ThriftFile의 처리도 유지합니다.
길이 표시 4바이트를 포함한 메시지 크기가 `chunk_size`를 넘으면 오류 로그 뒤 기록되지 않아도
Scribe 호출과 성공 집계가 성공으로 보일 수 있습니다.

#### Network 복사본의 목적지와 설정

원본의 network store 복사본은 service list, service 옵션·캐시 시간,
`ignore_network_error`와 동적 목적지 조회 설정을 모두 복사하지 않습니다.
동적 모델에서 정해진 주소를 새 category가 그대로 사용하며, 새 category의 주소를 다시 조회하거나
그 복사본을 같은 방식으로 자동 갱신하지 않을 수 있습니다.
list를 쓰는 복사본에서는 설정 누락 때문에 연결이 실패할 수도 있습니다.

복사 설정을 보완하면 원래 전송되지 않던 로그가 전달되거나 목적지가 바뀌고 상태 조회 결과도 달라집니다.
그래서 원본의 복사 규칙을 유지합니다. `default` 또는 category 모델로 network store를 쓸 때는
실제 목적지와 fb303 상태를 확인하세요. 원본의 직접 설정 store에 대한 동적 조회·TTL 갱신은 유지합니다.

#### service list의 연결 공유와 재연결

`service_list`와 `use_conn_pool=yes`를 함께 쓰면 서로 다른 list가 원본의 같은 빈 이름으로 연결을 공유할 수 있습니다.
따라서 두 list가 서로 다른 목적지를 적고 있어도 먼저 열린 연결을 사용할 수 있습니다.
재연결할 때는 서버 후보 목록도 누적됩니다. 같은 후보가 반복되면 선택 비율이 달라질 수 있습니다.

연결을 분리하거나 목록을 비우면 전송 대상·연결 사용·선택 비율이 바뀌므로 원본대로 남겼습니다.
서로 다른 list를 사용할 때는 실제 목적지를 확인하고 기존 `use_conn_pool=no` 설정을 검토하세요.
이 옵션은 새로운 버그 수정 옵션이 아니라 원래 있던 연결 공유 설정입니다.

#### 동적 목적지 변경 시 다른 연결을 닫는 문제

동적 network store가 A에서 B로 바뀔 때 원본은 주소를 먼저 B로 바꾸고 B의 연결을 닫습니다.
연결 pool에 다른 store가 B를 사용하고 있다면 그 store의 연결 참조를 줄이거나 끊을 수 있습니다.
A의 연결은 남거나 새 주소의 연결이 없다는 로그가 생길 수도 있습니다.

이 순서를 바로잡으면 다른 store의 전달·재연결·상태 결과가 달라져 원본 순서를 유지했습니다.
동적 목적지 변경과 pool 공유를 함께 쓰는 설정에서는 이 문제가 남습니다.
공유를 사용하지 않는 직접 설정으로도 동적 조회를 쓸 수 있지만, 전송 구성 변경은 운영 환경에서 따로 확인해야 합니다.

#### 복사본에서 ignore_network_error가 적용되지 않는 문제

모델에 `ignore_network_error=yes`를 써도 원본 복사본은 기본값을 사용합니다.
연결 실패 시 `Failed to connect` 상태와 fb303 `WARNING`이 보일 수 있습니다.
설정을 복사하면 기존 감시 프로그램이 보던 상태가 달라지므로 원본대로 남겼습니다.

`ignore_network_error`가 적용되는 경우에도 실제 연결 실패가 성공으로 바뀌는 것은 아닙니다.
알림을 숨기는 설정과 로그가 전달됐다는 사실을 혼동하지 마세요.

#### 빈 메시지만 있는 큐가 전달되지 않는 문제

원본은 큐에 들어 있는 메시지 내용의 총 byte 수로 처리 여부를 판단합니다.
빈 메시지만 있으면 큐에 메시지가 있어도 총 크기가 0이라 주기 처리나 종료 때 전달하지 않을 수 있습니다.
서버는 이미 `OK`를 반환하고 수신 카운터를 늘렸어도 저장 파일은 비어 있고 손실 카운터도 0일 수 있습니다.

이를 고치면 `add_newlines=1`에서 줄바꿈이 새로 저장되거나 전달 횟수가 달라집니다.
기존 저장·집계 결과를 유지하기 위해 원본대로 남겼습니다.
빈 메시지와 일반 메시지가 같은 큐에 섞이면 처리 결과가 다르며, 메시지가 하나도 없는 Log 요청과도 구분해야 합니다.

#### 일부 재전송 후 남은 로그가 손실되는 문제

원본의 일반 파일은 재전송할 파일을 교체할 때 append와 truncate를 동시에 지정합니다.
이 조합은 파일을 열지 못하게 하므로 일부 메시지만 처리한 뒤 남은 메시지를 저장하지 못할 수 있습니다.
예를 들어 3개 중 1개를 먼저 처리했다면 나머지 2개가 손실로 집계되고 임시 보관 파일이 삭제될 수 있습니다.

append를 제거하면 남은 로그를 보존하지만 원본의 삭제·손실 카운터·다음 재전송 결과가 달라집니다.
현재는 그 결과까지 유지하기로 했으므로 원본의 실패 동작을 남겼습니다.
부분 처리와 재시도가 가능한 구성은 이 손실 가능성을 고려해야 합니다.
이 정책이 무손실이나 장애 안전성을 보장한다는 뜻은 아닙니다.

### 통신 크기 제한과 확인한 호환성

새 Thrift의 기본 크기 제한은 원본과 다릅니다. 이 프로젝트는 server·relay·mapping에
`thrift_max_frame_size`와 `thrift_max_message_size`를 각각 **256 MiB**로 맞춥니다.
기준은 직렬화된 RPC 내용의 크기이며 바깥의 4-byte frame 길이 표시는 제외합니다.
다음은 현재 기본값과 같습니다.

```conf
thrift_max_frame_size=268435456
thrift_max_message_size=268435456
```

두 값은 양의 십진수 byte 수이며 1부터 2147483647까지 받을 수 있습니다.
처음 시작할 때 적용되므로 바꾸려면 restart가 필요합니다.
한도를 넘는 relay batch는 자동 분할하거나 버리지 않고 실패·재시도로 남습니다.
따라서 너무 큰 임시 보관 파일이나 메시지가 계속 재시도될 수 있습니다.
`max_write_size`나 파일 회전 설정만 줄인다고 RPC 크기까지 작아지는 것은 아닙니다.
이 한도는 프로세스 메모리의 상한이나 원본 모든 큰 요청의 호환 보장이 아닙니다.

대표적인 작은 로그로 **구 서버→새 서버와 새 서버→구 서버 전송**, 일반 임시 보관 파일의 양방향 읽기,
구 ThriftFile writer→새 reader와 새 writer→구 reader를 확인했습니다.
모든 파일·손상 입력·언어 client·장애 상황을 확인한 것은 아닙니다.
2026-10-06 원본 계약 복원 [PR #25](https://github.com/dbwk10317/scribe-next/pull/25)를 main에 반영했습니다.
새 writer→구 Thrift 0.9.0 reader의 최종 보관 기록도 정상 종료와
`events=2 bytes=10`을 확인하며, 복원한 내용은 `4100420aff656e64730a`입니다.
[호환성 정책](docs/legacy-compatibility-policy.md), [실제 비교 기록](docs/daemon-differential.md)와
[ThriftFile 처리 기록](docs/thriftfile-fix-options.md)에 자세한 근거를 남깁니다.

### 설정과 실행 시 함께 알아둘 점

- 원본 설정 파서는 잘못된 설정을 모두 거부하지 않습니다. 동적 설정 오류 뒤 기본 목적지로 전송하거나 준비되지 않은 store에도 listener와 `OK` 응답이 생길 수 있습니다
- 공개 원본의 서비스 이름 조회는 항상 실패하는 예제 구현입니다. `smc_service`만으로 실제 service discovery가 제공된다고 가정하지 마세요
- 원본 긴 명령행 옵션 `--config`와 `--port`의 인자 선언 문제를 유지합니다. 짧은 `-c`와 `-p`를 사용하고 설정 파일의 port가 우선한다는 점을 확인하세요
- `_current`는 일반 파일 저장에서는 symlink이지만 HDFS에서는 경로를 담은 일반 marker 파일입니다
- 원본 HDFS의 Scribe 파일 읽기 메서드(`readNext`/`getFrame`)와 닫힌 파일의 truncate에는 제한이 남습니다. HDFS 저장 확인을 일반 임시 보관 파일의 재전송 지원으로 해석하지 마세요
- 새로운 Thrift의 thread 구현과 라이브러리 ABI가 다르므로 stack 크기와 운영 성능까지 같다고 가정하지 마세요
