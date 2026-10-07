# scribe-next

**Facebook Scribe 로그 서버를 최신 Linux와 C++17[^1]에서 다시 빌드한 drop-in[^2] 대체판입니다.**

실행 파일 이름(`scribed`), 설정 파일 형식, Thrift[^3] 통신, 저장 파일 형식을 원본과 똑같이 유지합니다.
기존 서버의 실행 파일만 바꿔 끼우고 설정·클라이언트·로그를 읽는 프로그램은 그대로 두는 것이 목표입니다.

> [!NOTE]
> 원본과 새 서버를 섞어 쓰는 전송과 파일 읽기를 **대표적인 조건에서** 비교했습니다.
> 모든 설정과 장애 상황에서 완전히 같거나 운영 환경에서 충분히 검증됐다는 뜻은 아닙니다.
> 지원 범위와 남아 있는 원본 버그는 아래에서 설명합니다.

## 목차

- [소개](#소개)
- [유지하는 기능](#유지하는-기능)
- [지원 환경](#지원-환경)
- [빠른 시작](#빠른-시작)
  - [0. 미리 알아둘 것](#0-미리-알아둘-것)
  - [1. 배포판 패키지](#1-배포판-패키지)
  - [2. Thrift 0.25.0 빌드와 설치 (공통)](#2-thrift-0250-빌드와-설치-공통)
  - [3. 저장소 받기와 fb303 빌드·설치 (공통)](#3-저장소-받기와-fb303-빌드설치-공통)
  - [4. scribe-next 빌드와 설치 (공통, 원본과 같은 순서)](#4-scribe-next-빌드와-설치-공통-원본과-같은-순서)
  - [5. 설치 확인](#5-설치-확인)
  - [6. 설정 파일 만들기](#6-설정-파일-만들기)
  - [7. 실행](#7-실행)
  - [Docker로 실행](#docker로-실행)
- [기존 설정과 클라이언트 사용](#기존-설정과-클라이언트-사용)
- [바뀐 점](#바뀐-점)
  - [빌드와 의존성](#빌드와-의존성)
  - [새 설정 키](#새-설정-키)
  - [고친 문제](#고친-문제)
    - [동적 목적지 변경과 연결 pool](#동적-목적지-변경과-연결-pool)
    - [service_list 재연결](#service_list-재연결)
    - [buffer 재전송 일부 성공](#buffer-재전송-일부-성공)
  - [C++17 정리 (동작 불변)](#c17-정리-동작-불변)
  - [검증 도구](#검증-도구)
- [일부러 남겨 둔 버그](#일부러-남겨-둔-버그)
- [알아둘 점](#알아둘-점)
- [업데이트와 되돌리기](#업데이트와-되돌리기)
- [관련 문서](#관련-문서)
- [라이선스](#라이선스)
- [각주](#각주)

## 소개

scribe-next는 2007~2008년에 작성된 [공개 Facebook Scribe 원본](https://github.com/facebookarchive/scribe/tree/fcd294faffd1e88af1643a3a8c2359c41713f7c2)을 옮긴 프로젝트입니다.
현대 Linux, 현대 컴파일러와 Thrift 0.25에서 빌드하고 실행할 수 있도록 옮겼습니다.
새로 설계한 로그 서버가 아니라 **원본 구조를 그대로 두고 빌드와 실행에 필요한 부분만 고친 이식판**입니다.

이 문서에서 **구버전**은 공개 원본(`fcd294f`)을 당시 Thrift/fb303 0.9.0으로 빌드한 서버를 말합니다.
**신버전**은 이 저장소에서 빌드한 서버를 말합니다.

| 원본과 같은 것 | 내용 |
| --- | --- |
| 실행 파일 | 이름 `scribed`, 옵션 `-c 설정파일`, `-p 포트` |
| 설정 파일 | `<store>` 블록과 `key=value` 형식, 설정 이름·기본값·상속 규칙 |
| 통신 | 원본 IDL[^4] 두 개, framed binary[^5] 통신, fb303[^6] 상태 조회 API |
| 저장 | 파일 이름, 회전 규칙, `_current` 표시, 임시 보관 파일(spool[^7])의 형식 |

원본 IDL 두 개는 `if/scribe.thrift`와 `if/bucketupdater.thrift`입니다.

### "그대로 바꿔 끼우기"의 뜻

기존 서버의 실행 파일만 신버전으로 바꾸고 나머지는 손대지 않은 채 운영을 이어 갈 수 있다는 뜻입니다.
구체적으로 다음 네 가지를 지키는 것이 목표입니다.

1. 기존 설정 파일을 고치지 않고 그대로 읽습니다.
2. 기존 클라이언트를 업그레이드하지 않아도 로그를 그대로 보낼 수 있습니다.
3. 구버전 → 신버전, 신버전 → 구버전 어느 방향으로도 로그를 넘길 수 있어 여러 대를 한 대씩 바꿀 수 있습니다.
4. 같은 입력이면 같은 이름의 파일에 같은 바이트로 저장되고, fb303 상태와 카운터 이름도 같습니다.

4번을 지키기 위해 원본 버그 중 **로그 결과에 영향을 주는 것은 고치지 않고 [일부러 남겨 두었습니다](#일부러-남겨-둔-버그).**
여기서 로그 결과는 어느 파일에 무엇이 저장되고 어디로 전달되는가를 말합니다.
반대로 프로그램이 비정상 종료하거나 잘못된 메모리를 읽는 문제는 [안전하게 고쳤습니다](#고친-문제).

### OK 응답의 뜻

서버가 돌려주는 `OK`는 **로그를 메모리 큐에 받았다**는 뜻입니다.
디스크 저장이 끝났다거나 다음 서버에 전달됐다는 보장(durable ACK)이 아니며, 중복 없는 전달도 보장하지 않습니다.
파일 `flush`도 `fsync`[^8]와 다릅니다.
신버전도 이 의미를 바꾸지 않았습니다.

## 유지하는 기능

- 기존 Thrift IDL, 요청·응답 형식과 fb303 상태 조회 API
- category[^9]별 로그 분배, 파일 저장, 다른 Scribe 서버로의 전송
- spool에 임시 보관한 로그의 재전송, 파일 회전과 다시 열기
- 저장 방식(store[^10])
  - `file`, `buffer`, `network`, `bucket`, `null`
  - `multi`, `category`, `thriftfile`, `multifile`, `thriftmultifile`
- 기존 설정 이름, 파일 이름, 줄바꿈 처리와 `_current` 파일 표시(symlink[^11])

## 지원 환경

실제로 빌드와 실행을 확인한 환경입니다.

| 항목 | 확인한 환경 |
| --- | --- |
| 운영체제 | Linux x86_64: Debian 13, Ubuntu 26.04.1, Rocky 8.10 / 9.8 |
| C++ | C++17, GCC 8.5 / 11.5 / 13 / 14.2 / 15.2(13은 설치 확인만) |
| 통신 라이브러리 | Thrift compiler와 C++ runtime 0.25.0, 이에 맞춰 준비한 fb303 |
| 기타 빌드 도구 | Boost[^12] header 1.83 / 1.75(Thrift 빌드용), libevent[^13], pthread, make, autotools[^14], Git |
| Python 설치 검사 | Python 3.12 / 3.14, setuptools와 해당 Thrift/fb303 Python runtime |
| 선택 기능 | 공유 RPC[^15] 라이브러리, Hadoop 3.5/libhdfs와 JDK 17을 사용하는 HDFS[^16] |
| 설치 순서 | 2026-10-07 `ubuntu:24.04`·`rockylinux:9` 컨테이너에서 `scribed --help`까지 |

Rocky 8.10 / 9.8은 기본 빌드와 임시 설치를 확인했습니다.
scribed는 Boost 라이브러리를 쓰지 않습니다. Boost header는 Thrift 0.25.0을 빌드하고 그 header를 include할 때만 필요합니다.
autotools는 autoconf, automake, libtool을 말합니다.

[빠른 시작](#빠른-시작)의 설치 순서는 2026-10-07에 깨끗한 `ubuntu:24.04`와 `rockylinux:9` 컨테이너에서 실행했습니다.
이때 Ubuntu는 GCC 13과 배포판 Boost header 1.83(`libboost-dev`), Rocky 9는 GCC 11.5와 배포판 Boost 1.75(`boost-devel`)를 썼습니다.
`sudo make install`, `scribed --help`, `ldd`에 Boost 라이브러리가 없음까지 확인했으며 시험 묶음은 실행하지 않았습니다.

Rocky의 기본 비-HDFS/static 검증은 각 218개 시험과 임시 설치까지 확인했습니다.
[Rocky 빌드 안내](docs/rocky-build.md)의 별도 준비 조건을 따르세요.
Rocky의 daemon 전용 [개발 RPM](docs/rocky-rpm.md)은 격리 설치·송수신·정상 종료·동일 RPM 재설치·제거까지 확인했습니다.
Rocky shared RPC는 source 빌드·218개 회귀·임시 설치 loader까지 확인했습니다.

2026-10-07 Rocky 9.8(WSL, 격리 컨테이너 아님)에서 `tools/validate_linux.py`로 시험 묶음을 실행했습니다.
이 작업 전에는 220개, 이 작업의 첫 PR(#48) 뒤에는 224개, 이어서 병합한 PR(#40–#49) 뒤 현재 `main`에서는 236개가 통과했습니다.
세 번 모두 실패·오류·skip은 0이었습니다.
220개에서 늘어난 4개는 `game-profile` 비교 case의 offline 시험입니다.

Rocky [HDFS 소스 검증](docs/rocky-hdfs.md)은 각 220개 회귀·local JNI와 격리 single-DataNode 저장·독립 reader·재시작 append까지 확인했습니다.
HDFS/shared RPM, 서로 다른 RPM 버전 간 upgrade와 운영 배포는 아직 검증하지 않았습니다.
HDFS는 하나의 DataNode로 구성한 테스트에서 파일 쓰기·다시 열어 추가 쓰기와 Hadoop client로 저장 내용을 읽는 것을 확인했습니다.
과거 libhdfs와의 완전한 동등성이나 권한·복제·여러 DataNode의 장애 처리는 확인하지 않았습니다.

Mac과 Windows를 Scribe 서버의 지원 환경으로 확인한 것은 아닙니다.
다른 compiler·의존성 조합과 상세 성능 비교도 별도 확인이 필요합니다.
랜덤 재시도·서버 후보 shuffle 순서는 GNU 구현을 기준으로 확인했습니다.
다른 C++ 표준 라이브러리에서 같은 순서를 보장한 것은 아닙니다.

## 빠른 시작

처음 보는 사람이 `git clone`부터 `scribed` 실행까지 명령을 복사해 따라 할 수 있도록 정리한 순서입니다.
원본 Scribe와 같은 `bootstrap.sh` → `make` → `make install` 흐름을 따릅니다.
Docker 이미지로 실행하려면 [Docker로 실행](#docker로-실행)으로 바로 가도 됩니다.

아래 명령은 2026-10-07에 깨끗한 `ubuntu:24.04`와 `rockylinux:9` 컨테이너에서 `scribed --help`와 `ldd`까지 실행해 확인했습니다.
그 컨테이너에서 전체 시험은 실행하지 않았습니다([검증 도구](#검증-도구) 참고).

### 0. 미리 알아둘 것

- Thrift 0.25.0은 두 배포판 모두 배포판 패키지 없이 소스에서 빌드합니다.
  - Thrift는 `thrift` compiler와 `scribed`가 링크하는 C++ runtime을 제공합니다.
- fb303은 같은 Thrift 소스의 `contrib/fb303`을 쓰며, 이 프로젝트의 patch를 `tools/prepare_fb303.py`로 적용한 뒤 빌드합니다.
  - 이 patch는 카운터 잠금을 예외에 안전하게 만듭니다([fb303 카운터 잠금](docs/fb303-counter-safety.md)).
- 모든 것을 `/usr/local` 아래에 설치합니다.
  - 원본 Scribe도 `/usr/local`을 기본값으로 가정했으므로, 아래 `--with-*path` 옵션은 이를 명시할 뿐입니다.
- 저장소는 비공개이므로 clone하려면 GitHub 로그인이 필요합니다.
  - `gh auth login`으로 로그인하거나, SSH key를 등록한 뒤 `git clone git@github.com:dbwk10317/scribe-next.git`을 씁니다.

> [!IMPORTANT]
> **Thrift compiler와 C++ runtime은 같은 버전을 사용하세요.**
> fb303도 해당 compiler로 생성하고 빌드한 것을 사용해야 합니다.
> 아래 순서는 세 가지를 모두 같은 Thrift 0.25.0 소스에서 만들므로 이 조건을 지킵니다.

### 1. 배포판 패키지

빌드 도구, libevent, Thrift 빌드에 필요한 Boost header, 그리고 준비 스크립트와 Python client 설치에 쓰는 Python을 설치합니다.
사용하는 배포판의 블록 하나만 실행하세요.

#### Ubuntu 24.04

```sh
sudo apt-get update
sudo apt-get install -y git build-essential autoconf automake libtool pkg-config cmake bison flex \
  libevent-dev libboost-dev python3 python3-setuptools
```

#### Rocky Linux 9

```sh
sudo dnf -y install git gcc gcc-c++ make cmake autoconf automake libtool bison flex \
  libevent-devel boost-devel python3 python3-setuptools
echo /usr/local/lib | sudo tee /etc/ld.so.conf.d/scribe-local.conf
```

Rocky에는 Boost header만 담은 패키지가 없어 `boost-devel`을 설치합니다. 함께 설치되는 Boost 라이브러리는 scribed가 링크하지 않습니다.
마지막 줄은 공유 라이브러리 검색 경로에 `/usr/local/lib`을 추가합니다.
Ubuntu는 기본으로 `/usr/local/lib`을 찾지만 Rocky는 찾지 않기 때문입니다.
Rocky 8은 더 새로운 bison이 필요하며, 준비 방법은 [Rocky 빌드 안내](docs/rocky-build.md)에 있습니다.

### 2. Thrift 0.25.0 빌드와 설치 (공통)

Apache 배포 서버에서 Thrift 0.25.0 소스를 받아 checksum을 확인합니다.
그다음 다른 언어 지원은 끄고 compiler와 C++ 라이브러리(libevent 지원 포함)만 빌드해 `/usr/local`에 설치합니다.

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

### 3. 저장소 받기와 fb303 빌드·설치 (공통)

scribe-next 저장소를 받고, Thrift 소스에 들어 있는 fb303에 이 프로젝트의 patch를 적용해 `fb303-build` 폴더를 만듭니다.
그 폴더에서 autotools로 configure를 만들고 빌드한 뒤 `/usr/local`에 설치합니다.

```sh
cd ~/scribe-build
git clone https://github.com/dbwk10317/scribe-next.git
python3 scribe-next/tools/prepare_fb303.py --source thrift-0.25.0/contrib/fb303 --output fb303-build
cd fb303-build
aclocal -I ./aclocal && automake -a --copy && autoconf
./configure --prefix=/usr/local --with-thriftpath=/usr/local --with-boost=/usr \
  --without-java --without-php --without-python
make -j"$(nproc)" CXXFLAGS='-O2 -std=c++17' CPPFLAGS='-I/usr/local/include'
sudo make install
sudo mkdir -p /usr/local/share/scribe-next
sudo cp scribe-next-fb303-safety.json /usr/local/share/scribe-next/fb303-safety.json
```

마지막 두 줄은 patch 적용 기록(`fb303-safety.json`)을 설치하며, 검증기 `tools/validate_linux.py`가 이 파일을 찾습니다.

### 4. scribe-next 빌드와 설치 (공통, 원본과 같은 순서)

`bootstrap.sh`는 원본처럼 autoreconf와 configure를 차례로 실행하며, 넘긴 옵션은 configure에 그대로 전달됩니다.
그다음 `make`와 `make install`로 빌드하고 설치합니다.

```sh
cd ~/scribe-build/scribe-next
./bootstrap.sh --prefix=/usr/local --with-thriftpath=/usr/local --with-fb303path=/usr/local
make -j"$(nproc)"
sudo make install
```

`make install`은 `scribed`를 `/usr/local/bin`에, 정적 RPC 라이브러리를 `/usr/local/lib`에 설치합니다.
Python client package `scribe`도 시스템 Python(`PY_PREFIX`, 기본값 `/usr`)에 설치됩니다.
configure는 명시적으로 지정한 `PYTHON`을 보존하며, 지정하지 않으면 `python3`, `python` 순서로 찾습니다.

Python client를 쓰려면 같은 버전의 Thrift Python package(`python3 -m pip install thrift==0.25.0`)도 필요합니다.
daemon을 실행하는 데는 Python client가 필요하지 않습니다.
기존 client 환경과 겹칠 때의 주의점은 [기존 설정과 클라이언트 사용](#기존-설정과-클라이언트-사용)을 참고하세요.

공유 라이브러리 경로와 HDFS 빌드 설정은 [빌드 안내](docs/linux-build-mvp.md)와 [HDFS 안내](docs/hdfs-compatibility.md)를 참고하세요.

### 5. 설치 확인

설치한 `scribed`가 PATH에서 실행되는지, 그리고 `/usr/local/lib`의 Thrift 라이브러리를 찾는지 확인합니다.

```sh
scribed --help
ldd "$(command -v scribed)"
```

`scribed --help`는 사용법 줄 `Usage: scribed [-p port] [-c config_file]`을 출력해야 합니다.
`ldd` 결과에는 `/usr/local/lib`의 `libthrift.so.0.25.0`, `libthriftnb.so.0.25.0`과 배포판의 libevent가 보여야 하며, Boost 라이브러리(`libboost_*`)는 보이지 않아야 합니다.
기본 빌드는 모든 의존성을 실행 파일에 넣는 완전 정적 빌드가 아니므로, 실행할 때도 이 라이브러리들을 찾을 수 있어야 합니다.

### 6. 설정 파일 만들기

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
이 예제에서 지정하지 않은 category는 원본 규칙에 따라 버려지고 fb303 카운터 `received bad`가 늘어납니다.

### 7. 실행

```sh
scribed -c "$SCRIBE_CONFIG"
```

`scribed`는 실행한 터미널에 연결된 상태로 동작합니다.
예제는 포트를 localhost에만 제한하지 않습니다.
실행 환경의 접근 범위를 확인한 뒤 기동하세요.
서비스 등록이나 자동 배포는 제공하지 않습니다.

설정의 `port`가 명령행 `-p`보다 우선합니다.
긴 옵션 대신 `-c`와 `-p` 형태를 사용하세요.

프로세스가 시작됐다는 것만으로 로그 저장이 정상이라고 판단하지 마세요.
fb303 상태·상세 설명·수신 카운터와 실제 저장 파일을 함께 확인해야 합니다([시작에 실패해도 종료 코드는 0](#시작에-실패해도-종료-코드는-0이다)).

### Docker로 실행

1~4단계를 직접 하지 않고 Docker 이미지로 `scribed`를 실행할 수도 있습니다.
저장소의 [`Dockerfile`](Dockerfile)과 기본 설정 [`examples/docker.conf`](examples/docker.conf)를 씁니다.
자세한 내용은 [Docker 안내](docs/docker.md)에 있습니다.
아래 내용은 2026-10-07에 WSL의 Docker 29.8에서 확인했습니다.

#### 이미지 빌드

저장소 checkout의 최상위 폴더에서 이미지를 빌드합니다.
저장소가 비공개이므로 Dockerfile은 저장소를 clone하지 않고, 지금 checkout을 빌드 재료(build context)로 씁니다.

```sh
docker build -t scribe-next:local .
```

이미지는 `rockylinux:9` 위의 두 단계(stage)로 만들어집니다.
빌드 단계는 위 1~4단계와 같은 순서를 실행합니다.

- SHA256을 확인한 archive로 Thrift 0.25.0 빌드
- 이 프로젝트의 patch를 적용한 fb303 빌드
- `bootstrap.sh` → `make` → `make install`

빌드 단계는 CRLF 줄 끝을 변환하므로 Windows checkout도 빌드 재료로 쓸 수 있습니다.
실행 단계에는 `scribed`, `libthrift.so.0.25.0`, `libthriftnb.so.0.25.0`, 배포판 libevent 패키지와 LICENSE/NOTICE 파일만 남깁니다.
빌드 단계의 `boost-devel`은 Thrift 빌드용 header이며 실행 단계에는 Boost가 없습니다.

Thrift archive를 받으므로 빌드할 때 네트워크가 필요합니다.
확인한 환경(20 core)에서 빌드는 약 1.5분 걸렸고, 이미지 크기는 272 MB(기반 이미지 264 MB)였습니다.

#### 컨테이너 실행과 기본 설정

로그를 저장할 폴더를 만들고, 그 폴더를 컨테이너의 `/var/log/scribed`에 연결해 실행합니다.
컨테이너는 root가 아닌 시스템 사용자 `scribe`(확인한 이미지에서 uid 999)로 실행되므로, 연결한 폴더에 그 uid가 쓸 수 있어야 합니다.
아래 `chmod 0777`은 이를 위한 것입니다.

```sh
mkdir -p scribe-logs && chmod 0777 scribe-logs
docker run -d --name scribe -p 1463:1463 \
  -v "$PWD/scribe-logs:/var/log/scribed" \
  scribe-next:local
```

컨테이너가 만든 파일은 host에서도 그 uid의 소유로 보입니다.
기본 설정 [`examples/docker.conf`](examples/docker.conf)의 내용은 다음과 같습니다.

- `port=1463`
- `category=default` 모델 하나와 `type=file` store 하나([모델과 복사본](#default-categories-prefix-설정은-모델이고-실제-store는-복사본이다) 참고)
- 저장 위치는 `/var/log/scribed/<category>/<category>-YYYY-MM-DD_00000`
- `add_newlines=1`, `rotate_period=daily`, `max_size=1073741824`
- `create_symlink=yes`이므로 `<category>_current`도 생깁니다.

날짜는 컨테이너 시계(기본 UTC)를 따릅니다.
직접 만든 설정을 쓰려면 아래처럼 `/etc/scribe/scribe.conf` 위에 읽기 전용으로 연결합니다.

```sh
docker run -d --name scribe -p 1463:1463 \
  -v "$PWD/scribe-logs:/var/log/scribed" \
  -v "$PWD/my-scribe.conf:/etc/scribe/scribe.conf:ro" \
  scribe-next:local
```

설정의 `port`를 바꾸면 `docker run`의 `-p` 포트 연결도 같이 바꾸세요.
원본과 마찬가지로 설정의 `port`가 `scribed`의 명령행 `-p`보다 우선하므로, 컨테이너 안에서 받는 포트는 설정의 값입니다([port 우선순위](#설정-파일의-port가--p보다-우선한다)).

#### 동작 확인

먼저 컨테이너 로그에서 시작 메시지와 상태를 확인합니다.

```sh
docker logs scribe
```

`Starting scribe server on port 1463`과 `STATUS: ALIVE`가 보여야 합니다.
프로세스가 떴다는 것만으로 저장이 정상이라고 판단하지 말고, 시험 메시지를 보내 실제 파일을 확인하세요.
시험 메시지를 보내는 Python 예제는 [Docker 안내](docs/docker.md)에 있습니다.

확인할 때 category `demo`로 메시지 `hello docker\n`을 보내면 `OK`가 돌아왔습니다.
그리고 `scribe-logs/demo/demo-<날짜>_00000`에 정확히 `hello docker\n\n`이 저장됐습니다.
메시지에 든 줄바꿈 하나에 `add_newlines=1`이 하나를 더 붙이기 때문입니다.
`demo_current`가 이 파일을 가리켰고, fb303 `getStatus`는 `ALIVE`였습니다.

#### 컨테이너 정지

`docker stop`은 유예 시간을 기다린 뒤 SIGKILL로 종료합니다.
`scribed`에는 SIGTERM 처리기가 없고 컨테이너에서 PID 1로 실행되기 때문이며, 원본과 같은 동작입니다.
그 순간 메모리 큐에 남아 있던 메시지는 잃습니다.

깔끔하게 멈추려면 fb303의 oneway `shutdown`을 보내세요(종료 코드 0).
보내는 방법은 [Docker 안내](docs/docker.md)에 있습니다.

#### Docker 이미지의 제한

- HDFS를 지원하지 않습니다.
- RPC 라이브러리는 정적 라이브러리로 빌드합니다(공유 RPC 아님).
- `rockylinux:9` tag를 digest로 고정하지 않았습니다.
- 보안 강화 안내가 아닙니다.
  - TLS나 인증이 없으며, 포트에 닿을 수 있는 모든 client의 요청을 받습니다.

## 기존 설정과 클라이언트 사용

기존 `<store>` 설정을 출발점으로 쓸 수 있습니다.
[원본 설정 예제](examples/example1.conf)의 파일·임시 보관 경로와 포트를 본인 환경에 맞게 바꾸세요.
기존 보조 스크립트에 들어 있는 공유 `/tmp` 경로나 root 실행 가정을 그대로 따라갈 필요는 없습니다.

원본 [README](README)와 [examples 안내](examples/README)는 역사적 자료입니다.
없는 `example2.conf`·`README.BUILD` 안내 대신 실제 `example2client.conf`·`example2central.conf`와 현재 빌드 안내를 따르세요.
구 Python/PHP 스크립트의 현대 runtime 호환성을 보장하지 않습니다.

원본 시험 설정도 그대로 보존합니다.
`test/scribe.conf.bucketupdater.central`은 `<bucket3>`를 `</bucket2>`로 닫습니다.
`scribehtest`의 `lzo_compression`·`lzo_block_size`·`sync_interval`과 `simpletest`의 `send_buffer`는 현재 코드가 읽지 않습니다.
예제를 그대로 운영 설정으로 쓰지 마세요.

원본 IDL과 framed binary 통신을 유지하며 구 서버→새 서버와 새 서버→구 서버 전송을 비교했습니다.
원본 버그 때문에 로그의 분배·내용·형식·전달 결과가 달라지던 수정은 되돌렸습니다.
그 버그는 [일부러 남겨 둔 버그](#일부러-남겨-둔-버그)에, 설정상 주의점은 [알아둘 점](#알아둘-점)에 정리했습니다.

**기존 클라이언트를 함께 업그레이드하도록 요구하지 않습니다.**
다만 사용 중인 모든 언어·Thrift 버전 조합을 검증한 것은 아닙니다.

이 저장소에서 생성·설치하는 Python package는 Thrift 0.25용 Python3 client입니다.
원본 Python2 client나 구 Thrift Python runtime의 대체품으로 검증하지 않았습니다.
이름이 같은 `scribe` package를 기존 client 환경에 덮어 설치하지 말고, 별도 Python 가상환경이나 설치 경로에서 맞는 Thrift/fb303 runtime과 사용하세요.
`bucketupdater` Python package 설치와 구 Python/PHP 예제 전체의 현대화는 포함하지 않습니다.

## 바뀐 점

구버전과 비교해 달라진 점을 한눈에 정리하면 다음과 같습니다.
**어느 항목도 기존 설정을 고치도록 요구하지 않습니다.**

| 구분 | 무엇이 바뀌었나 | 로그의 분배·내용·파일 형식 |
| --- | --- | --- |
| [빌드와 의존성](#빌드와-의존성) | C++17, Thrift 0.25, 최신 GCC로 빌드, Boost 라이브러리 제거 | 같음 |
| [새 설정 키](#새-설정-키) | `thrift_max_frame_size`, `thrift_max_message_size` 추가 | 같음(큰 요청 제외) |
| [고친 문제](#고친-문제) | 비정상 종료·미정의 동작 6가지, 전송·연결 수정 3가지 | 정상 설정에서는 같음 |
| [C++17 정리](#c17-정리-동작-불변) | 잠금·소유권·전역 변수 의존·죽은 코드 정리 | 같음 |
| [max_msg_per_second 계산](#max_msg_per_second와-절반-예외) | 동시에 들어오는 요청도 잠금 아래에서 정확히 셈 | 같음(동시 요청 제외) |

새 설정 키 두 개의 기본값은 각각 256 MiB[^17]이며, 이 한도를 넘는 큰 요청만 처리가 다릅니다.
전송·연결 수정 3가지는 pooled 동적 목적지 변경, `service_list` 재연결, 재전송 일부 성공입니다.
이 세 가지도 분배·내용·파일 형식은 같고, 일시 실패·메모리 증가·손실이 줄어듭니다.
`max_msg_per_second`는 한도 근처의 동시 요청에서만 수락 개수가 다를 수 있습니다.

### 빌드와 의존성

신버전을 빌드하려면 다음이 필요합니다.
구버전 비교에는 공개 원본을 Thrift/fb303 0.9.0으로 빌드한 서버를 사용했습니다.

| 항목 | 신버전 요구 사항 | 비고 |
| --- | --- | --- |
| 언어 표준 | C++17 | `src/Makefile.am`이 `-std=c++17 -Wall`을 직접 선언 |
| Thrift | compiler와 C++ runtime 모두 0.25.0 | 두 버전이 다르면 생성 코드와 runtime이 맞지 않음 |
| fb303 | Thrift 0.25.0 compiler로 생성·빌드한 것 | 상태 조회 API는 원본과 같음 |
| Boost | scribed는 쓰지 않음. Thrift 0.25.0 빌드와 그 header에 Boost header(Thrift 요구 1.56 이상)만 필요 | 확인: 1.83(소스 빌드), 1.83(Ubuntu 24.04 `libboost-dev`), 1.75(Rocky 9 `boost-devel`) |
| 기타 | libevent, pthread | 원본과 같음 |
| 컴파일러 | GCC 8.5 / 11.5 / 13(Ubuntu 24.04) / 14.2 / 15.2에서 확인 | GCC 8은 configure가 `-lstdc++fs`를 붙임. GCC 13은 `scribed --help`·`ldd`까지만, 다른 조합은 미확인 |
| 빌드 방식 | autotools(`configure` + `make`) | CMake 등으로 바꾸지 않음 |

scribed 소스는 Boost를 쓰지 않으며 Boost 라이브러리를 링크하지 않습니다.
다만 Thrift 0.25.0의 C++ 라이브러리는 빌드할 때 Boost header를 요구하고, 설치된 Thrift·fb303 header도 Boost header를 include합니다.
그래서 빌드할 때는 Boost header가 필요하고, 실행할 때는 Boost가 필요하지 않습니다.
Boost header가 기본 include 경로(`/usr/include` 등)에 없으면 `CPPFLAGS=-I<Boost 위치>/include`로 알려 줍니다.
configure의 `--with-boost`, `--with-boost-system`, `--with-boost-filesystem` 옵션은 없어졌습니다.
예전 명령줄에 남아 있으면 configure가 `unrecognized options` 경고만 출력하고 계속합니다.
GCC 8은 `std::filesystem`을 별도 라이브러리 `libstdc++fs`에 두므로, configure가 작은 프로그램을 링크해 보고 필요할 때만 `-lstdc++fs`를 붙입니다(GCC 9 이상은 필요 없음).
시험 묶음은 원본(C++03) 비교 기준을 빌드하려고 `TOOLS_PREFIX`의 Boost filesystem 라이브러리를 계속 사용합니다.
표의 Boost 1.83과 1.75는 확인에 쓴 버전입니다.
Ubuntu 24.04의 GCC 13·Boost 1.83과 Rocky 9의 Boost 1.75는 두 컨테이너에서 `scribed --help`와 `ldd`까지만 확인했습니다.

#### 왜 Boost를 제거했나

scribed가 Boost에서 쓰던 기능은 공유 포인터(`shared_ptr`·`weak_ptr`), 파일 크기·목록·삭제·디렉터리 만들기 같은 파일 시스템 함수 몇 개, 서버 목록 문자열을 나누는 함수 하나뿐이었습니다.
C++17 표준 라이브러리가 이것을 모두 제공합니다(`std::shared_ptr`, `std::filesystem`, 그리고 몇 줄짜리 분리 함수).
그래서 scribed를 설치하거나 배포할 때 함께 설치·동봉해야 하는 Boost 라이브러리가 없어졌습니다.
설정 키는 바뀌지 않았고 로그의 분배·내용·파일 형식과 카운터도 같습니다.
서버 목록 분리 결과는 원본 빌드가 쓰던 Boost 1.58과 Boost 1.83의 `boost::split`과 비교해, 탭·공백·콜론·NUL을 포함한 7개 문자로 만든 길이 7 이하의 모든 문자열에서 같았습니다.
파일 함수의 오류는 예전처럼 잡아서 같은 값을 돌려주며, 진단 로그에 찍히는 예외 문구만 표준 라이브러리의 표현으로 바뀝니다.

예전에는 `-std=c++17`이 검증기(`tools/validate_linux.py`)나 RPM spec이 `CXXFLAGS`로 넣어 줄 때만 적용됐습니다.
그래서 직접 `./configure && make`를 하면 컴파일러 기본 표준(예: GCC 8은 gnu++14)으로 빌드될 수 있었습니다.
이제 빌드 파일이 표준을 직접 선언합니다.

```make
# src/Makefile.am
AM_CXXFLAGS = -std=c++17 -Wall
```

automake는 `AM_CXXFLAGS` **뒤에** 사용자 `CXXFLAGS`를 붙이므로 사용자가 명시한 값이 이깁니다.
예를 들어 `CXXFLAGS="-O2 -std=gnu++17"`을 주면 컴파일 명령은 아래 순서가 되고, 마지막 `-std=gnu++17`이 적용됩니다.
빈 `CXXFLAGS`를 준 경우도 그대로 보존됩니다.

```text
g++ ... -std=c++17 -Wall -O2 -std=gnu++17 -c store.cpp
```

빌드 방식의 변경은 실행 중 동작이나 설정 해석에 영향을 주지 않습니다.
generated code는 규칙으로 생성하며 손으로 고치지 않습니다.

### 새 설정 키

신버전에서 새로 생긴 설정 키는 아래 두 개뿐입니다.
쓰지 않아도 기본값으로 동작합니다.

#### 통신 크기 제한과 확인한 호환성

새 Thrift(0.25)는 기본 크기 제한이 원본 시절과 다릅니다(frame 16,384,000 / message 104,857,600 bytes).
그대로 두면 원본에서 받던 큰 요청을 거절하게 되므로, 이 프로젝트는 두 설정을 추가하고 server·relay·mapping에 같은 값을 적용합니다.
기본값은 각각 **256 MiB**입니다.

```conf
# 설정 파일의 최상위(어떤 <store> 블록에도 넣지 않는 위치)에 둡니다.
# 아래 두 줄은 기본값과 같습니다.
thrift_max_frame_size=268435456
thrift_max_message_size=268435456
```

| 키 | 기본값 | 허용 값 | 적용 대상 | 바꾸는 방법 |
| --- | --- | --- | --- | --- |
| `thrift_max_frame_size` | 268435456 (256 MiB) | 1부터 2147483647까지의 십진수 byte 수 | 서버 수신, network store의 relay 송신, dynamic bucket updater 조회 | 재시작 |
| `thrift_max_message_size` | 268435456 (256 MiB) | 1부터 2147483647까지의 십진수 byte 수 | 서버 수신, network store의 relay 송신, dynamic bucket updater 조회 | 재시작 |

- 기준은 직렬화된 RPC 내용의 크기이며, 바깥의 4-byte frame 길이 표시는 제외합니다.
- 두 값이 다르면 작은 쪽이 실제 한도가 됩니다.
- `0`, 음수, `+` 부호, 16진수, `256M` 같은 단위가 붙은 값은 잘못된 값입니다.
  - 처음 시작할 때 잘못된 값이면 listener를 열지 않고 시작에 실패합니다(`Invalid Thrift wire limits; listener not started`, 종료 코드는 0).
- 시작할 때만 읽습니다.
  - fb303 `reinitialize`로 값을 바꾸면 `Thrift wire-limit changes require restart` 로그를 남기고 기존 값을 유지합니다.
- 이 한도는 프로세스 메모리 상한이 아니며, 원본에서 받던 모든 큰 요청의 호환을 보장하지도 않습니다.

**한도를 넘는 relay batch[^18]는 나누거나 버리지 않습니다.**
**실패로 처리하고 계속 다시 시도합니다.**
신버전 network store는 보내기 전에 요청 크기를 계산합니다(요청 전체 21 bytes + 메시지마다 15 bytes + category 길이 + 메시지 길이).
한도를 넘으면 `Relay Log exceeds configured wire limit <268435456> bytes` 로그를 남기고 일시 실패로 처리합니다.

buffer store 아래라면 spool 파일을 지우지 않은 채 재시도를 반복합니다.
가장 오래된 파일부터 보내므로 그 뒤의 spool 파일도 모두 함께 멈춥니다.

**계산 예.** 짧은 메시지를 많이 보내는 category를 128 MiB spool로 보호하는 경우입니다.

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

| 평균 메시지 길이 | 가득 찬 128 MiB 파일의 메시지 수 | 재전송 요청 크기 | 256 MiB 한도 |
| --- | --- | --- | --- |
| 12 bytes | 8,388,608 | 293,601,301 bytes (약 280 MiB) | **넘음: 영원히 재시도** |
| 30 bytes | 약 3,947,580 | 약 209,221,761 bytes (약 199.5 MiB) | 통과 |

`game_pvp`라면 평균 메시지가 약 15 bytes(= category 길이 + 7)보다 짧을 때 가득 찬 128 MiB spool 하나가 256 MiB를 넘습니다.
이런 category는 secondary `max_size`를 더 작게 잡으세요(예: `max_size=67108864`).
`max_size`는 쓰고 난 뒤에 검사하므로 파일이 `max_size`를 조금(대략 `max_write_size`, 기본 1,000,000 bytes 이내) 넘을 수 있습니다.

secondary에 `max_size`를 쓰지 않으면 file store 기본값 1,000,000,000 bytes가 적용됩니다.
그러면 장애가 길어질 때 256 MiB를 넘는 spool이 생길 수 있습니다.
`max_write_size`나 회전 설정만 줄인다고 요청 크기가 보장되지는 않습니다.
한도를 올리려면 받는 서버도 그 크기를 받을 수 있어야 합니다.

**확인한 호환성.** 대표적인 작은 로그로 **구 서버→새 서버와 새 서버→구 서버 전송**과 일반 spool 파일의 양방향 읽기를 확인했습니다.
구 ThriftFile writer→새 reader와 새 writer→구 reader도 확인했습니다.
모든 파일·손상 입력·언어 client·장애 상황을 확인한 것은 아닙니다.

2026-10-06 원본 계약 복원 [PR #25](https://github.com/dbwk10317/scribe-next/pull/25)를 main에 반영했습니다.
새 writer→구 Thrift 0.9.0 reader의 최종 보관 기록도 정상 종료와 `events=2 bytes=10`을 확인하며, 복원한 내용은 `4100420aff656e64730a`입니다.
[호환성 정책](docs/legacy-compatibility-policy.md), [실제 비교 기록](docs/daemon-differential.md)과 [ThriftFile 처리 기록](docs/thriftfile-fix-options.md)에 자세한 근거를 남깁니다.

### 고친 문제

이 항목에는 두 종류의 수정이 있습니다.
원본이 비정상 종료하거나 정의되지 않은 동작(UB[^19])을 하던 경우를 정의된 오류로 바꾼 수정과, 로그의 분배·파일 형식·전달 결과를 바꾸지 않는 전송·연결 수정 세 가지입니다.

2026-10-06의 [PR #25](https://github.com/dbwk10317/scribe-next/pull/25)는 원본 계약을 우선해 이전 수정들을 원본 동작으로 되돌렸습니다.
그중 **로그의 분배·파일 형식·전달 결과를 바꾸지 않는다고 리뷰로 확인한 세 가지만** 2026-10-07에 다시 적용했습니다.
근거와 관찰 차이는 [호환성 정책의 "다시 고친 동작"](docs/legacy-compatibility-policy.md#다시-고친-동작-2026-10-07)에 있습니다.

아래 표의 6가지는 원본에서 프로그램이 비정상 종료하거나 미정의 동작을 하던 경우입니다.
이런 경우에는 "원본과 같은 결과"라는 것이 없으므로 안전한 동작으로 바꿨습니다.
정상 설정의 결과는 바꾸지 않았습니다.

| 원본 문제 | 이런 설정에서 생김 (예) | 구버전 | 신버전 |
| --- | --- | --- | --- |
| spool 읽기 버퍼를 `malloc`으로 만들고 `delete[]`로 해제 | buffer의 file secondary에서 spool을 다시 읽을 때 | 해제 함수가 맞지 않는 미정의 동작 | 맞는 함수로 해제 |
| 재시도 시간의 랜덤 범위가 0이면 나머지 연산 오류 | `retry_interval_range=0`인 buffer의 primary 연결 실패 | 0으로 나누기 오류로 비정상 종료할 수 있음 | 랜덤 오프셋 없이 재시도 간격 계산 |
| 알 수 없는 bucket 하위 store 종류 | `<bucket1>` 안의 `type=netwrok`처럼 오타 | null store를 사용해 비정상 종료할 수 있음 | 설정 오류와 fb303 `WARNING` |
| service list의 기본 port를 지정하지 않으면 초기화되지 않은 값 사용 | port 없는 `service_list`, `list_default_port`도 없음 | 쓰레기 값을 port로 사용 | port를 0으로 정함(연결 실패) |
| 추가 bucket 검사가 문자열 밖 메모리를 읽음 | `bucket0`…`bucketN`을 직접 정의하고 `num_buckets=6` 이상 | 문자열 밖을 읽는 미정의 동작 | 이 검사를 건너뜀 |
| 빌드 호환성: 구 libhdfs와 현대 libhdfs의 파일 삭제 함수 인자 수가 다름 | `fs_type=hdfs`로 빌드·실행 | 현대 libhdfs와 빌드 불가 | 두 API에 맞게 연결 |

spool 읽기 버퍼 문제는 `type=buffer`의 `<secondary>`가 `type=file`(`fs_type=std`)이고, 장애가 끝난 뒤 spool을 다시 읽어 보낼 때 생깁니다.
신버전도 읽는 내용과 파일 형식은 같습니다.

재시도 시간 문제는 `retry_interval=30`, `retry_interval_range=0`인 buffer가 primary 연결에 실패할 때 생깁니다.
`adaptive_backoff=yes`, `max_random_offset=0`도 같습니다.
신버전은 랜덤 오프셋(jitter[^20]) 없이 재시도 간격을 30초로 계산하며, 정상 범위의 계산은 같습니다.

알 수 없는 bucket 하위 store 종류를 쓰면 신버전은 `can't create store of type: netwrok` 설정 오류를 내고 fb303 상태가 `WARNING`이 됩니다.
정상 종류의 분배는 같습니다.

service list 문제는 `service_list=relay-a.example relay-b.example`처럼 port 없이 쓰고 `list_default_port`도 없을 때 생깁니다.
신버전은 자동으로 맞는 port를 찾아 주지는 않으므로 `host:port`나 `list_default_port=1463`을 쓰세요.

추가 bucket 검사를 건너뛰어도 정상 분배는 같고, 추가 bucket을 새로 거부하지 않습니다([남겨 둔 버그](#추가-bucket-검사는-이름-대신-문자열-중간을-본다) 참고).

libhdfs의 파일 삭제 함수는 두 API에 맞게 연결하며, 현대 API에는 `recursive=1`을 넘깁니다.
원본의 결과 무시·로그 처리는 같습니다.
HDFS 전체 오류 처리를 새로 고친 것은 아닙니다.

전송·연결 수정 세 가지를 요약하면 다음과 같습니다.

| 수정 | 해당하는 설정 | 구버전 | 신버전 |
| --- | --- | --- | --- |
| [동적 목적지 변경](#동적-목적지-변경과-연결-pool) | `use_conn_pool=yes` + `dynamic_config_type` | 새 목적지의 연결을 닫아 다른 store의 batch가 한 번 실패할 수 있고, 옛 연결은 계속 열림 | 옛 연결만 닫음 |
| [`service_list` 재연결](#service_list-재연결) | `service_list` | 다시 연결할 때마다 후보 목록이 한 벌씩 늘어남 | 매번 목록을 새로 만듦 |
| [재전송 일부 성공](#buffer-재전송-일부-성공) | `buffer` + `file` 등 일부만 처리할 수 있는 primary | 남은 로그를 `lost`로 세고 spool 파일 삭제 | 남은 로그를 spool에 다시 쓰고 재시도 |

#### 동적 목적지 변경과 연결 pool

**무엇이 문제였나.** `dynamic_config_type=thrift_bucket`을 쓰는 network store는 `check_interval`마다 목적지를 확인합니다.
bucket updater에는 `bucket_updater_ttl`(기본 60초)마다 다시 묻습니다.
목적지가 바뀌면 연결을 닫았다가 새 목적지로 다시 엽니다.
구버전은 **주소를 새 값으로 먼저 바꾼 뒤** 연결을 닫았습니다.

`use_conn_pool=yes`이면 연결은 `host:port` 이름으로 공유되고 사용자 수(refcount[^21])로 관리됩니다.
그래서 구버전은 옛 목적지 대신 **새 목적지 이름의 사용자 수를 줄이게** 됩니다.

**신버전의 동작.** 연결을 먼저 닫고(옛 목적지의 사용자 수를 줄이고) 그다음 주소를 바꿉니다.
`use_conn_pool=no`(기본값)는 원래부터 자기 연결만 닫았으므로 차이가 없습니다.
분배·파일 내용·최종 전달 결과는 같습니다.

**영향받는 설정 키.** `use_conn_pool=yes`와 `dynamic_config_type`입니다.
`bucket_updater_host`·`bucket_updater_port`(또는 `bucket_updater_service`)와 `bucket_updater_ttl`도 해당합니다.
[모델 복사본은 동적 조회 설정을 물려받지 않으므로](#network-복사본은-service_list와-동적-조회-설정을-물려받지-않는다) 직접 설정한 store만 해당합니다.

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

bucket updater가 game_purchase bucket1의 목적지를 `relay-a.example:1463`에서 `relay-b.example:1463`으로 바꾸면:

| 단계 | 구버전 | 신버전 |
| --- | --- | --- |
| 닫는 연결 | `relay-b.example:1463`(새 목적지)의 사용자 수를 줄임 | `relay-a.example:1463`(옛 목적지)의 사용자 수를 줄임 |
| `relay-a.example:1463` 연결 | 사용자 수가 줄지 않아 계속 열려 있음 | 다른 사용자가 없으면 닫힘 |
| game_login의 `relay-b.example:1463` 연결 | 닫히고 pool에서 지워질 수 있음 | 영향 없음 |
| 새 목적지를 쓰던 store가 없을 때 | `LOGIC ERROR` 진단 로그 | 이 로그 없음 |
| 로그의 분배·내용·최종 전달 | 같음 | 같음 |

구버전에서 game_login의 `relay-b.example:1463` 연결은 사용자 수가 0이 되면 닫히고 pool에서 지워질 수 있습니다.
그러면 game_login의 다음 batch 1회가 실패해 `requeue`로 집계되고 다시 연결됩니다.
새 목적지를 쓰던 store가 없을 때 구버전이 남기는 진단 로그는 다음과 같습니다.

```text
LOGIC ERROR: attempting to close connection <relay-b.example:1463> that connPool has no entry for
```

#### service_list 재연결

**무엇이 문제였나.** `service_list`를 쓰는 network store는 연결을 열 때마다 목록 문자열을 해석해 서버 후보 목록을 만듭니다.
구버전은 기존 목록을 비우지 않고 **매번 전체 목록을 뒤에 덧붙였습니다.**
그래서 실행 시간과 재연결 횟수에 따라 메모리가 늘었습니다.
K번 다시 연결한 뒤에는 죽은 서버를 한 번 여는 동안 최대 K번(각각 `timeout`만큼) 시도해, 다른 서버로 넘어가는(failover[^22]) 시간이 점점 길어졌습니다.

**신버전의 동작.** 해석하기 전에 목록을 비웁니다.
모든 후보가 똑같이 K번씩 중복됐었으므로 **서버 선택 확률은 구·신 모두 1/N으로 같습니다.**
`smc_service`를 쓰는 경로는 자체 cache로 목록을 갱신하므로 바뀌지 않았습니다.

**영향받는 설정 키.** `service_list`(그리고 `list_default_port`).
`use_conn_pool` 값과 무관합니다.

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
| 서버 후보 목록 | 15개(세 서버가 각각 5번씩 중복) | 3개 |
| 한 번 열 때 `relay-c.example` 시도 | 최대 5번, 각각 최대 2초(`timeout=2000`) | 최대 1번 |
| 각 서버가 선택될 확률 | 1/3 | 1/3 |

#### buffer 재전송 일부 성공

**무엇이 문제였나.** buffer store는 primary에 보내지 못한 로그를 secondary spool에 모아 둡니다.
primary가 살아나면 spool 파일 하나씩 다시 보냅니다(재전송, replay).
primary가 그 batch의 **앞부분만 처리하고 실패**하면 남은 로그만 spool 파일에 다시 써야 합니다.

그런데 구버전의 일반 파일(`StdFile::openTruncate`)은 `out|app|trunc` 조합으로 파일을 열었습니다.
이 조합은 C++ 표준상 열 수 없는 조합이라 **항상 실패**했습니다.
그 결과 남은 로그를 `lost`로 세고 spool 파일을 지워 영구 손실이 났습니다.

**신버전의 동작.** `out|trunc`로 열어 남은 로그를 **같은 4-byte 길이 frame 형식으로** spool 파일에 다시 씁니다.
그리고 primary 재연결 간격(`retry_interval`)이 지난 뒤 다시 보냅니다.
전체 실패는 원래부터 계속 재시도했으므로 일부 실패도 같은 방식이 된 것입니다.

spool 파일 형식은 바뀌지 않아 구버전도 읽을 수 있습니다.
보존·exactly-once·durable ACK·원자적 교체를 새로 약속하지는 않습니다.

**영향받는 설정 키.** 다음 설정의 buffer store가 해당합니다.

- `type=buffer`이고 `<secondary>`가 `type=file`(`fs_type=std`, 기본값)인 경우
- primary가 batch의 일부만 처리할 수 있는 store일 때
  - 대표적인 경우는 `type=file` primary가 쓰는 도중 실패(예: 디스크가 가득 참)하는 경우입니다.
  - file store는 `max_write_size` 단위로 나눠 쓰므로 batch가 여러 단위에 걸칠 때 일부만 쓰일 수 있습니다.
  - 코드상 `thriftfile`, `bucket`, `category`/`multifile` primary도 일부만 처리하고 실패를 돌려줄 수 있어 같은 경로를 탑니다.
- `type=network` primary는 batch를 통째로 성공 또는 실패로 보내므로 **이 경로에 오지 않습니다.**

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
| 남은 `m2`, `m3` | 다시 쓰지 못함(`Failed to open file <...> for writing and truncate` 로그) | spool 파일을 `m2`, `m3`만 남도록 다시 씀 |
| `game_purchase:lost` 카운터 | +2 | 늘지 않음 |
| spool 파일 | 삭제됨 | 남아 있다가 다음 재시도 때 전송 |
| primary 파일의 최종 내용 | `m1`만 저장되고 `m2`, `m3`는 영구 손실 | 다음 재시도가 성공하면 `m2`, `m3`도 저장 |

정상 frame에서는 `bytes lost` 카운터가 구·신 모두 0입니다.
secondary에 `add_newlines=1`이 있으면 기존 writer 규칙대로 **다시 쓴 나머지 메시지 끝에 LF[^23]가 하나 더 붙습니다.**
spool frame은 4-byte little-endian[^24] 길이 뒤에 내용을 둡니다.

```text
secondary에 add_newlines가 없을 때(example1.conf 방식): 다시 써도 같음
  m2 frame:  02 00 00 00  6d 32
secondary에 add_newlines=1일 때: 다시 쓴 frame에 LF가 하나 더 붙음
  처음 frame:     03 00 00 00  6d 32 0a          ("m2\n")
  다시 쓴 frame:  04 00 00 00  6d 32 0a 0a       ("m2\n\n")
```

### C++17 정리 (동작 불변)

원본 코드의 동작은 그대로 두고 표현만 C++17 방식으로 정리한 항목입니다.
**영향받는 설정 키는 없습니다.**
로그의 분배·내용·파일 형식·전달·손실 집계·상태 조회·설정 해석은 바뀌지 않습니다.
바깥에서 보이는 차이는 아래 표의 stderr 진단 문구와, 원래 미정의 동작이던 경우뿐입니다.

| 정리한 것 | 예전 코드 | 바꾼 코드 | 왜 바깥 동작이 같은가 |
| --- | --- | --- | --- |
| `Log()`의 잠금 | 읽기 잠금을 손으로 잡고 `goto`로 풀었음 | 범위를 벗어나면 자동으로 푸는 RAII[^25] guard | 잠그고 푸는 지점과 순서가 같음 |
| 설정 트리의 부모 연결 | 부모와 자식 설정이 서로를 `shared_ptr`로 붙잡음 | 자식은 부모를 `weak_ptr`[^26]로 참조 | 상속 규칙과 해석 결과가 같고 누수만 없어짐 |
| store 상태·연결 pool map·HDFS 잠금 | `pthread_mutex_lock/unlock`을 손으로 호출 | `std::mutex`[^27]와 guard | glibc에서 같은 종류의 비재귀 mutex이고 잠그는 지점과 범위가 같음 |
| 가상 함수와 복사 금지 | 선언만 하고 정의하지 않는 옛 관용구 | `override`, `= delete` | 컴파일할 때 검사만 늘고 생성 코드는 같음 |
| 설정 값 읽기 | `(unsigned long&)` 캐스트로 다른 타입 변수에 바로 씀 | 같은 타입의 지역 변수로 읽은 뒤 대입 | 값·기본값·숫자 해석 방식이 같음 |
| 죽은 코드와 옛 함수 | `new` 직후의 null 검사, 쓰지 않는 include·변수 등 | 삭제하거나 표준 함수(`strrchr`, `std::string`)로 바꿈 | 실행되지 않던 코드이거나 같은 결과를 내는 표현 |
| spool 읽기의 손실 계산 | 함수 안 `CALC_LOSS` 매크로 | 같은 계산을 하는 멤버 함수 | 읽는 바이트·반환값·손실 계산이 같음 |
| store thread 생성 실패 | `pthread_create` 반환값을 보지 않아 실패하면 미정의 동작 | 실패를 store 생성 실패로 처리 | 원래 미정의 동작이던 경우만 정의된 오류가 됨 |
| 진단 로그 두 줄 | stderr에 글자 그대로 `oss.str()`로 찍혔음 | 실제 내용을 찍거나 함께 삭제 | stderr 문구만 바뀌고 로그 데이터·파일·카운터와 무관 |
| Boost 의존성(현대화 1·2단계) | `boost::shared_ptr`·`boost::filesystem`·`boost::split` | `std::shared_ptr`·`std::filesystem`·작은 분리 함수 | 같은 호출에 같은 결과. [왜 Boost를 제거했나](#왜-boost를-제거했나) 참고 |
| 전역 handler·연결 pool 의존(현대화 3단계) | store·queue·연결 pool·설정 조회가 전역 `g_Handler`·`g_connPool`을 직접 읽음 | handler가 넘겨주는 context(`ScribeContext`)를 씀 | 같은 handler의 같은 값·카운터·pool. [왜 전역 의존을 없앴나](#왜-전역-의존을-없앴나) 참고 |

`Log()`의 예전 코드는 중간에 예외가 나면 잠금이 영원히 풀리지 않았습니다.
그러면 이후 `reinitialize`·`shutdown`·새 category 생성이 멈출 수 있었습니다.
바꾼 코드도 잠그는 지점·푸는 지점·읽기에서 쓰기로 바꾸는 순서가 같고, 예외 때만 잠금이 제대로 풀립니다.

설정 트리는 예전에 `reinitialize`마다 메모리에 남았습니다.
지금도 설정 상속(`type::key`) 규칙과 해석 결과는 같습니다.

`std::mutex`로 바꾼 것은 store 상태 잠금, 연결 pool map 잠금, HDFS 잠금입니다.
연결 하나의 잠금(`scribeConn::mutex`)은 시험 fixture가 ERRORCHECK 속성으로 초기화하므로 `pthread_mutex_t`로 남아 있습니다.

설정 값 읽기에서 캐스트로 바로 쓰던 값은 `retry_interval`·`retry_interval_range`·`max_write_interval` 등입니다.
정리한 죽은 코드와 옛 함수는 `new` 직후의 null 검사, 쓰지 않는 `<strstream>`·include·변수, `rindex`, HDFS host 문자열의 `malloc`/`free`입니다.

store thread 생성 실패는 설정 단계에서 `Bad config - can't create a store of type: ...` 오류가 됩니다.

진단 로그 두 줄은 dynamic bucket updater의 "매핑 없음" 로그와 "socket 생성 실패" 로그입니다.
"매핑 없음"은 이제 실제 내용을 찍습니다.
"socket 생성 실패"는 실행될 수 없는 null 검사 안에 있어 함께 삭제했습니다.

이번 정리에서도 일부러 건드리지 않은 것이 있습니다.
겉보기에는 고칠 곳 같지만 원본의 관찰 결과를 만드는 코드입니다.

- [추가 bucket 검사의 문자열 포인터 계산](#추가-bucket-검사는-이름-대신-문자열-중간을-본다)과 bucket key 계산 방식(NUL이 든 key를 자르는 처리, 음수 key의 나머지 계산)
- [긴 명령행 옵션의 인자 선언](#긴-명령행-옵션의-인자-선언-결함)과 [시작 실패 시 종료 코드 0](#시작에-실패해도-종료-코드는-0이다)
- [빈 메시지만 든 큐를 전달하지 않는 판단](#빈-메시지만-든-큐는-전달되지-않는다)
- 재시도·bucket·서버 후보 순서에 쓰는 GNU `rand()` 순서
- store queue의 thread·조건 변수(시간 기준과 깨우기 의미가 바뀔 수 있어 그대로 둠)

#### 왜 전역 의존을 없앴나

원본의 store·store queue·연결 pool·설정 조회·dynamic bucket updater는 프로세스 전역 변수 두 개를 직접 읽었습니다.
실행 중인 서버 handler인 `g_Handler`에서 카운터 증가, `max_queue_size`, Thrift 크기 한도, 설정 상속(`type::key`)의 최상위 설정, fb303 객체를 얻었고, `use_conn_pool=yes` 연결은 `store.cpp`의 전역 `g_connPool`로 공유했습니다.
이제 handler가 이 기능만 담은 작은 interface(`ScribeContext`, `src/context.h`)를 구현하고 연결 pool을 직접 가지며, store queue를 만들 때 자신을 넘깁니다.
store와 연결은 그 context를 queue나 부모 store에서 이어받고, 설정 트리는 handler가 설정을 읽을 때마다 최상위 설정을 연결해 둡니다.
전역 변수가 없으니 store·queue·연결 pool을 서버 전체 없이 따로 만들어 시험할 수 있고, 각 부품이 서버의 무엇을 쓰는지 생성자에 드러나 숨은 연결이 없습니다.
서버 하나에 context 하나이므로 읽는 값, 카운터 이름, 연결 pool의 공유 범위·참조 수·잠금 순서는 예전과 같습니다.
설정 키는 바뀌지 않았고 로그의 분배·내용·파일 형식, 카운터와 stderr 문구도 같습니다.
`g_Handler`는 Thrift 서버를 구성하는 `main()`과 `scribe::createServer()`에만 남아 있습니다.

### 검증 도구

이 절의 도구는 이식 결과를 검증하는 개발자용이며, 설치에는 필요하지 않습니다.
설치는 [빠른 시작](#빠른-시작)을 따르세요.

| 도구 | 하는 일 | 현재 결과 |
| --- | --- | --- |
| `tools/validate_linux.py` | 새 출력 폴더에서 빌드·시험·임시 설치 확인 | 2026-10-07 Rocky 9.8(WSL), 현재 `main` 236개 통과 |
| `tools/daemon_differential.py` | 구·신 daemon을 실제로 실행해 결과 비교 | 2026-10-07 10개 case 구·신 통과 |
| `tools/old-lane/` | 구버전 daemon 재현 빌드와 격리 컨테이너 실행 | 위 비교에 사용 |

`tools/validate_linux.py`는 새 출력 폴더에서 configure·전체 빌드·시험·임시 설치·`scribed --help`를 확인합니다.
시스템에 설치하거나 서비스를 시작하지 않습니다.

2026-10-07 WSL Rocky 9.8에서 이 시험 묶음을 실행했습니다.
이 작업 전에는 220개, 이 작업의 첫 PR(#48) 뒤에는 224개, 이어서 병합한 PR(#40–#49) 뒤 현재 `main`에서는 236개가 통과했습니다.
세 번 모두 실패·오류·skip은 0이었습니다.
다른 환경의 횟수는 [지원 환경](#지원-환경)을 참고하세요.

검증기는 미리 준비한 의존성의 위치를 `THRIFT_PREFIX`, `FB303_PREFIX`, `TOOLS_PREFIX`, `THRIFT_PYTHON_SOURCE` 환경 변수로 받습니다.
원본 비교용 커밋 `fcd294f`의 Git object도 필요하므로 ZIP이 아닌 Git checkout에서 실행합니다.
검증기는 이 object와 Git 보호 옵션을 빌드 전에 검사하지만, 원본을 자동으로 fetch하지는 않습니다.
준비 방법과 명령은 [빌드 안내](docs/linux-build-mvp.md)와 [Git 준비 안내](docs/linux-build-mvp.md#검증용-git-이력-준비)에 있습니다.

출력 폴더는 프로젝트 밖의 아직 없는 폴더여야 하며, 그 상위 폴더는 미리 존재해야 합니다.
`--shared-rpc`를 붙이면 공유 RPC 라이브러리 빌드도 확인합니다.

`tools/daemon_differential.py`는 구버전 daemon과 신버전 daemon을 각자의 runtime으로 실제 실행합니다.
그리고 같은 요청의 응답·저장 bytes·카운터를 비교합니다.
격리 환경에서만 실행하는 opt-in 도구이며, 그 환경은 아래 `tools/old-lane/`이 만들어 줍니다.
case별 결과는 [실제 비교 기록](docs/daemon-differential.md)에 있습니다.

비교 도구는 Docker·namespace·의존성·권한을 직접 설정하지 않으며, 구·신 실행 파일의 절대 경로와 환경은 targets 파일로 받습니다.
시험 묶음은 `--case`로 고릅니다.

- `file`(기본값)
- `stores`
- `rotation`
- `restart`
- `spool`
- `mixed-spool`
- `file-stores`
- `performance`
- `fb303`
- `mapping`
- `game-profile`

```sh
python tools/daemon_differential.py --run-isolated-daemons --case game-profile \
  --targets /prepared/targets.json --output /prepared/new-game-profile-output
```

**구·신 실제 비교.** 2026-10-07에 WSL Rocky 9.8과 Docker 29.8에서 구버전 daemon을 재현해 빌드하는 `tools/old-lane/`을 추가했습니다.
구성 파일은 다음 세 가지입니다.

- `Dockerfile.old`: 원본 `fcd294f`를 `ubuntu:16.04`에서 GCC 5.4, Boost 1.58, Thrift/fb303 0.9.0으로 빌드합니다.
  - 원본에 더하는 변경은 autotools만 고치는 `scribe-autotools.patch` 하나뿐입니다.
- `Dockerfile.runtime`: 이 구버전 실행 파일과 runtime 라이브러리 7개를 현대 이미지와 합칩니다.
- `run_differential.sh`: 비교 도구를 `--network none --user 65534:65534 --cap-drop ALL` 컨테이너에서 실행합니다.

이 환경에서 위 목록 중 `performance`를 뺀 10개 case가 모두 구·신 비교를 통과했습니다.
각 case는 `main`의 e012376에서 한 번씩 실행했습니다.
`performance`와 HDFS는 실행하지 않았습니다.
구버전 실행 파일은 Ubuntu 16.04 전체 userland가 아니라 Rocky의 glibc/libstdc++ 위에서 실행했습니다.

다시 빌드하고 실행하는 세 명령은 [`tools/old-lane/README.md`](tools/old-lane/README.md)에 있습니다.

**`--case game-profile`(새로 추가).** 게임 서버 배포에서 자주 쓰지만 앞의 case가 다루지 않던 설정 기능을 가상의 설정 하나에 모았습니다.
설정은 `tools/daemon_game_profile.conf.template`, driver는 `tools/daemon_game_profile_case.py`입니다.
실제 운영 설정·host·경로·category 이름은 옮기지 않았습니다.
다루는 기능은 다음과 같습니다.

- prefix를 포함한 `categories=` 목록(`categories=fixture-login fixture-session fixture-metrics-*`)
- `category=default` 모델과 단독 prefix 모델 `category=ext-*`
- `type=multi` 아래 두 개의 `buffer` 하위 store
- `use_conn_pool` 없는 network primary와 `use_conn_pool=yes` network primary, 각각 `add_newlines=1` file secondary
- `rotate_period=1h`인 file primary
- 줄 중간의 `#` 주석(`max_size=1000000 #1M`)

이 case에는 소스 코드를 읽어 정한 기대값에 대한 offline 시험 4개가 있습니다.
격리 없는 개발 host에서 **신버전만** 같은 절차로 6회 실행한 결과도 있습니다.
2026-10-07에는 위 `tools/old-lane/` 환경에서 **구버전과 신버전을 실제로 나란히 실행해** 비교를 통과했습니다.

이 case는 bucket·thriftfile·multifile, `service_list`/`smc_service`, `dynamic_config_type`, 재전송 일부 성공을 다루지 않습니다.
여러 category가 공유하는 pooled 연결, 실제 1시간 회전, 반복 실패와 성능도 다루지 않습니다.

## 일부러 남겨 둔 버그

기준은 [공개 Facebook Scribe 원본](https://github.com/facebookarchive/scribe/tree/fcd294faffd1e88af1643a3a8c2359c41713f7c2)입니다.
아래 항목은 원본의 **정의된** 동작이며, 고치면 로그가 저장되는 위치·내용·형식, 전달 여부, 상태 조회 결과가 바뀝니다.
그 결과를 읽는 기존 프로그램(적재·집계 job, 감시 도구)을 지키기 위해 **구버전과 신버전이 똑같이 동작하도록 남겨 두었습니다.**

되돌린 버그를 다시 고치는 새 옵션도 추가하지 않았습니다.
반대로 `retry_interval_range=0`처럼 원본이 비정상 종료하던 경우는 남기지 않았습니다([고친 문제](#고친-문제)).

여러 항목에 나오는 "복사본"은 `category=default`, `categories=...`, `prefix*` 같은 모델 설정에서 category마다 만들어지는 store입니다.
자세한 규칙은 [알아둘 점](#default-categories-prefix-설정은-모델이고-실제-store는-복사본이다)에 있습니다.

| 항목 | 영향받는 설정 키 |
| --- | --- |
| [Bucket 복사본은 bucket_range와 remove_key를 물려받지 않는다](#bucket-복사본은-bucket_range와-remove_key를-물려받지-않는다) | `bucket_range`, `remove_key` |
| [추가 bucket 검사는 이름 대신 문자열 중간을 본다](#추가-bucket-검사는-이름-대신-문자열-중간을-본다) | `num_buckets`, `bucket0`…`bucketN` |
| [ThriftFile 복사본은 use_simple_file을 무시한다](#thriftfile-복사본은-use_simple_file을-무시한다) | `use_simple_file`, `chunk_size` |
| [Network 복사본은 service_list와 동적 조회 설정을 물려받지 않는다](#network-복사본은-service_list와-동적-조회-설정을-물려받지-않는다) | `service_list`, `dynamic_config_type` 등 6개(항목 참고) |
| [service_list와 use_conn_pool은 빈 연결 key 하나를 같이 쓴다](#service_list와-use_conn_pool은-빈-연결-key-하나를-같이-쓴다) | `service_list`, `use_conn_pool` |
| [빈 메시지만 든 큐는 전달되지 않는다](#빈-메시지만-든-큐는-전달되지-않는다) | `add_newlines`(결과에 영향) |
| [OK는 메모리 큐에 받았다는 뜻이다](#ok는-메모리-큐에-받았다는-뜻이다) | 없음 |
| [긴 명령행 옵션의 인자 선언 결함](#긴-명령행-옵션의-인자-선언-결함) | 명령행 `--config`, `--port` |

### Bucket 복사본은 bucket_range와 remove_key를 물려받지 않는다

**무엇이 문제인가.** bucket store 복사본은 `num_buckets`, `bucket_type`, `delimiter`와 하위 store를 복사합니다.
하지만 `bucket_range`와 `remove_key`는 복사하지 않습니다.
그래서 복사본에서는 `bucket_type=key_range`의 범위가 0이 되어 **모든 메시지가 bucket 0으로 가고**, `remove_key=yes`여도 **key가 메시지에 남습니다.**
`key_hash`·`key_modulo`는 분배는 맞지만 key가 남는 점은 같습니다.

**왜 남겨 두었는가.** 고치면 기존 복사본 로그가 다른 bucket 폴더로 옮겨 가고 내용에서 key가 빠집니다.
bucket 폴더별로 파일을 가져가거나 key가 붙은 형식을 파싱하는 프로그램이 다른 결과를 보게 됩니다.

**구버전과 신버전의 동작.** 같습니다.

**영향받는 설정 키.** 모델 store의 `bucket_range`, `remove_key`(그리고 `bucket_type=key_range`).

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
| 같은 설정을 `category=game_score`로 직접 썼다면 | 15 % 20 = 15 → bucket 2 | `/var/log/scribed/score/shard002/game_score_all_00000` | `hello\n` |
| 위 설정의 실제 결과(복사본) | 범위 0 → bucket 0 | `/var/log/scribed/score/shard000/game_score/game_score_00000` | `15\|hello\n` |

### 추가 bucket 검사는 이름 대신 문자열 중간을 본다

**무엇이 문제인가.** `bucket0`부터 `bucketN`까지 직접 정의할 때 원본은 `bucketN+1`이 더 있는지 검사하려고 했습니다.
하지만 문자열 `"bucket"`에 숫자를 더하는 C 포인터 계산 실수 때문에 **글자 중간부터를 이름으로 찾습니다.**
`num_buckets=1`이면 `bucket2`가 아니라 `cket`, 2이면 `ket`, 3이면 `et`, 4이면 `t`, 5이면 빈 이름을 찾습니다.
그래서 `bucketN+1`을 정의해도 거부하지 않습니다.

**왜 남겨 두었는가.** 올바르게 고치면 지금까지 시작되던 설정이 `bucket store has too many buckets defined`로 거부됩니다.
그러면 해당 store 없이 `WARNING` 상태로 뜨게 됩니다.

**구버전과 신버전의 동작.** `num_buckets` 1~5에서는 같습니다.
6 이상에서 구버전은 문자열 밖 메모리를 읽는 미정의 동작이고, 신버전은 이 검사를 건너뜁니다(둘 다 거부하지 않음).

**영향받는 설정 키.** `num_buckets`, `bucket0`…`bucketN` 블록.

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

결과: 설정은 정상으로 시작합니다(검사는 `ket`이라는 이름을 찾음).
로그는 `unkeyed`, `shard1`, `shard2`로만 가고 `shard3`에는 쓰이지 않습니다.
필요한 bucket 수는 `num_buckets`로 정하고 실제 분배 결과를 확인하세요.

### ThriftFile 복사본은 use_simple_file을 무시한다

**무엇이 문제인가.** `type=thriftfile`에 `use_simple_file=1`(0이 아닌 값)을 주면 메시지 내용만 이어 쓰는 raw 형식으로 저장합니다.
그런데 복사본은 이 값을 복사하지 않아 **길이 정보와 chunk 경계 padding이 붙은 framed 형식(Thrift `TFileTransport`)으로 저장합니다.**
category별 복사본을 쓰는 `thriftmultifile`도 같습니다.

**왜 남겨 두었는가.** 고치면 기존 reader가 읽던 framed 파일 자리에 raw 파일이 생깁니다.
raw와 framed는 서로 다른 reader가 필요합니다.

**구버전과 신버전의 동작.** 같습니다.

**영향받는 설정 키.** 모델 store의 `use_simple_file`.
framed 파일을 읽을 때는 writer와 같은 `chunk_size`를 써야 합니다.

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
| 같은 설정을 `category=game_chat`으로 직접 썼다면 | `/var/log/scribed/tfile/chat_all_00000` | raw (메시지 bytes만) |
| 위 설정의 실제 결과(복사본) | `/var/log/scribed/tfile/game_chat/game_chat_00000` | framed |

함께 알아둘 점:

- 원본 일반 spool 파일의 형식은 ThriftFile 형식과 별개입니다.
- 이전 개발 버전이 raw 형식 복사본 파일을 이미 만들었다면 그 파일은 그대로 남습니다.
  - 현재 버전으로 바꿔도 변환하지 않으며, 같은 폴더에 서로 다른 형식의 파일이 있을 수 있습니다.
  - reader 선택과 이전 버전으로의 전환 전에 실제 파일 형식을 확인하세요.
- 빈 메시지나 chunk보다 큰 메시지에 대한 원본 ThriftFile의 처리도 유지합니다.
  - 길이 표시 4 bytes를 포함한 메시지 크기가 `chunk_size`(기본 16,777,216 bytes)를 넘으면 오류 로그만 남고 기록되지 않습니다.
  - 그런데도 Scribe 호출과 성공 집계는 성공으로 보일 수 있습니다.

### Network 복사본은 service_list와 동적 조회 설정을 물려받지 않는다

**무엇이 문제인가.** network store 복사본은 원래 필드만 복사합니다.
원래 필드는 `remote_host`, `remote_port`, `use_conn_pool`, `timeout`, `smc_service` 이름입니다.
다음은 복사하지 않습니다.

| 복사하지 않는 설정 | 복사본에서 생기는 일 |
| --- | --- |
| `service_list`, `list_default_port` | 목록이 비어 서버에 연결할 수 없음 |
| `service_options`, `service_cache_timeout` | 기본값(cache 300초)을 씀 |
| `ignore_network_error` | 기본값(no)을 씀 |
| `dynamic_config_type`과 갱신기 | 모델이 설정 시점에 받아 둔 주소를 계속 씀 |

**`service_list`를 쓰는 `default`·`categories=`·prefix 모델의 복사본은 구·신 모두 로그를 전달하지 못합니다.**
예외는 모델이 `use_conn_pool=yes`이고, 직접 설정한 다른 `service_list` store가 [빈 연결 key](#service_list와-use_conn_pool은-빈-연결-key-하나를-같이-쓴다)로 연결을 열어 둔 경우입니다.
이때는 그 연결(즉 그 store의 목록 서버)로 보냅니다.

공개 원본의 서비스 이름 조회는 항상 실패하는 예제 구현입니다.
`ignore_network_error`가 기본값이므로 연결 실패 시 `Failed to connect` 상태와 fb303 `WARNING`이 보입니다.
`dynamic_config_type`을 쓰는 모델의 복사본은 category별로 다시 조회하거나 갱신하지 않습니다.

**왜 남겨 두었는가.** 보완하면 전달되지 않던 로그가 갑자기 전달되거나 목적지가 바뀌고 상태 조회 결과도 달라집니다.
다음 서버의 데이터 양과 감시 도구가 보던 상태가 바뀝니다.

**구버전과 신버전의 동작.** 같습니다.
직접 설정한 store의 동적 조회·TTL 갱신은 원본대로 동작합니다.

**영향받는 설정 키.** 모델 store의 `service_list`, `list_default_port`, `service_options`, `service_cache_timeout`입니다.
`ignore_network_error`와 `dynamic_config_type`도 해당합니다.

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

결과: 처음 보는 category(예: `game_event`)가 들어올 때마다 복사본이 만들어지지만 연결할 서버가 없습니다.
로그는 `/var/log/scribed/spool/game_event/game_event_00000`, `_00001`, …에 계속 쌓입니다.
`game_event:retries` 카운터가 늘며 fb303 상태는 `WARNING`, 상세 설명은 `Failed to connect`입니다.

`default`·category 모델로 network store를 쓸 때는 `remote_host`/`remote_port`를 쓰거나 category를 직접 설정하세요.
그리고 실제 목적지와 fb303 상태를 확인하세요.
`ignore_network_error`가 적용되는 경우에도 실제 연결 실패가 성공으로 바뀌는 것은 아닙니다.

### service_list와 use_conn_pool은 빈 연결 key 하나를 같이 쓴다

**무엇이 문제인가.** `use_conn_pool=yes`인 연결은 이름(key)으로 공유됩니다.
`remote_host`/`remote_port`는 `host:port`, `smc_service`는 서비스 이름이 key인데, `service_list`는 **빈 문자열**이 key입니다.
그래서 서로 다른 목록을 쓰는 store들이 **먼저 열린 연결 하나를 같이 씁니다.**

**왜 남겨 두었는가.** 연결을 목록마다 나누면 전송 대상·연결 수·선택 비율이 바뀝니다.

**구버전과 신버전의 동작.** 같습니다.
재연결할 때 후보 목록이 늘어나던 문제는 따로 [고쳤습니다](#service_list-재연결).

**영향받는 설정 키.** `service_list`, `use_conn_pool`.

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

결과: 먼저 연결을 연 store의 목록 서버로 두 category가 모두 전송됩니다.
예를 들어 game_login이 먼저 열었다면 game_chat 로그도 `relay-a.example` 또는 `relay-b.example`로 갑니다.
서로 다른 목록을 쓴다면 실제 목적지를 확인하고, 기존 옵션인 `use_conn_pool=no`(기본값)를 검토하세요.
이 옵션은 새로 만든 버그 수정 옵션이 아니라 원래 있던 연결 공유 설정입니다.

### 빈 메시지만 든 큐는 전달되지 않는다

**무엇이 문제인가.** store queue는 큐에 든 **메시지 내용의 총 byte 수**로 처리할지를 판단합니다.
빈 메시지만 있으면 메시지가 있어도 총 크기가 0이라 주기 처리나 종료 때 전달하지 않습니다.
서버는 이미 `OK`를 돌려주고 `received good` 카운터를 늘렸는데도 저장 파일은 비어 있고 `lost` 카운터도 0일 수 있습니다.

**왜 남겨 두었는가.** 고치면 `add_newlines=1`인 store에 빈 줄이 새로 저장되고 전달 횟수가 달라집니다.
줄 단위로 읽는 프로그램이 새로운 빈 줄을 보게 됩니다.

**구버전과 신버전의 동작.** 같습니다.
빈 메시지와 일반 메시지가 같은 큐에 섞이면 함께 처리되며, 메시지가 하나도 없는 Log 요청과도 구분해야 합니다.

**영향받는 설정 키.** 특정 키는 없습니다.
`add_newlines` 값에 따라 고쳤을 때의 결과가 달라집니다.

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
같은 큐에 비어 있지 않은 메시지가 함께 들어오면 그때 빈 메시지도 `\n`으로 저장됩니다.

### OK는 메모리 큐에 받았다는 뜻이다

**무엇이 문제인가.** 서버의 `OK` 응답은 로그를 메모리 큐에 받았다는 뜻입니다.
디스크 저장 완료나 중복 없는 전달을 보장하지 않습니다.
파일 `flush`도 `fsync`와 다릅니다.
`OK`를 받은 직후 프로세스가 갑자기 종료되면 큐에 있던 로그는 남지 않을 수 있습니다.

**왜 남겨 두었는가.** 응답 의미를 바꾸면 응답 시점과 처리량이 달라지고, 기존 클라이언트의 재시도 동작에 영향을 줍니다.

**구버전과 신버전의 동작.** 같습니다.
신버전은 durable ACK, exactly-once, fsync를 새로 보장하지 않습니다.

**영향받는 설정 키.** 없습니다.

### 긴 명령행 옵션의 인자 선언 결함

**무엇이 문제인가.** 원본은 `--config`와 `--port`를 **값을 받지 않는 옵션**으로 선언했습니다.
`--config=/etc/scribed/scribed.conf`처럼 쓰면 값을 받지 않는 옵션이라며 사용법만 출력하고 종료(코드 0)합니다.
`--config /etc/scribed/scribed.conf`처럼 쓰면 값이 옵션에 전달되지 않아 정상 동작을 기대할 수 없습니다.

**왜 남겨 두었는가.** 명령행 해석 결과도 외부에서 보이는 동작이므로 원본대로 둡니다.

**구버전과 신버전의 동작.** 같습니다.

**영향받는 설정 키.** 명령행 `--config`, `--port`.
짧은 옵션을 쓰세요.

```sh
scribed -c /etc/scribed/scribed.conf -p 1463
# 옵션이 아닌 첫 인자도 설정 파일로 읽습니다.
scribed /etc/scribed/scribed.conf
```

## 알아둘 점

버그라기보다 원본 설계에서 나오는 동작이며 **구버전과 신버전 모두 같습니다**(`max_msg_per_second`의 동시 요청 계산만 다름).
기존 설정을 옮기거나 새로 쓸 때 확인하세요.

### default, categories, prefix 설정은 모델이고 실제 store는 복사본이다

`category=default`, `categories=a b c`, `category=game_*`(끝이 `*`인 prefix)로 쓴 `<store>`는 **모델**입니다.
기본값 `new_thread_per_category=yes`에서는 실제로 로그를 처리하는 store가 모두 모델의 **복사본**입니다.
`categories=`의 이름들은 시작할 때, `default`와 prefix는 해당 category의 첫 로그가 들어올 때 복사됩니다.

복사본의 file store는 이름과 위치가 바뀝니다.

- `base_filename`은 무시되고 **category 이름**으로 바뀝니다.
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

2026-10-07에 category `game_login` 로그가 처음 들어오면:

```text
/var/log/scribed/data/game_login/game_login-2026-10-07_00000
/var/log/scribed/data/game_login/game_login_current -> game_login-2026-10-07_00000
```

같은 설정을 `category=game_login`으로 직접 쓰면 `/var/log/scribed/data/ignored_name-2026-10-07_00000`이 됩니다(category 폴더 없음).
복사본은 일부 설정을 물려받지 않습니다([남겨 둔 버그](#일부러-남겨-둔-버그)).
`new_thread_per_category=no`에서는 복사하지 않고 한 store가 모든 category를 받습니다.
그래서 file store라면 설정한 `base_filename` 파일 하나에 모입니다.

### prefix는 가장 긴 것이 아니라 정렬 순서상 첫 번째가 이긴다

처음 보는 category가 들어오면 서버는 ① 정확히 같은 이름의 store, ② prefix 모델, ③ `default` 모델 순서로 찾습니다.
prefix 모델은 **byte 순서로 정렬한 목록에서 처음 맞는 것**을 씁니다.
가장 길게 맞는 것을 고르지 않습니다.
`*`(0x2A)는 영문자·숫자·`_`·`-`보다 앞에 정렬되므로, **겹치는 prefix가 있으면 사실상 짧은 쪽이 항상 이깁니다.**

```conf
<store>
  category=game_*
  type=file
  file_path=/var/log/scribed/game
  base_filename=ignored
</store>

<store>
  category=game_login_*
  type=file
  file_path=/var/log/scribed/login
  base_filename=ignored
</store>
```

결과: `game_login_eu`는 `game_*`에 먼저 맞아 `/var/log/scribed/game/game_login_eu/`에 저장됩니다.
`game_*`로 시작하는 이름은 모두 `game_*`가 받으므로 `game_login_*` 모델은 쓰이지 않습니다.
특정 category를 따로 보내려면 정확한 이름(`category=game_login_eu`)이나 서로 겹치지 않는 prefix를 쓰세요.

### new_thread_per_category 기본값은 category마다 thread를 만든다

`new_thread_per_category`의 기본값은 `yes`입니다(`no`라고 정확히 쓴 경우만 꺼짐).
이때 **category마다, 그 category를 받는 최상위 `<store>`마다** store queue와 thread가 하나씩 생깁니다.
각 store는 자기 파일을 열고, `use_conn_pool=no`(기본값)이면 network 연결도 따로 엽니다.

예: `category=default` 모델 하나로 category 300개를 받으면 store thread 300개와 열린 파일 300개 이상이 생깁니다.
같은 category가 두 `<store>`에 걸려 있으면(예: `categories=` 목록과 `category=` 직접 설정) 그 category의 thread는 2개입니다.
category가 많다면 thread·파일·연결 수를 감안하세요.
값을 `no`로 바꾸면 출력 위치가 바뀌므로 기존 설정의 값을 함부로 바꾸지 마세요.

### buffer secondary의 add_newlines는 재전송 때 줄바꿈을 하나 더 만든다

`add_newlines=1`인 file store는 메시지마다 LF 하나를 붙여 씁니다.
buffer의 secondary(spool, 기본값 `replay_buffer=yes`)에 `add_newlines=1`을 두면 **LF가 frame 안에 함께 저장**됩니다.
재전송할 때 spool은 frame 내용 그대로 `메시지\n`을 돌려줍니다.

그래서 받는 쪽 file store에도 `add_newlines=1`이 있으면 `메시지\n\n`이 저장됩니다.
장애가 없어 spool을 거치지 않은 로그는 `메시지\n`이므로, **같은 로그가 spool을 거쳤는지에 따라 바이트가 달라집니다.**

```conf
<store>
  category=game_login
  type=buffer

  <primary>
    type=network
    remote_host=relay-a.example
    remote_port=1463
  </primary>

  <secondary>
    type=file
    fs_type=std
    file_path=/var/log/scribed/spool
    base_filename=game_login
    add_newlines=1
  </secondary>
</store>
```

받는 서버(`relay-a.example`)의 file store가 `add_newlines=1`이고 메시지가 `login ok`(8 bytes)일 때:

```text
장애 없이 바로 전송:     받는 쪽 파일  6c 6f 67 69 6e 20 6f 6b 0a          "login ok\n"
spool에 저장된 frame:                09 00 00 00 6c 6f 67 69 6e 20 6f 6b 0a  (길이 9, LF 포함)
재전송 후 받는 쪽 파일:              6c 6f 67 69 6e 20 6f 6b 0a 0a       "login ok\n\n"
```

**primary에만 `add_newlines=1`을 두고 secondary에는 두지 않으면** 원본 [`examples/example1.conf`](examples/example1.conf)와 같은 방식이 됩니다.
이때 spool frame은 `08 00 00 00 6c 6f 67 69 6e 20 6f 6b`이고, 재전송 후에도 `login ok\n` 하나만 저장됩니다.
다만 운영 중인 설정을 바꾸면 이미 쌓인 spool의 LF는 그대로이고 이후 바이트가 달라지므로 다운스트림 영향을 먼저 확인하세요.

### spool 파일 하나가 Log 요청 하나로 재전송된다

buffer store는 재전송할 때 **가장 오래된 spool 파일 하나를 통째로 읽어 Log 요청 하나**로 보냅니다.
`check_interval`마다 `buffer_send_rate`(기본 1)개 파일을 보냅니다.
따라서 secondary `max_size`가 재전송 요청 하나의 크기를 정합니다.

- 요청 크기가 [256 MiB 한도](#통신-크기-제한과-확인한-호환성)를 넘으면 그 파일과 뒤의 파일이 모두 멈춥니다.
- 받는 서버는 요청을 큐에 넣기 **전에** 큐 크기를 검사하므로 큰 요청 하나는 받아들입니다.
  - 하지만 그 요청이 들어간 category의 store queue는 store thread가 가져갈 때까지 `max_queue_size`를 넘은 상태가 됩니다.
  - store thread가 앞 batch를 처리하느라 바쁘면 그동안 모든 클라이언트가 `TRY_LATER`[^28]를 받습니다([max_queue_size는 모든 category를 한꺼번에 본다](#max_queue_size는-모든-category를-한꺼번에-본다)).
  - 받는 서버의 `max_queue_size`는 보내는 쪽 secondary `max_size`보다 넉넉히 크게 잡으세요.

```conf
# 보내는 서버: secondary max_size=134217728 (128 MiB)
# 받는 서버가 기본 max_queue_size=5000000(약 4.8 MiB)이면 재전송 요청 하나만으로 큐가 한도를 넘습니다.
# 받는 서버 최상위 설정 예:
max_queue_size=268435456
```

### max_queue_size는 모든 category를 한꺼번에 본다

`max_queue_size`(기본 5,000,000 bytes)는 store queue 하나에 쌓여 아직 store thread가 가져가지 않은 메시지 내용의 byte 수 한도입니다.
서버는 Log 요청을 큐에 넣기 전에 **모든 category의 모든 store queue**를 검사합니다.
어느 하나라도 한도를 넘으면 요청에 든 category와 상관없이 **요청 전체에 `TRY_LATER`를 돌려줍니다.**
한 요청은 모두 성공하거나 모두 실패하기 위해서입니다.

예: `game_replay`의 store가 느려(예: 다음 서버의 응답이 늦음) 큐가 5,000,000 bytes를 넘으면 `game_login`만 보내는 클라이언트도 `TRY_LATER`를 받습니다.
이때 `game_replay:denied for queue size`와 `scribe_overall:denied for queue size` 카운터가 늘어납니다.
클라이언트는 `TRY_LATER`를 받으면 다시 보내야 합니다.

### max_msg_per_second와 절반 예외

`max_msg_per_second`는 1초에 받을 메시지 수 한도입니다.
기본값 0은 제한 없음입니다.
한도를 넘으면 요청 전체에 `TRY_LATER`를 돌려주고 `scribe_overall:denied for rate` 카운터가 늘어납니다.

단, **한 요청의 메시지 수가 한도의 절반보다 많으면 항상 받아들이고 그 초의 개수에도 세지 않습니다.**
큰 요청을 계속 거절하면 그 요청은 영원히 들어올 수 없기 때문입니다.

```conf
max_msg_per_second=1000
```

| 같은 1초 안의 요청 | 결과 |
| --- | --- |
| 메시지 100개짜리 요청 10개 | 모두 받음(합계 1000) |
| 그다음 100개짜리 요청 | `TRY_LATER` |
| 600개짜리 요청(절반 500보다 많음) | 항상 받고 합계에 더하지 않음 |

**구·신 차이.** 구버전은 동시에 들어온 요청들이 이 개수를 잠금 없이 고쳐서 한도보다 많이 받아들일 수 있었습니다.
신버전은 이 계산만 별도 잠금 아래에서 하므로 동시 요청도 정확히 셉니다.
요청이 하나씩 들어오면 결과는 같습니다.

### rotate_period 형식과 파일 이름

| `rotate_period` 값 | 의미 | 파일 이름 예(`base_filename=game_login`, 2026-10-07) |
| --- | --- | --- |
| `never`(기본값) | 시간으로 회전하지 않음 | `game_login_00000` |
| `hourly` | 매시 `rotate_minute`(기본 15)분 이후 첫 검사 때 | `game_login-2026-10-07_00013`(그날 파일 없이 13시에 시작한 경우) |
| `daily` | 매일 `rotate_hour`(기본 1)시 `rotate_minute`(기본 15)분 이후 첫 검사 때 | `game_login-2026-10-07_00000` |
| `30m`, `1h`, `2d`, `1w`, `3600`, `3600s` | 파일을 연 뒤 N초·분·시간·일·주가 지나면(숫자만 쓰면 초) | `game_login-2026-10-07_00000` |
| 그 밖의 값(예: `1x`, `0h`, `1hh`) | 경고 로그 후 시간 회전을 끔 | `game_login_00000` |

- 이름은 `<base_filename>-YYYY-MM-DD_NNNNN` 형식입니다.
  - 날짜는 daemon의 지역 시간(TZ)이며, `never`이면 날짜가 붙지 않습니다.
- 크기 회전(`max_size`, file store 기본 1,000,000,000 bytes, 0이면 제한 없음)은 모든 형식에서 동작하며 번호 `NNNNN`을 하나씩 올립니다.
  - 날짜가 바뀐 뒤 첫 회전은 `_00000`부터 시작합니다.
- `hourly`로 시작할 때 그날 파일이 없으면 첫 번호가 현재 시(예: 13시 → `_00013`)입니다.
- `<base_filename>_current`는 가장 최근 파일을 가리키는 symlink이며 이름에 날짜가 붙지 않습니다.
  - `base_symlink_name`으로 바꿀 수 있고, `create_symlink=no`이면 만들지 않습니다.
- buffer의 secondary(spool) 파일은(기본값 `replay_buffer=yes`일 때) 항상 `never`로 동작하고 symlink를 만들지 않습니다.
  - 예: `game_login_00000`, `game_login_00001`, …
- 회전 검사는 `check_interval`마다 하므로 실제 회전 시각은 그만큼 늦을 수 있습니다.

### 주석 기호 #은 줄 어디에서나 동작한다

설정 파일에서 `#`은 줄의 맨 앞이 아니어도 **그 뒤를 모두 주석으로 지웁니다.**
그래서 값 안에 `#`을 쓸 수 없습니다.
앞뒤 공백과 탭은 지워집니다.

```text
설정 파일에 쓴 줄                      서버가 읽는 값
max_size=1000000   # 1 MB              max_size=1000000
file_path=/var/log/scribed/game#1      file_path=/var/log/scribed/game
```

### use_conn_pool은 host와 port마다 TCP 연결 하나를 공유한다

`use_conn_pool=yes`이면 같은 `host:port`로 보내는 network store들이 **TCP 연결 하나**를 함께 쓰고, 한 번에 한 store씩 보냅니다.
기본값 `no`에서는 store(복사본 포함)마다 자기 연결을 엽니다.
key는 설정에 쓴 문자열 그대로라서 `relay-a.example:1463`과 그 서버의 IP로 쓴 값은 서로 다른 연결입니다.
`service_list`는 [빈 key를 공유](#service_list와-use_conn_pool은-빈-연결-key-하나를-같이-쓴다)합니다.

```conf
# 두 category가 relay-a.example:1463 연결 하나를 같이 씁니다.
<store>
  category=game_login
  type=network
  remote_host=relay-a.example
  remote_port=1463
  use_conn_pool=yes
</store>
<store>
  category=game_purchase
  type=network
  remote_host=relay-a.example
  remote_port=1463
  use_conn_pool=yes
</store>
```

### 설정 파일의 port가 -p보다 우선한다

설정 파일에 `port`가 있으면 명령행 `-p`보다 우선합니다.

```sh
# 설정 파일에 port=1463이 있으면 1464가 아니라 1463에서 받습니다.
scribed -c /etc/scribed/scribed.conf -p 1464
# 로그: port 1463 from conf file overriding old port 1464
```

port는 시작할 때만 정해지며 fb303 `reinitialize`로 바뀌지 않습니다.
`port`와 `-p`가 모두 없으면 `No port number configured` 설정 오류입니다.

### check_interval이 회전 검사와 재시도 주기를 정한다

`check_interval`(기본 5초, 0이면 1초)마다 각 store가 주기 작업을 합니다.
시간 기반 회전 검사, buffer의 primary 재연결 시도와 spool 재전송(`buffer_send_rate`개 파일), 동적 목적지 확인이 모두 이 주기를 따릅니다.
그래서 실제 간격은 설정값보다 길어질 수 있습니다.

```conf
check_interval=5
<store>
  category=game_login
  type=buffer
  retry_interval=10
  retry_interval_range=0
  ...
</store>
```

위 설정에서 재연결은 "마지막 시도 후 10초 초과" 조건을 5초마다 검사하므로 실제로는 약 15초마다 시도합니다(`check_interval=1`이면 약 11초).

### 시작에 실패해도 종료 코드는 0이다

`scribed`는 시작에 실패해도 **종료 코드 0**으로 끝납니다.
예를 들어 port가 이미 쓰이고 있거나, `thrift_max_frame_size=256M`처럼 잘못된 한도를 주면 `Exception in main: ...` 로그를 남기고 0으로 종료합니다.

반대로 store 설정이 잘못되면 프로세스는 계속 떠 있지만 fb303 상태가 `WARNING`입니다.
그래서 서비스 관리자의 "실패 시 재시작" 조건이나 종료 코드만으로는 이상을 알 수 없습니다.
**fb303 `getStatus`(`ALIVE`/`WARNING`)·`getStatusDetails`·카운터, 열린 port, 실제 저장 파일로 감시하세요.**

### 빈 메시지가 든 spool은 재전송이 중간에 멈출 수 있다

secondary에 `add_newlines`가 없을 때 빈 메시지는 길이 0인 frame(`00 00 00 00`)으로 저장됩니다.
재전송할 때 spool reader는 길이 0인 frame을 **파일 끝으로 여겨 읽기를 멈추고**, 그때까지 읽은 메시지를 보낸 뒤 파일을 지웁니다.
그 뒤의 메시지는 전달되지 않는데 `lost`·`bytes lost` 카운터는 늘지 않습니다.

`add_newlines=1`이면 빈 메시지가 `0a` 한 byte로 저장되어 이 문제는 없지만 [줄바꿈이 하나 더 생깁니다](#buffer-secondary의-add_newlines는-재전송-때-줄바꿈을-하나-더-만든다).
근거는 [FileStore 계약 기록](docs/filestore-contracts-status.md)에 있습니다.

```text
장애 중 spool에 쌓인 메시지 "a", "", "b" (add_newlines 없음)
  01 00 00 00 61 | 00 00 00 00 | 01 00 00 00 62
재전송: "a"만 보내고 파일 삭제. "b"는 전달되지 않음
```

### 그 밖의 주의점

- 원본 설정 파서는 잘못된 설정을 모두 거부하지 않습니다.
  - 동적 설정 오류 뒤 기본 목적지로 전송하거나 준비되지 않은 store에도 listener와 `OK` 응답이 생길 수 있습니다.
- 정의하지 않은 category의 로그는 버려지고 `received bad` 카운터가 늘어납니다.
  - 빈 category는 `received blank category`로 셉니다.
- 공개 원본의 서비스 이름 조회는 항상 실패하는 예제 구현입니다.
  - `smc_service`만으로 실제 service discovery가 제공된다고 가정하지 마세요.
- `_current`는 일반 파일 저장에서는 symlink이지만 HDFS에서는 경로를 담은 일반 marker 파일입니다.
- 원본 HDFS의 Scribe 파일 읽기 메서드(`readNext`/`getFrame`)와 닫힌 파일의 truncate에는 제한이 남습니다.
  - HDFS 저장 확인을 일반 spool 파일의 재전송 지원으로 해석하지 마세요.
- 새로운 Thrift의 thread 구현과 라이브러리 ABI가 다르므로 stack 크기와 운영 성능까지 같다고 가정하지 마세요.

## 업데이트와 되돌리기

운영 배포와 실제 복구 절차를 검증한 것은 아닙니다.
전환 전에 다음을 준비하세요.

1. 이전 실행 파일, 의존성 라이브러리, 설정과 검증 기록을 한 묶음으로 보관합니다
2. 기존 writer를 종료한 뒤 데이터와 spool 파일을 보존합니다
3. 구·신 서버가 같은 파일에 동시에 쓰지 않도록 합니다
4. 별도 폴더에서 작은 로그의 전송·읽기·상태를 확인한 뒤 전환을 결정합니다

실행 파일만 되돌려도 이미 손실된 메시지가 복구되거나 저장 파일 형식이 바뀌지는 않습니다.
특히 이전 개발 버전이 만든 raw 형식 복사본 파일은 현재 버전이 자동으로 변환하지 않습니다.
[ThriftFile 복사본의 형식 주의점](#thriftfile-복사본은-use_simple_file을-무시한다)을 확인하세요.

구버전으로 되돌리면 [고친 문제](#고친-문제)의 전송·연결 수정 세 가지도 원본 동작(예: 재전송 일부 성공 시 손실)으로 돌아옵니다.
신버전이 다시 쓴 spool 파일도 같은 frame 형식입니다.

## 관련 문서

| 문서 | 내용 |
| --- | --- |
| [빌드 안내](docs/linux-build-mvp.md) | 의존성 경로, 빌드·임시 설치와 지원 범위 |
| [호환성 정책](docs/legacy-compatibility-policy.md) | 원본 동작을 유지하기로 한 결정과 남는 버그, [2026-10-07에 다시 고친 동작](docs/legacy-compatibility-policy.md#다시-고친-동작-2026-10-07) |
| [실제 구·신 서버 비교](docs/daemon-differential.md) | 전송, 저장, 재시작, 게임 서버 설정 기능 profile(`--case game-profile`)과 시험 방법 |
| [구버전 비교 환경](tools/old-lane/README.md) | 구버전 daemon 재현 빌드와 구·신 비교를 다시 실행하는 세 명령 |
| [FileStore 계약 기록](docs/filestore-contracts-status.md) | 일반 spool의 byte 형식, 재전송과 기존 손실 경로 |
| [HDFS 안내](docs/hdfs-compatibility.md) | 선택 기능의 빌드·실행 범위와 제한 |
| [Docker 안내](docs/docker.md) | 이미지 빌드·실행, 시험 메시지 보내기, fb303 `shutdown`으로 정지 |
| [Rocky 빌드](docs/rocky-build.md) / [Rocky RPM](docs/rocky-rpm.md) / [Rocky HDFS](docs/rocky-hdfs.md) | Rocky 8.10/9.8의 빌드·RPM·HDFS 확인 범위 |
| [Python 설치 기록](docs/python-packaging-status.md) | 설치 경로와 생성 client의 지원 범위 |
| [첫 버전의 지원 범위](docs/first-modern-version.md) | 확인한 기능과 아직 확인하지 않은 사항 |
| [설계](docs/design.ko.md) / [구현 계획](docs/implementation.ko.md) | 원본 구조와 개발 방향 |
| [개발 지침](AGENTS.md) | 코드 변경과 검증 시 지킬 규칙 |

세부 실행 결과와 과거 단계별 기록은 관련 문서와 보관된 원시 결과를 참고하세요.
README에는 실행 이력을 모두 나열하지 않습니다.

## 라이선스

[Apache License 2.0](LICENSE)을 따릅니다.
원본 Facebook Scribe의 저작권과 고지를 보존합니다.

재배포할 때는 LICENSE, 변경 파일의 수정 고지와 필요한 원본 고지를 포함해야 합니다.
의존성 라이브러리도 함께 배포한다면 각 라이브러리의 LICENSE/NOTICE를 따로 확인하세요.
현재 빌드·임시 설치 검사가 완성된 배포 패키지나 의존성 고지 목록을 대신하지는 않습니다.

## 각주

처음 나오는 용어를 쉽게 풀어 쓴 설명입니다.

[^1]: C++17: 2017년에 정해진 C++ 언어 표준입니다.
  컴파일러에 `-std=c++17`을 주면 이 표준으로 빌드합니다.
[^2]: drop-in 대체: 기존 프로그램을 빼고 그 자리에 새 프로그램을 넣어도 주변 설정이나 다른 프로그램을 고치지 않고 그대로 동작하는 것을 말합니다.
[^3]: Thrift: 서버와 클라이언트가 주고받는 데이터 형식과 함수를 정의하고, 여러 언어용 통신 코드를 자동으로 만들어 주는 라이브러리입니다.
  Scribe는 로그를 Thrift로 주고받습니다.
[^4]: IDL(Interface Definition Language): 서버가 제공하는 함수와 데이터 구조를 언어와 상관없이 적어 둔 정의 파일입니다.
  이 파일의 field 번호나 이름이 바뀌면 구·신 프로그램이 서로 통신할 수 없습니다.
[^5]: framed binary: 요청마다 앞에 4-byte 길이를 붙이고(framed), 내용은 Thrift의 이진 형식(binary)으로 보내는 통신 방식입니다.
  양쪽이 같은 방식을 써야 통신됩니다.
[^6]: fb303: Facebook이 만든 서버 상태 조회 규약입니다.
  상태(`ALIVE`, `WARNING` 등), 상세 설명, 카운터를 원격으로 읽고 `reinitialize`·`shutdown` 같은 명령을 보낼 수 있습니다.
[^7]: spool: 다음 서버로 보내지 못한 로그를 잠시 디스크에 모아 두는 파일입니다.
  Scribe에서는 buffer store의 secondary가 이 역할을 하며, 상대가 살아나면 다시 보냅니다.
[^8]: fsync: 운영체제 메모리에 있는 파일 내용을 디스크에 실제로 기록하도록 강제하는 호출입니다.
  `flush`는 프로그램 버퍼를 운영체제로 넘길 뿐이라 전원이 꺼지면 내용이 사라질 수 있습니다.
[^9]: category: 로그의 종류를 나타내는 이름입니다(예: `game_login`).
  Scribe는 category를 보고 어느 store로 보낼지 정합니다.
[^10]: store: 설정 파일의 `<store>` 블록으로 정하는 로그 처리 단위입니다.
  파일에 쓰기(`file`), 다른 서버로 보내기(`network`), 실패하면 디스크에 모았다가 다시 보내기(`buffer`) 등의 종류가 있습니다.
[^11]: symlink(심볼릭 링크): 다른 파일을 가리키는 바로가기 파일입니다.
  Scribe는 `<이름>_current`라는 symlink로 지금 쓰고 있는 파일을 가리킵니다.
[^12]: Boost: C++에서 널리 쓰는 공개 라이브러리 모음입니다.
  scribed는 Boost를 쓰지 않지만, Thrift 0.25.0이 빌드할 때와 그 header가 Boost header를 요구합니다.
[^13]: libevent: 많은 네트워크 연결을 적은 thread로 처리하도록 도와주는 C 라이브러리입니다.
  Thrift의 비동기 서버가 사용합니다.
[^14]: autotools: `configure` 스크립트와 `Makefile`을 만들어 주는 전통적인 빌드 도구 묶음(autoconf, automake, libtool)입니다.
[^15]: RPC(Remote Procedure Call): 다른 서버의 함수를 네트워크로 호출하는 것입니다.
  Scribe에서는 로그를 보내는 `Log` 호출 하나가 RPC 하나입니다.
[^16]: HDFS: Hadoop의 분산 파일 시스템입니다.
  Scribe는 선택 기능으로 로그를 HDFS에 직접 쓸 수 있습니다(`fs_type=hdfs`).
[^17]: MiB: 1 MiB는 1,048,576 bytes(2의 20제곱)입니다.
  256 MiB는 268,435,456 bytes입니다.
[^18]: batch: 여러 메시지를 한 번에 묶어 처리하거나 보내는 단위입니다.
[^19]: UB(Undefined Behavior, 정의되지 않은 동작): C/C++ 표준이 결과를 정하지 않은 동작입니다.
  실행할 때마다 결과가 다르거나 비정상 종료할 수 있어, 원본과 "같은 결과"를 재현할 수 없습니다.
[^20]: jitter: 여러 서버가 같은 순간에 몰려 재시도하지 않도록 재시도 시간에 더하는 작은 랜덤 값입니다.
[^21]: refcount(참조 수): 하나의 자원(여기서는 TCP 연결)을 몇 곳에서 쓰고 있는지 세는 숫자입니다.
  0이 되면 아무도 쓰지 않는다고 보고 자원을 닫습니다.
[^22]: failover: 연결하려던 서버가 응답하지 않을 때 목록의 다른 서버로 넘어가는 것입니다.
[^23]: LF(Line Feed): 줄바꿈 문자 `\n`, byte 값 `0x0a`입니다.
[^24]: little-endian: 여러 byte로 된 숫자를 작은 자리부터 저장하는 방식입니다.
  길이 9는 `09 00 00 00`으로 저장됩니다.
[^25]: RAII: 자원(잠금, 메모리 등)을 객체가 만들어질 때 얻고 객체가 사라질 때 자동으로 돌려주는 C++ 방식입니다.
  중간에 예외가 나도 자원이 풀립니다.
[^26]: weak_ptr: 객체를 가리키기만 하고 수명은 붙잡지 않는 C++ 스마트 포인터입니다.
  서로를 붙잡아 영원히 해제되지 않는 순환을 끊을 때 씁니다.
[^27]: mutex: 여러 thread가 같은 데이터를 동시에 고치지 못하도록 한 번에 하나만 들어가게 하는 잠금입니다.
[^28]: TRY_LATER: Scribe의 `Log` 호출이 돌려주는 결과 값 중 하나로, "지금은 받을 수 없으니 나중에 다시 보내라"는 뜻입니다.
  이 요청의 메시지는 하나도 저장되지 않았습니다.
