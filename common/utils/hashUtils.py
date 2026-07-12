from __future__ import annotations

import hashlib
import hmac
from typing import Any

from common.utils.jsonUtils import JsonUtils


class HashUtils:
    @staticmethod
    def md5Text(value: str) -> str:
        return hashlib.md5(value.encode("utf-8")).hexdigest()  # noqa: S324 - ABDM data-push checksum contract

    @staticmethod
    def sha256Text(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    @staticmethod
    def sha256Json(value: dict[str, Any]) -> str:
        return HashUtils.sha256Text(JsonUtils.dumps(value))

    @staticmethod
    def hmacSha256(secret: str, body: str) -> str:
        digest = hmac.new(secret.encode("utf-8"), body.encode("utf-8"), hashlib.sha256).hexdigest()
        return f"sha256={digest}"

    @staticmethod
    def secureCompare(left: str, right: str) -> bool:
        return hmac.compare_digest(left or "", right or "")
