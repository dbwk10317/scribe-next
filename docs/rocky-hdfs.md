# Rocky 선택 HDFS 소스 검증

2026-10-06, Linux x86_64. Base main `301049733ac83cbf770e0c68ce2bac71719766f3`에
선택 HDFS 검증기와 fixture 연결을 추가했다. production C++·IDL·원본 예제는 변경하지 않는다.
Hadoop 3.5.0, 배포판 JDK17, Thrift compiler/runtime 및 matching fb303 0.25.0,
Scribe용 Boost1.83을 사용한다. 기본 static RPC HDFS source lane이며 HDFS/shared RPM은 아니다.

## 정상 SDK와 사용자 준비

[Dockerfile.hdfs](../tools/rocky/Dockerfile.hdfs)는 기존
[Rocky 검증 이미지](rocky-build.md)를 기반으로 공식 native client를 재빌드한다.
Hadoop 공식 binary의 libhdfs는 Rocky8에서 GLIBC/GLIBCXX, Rocky9에서 GLIBCXX 요구가
맞지 않았다. host runtime을 교체하거나 ABI 검사를 끄지 않고, 같은 3.5.0 source의
표준 CMake `hdfs` target을 각 배포판 compiler로 빌드했다. SDK와 Scribe dependency는 분리한다.

Hadoop binary와 source archive 모두 공식 published SHA512 및 detached signature를
검증한 뒤 추출했다. signer fingerprint는
`3EC9157CB0281495A6E7FC9F1105854687CDDA79`다. 새 public keyring의 undefined owner
trust를 cryptographic signature 실패로 해석하거나 signature/expiry 검사를 끄지 않는다.

- Binary: https://downloads.apache.org/hadoop/common/hadoop-3.5.0/hadoop-3.5.0.tar.gz
- Source: https://downloads.apache.org/hadoop/common/hadoop-3.5.0/hadoop-3.5.0-src.tar.gz
- `.asc`, `.sha512`, `KEYS`: 같은 Apache 공식 배포 경로에서 준비·검증한다.

고정 archive hash는 Dockerfile에 있다. 추가 SDK dependency는 공식 Boost1.86 archive와
공식 GitHub의 다음 immutable commit archive다. 이 TLS/hash 확인을 GPG 검증으로 부르지 않는다.

| Context 파일 | 공식 source |
| --- | --- |
| `boost_1_86_0.tar.bz2` | https://archives.boost.io/release/1.86.0/source/boost_1_86_0.tar.bz2 |
| `protobuf-3.25.5.tar.gz` | https://codeload.github.com/protocolbuffers/protobuf/tar.gz/9d0ec0f92b5b5fdeeda11f9dcecc1872ff378014 |
| `abseil-20230802.1.tar.gz` | https://codeload.github.com/abseil/abseil-cpp/tar.gz/fb3621f4f897824c0dbe0615fa94543df6192f30 |
| `googletest-1.10.0.tar.gz` | https://codeload.github.com/google/googletest/tar.gz/703bd9caab50b139428cea1aaff9974ebee5742e |

Protobuf3.25.5/Abseil20230802.1/Boost1.86은 Hadoop source의 BUILDING.txt와 맞추며
GoogleTest commit은 native CMake가 지정한 값이다. `/opt/hadoop-deps`에서 SDK만 준비한다.
`HDFSPP_LIBRARY_ONLY=ON`은 공식 library-only 선택이며 Hadoop 전체 native tests/tools
성공을 주장하지 않는다. `JVM_ARCH_DATA_MODEL=64`는 실제 Java property로 확인한다.
Rocky8/GCC8의 std::filesystem backend는 정상 `-lstdc++fs`로 연결한다.
Rocky9에는 이 추가 flag가 필요 없다.

`/opt/hadoop-rocky-3.5.0`은 새 native library와 같은 버전의 공식 header/jar/shell layout을
연결한 SDK다. source header와 binary header bytes를 비교하고 `ldd -r`에서 missing library와
undefined symbol이 없음을 확인한다. 원래 prebuilt native 파일은 변경하지 않는다.
실제 시험은 SDK image와 identity/layout 후속 layer를 사용했으며 Dockerfile은 같은 명령을 합쳤다.

UID1000만 지정한 첫 JNI 시험은 passwd에 해당 이름이 없어 실패했다.
`getent passwd 1000` 및 Python `pwd.getpwuid` 실패와 Hadoop UserGroupInformation의
invalid-UID 처리로 원인을 확인했다. 이미지 안에 비특권 `scribe-fixture` UID1000/GID973을
정상 생성한 뒤 통과했다. host 사용자·권한·인증 정책은 바꾸지 않았다.
가짜 HADOOP_USER_NAME, Java user.name override나 인증 우회는 사용하지 않는다.

## 재현

`CONTEXT`에는 검증된 공개 archive와 Dockerfile만 둔다. checkout·인증 파일·다른 작업을
넣지 않는다. MAJOR는8/9, NATIVE_CXX_LIBS는8에서 `-lstdc++fs`,9에서 빈 값이다.

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

OUTPUT는 checkout 밖의 기존 writable parent다. fixture UID1000과 source checkout 소유자를
맞춘다. Git 안전 검사를 끄지 않는다. caller flags의 명시값과 빈 값은 그대로 유지하며
위 LDFLAGS는 이 실행의 caller가 정상 native/JVM 경로를 제공하는 것이다.
검증기는 fresh source export, configure/clean/build, HDFS ELF, Java version, 기존 local JNI,
전체 suite, DESTDIR와 설치된 help를 실행한다. daemon/cluster는 자동 시작하지 않는다.
API fixture는 HDFS를 켠 경우 실제 HdfsFile.o와 native/JVM을 연결하며 그 객체의 compiler
freshness와 daemon link freshness도 확인한다. 첫 연결 실패 원인은 fixture의 HdfsFile.o
누락이었다. production 코드를 수정하거나 시험을 skip하지 않았다.

## 실제 결과와 경계

Rocky8.10/GCC8.5/JDK17.0.20.1 및 Rocky9.8/GCC11.5/JDK17.0.20.1 각각
전체11단계, 220 tests, failure/error/skip0, local JNI 및 staged help가 통과했다.
local JNI는 binary write/flush/stat, reopen append, truncate, regular marker/list/delete,
원본 unsupported readNext/getFrame 경계를 확인한다.

single-DataNode 후속 시험은 [기존 runner](../tools/daemon_hdfs.py)를 그대로 사용한다.
runner의 UID65534 계약 때문에 이미지의 정상 nobody NSS 계정으로 실행하며 UID 검사를
완화하지 않는다. source와 staged binary는 read-only mount, 출력은 container 내부 새
임시 디렉터리다. network-none·hostname localhost·cap-drop ALL·no-new-privileges,
2CPUs/3GiB/512PIDs, host port publish 없음으로 한정한다. runner 호출·expected bytes와
seeded-directory 조건은 [HDFS 안내](hdfs-compatibility.md#single-datanode-distributed-check)를 따른다.
전용 컨테이너 결과만 복사한 뒤 그 컨테이너만 제거한다.

양쪽 실제 분산 시험이 통과했다. live DataNode1/safemode OFF, initial exact
`4100420aff7461696c` 9 bytes, 재시작 append `4100420aff7461696c5a` 10 bytes,
독립 Hadoop CLI reader, regular marker `fixture_00000`, 정확한 세 파일 inventory,
각 프로세스의 fresh received counters2/1과 Scribe shutdown/cleanup exit0을 확인했다.
NameNode/DataNode는 owned SIGTERM exit143으로 회수했고 listener before/after는 empty다.
기존 36개 container ID가 보존됐음을 별도로 확인했다.

| Rocky | HDFS-enabled staged scribed SHA256 |
| --- | --- |
| 8.10 | `cad7198a11862a1f52e414a092a8cedecf71c60a177337f82f63b20bac3cc292` |
| 9.8 | `46d4abbd90f860c509f7e7e8bc28cd840d1fc590bd96c09d09c1487fdac7c57a` |

원시 `validation.json`, test-results, JNI/build logs와 두 daemon `result.json`/logs를
별도 보존한다. 처음 numeric UID JNI 실패, prebuilt ABI 실패 및 fixture link 실패도 남긴다.
 실제 historical libhdfs binary old/new,
권한·복제·장애 matrix와 성능은 범위 밖이다. HDFS와 shared의 조합, HDFS/shared RPM,
서로 다른 RPM 버전 간 upgrade 및 production Rocky host kernel/service 배포는 미검증이다.
