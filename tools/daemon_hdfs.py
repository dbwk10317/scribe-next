#!/usr/bin/env python3
"""Opt-in modern single-DN HDFS check inside an already isolated container.

Never creates Docker, changes networking, installs dependencies or starts SSH/YARN.
Expected bytes come from public fcd294f FileStore/HdfsFile contracts; this is not
historical libhdfs binary equivalence or a durable-ACK test.
"""
import argparse
from contextlib import contextmanager
import hashlib
import ipaddress
import os
from pathlib import Path
import re
import subprocess
import time
import traceback
import xml.etree.ElementTree as ET

import daemon_differential as c
import daemon_spool_case as helpers

FIRST = [(b'fixture', b'A\0B\n\xff'), (b'fixture', b'tail')]
SECOND = [(b'fixture', b'Z')]
NAMES = ['.fixture-seed', 'fixture_00000', 'fixture_current']
PORTS = (19000, 19870, 19866, 19867, 19864, 14630)
DEADLINE = None


def budget(limit):
    remaining = limit if DEADLINE is None else min(limit, DEADLINE - time.monotonic())
    if remaining <= 0:
        raise TimeoutError('overall HDFS validation deadline reached')
    return remaining


def listeners():
    result = []
    for protocol in ("tcp", "tcp6"):
        for line in Path("/proc/net/" + protocol).read_text().splitlines()[1:]:
            fields = line.split()
            if fields[3] == "0A":
                result.append([protocol, fields[1]])
    return sorted(result)


def loopback_endpoint(protocol, endpoint):
    raw = bytes.fromhex(endpoint.split(':')[0])
    address = raw[::-1] if protocol == 'tcp' else b''.join(raw[i:i + 4][::-1] for i in range(0, 16, 4))
    return ipaddress.ip_address(address).is_loopback


def hadoop_listeners(process):
    inodes = set()
    for descriptor in Path('/proc/%d/fd' % process.pid).iterdir():
        try:
            target = os.readlink(descriptor)
        except FileNotFoundError:
            continue
        if target.startswith('socket:['):
            inodes.add(target[8:-1])
    found = []
    for protocol in ('tcp', 'tcp6'):
        for line in Path('/proc/net/' + protocol).read_text().splitlines()[1:]:
            fields = line.split()
            if fields[3] == '0A' and fields[9] in inodes:
                if not loopback_endpoint(protocol, fields[1]):
                    raise ValueError('owned Hadoop listener is not loopback: ' + fields[1])
                found.append([protocol, fields[1]])
    if not found:
        raise ValueError('owned Hadoop listener inventory missing')
    return sorted(found)


def java17(text):
    match = re.search(r'(?:openjdk|java) version "([0-9]+)', text)
    return bool(match and match.group(1) == '17')


def properties(work):
    return {'dfs.namenode.rpc-address': '127.0.0.1:19000',
            'dfs.namenode.rpc-bind-host': '127.0.0.1',
            'dfs.namenode.http-address': '127.0.0.1:19870',
            'dfs.namenode.http-bind-host': '127.0.0.1',
            'dfs.datanode.address': '127.0.0.1:19866',
            'dfs.datanode.ipc.address': '127.0.0.1:19867',
            'dfs.datanode.http.address': '127.0.0.1:19864',
            'dfs.datanode.hostname': 'localhost', 'dfs.http.policy': 'HTTP_ONLY',
            'dfs.replication': '1', 'dfs.namenode.safemode.min.datanodes': '1',
            'dfs.namenode.safemode.extension': '0',
            'dfs.namenode.name.dir': 'file://' + str(work / 'name'),
            'dfs.datanode.data.dir': 'file://' + str(work / 'data')}


def xml(path, values):
    root = ET.Element('configuration')
    for name, value in sorted(values.items()):
        prop = ET.SubElement(root, 'property')
        ET.SubElement(prop, 'name').text = name
        ET.SubElement(prop, 'value').text = value
    ET.ElementTree(root).write(path, encoding='utf-8', xml_declaration=True)


def command(args, env, log, timeout=20, check=True):
    """Own/reap even CLI children on deadline, including shell process groups."""
    with open(log, 'wb') as output, open(os.devnull, 'rb') as stdin:
        process = subprocess.Popen([str(x) for x in args], env=env, stdin=stdin,
                                   stdout=output, stderr=subprocess.STDOUT,
                                   start_new_session=True)
        try:
            code = process.wait(timeout=budget(timeout))
        finally:
            c.cleanup_process(process)
    data = Path(log).read_bytes()
    if check and code:
        raise ValueError('command failed (%s): %s; see %s' % (code, args, log))
    return code, data


@contextmanager
def foreground(role, hdfs, env, work, result):
    with open(work / (role + '.log'), 'wb') as output, open(os.devnull, 'rb') as stdin:
        process = subprocess.Popen([str(hdfs), role], env=env, stdin=stdin,
                                   stdout=output, stderr=subprocess.STDOUT,
                                   start_new_session=True)
        result[role] = {'pid': process.pid}
        try:
            yield process
        finally:
            result[role]['cleanup_exit'] = c.cleanup_process(process)
            result[role]['reaped'] = process.poll() is not None


def wait_ready(nn, dn, hdfs, env, work):
    until = time.monotonic() + 60
    attempts = 0
    while True:
        if nn.poll() is not None or dn.poll() is not None:
            raise ValueError('Hadoop foreground process exited during readiness')
        attempts += 1
        try:
            code, report = command([hdfs, 'dfsadmin', '-report'], env,
                                   work / 'readiness-report.log',
                                   timeout=min(10, max(0.01, until - time.monotonic())), check=False)
            safe_code, safe = command([hdfs, 'dfsadmin', '-safemode', 'get'], env,
                                      work / 'readiness-safemode.log',
                                      timeout=min(10, max(0.01, until - time.monotonic())), check=False)
        except subprocess.TimeoutExpired:
            code = safe_code = 1
            report = safe = b''
        if not code and not safe_code and b'Live datanodes (1):' in report and b'Safe mode is OFF' in safe:
            return {'attempts': attempts, 'live_datanodes': 1, 'safemode': 'OFF'}
        if time.monotonic() >= until:
            raise ValueError('one live DataNode/safemode readiness deadline failed')
        time.sleep(budget(0.2))


def inventory(hdfs, env, work, label):
    unused, data = command([hdfs, 'dfs', '-ls', '/fixture'], env, work / (label + '-ls.log'))
    lines = data.decode('utf-8').splitlines()
    names = sorted(line.split()[-1].rsplit('/', 1)[-1] for line in lines
                   if line.startswith('-') or line.startswith('d'))
    if names != NAMES or any(line.startswith('d') for line in lines):
        raise ValueError('HDFS inventory differs: ' + repr(names))
    # CLI reads distributed data independently of Scribe's unsupported readNext.
    for name in ('fixture_00000', 'fixture_current'):
        # stderr must not enter expected binary payloads.
        destination = work / (label + '-' + name)
        command([hdfs, 'dfs', '-get', '/fixture/' + name, destination], env,
                work / (label + '-' + name + '-get.log'))
    return {(name): (work / (label + '-' + name)).read_bytes()
            for name in ('fixture_00000', 'fixture_current')}


def scribe_stage(hdfs, env, work, label, entries, wanted, result):
    with open(c.TEMPLATE) as source:
        config = source.read().replace('@PORT@', str(c.PORT)).replace(
            '@SEPARATE_TEMP_OUTPUT@', '/fixture').replace('fs_type=std', 'fs_type=hdfs')
    config = 'num_thrift_server_threads=2\n' + config.replace(
        'max_msg_per_second=2000000', 'max_msg_per_second=0')
    with helpers.owned_daemon(c, 'modern', label, config, c.PORT, budget(20)) as session:
        process, conn, record, directory = session
        conn.settimeout(budget(3))
        if c.call(conn, b'getVersion', 1, b'\0', directory, record['records']) != c.hexbytes(b'2.2'):
            raise ValueError('unexpected Scribe version')
        if c.call(conn, b'getCounters', 2, b'\0', directory, record['records']) != {}:
            raise ValueError('per-process counters are not fresh')
        if c.call(conn, b'Log', 3, c.log_fields(entries), directory, record['records']) != 0:
            raise ValueError('Log was not accepted')
        # A bounded worker completion interval, not a durable ACK assertion.
        time.sleep(budget(2))
        count = len(entries)
        counters = {'fixture:received good': count, 'scribe_overall:received good': count}
        if c.call(conn, b'getCounters', 4, b'\0', directory, record['records']) != counters:
            raise ValueError('received counters differ')
        if c.call(conn, b'getStatus', 5, b'\0', directory, record['records']) != 2:
            raise ValueError('HDFS store did not reach ALIVE')
        helpers.shutdown(c, session, 6)
        budget(1)
    actual = inventory(hdfs, env, work, label)
    if actual != {'fixture_00000': wanted, 'fixture_current': b'fixture_00000'}:
        raise ValueError('HDFS data/regular marker bytes differ')
    result[label] = {'bytes_hex': c.hexbytes(wanted), 'counters': counters,
                     'files': NAMES, 'marker_hex': c.hexbytes(b'fixture_00000'),
                     'scribed_exit': record['exit'], 'cleanup_exit': record['cleanup_exit']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-isolated-hdfs', action='store_true')
    for name in ('hadoop', 'java-home', 'scribed', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--library-dir', action='append', type=Path, default=[])
    args = parser.parse_args()
    if not args.run_isolated_hdfs:
        parser.error('execution requires --run-isolated-hdfs')
    work = args.output.absolute()
    root = Path(__file__).resolve().parents[1]
    if work.exists() or work.is_symlink() or work == root or root in work.resolve().parents:
        parser.error('output must be new and outside the checkout')
    hadoop = args.hadoop.resolve(strict=True); java = args.java_home.resolve(strict=True)
    scribed = args.scribed.resolve(strict=True)
    for path in (hadoop / 'bin/hdfs', java / 'bin/java', scribed):
        if not path.is_file() or not os.access(path, os.X_OK) or path.stat().st_mode & 0o6000:
            parser.error('existing executable without setuid/setgid required: ' + str(path))
    for name in ('LD_PRELOAD', 'LD_AUDIT', 'JAVA_TOOL_OPTIONS', 'JDK_JAVA_OPTIONS', '_JAVA_OPTIONS'):
        if os.environ.get(name):
            parser.error('unsupported inherited override: ' + name)
    c.network_check()
    for port in PORTS:
        c.port_free(port)
    work.mkdir(); (work / 'conf').mkdir(); (work / 'evidence').mkdir()
    # The official Hadoop shell reads many HADOOP_*/HDFS_* worker/JVM controls.
    # Start from an allowlist, so inherited settings cannot select SSH or another SDK.
    env = {'PATH': '/usr/bin:/bin'}
    libs = [hadoop / 'lib/native', java / 'lib/server',
            *(path.resolve(strict=True) for path in args.library_dir)]
    env.update(JAVA_HOME=str(java), HADOOP_HOME=str(hadoop), HADOOP_PREFIX=str(hadoop),
               HADOOP_CONF_DIR=str(work / 'conf'), HADOOP_LOG_DIR=str(work),
               HADOOP_PID_DIR=str(work), HOME=str(work), LC_ALL='C', TZ='UTC',
               HADOOP_HEAPSIZE_MAX='256', HDFS_NAMENODE_OPTS='-Xmx512m -Xms64m',
               HDFS_DATANODE_OPTS='-Xmx256m -Xms32m', HADOOP_OPTS='', HADOOP_CLIENT_OPTS='', HADOOP_CLASSPATH='',
               LIBHDFS_OPTS='-Xmx256m -Xms32m -Djava.io.tmpdir=' + str(work),
               LD_LIBRARY_PATH=os.pathsep.join(map(str, libs)),
               CLASSPATH=os.pathsep.join(map(str, [work / 'conf',
                   hadoop / 'share/hadoop/common/*', hadoop / 'share/hadoop/common/lib/*',
                   hadoop / 'share/hadoop/hdfs/*', hadoop / 'share/hadoop/hdfs/lib/*'])))
    hdfs = hadoop / 'bin/hdfs'
    result = {'status': 'failed', 'scope': 'modern Hadoop3.5 single-DN distributed HDFS',
              'interfaces': sorted(os.listdir('/sys/class/net')), 'uid': os.getuid(),
              'listeners_before': listeners(),
              'hadoop': str(hadoop), 'java_home': str(java), 'scribed': str(scribed),
              'scribed_sha256': hashlib.sha256(scribed.read_bytes()).hexdigest(),
              'work_budget_seconds': 120, 'cleanup_allowance': 'bounded owned-group teardown outside work budget',
              'expected_source': 'public fcd294f FileStore::writeMessages/openInternal; HdfsFile::openWrite/createSymlink',
              'directory_precondition': 'unrelated empty .fixture-seed avoids original NULL-list empty-directory behavior'}
    global DEADLINE
    DEADLINE = time.monotonic() + 120
    try:
        unused, version = command([java / 'bin/java', '-version'], env, work / 'java-version.log')
        if not java17(version.decode('utf-8')):
            raise ValueError('Hadoop3.5 server requires JDK17; no cluster started')
        for label, binary in [('scribed', scribed), ('libhdfs', hadoop / 'lib/native/libhdfs.so')]:
            unused, dependencies = command(['ldd', binary], env, work / (label + '-ldd.log'))
            if b'not found' in dependencies:
                raise ValueError('native ABI/dependency preflight failed; no cluster started')
        command([scribed, '--help'], env, work / 'scribed-help-preflight.log')
        unused, version = command([hdfs, 'version'], env, work / 'hadoop-version.log')
        if re.findall(rb'(?m)^Hadoop [^\r\n]+', version) != [b'Hadoop 3.5.0']:
            raise ValueError('requires exact Hadoop3.5.0; no cluster started')
        xml(work / 'conf/core-site.xml', {'fs.defaultFS': 'hdfs://127.0.0.1:19000',
                                        'hadoop.tmp.dir': str(work / 'tmp')})
        xml(work / 'conf/hdfs-site.xml', properties(work))
        command([hdfs, 'namenode', '-format', '-nonInteractive'], env, work / 'format.log')
        with foreground('namenode', hdfs, env, work, result) as nn:
            with foreground('datanode', hdfs, env, work, result) as dn:
                result['readiness'] = wait_ready(nn, dn, hdfs, env, work)
                result['namenode']['listeners'] = hadoop_listeners(nn)
                result['datanode']['listeners'] = hadoop_listeners(dn)
                command([hdfs, 'dfs', '-mkdir', '/fixture'], env, work / 'mkdir.log')
                command([hdfs, 'dfs', '-touchz', '/fixture/.fixture-seed'], env, work / 'seed.log')
                c.ROOT = str(work); c.PORT = 14630
                c.TARGETS = {'modern': {'command': ['/usr/bin/env', '-i',
                    *(key + '=' + value for key, value in sorted(env.items())), str(scribed)],
                    'environment': {}}}
                scribe_stage(hdfs, env, work, 'initial', FIRST, b'A\0B\n\xfftail', result)
                scribe_stage(hdfs, env, work, 'append', SECOND, b'A\0B\n\xfftailZ', result)
                unused, blocks = command([hdfs, 'fsck', '/fixture', '-files', '-blocks', '-locations'], env,
                                         work / 'distributed-blocks.log')
                if b'Status: HEALTHY' not in blocks or b'127.0.0.1:19866' not in blocks:
                    raise ValueError('distributed healthy block-location evidence missing')
                result['status'] = 'passed'
    except BaseException:
        result['error'] = traceback.format_exc()
        raise
    finally:
        DEADLINE = None
        for port in PORTS:
            try:
                c.port_free(port)
            except BaseException:
                result['status'] = 'failed'; result['listener_cleanup_error'] = traceback.format_exc()
        result['listeners_after'] = listeners()
        if result['listeners_after'] != result['listeners_before']:
            result['status'] = 'failed'; result['listener_cleanup_error'] = 'listener inventory was not restored'
        c.save_json(str(work / 'result.json'), result)
        if result['status'] != 'passed' and 'error' not in result:
            raise ValueError('cleanup verification failed')


if __name__ == '__main__':
    main()
