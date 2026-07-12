from __future__ import annotations

from common.utils.hashUtils import HashUtils


class WebhookSignatureService:
    @staticmethod
    def signPayload(secret: str, body: str) -> str:
        return HashUtils.hmacSha256(secret, body)

    @staticmethod
    def verifyPayload(secret: str, body: str, signature: str) -> bool:
        expected = WebhookSignatureService.signPayload(secret, body)
        return HashUtils.secureCompare(expected, signature)
