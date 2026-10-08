# 빌드와 설치

기본 설치 순서는 README의 [설치](../README.md#설치)에 있다.
이 문서는 의존성 사실, 직접 autotools 빌드, 검증기 준비, fb303 patch, Rocky·RPM, Python client를 다룬다.

## 의존성

- Linux x86_64, C++17이다. `src/Makefile.am`의 `AM_CXXFLAGS`가 `-std=c++17`을 주고, 사용자 `CXXFLAGS`의 표준 지정이 우선한다
- Thrift compiler와 C++ runtime은 같은 0.25.0이어야 한다. libthrift와 libthriftnb(libevent 지원)를 쓴다
- fb303은 같은 Thrift 0.25.0 source의 `contrib/fb303`에 [patch](#fb303-patch)를 적용해 빌드한다
- Boost는 header만 필요하다. Thrift 0.25.0 C++ 빌드와 Thrift·fb303 header가 Boost header를 include한다
- scribed는 Boost 라이브러리를 링크하지 않고 configure에 `--with-boost`도 없다. 예전 스크립트에 남은 `--with-boost`는 경고만 내고 계속한다
- 검증기의 C++03 원본 비교 기준은 `TOOLS_PREFIX`의 Boost filesystem을 링크한다
- libevent는 배포판 것을 쓴다
- GCC 8은 `std::filesystem`에 `-lstdc++fs`가 필요하며 configure가 확인해 붙인다
- Rocky 8의 bison 3.0.4는 Thrift 빌드가 쓰는 `--file-prefix-map`을 지원하지 않는다. bison 3.8.2가 필요하다
- `tools/prepare_fb303.py`와 검증기는 Python 3.9 이상이 필요하다(`Path.is_relative_to`). Rocky 8 기본 `python3`는 3.6이므로 `python3.12` 패키지로 실행한다
- 기본 RPC library는 정적이다. scribed는 완전 정적 실행 파일이 아니므로 실행할 때 Thrift·libevent를 찾아야 한다

## 확인한 환경

| 환경 | 컴파일러 | 확인 | 날짜 |
| --- | --- | --- | --- |
| Rocky 9.8 | GCC 11.5 | `9e8d775`에서 검증기 240 tests, 구·신 비교 | 2026-10-07 |
| `ubuntu:24.04`, `rockylinux:9` | GCC 13.3, 11.5 | `9e8d775` README(`git clone` 방식)의 설치 순서 | 2026-10-07 |
| Rocky 8.10 | GCC 8.5 | Boost 제거 단계(`1e66160`) 검증기 236 tests, 개발 RPM | 2026-10-07 |
| Rocky 8.10, 9.8 | GCC 8.5, 11.5 | 기본·shared 218 tests, HDFS 220 tests | 2026-10-06 |
| Debian 13 | GCC 14.2 | 기본·shared 빌드와 시험, HDFS 빌드·local JNI | 2026-10-05 |
| Ubuntu 26.04.1 | GCC 15.2 | 기본·shared 빌드와 시험, HDFS | 2026-10-05 |
| Rocky 9 Docker 검증 이미지(WSL) | GCC 11.5 | `0afe2b4` 검증기 241 tests; `acc7edd` 검증기 241 tests, 구·신 비교 17개 case, Docker smoke([검증](verification.md#0afe2b4와-acc7edd의-재확인-2026-10-07)) | 2026-10-07 |
| Rocky 9 Docker 검증 이미지(WSL) | GCC 11.5 | `f2494d4`(src는 `e2fe61a`와 같음) 검증기 241 tests, 구·신 비교 22개 case, performance, Docker smoke([검증](verification.md#재검증-2026-10-08)) | 2026-10-08 |

첫 두 행은 `9e8d775`에서 잰 것이다. 그 뒤 코드를 바꾼 PR #63(`28a4d9a`), PR #65(`e4bb4cc`)를 합친 `0afe2b4`와 리뷰 수정 `acc7edd`는 마지막 행의 Rocky 9 Docker 이미지에서만 다시 확인했다.
지금 README의 설치 명령(`SCRIBE_SRC`, `curl` 추가, 기록 목록 기반 삭제)도 실행 기록이 없다.
Rocky 8.10의 Boost 제거 단계 확인은 3단계(context 주입) 전이다.
GCC 14·15에서는 2026-10-07 현대화 단계를 다시 확인하지 않았다.

## 직접 빌드

README 설치와 같은 흐름을 별도 prefix로 할 때의 예다.
설치는 별도 `DESTDIR`에서 확인한다.

```sh
export THRIFT_PREFIX=/absolute/thrift-0.25.0
export FB303_PREFIX=/absolute/fb303-0.25.0
export TOOLS_PREFIX=/absolute/tools/usr
export TOOLS_LIBDIR="$TOOLS_PREFIX/lib/x86_64-linux-gnu"   # Debian·Ubuntu multiarch. Rocky의 /opt/tools는 "$TOOLS_PREFIX/lib"
cd /absolute/fresh/source-copy
CPPFLAGS="-I$TOOLS_PREFIX/include -I$TOOLS_PREFIX/include/x86_64-linux-gnu" \
CXXFLAGS="-O2 -std=c++17 -D_GLIBCXX_USE_DEPRECATED=0" \
LDFLAGS="-L$TOOLS_LIBDIR -L$THRIFT_PREFIX/lib -L$FB303_PREFIX/lib -Wl,-rpath,$TOOLS_LIBDIR -Wl,-rpath,$THRIFT_PREFIX/lib -Wl,-rpath,$FB303_PREFIX/lib" \
sh ./bootstrap.sh --prefix=/opt/scribe \
  --with-thriftpath="$THRIFT_PREFIX" --with-fb303path="$FB303_PREFIX"
make clean
make -j2
src/scribed --help
make install DESTDIR=/absolute/new-stage
```

- `CPPFLAGS`의 `$TOOLS_PREFIX/include`는 Thrift·fb303 header가 include하는 Boost header 위치다
- `bootstrap.sh`는 autoreconf 뒤 `configure --config-cache`를 실행하고 받은 인자를 경계 그대로 넘긴다. autoreconf가 실패하면 멈춘다
- `--config-cache` 때문에 같은 폴더에서 `CPPFLAGS` 같은 precious 변수를 바꿔 다시 실행하면 configure가 cache 불일치로 멈춘다. 그때는 `config.cache`를 지우고 다시 실행한다
- generated Thrift source는 `src/Makefile.am`의 `BUILT_SOURCES`라 `make`가 먼저 만든다
- 사용자 `CFLAGS`/`CXXFLAGS`의 명시값과 빈 값을 보존한다. 지정하지 않을 때만 기본 opt·debug 값을 쓴다
- generated code는 make 규칙으로 생성하고 손으로 고치지 않는다
- 두 IDL에는 constants가 없어 Thrift 0.25.0이 만들지 않는 `*_constants.cpp`를 source 목록에서 뺐다
- 원본 configure의 중복 `AM_INIT_AUTOMAKE`는 `foreign -Wall 1.9.5 no-define` 한 번으로 합쳤다
- HDFS의 `--enable-hdfs --with-hadooppath=...`는 [HDFS](hdfs.md)를 따른다

## 검증기

`tools/validate_linux.py`는 프로젝트 밖 새 폴더에서 빌드, 전체 시험, 임시 설치, 설치된 `scribed --help`를 확인한다.
의존성 자동 설치, download, sudo, 시스템 설치, 서비스 기동은 하지 않는다.
단계별 검사는 [검증](verification.md#검증기-단계)에 있다.

```sh
export THRIFT_PREFIX=/absolute/thrift-0.25.0
export FB303_PREFIX=/absolute/fb303-0.25.0
export TOOLS_PREFIX=/absolute/tools/usr
export THRIFT_PYTHON_SOURCE=/absolute/thrift-0.25.0-source/lib/py/src
python3 -B tools/validate_linux.py --output /absolute/new-validation-directory
```

| 변수 | 뜻 |
| --- | --- |
| `THRIFT_PREFIX` | Thrift 0.25.0 설치 prefix. `bin/thrift --version`이 0.25.0이어야 한다 |
| `FB303_PREFIX` | patch한 fb303 설치 prefix |
| `TOOLS_PREFIX` | Boost header와 C++03 기준용 Boost filesystem |
| `THRIFT_PYTHON_SOURCE` | 같은 Thrift source의 `lib/py/src` |

- `--output`은 checkout 밖의 아직 없는 경로다. `build/`, `stage/`, `logs/`, `home/`, `test-results.json`, `validation.json`을 만든다
- `CPPFLAGS`·`CXXFLAGS`·`LDFLAGS`를 주지 않으면 C++17 기본값과 prefix 경로를 쓴다. 준 값과 빈 값은 덮어쓰지 않는다
- 상속된 `PYTHON_SETUPUTIL_ARGS`, make override(`MAKEFLAGS` 등), 추가 Python 설정(`DIST_EXTRA_CONFIG`, `lib/py`의 `setup.cfg`·`pyproject.toml`)은 거부한다. `HOME`은 `output/home`으로 분리한다
- 검증기는 `PYTHON_SETUPUTIL_ARGS`를 따로 넣지 않는다. Python install은 Makefile 그대로 `--record installed_files.txt`로 설치 목록을 남기고 `make uninstall`이 그 목록을 쓴다. `test/test_python_packaging.py`가 임시 `DESTDIR`에서 이 install·uninstall을 실행한다
- C++ prefix `/opt/scribe`와 Python prefix `/usr`의 실제 설치 대상은 언제나 `stage/` 아래다
- 원본 Git object가 있어야 한다([준비](#원본-git-object-준비))
- `--shared-rpc`는 [shared RPC](#shared-rpc), `--hadoop`·`--java-home`은 [HDFS](hdfs.md) lane이다

## 원본 Git object 준비

검증기는 현재 Git checkout과 고정 원본 commit object를 함께 쓴다.
ZIP이나 파일만 복사한 폴더로는 실행할 수 없다.
원본 object가 없으면 처음 한 번 공식 upstream에서 명시적으로 가져온다.

```sh
git --no-replace-objects --no-lazy-fetch --version && \
git fetch https://github.com/facebookarchive/scribe.git fcd294faffd1e88af1643a3a8c2359c41713f7c2:refs/remotes/upstream/baseline && \
git --no-replace-objects --no-lazy-fetch cat-file -e 'fcd294faffd1e88af1643a3a8c2359c41713f7c2^{commit}'
```

- 첫 명령이 옵션 미지원으로 실패하면 두 보호 옵션을 지원하는 Git을 준비한다
- 검증기는 보호 옵션을 빼거나 자동 fetch로 대신하지 않는다. 미지원 Git과 누락 object를 구분해 보고한다

## shared RPC

- 원본 선택은 `--disable-static`이다(`--disable-shared`가 아니다)
- 검증기 `--shared-rpc`는 이 선택만 전달한다. 기본 static, 빌드 규칙, C++, IDL은 바꾸지 않는다
- 검증기는 configured LTYPE, stage의 `libscribe.so`·`libdynamicbucketupdater.so`가 build 결과와 같은지, 설치된 help가 그 두 `.so`를 읽는지 확인한다(9단계)
- 실행하는 곳에서 두 `.so`와 matching Thrift를 찾을 수 있어야 한다. 빌드한 머신의 절대 경로가 다른 머신에서 유효하다고 가정하지 않는다
- 구·신 shared daemon 비교와 shared RPM은 없다

## fb303 patch

Thrift 0.25.0 `contrib/fb303/cpp/FacebookBase.cpp`(SHA256 `ac791badf8210c68694153fb507202b0ea4ef7baf0d5303b4d91f12ceabddcae`)의 counter 함수는 수동으로 잠근다.
`incrementCounter`·`setCounter`는 `counters_.lock()` 뒤 새 map node 할당이 실패하면 unlock을 건너뛴다.
`getCounters`도 반환 map 할당에서 같다.
그 뒤 counter 조회가 영원히 멈춘다. 실제 `Log` 쓰기 예외의 stack에서 확인했다.
2026-10-06 기준 공식 master(`50bbda109593a0b5c7634ac21c5d98eee97fe7ec`)의 같은 파일도 hash가 같다.

[patch](../dependencies/fb303-0.25.0-counter-lock.patch)는 네 counter 함수의 map·value 잠금을 Thrift `Guard`가 소유하게 한다.

- map → value 획득, value → map 해제 순서를 유지한다
- 값 연산, 정상 counter 결과, 오류 전까지의 partial snapshot, header, IDL, ABI, version은 바꾸지 않는다
- [회귀](../test/test_fb303_counter_safety.py)는 새 increment, 새 set, snapshot의 할당 실패를 주입한다. patch 전 archive는 세 경우 모두 후속 read가 2초 안에 끝나지 않았다

공식 archive·release tree·system package는 고치지 않는다.
[helper](../tools/prepare_fb303.py)가 입력 cpp·header hash를 확인하고 새 복사본에만 patch를 적용한다.

```sh
# THRIFT_SOURCE: 압축을 푼 thrift-0.25.0 source 폴더. FB303_BUILD: 아직 없는 새 작업 폴더(부모는 있어야 한다)
# THRIFT_PREFIX, FB303_PREFIX, TOOLS_PREFIX: 위 직접 빌드와 같다
python3 -B tools/prepare_fb303.py --source "$THRIFT_SOURCE/contrib/fb303" --output "$FB303_BUILD"
cd "$FB303_BUILD"
aclocal -I ./aclocal && automake -a --copy && autoconf
./configure --prefix="$FB303_PREFIX" --with-thriftpath="$THRIFT_PREFIX" \
  --with-boost="$TOOLS_PREFIX" --without-java --without-php --without-python
make clean
make -j2 CXXFLAGS='-O2 -std=c++17' \
  CPPFLAGS="-I$THRIFT_PREFIX/include -I$TOOLS_PREFIX/include"
make install
mkdir -p "$FB303_PREFIX/share/scribe-next"
cp scribe-next-fb303-safety.json "$FB303_PREFIX/share/scribe-next/fb303-safety.json"
```

- `fb303-safety.json`은 원본 cpp·header, patch, patch 뒤 cpp의 hash를 기록한다. 검증기는 있으면 `dependency_files`에 기록하고 없으면 없다는 사실을 기록한다. 필수가 아니며 hash를 대조하지 않는다
- 이미 만든 Rocky 검증 이미지를 다시 쓸 때는 [Dockerfile.fb303-safety](../tools/rocky/Dockerfile.fb303-safety)가 새 layer에서 private fb303 prefix만 다시 만든다
- 그 Dockerfile의 기본 `BASE`(`scribe-next-rocky-validation:8-20261006`)는 [Rocky 절](#rocky-linux-8과-9)의 recipe가 만들지 않는 tag다. 그 recipe의 `scribe-next-rocky-validation:$MAJOR`를 `BASE`로 준다

```sh
# CONTEXT에 Dockerfile.fb303-safety, prepare_fb303.py, fb303 patch. MAJOR: 8 또는 9
docker build -f "$CONTEXT/Dockerfile.fb303-safety" \
  --build-arg BASE="scribe-next-rocky-validation:$MAJOR" \
  -t "scribe-next-rocky-validation-fb303:$MAJOR" "$CONTEXT"
```

## Rocky Linux 8과 9

이 절은 Docker 검증 이미지 recipe다. 이 저장소에 기록된 Rocky 8·9 확인은 모두 이 이미지의 컨테이너에서 했다.
Rocky 8 host에 직접 설치할 때는 [Dockerfile](../tools/rocky/Dockerfile)처럼 bison 3.8.2를 source로 만들어 `PATH` 앞에 두고, Python 스크립트는 `python3.12`로 실행한다. 이 host 순서 자체는 실행 기록이 없다.

RESF의 `rockylinux/rockylinux` 이미지를 digest로 고정한다.

- Rocky 8: `rockylinux/rockylinux@sha256:e8a49c5403b687db05d4d67333fa45808fbe74f36e683cec7abb1f7d0f2338c6`
- Rocky 9: `rockylinux/rockylinux@sha256:8101994123cf3d0a8fee517bee7f39e555c7d92bd2d9eb3303cc988a0eeed00f`

build context에는 아래 공식 archive, Dockerfile, `prepare_fb303.py`, fb303 patch만 둔다.
checkout과 인증 파일은 넣지 않는다.
SHA256은 [Dockerfile](../tools/rocky/Dockerfile)이 검사한다. GPG 서명 검증은 아니다.

| archive | 공식 위치 |
| --- | --- |
| Thrift 0.25.0 | https://archive.apache.org/dist/thrift/0.25.0/thrift-0.25.0.tar.gz |
| Boost 1.83.0 | https://archives.boost.io/release/1.83.0/source/boost_1_83_0.tar.bz2 |
| Git 2.53.0 | https://www.kernel.org/pub/software/scm/git/git-2.53.0.tar.xz |
| Bison 3.8.2 | https://ftp.gnu.org/gnu/bison/bison-3.8.2.tar.xz |

- Rocky 8은 `BUILD_BISON=1`로 bison 3.8.2를 `/opt/bison-3.8.2`에 만든다. Rocky 9는 기본 bison 3.7.4로 되며 `BUILD_BISON=0`이다
- 배포판 Git 대신 두 보호 옵션을 지원하는 Git 2.53.0을 만든다
- `/opt/tools`의 Boost는 Thrift 빌드용 header와 C++03 기준용 filesystem 라이브러리로만 쓴다
- sanitizer 시험에는 `libasan`·`libubsan` 패키지가 필요하다([Dockerfile.validation-runtime](../tools/rocky/Dockerfile.validation-runtime)). 없으면 시험이 실패한다

```sh
# CONTEXT: archives, Dockerfiles, prepare_fb303.py, fb303 patch. CHECKOUT: Git checkout
# OUTPUT: CHECKOUT 밖의 쓰기 가능한 기존 폴더. BASE: 위 digest. MAJOR: 8 또는 9
docker build --build-arg BASE="$BASE" --build-arg BUILD_BISON="$BUILD_BISON" \
  -t "scribe-next-rocky-toolchain:$MAJOR" "$CONTEXT"
docker build -f "$CONTEXT/Dockerfile.validation-runtime" \
  --build-arg BASE="scribe-next-rocky-toolchain:$MAJOR" \
  -t "scribe-next-rocky-validation:$MAJOR" "$CONTEXT"
docker run --rm --network none --user "$(id -u):$(id -g)" \
  --cap-drop ALL --security-opt no-new-privileges --cpus 2 --memory 6g --pids-limit 512 \
  --mount "type=bind,src=$CHECKOUT,dst=/validation-input,readonly" \
  --mount "type=bind,src=$OUTPUT,dst=/validation-output" \
  "scribe-next-rocky-validation:$MAJOR" \
  python3.12 -B tools/validate_linux.py --output /validation-output/new-result
```

- 검증기의 `dependency_files`는 `THRIFT_PREFIX`의 `bin/thrift`·`lib/libthrift*`, `FB303_PREFIX`의 `lib/libfb303*`·`share/scribe-next/fb303-safety.json`, `TOOLS_PREFIX` 안 libevent 파일을 기록한다. 배포판 loader closure는 `ldd`와 `rpm -qf`로 따로 본다
- 다른 무거운 빌드와 동시에 돌리면 loopback 시험 1~2개가 fixture 종료 5초 제한을 넘을 수 있다. Boost 제거 전 `main`(`f09d68e`)에서도 재현된 기존 간헐 문제다
- 컨테이너는 host kernel을 공유한다. Rocky host kernel 자체의 검증이 아니다

## Rocky 개발 RPM

[spec](../packaging/rocky/scribe-next-dev.spec)은 daemon 전용 `scribe-next-dev`다.

- version은 원본 1.5.0, release는 `0.1.g<revision 7자리>.el8`/`.el9`다. 서명하지 않은 개발 RPM이다
- payload는 `/opt/scribe-next-dev`, CLI는 `scribed`다. 기본 env_default·비-HDFS·static RPC다
- Python client, 설정, user·group, service unit, scriptlet은 넣지 않는다
- Thrift 0.25.0 runtime과 patch한 fb303을 private `deps` prefix에 빌드해 링크한다. Boost runtime은 넣지 않는다
- libevent, glibc, libgcc, libstdc++는 배포판 의존성이다. 자동 Requires/Provides와 `bundled(thrift/fb303)`를 유지하고 `--nodeps`를 쓰지 않는다
- Rocky 8은 libevent soname 6, Rocky 9는 7이다. 각 RPM은 그 major용이다
- Scribe LICENSE, Thrift LICENSE/NOTICE, fb303 LICENSE, Apache license/NOTICE 6개를 `%license`로 넣고 [기대 hash](../packaging/rocky/expected-licenses.json)와 비교한다

```sh
# MAJOR=8 or 9, BASE는 위 digest. CONTEXT에 packaging Dockerfile, prepare_fb303.py, fb303 patch
# TOP은 새 RPM 출력 폴더
docker build -f "$CONTEXT/Dockerfile.dependencies" \
  --build-arg BASE="scribe-next-rocky-validation:$MAJOR" \
  -t "scribe-next-rocky-rpm-builder:$MAJOR" "$CONTEXT"
docker build -f "$CONTEXT/Dockerfile.runtime" --build-arg BASE="$BASE" \
  -t "scribe-next-rocky-rpm-runtime:$MAJOR" "$CONTEXT"

REVISION=$(git rev-parse HEAD)
SHORT=$(printf '%.7s' "$REVISION")
for d in SOURCES SPECS BUILD BUILDROOT RPMS SRPMS; do mkdir -p "$TOP/$d"; done
git archive --format=tar.gz --prefix=scribe-next-1.5.0/ "$REVISION" \
  > "$TOP/SOURCES/scribe-next-1.5.0.tar.gz"
cp packaging/rocky/scribe-next-dev.spec "$TOP/SPECS/"
docker run --rm --network none --user "$(id -u):$(id -g)" \
  --cap-drop ALL --security-opt no-new-privileges --cpus 2 --memory 6g --pids-limit 512 \
  --mount "type=bind,src=$TOP,dst=/rpmbuild" \
  "scribe-next-rocky-rpm-builder:$MAJOR" rpmbuild -ba \
  --define '_topdir /rpmbuild' --define "source_revision $REVISION" \
  --define "development_release 0.1.g$SHORT" --define "dist .el$MAJOR" \
  --define 'thrift_source /sources/thrift-0.25.0' /rpmbuild/SPECS/scribe-next-dev.spec
```

SRPM은 의존성을 스스로 준비하지 않는다. 위 recipe의 prefix가 필요하다.

[검증 script](../packaging/rocky/verify-container.py)는 컨테이너 안 root에서만 돈다.
`/verify.py`, `/expected-licenses.json`, `/packages`, `/loopback_rpc.py`(기존 `test/loopback_rpc.py`)를 read-only로 붙이고 runtime 이미지의 `/usr/libexec/platform-python -B /verify.py /packages/<rpm>`을 부른다.

- 빈 scriptlet, `rpm -V`, license hash 6개, Boost 없는 loader closure를 확인한다. Requires/Provides는 수집해 결과에 기록만 하고 검사하지 않는다
- 설치된 daemon으로 `ALIVE`, `Log` 응답 `OK`, counter, fb303 `shutdown` 뒤 종료 코드 0과 파일 bytes를 확인한다
- `rpm -U --replacepkgs`로 같은 RPM을 다시 설치해 설정·로그 보존과 재시작 뒤 이어 쓰기를 확인한다
- 제거 뒤 package 폴더와 build-id 링크 3개가 지워지는지 확인한다

2026-10-07 Boost 제거 단계 뒤 Rocky 8.10 RPM을 다시 만들어 위 검사를 모두 통과했다.
Rocky 9 RPM은 fb303 patch와 Boost 제거 뒤 다시 만들지 않았다.
버전 간 upgrade, 비정상 중단, HDFS·shared RPM, 운영 kernel·service 배포는 확인하지 않았다.

## 설치한 파일 직접 삭제

README의 [설치 삭제](../README.md#6-삭제)는 빌드 폴더의 `make uninstall`과 Thrift `install_manifest.txt`를 쓴다.
빌드 폴더를 이미 지웠다면 설치된 파일을 직접 지운다. README 설치 순서가 `/usr/local`에 만드는 파일은 다음이 전부다.

```sh
sudo rm -rf /usr/local/bin/scribed /usr/local/bin/thrift \
  /usr/local/lib/libscribe.a /usr/local/lib/libdynamicbucketupdater.a /usr/local/lib/libfb303.a \
  /usr/local/lib/libthrift.so /usr/local/lib/libthrift.so.0.25.0 \
  /usr/local/lib/libthriftnb.so /usr/local/lib/libthriftnb.so.0.25.0 \
  /usr/local/lib/pkgconfig/thrift.pc /usr/local/lib/pkgconfig/thrift-nb.pc \
  /usr/local/include/thrift /usr/local/lib/cmake/thrift /usr/local/share/fb303
```

- Python package는 `PY_PREFIX`(기본값 `/usr`) 아래 시스템 Python 경로에만 들어간다. 다른 `PY_PREFIX`로 설치했다면 `/usr` 대신 그 값 아래의 `scribe` 폴더를 지운다
- `import scribe`로 경로를 찾으면 가상환경이나 사용자 디렉터리의 다른 package를 지울 수 있으므로 설치 경로를 직접 지정한다
- Rocky는 `site-packages`, Ubuntu는 `dist-packages`다

```sh
sudo rm -rf /usr/lib/python3.*/site-packages/scribe /usr/lib/python3.*/site-packages/scribe-2.0-*.egg-info \
  /usr/lib/python3/dist-packages/scribe /usr/lib/python3/dist-packages/scribe-2.0-*.egg-info
```

저장소 폴더의 빌드 산출물은 `make distclean`으로 다 지워지지 않는다(`configure`, `Makefile.in` 등이 남는다).
`sudo make install`이 root 소유로 만든 `lib/py/scribe.egg-info`도 있으므로 저장소 폴더에서 `sudo git clean -fdx`로 지운다.
commit하지 않은 파일도 함께 지워지므로 먼저 `git clean -ndx`로 목록을 확인한다.

## Python client

- `make install`은 Python package `scribe`(version 2.0)를 `PY_PREFIX`(기본 `/usr`)에 설치한다
- `setup.py`는 이미 설치된 setuptools를 쓰고 현재 IDL 생성 결과(`src/gen-py/scribe`)를 package로 연결한다
- build hook은 phony `pythonstyle`로 package를 생성한 뒤 `build --force`로 누락 출력과 더 새 구 cache를 복구한다
- bucketupdater package는 설치하지 않는다. setuptools는 자동 설치하지 않는다
- 쓰려면 같은 버전의 Thrift Python package(0.25.0)와 fb303 Python module이 필요하다. 이 저장소의 설치 순서는 둘을 설치하지 않는다
- 시스템 Python에 pip로 넣는 경로는 배포판 정책(Ubuntu 24.04의 PEP 668 등)에 막힐 수 있다. 검증한 설치 경로는 없다
- `PY_PREFIX`는 configure 변수다. 별도 prefix에 설치하려면 configure에 `PY_PREFIX=...`를 준다
- Python 3 Thrift string은 UTF-8이다. 임의 non-UTF-8 bytes의 동등성은 보장하지 않는다
- 원본 Python 2 client를 대신하도록 검증하지 않았다. 같은 이름 `scribe` package가 있는 환경에 덮어 설치하지 않는다

2026-10-05에 Python 3.12.14·setuptools 84(site-packages)와 Python 3.14.4·setuptools 78.1.1(dist-packages)의 실제 설치 경로를 확인했다.
sdist·wheel, VPATH, 다른 Python 버전, socket 전송, 기존 언어 client 조합은 확인하지 않았다.
