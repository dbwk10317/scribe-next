# Docker 이미지

로컬 checkout을 build context로 `scribed` 실행 이미지를 만든다. 기본 env_default·비-HDFS·static RPC
lane이며 [Dockerfile](../Dockerfile)의 build 단계는 [빌드 안내](build.md)와 같은 Thrift 0.25.0,
[patch한 fb303](build.md#fb303-patch), 기존 autotools 경로를 사용한다.

## 빌드

checkout root에서 실행한다. Thrift archive를 내려받아 SHA256을 검사하므로 network가 필요하다.

```sh
docker build -t scribe-next:local .
```

build 단계는 줄바꿈을 고치지 않는다. `.gitattributes`가 모든 text 파일을 LF로 checkout하게 하므로 Windows checkout도 LF다.
2026-10-08 전에 받은 Windows checkout은 한 번 변환한다([checkout 줄바꿈](build.md#checkout-줄바꿈)).

## 실행

```sh
mkdir -p scribe-logs && chmod 0777 scribe-logs   # 또는 컨테이너 uid에 chown
docker run -d --name scribe -p 1463:1463 \
  -v "$PWD/scribe-logs:/var/log/scribed" \
  scribe-next:local
```

자기 설정을 쓰려면 같은 명령의 이미지 이름 앞에 `-v "$PWD/my-scribe.conf:/etc/scribe/scribe.conf:ro"`를 더한다.
그 파일이 host에 없으면 Docker가 같은 이름의 폴더를 만들어 mount가 실패하므로 파일을 먼저 만든다.

- 설정을 mount하지 않으면 이미지에 넣은 [examples/docker.conf](../examples/docker.conf)를 쓴다.
  모든 category를 `/var/log/scribed/<category>/<category>-YYYY-MM-DD_00000`에 쓰고 `<category>_current` symlink를 둔다.
- 컨테이너는 비root `scribe` system 사용자로 실행된다. uid는 `docker run --rm --entrypoint id scribe-next:local`로 확인한다.
  bind mount한 log 디렉터리는 그 uid가 쓸 수 있어야 하고 mount한 설정은 읽을 수 있어야 한다. 이름 있는 volume은 소유권이 자동으로 맞는다.
  bind mount에 생긴 log 파일은 그 uid 소유이므로 host에서 지우려면 같은 uid나 root가 필요하다.
- 이미지는 scribed에 `-p`를 주지 않으므로 listen port는 설정의 `port`가 정한다(설정 `port`가 CLI `-p`보다 우선하는 원본 동작도 같다). port를 바꾸면 설정과 `docker run -p`를 함께 바꾼다.
- 파일 날짜와 daily rotation은 컨테이너 local time(기본 UTC)을 따른다.

## 동작 확인

`docker logs scribe`에 `Starting scribe server on port 1463`과 `STATUS: ALIVE`가 보여야 한다.
시험 메시지는 checkout root에서 기존 harness encoder로 보낸다(Python 3 표준 라이브러리만 사용).

```sh
python3 - <<'PY'
import socket, struct, sys
sys.path.insert(0, 'tools')
from daemon_differential import framed, log_fields, parse_reply, recv_exact
with socket.create_connection(('127.0.0.1', 1463)) as s:
    s.sendall(framed(b'Log', 1, log_fields([(b'demo', b'hello docker\n')])))
    body = recv_exact(s, struct.unpack('>I', recv_exact(s, 4))[0])
    print(parse_reply(body, b'Log', 1))   # 0 = OK, 1 = TRY_LATER
PY
cat scribe-logs/demo/demo_current          # "hello docker\n\n" (add_newlines=1이 한 줄 더 붙인다)
```

`demo_current`는 실제 파일 `demo-YYYY-MM-DD_00000`을 가리키는 symlink다.
`OK`는 메모리 큐 수락이다. 파일 기록은 store thread가 약 1초 안에 한다.
fb303 상태는 `framed(b'getStatus', 2)` 응답 값 2(ALIVE)로 확인한다.

## 중지

```sh
docker stop scribe
```

`docker stop`은 PID 1인 scribed에 SIGTERM을 보낸다. scribed는 fb303 `shutdown`과 같이 store를 멈추고 큐를 처리한 뒤 exit 0으로 끝난다.
유예 시간(기본 10초) 안에 끝나지 않으면 Docker가 SIGKILL을 보내고, 쓰지 않은 큐 메시지는 잃을 수 있다. 큐가 크면 `docker stop -t <초>`로 늘린다.
fb303 oneway `shutdown`도 같은 정지를 한다.

```sh
python3 - <<'PY'
import socket, sys
sys.path.insert(0, 'tools')
from daemon_differential import framed
socket.create_connection(('127.0.0.1', 1463)).sendall(framed(b'shutdown', 1, oneway=True))
PY
```

## 이미지 구성

- `/usr/local/bin/scribed`, `/usr/local/lib/libthrift.so.0.25.0`, `libthriftnb.so.0.25.0`. fb303와 Scribe RPC library는 static link다
- 배포판 libevent. Boost는 없다(build 단계의 `boost-devel`은 Thrift 빌드용 header이며 scribed는 Boost 라이브러리를 링크하지 않는다)
- `/etc/scribe/scribe.conf`(examples/docker.conf), log volume `/var/log/scribed`, `EXPOSE 1463`
- `/usr/share/licenses/scribe-next/`: Scribe LICENSE, Thrift LICENSE/NOTICE, fb303 LICENSE
- compiler, source, Thrift compiler, Python client와 `scribe_cat`·`scribe_ctrl`은 넣지 않는다

## 한계

- HDFS 미포함. [HDFS 안내](hdfs.md)의 별도 lane을 쓴다
- static RPC library만 쓴다. shared RPC lane이 아니다
- 로컬 checkout을 그대로 빌드한다. commit하지 않은 변경도 들어가며 특정 commit 재현은 clean checkout에서 한다
- 두 단계의 base는 [Rocky 빌드 안내](build.md#rocky-linux-8과-9)의 Rocky 9 RESF 이미지 digest로 고정한다. `dnf`가 받는 패키지 버전은 고정하지 않는다
- Thrift archive는 `curl -f --proto '=https'`로 받아 SHA256을 검사한다
- 운영 hardening 안내가 아니다. Scribe에는 인증·TLS가 없으므로 1463은 신뢰 network에만 노출한다.
  자원 제한, log 보관·삭제, 감시와 정상 종료 절차는 운영 환경에서 따로 정한다

## 확인 기록

### 지금 Dockerfile (2026-10-08 이후)

digest 고정 base, CR 정리 없는 build 단계, SIGTERM 정지를 함께 확인한 기록이다.

- 2026-10-08, 통합 branch `fix/review-20261008`의 최종 commit에서 root `Dockerfile`로 처음부터 만든 이미지(WSL Rocky 9.8, Docker 29.8)
- `docker stop`: 로그 `received signal 15, shutting down`, `STATUS: STOPPING`, `scribe server exiting`, 종료 코드 0. 큐에 있던 메시지가 `demo_current`에 남았다
- SIGINT: `received signal 2` 뒤 종료 코드 0
- port 사용 중: `Exception in main: Could not bind: Address already in use` 뒤 종료 코드 1
- `.github/workflows/validate.yml`의 `docker-smoke` job(root Dockerfile 빌드, `Log` 한 번, `docker stop` 뒤 종료 코드 0과 `scribe server exiting` 확인)은 아직 어디에서도 실행되지 않았다

### 이전 Dockerfile의 기록

아래는 base가 `rockylinux:9` tag였고, build 단계가 CR을 지웠으며, scribed에 신호 처리가 없던 때의 기록이다.
그때의 `ExecStop`은 `examples/scribed.service`에 있던 Python 명령이다. 지금 unit에는 없다.

2026-10-07, WSL Rocky 9 host의 Docker 29.8.2에서 Windows CRLF checkout을 context로 빌드했다.
base `rockylinux:9`는 Rocky 9.3(`sha256:d7be1c094cc5845ee815d4632fe377514ee6ebcf8efaed6892889657e5ddaaa6`)이었다.

- 실행 이미지 272MB(content 67.2MB). `rpm -qa`에 Boost 패키지가 없고 `ldd`는 libthrift/libthriftnb 0.25.0과 배포판 libevent 2.1만 찾는다
- prepare_fb303의 patch SHA256이 Git blob과 같아 그때의 CR 정리를 확인했다
- 기본 설정으로 `Log(demo, "hello docker\n")` 응답 0(OK), `demo_current` bytes `hello docker\n\n`, `getStatus` 2(ALIVE)
- oneway `shutdown` 뒤 exit 0, 그때의 `docker stop`은 10초 뒤 exit 137. 설정 mount로 port 1500 기동도 확인했다
- `9e8d775` 이미지도 같은 smoke를 통과했다([최종 재검증](verification.md#최종-재검증-2026-10-07)). 그 뒤 PR #63(`28a4d9a`), PR #65(`e4bb4cc`)를 합친 `0afe2b4` 이미지는 smoke를 하지 않았다
- 리뷰 수정 `acc7edd` 이미지는 WSL의 LF checkout에서 만들어 같은 smoke 중 `Log` 응답 0과 `demo_current` bytes `hello docker\n\n`을 확인했다. 그 컨테이너의 실제 scribed에 그때 unit의 `ExecStop` 명령(shutdown frame 뒤 프로세스 종료 대기)을 실행해 `STATUS: STOPPING` 뒤 `scribe server exiting`, exit 0을 확인했다. `getStatus`와 port 1500 mount는 다시 하지 않았다([검증](verification.md#0afe2b4와-acc7edd의-재확인-2026-10-07))

한 환경의 실제 컨테이너 결과이며 운영 준비나 다른 host 호환성으로 확대하지 않는다.
