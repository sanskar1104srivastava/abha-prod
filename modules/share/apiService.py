from __future__ import annotations

from typing import Any

from common.abdm.abdmClient import AbdmClient
from common.abdm.abdmCryptoService import AbdmCryptoService
from common.config.settings import getSettings
from common.logging.loggingService import LoggingService
from common.utils.dateTimeUtils import DateTimeUtils
from modules.share.requests import ShareOnShareRequest


class ShareApiService:
    def __init__(self, abdmClient: AbdmClient | None = None) -> None:
        self.abdmClient = abdmClient or AbdmClient()
        self.settings = getSettings()
        self.logger = LoggingService("share.apiService")

    async def onShare(self, requestBody: ShareOnShareRequest) -> dict[str, Any]:
        """HIP sends acknowledgement to ABDM after receiving a patient profile share."""
        self.logger.logInput("onShare", body=requestBody.model_dump(mode="json"))
        acknowledgement: dict[str, Any] = {"status": requestBody.status}
        if requestBody.abhaAddress:
            acknowledgement["abhaAddress"] = requestBody.abhaAddress
        if requestBody.tokenNumber:
            acknowledgement["tokenNumber"] = requestBody.tokenNumber
        if requestBody.expiry:
            acknowledgement["expiry"] = requestBody.expiry
        if requestBody.context:
            acknowledgement["context"] = requestBody.context
        payload: dict[str, Any] = {
            "requestId": AbdmCryptoService.newRequestId(),
            "timestamp": DateTimeUtils.utcnowIso(),
            "acknowledgement": acknowledgement,
            "resp": {"requestId": requestBody.requestId},
        }
        return await self.abdmClient.hipPost("patientOnShare", payload)
