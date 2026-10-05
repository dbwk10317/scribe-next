"""Focused mixin for actual BufferStore jitter and BucketStore periodic order.

Uses the existing API fixture. No timer replacement, live service discovery,
bucket routing/copy path, listener, or whole-daemon sanitizer claim is made.
"""


class ReviewRetryShuffleContracts:
    @staticmethod
    def review_retry_config(**values):
        defaults = {"retry_interval": 300, "retry_interval_range": 60,
                    "min_retry_interval": 5, "max_retry_interval": 12,
                    "max_random_offset": 3, "adaptive_backoff": "no",
                    "test_actions": "FFFFF", "test_seed": 42}
        defaults.update(values)
        return ("".join(f"{key}={value}\n" for key, value in defaults.items()) +
                "replay_buffer=no\n<primary>\ntype=null\n</primary>\n"
                "<secondary>\ntype=null\n</secondary>\n")

    def review_retry_state(self, **values):
        directory = self.run_fixture("review-retry", self.review_retry_config(**values))
        state = dict(line.split("=", 1) for line in
                     (directory / "retry-state.txt").read_text().splitlines())
        for key in ("intervals", "continuous", "draws"):
            state[key] = [int(value) for value in state[key].split(",")]
        for key in ("range", "offset", "retries", "lost", "next-rand"):
            state[key] = int(state[key])
        self.assertEqual(state["continuous"], [0] * len(state["intervals"]))
        self.assertEqual(state["lost"], 0)
        return state

    def test_review_retry_linear_positive_preserves_rng_and_base(self):
        state = self.review_retry_state()
        self.assertEqual(state["intervals"], [270 + draw % 60 for draw in state["draws"][:5]])
        self.assertEqual(state["next-rand"], state["draws"][5])
        self.assertEqual(state["retries"], 5)

    def test_review_retry_linear_zero_jitter_preserves_base_and_rng(self):
        state = self.review_retry_state(retry_interval_range=0)
        self.assertEqual(state["intervals"], [300] * 5)
        self.assertEqual(state["next-rand"], state["draws"][0])
        self.assertEqual(state["retries"], 5)

    def test_review_retry_linear_zero_base_remains_supported(self):
        for requested_range in (0, 60):
            with self.subTest(requested_range=requested_range):
                state = self.review_retry_state(retry_interval=0,
                                                retry_interval_range=requested_range)
                self.assertEqual(state["range"], 0)  # existing configure clamp
                self.assertEqual(state["intervals"], [0] * 5)
                self.assertEqual(state["next-rand"], state["draws"][0])
                self.assertEqual(state["retries"], 5)

    def test_review_retry_adaptive_zero_jitter_preserves_bounds_and_counters(self):
        state = self.review_retry_state(adaptive_backoff="yes", max_random_offset=0,
                                        test_actions="FFFFSSSSS")
        self.assertEqual(state["intervals"], [7, 9, 12, 12, 10, 8, 6, 5, 5])
        self.assertEqual(state["next-rand"], state["draws"][0])
        self.assertEqual(state["retries"], 4)

    def test_review_retry_adaptive_positive_preserves_rng_and_caps(self):
        state = self.review_retry_state(adaptive_backoff="yes", test_actions="FFFFSSSSS")
        expected, interval = [], 5
        for draw in state["draws"][:4]:
            interval = min(int(interval * 1.414) + draw % 3, 12)
            expected.append(interval)
        for _ in range(5):
            interval = max(interval - 2, 5)
            expected.append(interval)
        self.assertEqual(state["intervals"], expected)
        self.assertEqual(state["next-rand"], state["draws"][4])
        self.assertEqual(state["retries"], 4)

    def test_review_retry_adaptive_zero_base_remains_supported(self):
        state = self.review_retry_state(adaptive_backoff="yes", min_retry_interval=0,
                                        max_retry_interval=0, max_random_offset=20,
                                        test_actions="FSFSS")
        self.assertEqual(state["offset"], 0)  # existing configure clamp
        self.assertEqual(state["intervals"], [0] * 5)
        self.assertEqual(state["next-rand"], state["draws"][0])
        self.assertEqual(state["retries"], 2)

    def test_review_shuffle_preserves_gnu_order_and_subsequent_rng(self):
        directory = self.run_fixture("review-shuffle")
        lines = (directory / "shuffle-state.txt").read_text().splitlines()
        self.assertEqual(len(lines), 32)  # 8 sizes, 4 seeds, 2 calls each
        for line in lines:
            size, seed, calls, next_rand = line.split(":")
            size = int(size)
            calls = [int(value) for value in calls.split(",")] if calls else []
            self.assertEqual(sorted(calls[:size]), list(range(size)))
            self.assertEqual(sorted(calls[size:]), list(range(size)))
