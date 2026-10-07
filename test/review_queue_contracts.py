"""Mixin for the existing real API fixture; no duplicate test discovery/build."""


class ReviewQueueContracts:
    def test_review_buffer_unconfigured_status_and_complete_status_priority(self):
        self.run_fixture("review-buffer-status")

    def test_review_concurrent_throttle_preserves_quota_and_legacy_exemptions(self):
        for limit in (100, 0):
            with self.subTest(limit=limit):
                self.run_fixture("review-throttle-concurrent", "port=1463\n"
                                 f"max_msg_per_second={limit}\n"
                                 "<store>\ncategory=accepted\ntype=null\n</store>\n")

    @staticmethod
    def review_queue_config(newlines=1, category=False, interval=3600):
        return (
            "port=1463\nmax_queue_size=0\n<store>\ncategory=accepted\ntype=file\n"
            "file_path=@DIRECTORY@/data\nbase_filename=fixture\nrotate_period=never\n"
            "create_symlink=no\nfs_type=std\nmax_size=0\nmax_write_size=7\n"
            f"target_write_size=16384\nmax_write_interval={interval}\n"
            f"add_newlines={newlines}\nwrite_category={'yes' if category else 'no'}\n"
            "</store>\n"
        )

    def check_review_queue_counters(self, directory, received=3):
        self.assertEqual((directory / "states.txt").read_text(),
                         f"ack=0\nreceived={received}\nlost=0\nrequeue=0\nbytes-lost=0\n")

    def test_review_queue_shutdown_accepts_empty_payloads_without_delivery_or_loss_count(self):
        for newlines, category in ((1, False), (0, True), (1, True)):
            with self.subTest(newlines=newlines, category=category):
                directory = self.run_fixture("review-queue-stop", self.review_queue_config(
                    newlines=newlines, category=category))
                self.check_review_queue_counters(directory)
                self.assertEqual((directory / "data/fixture_00000").read_bytes(), b"")

    def test_review_queue_periodic_flush_leaves_empty_payloads_undelivered(self):
        directory = self.run_fixture("review-queue-periodic", self.review_queue_config(interval=1))
        self.check_review_queue_counters(directory)
        self.assertEqual((directory / "before-stop.bin").read_bytes(), b"")
        self.assertEqual((directory / "data/fixture_00000").read_bytes(), b"")

    def test_review_queue_mixed_payload_bytes_and_newline_options(self):
        for newlines in (0, 1):
            for category in (False, True):
                with self.subTest(newlines=newlines, category=category):
                    directory = self.run_fixture("review-queue-mixed", self.review_queue_config(
                        newlines=newlines, category=category))
                    self.check_review_queue_counters(directory)
                    self.assertEqual((directory / "data/fixture_00000").read_bytes(), b"".join(
                        (b"accepted\n" if category else b"") + payload +
                        (b"\n" if newlines else b"") for payload in (b"", b"A\x00B\n\xff", b"ends\n")))

    def test_review_queue_empty_batch_has_no_output(self):
        directory = self.run_fixture("review-queue-empty-batch", self.review_queue_config())
        self.check_review_queue_counters(directory, received=0)
        self.assertEqual((directory / "data/fixture_00000").read_bytes(), b"")
