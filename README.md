# scribe-next

공개 Facebook Scribe [`fcd294f`](https://github.com/facebookarchive/scribe/tree/fcd294faffd1e88af1643a3a8c2359c41713f7c2)의
구조·설정·framed binary RPC·파일/store 동작을 보존하는 현대 Linux C++ 이식이다.
실행 파일은 기존 이름 `scribed`를 유지한다. 현재는 아래 범위를 검증한 초기
현대화 후보이며, 원본 전체 옵션의 완전 동등성이나 production-ready 선언은 아니다.
회사 환경은 범위 밖이다. release/tag·재배포 artifact·서비스 배포는 아직 결정하지 않았다.

## 검증된 지원 범위

2026-10-05, 기준 main `bc9ba6e`:

| 경계 | 확인한 범위 |
| --- | --- |
| OS/toolchain | Linux x86_64: Debian 13/GCC 14.2, Ubuntu 26.04.1/GCC 15.2, C++17, Boost 1.83 |
| RPC 의존성 | Thrift compiler/runtime 0.25.0과 해당 compiler로 생성·준비한 fb303 prefix; libthriftnb/libevent/pthread |
| 빌드/설치 | 기존 autotools, 기본 static Scribe RPC 및 선택 shared RPC, 전체 make, 작업 폴더 DESTDIR 설치·help·private loader |
| Python | 생성된 `scribe` package 설치·import/제한 wire smoke, Python 3.12/3.14와 실제 site/dist-packages scheme; setuptools 필요 |
| 공개 old/new | 공식 구 Thrift 0.9.0/fcd294f(build-only patch 명시)와 현대 daemon의 제한 framed binary/fb303,10종 정상 store, spool/relay 복구·회전·재개 |
| 동적 mapping | 실제 RPC/TTL: A→cache A→B→실패 refresh 중 B 유지→A 회복; 두 missing-key warning/static fallback |
| 선택 HDFS | 공식 Hadoop 3.5/JDK 17 single-DN의 nonempty seeded-directory에서 binary write·재시작 append·regular marker·block/readback·cleanup; JDK 21 local JNI client도 확인 |

최신 기본 Linux lane 회귀 **201개, failure/error/skip0**이며 실제 daemon 비교와 별도 근거다.
Mac에서는 해당 offline fixture만 확인했다. shared actual old/new daemon 전체,
역사 libhdfs binary, HDFS fault/permission/replication·빈 디렉터리, 전체 config/store
옵션·다른 platform은 미검증이다. 상세 성능 비교와 tuning은 사용자 결정으로 보류했다.
[완료 경계](docs/first-modern-version.md) · [실제 비교](docs/daemon-differential.md) ·
[HDFS 범위](docs/hdfs-compatibility.md)

## 검증된 Linux C++ 빌드 recipe

이미 준비한 Thrift 0.25 compiler/runtime, fb303, Boost system/filesystem,
libevent, C++ compiler, make, autoconf/automake/libtool과 Python3/setuptools를 사용한다.
의존성을 자동 설치하지 않는다. rootless toolchain이면 검증된 process-local 환경을
먼저 적용하고 실제 prefix/include/library 위치를 지정한다.

가장 짧은 재현 진입점은 기존 build/test/install 호출을 묶은 검증기다.
출력은 checkout 밖의 **새 디렉터리**여야 하며, 부모 디렉터리는 존재해야 한다.

```sh
export THRIFT_PREFIX=/absolute/existing/thrift-0.25.0
export FB303_PREFIX=/absolute/existing/fb303-prefix
export TOOLS_PREFIX=/absolute/existing/tools/usr
export THRIFT_PYTHON_SOURCE=/absolute/existing/thrift-0.25.0/lib/py/src
python3 -B tools/validate_linux.py --output /absolute/new/validation
# 선택 shared Scribe RPC: 별도의 새 output에 --shared-rpc 추가
```

이 명령은 configure/clean/전체 make, 회귀 시험, DESTDIR 설치와 설치된 help를
실행한다. 자동 daemon/service 기동이나 시스템 설치는 하지 않는다. binary는
`validation/stage/opt/scribe/bin/scribed`에 있다. Python 설치 위치는 선택된
interpreter scheme에 따라 달라지며 Thrift/fb303 Python 런타임은 별도 필요하다.
생성 package 이름/버전은 기존 `scribe`/`2.0`, fb303 getVersion은 `2.2`를
유지한다. 이 값들을 새 프로젝트 release/tag로 해석하지 않는다. `bucketupdater` Python 설치나
원본 Python2/PHP 예제 전체의 현대 runtime 지원을 추가했다고 주장하지 않는다.

수동 compile/link의 autotools 형태는 아래와 같다. 설치 검증은 위 검증기의
격리 HOME·override 검사·DESTDIR 경로를 사용한다:

```sh
export SCRIBE_BUILD=/absolute/fresh/source-copy
export TOOLS_LIBDIR="$TOOLS_PREFIX/lib/x86_64-linux-gnu"
cd "$SCRIBE_BUILD"
CPPFLAGS="-I$TOOLS_PREFIX/include -I$TOOLS_PREFIX/include/x86_64-linux-gnu" \
CXXFLAGS="-O2 -std=c++17 -D_GLIBCXX_USE_DEPRECATED=0" \
LDFLAGS="-L$TOOLS_LIBDIR -L$THRIFT_PREFIX/lib -L$FB303_PREFIX/lib -Wl,-rpath,$TOOLS_LIBDIR -Wl,-rpath,$THRIFT_PREFIX/lib -Wl,-rpath,$FB303_PREFIX/lib" \
sh ./bootstrap.sh --prefix=/opt/scribe \
  --with-thriftpath="$THRIFT_PREFIX" --with-fb303path="$FB303_PREFIX" \
  --with-boost="$TOOLS_PREFIX" --with-boost-system=boost_system \
  --with-boost-filesystem=boost_filesystem
make clean
make -C src thriftstyle
make -j2
src/scribed --help
```

`CFLAGS`/`CXXFLAGS`의 명시값·빈 값은 bootstrap이 덮어쓰지 않는다. 실제 toolchain
flags와 matching runtime을 유지한다. shared는 원본 `--disable-static` 선택이며
설치된 두 RPC `.so`와 matching 의존성의 **process-local loader 경로**가 필요하다.
HDFS는 `--enable-hdfs --with-hadooppath=...`와 libhdfs/libjvm/jars/classpath를
준비해야 한다. 실행 파일 RUNPATH만으로 transitive libjvm을 찾는다고 가정하지 않는다.
[전체/staged 검증](docs/linux-build-mvp.md) · [Python](docs/python-packaging-status.md)

## 실행과 기존 설정 사용

```sh
/absolute/matching/scribed -c /absolute/owned/scribe.conf
```

`scribed`는 foreground로 실행한다. 서비스 unit/자동 설치는 제공하지 않는다.
짧은 `-c`와 필요 시 `-p`를 사용한다. **config의 port가 CLI -p보다 우선**하며,
원본 long `--config`/`--port`의 argument 선언 문제는 수정하지 않았다.
현재 listener는 원본 port-only 방식이라 위 명령을 localhost-only라고 해석하면
안 된다. 노출/권한/운영 기동은 실행 환경에서 별도로 결정한다.

기존 `<store>` 설정과 이름을 유지한다. `file`, `buffer`, `network`, `bucket`,
`null`, `multi`, `category`, `thriftfile`, `multifile`, `thriftmultifile`과 기존
routing/rotation/filename/newline/meta 옵션을 새 언어로 바꾸지 않았다.
[원본 예제](examples/example1.conf)는 복사한 뒤 **본인 소유 writable data/spool
경로와 port**를 선택한다. 공유 `/tmp` 경로나 root를 가정하는 원본 helper를
그대로 실행하지 않는다. 예제 helper의 구 언어/runtime도 자동 현대화한 것은 아니다.

파싱은 기존 permissive 규칙을 유지한다. 잘못된 dynamic config가 warning 뒤
static endpoint를 사용하거나, store가 준비되지 않아도 listener/ACK가 생길 수 있다.
프로세스 exit/기동만으로 정상 설정이라고 판정하지 말고 fb303 status/details,
수신 카운터와 목적지의 실제 bytes를 확인한다. 공개 `env_default`의 service-name
조회는 원래 실패 stub이며, host/port mapping 확인을 임의 service discovery 지원으로
확대하지 않는다. port/wire 한도는 startup 설정이고 store reinitialize와 구분한다.

## 보존 계약과 승인된 변경

- 두 IDL의 field/method/namespace, framed binary와 strict 설정, fb303,
  byte·queue/batch/retry/store 형식을 유지한다. OK는 **메모리 큐 수락**이며
  durable ACK/exactly-once가 아니다. flush를 fsync로 설명하지 않는다
- 승인된 예외: StdFile 해제 오류, 빈 payload-only queue drain, StdFile truncate의
  append 제거/partial replay 보존, retry modulo0 방지, bucket/list/pool/config-copy
  결함과 ThriftFileStore raw-copy 설정 보존. 기존 framed 파일을 변환하지 않는다
- HDFS delete의 historical/modern API arity는 recursive=1로 연결하고 원래 ignored
  return/logging을 유지한다. HDFS `_current`는 symlink가 아닌 regular marker이며
  unsupported readNext/getFrame·closed-handle truncate의 원래 동작을 새로 바꾸지 않았다
- C++17 shuffle은 확인한 GNU 순서를 보존한다. Thrift 0.25의 std::thread/ABI는
  구 PosixThreadFactory와 다르므로 stack 크기나 성능 동등성을 가정하지 않는다

[변경 근거](docs/review-fixes-status.md) · [truncate/free](docs/truncate-fix-status.md) ·
[ThriftFile copy와 empty/oversized 보존](docs/thriftfile-fix-options.md)

## Thrift 입력 한도와 thread 경계

`thrift_max_frame_size`와 `thrift_max_message_size`의 기본은 각각 256 MiB다.
외부 4-byte frame prefix를 뺀 serialized RPC payload 기준이고, 양의 decimal
1..2147483647 bytes만 허용한다. 초기 오류는 listener 생성을 막고 변경은 restart가
필요하다. server/input/relay/mapping에 일관되게 적용한 유한 호환 후보이며
메모리 안전 상한이나 전체 old-runtime 동등성 보장은 아니다.

초과 relay batch는 transient failure로 남고 자동 분할/drop하지 않는다.
256 MiB 초과 retained spool의 반복 재시도 경계는 미해결이다. 별도의 ThriftFileStore
empty/oversized delegate/drop/log/성공집계는 사용자의 보존 결정대로 유지한다.
전체 fault matrix, crash/write-failure 손실·중복과 운영 안전성이 해결됐다고 쓰지 않는다.

## 안전한 rollback 준비

이것은 운영 rollback 실행/검증 결과가 아니라 artifact 전환 전의 준비 순서다.

1. 직전 검증 artifact, matching dependency/loader, config, hash와 검증 로그를 보관한다
2. 현재 writer를 정상 종료하고 소유 process/listener가 사라진 뒤 data/spool을 보존한다
3. 이전 binary/runtime/config를 한 묶음으로 되돌린다. old/new가 같은 spool/data에
   동시에 쓰지 않게 하며 저장 형식을 자동 변환하거나 파일을 지우지 않는다
4. 격리된 별도 경로에서 status/작은 payload/readback을 확인한 뒤 실제 전환을 결정한다

binary rollback은 이미 손실된 메시지를 복구하거나 바뀐 파일을 되돌리지 않는다.
구 upstream으로 돌아가면 승인된 결함 수정과 wire 한도가 사라질 수 있다.
안전한 보존/복구와 운영 배포 권한을 먼저 확인한다.

## 라이선스와 출처

[LICENSE](LICENSE)는 Apache2.0이며 원본 copyright/attribution을 보존한다.
[Apache2.0의 재배포 조건](https://www.apache.org/licenses/LICENSE-2.0)에
따라 LICENSE 사본, 변경 파일의 수정 고지, 관련 원본 고지를 포함해야 한다.
고정 Scribe upstream에는 NOTICE가 없지만 동봉 의존성의 LICENSE/NOTICE는 별도다.
Thrift/fb303/Boost/libevent/JDK/Hadoop 및 compiler/runtime library를 함께 배포할
경우 그 artifact에 해당하는 조건·고지를 확인한다. 현재 staged-install/private
loader 시험은 **완성된 재배포 license bundle이나 portable binary release 검사**가 아니다.
새 저작권·상표 권리나 Facebook의 보증을 주장하지 않는다.

현재 사용법/완료 경계는 위와 [첫 현대화 범위](docs/first-modern-version.md)를 따른다.
세부 source/검증 이력은 [출처](docs/source-status.md), [설계](docs/design.ko.md),
[구현](docs/implementation.ko.md)와 단계별 기록에 남고 raw는 Library checkpoint로
보존한다. 개발 시 [AGENTS.md](AGENTS.md)를 먼저 읽는다.
