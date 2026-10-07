# scribe-next

**Facebook Scribe 로그 수집 daemon을 지금의 Linux에서 다시 빌드할 수 있게 옮긴 drop-in[^dropin] 대체판입니다.**

실행 파일 이름, 설정 파일, 통신 방식, 저장 파일 형식, 상태 조회 방법이 원본과 같습니다.
기존 서버의 실행 파일만 바꿔 끼우고, 설정·클라이언트·로그를 읽는 프로그램은 그대로 두는 것이 목표입니다.

> [!NOTE]
> 원본과 새 서버를 섞어 쓰는 전송과 파일 읽기를 대표적인 조건에서 비교했습니다.
> 모든 설정과 장애 상황에서 똑같다거나, 운영 환경에서 충분히 검증됐다는 뜻은 아닙니다.
> 확인한 범위는 [테스트 결과](#테스트-결과)에 있습니다.

## 목차

- [개요](#개요)
- [설치](#설치)
  - [원래 Scribe 방식](#원래-scribe-방식)
  - [Docker 방식](#docker-방식)
- [실행](#실행)
- [원래 버전에서 달라진 점](#원래-버전에서-달라진-점)
  - [빌드와 의존성](#빌드와-의존성)
  - [고친 원래 버그](#고친-원래-버그)
  - [코드 정리 (동작 불변)](#코드-정리-동작-불변)
  - [새 설정 키](#새-설정-키)
  - [검증 도구](#검증-도구)
- [일부러 남겨 둔 원래 버그](#일부러-남겨-둔-원래-버그)
- [테스트 결과](#테스트-결과)
- [라이선스](#라이선스)

## 개요

### scribe-next는 무엇인가

Scribe는 여러 서버의 로그를 받아 파일로 저장하거나 다른 Scribe 서버로 넘기는 로그 수집 daemon입니다.
Facebook이 2008년에 공개했고, 원본 저장소는 지금 보관(archived) 상태로 더 이상 관리되지 않습니다.

scribe-next는 그 [공개 원본](https://github.com/facebookarchive/scribe/tree/fcd294faffd1e88af1643a3a8c2359c41713f7c2)을
지금의 Linux에서 빌드하고 실행할 수 있게 옮긴 프로젝트입니다.
새로 설계한 로그 서버가 아니라, 원본 구조를 그대로 두고 빌드와 바깥 경계에 필요한 부분만 고친 이식판입니다.

이 문서에서 **구버전**은 공개 원본(`fcd294f`)을 당시 Thrift/fb303 0.9.0으로 빌드한 서버입니다.
**신버전**은 이 저장소에서 빌드한 서버입니다.

### 왜 다시 만들었나

원본은 지금의 Linux 배포판에서 그대로는 빌드되지 않습니다.

- 원본은 Thrift[^thrift] 0.5~0.9 시절의 API로 작성됐고, 지금의 Thrift는 그 API를 크게 바꿨습니다.
- 원본이 쓰던 라이브러리 함수 일부가 없어지거나 모양이 바뀌었습니다(예: HDFS 라이브러리의 파일 삭제 함수).
- 컴파일러도 달라졌습니다.
  - 구버전을 비교용으로 빌드할 때도 Ubuntu 16.04와 GCC 5.4로 옛 환경을 따로 만들어야 했습니다.

그래서 scribe-next는 빌드 방법과 바깥 경계(통신 라이브러리, 파일 시스템 함수 등)의 코드를 새로 맞췄습니다.
반대로 로그를 나누고, 저장하고, 전달하는 방식은 원본 그대로 두었습니다.

### 바깥에서 보면 원본과 같습니다

| 원본과 같은 것 | 내용 |
| --- | --- |
| 실행 파일 | 이름 `scribed`, 옵션 `-c 설정파일`, `-p 포트` |
| 설정 파일 | `<store>` 블록과 `key=value` 형식, 설정 이름·기본값 |
| 통신 | Thrift framed binary[^framed], 같은 요청·응답 형식 |
| 저장 파일 | 파일 이름, 회전 규칙, `_current` 표시, spool[^spool] 형식 |
| 상태 조회 | fb303[^fb303] 상태·카운터 API |

그래서 다음이 가능합니다.

1. 기존 설정 파일을 고치지 않고 그대로 읽습니다.
2. 기존 클라이언트를 업그레이드하지 않아도 로그를 보낼 수 있습니다.
3. 구버전 → 신버전, 신버전 → 구버전 어느 방향으로도 로그를 넘길 수 있습니다.
   - 그래서 여러 대를 한 대씩 바꿔 끼울 수 있습니다.
4. 같은 입력이면 같은 이름의 파일에 같은 바이트로 저장되고, 카운터 이름도 같습니다.

4번을 지키려고, 로그 결과를 바꾸는 원본 버그는 [일부러 남겨 두었습니다](#일부러-남겨-둔-원래-버그).
여기서 로그 결과는 어느 파일에 무엇이 저장되고 어디로 전달되는가를 말합니다.
반대로 비정상 종료처럼 "원본과 같은 결과"가 없는 문제는 [안전하게 고쳤습니다](#고친-원래-버그).
다만 사용 중인 모든 언어·Thrift 버전의 클라이언트 조합을 검증한 것은 아닙니다.

> [!IMPORTANT]
> 서버가 돌려주는 `OK`는 로그를 **메모리 큐에 받았다**는 뜻입니다.
> 디스크에 저장했다거나 다음 서버에 전달했다는 뜻이 아니며, 중복 없는 전달도 보장하지 않습니다.
> 구버전과 신버전 모두 같습니다.

### 확인한 환경

| 배포판 | 컴파일러 | 확인한 범위 |
| --- | --- | --- |
| Ubuntu 24.04 | GCC 13.3 | 설치 순서 |
| Rocky Linux 9 | GCC 11.5 | 설치 순서, 전체 시험, 구·신 비교 |
| Rocky Linux 8.10 | GCC 8.5 | 빌드, 시험, 임시 설치 |
| Debian 13 | GCC 14.2 | 빌드, 시험 |
| Ubuntu 26.04.1 | GCC 15.2 | 빌드, 시험 |

모든 환경은 Linux x86_64입니다.
Ubuntu 24.04와 Rocky Linux 9는 2026-10-07에 깨끗한 컨테이너에서 이 문서의 [설치](#설치) 명령을 그대로 실행했습니다.
전체 시험과 구·신 비교는 같은 날 WSL의 Rocky 9.8에서 했습니다([테스트 결과](#테스트-결과)).

Rocky 8.10은 더 새로운 bison이 필요하며, 준비 방법은 [Rocky 빌드 안내](docs/build.md#rocky-linux-8과-9)에 있습니다.
Rocky 8.10, Debian 13, Ubuntu 26.04.1은 2026-10-07 최종 재검증에 포함하지 않았습니다.
특히 GCC 14·15에서는 최근 현대화 단계(Boost 제거 등)를 다시 확인하지 않았습니다.

HDFS[^hdfs] 저장, 공유 RPC 라이브러리[^rpc], Rocky용 개발 RPM은 선택 기능이며 확인 범위가 따로 있습니다.
각각 [HDFS 안내](docs/hdfs.md), [빌드 안내](docs/build.md#shared-rpc), [Rocky RPM](docs/build.md#rocky-개발-rpm)을 보세요.
Mac과 Windows는 서버 실행 환경으로 확인하지 않았습니다.

## 설치

두 가지 방법이 있습니다.

- [원래 Scribe 방식](#원래-scribe-방식): 소스에서 `bootstrap.sh` → `make` → `make install`로 설치합니다.
- [Docker 방식](#docker-방식): 원본에는 없던 방법으로, 이미지 하나로 `scribed`를 실행합니다.

### 원래 Scribe 방식

원본 Scribe와 같은 `bootstrap.sh` → `make` → `make install` 흐름입니다.
배포판에 맞는 1단계 블록 하나를 실행한 뒤, 2~5단계를 위에서부터 복사해 붙여 넣으면 됩니다.
아래 명령은 2026-10-07에 깨끗한 `ubuntu:24.04`와 `rockylinux:9` 컨테이너에서 그대로 실행해 확인했습니다.

#### 0. 미리 알아둘 것

- Thrift 0.25.0은 두 배포판 모두 배포판 패키지 없이 소스에서 빌드합니다.
  - Thrift는 `thrift` 코드 생성기(compiler)와 `scribed`가 쓰는 통신 라이브러리를 함께 제공합니다.
- fb303은 같은 Thrift 소스에 들어 있는 것을 쓰고, 이 프로젝트의 patch를 적용해 빌드합니다.
  - 이 patch는 카운터 잠금이 풀리지 않던 문제를 막습니다([자세히](#thrift-025와-fb303)).
- 모두 `/usr/local` 아래에 설치합니다.
  - 원본 Scribe도 `/usr/local`을 기본값으로 가정했으므로, 아래 `--with-*path` 옵션은 이를 명시할 뿐입니다.
- 저장소를 따로 받지 않습니다. 이 README가 들어 있는 폴더가 곧 scribe-next 저장소이며, 그대로 빌드합니다.
  - 아래 명령은 그 폴더를 `$SCRIBE_SRC`로 기억해 두고 씁니다. 저장소 폴더에서 다음을 실행합니다.

```sh
SCRIBE_SRC="$(pwd)"
```

터미널을 새로 열었다면 저장소 폴더에서 위 한 줄을 다시 실행합니다.

> [!IMPORTANT]
> Thrift compiler, Thrift 통신 라이브러리, fb303은 같은 Thrift 0.25.0 소스에서 만들어야 합니다.
> 아래 순서는 세 가지를 모두 같은 소스에서 만들므로 이 조건을 지킵니다.

#### 1-A. Ubuntu 24.04 패키지

빌드 도구, libevent[^libevent], Boost header, 그리고 준비 스크립트와 Python client 설치에 쓰는 Python을 설치합니다.

```sh
sudo apt-get update
sudo apt-get install -y git build-essential autoconf automake libtool pkg-config cmake bison flex \
  libevent-dev libboost-dev python3 python3-setuptools
```

#### 1-B. Rocky Linux 9 패키지 (RHEL 계열)

```sh
sudo dnf -y install git gcc gcc-c++ make cmake autoconf automake libtool bison flex \
  libevent-devel boost-devel python3 python3-setuptools
echo /usr/local/lib | sudo tee /etc/ld.so.conf.d/scribe-local.conf
```

Rocky에는 Boost header만 담은 패키지가 없어 `boost-devel`을 설치합니다.
함께 설치되는 Boost 라이브러리는 `scribed`가 쓰지 않습니다.

마지막 줄은 공유 라이브러리를 찾는 경로에 `/usr/local/lib`을 추가합니다.
Ubuntu는 이 경로를 기본으로 찾지만 Rocky는 찾지 않기 때문입니다.
Rocky 8은 더 새로운 bison이 필요하며, 준비 방법은 [Rocky 빌드 안내](docs/build.md#rocky-linux-8과-9)에 있습니다.

**Boost header가 필요한 이유.**
빌드하는 컴퓨터에는 Boost[^boost] header가 있어야 합니다.
Thrift와 fb303의 header가 Boost header를 불러오기 때문입니다.
`scribed` 자체는 Boost 라이브러리를 링크하지 않으므로, 실행만 하는 컴퓨터에는 Boost가 필요 없습니다.

#### 2. Thrift 0.25.0 빌드와 설치 (공통)

Apache 배포 서버에서 Thrift 0.25.0 소스를 받아 checksum을 확인합니다.
그다음 다른 언어 지원은 끄고, compiler와 C++ 라이브러리(libevent 지원 포함)만 빌드해 `/usr/local`에 설치합니다.

```sh
mkdir -p ~/scribe-build && cd ~/scribe-build
curl -LO https://archive.apache.org/dist/thrift/0.25.0/thrift-0.25.0.tar.gz
echo '66da4707214c54c94bac082103dc67adaf9e08925662700f269170a7b534b214  thrift-0.25.0.tar.gz' | sha256sum -c -
tar xzf thrift-0.25.0.tar.gz
cmake -S thrift-0.25.0 -B thrift-build -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_INSTALL_PREFIX=/usr/local -DCMAKE_INSTALL_LIBDIR=lib \
  -DBUILD_TESTING=OFF -DBUILD_SHARED_LIBS=ON -DWITH_CPP=ON -DWITH_C_GLIB=OFF \
  -DWITH_JAVA=OFF -DWITH_JAVASCRIPT=OFF -DWITH_NODEJS=OFF -DWITH_PYTHON=OFF \
  -DWITH_OPENSSL=OFF -DWITH_LIBEVENT=ON -DWITH_ZLIB=OFF
cmake --build thrift-build --parallel "$(nproc)"
sudo cmake --install thrift-build
sudo ldconfig
```

`sha256sum -c`가 `OK`를 출력하지 않으면 받은 파일이 다른 것이므로 진행하지 마세요.
마지막 `sudo ldconfig`는 새로 설치한 공유 라이브러리를 시스템이 찾도록 목록을 갱신합니다.
이후 단계도 같은 `~/scribe-build` 폴더에서 진행합니다.

#### 3. fb303 빌드·설치 (공통)

Thrift 소스에 든 fb303에 이 저장소의 patch를 적용해 `fb303-build` 폴더를 만듭니다.
그 폴더에서 빌드한 뒤 `/usr/local`에 설치합니다.

```sh
cd ~/scribe-build
python3 "$SCRIBE_SRC/tools/prepare_fb303.py" --source thrift-0.25.0/contrib/fb303 --output fb303-build
cd fb303-build
aclocal -I ./aclocal && automake -a --copy && autoconf
./configure --prefix=/usr/local --with-thriftpath=/usr/local --with-boost=/usr \
  --without-java --without-php --without-python
make -j"$(nproc)" CXXFLAGS='-O2 -std=c++17' CPPFLAGS='-I/usr/local/include'
sudo make install
sudo mkdir -p /usr/local/share/scribe-next
sudo cp scribe-next-fb303-safety.json /usr/local/share/scribe-next/fb303-safety.json
```

마지막 두 줄은 patch 적용 기록(`fb303-safety.json`)을 설치합니다.
검증 도구 `tools/validate_linux.py`가 이 파일을 찾습니다.

#### 4. scribe-next 빌드와 설치 (공통)

원본과 같은 순서입니다.
`bootstrap.sh`는 빌드 설정(configure)을 만들고 실행하며, 넘긴 옵션은 그대로 configure에 전달됩니다.

```sh
cd "$SCRIBE_SRC"
./bootstrap.sh --prefix=/usr/local --with-thriftpath=/usr/local --with-fb303path=/usr/local
make -j"$(nproc)"
sudo make install
```

`make install`은 `scribed`를 `/usr/local/bin`에, 정적 RPC 라이브러리를 `/usr/local/lib`에 설치합니다.
Python client package `scribe`도 시스템 Python(`PY_PREFIX`, 기본값 `/usr`)에 함께 설치됩니다.
daemon을 실행하는 데는 Python client가 필요하지 않습니다.

**Python client를 쓸 때.**
같은 버전의 Thrift Python package(`python3 -m pip install thrift==0.25.0`)와 fb303 Python module도 필요합니다.
위 3단계는 fb303 Python module을 만들지 않습니다(`--without-python`).

이 package는 Thrift 0.25용 Python 3 client이며, 원본의 Python 2 client를 대신하도록 검증하지 않았습니다.
이름이 같은 `scribe` package가 있는 기존 client 환경에 덮어 설치하지 말고, 별도 가상환경이나 설치 경로를 쓰세요.

공유 라이브러리 경로와 HDFS 빌드 설정은 [빌드 안내](docs/build.md)와 [HDFS 안내](docs/hdfs.md)에 있습니다.

#### 5. 설치 확인

설치한 `scribed`가 실행되는지, `/usr/local/lib`의 Thrift 라이브러리를 찾는지 확인합니다.

```sh
scribed --help
ldd "$(command -v scribed)"
```

`scribed --help`는 사용법 줄 `Usage: scribed [-p port] [-c config_file]`을 출력해야 합니다.
`ldd` 결과에는 `/usr/local/lib`의 `libthrift.so.0.25.0`, `libthriftnb.so.0.25.0`과 배포판의 libevent가 보여야 합니다.
Boost 라이브러리(`libboost_*`)는 보이지 않아야 합니다.
실행 파일에 모든 라이브러리를 넣는 빌드가 아니므로, 실행할 때도 이 라이브러리들을 찾을 수 있어야 합니다.

### Docker 방식

원본 Scribe에는 없던 방법입니다.
Docker[^docker]로 위 1~4단계를 대신하고, 저장소의 [`Dockerfile`](Dockerfile)로 만든 이미지에서 `scribed`를 실행합니다.
자세한 내용은 [Docker 안내](docs/docker.md)에 있습니다.

#### 이미지 빌드

저장소 checkout의 최상위 폴더에서 실행합니다.

```sh
docker build -t scribe-next:local .
```

- Dockerfile은 저장소를 따로 받지 않고 지금 checkout을 그대로 빌드합니다.
  - commit하지 않은 변경도 이미지에 들어갑니다.
- 빌드는 위 1~4단계와 같은 순서(Thrift → patch한 fb303 → `bootstrap.sh`·`make`·`make install`)입니다.
- Thrift 소스를 내려받으므로 네트워크가 필요합니다.
- Windows checkout의 CRLF 줄 끝은 빌드 중에 변환하므로, Windows에서 받은 checkout도 쓸 수 있습니다.

확인한 환경(20 core)에서 빌드는 약 1.5분 걸렸고, 이미지는 272 MB(기반 이미지 264 MB)였습니다.
실행 이미지에는 `scribed`, Thrift 라이브러리 두 개, 배포판 libevent, LICENSE/NOTICE 파일만 들어 있습니다.
Boost는 들어 있지 않습니다.

#### 실행과 기본 설정

로그를 저장할 폴더를 만들고, 컨테이너의 `/var/log/scribed`에 연결해 실행합니다.

```sh
mkdir -p scribe-logs && chmod 0777 scribe-logs
docker run -d --name scribe -p 1463:1463 \
  -v "$PWD/scribe-logs:/var/log/scribed" \
  scribe-next:local
```

컨테이너는 root가 아닌 시스템 사용자 `scribe`(확인한 이미지에서 uid 999)로 실행됩니다.
연결한 폴더에 그 사용자가 쓸 수 있어야 하므로 `chmod 0777`을 했습니다.
컨테이너가 만든 파일은 host에서도 그 uid의 소유로 보입니다.

기본 설정 [`examples/docker.conf`](examples/docker.conf)는 다음과 같이 동작합니다.

- `port=1463`에서 받습니다.
- 따로 정의하지 않은 모든 category[^category]를 `category=default` [모델](#먼저-모델과-복사본) 하나로 받습니다.
- 파일은 `/var/log/scribed/<category>/<category>-YYYY-MM-DD_00000`에 쌓입니다.
- 메시지마다 줄바꿈을 하나 붙입니다(`add_newlines=1`).
- 하루마다(`rotate_period=daily`) 또는 1 GiB를 넘으면(`max_size=1073741824`) 새 파일을 엽니다.
- `<category>_current` symlink[^symlink]가 지금 쓰는 파일을 가리킵니다.

날짜는 컨테이너 시계(기본 UTC)를 따릅니다.
직접 만든 설정을 쓰려면 `/etc/scribe/scribe.conf` 위에 읽기 전용으로 연결합니다.

```sh
docker run -d --name scribe -p 1463:1463 \
  -v "$PWD/scribe-logs:/var/log/scribed" \
  -v "$PWD/my-scribe.conf:/etc/scribe/scribe.conf:ro" \
  scribe-next:local
```

설정의 `port`를 바꾸면 `docker run`의 `-p` 포트 연결도 같이 바꾸세요.
설정의 `port`가 `scribed`의 명령행 `-p`보다 우선하기 때문입니다.

#### 동작 확인

먼저 컨테이너 로그에서 시작 메시지와 상태를 봅니다.

```sh
docker logs scribe
```

`Starting scribe server on port 1463`과 `STATUS: ALIVE`가 보여야 합니다.
프로세스가 떴다는 것만으로 저장이 정상이라고 판단하지 말고, 시험 메시지를 보내 실제 파일을 확인하세요.
보내는 방법은 [실행의 동작 확인](#3-동작-확인)과 같으며, 첫 줄의 `cd`만 이 checkout 폴더로 바꾸면 됩니다.

확인할 때 category `demo`로 `hello docker\n`을 보내면 `OK`가 돌아왔습니다.
`scribe-logs/demo/demo-<날짜>_00000`에는 정확히 `hello docker\n\n`이 저장됐습니다.
메시지에 든 줄바꿈 하나에 `add_newlines=1`이 하나를 더 붙이기 때문입니다.

#### 정지

`docker stop`은 유예 시간(기본 10초)을 기다린 뒤 SIGKILL로 강제 종료합니다.
`scribed`에는 SIGTERM 처리가 없기 때문이며, 원본과 같은 동작입니다.
이때 메모리 큐에 남아 있던 메시지는 잃을 수 있습니다.

깔끔하게 멈추려면 fb303 `shutdown`을 보내세요(종료 코드 0).
보내는 방법은 [실행의 정지](#4-정지)와 같습니다(첫 줄의 `cd`는 이 checkout 폴더로).

#### 제한

- HDFS를 지원하지 않습니다.
- RPC 라이브러리는 정적 라이브러리로만 빌드합니다.
- 기반 이미지 `rockylinux:9`를 digest로 고정하지 않았습니다.
- 보안 강화 안내가 아닙니다.
  - Scribe에는 인증·TLS가 없어 포트에 닿는 모든 client의 요청을 받으므로, 신뢰할 수 있는 네트워크에만 여세요.

## 실행

설치한 `scribed`를 작은 설정으로 띄우고, 시험 메시지로 저장을 확인한 뒤, 깔끔하게 멈추는 순서입니다.
[원래 Scribe 방식](#원래-scribe-방식)으로 설치했다고 가정합니다.

### 1. 설정 파일 만들기

아래는 category `demo`의 로그를 본인 소유 폴더에 저장하는 작은 설정입니다.

```sh
export SCRIBE_DATA="$HOME/scribe-data"
export SCRIBE_CONFIG="$HOME/scribe-demo.conf"
mkdir -p "$SCRIBE_DATA"
cat > "$SCRIBE_CONFIG" <<EOF_CONFIG
port=1463
check_interval=1

<store>
  category=demo
  type=file
  file_path=$SCRIBE_DATA
  base_filename=demo
  rotate_period=daily
  max_size=1048576
  add_newlines=1
  create_symlink=yes
</store>
EOF_CONFIG
```

| 설정 | 뜻 |
| --- | --- |
| `port=1463` | 로그를 받을 포트 |
| `check_interval=1` | 회전 검사·재시도 같은 주기 작업의 간격(초, 기본 5) |
| `category=demo` | 이 store[^store]가 받을 category |
| `type=file` | 받은 로그를 파일에 씀 |
| `file_path`, `base_filename` | 저장 폴더와 파일 이름의 앞부분 |
| `rotate_period=daily` | 하루마다 새 파일 |
| `max_size=1048576` | 1 MiB[^mib]를 넘으면 번호를 올린 새 파일 |
| `add_newlines=1` | 메시지마다 줄바꿈(LF[^lf]) 하나를 붙임 |
| `create_symlink=yes` | 지금 쓰는 파일을 가리키는 `demo_current`를 만듦 |

이 설정은 `demo`가 아닌 category를 받지 않습니다.
그런 로그는 원본 규칙대로 버려지고 카운터 `received bad`가 늘어납니다.
다른 category도 받으려면 `<store>`를 추가하거나 `category=default` [모델](#먼저-모델과-복사본)을 쓰세요.

기존 설정을 출발점으로 써도 됩니다.
[원본 설정 예제](examples/example1.conf)의 파일 경로와 포트만 본인 환경에 맞게 바꾸세요.
원본 [README](README)와 [examples 안내](examples/README)는 역사적 자료입니다.
그 안내에 나오는 `example2.conf` 대신 실제 파일인 `example2client.conf`·`example2central.conf`를 보세요.

### 2. 시작

```sh
scribed -c "$SCRIBE_CONFIG"
```

- `scribed`는 실행한 터미널에 붙은 채 동작하고, 진행 로그를 그 터미널에 출력합니다.
- 서비스 등록이나 자동 시작은 제공하지 않습니다.
- 예제는 포트를 localhost로 제한하지 않으므로, 실행 환경의 접근 범위를 먼저 확인하세요.

**설정의 `port`가 명령행 `-p`보다 우선합니다.**
위 설정으로 `scribed -c "$SCRIBE_CONFIG" -p 1464`를 실행해도 1463에서 받습니다.
이때 로그에 `port 1463 from conf file overriding old port 1464`가 남습니다.
`port`와 `-p`가 모두 없으면 `No port number configured` 오류로 시작하지 못합니다.

긴 옵션 `--config`, `--port`는 원본 결함 때문에 제대로 동작하지 않습니다([남겨 둔 버그](#긴-명령행-옵션은-값을-받지-못한다)).
항상 `-c`, `-p`를 쓰세요.

### 3. 동작 확인

시작 로그에 다음 두 줄이 보여야 합니다.

```text
"STATUS: ALIVE"
"Starting scribe server on port 1463"
```

프로세스가 떴다는 것만으로 정상이라고 판단하지 마세요.
`scribed`는 [시작에 실패해도 종료 코드 0](#시작에-실패해도-종료-코드는-0이다)으로 끝나고, store 설정이 틀려도 계속 떠 있습니다.
그래서 시험 메시지, fb303 상태, 카운터, 실제 파일을 함께 확인합니다.

다른 터미널을 열어 저장소 폴더로 이동한 뒤 아래를 실행합니다.
Python 3 표준 라이브러리만 쓰며, 저장소의 시험 도구에 든 Thrift 인코더를 빌려 씁니다.

```sh
python3 - <<'PY'
import socket, struct, sys
sys.path.insert(0, 'tools')
from daemon_differential import framed, log_fields, parse_reply, recv_exact

def call(name, seq, fields=b'\0'):
    with socket.create_connection(('127.0.0.1', 1463)) as s:
        s.sendall(framed(name, seq, fields))
        body = recv_exact(s, struct.unpack('>I', recv_exact(s, 4))[0])
        return parse_reply(body, name, seq)

print('Log:', call(b'Log', 1, log_fields([(b'demo', b'hello scribe')])))  # 0 = OK, 1 = TRY_LATER
print('status:', call(b'getStatus', 2))                                  # 2 = ALIVE, 5 = WARNING
for name, value in sorted(call(b'getCounters', 3).items()):
    print(name, value)
PY
```

정상이라면 다음과 같이 출력됩니다.

```text
Log: 0
status: 2
demo:received good 1
scribe_overall:received good 1
```

- `Log: 0`은 `OK`(메모리 큐에 받음)이고, `1`이면 `TRY_LATER`[^trylater]입니다.
- `status: 2`는 `ALIVE`입니다.
  - `5`(`WARNING`)이면 설정이나 연결에 문제가 있다는 뜻이며, 로그의 `STATUS:` 줄에 이유가 남습니다.
- 카운터는 `<category>:<이름>`과 전체 합계 `scribe_overall:<이름>`으로 나옵니다.

약 1초 뒤 파일을 확인합니다.

```sh
ls -l "$SCRIBE_DATA"
cat "$SCRIBE_DATA/demo_current"
```

`demo-<오늘 날짜>_00000` 파일과, 그 파일을 가리키는 `demo_current`가 있어야 합니다.
내용은 `hello scribe` 한 줄입니다(`add_newlines=1`이 줄바꿈을 붙임).
파일은 시작할 때 미리 열리므로, 파일이 있는지만 보지 말고 내용까지 확인하세요.

원본의 [`examples/scribe_cat`](examples/scribe_cat)으로도 보낼 수 있습니다.
다만 Python 2 시절 스크립트 그대로이며, [Python client](#4-scribe-next-빌드와-설치-공통)와 Thrift·fb303 Python module이 모두 필요합니다.
지금의 Python에서 동작하는지는 보장하지 않습니다.

### 4. 정지

저장소 폴더에서 fb303 `shutdown`을 보냅니다.

```sh
python3 - <<'PY'
import socket, sys
sys.path.insert(0, 'tools')
from daemon_differential import framed
socket.create_connection(('127.0.0.1', 1463)).sendall(framed(b'shutdown', 1, oneway=True))
PY
```

`scribed`는 큐에 남은 로그를 한 번 더 처리하고 store를 닫은 뒤 `scribe server exiting`을 남기고 끝납니다.
종료 코드는 0입니다.

SIGTERM(예: `kill`)이나 Ctrl+C에는 따로 처리하는 코드가 없어, 프로세스가 그 자리에서 끝납니다.
이때 메모리 큐에 있던 로그는 잃을 수 있습니다.
원본과 같은 동작입니다.

### 파일 회전 기본

file store는 일정 시간이나 크기가 되면 새 파일을 엽니다(회전).

- 파일 이름은 `<base_filename>-YYYY-MM-DD_NNNNN`입니다.
  - 날짜는 daemon의 지역 시간(TZ)을 따르고, `rotate_period=never`이면 날짜가 붙지 않습니다(`demo_00000`).
- 파일이 `max_size`를 넘으면 번호 `NNNNN`을 하나 올린 새 파일을 엽니다.
  - file store의 기본값은 1,000,000,000 bytes이고, 0이면 크기 제한이 없습니다.
  - 날짜가 바뀐 뒤 첫 파일은 `_00000`부터 시작합니다.
- `<base_filename>_current`는 가장 최근 파일을 가리키는 symlink입니다.
  - `base_symlink_name`으로 이름을 바꿀 수 있고, `create_symlink=no`이면 만들지 않습니다.
- 회전 검사는 `check_interval`마다 하므로, 실제 회전은 그만큼 늦을 수 있습니다.

| `rotate_period` | 새 파일을 여는 때 |
| --- | --- |
| `never`(기본값) | 시간으로는 열지 않음 |
| `hourly` | 매시 `rotate_minute`(기본 15)분 이후 |
| `daily` | 매일 `rotate_hour`(기본 1)시 `rotate_minute`분 이후 |
| `30m`, `1h`, `2d`, `1w`, `3600` | 파일을 연 뒤 그 시간이 지나면 |
| 그 밖의 값(예: `1x`) | 경고 로그를 남기고 시간 회전을 끔 |

숫자만 쓰면 초 단위입니다(`3600` = `3600s` = 1시간).
`hourly`로 시작할 때 그날 파일이 없으면 첫 번호가 현재 시각의 시가 됩니다(예: 13시 → `_00013`).
buffer의 secondary(spool) 파일은 항상 `never`처럼 동작하고 symlink를 만들지 않습니다.

### 기존 서버를 신버전으로 바꿀 때

운영 배포와 복구 절차 자체를 검증한 것은 아닙니다.
전환 전에 다음을 준비하세요.

1. 이전 실행 파일, 라이브러리, 설정을 한 묶음으로 보관합니다.
2. 기존 `scribed`를 fb303 `shutdown`으로 멈추고, 데이터와 spool 파일은 그대로 둡니다.
3. 구·신 서버가 같은 데이터·spool 폴더에 동시에 쓰지 않게 합니다.
4. 별도 폴더에서 작은 로그의 전송·저장·상태를 확인한 뒤 전환합니다.

신버전은 구버전이 남긴 spool을 이어서 다시 보낼 수 있고, 그 반대도 됩니다([시험 결과](#운영-시나리오-7개)).
구버전으로 되돌리면 [고친 원래 버그](#고친-원래-버그)도 원본 동작으로 돌아갑니다(예: 재전송 일부 성공 시 손실).
실행 파일을 되돌려도 이미 잃은 메시지가 복구되지는 않습니다.

## 원래 버전에서 달라진 점

구버전과 비교해 바뀐 것을 모았습니다.
**어느 항목도 기존 설정을 고치도록 요구하지 않습니다.**
각 항목은 왜 바꿨는지, 무엇을 기대할 수 있는지, 기존과 무엇이 다른지, 관련 설정 키, 예시 순서로 설명합니다.

| 묶음 | 요약 | 로그 결과 |
| --- | --- | --- |
| [빌드와 의존성](#빌드와-의존성) | Thrift 0.25, patch한 fb303, C++17, Boost 제거 | 같음 |
| [고친 원래 버그](#고친-원래-버그) | 비정상 종료·미정의 동작 8가지, 연결 pool·`service_list`·재전송 3가지 | 분배·형식 같음 |
| [코드 정리](#코드-정리-동작-불변) | 잠금·메모리·전역 의존 정리 | 같음 |
| [새 설정 키](#새-설정-키) | Thrift 크기 한도 2개 | 같음(256 MiB 초과 제외) |
| [검증 도구](#검증-도구) | 시험 묶음, 구·신 비교, Docker | 해당 없음 |

고친 원래 버그 중 여덟 가지는 정상 설정에서 결과가 같고, 연결 pool·`service_list`·재전송 세 가지는 분배·파일 형식은 같은 채 일시 실패·메모리 증가·손실이 줄어듭니다.

### 빌드와 의존성

#### Thrift 0.25와 fb303

- **왜 바꿨나.**
  원본은 Thrift 0.5~0.9 시절 API로 작성돼 지금의 Thrift와 함께 빌드되지 않습니다.
  그래서 통신 경계 코드를 Thrift 0.25.0에 맞췄습니다.
  상태 조회용 fb303도 같은 Thrift 0.25.0 소스에서 빌드합니다.

- **기대할 수 있는 것.**
  지금의 배포판에서 빌드하고 실행할 수 있습니다.
  요청·응답 형식과 fb303 조회 방법은 원본과 같아서 구버전 클라이언트·서버와 그대로 통신합니다.

- **기존과 달라진 점.**
  Thrift compiler와 통신 라이브러리는 반드시 같은 0.25.0이어야 합니다(다르면 서로 맞지 않음).
  새 Thrift에는 원본 시절과 다른 기본 크기 한도가 있어, [새 설정 키](#새-설정-키) 두 개로 한도를 정합니다.
  Thrift의 thread 구현과 라이브러리가 달라졌으므로, stack 크기와 운영 성능까지 같다고 가정하지 마세요.

- **fb303 patch.**
  Thrift 0.25.0에 든 fb303 코드는 카운터를 새로 추가하다 메모리 할당에 실패하면 카운터 잠금을 풀지 않았습니다.
  그러면 그 뒤로 카운터 조회가 영원히 멈춥니다.

  이 프로젝트의 patch는 잠금이 자동으로 풀리게 해 이 멈춤을 막습니다.
  카운터 이름·값·조회 방법은 바뀌지 않습니다([fb303 카운터 잠금](docs/build.md#fb303-patch)).

- **관련 설정 키.** 없습니다.

- **예시.**
  로그를 쓰다 예외가 나고, 그 순간 새 카운터를 추가하던 메모리 할당이 실패했다고 합시다.
  patch 전 fb303에서는 그 뒤 감시 도구의 `getCounters` 호출이 응답 없이 멈춥니다.
  patch한 fb303에서는 잠금이 풀려 다음 호출이 정상으로 답합니다.

#### C++17을 빌드 파일이 직접 정함

- **왜 바꿨나.**
  C++17[^cpp17]은 이 이식판이 쓰는 C++ 언어 판(표준)입니다.
  예전에는 이 판이 검증 도구나 RPM 빌드가 따로 지정할 때만 적용됐습니다.
  그래서 직접 `./configure && make`를 하면 컴파일러 기본 판으로 빌드될 수 있었습니다.

- **기대할 수 있는 것.**
  어떤 방법으로 빌드해도 같은 언어 판으로 빌드됩니다.

- **기존과 달라진 점.**
  빌드 방식은 원본처럼 `configure` + `make`이며 다른 빌드 도구로 바꾸지 않았습니다.
  빌드할 때 `CXXFLAGS`로 언어 판을 직접 주면 그 값이 우선합니다.
  실행 중 동작이나 설정 해석은 바뀌지 않습니다.

- **관련 설정 키.** 없습니다.

- **예시.**
  GCC 8의 기본 판은 C++14 계열(gnu++14)입니다.
  예전에는 Rocky 8에서 그냥 `make`하면 C++17이 아닌 판으로 빌드될 수 있었지만, 이제는 항상 C++17로 빌드됩니다.

#### Boost 제거

- **왜 바꿨나.**
  `scribed`가 Boost에서 쓰던 기능은 다음 세 가지뿐이었습니다.

  - 메모리를 자동으로 관리하는 스마트 포인터[^smartptr]
  - 파일 크기·목록·삭제·폴더 만들기 같은 파일 함수 몇 개
  - 서버 목록 문자열을 나누는 함수 하나

  C++17 표준 라이브러리가 이것을 모두 제공하므로 Boost 의존을 없앴습니다.

- **기대할 수 있는 것.**
  `scribed`를 설치하거나 배포할 때 함께 설치·동봉할 Boost 라이브러리가 없습니다.
  Docker 실행 이미지에도 Boost가 없습니다.

- **기존과 달라진 점.**
  빌드하는 컴퓨터에는 여전히 Boost header가 필요합니다.
  Thrift 자신의 header가 Boost header를 불러오기 때문입니다.
  `configure`의 `--with-boost` 옵션은 없어졌으며, 예전 빌드 스크립트에 남아 있으면 경고만 출력하고 계속합니다.

  로그의 분배·내용·파일 형식과 카운터는 같습니다.
  파일 함수가 실패했을 때의 진단 로그 문구만 표준 라이브러리 표현으로 바뀔 수 있습니다.

  서버 목록을 나누는 새 함수는 원본 빌드가 쓰던 Boost 1.58, 그리고 Boost 1.83과 결과를 비교했습니다.
  탭·공백·콜론·NUL을 포함한 7개 문자로 만든 길이 7 이하의 모든 문자열에서 결과가 같았습니다.

- **관련 설정 키.** 없습니다.

- **예시.**
  예전 Docker 이미지에서는 `ldd`에 Boost filesystem·system 라이브러리가 보였고, 실행 서버에도 이것을 설치해야 했습니다.
  이제 `ldd "$(command -v scribed)"`에 `libboost_*`가 없습니다.
  GCC 8(Rocky 8)은 표준 파일 함수가 별도 라이브러리에 있어, `configure`가 필요할 때만 `libstdc++fs`를 자동으로 붙입니다.

### 고친 원래 버그

원본의 버그 가운데 로그의 분배·파일 형식·전달 결과를 바꾸지 않고 고칠 수 있는 것만 고쳤습니다.
앞의 여덟 가지는 프로그램이 비정상 종료하거나 미정의 동작(UB[^ub])을 하던 경우입니다.
이런 경우에는 지켜야 할 "원본과 같은 결과"가 없으므로 안전한 동작으로 바꿨고, 정상 설정의 결과는 바뀌지 않습니다.
뒤의 세 가지는 논리 오류입니다.
분배·파일 형식은 같고, 일시 실패·메모리 증가·손실이 줄어듭니다.

| 문제 | 생기는 설정 | 구버전 | 신버전 |
| --- | --- | --- | --- |
| [spool 읽기 버퍼](#spool-읽기-버퍼의-해제-방식) | buffer의 file secondary | 미정의 동작 | 바르게 해제 |
| [재시도 범위 0](#retry_interval_range0의-0-나누기) | `retry_interval_range=0` | 종료할 수 있음 | jitter 없이 계산 |
| [bucket 하위 store 오타](#알-수-없는-bucket-하위-store-종류) | `type=netwrok` 등 | 종료할 수 있음 | 설정 오류, `WARNING` |
| [기본 port 없음](#list_default_port가-없을-때의-port) | port 없는 `service_list` | 쓰레기 값 | port 0 |
| [추가 bucket 검사](#추가-bucket-검사의-범위-밖-읽기) | `num_buckets` 6 이상 | 범위 밖 읽기 | 검사 건너뜀 |
| [HDFS 삭제 함수](#hdfs-파일-삭제-함수) | `fs_type=hdfs` | 빌드 불가 | 두 API에 맞춤 |
| [종료 시 exit](#종료할-때-exit를-한-번만) | fb303 `shutdown` | 드물게 crash | exit 한 번 |
| [초당 개수 계산](#max_msg_per_second의-동시-계산) | `max_msg_per_second` | 잠금 없이 셈 | 잠금 아래에서 셈 |
| [동적 목적지 변경](#동적-목적지-변경과-연결-pool) | `use_conn_pool=yes` + 동적 조회 | 엉뚱한 연결을 닫음 | 옛 연결만 닫음 |
| [`service_list` 재연결](#service_list-재연결) | `service_list` | 후보 목록이 계속 늘어남 | 매번 새로 만듦 |
| [재전송 일부 성공](#buffer-재전송-일부-성공) | `buffer` + `file` primary 등 | 남은 로그 손실 | spool에 다시 써서 재시도 |

#### spool 읽기 버퍼의 해제 방식

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

#### retry_interval_range=0의 0 나누기

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

#### 알 수 없는 bucket 하위 store 종류

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

#### list_default_port가 없을 때의 port

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

#### 추가 bucket 검사의 범위 밖 읽기

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

#### HDFS 파일 삭제 함수

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
  확인한 범위는 [HDFS 안내](docs/hdfs.md)에 있습니다.

#### 종료할 때 exit를 한 번만

- **왜 바꿨나.**
  fb303 `shutdown`을 받으면 그 요청을 처리하는 thread가 프로세스 종료를 시작합니다.
  같은 때 main thread도 서버가 멈춘 것을 보고 종료를 시작했습니다.
  두 곳이 동시에 종료 정리를 하면서 드물게 종료 중 비정상 종료(SIGSEGV)가 났습니다.

- **기대할 수 있는 것.**
  종료 정리는 한 번만 일어나고, 다른 쪽은 그 끝을 기다립니다.

- **기존과 달라진 점.**
  종료 코드 0, 종료 로그(`scribe server exiting`), store를 멈추는 순서는 같습니다.
  원본도 같은 구조였으므로 같은 경쟁이 있을 수 있었습니다.

- **관련 설정 키.** 없습니다.

- **예시.**
  구·신 비교 시험(`receiver-restart`)을 개발하던 중, 신버전 수신 서버의 `shutdown` 53번 가운데 1번이 SIGSEGV로 끝났습니다.
  감시 스크립트가 `shutdown` 뒤 종료 코드 0을 기대한다면 이런 드문 실패를 볼 수 있었습니다.
  이제 두 종료 경로가 하나로 모여 이 경쟁이 없습니다.

#### max_msg_per_second의 동시 계산

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

#### 동적 목적지 변경과 연결 pool

- **왜 바꿨나.**
  `dynamic_config_type=thrift_bucket`인 network store는 bucket updater라는 별도 서버에 목적지를 묻고, 바뀌면 연결을 다시 엽니다.
  `use_conn_pool=yes`이면 같은 `host:port`로 가는 연결 하나를 여러 store가 함께 쓰고, 사용자 수(refcount[^refcount])로 닫을 때를 정합니다.
  구버전은 주소를 새 값으로 먼저 바꾼 뒤 연결을 닫아서, 옛 목적지가 아니라 **새 목적지**의 사용자 수를 줄였습니다.

- **기대할 수 있는 것.**
  목적지가 바뀌면 옛 연결만 닫힙니다.
  같은 목적지를 쓰던 다른 store의 연결이 엉뚱하게 닫혀 batch[^batch]가 한 번 실패하는 일이 없습니다.

- **기존과 달라진 점.**
  분배·파일 내용·최종 전달 결과는 같습니다.
  `use_conn_pool=no`(기본값)는 원래부터 자기 연결만 닫았으므로 차이가 없습니다.
  구버전이 남기던 `LOGIC ERROR` 진단 로그가 이 경우에는 나오지 않습니다.

- **관련 설정 키.**
  `use_conn_pool=yes`와 `dynamic_config_type`입니다.
  `bucket_updater_host`·`bucket_updater_port`(또는 `bucket_updater_service`)와 `bucket_updater_ttl`도 해당합니다.
  bucket updater에는 `bucket_updater_ttl`(기본 60초)마다 다시 묻고, 목적지 확인은 `check_interval`마다 합니다.

  모델 복사본은 [동적 조회 설정을 물려받지 않으므로](#network-복사본은-service_list와-동적-조회-설정을-물려받지-않는다) 직접 설정한 store만 해당합니다.

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
  | 분배·내용·최종 전달 | 같음 | 같음 |

  구버전에서 `game_login`의 연결이 닫히면 다음 batch 1회가 실패해 `requeue` 카운터로 집계되고 다시 연결됩니다.
  새 목적지를 쓰던 store가 없을 때 구버전은 다음 진단 로그를 남깁니다.

  ```text
  LOGIC ERROR: attempting to close connection <relay-b.example:1463> that connPool has no entry for
  ```

#### service_list 재연결

- **왜 바꿨나.**
  `service_list`를 쓰는 network store는 연결을 열 때마다 목록을 해석해 서버 후보를 만듭니다.
  구버전은 이전 후보를 비우지 않고 매번 전체 목록을 뒤에 덧붙였습니다.
  그래서 오래 돌수록 메모리가 늘고, 죽은 서버를 여러 번 시도해 다른 서버로 넘어가는(failover[^failover]) 시간이 점점 길어졌습니다.

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

#### buffer 재전송 일부 성공

- **왜 바꿨나.**
  buffer store는 primary[^primary]에 보내지 못한 로그를 secondary spool에 모았다가, primary가 살아나면 spool 파일을 하나씩 다시 보냅니다(replay[^replay]).
  primary가 그 묶음의 앞부분만 처리하고 실패하면, 남은 로그만 spool 파일에 다시 써야 합니다.
  그런데 구버전은 이 파일을 여는 방식이 잘못돼 항상 실패했고, 남은 로그를 `lost`로 세고 spool 파일을 지웠습니다(영구 손실).

- **기대할 수 있는 것.**
  남은 로그가 같은 형식으로 spool 파일에 다시 써지고, `retry_interval`이 지난 뒤 다시 보냅니다.
  전체 실패는 원래부터 계속 재시도했으므로, 일부 실패도 같은 방식이 된 것입니다.

- **기존과 달라진 점.**
  spool 파일 형식은 같아 구버전도 읽을 수 있습니다.
  보존, exactly-once, 디스크 저장 보장(durable ACK)을 새로 약속하지는 않습니다.
  secondary에 `add_newlines=1`이 있으면 기존 기록 규칙대로 다시 쓴 메시지 끝에 LF가 하나 더 붙습니다.

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

  spool은 메시지마다 4-byte little-endian[^little] 길이 뒤에 내용을 둡니다.
  secondary에 `add_newlines=1`이 있으면 다시 쓴 frame에 LF가 하나 더 붙습니다.

  ```text
  secondary에 add_newlines가 없을 때(example1.conf 방식): 다시 써도 같음
    m2 frame:  02 00 00 00  6d 32
  secondary에 add_newlines=1일 때: 다시 쓴 frame에 LF가 하나 더 붙음
    처음 frame:     03 00 00 00  6d 32 0a          ("m2\n")
    다시 쓴 frame:  04 00 00 00  6d 32 0a 0a       ("m2\n\n")
  ```

### 코드 정리 (동작 불변)

- **왜 바꿨나.**
  원본 코드는 잠금과 메모리를 손으로 관리하는 오래된 방식이라, 예외 상황에서 잠금이 풀리지 않거나 메모리가 새는 곳이 있었습니다.
  지금의 C++ 표준 기능으로 같은 일을 하도록 표현을 바꿨습니다.

- **기대할 수 있는 것.**
  설정을 여러 번 다시 읽어도 메모리가 쌓이지 않고, 예외가 나도 잠금이 풀립니다.

- **기존과 달라진 점.**
  로그의 분배·내용·파일 형식·전달·손실 집계·상태 조회·설정 해석은 같습니다.
  바깥에서 보이는 차이는 아래에 적은 진단 로그 몇 줄과, 원래 미정의 동작이던 경우뿐입니다.

- **관련 설정 키.** 없습니다.

- **예시.**
  매일 fb303 `reinitialize`로 설정을 다시 읽는 서버는, 예전에는 다시 읽을 때마다 이전 설정이 메모리에 남았습니다.
  이제는 남지 않고, 설정 해석 결과는 같습니다.

  정리한 항목은 다음과 같습니다.

  - **로그 받기의 잠금.**
    잠금을 손으로 잡고 풀던 코드를, 범위를 벗어나면 자동으로 풀리는 방식(RAII[^raii])으로 바꿨습니다.
    예전에는 중간에 예외가 나면 잠금이 남아 이후 `reinitialize`·`shutdown`·새 category 처리가 멈출 수 있었습니다.
  - **설정 트리의 약한 참조.**
    부모와 자식 설정이 서로를 붙잡고 있어 `reinitialize`마다 이전 설정이 메모리에 남았습니다.
    이제 자식은 부모를 붙잡지 않고 가리키기만 하며(weak reference), 설정 상속 결과는 같습니다.
  - **표준 잠금.**
    store 상태, 연결 pool 목록, HDFS의 잠금을 C++ 표준 잠금(`std::mutex`)으로 바꿨습니다.
    잠그는 지점과 범위는 같습니다.
  - **컴파일러 검사 강화.**
    함수를 잘못 덮어쓰거나 복사하면 빌드할 때 오류가 나게 했습니다(`override`, `= delete`).
    만들어지는 실행 파일의 동작은 같습니다.
  - **표준 스마트 포인터.**
    메모리를 자동으로 돌려주는 포인터를 Boost 것에서 표준 것으로 바꿨습니다.
    같은 일을 같은 방식으로 합니다.
  - **spool 읽기 버퍼.**
    버퍼를 자동으로 돌려주는 표준 방식으로 받고, 메모리가 모자라면 예외 대신 실패 값을 받습니다(nothrow).
    메모리 부족일 때의 손실 집계는 예전과 같습니다.
  - **전역 의존 제거.**
    예전에는 store·큐·연결 pool·설정 조회가 프로세스 전체에 하나뿐인 전역 변수를 직접 읽었습니다.
    이제 서버가 카운터·큐 한도·크기 한도·연결 pool을 담은 "context"를 만들어 각 부품에 넘겨줍니다.
    부품을 서버 전체 없이 따로 시험할 수 있게 됐고, 서버 하나에 context 하나이므로 값·카운터·연결 공유 범위는 같습니다.
  - **그 밖의 정리.**
    설정 값을 읽는 무리한 형 변환, 실행되지 않던 검사, 쓰지 않는 코드를 정리했습니다.
    store thread를 만들지 못하면(원래 미정의 동작) 이제 `Bad config - can't create a store of type: ...` 설정 오류가 됩니다.
    dynamic bucket updater의 "매핑 없음" 진단 로그는 이제 실제 내용을 찍고, 실행될 수 없던 "socket 생성 실패" 로그는 삭제했습니다.

  겉보기에는 고칠 곳 같지만 원본의 관찰 결과를 만드는 코드는 일부러 건드리지 않았습니다.

  - 추가 bucket 검사의 문자열 계산과 bucket key 계산 방식
  - 긴 명령행 옵션의 결함과 시작 실패 시 종료 코드 0
  - 빈 메시지만 든 큐를 전달하지 않는 판단
  - 재시도·bucket·서버 후보 순서에 쓰는 무작위 순서(GNU C 라이브러리의 `rand()`)
  - store 큐의 thread와 깨우기 방식(시간 기준이 바뀔 수 있어 그대로 둠)

### 새 설정 키

신버전에서 새로 생긴 설정 키는 두 개뿐이며, 쓰지 않아도 기본값으로 동작합니다.

#### 통신 크기 제한과 확인한 호환성

- **왜 추가했나.**
  새 Thrift(0.25)는 원본 시절과 다른 기본 크기 한도가 있습니다(frame 16,384,000 bytes, message 104,857,600 bytes).
  그대로 두면 원본이 받던 큰 요청을 거절하게 되므로, 한도를 설정으로 정하게 하고 기본값을 256 MiB로 잡았습니다.

- **기대할 수 있는 것.**
  설정하지 않아도 256 MiB까지의 요청을 받고 보냅니다.
  서버 수신, network store의 relay 송신, dynamic bucket updater 조회에 같은 값이 적용됩니다.

- **기존과 달라진 점.**
  256 MiB를 넘는 요청만 처리가 다릅니다.
  **한도를 넘는 relay batch는 나누거나 버리지 않고, 실패로 처리해 계속 다시 시도합니다.**
  이 한도는 프로세스 메모리 상한이 아니며, 원본이 받던 모든 큰 요청의 호환을 보장하지도 않습니다.

- **관련 설정 키와 영향.**

  ```conf
  # 설정 파일의 최상위(어떤 <store> 블록에도 넣지 않는 위치)에 둡니다.
  # 아래 두 줄은 기본값과 같습니다.
  thrift_max_frame_size=268435456
  thrift_max_message_size=268435456
  ```

  | 키 | 기본값 | 허용 값 | 바꾸는 방법 |
  | --- | --- | --- | --- |
  | `thrift_max_frame_size` | 268435456 (256 MiB) | 1 ~ 2147483647 | 재시작 |
  | `thrift_max_message_size` | 268435456 (256 MiB) | 1 ~ 2147483647 | 재시작 |

  - 기준은 요청 내용의 크기이며, 앞에 붙는 4-byte 길이 표시는 빼고 셉니다.
  - 두 값이 다르면 작은 쪽이 실제 한도가 됩니다.
  - 값은 십진수 byte 수로만 씁니다.
    - `0`, 음수, `+` 부호, 16진수, `256M` 같은 단위는 잘못된 값입니다.
    - 시작할 때 값이 잘못됐으면 `Invalid Thrift wire limits; listener not started`를 남기고 시작에 실패합니다(종료 코드는 0).
  - 시작할 때만 읽습니다.
    - fb303 `reinitialize`로 바꾸면 `Thrift wire-limit changes require restart`를 남기고 기존 값을 유지합니다.

  신버전 network store는 보내기 전에 요청 크기를 계산합니다.
  요청 전체에 21 bytes, 메시지마다 15 bytes + category 길이 + 메시지 길이입니다.
  한도를 넘으면 `Relay Log exceeds configured wire limit <268435456> bytes`를 남기고 일시 실패로 처리합니다.
  buffer store 아래라면 spool 파일을 지우지 않고 재시도를 반복하며, 가장 오래된 파일부터 보내므로 뒤의 spool 파일도 모두 멈춥니다.

- **예시(계산).**
  짧은 메시지를 많이 보내는 category를 128 MiB spool로 보호하는 경우입니다.

  ```conf
  <store>
    category=game_pvp
    type=buffer
    retry_interval=30
    retry_interval_range=10

    <primary>
      type=network
      remote_host=relay-a.example
      remote_port=1463
    </primary>

    <secondary>
      type=file
      fs_type=std
      file_path=/var/log/scribed/spool
      base_filename=game_pvp
      max_size=134217728
    </secondary>
  </store>
  ```

  - spool 파일은 메시지마다 `4-byte 길이 + 메시지`를 저장합니다.
  - 재전송 요청은 메시지마다 `15 + category 길이 + 메시지 길이` bytes가 됩니다.
  - 따라서 **재전송 요청 크기 ≈ spool 파일 크기 + 메시지 수 × (11 + category 길이)** 입니다.
    - `game_pvp`(8글자)라면 메시지 하나당 약 19 bytes가 늘어납니다.

  | 평균 메시지 길이 | 128 MiB 파일의 메시지 수 | 재전송 요청 크기 | 256 MiB 한도 |
  | --- | --- | --- | --- |
  | 12 bytes | 8,388,608 | 293,601,301 bytes (약 280 MiB) | **넘음: 계속 재시도** |
  | 30 bytes | 약 3,947,580 | 약 209,221,761 bytes (약 199.5 MiB) | 통과 |

  `game_pvp`라면 평균 메시지가 약 15 bytes(= category 길이 + 7)보다 짧을 때, 가득 찬 128 MiB spool 하나가 256 MiB를 넘습니다.
  이런 category는 secondary `max_size`를 더 작게 잡으세요(예: `max_size=67108864`).
  `max_size`는 쓰고 난 뒤에 검사하므로, 파일이 `max_size`를 조금(대략 `max_write_size`, 기본 1,000,000 bytes 이내) 넘을 수 있습니다.

  secondary에 `max_size`를 쓰지 않으면 file store 기본값 1,000,000,000 bytes가 적용됩니다.
  그러면 장애가 길어질 때 256 MiB를 넘는 spool이 생길 수 있습니다.
  `max_write_size`나 회전 설정만 줄여서는 요청 크기가 보장되지 않습니다.
  한도를 올리려면 받는 서버도 그 크기를 받을 수 있어야 합니다.

- **확인한 호환성.**
  대표적인 작은 로그로 구 서버 → 새 서버, 새 서버 → 구 서버 전송과 일반 spool 파일의 양방향 읽기를 확인했습니다.
  구 ThriftFile writer → 새 reader와 새 writer → 구 reader도 확인했습니다.
  모든 파일, 손상된 입력, 언어별 client, 장애 상황을 확인한 것은 아닙니다.

  근거는 [호환성 정책](docs/compatibility-policy.md), [실제 비교 기록](docs/verification.md), [ThriftFile 처리 기록](docs/compatibility-policy.md#thriftfile-chunk-초과와-empty)에 있습니다.

### 검증 도구

설치에는 필요 없는 개발자용 도구입니다.

- **`tools/validate_linux.py`**:
  프로젝트 밖의 새 폴더에서 빌드 설정·전체 빌드·시험·임시 설치·`scribed --help`까지 한 번에 확인합니다.
  시스템에 설치하거나 서비스를 시작하지 않으며, 준비 방법은 [빌드 안내](docs/build.md#검증기)에 있습니다.
- **`tools/daemon_differential.py`와 `tools/old-lane/`**:
  구버전과 신버전 daemon을 실제로 띄워 같은 요청을 보내고, 응답·저장 bytes·카운터·symlink·종료 코드를 비교합니다.
  `tools/old-lane/`은 구버전을 다시 빌드하고 비교를 네트워크와 권한이 없는 컨테이너에서 돌리는 recipe입니다([세 명령](tools/old-lane/README.md)).
- **`Dockerfile`**:
  [Docker 방식](#docker-방식)의 이미지를 만들며, 구·신 비교에 쓰는 신버전 이미지도 이것으로 만듭니다.
  설치 순서와 같은 빌드이므로, 그 순서가 실제로 동작한다는 확인도 됩니다.

## 일부러 남겨 둔 원래 버그

기준은 [공개 Facebook Scribe 원본](https://github.com/facebookarchive/scribe/tree/fcd294faffd1e88af1643a3a8c2359c41713f7c2)입니다.
아래 항목은 원본의 버그지만, 고치면 로그가 저장되는 위치·내용·형식, 전달 여부, 상태 조회 결과가 바뀝니다.
그 결과를 읽는 기존 프로그램(적재·집계 job, 감시 도구)을 지키기 위해 **구버전과 신버전이 똑같이 동작하도록 남겨 두었습니다.**
고치는 새 옵션도 추가하지 않았습니다.

각 항목은 어떤 동작인지, 왜 남겼는지, 무엇을 기대하면 되는지, 구·신 차이, 관련 설정 키, 예시 순서로 설명합니다.
반대로 `retry_interval_range=0`처럼 원본이 비정상 종료하던 경우는 남기지 않았습니다([고친 원래 버그](#고친-원래-버그)).

### 먼저: 모델과 복사본

여러 항목에 나오는 "복사본"을 먼저 설명합니다.

`category=default`, `categories=a b c`, `category=game_*`(끝이 `*`인 prefix)로 쓴 `<store>`는 **모델**입니다.
기본값 `new_thread_per_category=yes`에서는 실제로 로그를 처리하는 store가 category마다 만든 모델의 **복사본**입니다.
`categories=`의 이름들은 시작할 때, `default`와 prefix는 그 category의 첫 로그가 들어올 때 복사됩니다.

복사본의 file store는 이름과 위치가 바뀝니다.

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

같은 설정을 `category=game_login`으로 직접 쓰면 `/var/log/scribed/data/ignored_name-2026-10-07_00000`이 됩니다(category 폴더 없음).
`new_thread_per_category=no`이면 복사하지 않고 한 store가 모든 category를 받으므로, file store라면 `base_filename` 파일 하나에 모입니다.
복사본은 아래 항목처럼 일부 설정을 물려받지 않습니다.

| 항목 | 관련 설정 키 |
| --- | --- |
| [Bucket 복사본의 범위·key 제거](#bucket-복사본은-bucket_range와-remove_key를-물려받지-않는다) | `bucket_range`, `remove_key` |
| [추가 bucket 검사](#추가-bucket-검사는-이름-대신-문자열-중간을-본다) | `num_buckets`, `bucket0`…`bucketN` |
| [ThriftFile 복사본의 형식](#thriftfile-복사본은-use_simple_file을-무시한다) | `use_simple_file` |
| [Network 복사본의 목록·동적 조회](#network-복사본은-service_list와-동적-조회-설정을-물려받지-않는다) | `service_list` 등 6개 |
| [빈 연결 key 공유](#service_list와-use_conn_pool은-빈-연결-key-하나를-같이-쓴다) | `service_list`, `use_conn_pool` |
| [빈 메시지만 든 큐](#빈-메시지만-든-큐는-전달되지-않는다) | `add_newlines`(영향) |
| [OK의 뜻](#ok는-메모리-큐에-받았다는-뜻이다) | 없음 |
| [긴 명령행 옵션](#긴-명령행-옵션은-값을-받지-못한다) | `--config`, `--port` |

### Bucket 복사본은 bucket_range와 remove_key를 물려받지 않는다

- **어떤 동작인가.**
  bucket store 복사본은 `num_buckets`, `bucket_type`, `delimiter`와 하위 store를 복사하지만, `bucket_range`와 `remove_key`는 복사하지 않습니다.
  그래서 복사본에서는 `bucket_type=key_range`의 범위가 0이 되어 **모든 메시지가 bucket 0으로** 갑니다.

  `remove_key=yes`여도 **key가 메시지에 남습니다.**
  `key_hash`·`key_modulo`는 분배는 맞지만, key가 남는 점은 같습니다.

- **왜 남겼나.**
  고치면 기존 복사본 로그가 다른 bucket 폴더로 옮겨 가고, 내용에서 key가 빠집니다.
  bucket 폴더별로 파일을 가져가거나, key가 붙은 형식을 파싱하는 프로그램이 다른 결과를 보게 됩니다.

- **무엇을 기대하면 되나.**
  `categories=`·`default`·prefix 모델로 만든 bucket store는 범위 분배와 key 제거를 하지 않는다고 보세요.
  범위 분배나 key 제거가 필요하면 `category=`로 직접 설정합니다.

- **구·신 차이.** 없습니다.
  둘 다 같은 폴더에 같은 내용을 씁니다.

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
  `bucket0`부터 `bucketN`까지 직접 정의하면, 원본은 `bucketN+1`이 더 있는지 검사하려고 합니다.
  하지만 계산 실수 때문에 이름 대신 **글자 `"bucket"`의 중간부터를 이름으로 찾습니다.**

  `num_buckets=1`이면 `cket`, 2이면 `ket`, 3이면 `et`, 4이면 `t`, 5이면 빈 이름을 찾습니다.
  그래서 `bucketN+1`을 정의해도 거부하지 않습니다.

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
  `type=thriftfile`에 `use_simple_file=1`(0이 아닌 값)을 주면 메시지 내용만 이어 쓰는 raw 형식으로 저장합니다.
  그런데 복사본은 이 값을 복사하지 않아, **길이 정보와 chunk 경계 padding이 붙은 framed 형식**으로 저장합니다.
  category별 복사본을 쓰는 `thriftmultifile`도 같습니다.

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

  함께 알아둘 점:

  - 일반 spool 파일의 형식은 ThriftFile 형식과 별개입니다.
  - 이전 개발 버전이 raw 형식 복사본 파일을 이미 만들었다면 그 파일은 그대로 남습니다.
    - 지금 버전은 변환하지 않으므로, 같은 폴더에 서로 다른 형식의 파일이 있을 수 있습니다.
    - reader를 고르거나 이전 버전으로 되돌리기 전에 실제 파일 형식을 확인하세요.
  - 길이 표시 4 bytes를 포함한 메시지가 `chunk_size`(기본 16,777,216 bytes)보다 크면 오류 로그만 남고 기록되지 않습니다.
    - 그런데도 Scribe 응답과 성공 집계는 성공으로 보일 수 있습니다(원본 처리 그대로).

### Network 복사본은 service_list와 동적 조회 설정을 물려받지 않는다

- **어떤 동작인가.**
  network store 복사본은 원래 필드인 `remote_host`, `remote_port`, `use_conn_pool`, `timeout`, `smc_service`만 복사합니다.
  다음 설정은 복사하지 않습니다.

  | 복사하지 않는 설정 | 복사본에서 생기는 일 |
  | --- | --- |
  | `service_list`, `list_default_port` | 목록이 비어 연결할 수 없음 |
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
  `default`·category 모델로 network store를 쓸 때는 `remote_host`/`remote_port`를 쓰거나, category를 직접 설정하세요.
  그리고 실제 목적지와 fb303 상태를 확인하세요.
  공개 원본의 서비스 이름 조회(`smc_service`)는 항상 실패하는 예제 구현이므로, 실제 서비스 탐색이 된다고 가정하지 마세요.

- **구·신 차이.**
  없습니다.
  직접 설정한 store의 동적 조회와 TTL 갱신은 원본대로 동작합니다.

- **관련 설정 키.**
  모델 store의 `service_list`, `list_default_port`, `service_options`, `service_cache_timeout`입니다.
  `ignore_network_error`와 `dynamic_config_type`도 해당합니다.

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

  처음 보는 category(예: `game_event`)가 들어올 때마다 복사본이 만들어지지만, 연결할 서버가 없습니다.
  로그는 `/var/log/scribed/spool/game_event/game_event_00000`, `_00001`, …에 계속 쌓입니다.
  `game_event:retries` 카운터가 늘고, fb303 상태는 `WARNING`, 상세 설명은 `Failed to connect`입니다.
  `ignore_network_error`가 적용되는 경우에도 실제 연결 실패가 성공으로 바뀌지는 않습니다.

### service_list와 use_conn_pool은 빈 연결 key 하나를 같이 쓴다

- **어떤 동작인가.**
  `use_conn_pool=yes`인 연결은 이름(key)으로 공유됩니다.
  `remote_host`/`remote_port`는 `host:port`, `smc_service`는 서비스 이름이 key인데, `service_list`는 **빈 문자열**이 key입니다.
  그래서 서로 다른 목록을 쓰는 store들이 **먼저 열린 연결 하나를 같이 씁니다.**

- **왜 남겼나.**
  연결을 목록마다 나누면 전송 대상, 연결 수, 서버 선택 비율이 바뀝니다.

- **무엇을 기대하면 되나.**
  `service_list`가 서로 다른 store에 `use_conn_pool=yes`를 함께 쓰면, 로그가 다른 목록의 서버로 갈 수 있습니다.
  서로 다른 목록을 쓴다면 실제 목적지를 확인하고, 원래 있던 옵션인 `use_conn_pool=no`(기본값)를 검토하세요.

- **구·신 차이.**
  없습니다.
  재연결할 때 후보 목록이 늘어나던 문제는 따로 [고쳤습니다](#service_list-재연결).

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
  store 큐는 쌓인 **메시지 내용의 총 byte 수**를 보고 처리할지를 정합니다.
  빈 메시지만 있으면 메시지가 있어도 총 크기가 0이라, 주기 처리 때나 종료할 때 전달하지 않습니다.
  서버는 이미 `OK`를 돌려주고 `received good` 카운터를 늘렸는데도, 파일은 비어 있고 `lost` 카운터도 0일 수 있습니다.

- **왜 남겼나.**
  고치면 `add_newlines=1`인 store에 빈 줄이 새로 저장되고 전달 횟수가 달라집니다.
  줄 단위로 읽는 프로그램이 새로운 빈 줄을 보게 됩니다.

- **무엇을 기대하면 되나.**
  빈 메시지만 보내는 용도(예: 살아 있음 신호)는 파일에 남지 않는다고 보세요.
  같은 큐에 비어 있지 않은 메시지가 함께 들어오면 그때는 빈 메시지도 함께 처리됩니다.
  메시지가 하나도 없는 `Log` 요청과는 다른 경우입니다.

- **구·신 차이.** 없습니다.

- **관련 설정 키.**
  특정 키는 없습니다.
  `add_newlines` 값에 따라 고쳤을 때의 결과가 달라집니다.

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
  서버의 `OK` 응답은 로그를 메모리 큐에 받았다는 뜻입니다.
  디스크 저장 완료나 중복 없는 전달을 보장하지 않습니다.
  파일 `flush`도 디스크 기록을 강제하는 `fsync`[^fsync]와 다릅니다.

- **왜 남겼나.**
  응답의 뜻을 바꾸면 응답 시점과 처리량이 달라지고, 기존 클라이언트의 재시도 동작에 영향을 줍니다.

- **무엇을 기대하면 되나.**
  `OK`를 받은 직후 프로세스가 갑자기 끝나면(SIGKILL, 전원 차단 등) 큐에 있던 로그는 남지 않을 수 있습니다.
  잃으면 안 되는 로그는 클라이언트 쪽 재전송이나 다른 보존 수단을 함께 생각하세요.

- **구·신 차이.**
  없습니다.
  신버전은 디스크 저장 보장(durable ACK), exactly-once, fsync를 새로 약속하지 않습니다.

- **관련 설정 키.** 없습니다.

- **예시.**
  클라이언트가 메시지 100개를 보내 `OK`를 받은 직후 서버가 SIGKILL로 끝났다고 합시다.
  store thread가 아직 파일에 쓰지 않은 메시지는 구·신 모두 사라집니다.

### 긴 명령행 옵션은 값을 받지 못한다

- **어떤 동작인가.**
  원본은 `--config`와 `--port`를 **값을 받지 않는 옵션**으로 선언했습니다.
  `--config=/etc/scribed/scribed.conf`처럼 쓰면 값을 받지 않는 옵션이라며 사용법만 출력하고 종료(코드 0)합니다.
  `--config /etc/scribed/scribed.conf`처럼 쓰면 값이 옵션에 전달되지 않아 정상 동작을 기대할 수 없습니다.

- **왜 남겼나.**
  명령행 해석 결과도 바깥에서 보이는 동작이므로 원본대로 둡니다.

- **무엇을 기대하면 되나.**
  항상 짧은 옵션 `-c`, `-p`를 쓰세요.
  옵션이 아닌 첫 인자도 설정 파일로 읽습니다.

- **구·신 차이.** 없습니다.

- **관련 설정 키.**
  명령행 `--config`, `--port`.

- **예시.**

  ```sh
  scribed -c /etc/scribed/scribed.conf -p 1463
  # 옵션이 아닌 첫 인자도 설정 파일로 읽습니다.
  scribed /etc/scribed/scribed.conf
  ```

### 그 밖에 원본 그대로인 주의점

버그라기보다 원본 설계에서 나오는 동작이며, 구버전과 신버전이 같습니다.
기존 설정을 옮기거나 새로 쓸 때 확인하세요.

#### prefix는 가장 긴 것이 아니라 정렬 순서상 첫 번째가 이긴다

처음 보는 category는 ① 정확히 같은 이름의 store, ② prefix 모델, ③ `default` 모델 순서로 찾습니다.
prefix 모델은 byte 순서로 정렬한 목록에서 **처음 맞는 것**을 쓰며, 가장 길게 맞는 것을 고르지 않습니다.
`*`는 영문자·숫자·`_`·`-`보다 앞에 정렬되므로, 겹치는 prefix가 있으면 사실상 짧은 쪽이 이깁니다.
예를 들어 `game_*`와 `game_login_*`가 함께 있으면 `game_login_eu`는 `game_*`가 받습니다.

#### new_thread_per_category 기본값은 category마다 thread를 만든다

기본값 `new_thread_per_category=yes`(정확히 `no`라고 쓴 경우만 꺼짐)에서는 category마다 store 큐와 thread가 하나씩 생깁니다.
각 store는 자기 파일을 열고, `use_conn_pool=no`(기본값)이면 network 연결도 따로 엽니다.
예를 들어 `category=default` 모델 하나로 category 300개를 받으면 store thread 300개와 열린 파일 300개 이상이 생깁니다.
값을 `no`로 바꾸면 출력 위치가 바뀌므로, 기존 설정의 값을 함부로 바꾸지 마세요.

#### buffer secondary의 add_newlines는 재전송 때 줄바꿈을 하나 더 만든다

buffer의 secondary(spool)에 `add_newlines=1`을 두면, 붙인 LF가 spool frame 안에 함께 저장됩니다.
재전송할 때 받는 쪽 file store에도 `add_newlines=1`이 있으면 `메시지\n\n`이 저장됩니다.
장애 없이 바로 간 로그는 `메시지\n`이므로, **같은 로그가 spool을 거쳤는지에 따라 바이트가 달라집니다.**

```text
장애 없이 바로 전송:     받는 쪽 파일  6c 6f 67 69 6e 20 6f 6b 0a          "login ok\n"
spool에 저장된 frame:                09 00 00 00 6c 6f 67 69 6e 20 6f 6b 0a  (길이 9, LF 포함)
재전송 후 받는 쪽 파일:              6c 6f 67 69 6e 20 6f 6b 0a 0a       "login ok\n\n"
```

primary에만 `add_newlines=1`을 두고 secondary에는 두지 않으면 원본 [`examples/example1.conf`](examples/example1.conf)와 같은 방식이 됩니다.
이때는 재전송 후에도 `login ok\n` 하나만 저장됩니다.
운영 중인 설정을 바꾸면 이미 쌓인 spool의 LF는 그대로이므로, 다운스트림 영향을 먼저 확인하세요.

#### spool 파일 하나가 Log 요청 하나로 재전송된다

buffer는 재전송할 때 **가장 오래된 spool 파일 하나를 통째로 읽어 Log 요청 하나**로 보냅니다.
`check_interval`마다 `buffer_send_rate`(기본 1)개 파일을 보내므로, secondary `max_size`가 재전송 요청 하나의 크기를 정합니다.
요청이 [256 MiB 한도](#통신-크기-제한과-확인한-호환성)를 넘으면 그 파일과 뒤의 파일이 모두 멈춥니다.

받는 서버는 큐 크기를 요청을 넣기 **전에** 검사하므로, 큰 요청 하나는 받아들입니다.
하지만 그동안 그 category의 큐가 `max_queue_size`를 넘어, 받는 서버의 모든 클라이언트가 `TRY_LATER`를 받을 수 있습니다.
받는 서버의 `max_queue_size`는 보내는 쪽 secondary `max_size`보다 넉넉히 크게 잡으세요.

```conf
# 보내는 서버: secondary max_size=134217728 (128 MiB)
# 받는 서버가 기본 max_queue_size=5000000(약 4.8 MiB)이면 재전송 요청 하나만으로 큐가 한도를 넘습니다.
# 받는 서버 최상위 설정 예:
max_queue_size=268435456
```

#### max_queue_size는 모든 category를 한꺼번에 본다

`max_queue_size`(기본 5,000,000 bytes)는 store 큐 하나에 쌓여 아직 처리되지 않은 메시지 내용의 한도입니다.
서버는 Log 요청을 넣기 전에 **모든 category의 모든 store 큐**를 검사합니다.
하나라도 한도를 넘으면 요청에 든 category와 상관없이 요청 전체에 `TRY_LATER`를 돌려줍니다.
예를 들어 `game_replay`의 다음 서버가 느려 큐가 넘치면, `game_login`만 보내는 클라이언트도 `TRY_LATER`를 받습니다.

이때 `denied for queue size` 카운터가 늘어나며, 클라이언트는 `TRY_LATER`를 받으면 다시 보내야 합니다.

#### max_msg_per_second의 절반 예외

`max_msg_per_second`(기본 0 = 제한 없음)를 넘으면 요청 전체에 `TRY_LATER`를 돌려주고 `denied for rate` 카운터가 늘어납니다.
단, **한 요청의 메시지 수가 한도의 절반보다 많으면 항상 받고, 그 초의 개수에도 세지 않습니다.**
큰 요청을 계속 거절하면 그 요청은 영원히 들어올 수 없기 때문입니다.
예를 들어 한도가 1000이면 600개짜리 요청은 언제나 받습니다.

#### 주석 기호 #은 줄 어디에서나 동작한다

설정 파일에서 `#`은 줄 맨 앞이 아니어도 **그 뒤를 모두 주석으로 지웁니다.**
그래서 값 안에 `#`을 쓸 수 없고, 앞뒤 공백과 탭은 지워집니다.

```text
설정 파일에 쓴 줄                      서버가 읽는 값
max_size=1000000   # 1 MB              max_size=1000000
file_path=/var/log/scribed/game#1      file_path=/var/log/scribed/game
```

#### use_conn_pool은 host와 port마다 TCP 연결 하나를 공유한다

`use_conn_pool=yes`이면 같은 `host:port`로 보내는 network store들이 TCP 연결 하나를 함께 쓰고, 한 번에 한 store씩 보냅니다.
기본값 `no`에서는 store(복사본 포함)마다 자기 연결을 엽니다.
key는 설정에 쓴 문자열 그대로라서, `relay-a.example:1463`과 그 서버의 IP로 쓴 값은 서로 다른 연결입니다.

#### check_interval이 회전 검사와 재시도 주기를 정한다

`check_interval`(기본 5초, 0이면 1초)마다 각 store가 주기 작업을 합니다.
시간 기반 회전 검사, buffer의 재연결 시도와 spool 재전송, 동적 목적지 확인이 모두 이 주기를 따릅니다.
예를 들어 `retry_interval=10`, `retry_interval_range=0`이면 "마지막 시도 후 10초 초과"를 5초마다 검사하므로, 실제로는 약 15초마다 재연결을 시도합니다.

#### 시작에 실패해도 종료 코드는 0이다

`scribed`는 시작에 실패해도 **종료 코드 0**으로 끝납니다.
예를 들어 port가 이미 쓰이고 있거나 `thrift_max_frame_size=256M`처럼 잘못된 한도를 주면, `Exception in main: ...`을 남기고 0으로 끝납니다.
반대로 store 설정이 잘못되면 프로세스는 계속 떠 있지만 fb303 상태가 `WARNING`입니다.
그래서 종료 코드나 "실패 시 재시작" 조건만으로는 이상을 알 수 없으니, fb303 상태·카운터, 열린 port, 실제 파일로 감시하세요.

#### 빈 메시지가 든 spool은 재전송이 중간에 멈출 수 있다

secondary에 `add_newlines`가 없을 때 빈 메시지는 길이 0인 frame(`00 00 00 00`)으로 저장됩니다.
재전송할 때 spool 읽기는 길이 0인 frame을 **파일 끝으로 여겨 멈추고**, 그때까지 읽은 메시지를 보낸 뒤 파일을 지웁니다.
그 뒤의 메시지는 전달되지 않는데 `lost`·`bytes lost` 카운터는 늘지 않습니다.
`add_newlines=1`이면 빈 메시지가 `0a` 한 byte로 저장되어 이 문제는 없지만, [줄바꿈이 하나 더 생깁니다](#buffer-secondary의-add_newlines는-재전송-때-줄바꿈을-하나-더-만든다).

```text
장애 중 spool에 쌓인 메시지 "a", "", "b" (add_newlines 없음)
  01 00 00 00 61 | 00 00 00 00 | 01 00 00 00 62
재전송: "a"만 보내고 파일 삭제. "b"는 전달되지 않음
```

근거는 [호환성 정책](docs/compatibility-policy.md#남긴-원본-버그)에 있습니다.

#### 그 밖의 주의점

- 원본 설정 파서는 잘못된 설정을 모두 거부하지 않습니다.
  - 준비되지 않은 store가 있어도 listener가 열리고 `OK`를 돌려줄 수 있습니다.
- 정의하지 않은 category의 로그는 버려지고 `received bad` 카운터가 늘어납니다.
  - category가 빈 로그는 `received blank category`로 셉니다.
- `_current`는 일반 파일 저장에서는 symlink지만, HDFS에서는 경로를 담은 일반 파일입니다.
- HDFS 저장을 일반 spool 파일의 재전송 지원으로 해석하지 마세요.
  - 원본 HDFS의 파일 읽기와 닫힌 파일 잘라내기에는 제한이 남아 있습니다.

## 테스트 결과

아래 결과는 2026-10-07 최종 `main`(`9e8d775`) 기준입니다.
WSL의 Rocky 9.8(GCC 11.5, 20 core)과 Docker 29.8에서, 이전 산출물을 모두 지우고 의존성부터 처음 다시 만들어 실행했습니다.
모든 수치는 이 한 번 실행의 값이며, 한 환경의 결과를 전체 호환성이나 운영 준비 완료로 확대하지 않습니다.

### 시험 묶음

`tools/validate_linux.py`의 전체 시험 240개가 실패 0, 오류 0, 건너뜀 0으로 통과했습니다.
빌드한 `scribed`는 Boost 라이브러리를 링크하지 않았습니다.

컴파일 경고는 30줄이었습니다.

- 26줄: Thrift 자신의 설정 header가 같은 이름(`PACKAGE_VERSION`, `PACKAGE_STRING`)을 다시 정의한다는 경고
- 1줄: Python 설치 단계의 안내(byte-compile을 하지 않음)
- 2줄: 재시도 간격 계산 코드의 부호 있는 수와 없는 수 비교
- 1줄: store 큐 상태 조회 코드의 속성(attribute) 무시 안내

### 설치 순서

[원래 Scribe 방식](#원래-scribe-방식)의 명령을 깨끗한 컨테이너 두 개에서 그대로 실행했습니다.

| 컨테이너 | 컴파일러 | 결과 |
| --- | --- | --- |
| `ubuntu:24.04` | GCC 13.3.0 | `scribed --help`, `ldd` 통과, Boost 없음 |
| `rockylinux:9` | GCC 11.5.0 | `scribed --help`, `ldd` 통과, Boost 없음 |

이 컨테이너들에서는 전체 시험 묶음을 실행하지 않았습니다.

### 구버전과 신버전 비교

구버전은 `tools/old-lane/`의 recipe로 다시 빌드했습니다.
공개 원본 `fcd294f`를 Ubuntu 16.04, GCC 5.4, Thrift/fb303 0.9.0으로 빌드하며, 원본에 더한 변경은 빌드 설정(autotools[^autotools])만 고치는 하나입니다.

구·신 daemon을 각각 실제로 띄워 같은 입력을 주고 결과를 비교했습니다.
아래 17개 case를 한 번씩 실행했고 모두 통과했습니다.
통과는 응답, 카운터, 저장 파일, symlink, 종료 코드가 구·신 모두 같았다는 뜻입니다.

#### 원본 계약 10개

| case | 확인한 것 |
| --- | --- |
| `file` | 파일 저장, 상태·카운터, 빈 요청, 잘못된 category |
| `stores` | `null`·`multi`·`category` store |
| `rotation` | 크기 회전, `reinitialize` 뒤 이어 쓰기 |
| `restart` | 강제 종료 뒤 재시작해 같은 파일에 이어 쓰기 |
| `spool` | 수신측이 없을 때 spool, 살아난 뒤 전체 재전송 |
| `mixed-spool` | 위 흐름을 구 → 신, 신 → 구로 |
| `file-stores` | bucket·thriftfile·multifile 파일 형식 |
| `fb303` | 옵션·카운터 조회, 모르는 요청 뒤 회복 |
| `mapping` | dynamic bucket updater로 목적지 조회·변경 |
| `game-profile` | 게임 서버에서 흔한 설정 기능 묶음 |

`game-profile`은 가상의 설정 하나에 다음 기능을 모았습니다.

- prefix가 섞인 `categories=` 목록과 `category=default` 모델, 단독 prefix 모델
- `type=multi` 아래 두 개의 buffer
- 연결 pool을 쓰는 network primary와 쓰지 않는 network primary, 각각 `add_newlines=1` file secondary
- `rotate_period=1h`인 file primary
- 줄 중간의 `#` 주석

#### 운영 시나리오 7개

세 역할로 실제 운영 흐름을 흉내 냈습니다.

- **송신측**: buffer store를 쓰는 `scribed`입니다.
  - primary는 수신측으로 보내는 network store, secondary는 spool 파일입니다.
- **수신측**: 받은 로그를 file store로 저장하는 `scribed`입니다.
- **소비 클라이언트**: 수신측 폴더를 읽기만 하는 쪽입니다.
  - 파일 목록, `_current`가 가리키는 파일, 파일을 번호 순서로 이은 내용을 확인합니다.

| case | 흐름 | 결과 |
| --- | --- | --- |
| `relay-stream` | 송신측 → 수신측 연속 전송, 수신측이 작은 크기로 회전 | 순서 보존 |
| `mixed-relay-stream` | 위 흐름을 구 송신 → 신 수신, 신 송신 → 구 수신으로 | 순서 보존 |
| `receiver-restart` | 수신측 정상 종료 → spool → 같은 폴더로 재시작 | 재전송 후 이어 씀 |
| `receiver-crash` | 위 흐름을 SIGKILL로 | 재전송 후 이어 씀 |
| `sender-restart-spool` | 송신측이 spool을 남기고 종료 → 재시작 | 이전 spool 재전송 |
| `mixed-sender-restart-spool` | 위 흐름에서 spool을 쓴 쪽과 읽는 쪽 버전을 바꿈 | 이전 spool 재전송 |
| `throttle-retry` | 수신측 초당 한도 4, 메시지 5개 | 5개 모두 순서대로 |

각 case의 내용은 다음과 같습니다.

- **`relay-stream`, `mixed-relay-stream`**:
  송신측에 로그를 세 번 보내고, 수신측은 `max_size=4`로 받은 로그를 저장하며 회전합니다.
  소비 클라이언트는 `_00000`, `_00001`, `_00002` 세 파일이 차례로 생기고 `_current`가 마지막 파일로 옮겨 가는 것을 봅니다.
  파일을 이은 내용은 보낸 순서와 같았습니다.
- **`receiver-restart`**:
  첫 로그가 수신측 파일에 보인 뒤 수신측을 fb303 `shutdown`으로 멈춥니다.
  송신측은 다음 로그를 보내지 못해 spool에 쓰고, 수신측을 같은 설정·같은 폴더로 다시 띄우면 spool을 재전송합니다.
  이어서 새 로그도 바로 전달되며, 수신측은 모두 같은 파일(`_00000`)에 이어 씁니다.
- **`receiver-crash`**:
  `receiver-restart`와 같지만 수신측을 SIGKILL로 강제 종료합니다.
  송신측에서는 두 경우가 똑같이 보이며, 결과도 같았습니다.
- **`sender-restart-spool`, `mixed-sender-restart-spool`**:
  수신측이 없는 동안 송신측이 spool을 쓰고 정상 종료하며, spool 파일은 지워지지 않고 남습니다.
  수신측을 띄우고 송신측을 같은 spool 폴더로 다시 띄우면, 이전 프로세스가 남긴 spool을 재전송한 뒤 연속 전송으로 돌아갑니다.
  mixed는 구버전이 쓴 spool을 신버전이, 신버전이 쓴 spool을 구버전이 재전송합니다(수신측은 신버전).
- **`throttle-retry`**:
  수신측은 `max_msg_per_second=4`이고, 같은 1초 안에 송신측이 메시지 5개를 보냅니다.
  수신측은 다섯 번째 메시지를 `TRY_LATER`로 거절하고, 송신측은 그것을 spool에 쓴 뒤 `retry_interval`이 지나 다시 보냅니다.
  수신측 파일에는 다섯 개가 모두 보낸 순서대로 남았습니다.

#### 이 결과가 보여 주지 않는 것

- 디스크 저장 보장이나 exactly-once를 보여 주지 않습니다.
  - `OK`는 메모리 큐에 받았다는 뜻이고, SIGKILL은 첫 로그가 파일에 보인 뒤에만 보냈습니다.
- 각 case는 한 번씩만 실행했으며, 반복 실행의 통계는 없습니다.
- 재전송 일부 성공은 구·신이 [일부러 다르게](#buffer-재전송-일부-성공) 동작하므로 비교하지 않았습니다.
- 반복 실패, 여러 송신측, 연결 pool, `service_list`, 디스크 가득 참, 실제 운영 설정과 부하는 다루지 않았습니다.
- 구버전 실행 파일은 Ubuntu 16.04 전체 환경이 아니라 비교 이미지의 Rocky 시스템 라이브러리 위에서 실행했습니다.
- 아래 성능 결과는 기준값 없는 서술적 측정입니다.

### 성능

`performance` case로 같은 컴퓨터에서 구·신을 측정했습니다.

- 4개 producer가 각각 1 KiB 메시지 4096개를 256개씩 묶어 보냅니다.
- 3번 반복한 값의 중앙값입니다.
- 구·신은 서로 다른 시스템 라이브러리와 컴파일러로 만들어져, 차이의 원인을 나누지 않았습니다.

| 지표 | 구버전 | 신버전 |
| --- | --- | --- |
| ACK 처리량 (msg/s) | 1,414,109 | 1,297,960 |
| ACK payload (MiB/s) | 1,381 | 1,268 |
| 파일 기록 완료 (MiB/s) | 957 | 895 |
| batch 지연 p95 (ms) | 1.24 | 1.21 |
| daemon CPU 시간 (s) | 0.04 | 0.04 |
| 최대 메모리 사용량 (MiB) | 23.5 | 21.1 |

신버전의 ACK 처리량은 구버전의 0.92배입니다.
처리량은 약 8% 이내, 지연은 같은 수준, 메모리는 조금 적었습니다.
한 번의 서술적 측정이며 벤치마크 결과로 주장하는 것은 아닙니다.

ACK는 `OK` 응답 기준이고, 파일 기록 완료는 저장 파일에 모두 쓰일 때까지를 기준으로 합니다.

### Docker 이미지

Windows의 CRLF checkout으로도 이미지를 빌드했습니다.
이미지는 272 MB였고, 기본 설정으로 다음을 확인했습니다.

- `Log` 응답 `OK`
- 저장된 bytes `hello docker\n\n`
- fb303 `getStatus` `ALIVE`
- fb303 `shutdown` 뒤 종료 코드 0

### 실행하지 않은 것

- HDFS lane
- Rocky 9 RPM
- GCC 14·15에서의 최근 현대화 단계
- 반복 실행으로 보는 불안정성(flake) 통계

### 관련 문서

| 문서 | 내용 |
| --- | --- |
| [최종 재검증 기록](docs/verification.md#최종-재검증-2026-10-07) | 이 절의 수치와 실행 순서 |
| [실제 구·신 비교](docs/verification.md#구신-daemon-비교) | case별 입력·기대값과 시험 방법 |
| [구버전 비교 환경](tools/old-lane/README.md) | 구버전 재현 빌드와 비교를 다시 돌리는 명령 |
| [호환성 정책](docs/compatibility-policy.md) | 원본 동작을 지키기로 한 결정, 남은 버그, 일반 spool의 손실 경로 |
| [빌드 안내](docs/build.md) | 의존성 경로, 빌드·임시 설치, 검증 준비, fb303 patch, Rocky 빌드·RPM, Python client |
| [Docker 안내](docs/docker.md) | 이미지 빌드·실행·정지 |
| [HDFS 안내](docs/hdfs.md) | 선택 기능의 빌드·실행 범위, Rocky HDFS |
| [설계](docs/design.md) | 원본 구조와 개발 방향 |
| [문서 안내](docs/README.md) | docs 폴더의 문서 목록 |
| [개발 지침](AGENTS.md) | 코드를 바꾸고 검증할 때의 규칙 |

## 라이선스

[Apache License 2.0](LICENSE)을 따르며, 원본 Facebook Scribe의 저작권과 고지를 보존합니다.

재배포할 때는 LICENSE, 변경한 파일의 수정 고지, 필요한 원본 고지를 포함해야 합니다.
Docker 실행 이미지에는 Scribe LICENSE와 함께 Thrift의 LICENSE/NOTICE, fb303의 LICENSE를 `/usr/share/licenses/scribe-next/`에 넣었습니다.
다른 방식으로 의존성 라이브러리를 함께 배포한다면 각 라이브러리의 LICENSE/NOTICE를 따로 확인하세요.
빌드·임시 설치 검사가 완성된 배포 패키지나 의존성 고지 목록을 대신하지는 않습니다.

[^dropin]: drop-in 대체: 기존 프로그램을 빼고 그 자리에 넣어도, 주변 설정이나 다른 프로그램을 고치지 않고 그대로 동작하는 것입니다.
[^thrift]: Thrift: 서버와 클라이언트가 주고받는 데이터 형식을 정의하고, 여러 언어용 통신 코드를 만들어 주는 라이브러리입니다.
  Scribe는 로그를 Thrift로 주고받으며, 구·신이 통신하려면 형식이 같아야 합니다.
[^framed]: framed binary: 요청마다 앞에 4-byte 길이를 붙이고(framed), 내용은 Thrift의 이진 형식(binary)으로 보내는 방식입니다.
  양쪽이 같은 방식을 써야 통신됩니다.
[^spool]: spool: 다음 서버로 보내지 못한 로그를 잠시 디스크에 모아 두는 파일입니다.
  buffer store의 secondary가 이 역할을 하며, 상대가 살아나면 다시 보냅니다.
[^fb303]: fb303: Facebook이 만든 서버 상태 조회 규약입니다.
  상태(`ALIVE`, `WARNING` 등), 상세 설명, 카운터를 원격으로 읽고, `reinitialize`(설정 다시 읽기)·`shutdown`(정상 종료) 명령을 보냅니다.
[^hdfs]: HDFS: Hadoop의 분산 파일 시스템입니다.
  Scribe는 선택 기능으로 로그를 HDFS에 직접 쓸 수 있습니다(`fs_type=hdfs`).
[^rpc]: RPC 라이브러리: Scribe의 통신 함수(`Log` 등)를 다른 프로그램이 쓸 수 있게 묶은 라이브러리입니다.
  기본은 정적 라이브러리이며, 선택하면 공유 라이브러리로도 빌드합니다.
[^libevent]: libevent: 많은 네트워크 연결을 적은 thread로 처리하도록 돕는 C 라이브러리입니다.
  Thrift의 서버가 사용합니다.
[^boost]: Boost: C++에서 널리 쓰는 공개 라이브러리 모음입니다.
  `scribed`는 Boost를 쓰지 않지만, Thrift의 header가 Boost header를 불러옵니다.
[^docker]: Docker: 프로그램과 필요한 라이브러리를 한 묶음(이미지)으로 만들어, 격리된 환경(컨테이너)에서 실행하는 도구입니다.
[^category]: category: 로그의 종류를 나타내는 이름입니다(예: `game_login`).
  Scribe는 category를 보고 어느 store로 보낼지 정합니다.
[^symlink]: symlink(심볼릭 링크): 다른 파일을 가리키는 바로가기 파일입니다.
  Scribe는 `<이름>_current` symlink로 지금 쓰는 파일을 가리킵니다.
[^store]: store: 설정 파일의 `<store>` 블록으로 정하는 로그 처리 단위입니다.
  파일에 쓰기(`file`), 다른 서버로 보내기(`network`), 실패하면 모았다가 다시 보내기(`buffer`) 등 10가지 종류가 있습니다.
[^mib]: MiB: 1 MiB는 1,048,576 bytes(2의 20제곱)입니다.
  256 MiB는 268,435,456 bytes입니다.
[^lf]: LF(Line Feed): 줄바꿈 문자 `\n`이며, byte 값은 `0x0a`입니다.
[^trylater]: TRY_LATER: `Log` 요청의 결과 값 중 하나로, "지금은 받을 수 없으니 나중에 다시 보내라"는 뜻입니다.
  이 요청의 메시지는 하나도 받지 않았으므로 클라이언트가 다시 보내야 합니다.
[^cpp17]: C++17: 2017년에 정해진 C++ 언어 표준입니다.
  컴파일러에 이 판을 지정하면, 그 판의 문법과 표준 라이브러리로 빌드합니다.
[^smartptr]: 스마트 포인터: 메모리를 다 쓰면 자동으로 돌려주는 C++ 도구입니다.
  손으로 돌려주다 빠뜨려 메모리가 새는 일을 막습니다.
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
[^little]: little-endian: 여러 byte로 된 숫자를 작은 자리부터 저장하는 방식입니다.
  길이 9는 `09 00 00 00`으로 저장됩니다.
[^raii]: RAII: 자원(잠금, 메모리 등)을 만들 때 얻고, 범위를 벗어나면 자동으로 돌려주는 C++ 방식입니다.
  중간에 예외가 나도 자원이 풀립니다.
[^fsync]: fsync: 운영체제 메모리에 있는 파일 내용을 디스크에 실제로 기록하도록 강제하는 호출입니다.
  `flush`는 프로그램의 버퍼를 운영체제로 넘길 뿐이라, 전원이 꺼지면 내용이 사라질 수 있습니다.
[^autotools]: autotools: `configure` 스크립트와 `Makefile`을 만들어 주는 전통적인 빌드 도구 묶음(autoconf, automake, libtool)입니다.
