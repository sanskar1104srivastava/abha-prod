from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

from common.constants.errorCodes import ErrorCode
from common.http.errorHandler import AppError


class NetworkUtils:
    @staticmethod
    def validateExternalHttpsUrl(url: str) -> str:
        value = str(url or "").strip()
        parsed = urlparse(value)
        if parsed.scheme != "https" or not parsed.netloc:
            raise AppError(422, ErrorCode.DATA_PUSH_URL_INVALID, "URL must be absolute HTTPS")
        host = parsed.hostname or ""
        try:
            addresses = socket.getaddrinfo(host, None)
        except socket.gaierror as exc:
            raise AppError(422, ErrorCode.DATA_PUSH_URL_INVALID, "URL host could not be resolved") from exc
        for address in addresses:
            ip = ipaddress.ip_address(address[4][0])
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast:
                raise AppError(422, ErrorCode.DATA_PUSH_URL_INVALID, "URL must not resolve to a private network")
        return value
