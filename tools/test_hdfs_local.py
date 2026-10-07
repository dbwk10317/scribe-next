#!/usr/bin/env python3
"""Opt-in bounded libhdfs/JNI local-filesystem probe; never starts Hadoop services."""
import argparse
import os
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("build", "hadoop", "java-home", "thrift", "fb303", "tools"):
        parser.add_argument("--" + name, required=True, type=Path)
    args = parser.parse_args()
    paths = {name: value.resolve(strict=True) for name, value in vars(args).items()}
    build, hadoop, java, thrift, fb303, tools = (paths[name] for name in
        ("build", "hadoop", "java_home", "thrift", "fb303", "tools"))
    for path in (build / "src/gen-cpp/scribe_types.h", hadoop / "include/hdfs.h",
                 hadoop / "lib/native/libhdfs.so", java / "lib/server/libjvm.so"):
        if not path.is_file():
            parser.error("missing required existing dependency: " + str(path))
    with tempfile.TemporaryDirectory(prefix="scribe-hdfs-local-") as temporary:
        work = Path(temporary)
        for name in ("conf", "data", "tmp"):
            (work / name).mkdir()
        (work / "conf/core-site.xml").write_text('''<configuration>
<property><name>fs.defaultFS</name><value>file:///</value></property>
<property><name>fs.file.impl</name><value>org.apache.hadoop.fs.RawLocalFileSystem</value></property>
<property><name>fs.file.impl.disable.cache</name><value>true</value></property>
</configuration>''')
        (work / "conf/hdfs-site.xml").write_text("<configuration/>")
        includes = [ROOT / "src", build, hadoop / "include", thrift / "include",
                    thrift / "include/thrift", fb303 / "include/thrift",
                    fb303 / "include/thrift/fb303", tools / "include",
                    tools / "include/x86_64-linux-gnu"]
        libraries = [hadoop / "lib/native", java / "lib/server", thrift / "lib",
                     tools / "lib", tools / "lib/x86_64-linux-gnu"]
        command = ["g++", "-std=c++17", "-O0", "-g", "-pthread", "-DUSE_SCRIBE_HDFS=1"]
        command += ["-I" + str(path) for path in includes]
        command += [str(ROOT / path) for path in
                    ("test/cpp/hdfs_contracts.cpp", "src/HdfsFile.cpp", "src/file.cpp")]
        command += ["-L" + str(path) for path in libraries]
        stdcxxfs = re.search(r"^STDCXXFS_LIB = (.*)$", (build / "src/Makefile").read_text(), re.M).group(1)
        command += ["-lhdfs", "-ljvm", *stdcxxfs.split(), "-lthrift",
                    "-o", str(work / "probe")]
        subprocess.run(command, check=True, timeout=60)
        env = dict(os.environ)
        for name in ("JAVA_TOOL_OPTIONS", "JDK_JAVA_OPTIONS", "_JAVA_OPTIONS"):
            if env.get(name):
                parser.error("unsupported inherited JVM override: " + name)
        env.update(JAVA_HOME=str(java), HADOOP_PREFIX=str(hadoop),
                   HADOOP_CONF_DIR=str(work / "conf"),
                   CLASSPATH=os.pathsep.join(map(str, [work / "conf",
                       hadoop / "share/hadoop/common/*", hadoop / "share/hadoop/common/lib/*",
                       hadoop / "share/hadoop/hdfs/*", hadoop / "share/hadoop/hdfs/lib/*"])),
                   LIBHDFS_OPTS="-Xmx256m -Xms32m -Djava.io.tmpdir=" + str(work / "tmp"),
                   LD_LIBRARY_PATH=os.pathsep.join(map(str, libraries)))
        subprocess.run([str(work / "probe"), str(work / "data")], env=env,
                       cwd=work, check=True, timeout=30)


if __name__ == "__main__":
    main()
