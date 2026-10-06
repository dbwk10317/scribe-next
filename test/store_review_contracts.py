"""Actual store/copy/pool regressions; scripted resolver, real loopback sockets."""

from pathlib import Path
import select
import socket
import tempfile

import relay_peer as relay


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
