from __future__ import annotations

import asyncio
import re
import time
from typing import Any

import httpx

from common.abdm.abdmCryptoService import AbdmCryptoService
from common.config.settings import getSettings
from common.constants.errorCodes import ErrorCode
from common.http.errorHandler import AppError
from common.utils.dateTimeUtils import DateTimeUtils


class AbdmClient:
    _cachedToken: str = ""
    _tokenExpiry: float = 0.0
    _tokenOverride: str = ""  # set via admin endpoint for manual injection

    def __init__(self) -> None:
        self.settings = getSettings()
        self.client = httpx.AsyncClient(timeout=30)

    def _buildBaseHeaders(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "REQUEST-ID": AbdmCryptoService.newRequestId(),
            "TIMESTAMP": DateTimeUtils.utcnowIso(),
        }

    @classmethod
    def setGatewayToken(cls, token: str, expiresIn: int = 3600) -> None:
        cls._tokenOverride = token
        cls._cachedToken = token
        cls._tokenExpiry = time.monotonic() + max(expiresIn - 60, 60)

    async def _resolveToken(self) -> str:
        if AbdmClient._tokenOverride:
            return AbdmClient._tokenOverride
        if self.settings.abdmGatewayToken:
            return self.settings.abdmGatewayToken
        now = time.monotonic()
        if AbdmClient._cachedToken and now < AbdmClient._tokenExpiry:
            return AbdmClient._cachedToken
        return await self._fetchToken()

    async def _fetchToken(self) -> str:
        if not self.settings.abdmGatewayBase:
            raise AppError(500, ErrorCode.INTERNAL_ERROR, "ABDM gateway base is not configured")
        sessionPath = self.settings.abdmEndpoints.get("gatewaySession", "")
        if not sessionPath:
            raise AppError(500, ErrorCode.INTERNAL_ERROR, "ABDM gatewaySession endpoint is not configured")
        url = f"{self.settings.abdmGatewayBase.rstrip('/')}/{sessionPath.lstrip('/')}"
        lastError: Exception | None = None
        for attempt in range(3):
            if attempt:
                await asyncio.sleep(1.5 * attempt)
            try:
                response = await self.client.post(
                    url,
                    json={
                        "clientId": self.settings.abdmClientId,
                        "clientSecret": self.settings.abdmClientSecret,
                        "grantType": "client_credentials",
                    },
                    headers={
                        "Content-Type": "application/json",
                        "Accept": "application/json",
                        "REQUEST-ID": AbdmCryptoService.newRequestId(),
                        "TIMESTAMP": DateTimeUtils.utcnowIso(),
                        "X-CM-ID": self.settings.abdmCmId,
                    },
                    follow_redirects=True,
                )
                if response.status_code >= 400:
                    lastError = AppError(
                        500, ErrorCode.UPSTREAM_ERROR,
                        "ABDM session token fetch failed",
                        {"statusCode": response.status_code, "body": response.text[:500], "url": url},
                    )
                    continue
                data = response.json() if response.text else {}
                token = str(data.get("accessToken") or "")
                if token:
                    expiresIn = int(data.get("expiresIn") or 1800)
                    AbdmClient._cachedToken = token
                    AbdmClient._tokenExpiry = time.monotonic() + max(expiresIn - 60, 60)
                return token
            except AppError:
                raise
            except Exception as exc:
                lastError = exc
        raise lastError or AppError(500, ErrorCode.UPSTREAM_ERROR, "ABDM session token fetch failed after retries")

    async def testTokenFetch(self) -> dict[str, Any]:
        """Diagnostic: attempt token fetch and return full detail — for admin use only."""
        if not self.settings.abdmGatewayBase:
            return {"ok": False, "error": "abdmGatewayBase not configured"}
        sessionPath = self.settings.abdmEndpoints.get("gatewaySession", "")
        url = f"{self.settings.abdmGatewayBase.rstrip('/')}/{sessionPath.lstrip('/')}"
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "REQUEST-ID": AbdmCryptoService.newRequestId(),
            "TIMESTAMP": DateTimeUtils.utcnowIso(),
            "X-CM-ID": self.settings.abdmCmId,
        }
        try:
            response = await self.client.post(
                url,
                json={
                    "clientId": self.settings.abdmClientId,
                    "clientSecret": self.settings.abdmClientSecret,
                    "grantType": "client_credentials",
                },
                headers=headers,
                follow_redirects=True,
            )
            body = response.text[:1000]
            ok = response.status_code < 400
            if ok:
                data = response.json() if response.text else {}
                token = str(data.get("accessToken") or "")
                if token:
                    AbdmClient.setGatewayToken(token, int(data.get("expiresIn") or 1800))
            return {
                "ok": ok,
                "statusCode": response.status_code,
                "url": url,
                "clientId": self.settings.abdmClientId,
                "cmId": self.settings.abdmCmId,
                "timestamp": headers["TIMESTAMP"],
                "body": body,
            }
        except Exception as exc:
            return {"ok": False, "url": url, "error": str(exc)}

    async def hipPost(self, endpointKey: str, payload: dict[str, Any], extraHeaders: dict[str, str] | None = None, hipId: str = "") -> dict[str, Any]:
        token = await self._resolveToken()
        headers: dict[str, str] = {
            **self._buildBaseHeaders(),
            "Authorization": f"Bearer {token}",
            "X-CM-ID": self.settings.abdmCmId,
            "X-HIP-ID": hipId or self.settings.abdmHipId,
        }
        if extraHeaders:
            headers.update(extraHeaders)
        return await self.postGateway(self.settings.abdmEndpoint(endpointKey), payload, headers)

    async def hiuPost(self, endpointKey: str, payload: dict[str, Any], extraHeaders: dict[str, str] | None = None, hiuId: str = "") -> dict[str, Any]:
        token = await self._resolveToken()
        headers: dict[str, str] = {
            **self._buildBaseHeaders(),
            "Authorization": f"Bearer {token}",
            "X-CM-ID": self.settings.abdmCmId,
            "X-HIU-ID": hiuId or self.settings.abdmHiuId,
        }
        if extraHeaders:
            headers.update(extraHeaders)
        return await self.postGateway(self.settings.abdmEndpoint(endpointKey), payload, headers)

    async def postGatewayEndpoint(self, endpointKey: str, payload: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
        return await self.postGateway(self.settings.abdmEndpoint(endpointKey), payload, headers)

    async def fetchAbhaPublicKey(self) -> str:
        if self.settings.abdmAbhaPublicKey:
            return self.settings.abdmAbhaPublicKey
        if not self.settings.abdmAbhaCertUrl:
            raise AppError(500, ErrorCode.INTERNAL_ERROR, "ABDM ABHA cert URL is not configured (set abdmAbhaCertUrl or abdmAbhaPublicKey)")
        headers = {**self._buildBaseHeaders()}
        try:
            token = await self._resolveToken()
            headers["Authorization"] = f"Bearer {token}"
        except Exception:
            pass
        try:
            response = await self.client.get(self.settings.abdmAbhaCertUrl, headers=headers)
        except Exception as exc:
            raise AppError(424, ErrorCode.UPSTREAM_ERROR, "ABDM public key fetch failed (connection error)", {"error": str(exc), "url": self.settings.abdmAbhaCertUrl})
        if response.status_code >= 400:
            raise AppError(424, ErrorCode.UPSTREAM_ERROR, "ABDM public key fetch failed", {"statusCode": response.status_code, "body": response.text[:500]})
        text = (response.text or "").strip()
        if not text:
            raise AppError(424, ErrorCode.UPSTREAM_ERROR, "ABDM public key fetch returned empty response")
        # Response may be a raw PEM string or JSON {"publicKey": "<base64-DER>"}
        raw = text
        if text.startswith("{"):
            data = response.json()
            raw = str(data.get("publicKey") or text)
        # Strip PEM headers/footers and whitespace → plain base64-DER expected by rsaEncryptOaep
        return re.sub(r"-----[^-]+-----|[\s]", "", raw)

    async def abhaPost(self, path: str, payload: dict[str, Any], xToken: str = "", extraHeaders: dict[str, str] | None = None) -> dict[str, Any]:
        token = await self._resolveToken()
        if not self.settings.abdmAbhaBase:
            raise AppError(500, ErrorCode.INTERNAL_ERROR, "ABDM ABHA base is not configured")
        url = f"{self.settings.abdmAbhaBase.rstrip('/')}/{path.lstrip('/')}"
        headers = {**self._buildBaseHeaders(), "Authorization": f"Bearer {token}"}
        if xToken:
            headers["X-token"] = f"Bearer {xToken}"
        if extraHeaders:
            headers.update(extraHeaders)
        response = await self.client.post(url, json=payload, headers=headers)
        if response.status_code >= 400:
            raise AppError(424, ErrorCode.UPSTREAM_ERROR, "ABDM ABHA request failed", {"statusCode": response.status_code, "body": response.text[:1000]})
        if not response.text:
            return {}
        try:
            parsed = response.json()
        except ValueError:
            return {"raw": response.text}
        return parsed if isinstance(parsed, dict) else {"items": parsed}

    async def abhaGet(self, path: str, extraHeaders: dict[str, str] | None = None) -> dict[str, Any]:
        token = await self._resolveToken()
        if not self.settings.abdmAbhaBase:
            raise AppError(500, ErrorCode.INTERNAL_ERROR, "ABDM ABHA base is not configured")
        url = f"{self.settings.abdmAbhaBase.rstrip('/')}/{path.lstrip('/')}"
        headers = {**self._buildBaseHeaders(), "Authorization": f"Bearer {token}"}
        if extraHeaders:
            headers.update(extraHeaders)
        response = await self.client.get(url, headers=headers)
        if response.status_code >= 400:
            raise AppError(424, ErrorCode.UPSTREAM_ERROR, "ABDM ABHA request failed", {"statusCode": response.status_code, "body": response.text[:1000]})
        if not response.text:
            return {}
        try:
            parsed = response.json()
        except ValueError:
            return {"raw": response.text}
        return parsed if isinstance(parsed, dict) else {"items": parsed}

    async def hipGet(self, endpointKey: str, extraHeaders: dict[str, str] | None = None) -> dict[str, Any]:
        token = await self._resolveToken()
        headers: dict[str, str] = {
            **self._buildBaseHeaders(),
            "Authorization": f"Bearer {token}",
            "X-CM-ID": self.settings.abdmCmId,
            "X-HIP-ID": self.settings.abdmHipId,
        }
        if extraHeaders:
            headers.update(extraHeaders)
        path = self.settings.abdmEndpoint(endpointKey)
        url = f"{self.settings.abdmGatewayBase.rstrip('/')}/{path.lstrip('/')}"
        response = await self.client.get(url, headers=headers)
        if response.status_code >= 400:
            raise AppError(424, ErrorCode.UPSTREAM_ERROR, "ABDM gateway GET failed", {"statusCode": response.status_code, "body": response.text[:1000]})
        if not response.text:
            return {}
        try:
            parsed = response.json()
        except ValueError:
            return {"raw": response.text}
        return parsed if isinstance(parsed, dict) else {"items": parsed}

    async def abhaGetBinary(self, path: str, xToken: str = "") -> bytes:
        token = await self._resolveToken()
        if not self.settings.abdmAbhaBase:
            raise AppError(500, ErrorCode.INTERNAL_ERROR, "ABDM ABHA base is not configured")
        url = f"{self.settings.abdmAbhaBase.rstrip('/')}/{path.lstrip('/')}"
        headers = {**self._buildBaseHeaders(), "Authorization": f"Bearer {token}"}
        if xToken:
            headers["X-token"] = f"Bearer {xToken}"
        response = await self.client.get(url, headers=headers)
        if response.status_code >= 400:
            raise AppError(424, ErrorCode.UPSTREAM_ERROR, "ABDM ABHA binary request failed", {"statusCode": response.status_code, "body": response.text[:500]})
        return response.content

    async def patchGateway(self, path: str, payload: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
        if not self.settings.abdmGatewayBase:
            raise AppError(500, ErrorCode.INTERNAL_ERROR, "ABDM gateway base is not configured")
        url = f"{self.settings.abdmGatewayBase.rstrip('/')}/{path.lstrip('/')}"
        response = await self.client.patch(url, json=payload, headers=headers)
        if response.status_code >= 400:
            raise AppError(424, ErrorCode.UPSTREAM_ERROR, "ABDM gateway PATCH failed", {"statusCode": response.status_code, "body": response.text[:1000]})
        if not response.text:
            return {"status": "ok"}
        try:
            parsed = response.json()
        except ValueError:
            return {"raw": response.text}
        return parsed if isinstance(parsed, dict) else {"items": parsed}

    async def postGateway(self, path: str, payload: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
        if not self.settings.abdmGatewayBase:
            raise AppError(500, ErrorCode.INTERNAL_ERROR, "ABDM gateway base is not configured")
        url = f"{self.settings.abdmGatewayBase.rstrip('/')}/{path.lstrip('/')}"
        response = await self.client.post(url, json=payload, headers=headers)
        if response.status_code >= 400:
            raise AppError(
                424,
                ErrorCode.UPSTREAM_ERROR,
                "ABDM gateway request failed",
                {"statusCode": response.status_code, "body": response.text[:1000]},
            )
        if not response.text:
            return {}
        try:
            parsed = response.json()
        except ValueError:
            return {"raw": response.text}
        return parsed if isinstance(parsed, dict) else {"items": parsed}
