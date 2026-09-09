import ssl
import unittest
import urllib.error
from unittest.mock import patch

from steam_price_polisher.http_client import UrllibJsonHttpClient, HttpClientError
from steam_price_polisher.request_policy import RetryingJsonHttpClient


class HttpClientTests(unittest.TestCase):
    def test_certificate_failure_is_non_retryable_and_sanitized(self):
        client = UrllibJsonHttpClient()
        error = urllib.error.URLError(ssl.SSLCertVerificationError(1, "private certificate details"))
        with patch.object(client._opener, "open", side_effect=error) as request:
            with self.assertRaises(HttpClientError) as raised:
                RetryingJsonHttpClient(client).get_json("https://example.test/?key=secret")
        self.assertTrue(raised.exception.tls_error)
        self.assertFalse(raised.exception.transient)
        self.assertNotIn("secret", str(raised.exception))
        self.assertNotIn("private certificate", str(raised.exception))
        request.assert_called_once()

    def test_native_context_keeps_certificate_and_hostname_checks(self):
        client = UrllibJsonHttpClient()
        handler = next(handler for handler in client._opener.handlers if hasattr(handler, "_context"))
        self.assertEqual(handler._context.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(handler._context.check_hostname)
