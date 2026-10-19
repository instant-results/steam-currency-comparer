import unittest

from steam_price_polisher.http_client import HttpClientError
from steam_price_polisher.request_policy import (
    RequestGate,
    RetryPolicy,
    RetryingJsonHttpClient,
)


class SequenceHttpClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    def get_json(self, url, headers=None):
        self.calls += 1
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class MutableClock:
    def __init__(self):
        self.value = 0.0
        self.sleeps = []

    def __call__(self):
        return self.value

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.value += seconds


class RequestPolicyTests(unittest.TestCase):
    def test_retries_transient_failures_with_exponential_backoff(self):
        upstream = SequenceHttpClient(
            [
                HttpClientError("temporary", transient=True),
                HttpClientError("temporary", transient=True),
                {"ok": True},
            ]
        )
        sleeps = []
        client = RetryingJsonHttpClient(
            upstream,
            policy=RetryPolicy(max_attempts=4, base_delay=2, jitter_ratio=0),
            sleep=sleeps.append,
        )

        result = client.get_json("https://example.test")

        self.assertEqual(result, {"ok": True})
        self.assertEqual(sleeps, [2, 4])
        self.assertEqual(upstream.calls, 3)

    def test_does_not_retry_permanent_failures(self):
        upstream = SequenceHttpClient(
            [HttpClientError("not found", status_code=404, transient=False)]
        )
        client = RetryingJsonHttpClient(upstream, sleep=lambda _: None)

        with self.assertRaises(HttpClientError):
            client.get_json("https://example.test")

        self.assertEqual(upstream.calls, 1)

    def test_retry_after_defers_the_shared_gate(self):
        clock = MutableClock()
        gate = RequestGate(1.5, clock=clock, sleep=clock.sleep)
        upstream = SequenceHttpClient(
            [
                HttpClientError(
                    "rate limited",
                    status_code=429,
                    retry_after=10,
                    transient=True,
                ),
                {"ok": True},
            ]
        )
        client = RetryingJsonHttpClient(upstream, gate=gate)

        client.get_json("https://example.test")

        self.assertEqual(clock.sleeps, [10])

    def test_gate_enforces_a_global_minimum_interval(self):
        clock = MutableClock()
        gate = RequestGate(1.5, clock=clock, sleep=clock.sleep)

        gate.wait()
        gate.wait()

        self.assertEqual(clock.sleeps, [1.5])

    def test_terminal_rate_limit_defers_next_request_and_honors_full_retry_after(self):
        clock = MutableClock()
        gate = RequestGate(1.5, clock=clock, sleep=clock.sleep)
        upstream = SequenceHttpClient([HttpClientError('Busy', status_code=429, transient=True, retry_after=90), {'ok': True}])
        client = RetryingJsonHttpClient(upstream, gate=gate, policy=RetryPolicy(max_attempts=1, maximum_delay=15))
        with self.assertRaises(HttpClientError): client.get_json('https://example.test')
        client.get_json('https://example.test')
        self.assertEqual(clock.sleeps, [90])

    def test_gate_wait_uses_cancellable_sleep_without_changing_shared_schedule(self):
        clock = MutableClock()
        gate = RequestGate(1.5, clock=clock, sleep=clock.sleep)
        gate.wait()
        def cancelled(seconds): raise RuntimeError('cancelled')
        with self.assertRaisesRegex(RuntimeError, 'cancelled'): gate.wait(sleep=cancelled)
        gate.wait()
        self.assertEqual(clock.sleeps, [1.5])


if __name__ == "__main__":
    unittest.main()
