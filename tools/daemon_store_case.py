"""Bounded single-daemon store cases for daemon_differential: time rotation, queue-size
backpressure and bucket hashing. One daemon on --port; this harness only sends RPCs and
reads the output directory. Every expectation below is derived from src/store.cpp,
src/store_queue.cpp, src/scribe_server.cpp and src/env_default.cpp (same in fcd294f).
"""
import binascii, hashlib, os, struct, time

CASES = ('rotation-time', 'backpressure', 'bucket-hash')
FIX = b'fixture'
ENTRIES = [(FIX, b'A\x00B\n\xff'), (FIX, b'tail')]
BUCKET_TEMPLATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'daemon_bucket_hash.conf.template')
# Edits on tools/daemon_differential.conf.template; each old text must occur exactly once.
EDITS = {
    # ROLL_OTHER: FileStoreBase::periodicCheck rotates when time(NULL) >= lastRollTime + 2,
    # checked by the queue thread every check_interval=1 s. target_write_size=1 writes each Log at once.
    'rotation-time': [('rotate_period=never', 'rotate_period=2s'), ('target_write_size=16384', 'target_write_size=1')],
    # StoreQueue drains only at max_write_interval or target_write_size, so the accepted bytes
    # stay queued; throttleRequest denies a Log while any queue holds more than max_queue_size.
    'backpressure': [('check_interval=1\n', 'check_interval=1\nmax_queue_size=8\n'),
                     ('target_write_size=16384', 'target_write_size=1000000'),
                     ('max_write_interval=1\n', 'max_write_interval=3600\n')]}


def djb2(key):
    """scribe::strhash::hash32: h = 5381; for each byte c (a signed char on x86-64, so bytes
    >= 0x80 add c - 256): h = h * 33 + c, modulo 2**32."""
    value = 5381
    for byte in bytearray(key):
        value = (value * 33 + (byte - 256 if byte > 127 else byte)) & 0xffffffff
    return value


def bucket(kind, message, count=3, delimiter=b'|'):
    """BucketStore::bucketize for key_hash/key_modulo: 0 (failure bucket) without a delimiter or
    with an empty key, else hash32(key) % n + 1 or atol(key) % n + 1, where atol's long is
    converted to unsigned long (-1 -> 2**64 - 1) and a non-numeric key reads as 0."""
    key, found, unused = message.partition(delimiter)
    if not found or not key: return 0
    if kind == 'key_hash': return djb2(key) % count + 1
    digits = key.lstrip(b'+-')
    digits = digits[:len(digits) - len(digits.lstrip(b'0123456789'))] if digits else b''
    number = int(digits or b'0') * (-1 if key.startswith(b'-') else 1)
    return (number & 0xffffffffffffffff) % count + 1


HASHED = [b'login|L', b'session|S', b'shop|P', b'caf\xc3\xa9|U', b'nokey', b'|empty']
MODULO = [b'7|seven', b'8|eight', b'9|nine', b'10|ten', b'x|zero', b'-1|neg', b'nodelim']


def bucket_files(kind, directory, messages):
    # remove_key=yes (getMessageWithoutKey: bytes after the first delimiter); bucket 0 is
    # failure_bucket=failed, buckets 1..3 are bucket_subdir b001..b003; add_newlines=0.
    files = {}
    for message in messages:
        index = bucket(kind, message)
        path = '%s/%s/data_00000' % (directory, 'failed' if index == 0 else 'b%03d' % index)
        files[path] = files.get(path, b'') + message.partition(b'|')[2 if b'|' in message else 0]
    return files


def snapshot(c, files, links):
    return {'files': [{'path': p, 'bytes': len(d), 'hex': c.hexbytes(d), 'sha256': hashlib.sha256(d).hexdigest()}
                      for p, d in sorted(files.items())],
            'symlinks': [{'path': p, 'target': t} for p, t in sorted(links.items())]}


def specification(c, case, date):
    """RPC steps (name, fields, value) and ('observe', phase, timeout) checkpoints; phases['final']
    is the output after the oneway shutdown exited 0."""
    v = c.hexbytes(b'2.2')
    log = lambda entries, value=0: (b'Log', c.log_fields(entries), value)
    get = lambda name, value: (name, b'\0', value)
    if case == 'rotation-time':
        name = lambda i: 'fixture-%s_%05d' % (date, i)  # ROLL_OTHER names carry the UTC date
        phases = {'first': snapshot(c, {name(0): b'first'}, {'fixture_current': name(0)}),
                  'rotated': snapshot(c, {name(0): b'first', name(1): b''}, {'fixture_current': name(1)}),
                  'second': snapshot(c, {name(0): b'first', name(1): b'second'}, {'fixture_current': name(1)})}
        phases['final'] = phases['second']
        steps = [get(b'getVersion', v), get(b'getStatus', 2), log([(FIX, b'first')]), ('observe', 'first', 1),
                 ('observe', 'rotated', 5), log([(FIX, b'second')]), ('observe', 'second', 1),
                 get(b'getCounters', {'fixture:received good': 2, 'scribe_overall:received good': 2})]
    elif case == 'backpressure':
        empty = snapshot(c, {'fixture_00000': b''}, {'fixture_current': 'fixture_00000'})
        denied = {'fixture:received good': 2, 'scribe_overall:received good': 2,
                  'fixture:denied for queue size': 1, 'scribe_overall:denied for queue size': 1}
        # 9 queued bytes > max_queue_size=8: the next Log is TRY_LATER (1) and is not counted good.
        phases = {'queued': empty, 'final': snapshot(c, {'fixture_00000': b'A\x00B\n\xfftail'},
                                                     {'fixture_current': 'fixture_00000'})}
        steps = [get(b'getVersion', v), get(b'getStatus', 2), log(ENTRIES), log([(FIX, b'Z')], 1),
                 get(b'getCounters', denied), ('observe', 'queued', 0)]
    elif case == 'bucket-hash':
        files = bucket_files('key_hash', 'hash', HASHED)
        files.update(bucket_files('key_modulo', 'modulo', MODULO))
        links = dict((p.rsplit('/', 1)[0] + '/data_current', 'data_00000') for p in files)
        phases = {'final': snapshot(c, files, links)}
        entries = [(b'hash', m) for m in HASHED] + [(b'modulo', m) for m in MODULO]
        counts = {'hash:received good': len(HASHED), 'modulo:received good': len(MODULO),
                  'scribe_overall:received good': len(entries)}
        steps = [get(b'getVersion', v), get(b'getStatus', 2), get(b'getCounters', {}), log(entries),
                 get(b'getCounters', counts)]
    else:
        raise ValueError('unknown store case')
    return {'steps': steps, 'phases': phases, 'requests': [s for s in steps if s[0] != 'observe'] + [get(b'shutdown', None)]}


def config(c, case, output):
    with open(BUCKET_TEMPLATE if case == 'bucket-hash' else c.TEMPLATE) as f: text = f.read()
    for old, new in EDITS.get(case, ()):
        if text.count(old) != 1: raise ValueError('store case template changed')
        text = text.replace(old, new)
    return text.replace('@PORT@', str(c.PORT)).replace('@SEPARATE_TEMP_OUTPUT@', output)


def run_lane(c, helpers, case, lane):
    date = time.strftime('%Y-%m-%d', time.gmtime())  # daemons run with TZ=UTC
    spec = specification(c, case, date)
    output = os.path.join(c.ROOT, lane + '-' + case); os.makedirs(output)
    result = {'case': case, 'lane': lane, 'utc_date': date, 'status': 'failed', 'timing': {}}
    result_path = os.path.join(c.ROOT, 'evidence', lane, 'store-result.json')
    os.makedirs(os.path.dirname(result_path)); c.save_json(result_path, result)
    with helpers.owned_daemon(c, lane, case, config(c, case, output), c.PORT) as session:
        unused, conn, part, directory = session
        result['daemon'] = part; seq = 0
        for step in spec['steps']:
            if step[0] == 'observe':
                result[step[1]] = helpers.wait_output(c, output, spec['phases'][step[1]], step[2])
                result['timing'][step[1]] = time.time(); c.save_json(result_path, result)
                continue
            seq += 1
            if c.call(conn, step[0], seq, step[1], directory, part['records']) != step[2]:
                raise ValueError('%s %d/%s differs' % (case, seq, step[0].decode()))
        if case == 'rotation-time':
            # The first rotation is due no earlier than 1 s after start and the next no earlier
            # than 1 s after the observed one; later checkpoints would race them, so they fail.
            timing = result['timing']
            if timing['first'] - part['started_at'] >= 1 or timing['second'] - timing['rotated'] >= 1:
                raise ValueError('rotation-time missed its 1 s windows: %r' % timing)
        helpers.shutdown(c, session, seq + 1)
    files, links = c.output_snapshot(output); result['final'] = {'files': files, 'symlinks': links}
    if result['final'] != spec['phases']['final']: c.save_json(result_path, result); raise ValueError('final store output differs')
    if time.strftime('%Y-%m-%d', time.gmtime()) != date: raise ValueError('UTC date changed during the case')
    result['status'] = 'passed'; c.save_json(result_path, result)
    return result


def compare_lanes(c, old, new, case):
    checks = {}
    for lane, label in ((old, 'old'), (new, 'modern')):
        if lane.get('case') != case or lane.get('lane') != label or lane.get('status') != 'passed':
            raise ValueError('incomplete store lane')
        spec = specification(c, case, lane.get('utc_date'))
        for phase, wanted in spec['phases'].items():
            if lane.get(phase) != wanted: raise ValueError('missing or wrong store phase ' + phase)
        part = lane.get('daemon') or {}; records = part.get('records', [])
        command = c.TARGETS[label]['command'] + ['-c', os.path.join(c.ROOT, label + '-' + case + '.conf')]
        if part.get('command') != command: raise ValueError('store target identity differs')
        if part.get('status') != 'passed' or part.get('exit') != 0 or part.get('cleanup_exit') != 0 or len(records) != len(spec['requests']):
            raise ValueError('incomplete store daemon')
        for seq, (name, fields, wanted) in enumerate(spec['requests'], 1):
            r = records[seq - 1]; oneway = name == b'shutdown'
            if r['method'] != name.decode() or r['sequence'] != seq or r.get('oneway') != oneway or r['request_hex'] != c.hexbytes(c.framed(name, seq, fields, oneway)):
                raise ValueError('store request differs')
            if oneway:
                if 'reply_hex' in r: raise ValueError('oneway store shutdown has reply')
                continue
            wire = binascii.unhexlify(r['reply_hex'])
            if len(wire) < 4 or not 0 < len(wire) - 4 <= c.MAX_REPLY or struct.unpack('>I', wire[:4])[0] != len(wire) - 4:
                raise ValueError('invalid store reply frame')
            if c.parse_reply(wire[4:], name, seq) != r.get('value') or r.get('value') != wanted:
                raise ValueError('store reply value differs')
    checks['utc-date'] = old['utc_date'] == new['utc_date']
    for a, b in zip(old['daemon']['records'], new['daemon']['records']):
        checks['request-%d' % a['sequence']] = a['request_hex'] == b['request_hex']
        if a['method'] not in ('getVersion', 'shutdown'): checks['reply-%d' % a['sequence']] = a['reply_hex'] == b['reply_hex']
    for phase in specification(c, case, old['utc_date'])['phases']: checks[phase] = old[phase] == new[phase]
    return {'case': case, 'status': 'passed' if all(checks.values()) else 'failed', 'checks': checks,
            'scope': 'single daemon: time rotation, queue-size TRY_LATER or key_hash/key_modulo bucket bytes; '
                     'no durability, rate or production-config claim'}
