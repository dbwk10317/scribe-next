"""Actual store/copy/pool regressions; scripted resolver, real loopback sockets."""

from pathlib import Path
import select
import socket
import struct
import tempfile

import relay_peer as relay
import loopback_rpc as tcp


class UpdaterReviewPeer(relay.RelayPeer):
    mode = "review-updater-driver"

    def configuration(self):
        return (super().configuration() + "port=1463\n"
                "<store>\ncategory=accepted\ntype=null\n</store>\n")

    def mapping(self, response):
        connection = self.accept()
        expected = tcp.message(b"getMapping", 0, tcp.string_argument(b"reviewmapping"))
        if relay.receive_request(connection, self.deadline) != expected:
            raise AssertionError("updater request differs from original IDL bytes")
        connection.sendall(struct.pack(">I", len(response)) + response)
        self.eof(connection)

    def success(self):
        fields = (b"\x0d\x00\x00\x08\x0c" + struct.pack(">ii", 1, 42)
                  + b"\x0b\x00\x02" + tcp.binary_string(b"resolved")
                  + b"\x08\x00\x03" + struct.pack(">i", 1234) + b"\0\0")
        self.mapping(tcp.reply(b"getMapping", 0, fields))


class StoreReviewPeer(relay.RelayPeer):
    mode = "review-store-driver"

    def __init__(self, executable, environment, directory, kind, pooled=True):
        super().__init__(executable, environment, directory, pooled)
        self.kind = kind

    def start(self):
        self.other = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sockets.append(self.other)
        try:
            self.other.bind(("127.0.0.1", 0))
            if self.kind != "copy-error":
                self.other.listen(4)
            return super().start()
        except BaseException:
            self.cleanup()
            raise

    def configuration(self):
        text = super().configuration()
        if self.kind == "copy-error":
            text = text.replace(f"remote_port={self.bound_address[1]}",
                                f"remote_port={self.other.getsockname()[1]}")
        return (text + f"test_kind={self.kind}\n"
                f"test_other_port={self.other.getsockname()[1]}\n"
                f"test_next_port={self.other.getsockname()[1]}\n"
                f"test_copy_port={self.bound_address[1]}\n"
                "ignore_network_error=yes\n")


class StoreReviewContracts:
    def test_review_nested_configuration_inherits_and_releases_with_store_owner(self):
        self.run_fixture("review-conf-parent", "port=1463\n<store>\ntype=multi\n"
                         "null::local=parent\nnull::nearest=parent\nnull::outer=parent\n"
                         "category=parent-category\ncategories=parent-categories\n"
                         "<store0>\ntype=multi\nnull::nearest=middle\n"
                         "<store0>\ntype=null\nlocal=leaf\nnull::qualified=leaf-qualified\n"
                         "</store0>\n</store0>\n</store>\n")

    def updater_review_peer(self):
        directory = Path(tempfile.mkdtemp(prefix="updater-review-", dir=self.temporary))
        return UpdaterReviewPeer(self.fixture, self.env, directory)

    def test_review_updater_exception_unwinding_releases_lock(self):
        with self.updater_review_peer() as peer:
            peer.command("GET")
            peer.success()
            self.assertEqual(peer.read_line(), "MAPPING 1 resolved 1234")
            peer.command("FAIL")
            self.assertEqual(peer.read_line(), "ALLOCATION FAILED")
            peer.command("GET")
            self.assertEqual(peer.read_line(), "MAPPING 1 resolved 1234")
            peer.no_pending_connections()

    def test_review_updater_concurrent_first_lookup_shares_one_cached_mapping(self):
        peer = self.updater_review_peer()
        peer.mode = "review-updater-concurrent"
        with peer:
            peer.success()
            self.assertEqual(peer.read_line(), "CONCURRENT 16 resolved 1234")
            peer.no_pending_connections()

    def test_review_updater_protocol_and_application_errors_recover(self):
        # Independent framed-binary responses from the owned loopback fixture.
        protocol_error = struct.pack(">i", -1)
        application_error = (tcp.binary_string(b"getMapping") + b"\x03" + struct.pack(">i", 0)
                             + b"\x0b\x00\x01" + tcp.binary_string(b"local fixture error")
                             + b"\x08\x00\x02" + struct.pack(">i", 6) + b"\0")
        for response in (protocol_error, application_error):
            with self.subTest(response=response), self.updater_review_peer() as peer:
                peer.command("GET")
                peer.mapping(response)
                self.assertEqual(peer.read_line(), "MAPPING 0 keep 19")
                peer.command("GET")
                peer.success()
                self.assertEqual(peer.read_line(), "MAPPING 1 resolved 1234")

    def store_review_peer(self, kind, pooled=True):
        directory = Path(tempfile.mkdtemp(prefix="store-review-", dir=self.temporary))
        return StoreReviewPeer(self.fixture, self.env, directory, kind, pooled)

    @staticmethod
    def bucket_review_config(count, extra="", **values):
        text = f"num_buckets={count}\nbucket_type=key_modulo\n"
        text += "".join(f"{key}={value}\n" for key, value in values.items())
        text += "".join(f"<bucket{i}>\ntype=null\n</bucket{i}>\n" for i in range(count + 1))
        return text + extra

    def test_review_store_list_default_port_is_initialized(self):
        self.run_fixture("review-store-defaults")

    def test_review_store_invalid_children_do_not_dereference_null(self):
        cases = {
            "buffer-primary": "<primary>\ntype=not-a-store\n</primary>\n<secondary>\ntype=null\n</secondary>\nreplay_buffer=no\n",
            "buffer-secondary": "<primary>\ntype=null\n</primary>\n<secondary>\ntype=not-a-store\n</secondary>\n",
            "multi": "<store0>\ntype=not-a-store\n</store0>\n",
            "category": "<model>\ntype=not-a-store\n</model>\n",
            "category-missing": "",
        }
        for kind, children in cases.items():
            with self.subTest(kind=kind):
                self.run_fixture("review-store-invalid-child", "test_kind=" + kind + "\n" + children)

    def test_review_store_bucket_preserves_small_count_legacy_suffix_rejection(self):
        for count in (1, 2, 3, 4):
            name = "bucket"[count + 1:]
            with self.subTest(count=count, name=name):
                self.run_fixture("review-store-bucket", self.bucket_review_config(
                    count, f"<{name}>\ntype=null\n</{name}>\n",
                    test_error="bucket store has too many buckets defined"))

    def test_review_store_bucket_accepts_ordinary_excess_names_and_safe_large_counts(self):
        for count in (1, 5, 6, 40):
            with self.subTest(count=count):
                self.run_fixture("review-store-bucket", self.bucket_review_config(
                    count, f"<bucket{count + 1}>\ntype=null\n</bucket{count + 1}>\n"))
        for count in (6, 40):
            with self.subTest(count=count, child="cket"):
                self.run_fixture("review-store-bucket", self.bucket_review_config(
                    count, "<cket>\ntype=null\n</cket>\n"))

    def test_review_store_bucket_unknown_child_type_fails_without_dereference(self):
        config = self.bucket_review_config(1).replace("type=null", "type=not-a-store", 1)
        self.run_fixture("review-store-bucket", config + "test_error=can't create store of type: not-a-store\n")

    def test_review_store_bucket_copy_uses_legacy_zero_range_and_retains_key_bytes(self):
        for remove in ("yes", "no"):
            with self.subTest(remove=remove):
                config = ("num_buckets=2\nbucket_type=key_range\nbucket_range=20\n"
                          f"delimiter=124\nremove_key={remove}\nbucket_subdir=b\n"
                          "<bucket>\ntype=file\nfile_path=@DIRECTORY@/data\n"
                          "base_filename=model\nrotate_period=never\nadd_newlines=0\n"
                          "create_symlink=no\nmax_size=0\n</bucket>\n")
                directory = self.run_fixture("review-store-bucket", config)
                self.assertEqual((directory / "data/b000/copied/copied_00000").read_bytes(),
                                 b"15|A\0B\n\xffno-key")
                self.assertEqual((directory / "data/b002/copied/copied_00000").read_bytes(), b"")
                self.assertEqual((directory / "data/b001/copied/copied_00000").read_bytes(), b"")

    def test_review_store_distinct_service_lists_share_legacy_empty_pool_key(self):
        for kind in ("list", "default-list"):
            with self.subTest(kind=kind), self.store_review_peer(kind) as peer:
                peer.command("OPEN 0")
                first = peer.accept()
                peer.state("OPEN", 0, result=True, opened=(True, False), sent=0)
                peer.command("OPEN 1")
                peer.state("OPEN", 1, result=True, opened=(True, True), sent=0)
                peer.no_pending_connections()
                self.assertFalse(select.select([peer.other], [], [], 0)[0],
                                 "legacy empty pool key unexpectedly connected to other list")
                for index, connection in enumerate((first, first)):
                    self.relay_request(peer, "binary", connection, index=index)
                    peer.response(connection)
                    peer.state("SEND", index, result=True, opened=(True, True), sent=3 * (index + 1), size=3)
                peer.command("CLOSE 0")
                peer.state("CLOSE", 0, result=True, opened=(False, True), sent=6)
                self.relay_request(peer, "abc", first, index=1)
                peer.response(first)
                peer.state("SEND", 1, result=True, opened=(False, True), sent=9, size=3)
                peer.command("CLOSE 1")
                peer.state("CLOSE", 1, result=True, opened=(False, False), sent=9)
                peer.eof(first)

    def test_review_store_same_service_list_shares_and_reopen_accumulates_servers(self):
        with self.store_review_peer("same-list") as peer:
            peer.command("OPEN 0")
            connection = peer.accept()
            peer.state("OPEN", 0, result=True, opened=(True, False), sent=0)
            peer.command("OPEN 1")
            peer.state("OPEN", 1, result=True, opened=(True, True), sent=0)
            peer.no_pending_connections()
            peer.command("CLOSE 0")
            peer.state("CLOSE", 0, result=True, opened=(False, True), sent=0)
            self.relay_request(peer, "abc", connection, index=1)
            peer.response(connection)
            peer.state("SEND", 1, result=True, opened=(False, True), sent=3, size=3)
            peer.command("CLOSE 1")
            peer.state("CLOSE", 1, result=True, opened=(False, False), sent=3)
            peer.eof(connection)
            for unused in range(2):
                peer.command("OPEN 0")
                reopened = peer.accept()
                peer.state("OPEN", 0, result=True, opened=(True, False), sent=3)
                peer.command("CLOSE 0")
                peer.state("CLOSE", 0, result=True, opened=(False, False), sent=3)
                peer.eof(reopened)

    def test_review_store_network_copy_omits_list_and_default_port(self):
        for pooled in (False, True):
            with self.subTest(pooled=pooled), self.store_review_peer("default-list", pooled) as peer:
                peer.command("OPEN 0")
                connection = peer.accept()
                peer.state("OPEN", 0, result=True, opened=(True, False), sent=0)
                peer.command("COPY 1")
                peer.state("COPY", 1, result=True, opened=(True, False), sent=0)
                peer.command("SEND 1 binary")
                if pooled:
                    peer.request(connection, "binary")
                    peer.response(connection)
                    peer.state("SEND", 1, result=True, opened=(True, True), sent=3, size=3)
                else:
                    peer.state("SEND", 1, result=False, opened=(True, False), sent=0, size=3)

    def test_review_store_network_copy_restores_default_error_reporting(self):
        for pooled in (False, True):
            with self.subTest(pooled=pooled), self.store_review_peer("copy-error", pooled) as peer:
                peer.command("COPY 1")
                peer.state("COPY", 1, result=True, opened=(False, False), sent=0)
                for index in (0, 1):
                    peer.command(f"OPEN {index}")
                    peer.state("OPEN", index, result=False, opened=(False, False), sent=0)

    def test_review_store_dynamic_update_to_absent_key_retains_previous_pool_reference(self):
        with self.store_review_peer("dynamic") as peer:
            peer.command("OPEN 0")
            first = peer.accept()
            peer.state("OPEN", 0, result=True, opened=(True, False), sent=0)
            peer.command("OPEN 1")
            peer.state("OPEN", 1, result=True, opened=(True, True), sent=0)
            peer.command("CHECK 0")
            peer.state("CHECK", 0, result=True, opened=(False, True), sent=0)
            self.relay_request(peer, "binary", first, index=1)
            peer.response(first)
            peer.state("SEND", 1, result=True, opened=(False, True), sent=3, size=3)
            peer.command("SEND 0 abc")
            second = peer.accept(peer.other)
            peer.request(second, "abc")
            peer.response(second)
            peer.state("SEND", 0, result=True, opened=(True, True), sent=6, size=3)
            peer.command("CLOSE 1")
            peer.state("CLOSE", 1, result=True, opened=(True, False), sent=6)
            peer.command("CLOSE 0")
            peer.state("CLOSE", 0, result=True, opened=(False, False), sent=6)
            peer.eof(second)

    def test_review_store_dynamic_copy_inherits_resolved_endpoint_without_refresh(self):
        for pooled in (False, True):
            with self.subTest(pooled=pooled), self.store_review_peer("dynamic", pooled) as peer:
                peer.command("CHECK 0")
                peer.state("CHECK", 0, result=True, opened=(False, False), sent=0)
                peer.command("COPY 1")
                peer.state("COPY", 1, result=True, opened=(False, False), sent=0)
                peer.command("SEND 1 binary")
                connection = peer.accept(peer.other)
                peer.request(connection, "binary")
                peer.response(connection)
                peer.state("SEND", 1, result=True, opened=(False, True), sent=3, size=3)
                peer.command("CHECK 1")
                peer.state("CHECK", 1, result=True, opened=(False, True), sent=3)
                self.relay_request(peer, "abc", connection, index=1)
                peer.response(connection)
                peer.state("SEND", 1, result=True, opened=(False, True), sent=6, size=3)

    def test_review_store_dynamic_update_closes_destination_owner_then_same_peer_reconnects(self):
        with self.store_review_peer("dynamic-owned") as peer:
            peer.command("OPEN 0")
            first = peer.accept()
            peer.state("OPEN", 0, result=True, opened=(True, False), sent=0)
            peer.command("OPEN 1")
            second = peer.accept(peer.other)
            peer.state("OPEN", 1, result=True, opened=(True, True), sent=0)
            peer.command("CHECK 0")
            peer.state("CHECK", 0, result=True, opened=(False, True), sent=0)
            peer.eof(second)
            # The other owner still believes it is open. Its first send finds
            # the erased pool key and fails without transmitting a frame.
            peer.command("SEND 1 abc")
            peer.state("SEND", 1, result=False, opened=(False, False), sent=0, size=3)
            peer.no_pending_connections()
            self.assertFalse(select.select([peer.other], [], [], 0)[0],
                             "missing pool key unexpectedly connected before retry")
            peer.command("SEND 1 abc")
            reconnected = peer.accept(peer.other)
            peer.request(reconnected, "abc")
            peer.response(reconnected)
            peer.state("SEND", 1, result=True, opened=(False, True), sent=3, size=3)
            self.relay_request(peer, "binary", reconnected, index=0)
            peer.response(reconnected)
            peer.state("SEND", 0, result=True, opened=(True, True), sent=6, size=3)
            peer.command("CLOSE 0")
            peer.state("CLOSE", 0, result=True, opened=(False, True), sent=6)
            self.relay_request(peer, "binary", reconnected, index=1)
            peer.response(reconnected)
            peer.state("SEND", 1, result=True, opened=(False, True), sent=9, size=3)
            peer.command("CLOSE 1")
            peer.state("CLOSE", 1, result=True, opened=(False, False), sent=9)
            peer.eof(reconnected)

    def test_review_store_failed_dynamic_refresh_and_copy_retain_live_endpoint(self):
        for pooled in (False, True):
            with self.subTest(pooled=pooled), self.store_review_peer("dynamic", pooled) as peer:
                peer.command("CHECK 0")
                peer.state("CHECK", 0, result=True, opened=(False, False), sent=0)
                peer.command("SEND 0 binary")
                live = peer.accept(peer.other)
                peer.request(live, "binary")
                peer.response(live)
                peer.state("SEND", 0, result=True, opened=(True, False), sent=3, size=3)
                peer.command("FAILRESOLVE 0")
                peer.state("FAILRESOLVE", 0, result=True, opened=(True, False), sent=3)
                peer.command("CHECK 0")
                peer.state("CHECK", 0, result=True, opened=(True, False), sent=3)
                self.relay_request(peer, "abc", live)
                peer.response(live)
                peer.state("SEND", 0, result=True, opened=(True, False), sent=6, size=3)
                peer.command("COPY 1")
                peer.state("COPY", 1, result=True, opened=(True, False), sent=6)
                peer.command("SEND 1 binary")
                copied = live if pooled else peer.accept(peer.other)
                peer.request(copied, "binary")
                peer.response(copied)
                peer.state("SEND", 1, result=True, opened=(True, True), sent=9, size=3)
