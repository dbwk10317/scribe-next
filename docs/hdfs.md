# HDFS

`fs_type=hdfs` 저장은 선택 기능이다. 기본 빌드, Docker 이미지, 개발 RPM에는 없다.
아래 결과는 2026-10-05~06 것이며 2026-10-07 현대화 단계(Boost 제거 등) 뒤에는 다시 확인하지 않았다.

## 빌드

- configure에 `--enable-hdfs --with-hadooppath=<Hadoop>`을 준다. `-lhdfs -ljvm`을 링크한다
- 빌드 규칙은 `-L<Hadoop>/lib`와 Hadoop 3의 `-L<Hadoop>/lib/native`를 더한다. configure 변수 `JAVA_HOME`이 있으면 `-L$JAVA_HOME/lib/server`도 더한다(`ef1c137`)
- 실행 때 찾을 rpath는 여전히 `LDFLAGS`의 `-Wl,-rpath,...`로 준다(아래 Rocky 명령). 검증기는 `--java-home` 값을 `JAVA_HOME`으로 넘긴다
- `JAVA_HOME`은 precious 변수라 `config.cache`에 남는다. 값을 바꾸면 `config.cache`를 지우고 configure를 다시 실행한다
- 이 빌드 규칙 변경 뒤 HDFS를 켠 빌드는 다시 하지 않았다
- `libhdfs.so`는 `libjvm.so`에 의존한다. 두 native 폴더와 그 의존성을 process-local loader 경로로 주고 Hadoop jar classpath도 준다
- 실행 파일 RUNPATH만으로는 JVM 전이 의존성을 찾지 못했다. 전역 ldconfig, 보안 설정, 시스템 설치는 필요 없다
- 검증기에 `--hadoop`, `--java-home`을 주면 HDFS ELF, Java version, local JNI 시험을 더해 11단계를 실행한다

## API 이식

- 원본 `HdfsFile::deleteFile`은 옛 2-인자 `hdfsDelete(fs, path)`를 부르고 반환값을 무시한다. Hadoop 3.5.0은 3-인자를 선언한다
- `src/compat_hdfs.h`가 compile 때 signature를 고르고 3-인자에는 `recursive=1`을 준다. 로그·반환 처리는 원본대로다
- Hadoop 0.20.2 libhdfs의 `FileSystem.delete(Path)`는 DistributedFileSystem·RawLocalFileSystem에서 재귀 삭제로 위임했다([hdfs.c](https://raw.githubusercontent.com/apache/hadoop/release-0.20.2/src/c++/libhdfs/hdfs.c), [DFSClient](https://raw.githubusercontent.com/apache/hadoop/release-0.20.2/src/hdfs/org/apache/hadoop/hdfs/DFSClient.java))
- 원본 Scribe의 모든 API가 Hadoop 0.20.2와 빌드된다는 뜻은 아니다(`hdfsConnectNewInstance`도 쓴다)
- 이식 전에는 HDFS를 켠 `HdfsFile.o` compile이 실패했고, 이식 후 2026-10-06까지 전체 compile·link를 확인했다
- 그 뒤 `28a4d9a`(PR #63)와 `e4bb4cc`(PR #65)가 `src/HdfsFile.h`·`HdfsFile.cpp`를 바꿨고 HDFS를 켠 빌드는 다시 하지 않았다
- `c226849`도 `HdfsFile.cpp`를 바꿨다. 소멸자는 열린 파일을 닫은 뒤 연결을 끊고, `openRead`는 이미 열린 파일을 `openWrite`처럼 거부한다(누수 수정). 이 변경도 HDFS 빌드로 확인하지 않았다

## 원본 그대로인 HDFS 동작

- `_current`는 경로를 담은 일반 파일이다. OS symlink가 아니다
- `createDirectory`는 아무것도 만들지 않고 true를 반환한다
- `readNext`·`getFrame`은 지원하지 않는다. HDFS를 spool 재전송 저장소로 쓰지 않는다
- 닫힌 handle의 `openTruncate`는 append로 동작한다. close가 fileSys를 끊어 재연결 전까지 `deleteFile`은 아무것도 하지 않는다
- FileStore는 파일을 만들기 전에 폴더를 나열하고, HdfsFile은 NULL·빈 목록에서 예외를 낸다

## SDK 준비

- [Dockerfile.hdfs](../tools/rocky/Dockerfile.hdfs)는 Hadoop archive 두 개를 SHA512(`sha512sum`), 나머지 네 개를 SHA256으로만 검사한다. 서명 검사 단계는 없다
- Hadoop 3.5.0 binary·source의 detached signature는 archive를 context에 넣기 전에 사람이 따로 확인한다. 2026-10-06 실행 때 확인한 기록은 정리 전 문서(`d5efec7^:docs/rocky-hdfs.md`)에 있다
- signer fingerprint는 `3EC9157CB0281495A6E7FC9F1105854687CDDA79`다. `.asc`, `.sha512`, `KEYS`는 Apache 공식 배포 경로에서 받는다
- 새 public keyring의 undefined owner trust는 서명 실패가 아니다. signature·expiry 검사를 끄지 않고 unsigned mirror를 쓰지 않는다
- Hadoop 3.5 client는 JDK 17·21을 지원한다. single-DataNode server는 JDK 17로 확인했다
- 공식 prebuilt libhdfs는 Rocky 8에서 GLIBC/GLIBCXX, Rocky 9에서 GLIBCXX 요구가 맞지 않는다
- Rocky에서는 같은 3.5.0 source의 CMake `hdfs` target을 배포판 compiler로 다시 빌드한다([Dockerfile.hdfs](../tools/rocky/Dockerfile.hdfs))
- 그 SDK는 Boost 1.86, Protobuf 3.25.5, Abseil 20230802.1, GoogleTest 1.10.0을 쓴다. archive hash는 Dockerfile에 있다
- build context에는 Dockerfile과 아래 archive 여섯 개를 이 이름으로 둔다. GitHub archive는 commit 고정 주소에서 받아 이름만 바꾸며, Dockerfile은 푼 뒤 오른쪽 폴더 이름을 쓴다

| context 파일 | 공식 위치 | 푼 뒤 폴더 |
| --- | --- | --- |
| `hadoop-3.5.0.tar.gz` | https://downloads.apache.org/hadoop/common/hadoop-3.5.0/hadoop-3.5.0.tar.gz | `/opt/hadoop-3.5.0` |
| `hadoop-3.5.0-src.tar.gz` | https://downloads.apache.org/hadoop/common/hadoop-3.5.0/hadoop-3.5.0-src.tar.gz | `hadoop-3.5.0-src` |
| `boost_1_86_0.tar.bz2` | https://archives.boost.io/release/1.86.0/source/boost_1_86_0.tar.bz2 | `boost_1_86_0` |
| `protobuf-3.25.5.tar.gz` | https://codeload.github.com/protocolbuffers/protobuf/tar.gz/9d0ec0f92b5b5fdeeda11f9dcecc1872ff378014 | `protobuf-9d0ec0f92b5b5fdeeda11f9dcecc1872ff378014` |
| `abseil-20230802.1.tar.gz` | https://codeload.github.com/abseil/abseil-cpp/tar.gz/fb3621f4f897824c0dbe0615fa94543df6192f30 | `abseil-cpp-fb3621f4f897824c0dbe0615fa94543df6192f30` |
| `googletest-1.10.0.tar.gz` | https://codeload.github.com/google/googletest/tar.gz/703bd9caab50b139428cea1aaff9974ebee5742e | `googletest-703bd9caab50b139428cea1aaff9974ebee5742e` |

- `HDFSPP_LIBRARY_ONLY=ON`을 쓴다. Rocky 8은 `NATIVE_CXX_LIBS=-lstdc++fs`, Rocky 9는 빈 값이다
- Dockerfile의 기본 `BASE`(`scribe-next-rocky-validation:8-20261006`)는 [Rocky recipe](build.md#rocky-linux-8과-9)가 만들지 않는 tag다. 아래처럼 `--build-arg BASE`를 준다
- 실행 사용자는 NSS에 이름이 있어야 한다. 이름 없는 UID는 Hadoop UserGroupInformation에서 실패한다
- 두 lane의 uid가 다르다. 검증기 HDFS lane(아래 명령)은 이미지가 만든 `scribe-fixture` UID 1000·GID 973으로 돈다
- 그래서 bind mount한 checkout의 소유자가 uid 1000이어야 한다. 아니면 Git 소유권 검사(dubious ownership)로 검증기가 멈춘다. 이 검사는 끄지 않는다
- [single-DataNode 시험](#single-datanode-시험)은 구·신 비교와 같은 guard로 real·effective UID 65534를 요구한다. Rocky의 65534는 `nobody`라 NSS 이름이 있다

```sh
docker build -f "$CONTEXT/Dockerfile.hdfs" \
  --build-arg BASE="scribe-next-rocky-validation:$MAJOR" \
  --build-arg NATIVE_CXX_LIBS="$NATIVE_CXX_LIBS" \
  -t "scribe-next-rocky-hdfs:$MAJOR" "$CONTEXT"
docker run --rm --network none --user 1000:973 \
  --cap-drop ALL --security-opt no-new-privileges --cpus 2 --memory 6g --pids-limit 512 \
  --mount "type=bind,src=$CHECKOUT,dst=/validation-input,readonly" \
  --mount "type=bind,src=$OUTPUT,dst=/validation-output" \
  -w /validation-input "scribe-next-rocky-hdfs:$MAJOR" sh -c '
    export LDFLAGS="$LDFLAGS -L/opt/hadoop-rocky-3.5.0/lib/native -L/usr/lib/jvm/java-17-openjdk/lib/server -Wl,-rpath,/opt/hadoop-rocky-3.5.0/lib/native -Wl,-rpath,/usr/lib/jvm/java-17-openjdk/lib/server"
    python3.12 -B tools/validate_linux.py --hadoop /opt/hadoop-rocky-3.5.0 \
      --java-home /usr/lib/jvm/java-17-openjdk --output /validation-output/new-hdfs-result'
```

## local JNI 시험

```sh
python3 -B tools/test_hdfs_local.py \
  --build /absolute/existing/configured-build \
  --hadoop /absolute/verified/hadoop-3.5.0 \
  --java-home /absolute/existing/jdk \
  --thrift /absolute/existing/thrift-0.25.0 \
  --fb303 /absolute/existing/fb303-0.25.0 \
  --tools /absolute/existing/tools/usr
```

- 실제 `HdfsFile`·file source를 compile해 private `file:///` JNI fixture로 실행한다
- binary write·flush·stat, close 뒤 reopen append, 연결된 handle의 truncate, 일반 marker 파일, 목록, 삭제, 원본의 미지원 `readNext`·`getFrame`을 확인한다
- NameNode·DataNode, daemon, network listener를 만들지 않는다

## single-DataNode 시험

```sh
python3 -B tools/daemon_hdfs.py --run-isolated-hdfs \
  --hadoop /absolute/verified/hadoop-3.5.0 \
  --java-home /absolute/verified/jdk17 \
  --scribed /absolute/matching/hdfs-enabled/scribed \
  --library-dir /absolute/existing/thrift/lib \
  --library-dir /absolute/existing/fb303/lib \
  --library-dir /absolute/existing/deps/lib \
  --output /absolute/new/private-hdfs-evidence
```

- 이미 network-none·lo-only·UID 65534인 컨테이너 안에서 실행한다. Docker·network 설정, download, SSH·YARN은 하지 않는다
- 두 Hadoop 프로세스는 loopback에 bind한다. scribed의 wildcard socket은 network-none으로 가둔다
- 작업 시간 120초 안에서 단계마다 monotonic 기한을 둔다. 소유한 프로세스의 정리는 별도 기한이다
- 폴더에 빈 `.fixture-seed`를 둔다. 위의 빈 목록 예외를 피하는 정상 case의 전제다
- 첫 프로세스는 `A\0B\n\xfftail` 9 bytes를 쓰고, 새 프로세스가 `Z`를 이어 써 10 bytes가 된다
- `_current`는 `fixture_00000`을 담은 일반 파일이다
- HDFS CLI 독립 읽기, 정확한 세 파일, fresh counter 2/1, DataNode 1·safemode OFF, healthy block, child·listener 회수를 확인한다
- network-none에서 컨테이너 hostname이 풀리지 않으면 Hadoop HTTP 인증 초기화가 실패한다. hostname을 `localhost`로 준다
- 자원은 2 CPU, 3 GiB, 512 PIDs로 했다. 측정한 최소값은 아니다

Rocky HDFS 이미지에서 UID 65534로 실행하는 예는 다음과 같다.
2026-10-05~06 실행은 host mount 없는 컨테이너에서 했으며 이 명령 그대로는 실행하지 않았다.
검증기 출력 폴더는 mode 0700이라 UID 65534가 읽을 수 있는 새 폴더로 scribed를 복사한다.

```sh
# WORK: checkout 밖의 아직 없는 폴더. HDFS_SCRIBED: HDFS 검증기 출력의 stage/opt/scribe/bin/scribed
mkdir -m 0755 "$WORK" "$WORK/bin" && mkdir -m 0777 "$WORK/out"
cp "$HDFS_SCRIBED" "$WORK/bin/scribed" && chmod 0755 "$WORK/bin/scribed"
docker run --rm --network none --hostname localhost --user 65534:65534 \
  --cap-drop ALL --security-opt no-new-privileges --cpus 2 --memory 3g --pids-limit 512 \
  --mount "type=bind,src=$CHECKOUT,dst=/validation-input,readonly" \
  --mount "type=bind,src=$WORK/bin,dst=/hdfs-bin,readonly" \
  --mount "type=bind,src=$WORK/out,dst=/hdfs-output" \
  -w /validation-input "scribe-next-rocky-hdfs:$MAJOR" \
  python3.12 -B tools/daemon_hdfs.py --run-isolated-hdfs \
    --hadoop /opt/hadoop-rocky-3.5.0 --java-home /usr/lib/jvm/java-17-openjdk \
    --scribed /hdfs-bin/scribed \
    --library-dir /opt/thrift-0.25.0/lib --library-dir /opt/fb303-0.25.0/lib --library-dir /opt/tools/lib \
    --output /hdfs-output/new-hdfs-evidence
```

## 결과

| 날짜 | 환경 | 결과 |
| --- | --- | --- |
| 2026-10-05 | Debian 13/GCC 14, OpenJDK 21 | HDFS build, local JNI |
| 2026-10-05 | Ubuntu 26.04.1/GCC 15.2, JRE 21·17 | 기본 185 tests, HDFS build, local JNI, single-DataNode(이후 194 tests) |
| 2026-10-06 | Rocky 8.10/GCC 8.5, Rocky 9.8/GCC 11.5, JDK 17 | 11단계 220 tests, local JNI, single-DataNode |

## 하지 않은 것

- historical libhdfs binary의 구·신 비교
- 분산 삭제, NameNode 장애, 권한·복제, 다중 DataNode
- HDFS와 shared RPC 조합, HDFS RPM
- durable ACK, 성능
- Mac 등 Linux 밖 플랫폼. 예전 Mac 시도는 fixture가 `/bin/true`를 쓰던 때 실패했다. 지금 fixture는 `sys.executable`을 쓰지만 다시 시도하지 않았다
