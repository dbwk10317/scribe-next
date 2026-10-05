"""Actual store/copy/pool regressions; scripted resolver, real loopback sockets."""

from pathlib import Path
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
                f"test_copy_port={self.other.getsockname()[1]}\n"
                "ignore_network_error=yes\n")


class StoreReviewContracts:
    def test_review_dynamic_copy_resolves_once_before_open_and_retains_periodic_refresh(self):
        self.run_fixture("review-dynamic-copy-initial-resolution")

    def test_review_dynamic_category_copy_does_not_hold_handler_lock_during_resolution(self):
        text = ("port=1463\nnew_thread_per_category=yes\n"
                "<store>\ncategory=accepted\ntype=null\n</store>\n"
                "<store>\ncategory=default\ntype=bucket\nnum_buckets=3\n"
                "bucket_type=key_modulo\nmust_succeed=no\n")
        for index in range(4):
            text += (f"<bucket{index}>\ntype=network\n"
                     "remote_host=127.0.0.1\nremote_port=0\n"
                     "dynamic_config_type=thrift_bucket\n"
                     f"</bucket{index}>\n")
        self.run_fixture("review-dynamic-copy-locking", text + "</store>\n")

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

    def test_review_store_bucket_detects_extra_named_bucket_at_any_count(self):
        for count in (1, 6, 40):
            with self.subTest(count=count):
                self.run_fixture("review-store-bucket", self.bucket_review_config(
                    count, f"<bucket{count + 1}>\ntype=null\n</bucket{count + 1}>\n",
                    test_error="bucket store has too many buckets defined"))

    def test_review_store_bucket_ignores_unrelated_child_and_opens_valid_counts(self):
        for count in (1, 6, 40):
            with self.subTest(count=count):
                self.run_fixture("review-store-bucket", self.bucket_review_config(
                    count, "<cket>\ntype=null\n</cket>\n"))

    def test_review_store_bucket_unknown_child_type_fails_without_dereference(self):
        config = self.bucket_review_config(1).replace("type=null", "type=not-a-store", 1)
        self.run_fixture("review-store-bucket", config + "test_error=can't create store of type: not-a-store\n")

    def test_review_store_bucket_copy_preserves_range_and_removed_key_bytes(self):
        for remove in ("yes", "no"):
            with self.subTest(remove=remove):
                config = ("num_buckets=2\nbucket_type=key_range\nbucket_range=20\n"
                          f"delimiter=124\nremove_key={remove}\nbucket_subdir=b\n"
                          "<bucket>\ntype=file\nfile_path=@DIRECTORY@/data\n"
                          "base_filename=model\nrotate_period=never\nadd_newlines=0\n"
                          "create_symlink=no\nmax_size=0\n</bucket>\n")
                directory = self.run_fixture("review-store-bucket", config)
                self.assertEqual((directory / "data/b000/copied/copied_00000").read_bytes(), b"no-key")
                expected = b"A\0B\n\xff" if remove == "yes" else b"15|A\0B\n\xff"
                self.assertEqual((directory / "data/b002/copied/copied_00000").read_bytes(), expected)
                self.assertEqual((directory / "data/b001/copied/copied_00000").read_bytes(), b"")

    def test_review_store_distinct_service_lists_never_share_destination(self):
        for kind in ("list", "default-list"):
            with self.subTest(kind=kind), self.store_review_peer(kind) as peer:
                peer.command("OPEN 0")
                first = peer.accept()
                peer.state("OPEN", 0, result=True, opened=(True, False), sent=0)
                peer.command("OPEN 1")
                second = peer.accept(peer.other)
                peer.state("OPEN", 1, result=True, opened=(True, True), sent=0)
                for index, connection in enumerate((first, second)):
                    self.relay_request(peer, "binary", connection, index=index)
                    peer.response(connection)
                    peer.state("SEND", index, result=True, opened=(True, True), sent=3 * (index + 1), size=3)
                peer.command("CLOSE 0")
                peer.state("CLOSE", 0, result=True, opened=(False, True), sent=6)
                peer.eof(first)
                self.relay_request(peer, "abc", second, index=1)
                peer.response(second)
                peer.state("SEND", 1, result=True, opened=(False, True), sent=9, size=3)
                peer.command("CLOSE 1")
                peer.state("CLOSE", 1, result=True, opened=(False, False), sent=9)
                peer.eof(second)

    def test_review_store_same_service_list_shares_and_reopen_replaces_server_list(self):
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

    def test_review_store_network_copy_retains_list_and_default_port(self):
        for pooled in (False, True):
            with self.subTest(pooled=pooled), self.store_review_peer("default-list", pooled) as peer:
                peer.command("OPEN 0")
                connection = peer.accept()
                peer.state("OPEN", 0, result=True, opened=(True, False), sent=0)
                peer.command("COPY 1")
                peer.state("COPY", 1, result=True, opened=(True, False), sent=0)
                peer.command("SEND 1 binary")
                if not pooled:
                    connection = peer.accept()
                peer.request(connection, "binary")
                peer.response(connection)
                peer.state("SEND", 1, result=True, opened=(True, True), sent=3, size=3)

    def test_review_store_network_copy_retains_error_suppression(self):
        for pooled in (False, True):
            with self.subTest(pooled=pooled), self.store_review_peer("copy-error", pooled) as peer:
                peer.command("COPY 1")
                peer.state("COPY", 1, result=True, opened=(False, False), sent=0)
                for index in (0, 1):
                    peer.command(f"OPEN {index}")
                    peer.state("OPEN", index, result=False, opened=(False, False), sent=0)

    def test_review_store_dynamic_update_closes_previous_pool_owner_only(self):
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
            peer.eof(first)
            peer.command("CLOSE 0")
            peer.state("CLOSE", 0, result=True, opened=(False, False), sent=6)
            peer.eof(second)

    def test_review_store_dynamic_copy_resolves_new_category_before_send(self):
        for pooled in (False, True):
            with self.subTest(pooled=pooled), self.store_review_peer("dynamic", pooled) as peer:
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

    def test_review_store_dynamic_update_keeps_owner_already_at_new_destination(self):
        with self.store_review_peer("dynamic-owned") as peer:
            peer.command("OPEN 0")
            first = peer.accept()
            peer.state("OPEN", 0, result=True, opened=(True, False), sent=0)
            peer.command("OPEN 1")
            second = peer.accept(peer.other)
            peer.state("OPEN", 1, result=True, opened=(True, True), sent=0)
            peer.command("CHECK 0")
            peer.state("CHECK", 0, result=True, opened=(False, True), sent=0)
            peer.eof(first)
            for index in (1, 0):
                self.relay_request(peer, "abc", second, index=index)
                peer.response(second)
                peer.state("SEND", index, result=True, opened=(bool(index == 0), True),
                           sent=3 if index == 1 else 6, size=3)
            peer.command("CLOSE 0")
            peer.state("CLOSE", 0, result=True, opened=(False, True), sent=6)
            self.relay_request(peer, "binary", second, index=1)
            peer.response(second)
            peer.state("SEND", 1, result=True, opened=(False, True), sent=9, size=3)
            peer.command("CLOSE 1")
            peer.state("CLOSE", 1, result=True, opened=(False, False), sent=9)
            peer.eof(second)

    def test_review_store_failed_dynamic_refresh_retains_live_endpoint_and_copy_fallback(self):
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
                fallback = peer.accept()
                peer.request(fallback, "binary")
                peer.response(fallback)
                peer.state("SEND", 1, result=True, opened=(True, True), sent=9, size=3)
