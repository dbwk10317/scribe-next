# scribe-next

**Facebook Scribe 로그 수집 서버(`scribed`)를 지금의 Linux에서 빌드할 수 있게 옮긴 대체판입니다.**
기존 서버의 `scribed` 실행 파일만 바꿔 끼우고, 설정·클라이언트·로그를 읽는 프로그램은 그대로 두는 것이 목표입니다(drop-in[^dropin]).

- 실행 파일 이름, 설정 파일, 통신 방식, 저장 파일 형식, 상태 조회 방법이 원본과 같습니다.
- 구버전과 신버전을 섞어 써도 됩니다. 구 → 신, 신 → 구 어느 방향으로도 로그가 전달됩니다.
- 구버전이 남긴 spool[^spool] 파일을 신버전이 이어서 보내고, 그 반대도 됩니다.
- 새 `scribed`는 Thrift 0.25.0 공유 라이브러리 두 개가 함께 있어야 합니다([설치](#설치)).

> [!NOTE]
> 구버전과 신버전을 섞어 쓰는 전송, 장애 뒤 재전송, 파일 읽기를 실제 서버 두 대를 띄워 비교했습니다.
> 결과와 범위는 [테스트 결과](#테스트-결과)에 있습니다.
> 모든 설정과 모든 장애 상황에서 똑같다는 뜻은 아닙니다.

## 목차

- [개요](#개요)
- [설치](#설치)
  - [원래 Scribe 방식](#원래-scribe-방식)
  - [Docker 방식](#docker-방식)
- [실행](#실행)
- [테스트 결과](#테스트-결과)
- [원래 버전에서 달라진 점](#원래-버전에서-달라진-점)
  - [빌드와 의존성](#빌드와-의존성)
  - [고친 원래 버그](#고친-원래-버그)
  - [코드 정리](#코드-정리)
  - [새 설정 키](#새-설정-키)
- [일부러 남겨 둔 원래 버그](#일부러-남겨-둔-원래-버그)
- [관련 문서](#관련-문서)
- [라이선스](#라이선스)

## 개요

### scribe-next는 무엇인가

- **Scribe란.**
  여러 서버의 로그를 받아 파일로 저장하거나 다른 Scribe 서버로 넘기는 로그 수집 서버입니다.
  Facebook이 2008년에 공개했고, 원본 저장소는 지금 보관(archived) 상태라 더 이상 관리되지 않습니다.
- **scribe-next란.**
  그 [공개 원본](https://github.com/facebookarchive/scribe/tree/fcd294faffd1e88af1643a3a8c2359c41713f7c2)을 지금의 Linux에서 빌드하고 실행할 수 있게 옮긴 프로젝트입니다.
  새로 설계한 로그 서버가 아닙니다. 원본 구조를 그대로 두고, 빌드와 바깥 경계에 필요한 부분만 고친 이식판입니다.
- **이 문서의 용어.**
  - **구버전**: 공개 원본의 마지막 버전을 당시의 Thrift/fb303 0.9.0으로 빌드한 서버입니다.
  - **신버전**: 이 저장소에서 빌드한 서버입니다.

### 왜 다시 만들었나

- **원본은 지금의 Linux에서 그대로 빌드되지 않습니다.**
  - 원본은 Thrift[^thrift] 0.5~0.9 시절의 API로 작성됐고, 지금의 Thrift는 그 API를 크게 바꿨습니다.
  - 원본이 쓰던 라이브러리 함수 일부가 없어지거나 모양이 바뀌었습니다(예: HDFS 라이브러리의 파일 삭제 함수).
  - 컴파일러도 달라졌습니다. 구버전을 비교용으로 빌드할 때도 Ubuntu 16.04와 GCC 5.4라는 옛 환경을 따로 만들어야 했습니다.
- **그래서 무엇을 바꿨나.**
  빌드 방법과 바깥 경계(통신 라이브러리, 파일 시스템 함수 등)의 코드를 새로 맞췄습니다.
- **그래서 무엇을 안 바꿨나.**
  로그를 나누고, 저장하고, 전달하는 방식은 원본 그대로입니다.

### 바깥에서 보면 원본과 같습니다

| 원본과 같은 것 | 내용 |
| --- | --- |
| 실행 파일 | 이름 `scribed`, 옵션 `-c 설정파일`, `-p 포트` |
| 설정 파일 | `<store>` 블록과 `key=value` 형식, 설정 이름과 기본값 |
| 통신 | Thrift framed binary[^framed], 같은 요청·응답 형식 |
| 저장 파일 | 파일 이름, 회전 규칙, `_current` 표시, spool 형식 |
| 상태 조회 | fb303[^fb303] 상태·카운터 API |

- **그래서 가능한 것.**
  1. 기존 설정 파일을 고치지 않고 그대로 읽습니다.
  2. 기존 클라이언트를 업그레이드하지 않아도 로그를 보낼 수 있습니다.
  3. 구버전 → 신버전, 신버전 → 구버전 어느 방향으로도 로그를 넘길 수 있습니다. 그래서 여러 대를 한 대씩 바꿔 끼울 수 있습니다.
  4. 같은 입력이면 같은 이름의 파일에 같은 바이트로 저장되고, 카운터 이름도 같습니다.
- **4번을 지키려고 한 일.**
  - 로그 결과(어느 파일에 무엇이 저장되고 어디로 전달되는가)를 바꾸는 원본 버그는 [일부러 남겨 두었습니다](#일부러-남겨-둔-원래-버그).
  - 반대로 비정상 종료처럼 "원본과 같은 결과"가 없는 문제는 [안전하게 고쳤습니다](#고친-원래-버그).
  - 예외로 고친 세 가지(연결 pool을 닫는 순서, `service_list` 재연결 후보, 파일 재전송의 일부 실패)는 분배와 파일 형식은 같지만, 원본이 버리던 로그가 전달되거나 다시 시도됩니다. 그 조건에서는 전달 결과와 `lost`·`requeue` 카운터 값이 원본과 달라집니다.
  - 2026-10-08에는 사용자 승인을 받아 운영 경계 세 가지를 바꿨습니다. SIGTERM·SIGINT는 `shutdown`처럼 정리한 뒤 끝나고, 시작에 실패하면 종료 코드 1이며, 동적 category 이름의 `..` 조각은 거부합니다([고친 원래 버그](#고친-원래-버그)).
- **확인하지 않은 것.**
  사용 중인 모든 언어·Thrift 버전의 클라이언트 조합을 검증한 것은 아닙니다.

> [!IMPORTANT]
> 서버가 돌려주는 `OK`는 로그를 **메모리 큐에 받았다**는 뜻일 뿐입니다([자세히](docs/behaviour.md#ok는-메모리-큐에-받았다는-뜻이다)).

### 확인한 환경

- **서버 실행 환경.** Linux x86_64만 확인했습니다. Mac과 Windows는 확인하지 않았습니다.
- **설치 명령.** Ubuntu 24.04와 Rocky Linux 9용입니다. 배포판·컴파일러별 확인 범위는 [빌드 안내](docs/build.md#확인한-환경)에 있습니다.
- **선택 기능.** HDFS[^hdfs] 저장, 공유 RPC 라이브러리[^rpc], Rocky용 개발 RPM은 선택 기능이며 확인 범위가 따로 있습니다.
  각각 [HDFS 안내](docs/hdfs.md), [빌드 안내](docs/build.md#shared-rpc), [Rocky RPM](docs/build.md#rocky-개발-rpm)을 보세요.

## 설치

두 가지 방법이 있습니다.

- [원래 Scribe 방식](#원래-scribe-방식): 소스에서 `bootstrap.sh` → `make` → `make install`로 설치합니다.
- [Docker 방식](#docker-방식): 원본에는 없던 방법으로, 이미지 하나로 `scribed`를 실행합니다.

### 원래 Scribe 방식

원본 Scribe와 같은 `bootstrap.sh` → `make` → `make install` 흐름입니다.

- 0단계의 한 줄과 배포판에 맞는 1단계 블록 하나를 실행합니다.
- 그다음 2~5단계를 위에서부터 복사해 붙여 넣으면 됩니다.
- 6단계는 설치한 것을 지우는 방법입니다.

#### 0. 미리 알아둘 것

- **Thrift 0.25.0은 소스에서 빌드합니다.**
  두 배포판 모두 맞는 패키지가 없습니다.
  Thrift는 `thrift` 코드 생성기(compiler)와 `scribed`가 쓰는 통신 라이브러리를 함께 제공합니다.
- **fb303도 같은 Thrift 소스에서 빌드합니다.**
  이 프로젝트의 patch를 적용해 빌드합니다. 이 patch는 카운터 잠금이 풀리지 않던 문제를 막습니다([자세히](#thrift-025와-fb303)).
- **설치 위치는 `/usr/local`입니다.**
  Python client package만 예외입니다([4단계](#4-scribe-next-빌드와-설치-공통)).
  원본 Scribe도 `/usr/local`을 기본값으로 가정했으므로, 아래 `--with-*path` 옵션은 이를 명시할 뿐입니다.
- **저장소를 따로 받지 않습니다.**
  이 README가 들어 있는 폴더가 곧 scribe-next 저장소이며, 그대로 빌드합니다.
  아래 명령은 그 폴더를 `$SCRIBE_SRC`로 기억해 두고 씁니다. 저장소 폴더에서 다음을 실행합니다.

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
sudo apt-get install -y git curl build-essential autoconf automake libtool pkg-config cmake bison flex \
  libevent-dev libboost-dev python3 python3-setuptools
```

#### 1-B. Rocky Linux 9 패키지 (RHEL 계열)

```sh
sudo dnf -y install git gcc gcc-c++ make cmake autoconf automake libtool bison flex \
  libevent-devel boost-devel python3 python3-setuptools
echo /usr/local/lib | sudo tee /etc/ld.so.conf.d/scribe-local.conf
```

- **`boost-devel`을 설치하는 이유.**
  Rocky에는 Boost header만 담은 패키지가 없습니다. 함께 설치되는 Boost 라이브러리는 `scribed`가 쓰지 않습니다.
- **마지막 줄의 뜻.**
  공유 라이브러리를 찾는 경로에 `/usr/local/lib`을 추가합니다. Ubuntu는 이 경로를 기본으로 찾지만 Rocky는 찾지 않습니다.
- **Rocky 8에서는 이 설치 명령을 실행하지 않았습니다.**
  Rocky 8.10은 Docker 검증 이미지에서 검증기와 개발 RPM만 확인했습니다([확인한 환경](docs/build.md#확인한-환경)).
  배포판의 bison 3.0.4로는 Thrift가 빌드되지 않아 bison 3.8.2가 필요하고, 기본 `python3`(3.6)로는 준비 스크립트가 동작하지 않아 Python 3.9 이상이 필요합니다.
  bison을 준비하는 방법은 [Rocky 빌드 안내](docs/build.md#rocky-linux-8과-9)에 있습니다.
- **Boost header가 필요한 이유.**
  Thrift와 fb303의 header가 Boost[^boost] header를 불러옵니다.
  `scribed` 자체는 Boost 라이브러리를 링크하지 않으므로, 실행만 하는 컴퓨터에는 Boost가 필요 없습니다.

#### 2. Thrift 0.25.0 빌드와 설치 (공통)

Apache 배포 서버에서 Thrift 0.25.0 소스를 받아 checksum을 확인한 뒤, compiler와 C++ 라이브러리만 빌드해 `/usr/local`에 설치합니다.

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

- `sha256sum -c`가 `OK`를 출력하지 않으면 받은 파일이 다른 것이므로 진행하지 마세요.
- 마지막 `sudo ldconfig`는 새로 설치한 공유 라이브러리를 시스템이 찾도록 목록을 갱신합니다.
- 이후 단계도 같은 `~/scribe-build` 폴더에서 진행합니다.

#### 3. fb303 빌드·설치 (공통)

Thrift 소스에 든 fb303에 이 저장소의 patch를 적용해 `fb303-build` 폴더를 만들고, 빌드한 뒤 `/usr/local`에 설치합니다.

```sh
cd ~/scribe-build
python3 "$SCRIBE_SRC/tools/prepare_fb303.py" --source thrift-0.25.0/contrib/fb303 --output fb303-build
cd fb303-build
aclocal -I ./aclocal && automake -a --copy && autoconf
./configure --prefix=/usr/local --with-thriftpath=/usr/local --with-boost=/usr \
  --without-java --without-php --without-python
make -j"$(nproc)" CXXFLAGS='-O2 -std=c++17' CPPFLAGS='-I/usr/local/include'
sudo make install
```

#### 4. scribe-next 빌드와 설치 (공통)

원본과 같은 순서입니다.
`bootstrap.sh`는 빌드 설정(configure)을 만들고 실행하며, 넘긴 옵션은 그대로 configure에 전달됩니다.

```sh
cd "$SCRIBE_SRC"
./bootstrap.sh --prefix=/usr/local --with-thriftpath=/usr/local --with-fb303path=/usr/local
make -j"$(nproc)"
sudo make install
```

- **설치되는 것.**
  - `scribed`는 `/usr/local/bin`에, 정적 RPC 라이브러리는 `/usr/local/lib`에 들어갑니다.
  - IDL에서 만든 Python 3용 client package `scribe`도 `PY_PREFIX`(기본값 `/usr`) 아래의 시스템 Python 경로에 함께 설치됩니다.
    daemon을 실행하는 데는 Python client가 필요하지 않습니다.
- **이름이 같은 `scribe` package가 이미 있다면.**
  예를 들어 원본의 Python 2 client가 있는 시스템이라면, 덮어쓰지 않도록 다른 `PY_PREFIX`를 주세요.
  위 `./bootstrap.sh` 줄 끝에 `PY_PREFIX=/opt/scribe-python`처럼 더하면 됩니다.
- **Python client를 쓸 때.**
  위 순서만으로는 Python client를 바로 쓸 수 없습니다(Thrift·fb303 Python module이 따로 필요). 자세한 것은 [빌드 안내](docs/build.md#python-client)에 있습니다.
- **그 밖의 설정.**
  공유 라이브러리 경로와 HDFS 빌드 설정은 [빌드 안내](docs/build.md)와 [HDFS 안내](docs/hdfs.md)에 있습니다.

#### 5. 설치 확인

설치한 `scribed`가 실행되는지, `/usr/local/lib`의 Thrift 라이브러리를 찾는지 확인합니다.

```sh
scribed --help
ldd "$(command -v scribed)"
```

- `scribed --help`는 사용법 줄 `Usage: scribed [-p port] [-c config_file]`을 출력해야 합니다.
- `ldd` 결과에는 `/usr/local/lib`의 `libthrift.so.0.25.0`, `libthriftnb.so.0.25.0`과 배포판의 libevent가 보여야 합니다.
- Boost 라이브러리(`libboost_*`)는 보이지 않아야 합니다.
- 실행 파일에 모든 라이브러리를 넣는 빌드가 아니므로, 실행할 때도 이 라이브러리들을 찾을 수 있어야 합니다.

#### 6. 삭제

위 순서로 설치한 것을 모두 지우는 방법입니다.

- 빌드할 때 쓴 폴더(`$SCRIBE_SRC`, `~/scribe-build`)의 `make uninstall`과 Thrift의 설치 목록(`install_manifest.txt`)을 쓰므로, 그 폴더가 남아 있어야 합니다.
- `scribed`를 먼저 멈춘 뒤([실행의 정지](#4-정지)) 실행합니다.
- [systemd 서비스](#5-systemd-서비스로-등록)로 등록했다면 먼저 서비스와 그 파일을 지웁니다.
  `/var/log/scribed`에는 받은 로그가 들어 있으니 필요하면 옮긴 뒤 지우세요.

```sh
sudo systemctl disable --now scribed
sudo rm -f /etc/systemd/system/scribed.service
sudo systemctl daemon-reload
sudo rm -rf /etc/scribe /var/lib/scribed /var/log/scribed
sudo userdel scribe
```

```sh
cd "$SCRIBE_SRC" && sudo make uninstall
cd ~/scribe-build/fb303-build && sudo make uninstall
cd ~/scribe-build && sudo xargs rm -f < thrift-build/install_manifest.txt
sudo rm -rf /usr/local/include/thrift /usr/local/lib/cmake/thrift /usr/local/share/fb303
sudo rmdir --ignore-fail-on-non-empty /usr/local/lib/cmake /usr/local/lib/pkgconfig
sudo rm -f /etc/ld.so.conf.d/scribe-local.conf
sudo ldconfig
rm -rf ~/scribe-build
```

- **1번째 줄.** `scribed`와 정적 RPC 라이브러리, 그리고 `PY_PREFIX` 아래에 들어간 `scribe` package와 그 metadata를 지웁니다.
  - `make install`이 Python package로 설치한 파일 목록을 `lib/py/installed_files.txt`에 적어 두고, `make uninstall`은 그 목록의 파일만 지웁니다.
    가상환경이나 사용자 디렉터리에 있는 같은 이름의 package는 건드리지 않습니다.
  - 이 목록이 없는 이전 설치라면 아래 "빌드 폴더를 이미 지웠다면"의 Python 경로를 직접 지웁니다.
- **2~5번째 줄.** fb303, Thrift, 그리고 그 둘이 남긴 header 폴더와 빈 폴더를 지웁니다.
  `install_manifest.txt`는 파일만 적어 두므로 header 폴더는 따로 지웁니다.
- **`scribe-local.conf`.** Rocky(1-B)에서만 만들었습니다. Ubuntu에서는 없는 파일이라 그 줄은 아무것도 하지 않습니다.
- **1단계의 배포판 패키지.** 빌드 도구, libevent, Boost header는 다른 소프트웨어도 쓸 수 있어 지우지 않습니다.

- **빌드 폴더를 이미 지웠다면.**
  설치된 파일을 직접 지우는 목록과 저장소 폴더의 빌드 산출물 정리는 [빌드 안내](docs/build.md#설치한-파일-직접-삭제)에 있습니다.
- [실행](#실행)에서 만든 `$HOME/scribe-demo.conf`와 `$HOME/scribe-data`는 설치와 무관한 본인 파일이므로 필요 없으면 직접 지웁니다.
- 지운 뒤 `command -v scribed`는 아무것도 출력하지 않고, 기본 `PY_PREFIX`였다면 `python3 -c 'import scribe'`는 `ModuleNotFoundError`로 끝나야 합니다.

### Docker 방식

원본 Scribe에는 없던 방법입니다.

- Docker[^docker]로 위 1~4단계를 대신하고, 저장소의 [`Dockerfile`](Dockerfile)로 만든 이미지에서 `scribed`를 실행합니다.
- 이미지 구성, 확인 방법, 제한(HDFS 없음, 정적 RPC 라이브러리만)은 [Docker 안내](docs/docker.md)에 있습니다.
  기반 Rocky 9 이미지는 digest로 고정합니다.
- Scribe에는 인증·TLS가 없어 포트에 닿는 모든 client의 요청을 받으므로, 신뢰할 수 있는 네트워크에만 여세요.

#### 이미지 빌드

저장소 checkout의 최상위 폴더에서 실행합니다.
Thrift 소스를 내려받으므로 네트워크가 필요하고, commit하지 않은 변경도 이미지에 들어갑니다.

```sh
docker build -t scribe-next:local .
```

#### 실행과 기본 설정

로그를 저장할 폴더를 만들고, 컨테이너의 `/var/log/scribed`에 연결해 실행합니다.

```sh
mkdir -p scribe-logs && chmod 0777 scribe-logs
docker run -d --name scribe -p 1463:1463 \
  -v "$PWD/scribe-logs:/var/log/scribed" \
  scribe-next:local
```

- 컨테이너는 root가 아닌 시스템 사용자 `scribe`로 실행되므로, 연결한 폴더에 그 사용자가 쓸 수 있어야 합니다(위의 `chmod 0777`).
- 기본 설정 [`examples/docker.conf`](examples/docker.conf)는 다음과 같이 동작합니다.
  - `port=1463`에서 받습니다.
  - 모든 category[^category]를 `category=default` [모델](#먼저-모델과-복사본) 하나로 받습니다(이름 조각이 `..`인 category는 [거부](docs/behaviour.md#동적-category-이름의-상위-폴더-거부)).
  - 파일은 `/var/log/scribed/<category>/<category>-YYYY-MM-DD_00000`에 쌓이고, 메시지마다 줄바꿈을 하나 붙입니다(`add_newlines=1`).
  - `<category>_current` symlink[^symlink]가 지금 쓰는 파일을 가리킵니다.
- 직접 만든 설정을 쓰려면 `/etc/scribe/scribe.conf` 위에 읽기 전용으로 연결합니다.
  설정의 `port`를 바꾸면 `docker run -p 호스트포트:설정포트`도 같이 바꾸세요.

```sh
docker run -d --name scribe -p 1463:1463 \
  -v "$PWD/scribe-logs:/var/log/scribed" \
  -v "$PWD/my-scribe.conf:/etc/scribe/scribe.conf:ro" \
  scribe-next:local
```

#### 동작 확인

```sh
docker logs scribe
```

- `Starting scribe server on port 1463`과 `STATUS: ALIVE`가 보여야 합니다.
- 프로세스가 떴다는 것만으로 저장이 정상이라고 판단하지 마세요.
  [실행의 동작 확인](#3-동작-확인)과 같은 방법으로 저장소 폴더에서 시험 메시지를 보내고, `scribe-logs/demo/demo_current`의 내용을 확인합니다.

#### 정지

```sh
docker stop scribe
```

- `docker stop`은 SIGTERM을 보냅니다. `scribed`는 [실행의 정지](#4-정지)와 같이 큐를 처리하고 store를 닫은 뒤 종료 코드 0으로 끝납니다.
- 유예 시간(기본 10초) 안에 끝나지 않으면 Docker가 SIGKILL로 끝내고, 그때 큐에 남은 로그는 잃을 수 있습니다.
  큐가 크면 `docker stop -t 60 scribe`처럼 유예 시간을 늘리세요.

#### 삭제

컨테이너, 이미지, 로그 폴더를 지웁니다. 로그 폴더를 만든 곳에서 실행합니다.

```sh
docker rm -f scribe
docker rmi scribe-next:local
sudo rm -rf scribe-logs
```

- `docker rm -f`는 실행 중인 컨테이너를 SIGKILL로 끝내므로, 큐의 로그를 지키려면 먼저 [정지](#정지)대로 `docker stop`을 실행하세요.
- `scribe-logs`의 파일은 컨테이너 사용자 소유라 `sudo`가 필요할 수 있습니다.
- 빌드 중간 layer는 `docker builder prune`으로 지웁니다. 다른 이미지의 cache도 함께 지워집니다.

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

- **다른 category는 받지 않습니다.**
  그런 로그는 원본 규칙대로 버려지고 카운터 `received bad`가 늘어납니다.
  다른 category도 받으려면 `<store>`를 추가하거나 `category=default` [모델](#먼저-모델과-복사본)을 쓰세요.
- **기존 설정을 출발점으로 써도 됩니다.**
  [원본 설정 예제](examples/example1.conf)의 파일 경로와 포트만 본인 환경에 맞게 바꾸세요.
  원본 [README](README)와 [examples 안내](examples/README)는 역사적 자료입니다.
  그 안내에 나오는 `example2.conf` 대신 실제 파일인 `example2client.conf`·`example2central.conf`를 보세요.

### 2. 시작

```sh
scribed -c "$SCRIBE_CONFIG"
```

- `scribed`는 실행한 터미널에 붙은 채 동작하고, 진행 로그를 그 터미널에 출력합니다.
- 부팅 때 자동으로 시작하고 `systemctl restart scribed`로 다루려면 [systemd 서비스로 등록](#5-systemd-서비스로-등록)을 보세요.
- `scribed`에는 받을 주소를 정하는 설정이 없어 모든 네트워크 주소에서 받습니다(원본과 같음).
  인증·TLS도 없으니 실행 환경의 접근 범위를 먼저 확인하세요.
- `-c`와 옵션이 아닌 인자가 모두 없으면 원본 기본값 `/usr/local/scribe/scribe.conf`를 읽습니다.

- **설정의 `port`가 명령행 `-p`보다 우선합니다.**
  위 설정으로 `scribed -c "$SCRIBE_CONFIG" -p 1464`를 실행해도 1463에서 받습니다.
  이때 로그에 `port 1463 from conf file overriding old port 1464`가 남습니다.
- **설정에 `port=`를 꼭 쓰세요.**
  - `port`와 `-p`가 모두 없어도 `scribed`는 끝나지 않습니다.
  - `No port number configured` 오류로 상태가 `WARNING`이 되고, store를 하나도 만들지 않은 채 운영체제가 고른 임의의 port에서 받습니다(원본과 같음).
  - 설정 파일을 읽지 못할 때도 store 없이 `WARNING` 상태로 뜹니다(port는 `-p` 값, 없으면 임의의 port).
- **긴 옵션 `--config`, `--port`는 쓰지 마세요.**
  원본 결함 때문에 제대로 동작하지 않습니다([남겨 둔 버그](docs/behaviour.md#긴-명령행-옵션은-값을-받지-못한다)). 항상 `-c`, `-p`를 쓰세요.

### 3. 동작 확인

시작 로그에 다음 두 줄이 보여야 합니다.

```text
"STATUS: ALIVE"
"Starting scribe server on port 1463"
```

- **프로세스가 떴다는 것만으로 정상이라고 판단하지 마세요.**
  listener를 열지 못하면 종료 코드 1로 끝나지만, store 설정이 틀리면 `WARNING` 상태로 계속 떠 있습니다([자세히](docs/behaviour.md#시작-실패의-종료-코드)).
  그래서 시험 메시지, fb303 상태, 카운터, 실제 파일을 함께 확인합니다.
- **시험 메시지 보내기.**
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

- `Log: 0`은 [`OK`](docs/behaviour.md#ok는-메모리-큐에-받았다는-뜻이다)이고, `1`이면 `TRY_LATER`[^trylater]입니다.
- `status: 2`는 `ALIVE`입니다. `5`(`WARNING`)이면 설정이나 연결에 문제가 있다는 뜻이며, 로그의 `STATUS:` 줄에 이유가 남습니다.
- 카운터는 `<category>:<이름>`과 전체 합계 `scribe_overall:<이름>`으로 나옵니다.

- **파일 확인.**
  약 1초 뒤 파일을 확인합니다.

```sh
ls -l "$SCRIBE_DATA"
cat "$SCRIBE_DATA/demo_current"
```

- `demo-<오늘 날짜>_00000` 파일과, 그 파일을 가리키는 `demo_current`가 있어야 합니다.
- 내용은 `hello scribe` 한 줄입니다(`add_newlines=1`이 줄바꿈을 붙임).
- 파일은 시작할 때 미리 열리므로, 파일이 있는지만 보지 말고 내용까지 확인하세요.

- **원본 예제 스크립트는 쓸 수 없습니다.**
  [`examples/scribe_cat`](examples/scribe_cat)·[`examples/scribe_ctrl`](examples/scribe_ctrl)은 Python 2 스크립트 그대로입니다.
  `scribe_ctrl`은 Python 3에서 `SyntaxError`로 바로 끝나고, `scribe_cat`은 Ubuntu 24.04·Rocky 9 기본 설치에 없는 `/usr/bin/python`과 Python client·Thrift·fb303 Python module이 필요합니다.

### 4. 정지

`scribed`를 띄운 터미널에서 Ctrl+C를 누르거나, 다른 터미널에서 SIGTERM을 보냅니다.
PID는 `pgrep -a scribed`로 확인합니다.

```sh
kill <scribed의 PID>
```

- **세 가지 정지 방법은 같은 정리를 합니다.**
  Ctrl+C(SIGINT), SIGTERM, fb303 `shutdown` 모두 큐에 남은 로그를 한 번 더 처리하고 store를 닫은 뒤 종료 코드 0으로 끝납니다.
  신호로 멈추면 로그에 `received signal 15, shutting down`(Ctrl+C는 2)이 남습니다.
  마지막 로그 `scribe server exiting`은 종료 순서에 따라 남지 않을 수 있습니다.
- **예외.**
  직전에 실패해 재시도를 기다리던 묶음(`must_succeed=yes`의 requeue)이 있으면 그 묶음만 처리하고, 그 사이 큐에 들어온 로그는 처리하지 않은 채 store를 닫습니다.
  이때 `lost` 카운터는 늘지 않으며, 원본과 같은 동작입니다.
- **신호의 처리 시점.**
  설정을 읽는 도중 받은 신호는 설정이 끝난 뒤 처리합니다. 정지 중에 다시 보낸 신호는 무시하므로, 끝나지 않으면 SIGKILL(`kill -9`)로 끝냅니다. 이때 큐의 로그는 잃을 수 있습니다.
- **구버전은 다릅니다.**
  구버전은 SIGTERM·Ctrl+C에 큐를 처리하지 않고 바로 끝납니다. 구버전은 아래처럼 저장소 폴더에서 fb303 `shutdown`을 보내 멈춥니다.
  다른 서버의 `scribed`를 멈출 때도 이 방법을 쓸 수 있습니다(`127.0.0.1`과 port만 바꿈).

```sh
python3 - <<'PY'
import socket, sys
sys.path.insert(0, 'tools')
from daemon_differential import framed
socket.create_connection(('127.0.0.1', 1463)).sendall(framed(b'shutdown', 1, oneway=True))
PY
```

### 5. systemd 서비스로 등록

Ubuntu 24.04와 Rocky Linux 9에서 같은 방법으로 등록합니다.
[원래 Scribe 방식](#원래-scribe-방식)으로 `/usr/local/bin/scribed`를 설치했다고 가정합니다.

```sh
sudo useradd --system --no-create-home --shell /usr/sbin/nologin scribe
sudo install -D -m 644 "$SCRIBE_SRC/examples/docker.conf" /etc/scribe/scribe.conf
sudo install -D -m 644 "$SCRIBE_SRC/examples/scribed.service" /etc/systemd/system/scribed.service
sudo systemctl daemon-reload
sudo systemctl enable --now scribed
```

- **실행 사용자.** root가 아닌 시스템 사용자 `scribe`로 실행됩니다.
- **설정 파일.** `/etc/scribe/scribe.conf`입니다.
  [`examples/docker.conf`](examples/docker.conf)가 바로 쓸 수 있는 기본 설정이며, Docker 방식과 같은 파일입니다.
  본인 설정을 쓰려면 이 경로에 두거나, 설치 줄의 원본 경로만 바꾸세요. [`port=`는 꼭 있어야 합니다](#2-시작).
- **쓸 수 있는 경로.**
  systemd가 `/var/log/scribed`와 `/var/lib/scribed`를 `scribe` 소유로 만듭니다. 기본 설정은 buffer 없이 `/var/log/scribed`에만 씁니다.
  buffer를 쓴다면 spool 위치는 secondary의 `file_path`가 정하며, `/var/log/scribed/spool`을 써도 됩니다.
  그 밖의 경로는 서비스가 쓸 수 없게 막혀 있으므로(`ProtectSystem=strict`), 다른 곳에 쓰려면 `sudo systemctl edit scribed`로 `[Service]`에 `ReadWritePaths=/다른/경로`를 추가하세요.
- **진행 로그.** 터미널 대신 journal에 남습니다.

이후에는 평소 systemd 명령으로 다룹니다.

```sh
sudo systemctl restart scribed
sudo systemctl stop scribed
systemctl status scribed
journalctl -u scribed -n 50 -f
```

- **`stop`·`restart`의 동작.**
  - systemd가 SIGTERM을 보내고, `scribed`는 [정지](#4-정지)와 같이 큐에 남은 로그를 처리하고 store를 닫은 뒤 종료 코드 0으로 끝납니다.
  - 기다리는 시간의 상한은 `TimeoutStopSec=90`(90초)입니다. 그 안에 끝나지 않으면 systemd가 SIGKILL로 끝내고, 큐의 로그를 잃을 수 있습니다.
- **동작 확인.**
  [동작 확인](#3-동작-확인)의 시험 메시지를 보내면 `/var/log/scribed/demo/demo_current`에 저장됩니다(기본 설정은 모든 category를 받습니다).
- **실패와 재시작.**
  - listener를 열지 못하면(port 사용 중, 잘못된 크기 한도) 종료 코드 1로 끝나고, `Restart=on-failure`가 `RestartSec=5`(5초) 뒤 다시 시작합니다([자세히](docs/behaviour.md#시작-실패의-종료-코드)).
  - store 설정이 틀려도 `scribed`는 끝나지 않고 `WARNING` 상태로 계속 떠 있으므로, 서비스는 `active`로 보이고 다시 시작하지 않습니다.
    `systemctl status scribed`와 `journalctl -u scribed`로 `STATUS:` 줄을 확인하세요.
- **unit의 제한.**

  | 설정 | 영향 |
  | --- | --- |
  | `LimitNOFILE=65536` | `scribed`가 시작할 때 열린 파일 한도를 65535로 올릴 수 있게 함 |
  | `UMask=0027` | 새 로그 파일은 `0640`. 읽는 프로그램은 `scribe` group이거나 root여야 함 |
  | `CapabilityBoundingSet=` | 권한이 없어 1024 미만 port에서 받을 수 없음 |
  | `RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX` | IPv4·IPv6·Unix socket만 씀. network store의 TCP 전송은 이 범위 안 |
  | `ProtectSystem=strict` 등 | 위 [쓸 수 있는 경로](#5-systemd-서비스로-등록) 밖에는 쓰지 못함 |

  이 unit은 `systemd-analyze verify`로만 확인했습니다. systemd 아래에서 실제 `scribed`를 띄운 기록은 없습니다.
- **알아둘 점.**
  - Rocky의 firewalld는 1463을 막습니다. 다른 서버에서 로그를 받으려면 `sudo firewall-cmd --permanent --add-port=1463/tcp && sudo firewall-cmd --reload`를 실행하세요.

### 파일 회전 기본

file store는 일정 시간이나 크기가 되면 새 파일을 엽니다(회전).

- **파일 이름.** `<base_filename>-YYYY-MM-DD_NNNNN`입니다.
  날짜는 daemon의 지역 시간(TZ)을 따르고, `rotate_period=never`이면 날짜가 붙지 않습니다(`demo_00000`).
- **크기 회전.** 파일이 `max_size`를 넘으면 번호 `NNNNN`을 하나 올린 새 파일을 엽니다.
  - file store의 기본값은 1,000,000,000 bytes이고, 0이면 크기 제한이 없습니다.
  - 날짜가 바뀐 뒤 첫 파일은 `_00000`부터 시작합니다.
- **`_current`.** `<base_filename>_current`는 가장 최근 파일을 가리키는 symlink입니다.
  `base_symlink_name`으로 이름을 바꿀 수 있고, `create_symlink=no`이면 만들지 않습니다.
- **검사 주기.** 회전 검사는 `check_interval`마다 하므로, 실제 회전은 그만큼 늦을 수 있습니다.

| `rotate_period` | 새 파일을 여는 때 |
| --- | --- |
| `never`(기본값) | 시간으로는 열지 않음 |
| `hourly` | 매시 `rotate_minute`(기본 15)분 이후 |
| `daily` | 매일 `rotate_hour`(기본 1)시 `rotate_minute`분 이후 |
| `30m`, `1h`, `2d`, `1w`, `3600` | 파일을 연 뒤 그 시간이 지나면 |
| 그 밖의 값(예: `1x`) | 경고 로그를 남기고 시간 회전을 끔 |

- 숫자만 쓰면 초 단위입니다(`3600` = `3600s` = 1시간).
- `hourly`로 시작할 때 그날 파일이 없으면 첫 번호가 현재 시각의 시가 됩니다(예: 13시 → `_00013`).
- buffer의 secondary(spool) 파일은 항상 `never`처럼 동작하고 symlink를 만들지 않습니다.

### 기존 서버를 신버전으로 바꿀 때

운영 배포와 복구 절차 자체를 검증한 것은 아닙니다. 전환 전에 다음을 준비하세요.

1. 이전 실행 파일, 라이브러리, 설정을 한 묶음으로 보관합니다.
2. 기존 `scribed`를 fb303 `shutdown`으로 멈추고, 데이터와 spool 파일은 그대로 둡니다. 구버전은 SIGTERM에 큐를 처리하지 않으므로 `kill`·`systemctl stop`으로 멈추지 마세요.
3. 구·신 서버가 같은 데이터·spool 폴더에 동시에 쓰지 않게 합니다.
4. 별도 폴더에서 작은 로그의 전송·저장·상태를 확인한 뒤 전환합니다.

- 신버전은 구버전이 남긴 spool을 이어서 다시 보낼 수 있고, 그 반대도 됩니다([테스트 결과](#테스트-결과)).
- 구버전으로 되돌리면 [고친 원래 버그](#고친-원래-버그)도 원본 동작으로 돌아갑니다(예: 재전송 일부 성공 시 손실).
- 실행 파일을 되돌려도 이미 잃은 메시지가 복구되지는 않습니다.

## 테스트 결과

이 절은 "기존 구버전 `scribed`를 신버전으로 바꿔도 되는가"에 답하기 위한 시험과 그 결과입니다.
시험 도구와 case별 상세 기대값은 [검증 기록](docs/verification.md)에, 다시 돌리는 방법은 [구버전 비교 환경](tools/old-lane/README.md)에 있습니다.

### 무엇을 어떻게 비교했나

- **구버전.**
  공개 원본의 마지막 버전을 당시의 Thrift/fb303 0.9.0으로 Ubuntu 16.04(GCC 5.4)에서 빌드한 `scribed`입니다.
- **신버전.**
  이 저장소를 Rocky Linux 9(GCC 11.5), Thrift 0.25.0으로 빌드한 `scribed`입니다. 저장소의 [`Dockerfile`](Dockerfile)로 만든 이미지 그대로입니다.
- **비교 방법.**
  - 두 버전을 실제 프로세스로 띄우고 같은 요청을 보냅니다.
  - 응답 bytes, fb303 카운터, 저장 파일의 bytes, `_current` symlink, spool 파일, 종료 코드를 봅니다.
  - 각 case마다 기대값을 원본 소스에서 미리 정해 두고, 구버전 결과와 신버전 결과가 **모두 기대값과 같고 서로 같을 때만** 통과입니다.
  - 파일 내용은 정규화하지 않고 byte 그대로 비교합니다.
- **실행 환경.**
  2026-10-08, 리뷰 수정을 합친 통합 branch(`fix/review-20261008`)를 WSL의 Rocky Linux 9.8에서 Docker로 실행했습니다. 이미지는 모두 처음부터 다시 만들었습니다.
  case마다 새 컨테이너(네트워크 없음, 비root 사용자, CPU 2개, 메모리 2 GiB)를 씁니다.
  모든 수치는 한 번 실행한 값입니다.

### 결과 한눈에

| 시험 | 내용 | 결과 |
| --- | --- | --- |
| [단독 동작 비교](#1-같은-입력에-같은-결과를-내는가) | 같은 요청에 같은 파일·카운터·응답을 내는지, 11개 case | 11개 모두 통과 |
| [구·신 혼용 장애 시나리오](#2-구버전과-신버전을-섞어-썼을-때) | 송신측·수신측에 구·신을 조합한 7개 시나리오 × 4조합 = 28개 실행(14개 case) | 28개 모두 통과 |
| [성능 비교](#3-성능-비교) | 같은 부하에서 처리량·지연·자원 | 신버전 처리량 0.91배, 지연·자원 같은 수준 |
| [빌드·단위 시험](#4-빌드단위-시험과-docker-이미지) | 빌드, 단위 시험 묶음, 임시 설치 | 시험 253개 모두 통과 |
| [Docker 이미지](#4-빌드단위-시험과-docker-이미지) | 기본 설정으로 받기·저장, `docker stop`·SIGINT로 정상 종료, port 사용 중 종료 코드 1 | 통과 |

새로 더한 비교 case는 `rotation-time`, `backpressure`, `bucket-hash`입니다(아래 1번 표의 마지막 세 행).

### 1. 같은 입력에 같은 결과를 내는가

구버전과 신버전을 **따로** 띄우고 같은 요청을 보낸 뒤 결과를 비교합니다.
설정 파일·요청·파일 형식·상태 조회가 원본과 같은지 보는 기본 시험입니다.

| CASE | 보내는 것 | 예상 결과 | 실제 결과 |
| --- | --- | --- | --- |
| 기본 저장 (`file`) | 정상 메시지 3개(NUL·줄바꿈·비UTF-8·빈 메시지 포함), 빈 `Log`, 빈 category, 모르는 category, 상태·카운터 조회, `shutdown` | 파일 9 bytes, `_current` symlink, 카운터 `received good 3`·`bad 1`·`blank 1`, 종료 코드 0 | 구·신 같음, 통과 |
| store 종류 (`stores`) | null(버림)·multi(여러 곳에 복사)·category(이름별 분배) store에 한 batch | 각 store의 파일 bytes와 카운터 `received good 9`·`ignored 6`가 같음 | 구·신 같음, 통과 |
| 파일 회전 (`rotation`) | `max_size=4`로 크기 회전, 그 뒤 `reinitialize`(설정 다시 읽기) | `_00000` 5 bytes, `_00001` 4 bytes, 다시 읽은 뒤 `_00001`에 이어 쓰고 빈 `_00002` | 구·신 같음, 통과 |
| 강제 종료 후 재시작 (`restart`) | 첫 프로세스를 SIGKILL, 같은 설정으로 새 프로세스 | 새 프로세스가 같은 파일을 다시 열어 이어 씀 | 구·신 같음, 통과 |
| 파일 store 모음 (`file-stores`) | bucket(key로 분배), thriftfile(framed·raw), multifile·thriftmultifile 별칭 | 파일 9개·symlink 9개의 bytes와 `received good 13` | 구·신 같음, 통과 |
| 상태 조회 API (`fb303`) | getOptions·setOption·getCounter·getCounters, 모르는 method | 응답 14개의 bytes가 같고, 모르는 method 뒤에도 같은 연결로 계속 동작 | 구·신 같음, 통과 |
| 동적 목적지 (`mapping`) | bucket updater가 알려 주는 목적지가 A → B → (조회 실패) → A로 바뀜 | TTL 만료 전 A 유지, 만료 뒤 B, 조회 실패 때 B 유지, 회복 뒤 A | 구·신 같음, 통과 |
| 게임 서버형 설정 (`game-profile`) | prefix 모델, `categories=` 목록, multi 아래 buffer 두 개, 연결 pool, 시간 회전, 줄 중간 주석을 한 설정에 모음 | 시작 상태, spool frame, 수신측 기동 뒤 재전송 결과가 같음 | 구·신 같음, 통과 |
| 시간 회전 (`rotation-time`) | `rotate_period=2s`에서 `first`, 회전을 기다린 뒤 `second` | `_00000`=`first`, `_00001`=`second`, `_current`는 `_00001`, `received good 2` | 구·신 같음, 통과 |
| 큐 한도 (`backpressure`) | `max_queue_size=8`로 큐가 빠지지 않게 한 뒤 9 bytes 묶음과 다음 `Log` | 둘째 `Log`가 `TRY_LATER`, `denied for queue size` 1, 파일은 `shutdown` 때 9 bytes | 구·신 같음, 통과 |
| bucket 분배 (`bucket-hash`) | `key_hash`·`key_modulo` bucket store에 숫자·문자·UTF-8·음수·빈 key | bucket 파일 8개의 bytes가 원본 계산(djb2, `atol`)과 같음 | 구·신 같음, 통과 |

### 2. 구버전과 신버전을 섞어 썼을 때

운영에서 실제로 생기는 장애를 흉내 내고, 송신측과 수신측의 버전을 네 가지로 조합해 같은 결과가 나오는지 봅니다.

- **역할.**
  - **송신측**: buffer store를 쓰는 `scribed`입니다. primary는 수신측으로 보내는 network store, secondary는 spool 파일입니다.
    `retry_interval=10`(재시도 10초), `timeout=500`(응답 대기 0.5초)입니다.
  - **수신측**: 받은 로그를 file store에 그대로 저장하는 `scribed`입니다.
  - **소비 클라이언트**: 시험 도구가 수신 폴더를 읽기만 합니다. 파일 목록, 크기, 내용, `_current`, 번호 순서로 이은 bytes를 봅니다.
- **조합.**

  | 조합 | 송신측 | 수신측 |
  | --- | --- | --- |
  | 구 → 구 | 구버전 | 구버전 |
  | 신 → 신 | 신버전 | 신버전 |
  | 구 → 신 | 구버전 | 신버전 |
  | 신 → 구 | 신버전 | 구버전 |

- **통과 기준.**
  네 조합 모두에서 응답, 카운터, 수신 파일의 bytes, spool 파일, `_current`, 종료 코드가 소스에서 정한 기대값과 같아야 합니다.
- **보내는 메시지.**
  첫 묶음은 NUL·줄바꿈·비UTF-8 byte가 든 메시지와 `tail`, 그다음 묶음은 `second`·`third`, 마지막은 `Z`입니다.
  수신 파일은 `add_newlines=0`이라 메시지가 그대로 이어집니다.

#### CASE A. 평소 전달

- **상황.** 장애가 없는 평소 상태입니다. 송신측이 두 category의 메시지를 세 번에 나눠 수신측으로 넘깁니다.
- **절차.** 수신측(`category=default`, `max_size=4`) → 송신측 순서로 띄우고, `Log`를 세 번 보냅니다.
- **예상 결과.**
  - 수신측은 category마다 폴더를 만들고, 4 bytes를 넘을 때마다 번호를 올린 새 파일을 엽니다(`fixture_00000` 5 bytes, `_00001` 10 bytes, `_00002` 1 byte).
  - `_current`는 마지막 파일을 가리킵니다.
  - 파일을 번호 순서로 이으면 보낸 순서와 같습니다.
  - 송신측 카운터 `sent 7`, 수신측 `received good 7`, spool 파일 없음, 손실 0.
- **실제 결과.**

  | 구 → 구 | 신 → 신 | 구 → 신 | 신 → 구 |
  | --- | --- | --- | --- |
  | 통과 | 통과 | 통과 | 통과 |

#### CASE B. 수신측이 없을 때 쌓았다가 재전송

- **상황.** 송신측을 먼저 띄웠는데 수신측이 아직 없습니다(배포 순서가 어긋나거나 수신 서버가 내려간 상태).
- **절차.** 송신측만 띄우고 첫 묶음을 보냅니다. 그다음 수신측을 띄우고 `Z`를 보냅니다.
- **예상 결과.**
  - 수신측이 없는 동안 송신측은 상태 `WARNING`, 카운터 `retries 1`이 되고, 첫 묶음을 spool 파일(17 bytes)에 씁니다. 손실은 아닙니다.
  - 수신측이 뜨면 `retry_interval` 뒤 spool 전체를 다시 보내고(9 bytes), spool 파일을 지웁니다.
  - 그 뒤 `Z`는 바로 전달됩니다(10 bytes). 송신측 `sent 3`.
- **실제 결과.**

  | 구 → 구 | 신 → 신 | 구 → 신 | 신 → 구 |
  | --- | --- | --- | --- |
  | 통과 | 통과 | 통과 | 통과 |

#### CASE C. 수신측이 정상 종료됐다가 다시 시작

- **상황.** 수신 서버를 점검이나 교체로 잠시 내렸다가 같은 설정·폴더로 다시 올립니다. 그 사이 송신측은 계속 로그를 받습니다.
- **절차.** 첫 묶음이 수신 파일에 보인 뒤 수신측에 fb303 `shutdown`을 보냅니다. 송신측에 둘째 묶음을 보냅니다. 수신측을 다시 띄우고 `Z`를 보냅니다.
- **예상 결과.**
  - 수신측이 없는 동안의 둘째 묶음은 송신측 spool에 쌓이고(`retries 1`), 송신측 상태는 `ALIVE`를 유지합니다.
  - 다시 뜬 수신측은 같은 `fixture_00000` 파일을 이어서 씁니다. 재전송된 둘째 묶음이 첫 묶음 뒤에 붙고 spool은 비워집니다.
  - `Z`는 바로 전달됩니다. 최종 수신 파일은 첫 묶음 + 둘째 묶음 + `Z` 순서이며 손실·중복이 없습니다.
  - 다시 뜬 수신측의 카운터는 새로 시작해 `received good 3`입니다.
- **실제 결과.**

  | 구 → 구 | 신 → 신 | 구 → 신 | 신 → 구 |
  | --- | --- | --- | --- |
  | 통과 | 통과 | 통과 | 통과 |

#### CASE D. 수신측이 강제 종료(SIGKILL)됐다가 다시 시작

- **상황.** 수신 서버가 OOM kill이나 장비 장애처럼 정리 없이 죽었다가 다시 올라옵니다.
- **절차.** CASE C와 같되 수신측을 SIGKILL로 끝냅니다(종료 코드 -9 확인).
- **예상 결과.**
  - 송신측에서는 CASE C와 똑같이 보입니다. 운영체제가 연결을 끊으므로 다음 전송에서 실패를 알고 spool에 씁니다.
  - 최종 수신 파일과 카운터는 CASE C와 같습니다. 손실·중복이 없습니다.
  - (수신측이 SIGKILL 전에 `OK`를 돌려주고 아직 파일에 쓰지 않은 로그는 사라질 수 있습니다. 이 시험은 첫 묶음이 파일에 보인 뒤에만 죽이므로 그 경우는 포함하지 않습니다. [OK의 뜻](docs/behaviour.md#ok는-메모리-큐에-받았다는-뜻이다)을 보세요.)
- **실제 결과.**

  | 구 → 구 | 신 → 신 | 구 → 신 | 신 → 구 |
  | --- | --- | --- | --- |
  | 통과 | 통과 | 통과 | 통과 |

#### CASE E. 수신측이 멈췄다가(응답 지연) 회복

- **상황.** 수신 서버가 죽지는 않았지만 응답하지 못합니다(과부하, 디스크 I/O 정지, 프로세스 일시 정지 등). 네트워크 연결은 살아 있습니다.
- **절차.** 첫 묶음이 수신 파일에 보인 뒤 수신측 프로세스를 SIGSTOP(프로세스를 그 자리에서 일시 정지시키는 신호)으로 멈춥니다. 송신측에 둘째 묶음을 보냅니다. spool이 생긴 것을 확인한 뒤 SIGCONT로 수신측을 깨우고, 재전송이 끝나면 `Z`를 보냅니다.
- **예상 결과.**
  - 송신측의 둘째 묶음 전송은 TCP로는 나가지만 응답이 0.5초 안에 오지 않습니다. 송신측은 연결을 닫고 둘째 묶음을 spool에 씁니다(`retries 1`, 상태 `ALIVE`).
  - 깨어난 수신측은 socket 버퍼에 남아 있던 둘째 묶음을 읽어 파일에 씁니다(응답은 이미 닫힌 연결로 가서 버려짐).
  - `retry_interval` 뒤 송신측이 spool을 다시 보내므로 **둘째 묶음이 한 번 더 저장됩니다.**
  - 최종 수신 파일은 첫 묶음 + 둘째 묶음 + 둘째 묶음 + `Z`입니다. **손실은 없지만 중복이 생깁니다.** 수신측 `received good 7`, 송신측 `sent 5`.
  - 이 중복은 "`OK`는 큐 수락"이라는 원본 설계에서 나오는 동작이며, 구버전과 신버전이 같아야 합니다.
- **실제 결과.**

  | 구 → 구 | 신 → 신 | 구 → 신 | 신 → 구 |
  | --- | --- | --- | --- |
  | 통과 | 통과 | 통과 | 통과 |

  네 조합 모두 예상대로 둘째 묶음이 두 번 저장됐고, 구·신의 파일 bytes와 카운터가 같았습니다.

#### CASE F. 송신측이 종료됐다가 다시 시작 (이전 프로세스의 spool 이어 보내기)

- **상황.** 수신측이 없어 spool이 쌓인 상태에서 송신 서버를 내렸다가(예: `scribed` 교체) 다시 올립니다. 이 case가 **구버전이 쓴 spool 파일을 신버전이 읽는** 시험입니다.
- **절차.** 수신측 없이 송신측을 띄워 첫 묶음을 spool에 쓰게 하고 정상 종료합니다. 수신측을 띄운 뒤, 같은 spool 폴더로 송신측을 다시 띄우고 `Z`를 보냅니다.
- **예상 결과.**
  - 정상 종료해도 spool 파일(17 bytes)은 지워지지 않고 남습니다.
  - 다시 뜬 송신측은 이전 프로세스가 쓴 spool을 읽어 재전송하고(`sent 2`) 파일을 지운 뒤, `Z`를 바로 보냅니다.
  - 최종 수신 파일은 첫 묶음 + `Z`이며 손실·중복이 없습니다.
- **조합.** 이 case의 조합은 "spool을 쓴 송신측 → 다시 뜬 송신측"입니다.
  같은 버전끼리(`sender-restart-spool`)는 수신측도 같은 버전이고, 버전을 바꾸는 두 조합(`mixed-sender-restart-spool`)만 수신측을 신버전으로 고정했습니다.

  | 조합 | spool을 쓴 송신측 | 다시 뜬 송신측 | 수신측 | 결과 |
  | --- | --- | --- | --- | --- |
  | 구 → 구 | 구버전 | 구버전 | 구버전 | 통과 |
  | 신 → 신 | 신버전 | 신버전 | 신버전 | 통과 |
  | 구 → 신 | 구버전 | 신버전 | 신버전 | 통과 |
  | 신 → 구 | 신버전 | 구버전 | 신버전 | 통과 |

  구버전이 쓴 spool을 신버전이, 신버전이 쓴 spool을 구버전이 그대로 읽어 보냈습니다.

#### CASE G. 수신측이 자원 한도로 거절(`TRY_LATER`)한 뒤 재시도

- **상황.** 수신 서버가 한도를 넘는 요청을 `TRY_LATER`로 거절합니다. 여기서는 초당 메시지 한도(`max_msg_per_second=4`)를 씁니다. 큐 크기 한도(`max_queue_size`)를 넘을 때도 송신측은 같은 경로를 탑니다.
- **절차.** 한 초 안에 메시지 2개·2개·1개를 보냅니다. 재전송이 끝날 때까지 기다립니다.
- **예상 결과.**
  - 다섯 번째 메시지(`Z`)가 `TRY_LATER`를 받고 수신측 `denied for rate 1`이 됩니다.
  - 송신측은 연결을 닫지 않은 채 `Z`를 spool에 쓰고(`retries 1`), `retry_interval` 뒤 다시 보냅니다.
  - 최종 수신 파일은 다섯 메시지가 순서대로이며 손실·중복이 없습니다.
- **실제 결과.**

  | 구 → 구 | 신 → 신 | 구 → 신 | 신 → 구 |
  | --- | --- | --- | --- |
  | 통과 | 통과 | 통과 | 통과 |

#### 시나리오 종합

| CASE | 장애 종류 | 예상 | 구 → 구 | 신 → 신 | 구 → 신 | 신 → 구 |
| --- | --- | --- | --- | --- | --- | --- |
| A | 없음(평소 전달) | 손실·중복 없음, 순서 유지 | 통과 | 통과 | 통과 | 통과 |
| B | 수신측 부재 → 기동 | spool 뒤 재전송, 손실 없음 | 통과 | 통과 | 통과 | 통과 |
| C | 수신측 정상 종료 → 재시작 | spool 뒤 재전송, 같은 파일에 이어 씀 | 통과 | 통과 | 통과 | 통과 |
| D | 수신측 강제 종료 → 재시작 | C와 같음 | 통과 | 통과 | 통과 | 통과 |
| E | 수신측 응답 지연 → 회복 | 손실 없음, **중복 1회** | 통과 | 통과 | 통과 | 통과 |
| F | 송신측 종료 → 재시작 | 이전 spool 이어 보냄, 손실 없음 | 통과 | 통과 | 통과 | 통과 |
| G | 수신측 거절(`TRY_LATER`) → 재시도 | spool 뒤 재전송, 손실 없음 | 통과 | 통과 | 통과 | 통과 |

- **이 결과가 말해 주는 것.**
  - 송신측이 buffer store를 쓰면 수신측의 부재·종료·강제 종료·지연·거절 어느 경우에도 로그가 없어지지 않고, 회복 뒤 순서대로 전달됩니다.
  - 그 동작이 구·신 어느 조합에서도 byte 단위로 같습니다. 구버전 한 대를 신버전으로 바꿔도 상대 서버는 차이를 보지 못합니다.
  - 응답이 늦어 timeout이 난 묶음은 중복될 수 있습니다(CASE E). 이는 원본 설계이며 신버전이 바꾸지 않았습니다.
  - 네트워크 장애는 수신측 강제 종료(연결 끊김, CASE D)와 응답 없음(CASE E)으로 대신했습니다. 패킷 유실 같은 중간 장애는 따로 흉내 내지 않았습니다.

### 구버전보다 좋아진 동작

[고친 원래 버그](#고친-원래-버그) 가운데 아래 항목은 구·신이 **일부러 다르게** 동작하므로 위 "같음" 비교에는 넣지 않았습니다.
대신 단위 시험이나 Docker 확인으로 신버전의 동작을 봅니다(아래 [빌드·단위 시험](#4-빌드단위-시험과-docker-이미지)에 포함).

| 상황 | 구버전 | 신버전 | 확인 방법 |
| --- | --- | --- | --- |
| spool 재전송 중 primary가 일부만 쓰고 실패 | 남은 로그를 `lost`로 세고 spool 삭제(영구 손실) | 남은 로그를 spool에 다시 써서 재시도 | 단위 시험(spool 파일 다시 쓰기 성공) |
| `retry_interval_range=0` 설정 | 0으로 나눠 비정상 종료할 수 있음 | jitter 없이 `retry_interval`마다 재시도 | 단위 시험(간격 계산) |
| `service_list` 재연결 반복 | 서버 후보가 매번 늘어나 메모리 증가, failover 지연 | 후보는 항상 목록 수만큼 | 단위 시험(재연결 뒤 목록 교체) |
| `use_conn_pool=yes` + 동적 목적지 변경 | 다른 store의 연결을 잘못 닫아 batch 1회 실패 | 옛 목적지 연결만 닫음 | 단위 시험(옛 연결만 닫힘) |
| SIGTERM·Ctrl+C로 정지 | 큐를 처리하지 않고 바로 끝남 | `shutdown`과 같은 정리 뒤 종료 코드 0 | 빌드한 실제 `scribed`로 단위 시험, Docker 이미지에서 `docker stop`·SIGINT |
| listener를 열지 못함 | 종료 코드 0 | 종료 코드 1 | 빌드한 실제 `scribed`로 단위 시험(port 사용 중), Docker 이미지 |
| 동적 category 이름에 `..` 조각 | `file_path` 밖에 파일을 만들 수 있음 | 거부, `received bad` | 단위 시험(`..`은 거부, `..x`는 받음) |

### 3. 성능 비교

같은 부하를 구버전과 신버전에 번갈아 주고 중앙값을 비교했습니다.
아래 수치는 2026-10-08 통합 branch `fix/review-20261008`의 최종 commit(검증기 253 tests를 잰 commit)에서 잰 값입니다. old0 → modern0 → modern1 → old1 → old2 → modern2 순서 3회의 중앙값입니다.

- **부하.** producer 4개가 각각 1 KiB 메시지 4,096개를 256개씩 묶어 보냅니다(합계 16,384개, 16 MiB). 먼저 256개로 warm-up합니다.
- **서버 설정.** `num_thrift_server_threads=4`, `max_queue_size=33554432`, file store(`rotate_period=never`).
- **측정.** 구·신을 번갈아 3회씩 돌려 중앙값을 씁니다. 모든 `Log`가 `OK`여야 하고, 기록 뒤 누락·중복·변형·순서를 검사합니다.
- **환경.** 위와 같은 컨테이너(CPU 2개, 메모리 2 GiB). 구버전과 신버전은 컴파일러·라이브러리가 다르므로 차이의 원인을 나누지는 않았습니다.

| 지표 | 구버전 | 신버전 | 뜻 |
| --- | --- | --- | --- |
| ACK 처리량 (msg/s) | 1,501,101 | 1,371,568 | 모든 batch가 `OK`를 받을 때까지의 초당 메시지 수 |
| ACK payload (MiB/s) | 1,466 | 1,339 | 같은 기간의 초당 bytes |
| 파일 기록 완료 (MiB/s) | 995 | 936 | 기대 크기가 파일에 보일 때까지(fsync 아님) |
| batch 지연 p95 (ms) | 1.25 | 1.35 | batch 하나가 `OK`를 받기까지, 상위 5% 경계 |
| daemon CPU (s) | 0.04 | 0.04 | 프로세스가 쓴 CPU 시간 |
| 최대 메모리 (MiB) | 20.9 | 21.2 | 프로세스가 실행 중 가장 많이 쓴 물리 메모리(`VmHWM`) |

- 신버전의 ACK 처리량은 구버전의 **0.91배**입니다. 지연과 자원 사용은 같은 수준입니다.
- 정확성 검사(누락·중복·변형·순서)는 구·신 모두 통과했습니다.
- 합격 기준이 있는 시험이 아니라 서술적 측정입니다. 운영 부하와 장기 실행은 재지 않았습니다.

### 4. 빌드·단위 시험과 Docker 이미지

- **빌드·단위 시험 묶음.**
  저장소의 검증 도구(`tools/validate_linux.py`)가 깨끗한 복사본을 빌드하고, 단위 시험 전체를 돌리고, 임시 폴더에 설치해 `scribed --help`를 확인합니다.
  - 단위 시험에는 C++03 원본 코드와의 spool 파일 교차 읽기, ASan·UBSan(메모리·미정의 동작 검사) component 시험, loopback RPC, fb303 patch 회귀 시험이 들어 있습니다.
  - 결과: 시험 **253개, 실패·오류·건너뜀 0**, 8단계 모두 통과(`status: passed`).
  - 이번에 더한 12개는 신호 정지·시작 실패 종료 코드(빌드한 실제 `scribed`), `..` category, 동적 category 큐 생성 실패, 연결 pool 대기, 손상 spool의 `bytes lost`, key_range, 복사본 큐 포인터, 새 비교 case의 harness를 확인합니다. 새 store 시험은 ASan 아래에서 돌지 않습니다.
- **시험 수를 읽는 법.**
  - 시험 수가 곧 `scribed`를 확인한 양은 아닙니다. 253개 가운데 약 108개는 `scribed`가 아니라 시험 harness·검증 도구 자체를 확인합니다.
  - daemon 수준의 근거는 위의 구·신 비교 case와, `scribed` 소스를 묶어 만든 fixture 프로그램으로 store·handler를 실제로 돌리는 시험입니다.
  - `python3 -m unittest discover test`를 검증기 밖에서 그냥 실행하면 준비된 의존성이 없는 module 대부분을 조용히 건너뜁니다. 그 결과는 의미 있는 실행이 아닙니다. 항상 `tools/validate_linux.py`로 돌리세요.
  - 원본에서 물려받은 PHP 시험(`test/*.php`, `test/600buckets`, `test/simulatebackoff`, `test/resultChecker`)은 지금 상태로는 실행할 수 없고, 검증에 들어 있지 않습니다.
- **Docker 이미지.**
  [`Dockerfile`](Dockerfile)로 만든 이미지를 기본 설정으로 띄워 확인했습니다.
  - `docker stop` 뒤 로그 `received signal 15, shutting down`, `STATUS: STOPPING`, `scribe server exiting`, 종료 코드 0. 큐에 있던 메시지가 `demo_current`에 남아 있었습니다.
  - SIGINT는 `received signal 2` 뒤 종료 코드 0, port가 이미 쓰이고 있으면 `Exception in main: Could not bind: Address already in use` 뒤 종료 코드 1.
  - 저장소의 CI(`.github/workflows/validate.yml`)에도 같은 확인(`docker stop` 뒤 종료 코드 0)과 Rocky 9 검증기 실행이 있지만, 아직 어디에서도 실행된 기록이 없습니다.

### 이 결과의 범위

- `OK`는 메모리 큐 수락입니다. 디스크 보장, 전원 장애, exactly-once는 시험하지 않았습니다.
- 각 case는 한 번씩 실행했습니다. 반복 실행 통계는 없습니다.
- 운영 설정·운영 부하·장기 실행·디스크 가득 참은 이 시험에 없습니다.
- 아직 하지 않은 검증 목록은 [검증 기록](docs/verification.md#확인한-것과-하지-않은-것)에 있습니다.

## 원래 버전에서 달라진 점

구버전과 비교해 바뀐 것을 모았습니다.
**어느 항목도 기존 설정을 고치도록 요구하지 않습니다.**
각 항목은 왜 바꿨는지, 무엇을 기대할 수 있는지, 기존과 무엇이 다른지, 관련 설정 키, 예시 순서로 설명합니다.

| 묶음 | 요약 | 로그 결과 |
| --- | --- | --- |
| [빌드와 의존성](#빌드와-의존성) | Thrift 0.25, patch한 fb303, C++17, Boost 제거 | 같음 |
| [고친 원래 버그](#고친-원래-버그) | 비정상 종료·미정의 동작, HDFS 빌드·handle, 연결 pool·`service_list`·재전송, 신호 정지·시작 실패 종료 코드·category `..` | 분배·형식 같음(`..` category 제외) |
| [코드 정리](#코드-정리) | 잠금·메모리·전역 의존 정리 | 같음(실패 경로 제외) |
| [새 설정 키](#새-설정-키) | Thrift 크기 한도 2개 | 같음(256 MiB 초과 제외) |

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
  - Thrift compiler와 통신 라이브러리는 반드시 같은 0.25.0이어야 합니다(다르면 서로 맞지 않음).
  - 새 Thrift에는 원본 시절과 다른 기본 크기 한도가 있어, [새 설정 키](#새-설정-키) 두 개로 한도를 정합니다.
  - Thrift의 thread 구현과 라이브러리가 달라졌으므로, stack 크기와 운영 성능까지 같다고 가정하지 마세요.
- **fb303 patch.**
  - Thrift 0.25.0에 든 fb303 코드는 카운터를 새로 추가하다 메모리 할당에 실패하면 카운터 잠금을 풀지 않았습니다.
    그러면 그 뒤로 카운터 조회가 영원히 멈춥니다.
  - 이 프로젝트의 patch는 잠금이 자동으로 풀리게 해 이 멈춤을 막습니다.
    카운터 이름·값·조회 방법은 바뀌지 않습니다([fb303 patch](docs/build.md#fb303-patch)).
- **관련 설정 키.** 없습니다.
- **예시.**
  로그를 쓰다 예외가 나고, 그 순간 새 카운터를 추가하던 메모리 할당이 실패했다고 합시다.
  patch 전 fb303에서는 그 뒤 감시 도구의 `getCounters` 호출이 응답 없이 멈춥니다.
  patch한 fb303에서는 잠금이 풀려 다음 호출이 정상으로 답합니다.

#### C++17

- **무엇이 바뀌었나.**
  빌드 파일(`src/Makefile.am`)이 C++17[^cpp17] 표준(`-std=c++17`)을 지정하므로, 원본처럼 `configure` + `make`만 해도 C++17로 빌드됩니다.
- **기존과 달라진 점.**
  `CXXFLAGS`로 다른 언어 판을 주면 그 값이 뒤에 붙어 우선합니다.
  실행 중 동작이나 설정 해석은 바뀌지 않습니다.

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
  - 빌드하는 컴퓨터에는 여전히 [Boost header가 필요합니다](#1-b-rocky-linux-9-패키지-rhel-계열).
  - `configure`의 `--with-boost` 옵션은 없어졌으며, 예전 빌드 스크립트에 남아 있으면 경고만 출력하고 계속합니다.
  - 로그의 분배·내용·파일 형식과 카운터는 같습니다. 파일 함수가 실패했을 때의 진단 로그 문구만 표준 라이브러리 표현으로 바뀔 수 있습니다.
  - 서버 목록을 나누는 새 함수는 개발 중에 Boost 함수와 같은 결과를 내는지 비교했지만, 그 비교 시험은 저장소에 남아 있지 않습니다.
- **관련 설정 키.** 없습니다.
- **예시.**
  구버전 `scribed`는 Boost filesystem·system 라이브러리를 링크하므로 실행 서버에도 이것을 설치해야 했습니다.
  이제 `ldd "$(command -v scribed)"`에 `libboost_*`가 없습니다.
  GCC 8(Rocky 8)은 표준 파일 함수가 별도 라이브러리에 있어, `configure`가 필요할 때만 `libstdc++fs`를 자동으로 붙입니다.

### 고친 원래 버그

원본의 버그 가운데 로그의 분배·파일 형식을 바꾸지 않고 고칠 수 있는 것과, 사용자가 승인한 예외만 고쳤습니다.
항목별 설명과 예시는 [고친 버그와 남긴 버그](docs/behaviour.md#고친-원래-버그)에 있습니다.

- **비정상 종료·미정의 동작·빌드 불가.** 지켜야 할 "원본과 같은 결과"가 없으므로 안전한 동작으로 바꿨습니다. 정상 설정의 결과는 같습니다.
- **논리 오류(동적 목적지, `service_list`, 재전송 일부 성공).** 분배·파일 형식은 같고, 일시 실패·메모리 증가·손실이 줄어듭니다.
- **운영 경계(2026-10-08).** 신호로 정지, 시작 실패의 종료 코드, 동적 category 이름입니다. 2026-10-08 사용자 승인으로 바꿨습니다. 정지 결과·종료 코드·만들 수 있는 폴더가 원본과 다릅니다.

| 문제 | 생기는 설정 | 구버전 | 신버전 |
| --- | --- | --- | --- |
| [spool 읽기 버퍼](docs/behaviour.md#spool-읽기-버퍼의-해제-방식) | buffer의 file secondary | 미정의 동작 | 바르게 해제 |
| [재시도 범위 0](docs/behaviour.md#retry_interval_range0의-0-나누기) | `retry_interval_range=0` | 종료할 수 있음 | jitter 없이 계산 |
| [bucket 하위 store 오타](docs/behaviour.md#알-수-없는-bucket-하위-store-종류) | `type=netwrok` 등 | 종료할 수 있음 | 설정 오류, `WARNING` |
| [기본 port 없음](docs/behaviour.md#list_default_port가-없을-때의-port) | port 없는 `service_list` | 쓰레기 값 | port 0 |
| [추가 bucket 검사](docs/behaviour.md#추가-bucket-검사의-범위-밖-읽기) | `num_buckets` 6 이상 | 범위 밖 읽기 | 검사 건너뜀 |
| [key_range 계산](docs/behaviour.md#key_range-bucket-계산의-범위-밖-접근) | `bucket_range` 2^53 초과 | 범위 밖 bucket | 마지막 bucket |
| [모델 복사본의 큐 포인터](docs/behaviour.md#모델-복사본의-큐-포인터) | `categories=` 등 모델 | 없어진 모델 큐를 가리킴 | 자기 큐를 가리킴 |
| [HDFS 삭제 함수](docs/behaviour.md#hdfs-파일-삭제-함수) | `fs_type=hdfs` | 빌드 불가 | 두 API에 맞춤 |
| [HDFS 파일 handle](docs/behaviour.md#hdfs-파일-handle-정리) | `fs_type=hdfs` | 열린 파일을 닫지 않고 연결을 끊음 | 닫은 뒤 끊음 |
| [종료 시 exit](docs/behaviour.md#종료할-때-exit를-한-번만) | fb303 `shutdown` | 두 곳에서 exit(경쟁 가능) | exit 한 번 |
| [초당 개수 계산](docs/behaviour.md#max_msg_per_second의-동시-계산) | `max_msg_per_second` | 잠금 없이 셈 | 잠금 아래에서 셈 |
| [동적 목적지 변경](docs/behaviour.md#동적-목적지-변경과-연결-pool) | `use_conn_pool=yes` + 동적 조회 | 엉뚱한 연결을 닫음 | 옛 연결만 닫음 |
| [`service_list` 재연결](docs/behaviour.md#service_list-재연결) | `service_list` | 후보 목록이 계속 늘어남 | 매번 새로 만듦 |
| [재전송 일부 성공](docs/behaviour.md#buffer-재전송-일부-성공) | `buffer` + `file` primary 등 | 남은 로그 손실 | spool에 다시 써서 재시도 |
| [SIGTERM·SIGINT](docs/behaviour.md#sigterm과-sigint로-정상-종료) | 모든 설정 | 큐를 처리하지 않고 바로 끝남 | `shutdown`과 같은 정리 뒤 종료 코드 0 |
| [시작 실패 종료 코드](docs/behaviour.md#시작-실패의-종료-코드) | port 사용 중, 잘못된 크기 한도 | 0 | 1 |
| [동적 category의 `..`](docs/behaviour.md#동적-category-이름의-상위-폴더-거부) | `default`·prefix 모델 | `file_path` 밖에 파일을 만들 수 있음 | 거부, `received bad` |

### 코드 정리

- **왜 바꿨나.**
  원본 코드는 잠금과 메모리를 손으로 관리하는 오래된 방식이라, 예외 상황에서 잠금이 풀리지 않거나 메모리가 새는 곳이 있었습니다.
  지금의 C++ 표준 기능으로 같은 일을 하도록 표현을 바꿨습니다.
- **기대할 수 있는 것.**
  설정을 여러 번 다시 읽어도 메모리가 쌓이지 않고, 예외가 나도 잠금이 풀립니다.
- **기존과 달라진 점.**
  정상 동작에서 로그의 분배·내용·파일 형식·전달·손실 집계·상태 조회·설정 해석은 같습니다.
  달라지는 것은 예전에 멈추거나 비정상 종료하던 실패 경로(예외, 메모리 부족, thread 생성 실패)와 아래에 적은 진단 로그 몇 줄입니다.
- **관련 설정 키.** 없습니다.
- **예시.**
  매일 fb303 `reinitialize`로 설정을 다시 읽는 서버는, 예전에는 다시 읽을 때마다 이전 설정이 메모리에 남았습니다.
  이제는 남지 않고, 설정 해석 결과는 같습니다.
- **정리한 항목.**
  - **로그 받기의 잠금.**
    잠금을 손으로 잡고 풀던 코드를, 범위를 벗어나면 자동으로 풀리는 방식(RAII[^raii])으로 바꿨습니다.
    예전에는 중간에 예외가 나면 잠금이 남아 이후 `reinitialize`·`shutdown`·새 category 처리가 멈출 수 있었습니다.
  - **설정 트리의 약한 참조.**
    부모와 자식 설정이 서로를 붙잡고 있어 `reinitialize`마다 이전 설정이 메모리에 남았습니다.
    이제 자식은 부모를 붙잡지 않고 가리키기만 하며(weak reference), 설정 상속 결과는 같습니다.
  - **store 큐의 잠금.**
    큐에 메시지나 명령을 넣는 동안 잡는 잠금도 범위를 벗어나면 자동으로 풀립니다.
    예전에는 넣는 중 메모리 부족 예외가 나면 큐 잠금이 남아 그 category의 로그 받기와 store thread가 멈출 수 있었습니다.
    잠그는 순서와 범위는 같습니다.
  - **store 큐의 생성 실패와 상태 조회.**
    새 category의 큐를 만든 직후 등록 중에 메모리 부족이 나면, 예전에는 store thread가 도는 채로 큐가 사라져 비정상 종료할 수 있었습니다.
    이제 큐는 사라지기 전에 store thread를 끝내고 기다리며, 처음 열기 전에 끝난 store는 닫지 않습니다.
    fb303 상태 조회는 store가 처음 열리기 전에는 그 store를 문제없음으로 보고 기다리지 않으며, 연 뒤에는 상태를 잠금 없이 읽습니다.
    원본은 열기 전의 짧은 순간에 buffer store의 상태를 읽다 비정상 종료할 수 있었습니다.
  - **복사본의 소유권.**
    multi·category store의 복사본은 하위 store를 복사하기 전에 스마트 포인터가 소유합니다.
    하위 store 복사 중 예외가 나도 부모와 먼저 복사한 하위 store가 새지 않습니다.
  - **표준 잠금.**
    store 상태와 연결 pool 목록의 잠금을 C++ 표준 잠금(`std::mutex`)으로 바꿨습니다.
    잠그는 지점과 범위는 같습니다. 쓰이지 않던 HDFS 잠금 선언은 삭제했습니다.
  - **연결 pool 열기의 대기.**
    `use_conn_pool=yes`에서 연결을 열 때 pool 목록 잠금을 쥔 채 다른 store의 전송이 끝나기를 기다리지 않습니다.
    목록 잠금을 푼 채 그 연결의 상태를 보고, 목록을 다시 확인해 그사이 바뀌었으면 처음부터 다시 판단합니다.
    그래서 한 목적지로 전송 중인 연결이 있어도 다른 목적지의 열기·전송이 멈추지 않습니다. 전송의 잠금 순서(목록 → 연결)는 같습니다.
  - **컴파일러 검사 강화.**
    함수를 잘못 덮어쓰거나 복사하면 빌드할 때 오류가 나게 했습니다(`override`, `= delete`).
    만들어지는 실행 파일의 동작은 같습니다.
  - **전역 의존 제거.**
    예전에는 store·큐·연결 pool·설정 조회가 프로세스 전체에 하나뿐인 전역 변수를 직접 읽었습니다.
    이제 서버가 카운터·큐 한도·크기 한도·연결 pool을 담은 "context"를 만들어 각 부품에 넘겨줍니다.
    부품을 서버 전체 없이 따로 시험할 수 있게 됐고, 서버 하나에 context 하나이므로 값·카운터·연결 공유 범위는 같습니다.
  - **그 밖의 정리.**
    설정 값을 읽는 무리한 형 변환, 실행되지 않던 검사, 쓰지 않는 코드를 정리했습니다.
    store thread를 만들지 못하면(원래 미정의 동작) 이제 `Bad config - can't create a store of type: ...` 설정 오류가 됩니다.
    처음 보는 category의 store를 모델에서 만들지 못하면(thread·잠금 생성 실패, 모델 복사 실패) `failed to create category store from model`을 남기고 그 요청에 `TRY_LATER`를 돌려주며 `denied for store creation` 카운터를 올립니다. 앞선 모델로 만든 store는 멈추고 등록을 되돌리므로 client가 다시 보내면 처음부터 다시 만듭니다.
    원본은 thread 생성 결과를 보지 않아 이때 로그가 조용히 사라졌습니다. `..` 조각 거부는 그대로 `received bad`입니다.
    dynamic bucket updater의 "매핑 없음" 진단 로그는 이제 실제 내용을 찍고, 실행될 수 없던 "socket 생성 실패" 로그는 삭제했습니다.
- **일부러 건드리지 않은 것.**
  겉보기에는 고칠 곳 같지만 원본의 관찰 결과를 만드는 코드입니다.
  - 추가 bucket 검사의 문자열 계산과 bucket key 계산 방식
  - 긴 명령행 옵션이 값을 받지 않는 선언(값 없이 들어온 옵션을 읽던 미정의 동작만 [고쳤습니다](docs/behaviour.md#긴-명령행-옵션은-값을-받지-못한다))
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
  - 256 MiB를 넘는 요청만 처리가 다릅니다.
  - **한도를 넘는 relay batch는 나누거나 버리지 않고, 실패로 처리해 계속 다시 시도합니다.**
  - 이 한도는 프로세스 메모리 상한이 아니며, 원본이 받던 모든 큰 요청의 호환을 보장하지도 않습니다.
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
  - 값은 십진수 byte 수로만 씁니다. `0`, 음수, `+` 부호, 16진수, `256M` 같은 단위는 잘못된 값입니다.
    시작할 때 값이 잘못됐으면 `Invalid Thrift wire limits; listener not started`를 남기고 끝납니다([종료 코드 1](docs/behaviour.md#시작-실패의-종료-코드)).
  - 바꾼 값은 재시작해야 적용됩니다.
    fb303 `reinitialize`도 두 값을 다시 읽어 검사합니다. 값이 바뀌었으면 `Thrift wire-limit changes require restart`를 남기고 기존 값을 유지합니다.
    `reinitialize` 때 값이 잘못됐으면 설정 다시 읽기가 실패해, 고친 설정으로 다시 `reinitialize`할 때까지 store가 하나도 없는 `WARNING` 상태가 됩니다.
  - 신버전 network store는 보내기 전에 요청 크기를 계산합니다.
    요청 전체에 21 bytes, 메시지마다 15 bytes + category 길이 + 메시지 길이입니다.
    한도를 넘으면 `Relay Log exceeds configured wire limit <268435456> bytes`를 남기고 일시 실패로 처리합니다.
    buffer store 아래라면 가장 오래된 spool 파일부터 보내므로, 그 파일이 한도를 넘으면 뒤의 spool 파일도 모두 멈춥니다.
- **예시.**
  spool 파일 하나가 재전송 요청 하나가 되고, 재전송 요청은 메시지마다 category 이름만큼 spool 파일보다 커집니다.
  그래서 짧은 메시지가 많은 category는 spool 파일(secondary `max_size`)이 128 MiB여도 요청이 256 MiB를 넘을 수 있습니다.

  | 평균 메시지 길이 | 128 MiB spool 파일의 재전송 요청 크기 | 256 MiB 한도 |
  | --- | --- | --- |
  | 12 bytes | 약 280 MiB | **넘음: 계속 재시도** |
  | 30 bytes | 약 200 MiB | 통과 |

  - 이런 category는 secondary `max_size`를 64 MiB(`67108864`) 이하로 잡으세요.
  - secondary에 `max_size`를 쓰지 않으면 기본값 1,000,000,000 bytes라, 장애가 길어지면 256 MiB를 넘는 spool이 생길 수 있습니다.
  - 한도를 올리려면 받는 서버도 그 크기를 받을 수 있어야 합니다.
- **확인한 호환성.**
  구·신 서버 사이의 전송과 일반 spool·ThriftFile 파일의 양방향 읽기는 대표적인 작은 로그로만 확인했고, 256 MiB 근처의 큰 요청은 구·신 비교에 없습니다.
  근거는 [호환성 정책](docs/compatibility-policy.md#통신-크기-한도), [ThriftFile 처리 기록](docs/compatibility-policy.md#thriftfile-chunk-초과와-empty), [검증 기록](docs/verification.md)에 있습니다.

## 일부러 남겨 둔 원래 버그

기준은 [공개 Facebook Scribe 원본](https://github.com/facebookarchive/scribe/tree/fcd294faffd1e88af1643a3a8c2359c41713f7c2)입니다.

- 아래 항목은 원본의 버그지만, 고치면 로그의 저장 위치·내용·형식, 전달 여부, 상태 조회 결과가 바뀝니다.
- 그 결과를 읽는 기존 프로그램(적재·집계 job, 감시 도구)을 지키려고 **구버전과 신버전이 똑같이 동작하도록 남겼습니다.** 고치는 새 옵션도 없습니다.
- 원본이 비정상 종료하던 경우는 남기지 않았습니다([고친 원래 버그](#고친-원래-버그)).
- 항목마다 어떤 동작인지, 왜 남겼는지, 구·신 차이, 관련 설정 키, 예시는 [고친 버그와 남긴 버그](docs/behaviour.md#일부러-남겨-둔-원래-버그)에 있습니다.

### 먼저: 모델과 복사본

- **모델.** `category=default`, `categories=a b c`, `category=game_*`(끝이 `*`인 prefix)로 쓴 `<store>`입니다.
- **복사본.** 기본값 `new_thread_per_category=yes`에서는 category마다 만든 모델의 복사본이 로그를 처리합니다.
  `categories=`의 이름들은 시작할 때, `default`와 prefix는 그 category의 첫 로그가 들어올 때 복사합니다.
- **복사본의 file store.** `base_filename` 대신 category 이름을 쓰고, 파일은 `<file_path>/<category>/`에 생깁니다([예시](docs/behaviour.md#먼저-모델과-복사본)).

| 항목 | 기대할 것 | 관련 설정 키 |
| --- | --- | --- |
| [Bucket 복사본](docs/behaviour.md#bucket-복사본은-bucket_range와-remove_key를-물려받지-않는다) | 범위 분배·key 제거를 하지 않음. `key_range`면 모두 bucket 0 | `bucket_range`, `remove_key` |
| [추가 bucket 검사](docs/behaviour.md#추가-bucket-검사는-이름-대신-문자열-중간을-본다) | `num_buckets`보다 많은 bucket 블록도 거부하지 않고, 넘치는 bucket은 로그를 받지 않음 | `num_buckets`, `bucket0`…`bucketN` |
| [ThriftFile 복사본](docs/behaviour.md#thriftfile-복사본은-use_simple_file을-무시한다) | 항상 framed 형식 | `use_simple_file` |
| [Network 복사본](docs/behaviour.md#network-복사본은-service_list와-동적-조회-설정을-물려받지-않는다) | `service_list` 모델의 복사본은 로그를 전달하지 못함 | `service_list` 등 6개 |
| [Buffer 복사본](docs/behaviour.md#buffer-복사본은-flush_streaming과-buffer_bypass_max_ratio를-물려받지-않는다) | 재전송 중 새 로그도 spool을 거침 | `flush_streaming`, `buffer_bypass_max_ratio` |
| [빈 연결 key 공유](docs/behaviour.md#service_list와-use_conn_pool은-빈-연결-key-하나를-같이-쓴다) | 목록이 서로 다른 `service_list` store가 먼저 열린 연결 하나를 같이 씀 | `service_list`, `use_conn_pool` |
| [빈 메시지만 든 큐](docs/behaviour.md#빈-메시지만-든-큐는-전달되지-않는다) | `OK`와 `received good`이어도 파일에 남지 않음 | `add_newlines`(영향) |
| [OK의 뜻](docs/behaviour.md#ok는-메모리-큐에-받았다는-뜻이다) | 메모리 큐에 받았다는 뜻. 디스크 저장·전달·중복 없음을 보장하지 않음 | 없음 |
| [긴 명령행 옵션](docs/behaviour.md#긴-명령행-옵션은-값을-받지-못한다) | 값을 받지 못하므로 `-c`, `-p`를 씀 | `--config`, `--port` |

### 원본 그대로인 주의점

버그라기보다 원본 설계에서 나오는 동작이며, 구버전과 신버전이 같습니다.

| 항목 | 기대할 것 |
| --- | --- |
| [prefix 우선순위](docs/behaviour.md#prefix는-가장-긴-것이-아니라-정렬-순서상-첫-번째가-이긴다) | 가장 길게 맞는 prefix가 아니라 정렬 순서상 첫 번째가 받음 |
| [category마다 thread](docs/behaviour.md#new_thread_per_category-기본값은-category마다-thread를-만든다) | category 수만큼 store thread와 열린 파일이 생김 |
| [secondary의 `add_newlines`](docs/behaviour.md#buffer-secondary의-add_newlines는-재전송-때-줄바꿈을-하나-더-만든다) | spool을 거친 로그에 LF가 하나 더 붙음 |
| [spool 파일과 재전송 요청](docs/behaviour.md#spool-파일-하나가-log-요청-하나로-재전송된다) | spool 파일 하나가 요청 하나. 받는 서버의 `max_queue_size`를 넉넉히 |
| [`max_queue_size`](docs/behaviour.md#max_queue_size는-모든-category를-한꺼번에-본다) | 한 category의 큐가 넘쳐도 요청 전체가 `TRY_LATER` |
| [`max_msg_per_second`의 절반 예외](docs/behaviour.md#max_msg_per_second의-절반-예외) | 한도의 절반보다 많은 메시지를 담은 요청은 항상 받음 |
| [`#` 주석](docs/behaviour.md#주석-기호-은-줄-어디에서나-동작한다) | 줄 중간의 `#` 뒤도 주석이라 값 안에 `#`을 쓸 수 없음 |
| [`use_conn_pool`](docs/behaviour.md#use_conn_pool은-host와-port마다-tcp-연결-하나를-공유한다) | 같은 `host:port` 문자열이면 TCP 연결 하나를 같이 씀 |
| [`check_interval`](docs/behaviour.md#check_interval이-회전-검사와-재시도-주기를-정한다) | 회전 검사·재연결·재전송이 이 주기를 따름 |
| [빈 메시지가 든 spool](docs/behaviour.md#빈-메시지가-든-spool은-재전송이-중간에-멈출-수-있다) | 길이 0 frame 뒤의 메시지는 전달되지 않고 `lost`도 늘지 않음 |
| [그 밖의 주의점](docs/behaviour.md#그-밖의-주의점) | 정의하지 않은 category, `TRY_LATER`의 예외, HDFS의 `_current`와 재전송 |

## 관련 문서

| 문서 | 내용 |
| --- | --- |
| [검증 기록](docs/verification.md) | 검증 도구, 구·신 비교 case별 입력·기대값, 실행 기록, 아직 하지 않은 검증 |
| [구버전 비교 환경](tools/old-lane/README.md) | 구버전 재현 빌드와 비교를 다시 돌리는 명령 |
| [고친 버그와 남긴 버그](docs/behaviour.md) | 고친 원래 버그와 일부러 남긴 원래 버그의 항목별 설명과 예시 |
| [호환성 정책](docs/compatibility-policy.md) | 원본 동작을 지키기로 한 결정, 남은 버그, 일반 spool의 손실 경로 |
| [빌드 안내](docs/build.md) | 의존성 경로, 배포판별 확인 범위, 검증 준비, fb303 patch, Rocky 빌드·RPM, Python client |
| [Docker 안내](docs/docker.md) | 이미지 구성·실행·정지·제한 |
| [HDFS 안내](docs/hdfs.md) | 선택 기능의 빌드·실행 범위, Rocky HDFS |
| [설계](docs/design.md) | 원본 구조와 개발 방향 |
| [문서 안내](docs/README.md) | docs 폴더의 문서 목록 |

## 라이선스

- [Apache License 2.0](LICENSE)을 따르며, 원본 Facebook Scribe의 저작권과 고지를 보존합니다.
- 재배포할 때는 LICENSE, 변경한 파일의 수정 고지, 필요한 원본 고지를 포함해야 합니다.
- Docker 실행 이미지에는 Scribe LICENSE와 함께 Thrift의 LICENSE/NOTICE, fb303의 LICENSE를 `/usr/share/licenses/scribe-next/`에 넣었습니다.
- 다른 방식으로 의존성 라이브러리를 함께 배포한다면 각 라이브러리의 LICENSE/NOTICE를 따로 확인하세요.

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
  기본은 정적 라이브러리이며, `--disable-static`을 주면 정적 대신 공유 라이브러리로 빌드합니다.
[^libevent]: libevent: 많은 네트워크 연결을 적은 thread로 처리하도록 돕는 C 라이브러리입니다.
  Thrift의 서버가 사용합니다.
[^boost]: Boost: C++에서 널리 쓰는 공개 라이브러리 모음입니다.
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
  클라이언트가 요청을 다시 보내야 합니다([예외](docs/behaviour.md#그-밖의-주의점)).
[^cpp17]: C++17: 2017년에 정해진 C++ 언어 표준입니다.
  컴파일러에 이 판을 지정하면, 그 판의 문법과 표준 라이브러리로 빌드합니다.
[^smartptr]: 스마트 포인터: 메모리를 다 쓰면 자동으로 돌려주는 C++ 도구입니다.
  손으로 돌려주다 빠뜨려 메모리가 새는 일을 막습니다.
[^raii]: RAII: 자원(잠금, 메모리 등)을 만들 때 얻고, 범위를 벗어나면 자동으로 돌려주는 C++ 방식입니다.
  중간에 예외가 나도 자원이 풀립니다.
