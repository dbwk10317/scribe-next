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
boundary. Distributed HDFS create/append/flush/list/delete, Namenode failures,
permissions, replication and end-to-end Scribe HDFS file-store behavior remain
unverified. A bounded isolated official Hadoop JDK17 server lane is the next
meaningful HDFS validation, requiring a separate explicit cluster/resource plan.
Historical libhdfs binary old/new equivalence is also unverified. The other ten
normal-store actual comparisons do not include distributed HDFS. Performance
comparison remains deferred by the user.
