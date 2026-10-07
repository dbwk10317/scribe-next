# HDFS

`fs_type=hdfs` 저장은 선택 기능이다. 기본 빌드, Docker 이미지, 개발 RPM에는 없다.
아래 결과는 2026-10-05~06 것이며 2026-10-07 현대화 단계(Boost 제거 등) 뒤에는 다시 확인하지 않았다.

## 빌드

- configure에 `--enable-hdfs --with-hadooppath=<Hadoop>`을 준다. `-lhdfs -ljvm`을 링크한다
- 빌드 규칙은 `-L<Hadoop>/lib`만 더한다. Hadoop 3의 `lib/native`와 `$JAVA_HOME/lib/server`는 `LDFLAGS`로 준다(아래 Rocky 명령)
- `libhdfs.so`는 `libjvm.so`에 의존한다. 두 native 폴더와 그 의존성을 process-local loader 경로로 주고 Hadoop jar classpath도 준다
- 실행 파일 RUNPATH만으로는 JVM 전이 의존성을 찾지 못했다. 전역 ldconfig, 보안 설정, 시스템 설치는 필요 없다
- 검증기에 `--hadoop`, `--java-home`을 주면 HDFS ELF, Java version, local JNI 시험을 더해 11단계를 실행한다

## API 이식

- 원본 `HdfsFile::deleteFile`은 옛 2-인자 `hdfsDelete(fs, path)`를 부르고 반환값을 무시한다. Hadoop 3.5.0은 3-인자를 선언한다
- `src/compat_hdfs.h`가 compile 때 signature를 고르고 3-인자에는 `recursive=1`을 준다. 로그·반환 처리는 원본대로다
- Hadoop 0.20.2 libhdfs의 `FileSystem.delete(Path)`는 DistributedFileSystem·RawLocalFileSystem에서 재귀 삭제로 위임했다([hdfs.c](https://raw.githubusercontent.com/apache/hadoop/release-0.20.2/src/c++/libhdfs/hdfs.c), [DFSClient](https://raw.githubusercontent.com/apache/hadoop/release-0.20.2/src/hdfs/org/apache/hadoop/hdfs/DFSClient.java))
- 원본 Scribe의 모든 API가 Hadoop 0.20.2와 빌드된다는 뜻은 아니다(`hdfsConnectNewInstance`도 쓴다)
- 이식 전에는 HDFS를 켠 `HdfsFile.o` compile이 실패하고, 이식 후 전체 compile·link가 된다

## 원본 그대로인 HDFS 동작

- `_current`는 경로를 담은 일반 파일이다. OS symlink가 아니다
- `createDirectory`는 아무것도 만들지 않고 true를 반환한다
- `readNext`·`getFrame`은 지원하지 않는다. HDFS를 spool 재전송 저장소로 쓰지 않는다
- 닫힌 handle의 `openTruncate`는 append로 동작한다. close가 fileSys를 끊어 재연결 전까지 `deleteFile`은 아무것도 하지 않는다
- FileStore는 파일을 만들기 전에 폴더를 나열하고, HdfsFile은 NULL·빈 목록에서 예외를 낸다

## SDK 준비

- Hadoop 3.5.0 공식 binary와 source를 공식 SHA512와 detached signature로 확인한 뒤 푼다
- signer fingerprint는 `3EC9157CB0281495A6E7FC9F1105854687CDDA79`다. `.asc`, `.sha512`, `KEYS`는 Apache 공식 배포 경로에서 받는다
- 새 public keyring의 undefined owner trust는 서명 실패가 아니다. signature·expiry 검사를 끄지 않고 unsigned mirror를 쓰지 않는다
- Hadoop 3.5 client는 JDK 17·21을 지원한다. single-DataNode server는 JDK 17로 확인했다
- 공식 prebuilt libhdfs는 Rocky 8에서 GLIBC/GLIBCXX, Rocky 9에서 GLIBCXX 요구가 맞지 않는다
- Rocky에서는 같은 3.5.0 source의 CMake `hdfs` target을 배포판 compiler로 다시 빌드한다([Dockerfile.hdfs](../tools/rocky/Dockerfile.hdfs))
- 그 SDK는 Boost 1.86, Protobuf 3.25.5, Abseil 20230802.1, GoogleTest 1.10.0을 쓴다. archive hash는 Dockerfile에 있다
- `HDFSPP_LIBRARY_ONLY=ON`을 쓴다. Rocky 8은 `NATIVE_CXX_LIBS=-lstdc++fs`, Rocky 9는 빈 값이다
- 실행 사용자는 NSS에 이름이 있어야 한다. 이름 없는 UID는 Hadoop UserGroupInformation에서 실패한다(Rocky 이미지는 UID 1000·GID 973 사용자를 만든다)

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
- Mac. Linux fixture가 `/bin/true`를 가정한다
