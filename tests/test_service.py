import importlib.util
import json
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "service", ROOT / "product_si5_gtin/service.py"
)
s = importlib.util.module_from_spec(spec)
spec.loader.exec_module(s)


class ClientTests(unittest.TestCase):
    def fake(self, path, token=None, limit=None):
        self.assertEqual(path, "/api/produtos/7891000325858")
        self.assertEqual(token, "FAKE_NOT_A_CREDENTIAL")
        return (
            200,
            {"content-type": "application/json"},
            (ROOT / "tests/fixtures/product.json").read_bytes(),
        )

    def test_fixture(self):
        self.assertEqual(
            s.lookup("7891000325858", "FAKE_NOT_A_CREDENTIAL", self.fake)["marca"],
            "Fixture",
        )

    def test_gtin(self):
        for value in (
            "0000000104500",
            "7891000325858",
            "036000291452",
            "96385074",
            "10012345000017",
        ):
            self.assertEqual(s.gtin(value), value)
        for value in (
            123,
            None,
            "",
            "7891000325859",
            "2" * 13,
            "１２３４５６７８",
            "123456789",
            "../file",
        ):
            with self.subTest(value=value), self.assertRaises(s.LookupError):
                s.gtin(value)

    def test_errors_are_sanitized(self):
        for status in (401, 403, 404, 429, 500, 502, 503, 302):
            with self.subTest(status=status), self.assertRaises(s.LookupError) as error:
                s.lookup(
                    "7891000325858",
                    "FAKE_SECRET",
                    lambda *a, status=status, **k: (status, {}, b"FAKE_SECRET"),
                )
            self.assertNotIn("FAKE_SECRET", str(error.exception))

    def test_cloudflare(self):
        with self.assertRaisesRegex(s.LookupError, "challenge"):
            s.check_status(403, {"cf-mitigated": "challenge"})
        with self.assertRaisesRegex(s.LookupError, "forbidden"):
            s.check_status(403, {"content-type": "application/json"})

    def test_bad_contract(self):
        for body in (
            b"{}",
            b"[]",
            b"not json",
            json.dumps({"codbar": 7891000325858}).encode(),
        ):
            with self.assertRaises(s.LookupError):
                s.lookup(
                    "7891000325858",
                    "FAKE",
                    lambda *a, body=body, **k: (
                        200,
                        {"content-type": "application/json"},
                        body,
                    ),
                )

    def test_image_urls(self):
        for url in (
            "http://global.si5.com.br/img/1.jpg",
            "https://127.0.0.1/img/1.jpg",
            "https://global.si5.com.br@localhost/img/1.jpg",
            "https://global.si5.com.br/img/../1.jpg",
            "https://global.si5.com.br/img/1.jpg?x=1",
            "https://other.example/img/1.jpg",
        ):
            with self.assertRaises(s.LookupError):
                s.image(url, lambda *a, **k: self.fail("Transport must not be called"))

    def test_image_mime_and_redirect(self):
        url = "https://global.si5.com.br/img/78/91/7891000325858.webp"
        for response in (
            (302, {}, b""),
            (200, {"content-type": "image/svg+xml"}, b"<svg/>"),
            (200, {"content-type": "image/png"}, b"html"),
        ):
            with self.assertRaises(s.LookupError):
                s.image(url, lambda *a, response=response, **k: response)
        raw = b"RIFF0000WEBPfixture"

        def fake(path, **kwargs):
            self.assertNotIn("token", kwargs)
            return 200, {"content-type": "image/webp"}, raw

        self.assertEqual(s.image(url, fake), raw)

    def test_private_dns(self):
        with patch.object(
            s.socket, "getaddrinfo", return_value=[(2, 1, 6, "", ("127.0.0.1", 443))]
        ):
            with self.assertRaises(s.LookupError):
                s.PinnedHTTPS(s.HOST).connect()

    def test_body_limit(self):
        from unittest.mock import MagicMock

        conn = MagicMock()
        conn.getresponse.return_value.read.return_value = b"x" * 33
        with patch.object(s, "PinnedHTTPS", return_value=conn):
            with self.assertRaisesRegex(s.LookupError, "response_size"):
                s.transport("/api/produtos/7891000325858", "FAKE", limit=32)
        conn.close.assert_called_once()

    def test_timeout_sanitized(self):
        with patch.object(
            s.PinnedHTTPS, "request", side_effect=TimeoutError("FAKE_SECRET")
        ):
            with self.assertRaisesRegex(s.LookupError, "network") as error:
                s.transport("/api/produtos/7891000325858", "FAKE_SECRET")
            self.assertNotIn("FAKE_SECRET", str(error.exception))

    def test_gtin14_indicator_is_not_local_prefix(self):
        self.assertEqual(s.gtin("20012345000014"), "20012345000014")
        for value in (
            "2012345678903",
            "0201234567899",
            "00201234567899",
            "0000000000000",
        ):
            with self.subTest(value=value), self.assertRaises(s.LookupError):
                s.gtin(value)

    def test_non_ascii_digits_are_rejected(self):
        value = "".join(chr(0xFF10 + int(char)) for char in "7891000325858")
        with self.assertRaises(s.LookupError):
            s.gtin(value)

    def test_invalid_token_never_calls_transport(self):
        for token in (None, "", "with space", "line\nfeed", 123, "x" * 4097):
            with (
                self.subTest(token_type=type(token).__name__),
                self.assertRaises(s.LookupError),
            ):
                s.lookup(
                    "7891000325858",
                    token,
                    lambda *a, **k: self.fail("Invalid credential sent"),
                )

    def test_json_mime_must_be_exact(self):
        with self.assertRaises(s.LookupError):
            s.lookup(
                "7891000325858",
                "FAKE",
                lambda *a, **k: (200, {"content-type": "application/jsonp"}, b"{}"),
            )

    def test_contract_rejects_numeric_and_boolean_fields(self):
        for value in (False, 0, [], {}):
            body = json.dumps(
                {"codbar": "7891000325858", "produto": "Fixture", "marca": value}
            ).encode()
            with self.subTest(value=value), self.assertRaises(s.LookupError):
                s.lookup(
                    "7891000325858",
                    "FAKE",
                    lambda *a, body=body, **k: (
                        200,
                        {"content-type": "application/json"},
                        body,
                    ),
                )

    def test_malformed_image_url_is_friendly(self):
        for url in ("https://[invalid/img/1.png", 12, None):
            with self.subTest(url=url), self.assertRaises(s.LookupError):
                s.image(url, lambda *a, **k: self.fail("Malformed URL sent"))

    def test_body_limit_and_timeout_are_explicit(self):
        from unittest.mock import MagicMock

        conn = MagicMock()
        conn.getresponse.return_value.status = 200
        conn.getresponse.return_value.read.return_value = b"{}"
        conn.getresponse.return_value.getheaders.return_value = [
            ("Content-Type", "application/json")
        ]
        with patch.object(s, "PinnedHTTPS", return_value=conn) as factory:
            s.transport("/api/produtos/7891000325858", "FAKE", limit=128)
        self.assertEqual(factory.call_args.kwargs["timeout"], 8)
        conn.getresponse.return_value.read.assert_called_once_with(129)
        headers = conn.request.call_args.kwargs["headers"]
        self.assertEqual(headers["Accept-Encoding"], "identity")
        conn.close.assert_called_once()

    def test_deep_json_is_sanitized_as_invalid_contract(self):
        body = (
            b'{"codbar":"7891000325858","produto":"Fixture","extra":'
            + b"[" * 10000
            + b"0"
            + b"]" * 10000
            + b"}"
        )
        self.assertLess(len(body), 262144)
        with self.assertRaises(RecursionError):
            json.loads(body)
        with self.assertRaisesRegex(s.LookupError, "^contract$") as error:
            s.lookup(
                "7891000325858",
                "FAKE_SECRET",
                lambda *a, **kw: (200, {"content-type": "application/json"}, body),
            )
        self.assertNotIn("FAKE_SECRET", str(error.exception))
        self.assertNotIn("extra", str(error.exception))


if __name__ == "__main__":
    unittest.main()


class CatalogueContractTests(unittest.TestCase):
    def send(self, payload):
        body = json.dumps(payload).encode()
        return lambda path, token=None, limit=None: (
            200,
            {"content-type": "application/json"},
            body,
        )

    def test_cdn_images_are_allowed(self):
        raw = b"RIFF0000WEBPfixture"
        for host in ("cdn2.si5.com.br", "cdn3.si5.com.br"):
            url = f"https://{host}/img/78/91/7891000100103.webp"
            seen = {}

            def fake(path, host=None, **kwargs):
                seen["host"] = host
                return 200, {"content-type": "image/webp"}, raw

            self.assertEqual(s.image(url, fake), raw)
            self.assertEqual(seen["host"], host)

    def test_cdn_lookalike_hosts_rejected(self):
        for url in (
            "https://cdn9.si5.com.br/img/1.webp",
            "https://cdn3.si5.com.br.evil.example/img/1.webp",
            "https://cdn3.si5.com.br:8443/img/1.webp",
        ):
            with self.assertRaises(s.LookupError):
                s.image(url, lambda *a, **k: self.fail("Transport must not be called"))

    def test_transport_refuses_unknown_host(self):
        with self.assertRaises(s.LookupError):
            s.transport("/img/1.webp", host="example.com")

    def test_upc_a_matches_normalised_ean13(self):
        payload = {"codbar": "0012000001291", "produto": "Pepsi", "peso": None}
        seen = []
        send = self.send(payload)

        def spy(path, token=None, limit=None):
            seen.append(path)
            return send(path, token)

        result = s.lookup("012000001291", "FAKE", spy)
        self.assertEqual(seen, ["/api/produtos/0012000001291"])
        self.assertEqual(result["produto"], "Pepsi")
        self.assertIsNone(result["peso"])

    def test_other_gtin_still_rejected(self):
        payload = {"codbar": "7891000100103", "produto": "Other"}
        with self.assertRaises(s.LookupError):
            s.lookup("7894900011517", "FAKE", self.send(payload))

    def test_weight_parsing(self):
        base = {"codbar": "7891000100103", "produto": "Leite"}
        for raw, expected in (("415.00", 415.0), ("0", None), ("", None), (None, None), ("NaN", None)):
            result = s.lookup("7891000100103", "FAKE", self.send(dict(base, peso=raw)))
            self.assertEqual(result["peso"], expected)
        for raw in ("abc", 415):
            with self.assertRaises(s.LookupError):
                s.lookup("7891000100103", "FAKE", self.send(dict(base, peso=raw)))

    def test_user_agent_is_sent(self):
        from unittest.mock import MagicMock

        with patch.object(s, "PinnedHTTPS") as conn_class:
            conn = conn_class.return_value
            response = MagicMock(status=200)
            response.read.return_value = b"{}"
            response.getheaders.return_value = []
            conn.getresponse.return_value = response
            s.transport("/api/produtos/7891000100103", token="FAKE")
            headers = conn.request.call_args.kwargs["headers"]
            self.assertTrue(headers["User-Agent"].startswith("Odoo-product_si5_gtin"))
