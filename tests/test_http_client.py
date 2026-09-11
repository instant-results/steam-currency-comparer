import ssl
import errno
import unittest
import urllib.error
from unittest.mock import patch

from steam_price_polisher.http_client import UrllibJsonHttpClient, HttpClientError
from steam_price_polisher.request_policy import RetryingJsonHttpClient


class HttpClientTests(unittest.TestCase):
    def test_local_socket_denial_is_sanitized_and_not_retried(self):
        windows_error = OSError("private path")
        windows_error.winerror = 10013
        for error in (PermissionError(errno.EACCES, "private path"),
                      OSError(errno.EPERM, "private path"), OSError(10013, "private path"), windows_error):
            for wrapped in (error, urllib.error.URLError(error)):
                with self.subTest(error=wrapped):
                    client = UrllibJsonHttpClient()
                    with patch.object(client._opener, "open", side_effect=wrapped) as request:
                        with self.assertRaises(HttpClientError) as raised:
                            RetryingJsonHttpClient(client).get_json("https://example.test/?key=secret")
                    self.assertTrue(raised.exception.network_access_denied)
                    self.assertFalse(raised.exception.transient)
                    self.assertNotIn("secret", str(raised.exception))
                    self.assertNotIn("private path", str(raised.exception))
                    request.assert_called_once()

    def test_http_403_and_connection_refused_are_not_local_permission_denials(self):
        for error in (urllib.error.HTTPError("https://example.test", 403, "Forbidden", {}, None),
                      urllib.error.URLError(ConnectionRefusedError(errno.ECONNREFUSED, "refused"))):
            client = UrllibJsonHttpClient()
            with patch.object(client._opener, "open", side_effect=error):
                with self.assertRaises(HttpClientError) as raised:
                    client.get_json("https://example.test")
            self.assertFalse(raised.exception.network_access_denied)

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
