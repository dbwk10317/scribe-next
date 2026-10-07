"""Bounded sender/receiver/consumer operational scenarios for daemon_differential.

송신측 = scribed relaying through a buffer store (network primary, file spool secondary;
tools/daemon_spool.conf.template), 수신측 = scribed writing ordinary file stores
(tools/daemon_differential.conf.template), 소비 클라이언트 = this harness reading the
receiver directory read-only (consumer_view). Sender listens on --port, receiver on
--port+1. Every expectation below is derived from src/store.cpp, src/store_queue.cpp,
src/conn_pool.cpp, src/scribe_server.cpp and src/file.cpp (same behaviour in the original fcd294f).
"""
import binascii, hashlib, os, signal, struct, time

FIX, OTHER = b'fixture', b'other'
BASE = {'mixed-relay-stream': 'relay-stream', 'mixed-sender-restart-spool': 'sender-restart-spool'}
# Config edits on the two existing templates; each old text must exist exactly as written.
SENDER_EDITS = {'relay-stream': [('category=fixture', 'categories=fixture other')],
                # target_write_size=1: addMessage signals the queue thread at once, so every
                # sender Log is relayed immediately instead of at the next second boundary.
                'throttle-retry': [('target_write_size=16384', 'target_write_size=1')]}
RECEIVER_EDITS = {'relay-stream': [('category=fixture', 'category=default'), ('max_size=1000000', 'max_size=4')],
                  'throttle-retry': [('max_msg_per_second=2000000', 'max_msg_per_second=4'),
                                     ('target_write_size=16384', 'target_write_size=1')]}


def frames(entries):
    # Ordinary buffer spool (FileStore isBufferFile, add_newlines=0, writeCategory=no):
    # StdFile::getFrame little-endian uint32 length, then the message bytes.
    return b''.join(struct.pack('<I', len(value)) + value for category, value in entries)


def joined(entries, category=FIX):
    return b''.join(value for name, value in entries if name == category)


def snapshot(c, files, links=None):
    return {'files': [{'path': p, 'bytes': len(d), 'hex': c.hexbytes(d), 'sha256': hashlib.sha256(d).hexdigest()}
                      for p, d in sorted(files.items())],
            'symlinks': [{'path': p, 'target': t} for p, t in sorted((links or {}).items())]}


def receiver(c, data):
    # Ordinary receiver, rotate_on_reopen unset: FileStoreBase::open -> openInternal(false)
    # reuses the newest suffix, so a restarted receiver appends to the same fixture_00000.
    return snapshot(c, {'fixture_00000': data}, {'fixture_current': 'fixture_00000'})


def spool(c, entries=None):
    # Buffer secondary: ROLL_NEVER, no symlink. deleteOldest removes the file after replay.
    return snapshot(c, {'spool_00000': frames(entries)} if entries else {})


def consumer_view(c, snap):
    """What a log consumer reads: files with size/SHA256, the _current targets and, per
    <dir>/<base>_NNNNN family, the bytes of every file concatenated in suffix order."""
    streams = {}
    for item in snap['files']:
        base, sep, suffix = item['path'].rpartition('_')
        if not sep or not suffix.isdigit(): raise ValueError('unexpected receiver file name')
        streams.setdefault(base, []).append((int(suffix), item['hex']))
    return {'files': [{'path': f['path'], 'bytes': f['bytes'], 'sha256': f['sha256']} for f in snap['files']],
            'current': snap['symlinks'],
            'streams': dict((base, ''.join(h for i, h in sorted(parts))) for base, parts in streams.items())}


def received(good, **extra):
    result = {'fixture:received good': good, 'scribe_overall:received good': good}
    result.update(extra)
    return result


def sender(good=0, sent=0, retries=0):
    result = received(good) if good else {}
    if retries: result.update({'fixture:retries': retries, 'scribe_overall:retries': retries})
    if sent: result['scribe_overall:sent'] = sent  # scribeConn::send: incCounter("sent", size) per OK
    return result


def relay_batches(c):
    p = c.PAYLOADS
    # The empty payload sits between nonempty fixture payloads: StoreQueue never drains an
    # empty-only queue (msgQueueSize>0 check), but it is drained and relayed with its neighbours.
    return [[(FIX, p[0]), (OTHER, b'o1'), (FIX, p[1]), (FIX, p[2])], [(FIX, b'second')], [(OTHER, b'o3'), (FIX, b'Z')]]


def specification(c, case):
    """Per role RPC (method, fields, expected value), exits, read-only phases and the consumer view."""
    base = BASE.get(case, case)
    v = c.hexbytes(b'2.2')
    log = lambda entries: (b'Log', c.log_fields(entries), 0)
    get = lambda name, value: (name, b'\0', value)
    stop = (b'shutdown', b'\0', None)
    p = c.PAYLOADS
    if base == 'relay-stream':
        b1, b2, b3 = relay_batches(c)
        # Receiver category=default: each category is a FileStore copy in <cat>/<cat>_NNNNN
        # (copyCommon). max_size=4: writeMessages writes, then rotates while currentSize>4.
        # Every rotation here is caused by one message longer than 4 bytes, so the split does
        # not depend on how the queues batch messages: binary5 fills _00000; tail (4) stays;
        # 'second' makes _00001 10 bytes and opens empty _00002; 'Z' goes to _00002.
        # 'other' reaches only 4 bytes and never rotates. Empty payload adds no bytes.
        def tree(fixture, current, other):
            files = dict(('fixture/fixture_%05d' % i, d) for i, d in enumerate(fixture))
            files['other/other_00000'] = other
            return snapshot(c, files, {'fixture/fixture_current': 'fixture_%05d' % current,
                                       'other/other_current': 'other_00000'})
        good = {'fixture:received good': 5, 'other:received good': 2, 'scribe_overall:received good': 7}
        phases = {'stream-1': tree([p[0], p[2]], 1, b'o1'),
                  'stream-2': tree([p[0], p[2] + b'second', b''], 2, b'o1'),
                  'stream-3': tree([p[0], p[2] + b'second', b'Z'], 2, b'o1o3'),
                  # categories= copies open at startup with the receiver up: SENDING_BUFFER opens
                  # <cat>/<cat>_00000, the first periodicCheck reads it empty, deleteOldest, STREAMING.
                  'final_spool': snapshot(c, {})}
        phases['final_receiver'] = phases['stream-3']
        roles = {'receiver': [get(b'getVersion', v), get(b'getStatus', 2), get(b'getCounters', {}),
                              get(b'getCounters', good), stop],
                 # No retries: the receiver accepted every relay Log. sent 7 = every entry.
                 'sender': [get(b'getVersion', v), log(b1), log(b2), log(b3),
                            get(b'getCounters', dict(good, **{'scribe_overall:sent': 7})), get(b'getStatus', 2), stop]}
        streams = {'fixture/fixture': joined(b1 + b2 + b3), 'other/other': joined(b1 + b2 + b3, OTHER)}
        exits = {'receiver': 0, 'sender': 0}
    elif base in ('receiver-restart', 'receiver-crash'):
        b1, b2, b3 = [(FIX, p[0]), (FIX, p[2])], [(FIX, b'second'), (FIX, b'third')], [(FIX, b'Z')]
        first = [get(b'getVersion', v), get(b'getStatus', 2), get(b'getCounters', {}), get(b'getCounters', received(2))]
        roles = {'receiver': first + ([stop] if base == 'receiver-restart' else []),
                 # Batch 2 after the receiver is gone: the unpooled NetworkStore still has its old
                 # socket, scribeConn::send gets a TTransportException (EOF/RST) -> fatal ->
                 # CONN_FATAL -> NetworkStore::close; BufferStore::handleMessages ->
                 # changeState(DISCONNECTED) counts retries once and the secondary spools both.
                 # Clean shutdown and SIGKILL look the same here: the kernel closes the receiver
                 # socket either way and the sender only notices on its next send.
                 # getStatus stays ALIVE: CONN_FATAL never calls setStatus (only open() does).
                 'sender': [get(b'getVersion', v), log(b1), log(b2),
                            get(b'getCounters', sender(4, 2, 1)), get(b'getStatus', 2),
                            # retry_interval=10/range=1 (1/2=0, rand()%1=0): periodicCheck reopens
                            # once now-lastOpenAttempt>10, SENDING_BUFFER replays, deleteOldest.
                            get(b'getCounters', sender(4, 4, 1)), get(b'getStatus', 2),
                            log(b3), get(b'getCounters', sender(5, 5, 1)), stop],
                 'receiver-restarted': [get(b'getVersion', v), get(b'getStatus', 2), get(b'getCounters', {}),
                                        get(b'getCounters', received(3)), stop]}
        whole = joined(b1 + b2 + b3)
        phases = {'before_stop': receiver(c, joined(b1)), 'spooled': spool(c, b2),
                  'replayed': receiver(c, joined(b1 + b2)), 'drained': spool(c),
                  'streamed': receiver(c, whole), 'final_receiver': receiver(c, whole), 'final_spool': spool(c)}
        streams = {'fixture': whole}
        exits = {'receiver': 0 if base == 'receiver-restart' else -signal.SIGKILL, 'sender': 0, 'receiver-restarted': 0}
    elif base == 'sender-restart-spool':
        b1, b2 = [(FIX, p[0]), (FIX, p[2])], [(FIX, b'Z')]
        roles = {# Receiver absent: BufferStore::open -> NetworkStore "Failed to connect" (WARNING),
                 # DISCONNECTED counts retries 1; batch 1 goes to spool_00000. Shutdown closes the
                 # secondary without deleting it (BufferStore::close).
                 'sender': [get(b'getVersion', v), log(b1), get(b'getCounters', sender(2, 0, 1)),
                            get(b'getStatus', 5), stop],
                 'receiver': [get(b'getVersion', v), get(b'getStatus', 2), get(b'getCounters', {}),
                              get(b'getCounters', received(3)), stop],
                 # Same config/spool directory, receiver up: open() succeeds -> SENDING_BUFFER (no
                 # retries); the first periodicCheck readOldest()s the file the previous process
                 # wrote, sends it, deleteOldest, empty -> STREAMING. Fresh counters: sent 2 only.
                 'sender-restarted': [get(b'getVersion', v), get(b'getCounters', sender(0, 2)), get(b'getStatus', 2),
                                      log(b2), get(b'getCounters', sender(1, 3)), stop]}
        whole = joined(b1 + b2)
        phases = {'spooled': spool(c, b1), 'after_sender_exit': spool(c, b1), 'replayed': receiver(c, joined(b1)),
                  'drained': spool(c), 'streamed': receiver(c, whole), 'final_receiver': receiver(c, whole),
                  'final_spool': spool(c)}
        streams = {'fixture': whole}
        exits = {'sender': 0, 'receiver': 0, 'sender-restarted': 0}
    elif base == 'throttle-retry':
        a, b, z = [(FIX, p[0]), (FIX, p[2])], [(FIX, b'second'), (FIX, b'third')], [(FIX, b'Z')]
        # Receiver max_msg_per_second=4. throttleDeny resets its count when time() changes and
        # always allows num_messages > max/2 (=2) WITHOUT counting it, so two batches can never
        # be denied (a,b<=2 means a+b<=4). Three sender Logs in one receiver second, each relayed
        # alone (<=2 entries, split or not): 2 -> count 2, 2 -> count 4, then 'Z' 4+1>4 ->
        # TRY_LATER, "denied for rate". scribeConn::send returns CONN_TRANSIENT (not fatal), so
        # NetworkStore stays open; BufferStore goes DISCONNECTED (retries 1) and spools 'Z'.
        # The reopen after retry_interval reuses the open connection; 'Z' arrives in a new second.
        roles = {'receiver': [get(b'getVersion', v), get(b'getStatus', 2), get(b'getCounters', {}),
                              get(b'getCounters', received(5, **{'scribe_overall:denied for rate': 1})), stop],
                 'sender': [get(b'getVersion', v), log(a), log(b), log(z),
                            get(b'getCounters', sender(5, 4, 1)), get(b'getStatus', 2),
                            get(b'getCounters', sender(5, 5, 1)), get(b'getStatus', 2), stop]}
        whole = joined(a + b + z)
        phases = {'stream-a': receiver(c, joined(a)), 'stream-b': receiver(c, joined(a + b)), 'spooled': spool(c, z),
                  'replayed': receiver(c, whole), 'drained': spool(c), 'final_receiver': receiver(c, whole),
                  'final_spool': spool(c)}
        streams = {'fixture': whole}
        exits = {'receiver': 0, 'sender': 0}
    else:
        raise ValueError('unknown scenario case')
    consumer = consumer_view(c, phases['final_receiver'])
    if consumer['streams'] != dict((k, c.hexbytes(d)) for k, d in streams.items()):
        raise ValueError('scenario file split does not preserve message order')
    return {'roles': roles, 'exits': exits, 'phases': phases, 'consumer': consumer}


def role_targets(c, case, lane):
    other = 'modern' if lane == 'old' else 'old'
    targets = dict((role, lane) for role in specification(c, case)['roles'])
    if case == 'mixed-relay-stream': targets['receiver'] = other
    if case == 'mixed-sender-restart-spool': targets.update({'sender-restarted': other, 'receiver': 'modern'})
    return targets


def config(c, case, template, path, port, edits):
    with open(template) as f: text = f.read()
    for old, new in edits.get(BASE.get(case, case), ()):
        if old not in text: raise ValueError('scenario template changed')
        text = text.replace(old, new)
    return text.replace('@PORT@', str(port)).replace('@DOWNSTREAM_PORT@', str(c.PORT + 1)).replace('@SEPARATE_TEMP_OUTPUT@', path)


def kill(session):
    process, unused, part, unused_directory = session
    # Owned session from Popen(setsid) whose socket ownership was verified; never by name.
    if process.poll() is not None: raise ValueError('receiver exited before injected crash')
    os.killpg(process.pid, signal.SIGKILL)
    deadline = time.time() + 10
    while process.poll() is None and time.time() < deadline: time.sleep(0.05)
    if process.returncode != -signal.SIGKILL: raise ValueError('injected crash exit differs')
    part['exit'] = process.returncode; part['status'] = 'passed'


def run_lane(c, helpers, case, lane):
    spec = specification(c, case); targets = role_targets(c, case, lane)
    result = {'case': case, 'lane': lane, 'targets': targets, 'status': 'failed'}
    result_path = os.path.join(c.ROOT, 'evidence', lane, 'scenario-result.json')
    os.makedirs(os.path.dirname(result_path)); c.save_json(result_path, result)
    recv_path = os.path.join(c.ROOT, lane + '-receiver'); spool_path = os.path.join(c.ROOT, lane + '-spool')
    os.makedirs(recv_path); os.makedirs(spool_path)
    tools = os.path.dirname(os.path.abspath(__file__))
    send_conf = config(c, case, os.path.join(tools, 'daemon_spool.conf.template'), spool_path, c.PORT, SENDER_EDITS)
    recv_conf = config(c, case, c.TEMPLATE, recv_path, c.PORT + 1, RECEIVER_EDITS)
    # Both ports must be absent before any sender retry can contact a receiver.
    c.port_free(c.PORT); c.port_free(c.PORT + 1)

    def start(role, conf, port, timeout=10):
        return helpers.owned_daemon(c, lane, role, conf, port, timeout, target_lane=targets[role])

    def step(session, role, seq):
        name, fields, wanted = spec['roles'][role][seq - 1]
        unused, conn, part, directory = session
        result[role] = part
        if c.call(conn, name, seq, fields, directory, part['records']) != wanted:
            raise ValueError('%s %s %d/%s differs' % (case, role, seq, name.decode()))

    def observe(phase, path, timeout=20):
        result[phase] = helpers.wait_output(c, path, spec['phases'][phase], timeout)
        c.save_json(result_path, result)

    def window(since, limit=8):
        # A retry needs now-lastOpenAttempt>10 in whole seconds, i.e. at least int(since)+11.
        # 8 s (as in the spool case) leaves margin; later is a failure, never relabelled.
        remaining = limit - (time.time() - since)
        if remaining <= 0: raise ValueError('%s missed the pre-retry window' % case)
        return remaining

    base = BASE.get(case, case)
    if base == 'relay-stream':
        with start('receiver', recv_conf, c.PORT + 1) as r:
            for seq in (1, 2, 3): step(r, 'receiver', seq)
            with start('sender', send_conf, c.PORT) as s:
                step(s, 'sender', 1)
                for seq, phase in ((2, 'stream-1'), (3, 'stream-2'), (4, 'stream-3')):
                    step(s, 'sender', seq); observe(phase, recv_path)
                step(r, 'receiver', 4); step(s, 'sender', 5); step(s, 'sender', 6)
                helpers.shutdown(c, s, 7); helpers.shutdown(c, r, 5)
    elif base in ('receiver-restart', 'receiver-crash'):
        with start('receiver', recv_conf, c.PORT + 1) as r1:
            for seq in (1, 2, 3): step(r1, 'receiver', seq)
            with start('sender', send_conf, c.PORT) as s:
                step(s, 'sender', 1); step(s, 'sender', 2)
                observe('before_stop', recv_path)
                step(r1, 'receiver', 4)
                if base == 'receiver-restart': helpers.shutdown(c, r1, 5)
                else: kill(r1)
                c.save_json(result_path, result)
                sent_batch2 = time.time()
                step(s, 'sender', 3)
                observe('spooled', spool_path, window(sent_batch2))
                window(sent_batch2); step(s, 'sender', 4); step(s, 'sender', 5)
                # Same config text and directory; new evidence role only.
                with start('receiver-restarted', recv_conf, c.PORT + 1, window(sent_batch2)) as r2:
                    for seq in (1, 2, 3): step(r2, 'receiver-restarted', seq)
                    window(sent_batch2)  # fresh receiver counters were read before any replay
                    observe('replayed', recv_path); observe('drained', spool_path)
                    for seq in (6, 7, 8): step(s, 'sender', seq)
                    observe('streamed', recv_path)
                    step(r2, 'receiver-restarted', 4); step(s, 'sender', 9)
                    helpers.shutdown(c, s, 10); helpers.shutdown(c, r2, 5)
    elif base == 'sender-restart-spool':
        with start('sender', send_conf, c.PORT) as s1:
            step(s1, 'sender', 1); step(s1, 'sender', 2)
            observe('spooled', spool_path, window(s1[2]['started_at']))
            window(s1[2]['started_at']); step(s1, 'sender', 3); step(s1, 'sender', 4)
            helpers.shutdown(c, s1, 5)
        # Read-only check after the first sender exited and was reaped: the spool survives.
        observe('after_sender_exit', spool_path, 0)
        with start('receiver', recv_conf, c.PORT + 1) as r:
            for seq in (1, 2, 3): step(r, 'receiver', seq)
            with start('sender-restarted', send_conf, c.PORT) as s2:
                step(s2, 'sender-restarted', 1)
                observe('replayed', recv_path); observe('drained', spool_path)
                for seq in (2, 3, 4): step(s2, 'sender-restarted', seq)
                observe('streamed', recv_path)
                step(r, 'receiver', 4); step(s2, 'sender-restarted', 5)
                helpers.shutdown(c, s2, 6); helpers.shutdown(c, r, 5)
    else:
        with start('receiver', recv_conf, c.PORT + 1) as r:
            for seq in (1, 2, 3): step(r, 'receiver', seq)
            with start('sender', send_conf, c.PORT) as s:
                step(s, 'sender', 1)
                # The receiver and harness share the clock: begin just after a second boundary
                # so the three relays fit in one receiver second (about 0.1-0.2 s here).
                time.sleep(1.02 - time.time() % 1)
                timing = result['timing'] = {'aligned': time.time()}
                step(s, 'sender', 2); observe('stream-a', recv_path, 2); timing['a_seen'] = time.time()
                step(s, 'sender', 3); observe('stream-b', recv_path, 2); timing['b_seen'] = time.time()
                step(s, 'sender', 4); timing['z_ok'] = time.time()
                if int(timing['z_ok']) != int(timing['aligned']):
                    raise ValueError('throttle relays crossed a second boundary: %r' % timing)
                observe('spooled', spool_path, window(timing['z_ok']))
                window(timing['z_ok']); step(s, 'sender', 5); step(s, 'sender', 6)
                observe('replayed', recv_path); observe('drained', spool_path)
                step(r, 'receiver', 4); step(s, 'sender', 7); step(s, 'sender', 8)
                helpers.shutdown(c, s, 9); helpers.shutdown(c, r, 5)
    for phase, path in (('final_receiver', recv_path), ('final_spool', spool_path)):
        files, links = c.output_snapshot(path); result[phase] = {'files': files, 'symlinks': links}
    result['consumer'] = consumer_view(c, result['final_receiver'])
    if any(result[k] != spec['phases'][k] for k in ('final_receiver', 'final_spool')) or result['consumer'] != spec['consumer']:
        c.save_json(result_path, result); raise ValueError('shutdown changed scenario outputs')
    result['status'] = 'passed'; c.save_json(result_path, result)
    return result


def compare_lanes(c, old, new, case):
    spec = specification(c, case); checks = {}
    for lane, label in ((old, 'old'), (new, 'modern')):
        targets = role_targets(c, case, label)
        if lane.get('case') != case or lane.get('lane') != label or lane.get('status') != 'passed':
            raise ValueError('incomplete scenario lane')
        if lane.get('targets') != targets: raise ValueError('scenario direction differs')
        for phase, wanted in spec['phases'].items():
            if lane.get(phase) != wanted: raise ValueError('missing or wrong scenario phase ' + phase)
        if lane.get('consumer') != spec['consumer']: raise ValueError('consumer view differs')
        for role, requests in spec['roles'].items():
            part = lane.get(role) or {}; records = part.get('records', [])
            command = c.TARGETS[targets[role]]['command'] + ['-c', os.path.join(c.ROOT, label + '-' + role + '.conf')]
            if part.get('target_lane') != targets[role] or part.get('command') != command:
                raise ValueError('scenario target identity differs')
            exit_code = spec['exits'][role]
            if part.get('status') != 'passed' or part.get('exit') != exit_code or part.get('cleanup_exit') != exit_code or len(records) != len(requests):
                raise ValueError('incomplete scenario child ' + role)
            for seq, (name, fields, wanted) in enumerate(requests, 1):
                r = records[seq - 1]; oneway = name == b'shutdown'
                if r['method'] != name.decode() or r['sequence'] != seq or r.get('oneway') != oneway or r['request_hex'] != c.hexbytes(c.framed(name, seq, fields, oneway)):
                    raise ValueError('scenario request differs')
                if oneway:
                    if 'reply_hex' in r: raise ValueError('oneway scenario shutdown has reply')
                    continue
                wire = binascii.unhexlify(r['reply_hex'])
                if len(wire) < 4 or not 0 < len(wire) - 4 <= c.MAX_REPLY or struct.unpack('>I', wire[:4])[0] != len(wire) - 4:
                    raise ValueError('invalid scenario reply frame')
                if c.parse_reply(wire[4:], name, seq) != r.get('value') or r.get('value') != wanted:
                    raise ValueError('scenario reply value differs')
    for role, requests in spec['roles'].items():
        for seq, (name, unused, unused_value) in enumerate(requests, 1):
            a = old[role]['records'][seq - 1]; b = new[role]['records'][seq - 1]
            checks['%s-request-%d' % (role, seq)] = a['request_hex'] == b['request_hex']
            if name not in (b'getVersion', b'shutdown'): checks['%s-reply-%d' % (role, seq)] = a['reply_hex'] == b['reply_hex']
    for phase in spec['phases']: checks[phase] = old[phase] == new[phase]
    checks['consumer'] = old['consumer'] == new['consumer']
    result = {'case': case, 'status': 'passed' if all(checks.values()) else 'failed', 'checks': checks,
              'directions': [role_targets(c, case, 'old'), role_targets(c, case, 'modern')],
              'scope': 'bounded sender/receiver/consumer scenario with full ordinary spool replay; '
                       'no partial replay, durability, exactly-once or production-config claim'}
    if case in BASE: result['target_commands'] = dict((lane, c.TARGETS[lane]['command']) for lane in ('old', 'modern'))
    return result
