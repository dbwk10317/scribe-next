# Optional libhdfs compatibility boundary

2026-10-05; baseline main f68eecf, public Scribe fcd294f.

## Narrow API port

The original `HdfsFile::deleteFile` calls the historical two-argument
`hdfsDelete(fs, path)` and ignores its return. Hadoop 3.5.0 declares the
three-argument function. `compat_hdfs.h` selects either signature at compile time;
modern calls receive `recursive=1`. The original logging/return handling remains.

This preserves historical behavior: Hadoop release-0.20.2 libhdfs invoked
`FileSystem.delete(Path)`; its DistributedFileSystem/DFSClient and RawLocalFileSystem
implementations delegated to recursive deletion. This is evidence for deletion
semantics, not a claim that every original Scribe API builds against Hadoop 0.20.2
(the original Scribe also uses `hdfsConnectNewInstance`).

Official references:
- https://raw.githubusercontent.com/apache/hadoop/release-0.20.2/src/c++/libhdfs/hdfs.c
- https://raw.githubusercontent.com/apache/hadoop/release-0.20.2/src/hdfs/org/apache/hadoop/hdfs/DFSClient.java
- https://raw.githubusercontent.com/apache/hadoop/release-0.20.2/src/core/org/apache/hadoop/fs/RawLocalFileSystem.java
- https://hadoop.apache.org/docs/r3.5.0/hadoop-project-dist/hadoop-hdfs/LibHdfs.html
- https://cwiki.apache.org/confluence/spaces/HADOOP/pages/100827883/Hadoop+Java+Versions

## Reproduced local lane

Official Hadoop 3.5.0 binary distribution (581,280,703 compressed bytes, about
1.3 GiB extracted), existing OpenJDK 21.0.12.1 client runtime, Debian13/GCC14,
Boost1.83 and Thrift/fb3030.25.0. Hadoop3.5 clients support JDK17/21; the Hadoop
server JDK17 requirement does not establish a JDK21 server lane.

Official tarball:
https://dlcdn.apache.org/hadoop/common/hadoop-3.5.0/hadoop-3.5.0.tar.gz
SHA512:
`04ab94496cc00c8b7a28d03f6308eff8d2a4e7f37a9da5e8e086e4d6fc990e7a94d661908f6a6136039536efb362614b8aecdef185b5fb8ed588f0b152c7aa16`

The published SHA512 and detached OpenPGP signature were verified before use.
Signature fingerprint `3EC9157CB0281495A6E7FC9F1105854687CDDA79` (Chris Nauroth,
Apache code-signing key). A fresh public keyring reports undefined owner trust;
cryptographic verification succeeded without disabling signature/expiry checks.
Acquire `.asc`, `.sha512` and `KEYS` from the official Apache Hadoop distribution;
verify in a private keyring before extracting. Do not substitute unsigned mirrors.

Before port: actual HDFS-enabled `HdfsFile.o` compilation fails at the old
hdfsDelete call. After port: HDFS-enabled full compile/link succeeds.
The two synthetic API-shape tests exercise exact argument forwarding, one call,
recursive=1 for modern, and unchanged ignored success/failure returns.

The opt-in runner compiles the real HdfsFile/file sources against existing
prefixes and generated IDL, then runs a bounded private file:/// JNI fixture.
It creates no NameNode/DataNode, daemon, network listener, or cluster configuration.

```sh
python3 -B tools/test_hdfs_local.py \
  --build /absolute/existing/configured-build \
  --hadoop /absolute/verified/hadoop-3.5.0 \
  --java-home /absolute/existing/jdk21 \
  --thrift /absolute/existing/thrift-0.25.0 \
  --fb303 /absolute/existing/fb303-0.25.0 \
  --tools /absolute/existing/tools/usr
```

It checks binary write/flush/stat, close/reopen append, connected-handle truncate,
regular marker contents (the original createSymlink is not an OS symlink), listing,
delete, and the original unsupported readNext/getFrame behavior. It also preserves
closed-handle openTruncate's existing append behavior: close disconnects fileSys,
so deleteFile is a no-op until reconnect. createDirectory still returns true without
creating anything. No new durability, framed read/replay, or failure policy is added.

`libhdfs.so` depends on `libjvm.so`; use private process-local loader paths to both
native directories (and matching dependencies), plus the Hadoop jars/classpath.
Executable RUNPATH alone does not resolve a transitive JVM dependency on this lane.
No global ldconfig, security flags, or system installation is required.

## Server reproduction

The same source passed a fresh default eight-step clean validation on Ubuntu
26.04.1/GCC15.2 with 185 tests, failure/error/skip0, DESTDIR install and help0.
A separate HDFS-enabled full compile/link, staged install/help0 and the bounded
local JNI fixture also passed. No Hadoop server, NameNode/DataNode or Hadoop service listener
was started. All 31 container IDs observed before/after were identical, including
the previous 30 operating containers.

The server had no existing Java/JVM. Ubuntu's official JRE21 headless package
21.0.12.1+1-1~26.04.4 was privately extracted after verifying the existing signed
resolute-security InRelease, the Packages SHA256 and package SHA256
`174105c57728ea7652d2a49b5af2f529277dbef51c02417b931e792e54fb2b29`.
Its shipped configuration symlinks were relocated only within the private package
extraction; no maintainer scripts, system install or alternatives were run.
The official Adoptium metadata API returned403; no security bypass was used.
The exact Hadoop tar SHA512 and detached signature/fingerprint above were verified
again before private extraction. SDK archives/extractions are excluded from the
source checkpoint; acquisition and signature/hash records are retained.

Existing Thrift/fb3030.25 and Boost/tool prefixes were reused. HDFS/JVM native
libraries and jar/classpath settings were process-local. No global loader,
permission, service, power or security settings changed, and no benchmark ran.
The local result includes the original closed-handle truncate append and ignored
delete-return behavior; this does not fix those policies or establish durability.

## Remaining original-feature gate

Local JNI validation establishes a modern optional build and local client API
boundary. The subsequent single-DataNode result below confirms one normal
modern Scribe distributed file-store create/write/read-by-CLI/restart-append path.
Distributed deletion, Namenode failures, permissions/replication matrix and other
fault paths remain unverified. Historical libhdfs binary old/new equivalence is
also unverified; the ten normal-store old/new comparisons do not establish it.
Performance comparison remains deferred by the user.

## Single-DataNode distributed check

`tools/daemon_hdfs.py --run-isolated-hdfs` reuses the existing owned-child,
framed client and cleanup helpers inside an already network-none/lo-only Docker
container, uid65534. It never sets up Docker/networking, downloads dependencies
or starts SSH/YARN. It requires explicit verified Hadoop3.5/JDK17, matching
HDFS-enabled scribed and existing private library prefixes. JDK21/native loader
preflight failures stop before NameNode format/start and retain diagnostics.

The two Hadoop foreground processes bind loopback; their actual owned socket
inventory is checked. Original scribed retains its wildcard socket, confined by
network-none with only lo. The 120-second work budget uses monotonic per-operation
bounds; owned-process teardown is bounded separately and cannot be interrupted by
an asynchronous deadline signal. The inherited environment cannot select Hadoop
worker/SSH mode, another SDK or extra JVM flags.

The private directory includes an unrelated empty `.fixture-seed`: original
FileStore lists before creating its file, and HdfsFile throws on a NULL directory
listing, including an empty-list shape. This recorded normal-case precondition
avoids changing or claiming validation of the original empty-directory edge.

Expected data is derived from public fcd294f FileStore::writeMessages/openInternal
and HdfsFile::openWrite/createSymlink: first `A\0B\n\xfftail` (9 bytes), then a new
owned Scribe process appends `Z` (10 bytes). `_current` is a regular marker file
containing `fixture_00000`, not a filesystem symlink. Independent HDFS CLI reads,
exact three-file inventory, fresh counters, one registered DataNode, safemode OFF,
healthy distributed block locations and full child/listener cleanup are required.
No actual historical libhdfs binary comparison, durable ACK, failure recovery or
production cluster operation is claimed by this bounded test.

```sh
python3 -B tools/daemon_hdfs.py --run-isolated-hdfs \
  --hadoop /absolute/verified/hadoop-3.5.0 \
  --java-home /absolute/verified/jdk17 \
  --scribed /absolute/matching/hdfs-enabled/scribed \
  --library-dir /absolute/existing/thrift/lib \
  --library-dir /absolute/existing/fb303/lib \
  --library-dir /absolute/existing/boost-event/lib \
  --output /absolute/new/private-hdfs-evidence
```

Proposed Docker ceiling, subject to operational resource preflight:2 CPUs,
3GiB memory,512 PIDs and4GiB free disposable disk. NameNode heap512MiB,
DataNode/Scribe JNI256MiB each. No host mounts/socket, published ports, privileged
mode or host network. Stop/reap only owned children; preserve all existing
operational container IDs. This resource proposal is not a measured minimum.

### Actual isolated server result

2026-10-05: the source-defined modern case passed using the existing official
Ubuntu26.04 image pinned to digest
`88a381d5b5eeb2b35d3ad70925a362c37ce569daf43ede89ff818ec20e4d3794`,
privately verified Ubuntu JRE17.0.20.1 and the previous signature/hash-verified
Hadoop3.5 distribution. Matching HDFS-enabled scribed SHA256 was
`a0a815375be63a315853c8736cd7696669b9b8de75fbea5a1dfab94a2e022b23`.
JDK17/Hadoop version, native ldd and scribed help preflight all passed before
formatting fresh container-only directories. No new daemon clean build occurred.

The first disposable container failed because its default hostname did not
resolve in network-none, causing Hadoop HTTP authentication initialization to
exit. Both Hadoop children were reaped and listeners restored to empty; raw
failure evidence was retained. A new container set only its hostname to
`localhost`; an extra pre-format check resolved it solely to127.0.0.1/::1.
No permission/authentication/registration/JVM security check was disabled.

Actual readiness reported one live DataNode and safemode OFF (three attempts).
All owned Hadoop listeners were loopback, including its ephemeral internal HTTP
proxy port. Initial exact binary9 bytes and restart append10 bytes, fresh received
counters2/1, the three regular files including the seed, marker bytes
`fixture_00000` and HEALTHY block location127.0.0.1:19866 passed. Both Scribe
children exited/cleaned0. Owned NameNode/DataNode received SIGTERM, exited143 and
were reaped; listeners before/after were empty. The container exited0 without OOM.

The actual Docker limits were network-none/no mounts or published ports,
uid65534, all capabilities dropped, no-new-privileges,2CPUs/3GiB/512PIDs.
Before the successful attempt host18CPUs,2-second busy1.67%,load0.81/1.03/0.74,
MemAvailable61.44GB and disk free651.40GB were observed, with no other build.
All31 operating container IDs were unchanged, including the previous30.
Server full194 tests had failure/error/skip0; all40 production/fixture C++/header/IDL
files matched the existing build. Cloud offline9 also passed. A Mac offline
attempt yielded7PASS/2ERROR because the Linux fixture hardcodes `/bin/true`,
absent on that Mac; no test was relaxed or changed. Mac support is not established.

This closes one normal modern distributed HDFS storage/restart-append path,
with the explicitly seeded directory precondition. It does not establish
historical libhdfs binary equivalence, distributed fault recovery, permissions/
replication matrix, durable ACK or performance. No host service/system/security/
power settings changed. Raw evidence includes the failed preparation attempt.

## Rocky 8/9 후속 소스 검증

[Rocky HDFS 기록](rocky-hdfs.md)은 공식 native client를 각 배포판 ABI로 재빌드하고
정상 NSS 비특권 계정으로 전체 HDFS build/220 tests/local JNI와 동일한 기존 single-DN
daemon/독립 reader/restart append를 확인한다. IDL·production C++·이 runner의 UID65534
및 network-none guard는 변경하지 않았다. HDFS RPM·historical binary differential·
권한/복제/장애 matrix와 운영 배포는 미검증이다.
