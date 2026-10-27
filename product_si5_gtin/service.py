# Copyright 2026 SI5
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Small independently testable client. Never log requests or credentials."""

import http.client
import ipaddress
import json
import re
import socket
import ssl
from decimal import Decimal, InvalidOperation
from urllib.parse import urlsplit

HOST = "global.si5.com.br"
# Product pictures are served by the SI5 CDNs, never by arbitrary hosts.
IMAGE_HOSTS = frozenset({HOST, "cdn2.si5.com.br", "cdn3.si5.com.br"})
USER_AGENT = "Odoo-product_si5_gtin/18.0 (+https://github.com/dhoneshost/odoo-si5-gtin)"
TEXT_FIELDS = (
    "produto",
    "marca",
    "imagem_url",
    "ncm",
    "cest_codigo",
    "ncm_descricao",
    "categoria",
)


class LookupError(Exception):
    """Stable codes only: never credential, URL, response or traceback text."""

    def __init__(self, code):
        self.code = code
        super().__init__(code)


def gtin(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{8}|[0-9]{12,14}", value):
        raise LookupError("gtin_format")
    if not value.strip("0"):
        raise LookupError("gtin_format")
    unit = (
        value[1:]
        if len(value) == 14
        else value.zfill(13)
        if len(value) == 12
        else value
    )
    prefix = int(unit[:3])
    if 20 <= prefix <= 29 or 40 <= prefix <= 49 or 200 <= prefix <= 299:
        raise LookupError("restricted_code")
    total = sum(int(c) * (3 if i % 2 == 0 else 1) for i, c in enumerate(value[-2::-1]))
    if (10 - total % 10) % 10 != int(value[-1]):
        raise LookupError("gtin_checksum")
    return value


class PinnedHTTPS(http.client.HTTPSConnection):
    def connect(self):
        addresses = socket.getaddrinfo(self.host, 443, type=socket.SOCK_STREAM)
        if not addresses or any(
            not ipaddress.ip_address(a[4][0]).is_global for a in addresses
        ):
            raise LookupError("destination")
        # Connect to the validated IP; TLS still checks the original hostname.
        self.sock = socket.create_connection((addresses[0][4][0], 443), self.timeout)
        self.sock = self._context.wrap_socket(self.sock, server_hostname=self.host)


def transport(path, token=None, limit=262144, host=HOST):
    if host not in IMAGE_HOSTS:
        raise LookupError("destination")
    conn = PinnedHTTPS(host, timeout=8, context=ssl.create_default_context())
    try:
        headers = {
            "Accept": "application/json" if token else "image/*",
            "Accept-Encoding": "identity",
            # Without an identifying agent the CDN may answer with a bot challenge.
            "User-Agent": USER_AGENT,
        }
        if token:
            headers["Authorization"] = "Bearer " + token
        conn.request("GET", path, headers=headers)
        response = conn.getresponse()
        body = response.read(limit + 1)
        if len(body) > limit:
            raise LookupError("response_size")
        return (
            response.status,
            dict((k.lower(), v) for k, v in response.getheaders()),
            body,
        )
    except LookupError:
        raise
    except (OSError, http.client.HTTPException, ValueError):
        raise LookupError("network") from None
    finally:
        conn.close()


def check_status(status, headers):
    if headers.get("cf-mitigated") == "challenge" or (
        status in (403, 503) and "text/html" in headers.get("content-type", "")
    ):
        raise LookupError("challenge")
    errors = {401: "authentication", 403: "forbidden", 404: "not_found", 429: "quota"}
    if status != 200:
        raise LookupError(errors.get(status, "unavailable"))


def _weight_grams(value):
    """API sends gross weight in grams as a decimal string ("415.00"); None if absent."""
    if value is None or value == "":
        return None
    if not isinstance(value, str) or len(value) > 32:
        raise ValueError()
    try:
        grams = Decimal(value)
    except InvalidOperation:
        raise ValueError() from None
    # Zero/negative or above 100 t is not a usable product weight: ignore it.
    if not grams.is_finite() or grams <= 0 or grams > 100000000:
        return None
    return float(grams)


def lookup(code, token, send=transport):
    code = gtin(code)
    if not isinstance(token, str) or not re.fullmatch(r"[!-~]{1,4096}", token):
        raise LookupError("configuration")
    # The catalogue keys UPC-A (12 digits) as EAN-13 with a leading zero.
    query = code.zfill(13) if len(code) == 12 else code
    status, headers, body = send("/api/produtos/" + query, token=token)
    check_status(status, headers)
    if (
        headers.get("content-type", "").split(";", 1)[0].strip().lower()
        != "application/json"
    ):
        raise LookupError("json_type")
    try:
        data = json.loads(body.decode("utf-8-sig"))
        if not isinstance(data, dict) or not isinstance(data.get("codbar"), str):
            raise ValueError()
        # The catalogue may normalise UPC-A (12) to EAN-13 with a leading zero.
        if data["codbar"].zfill(14) != code.zfill(14):
            raise ValueError()
        result = {}
        for key in TEXT_FIELDS:
            value = data.get(key)
            if value is None:
                value = ""
            if not isinstance(value, str) or len(value) > 2048:
                raise ValueError()
            result[key] = value.strip()
        if not result["produto"]:
            raise ValueError()
        result["peso"] = _weight_grams(data.get("peso"))
        return result
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise LookupError("contract") from None


def image(url, send=transport):
    if not isinstance(url, str):
        raise LookupError("image_url")
    try:
        parts = urlsplit(url)
    except (TypeError, ValueError):
        raise LookupError("image_url") from None
    if (
        parts.scheme != "https"
        or parts.netloc not in IMAGE_HOSTS
        or not re.fullmatch(r"/img/[0-9/]+\.(?:webp|png|jpg|jpeg)", parts.path)
        or parts.query
        or parts.fragment
    ):
        raise LookupError("image_url")
    status, headers, body = send(parts.path, limit=2097152, host=parts.netloc)
    check_status(status, headers)
    mime = headers.get("content-type", "").split(";")[0].strip().lower()
    valid = (
        mime == "image/png"
        and body.startswith(b"\x89PNG\r\n\x1a\n")
        or mime == "image/jpeg"
        and body.startswith(b"\xff\xd8\xff")
        or mime == "image/webp"
        and body[:4] == b"RIFF"
        and body[8:12] == b"WEBP"
    )
    if not valid or len(body) > 2097152:
        raise LookupError("image_content")
    return body
