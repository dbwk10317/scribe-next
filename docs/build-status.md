# 의존성과 빌드 경계의 실제 검증 상태

2026-10-04 · base `00826b8f0ac9288944e7ae56844f926dd654f0bb` · 후속 작업 트리, 아직 commit/push하지 않음

관련 문서: [저장소 안내](../README.md) · [구현 계획](implementation.ko.md) · [원본 도입 기록](source-status.md) · [기계 판독 manifest](build-manifest.json)

> 이 문서는 의존성·빌드 경계 단계의 검증 이력이다. 이후 API 이식으로 scribed clean compile/link에 성공했다. 최신 결과·시험·남은 위험은 [API 이식 기록](api-compat-status.md)을 따른다. 아래의 compile 실패·C++ 미수정·29개 프로젝트 시험 수는 이전 단계의 사실이다.

## 결과 요약

Thrift 0.25.0 compiler/C++ runtime과 fb303를 workspace 전용 경로에 빌드·설치했다. Thrift upstream C++ 시험 29개, 프로젝트 회귀 시험 29개를 각각 통과했다. Scribe의 두 RPC 정적 라이브러리는 빌드되고 생성 client의 링크·메모리 직렬화 smoke 시험도 통과했다.

**Scribe 전체 compile/link는 아직 실패한다.** 첫 오류는 `src/env_default.h`가 현재 Thrift에 없는 `thrift/concurrency/PosixThreadFactory.h`를 포함하는 지점이다. daemon·PHP suite·old/new wire/spool·fault·sanitizer·성능·운영 검증은 실행하지 않았다. Gate A는 시도했으나 미통과이며 B–D는 미실행·미통과다. 의존성 시험 성공을 Scribe 행동 동등성으로 확대하지 않는다.

## 수정한 범위

| 파일 | 기존 문제와 제한된 수정 |
| --- | --- |
| `bootstrap.sh` | autoreconf 실패/도구 부재 뒤 낡은 configure를 실행하던 흐름을 중단. `$*`의 인자 분할·glob 확장을 `"$@"`로 바로잡아 공백·빈 인자 보존 |
| `configure.ac` | 중복 Automake 초기화를 한 번으로 통합. 원래 옵션 `foreign`, `-Wall`, `1.9.5`, `no-define` 보존 |
| `acinclude.m4` | compiler 탐지 전에 caller flag 설정 여부를 기록. 명시한 CFLAGS/CXXFLAGS와 빈 값을 보존하고 미지정 opt/debug 기본값 유지 |
| `src/Makefile.am` | 두 IDL에 constants가 없고 Thrift 0.25.0이 해당 파일을 만들지 않으므로 static/shared source 목록에서 빈 `*_constants.cpp` 요구를 제거 |
| `test/test_build_boundaries.py` | bootstrap 실행·flag 조합 및 실제 Autotools 통합 회귀 시험 |
| `test/test_thrift_generation.py` | 실제 고정 compiler 출력과 각 RPC의 static/shared source 목록을 개별 대조 |

C++·IDL·기존 runtime/시험 소스는 수정하지 않았고 생성 파일을 손으로 고치지 않았다. thread·queue·store·spool 동작이나 protocol 정책을 이 변경에 섞지 않았다. 원본 라이선스·고지는 보존하고 수정한 build 파일에 변경 표시를 남겼다.

## 환경과 의존성 입력

실행 환경은 클라우드 Debian 13 x86_64, GCC 14.2.0, Python 3.12.14, Git 2.52.0, GNU Make 4.4.1이다. 회사 승인 target matrix가 아니다.

시스템 APT는 비루트 환경의 권한·상태 경로 제약으로 실패했다. 승인된 동일 Debian snapshot source와 서명 keyring을 유지하면서 APT 목록·cache·payload 경로만 workspace로 분리했다. 인증된 metadata의 SHA256과 각 `.deb`를 대조한 뒤 필요한 35개 package payload를 작업 폴더에 풀었다. 기존 GCC/libc/Perl을 복제하거나 maintainer script·system install·권한·보안 설정 변경을 하지 않았다. 도구·Perl module·macro·pkg-config·library 경로는 해당 build process에만 적용했다.

직접 요청한 패키지는 아래 11개이며 m4, autotools-dev, 버전별 Boost·libevent 등 필요한 전이 payload와 각 hash는 manifest에 기록했다.

```text
autoconf automake libtool bison flex
libboost-system-dev libboost-filesystem-dev libboost-test-dev
libboost-thread-dev libboost-chrono-dev libevent-dev
```

실제 도구는 Autoconf 2.72, Automake 1.17, Libtool 2.5.4, m4 1.4.19, Bison 3.8.2, Flex 2.6.4다. Boost는 1.83.0, libevent는 2.1.13-stable이다. 기존 OpenSSL 3.5.7·zlib 1.3.1은 추가 설치 없이 C++17 compile/link/실행 probe를 통과했다. Mac/봉구서버 패키지는 변경하지 않았다.

Thrift는 [공식 0.25.0 release](https://thrift.apache.org/download) archive 5,068,440 bytes를 사용했다. [공식 SHA256](https://downloads.apache.org/thrift/0.25.0/thrift-0.25.0.tar.gz.sha256) `66da4707214c54c94bac082103dc67adaf9e08925662700f269170a7b534b214`와 실제 bytes가 일치한다. compiler/runtime은 같은 release이며 `/usr/local` 대신 workspace prefix에 설치했다. 배포판의 다른 Thrift 버전으로 대체하지 않았다.

## 실제 실행한 검증

| 경계 | 결과와 해석 |
| --- | --- |
| 원본 Autotools 재현 | clean base `00826b8`에서 `AM_INIT_AUTOMAKE expanded multiple times`로 autoreconf exit 1 재현 |
| 수정한 Autotools | 실제 프로젝트 autoreconf/configure help와 실제 configure flag matrix 포함 10개 시험 통과. skip 없음 |
| flag 의미 | opt/debug × CFLAGS 미지정/빈 값/사용자 값 × CXXFLAGS 미지정/빈 값/C++17 값의 18개 조합 보존 |
| 원본 검증기 회귀 | 별도 원본 fixture를 사용하는 기존 18개 시험 통과 |
| 실제 IDL 생성 회귀 | 고정 0.25.0 compiler 출력과 각 static/shared source 목록 대조 1개 시험 통과. 수정 전 constants 파일 요구로 실패 재현 |
| 프로젝트 합계 | 위 10+18+1 = 29개 통과. dependency prefix를 지정한 실행이며 일반 환경에서 도구가 없으면 해당 시험은 skip |
| Thrift build | compiler, libthrift, libthriftnb, libthriftz 생성·workspace 설치 및 0.25.0 metadata 확인 |
| Thrift C++ runtime | 공식 C++ suite 29개 모두 통과. TNonblockingServer·TFileTransport·protocol·SSL 시험 포함 |
| fb303 | 별도 build로 FacebookService, fb303_types, FacebookBase, ServiceTracker 네 객체와 libfb303.a·headers·IDL 설치 확인 |
| Scribe RPC 정적 library | 실제 생성 규칙으로 두 IDL을 생성하고 libscribe.a·libdynamicbucketupdater.a clean build 통과 |
| 생성 client smoke | 두 library와 fb303/Thrift를 실제 링크하고 메모리 버퍼에 요청 96 bytes 기록. 네트워크·Scribe daemon을 사용하지 않음 |
| Scribe bootstrap/configure | 위 dependency prefix·C++17 flag로 통과 |
| Scribe 전체 C++ build | `PosixThreadFactory.h` 부재로 exit 2. link 단계·실행에는 도달하지 못함 |

Scribe 생성 C++ compile에서 `PACKAGE_*` 재정의 경고도 관찰했고 실제 log에 보존했다. 경고 일괄 정리는 수행하지 않았다.

Static library build와 shared source 목록 검증을 구분한다. shared library build, 기존 Python packaging을 포함한 root 전체 make, PHP/cross-language suite는 수행하지 않았다. Fuzz executable의 build는 이루어졌지만 fuzz campaign을 실행한 것으로 세지 않는다. compiler의 빈 `make check`를 실질적 compiler 시험으로 세지 않고 두 IDL의 실제 생성과 compile/link 결과를 사용했다.

### 분리된 Thrift build에서 수정한 실행 조건

Dependency 소스를 수정하지 않고 지원되는 include flag와 공식 fixture 위치만 명시했다.

- 첫 C++ build는 generated `thrift/config.h` 검색 경로가 없어 실패. CPPFLAGS에 build의 `lib/cpp/src` 추가
- 시험 build의 `<config.h>`를 위해 build root도 include 경로에 추가. 최종 flag로 clean build 재실행
- 최초 C++ 시험은 29개 중 4개가 인증서 fixture를 찾지 못해 setup 실패. 공식 source의 `test/keys`를 build tree의 동일 상대 위치에 연결한 뒤 전체 재실행하여 29개 통과
- TLS 검증을 끄거나 certificate를 바꾸지 않음. 사용한 key는 upstream 공개 시험 fixture이며 사용자 인증 정보가 아님

Thrift의 configure는 CXX에 `-std=c++11`을 붙였지만 실제 compile 명령의 뒤쪽 CXXFLAGS `-O2 -std=c++17`이 최종 표준을 결정한다. fb303의 원래 configure가 flags를 덮어쓰므로 make 호출에서 CXXFLAGS를 명시했다. source·option·출력 hash·결과는 manifest와 checkpoint의 실제 log에 구분해 남긴다.

## 재실행과 남은 경계

동일 도구와 workspace dependency prefix를 준비한 환경에서 다음 프로젝트 시험을 실행한다. 자동 설치하거나 prefix를 추측하는 시험은 없다.

```sh
export THRIFT_PREFIX=/absolute/workspace-prefix/thrift-0.25.0
export FB303_PREFIX=/absolute/workspace-prefix/fb303-0.25.0
python3 -B -m unittest discover -s test -p 'test_*.py' -v
sh -n bootstrap.sh
git diff --check
```

위 두 prefix 예시는 실제 설치 경로로 바꾼다. rootless Autotools의 process-local 환경이 필요한 경우도 먼저 적용한다. Thrift configure의 실제 C++-only 선택, compile flags, build/검증 command와 생성 파일 hash는 [manifest](build-manifest.json)를 따른다.

`test/verify_upstream_import.py`는 여전히 엄격한 원본 검사다. 현재 작업 트리에서는 `acinclude.m4`, `bootstrap.sh`, `configure.ac`, `src/Makefile.am` 네 경로를 정확히 content mismatch로 보고한다. 이를 통과시키는 예외는 추가하지 않았다. 원본 105개 경로 PASS 재현은 수정되지 않은 `00826b8`의 별도 checkout에서 수행한다.

다음 단계는 실제로 확인한 Thrift concurrency·pointer/server API 경계를 기존 wrapper 안에서 이식하는 일이다. 현재 결과로 thread/queue 동작, old/new client·relay·spool, fb303 운영 API 또는 회사 운영 동등성을 보장하지 않는다. 후속 source 변경·검증은 작은 단위로 분리하고 commit/push·서버 작업·배포는 각각 승인 범위를 확인한다.
