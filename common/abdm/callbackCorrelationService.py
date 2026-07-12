from __future__ import annotations

from typing import Any


class CallbackCorrelationService:
    def extractCorrelationIds(self, path: str, headers: dict[str, Any], payload: dict[str, Any]) -> dict[str, str]:
        response = payload.get("response") if isinstance(payload.get("response"), dict) else {}
        resp = payload.get("resp") if isinstance(payload.get("resp"), dict) else {}
        notification = payload.get("notification") if isinstance(payload.get("notification"), dict) else {}
        consentRequest = payload.get("consentRequest") if isinstance(payload.get("consentRequest"), dict) else {}
        consent = payload.get("consent") if isinstance(payload.get("consent"), dict) else {}
        hiRequest = payload.get("hiRequest") if isinstance(payload.get("hiRequest"), dict) else {}
        keyMaterial = hiRequest.get("keyMaterial") if isinstance(hiRequest.get("keyMaterial"), dict) else {}
        loweredHeaders = {str(key).lower(): str(value) for key, value in headers.items()}
        return {
            "eventPath": path,
            "requestId": self.firstNonEmpty(payload.get("requestId"), response.get("requestId"), resp.get("requestId")),
            "transactionId": self.firstNonEmpty(payload.get("transactionId"), hiRequest.get("transactionId"), notification.get("transactionId")),
            "consentRequestId": self.firstNonEmpty(notification.get("consentRequestId"), consentRequest.get("id"), payload.get("consentRequestId")),
            "consentId": self.firstNonEmpty(
                notification.get("consentId"),
                payload.get("consentId"),
                consent.get("id"),
                ((consent.get("consentDetail") or {}).get("consentId") if isinstance(consent.get("consentDetail"), dict) else ""),
                ((hiRequest.get("consent") or {}).get("id") if isinstance(hiRequest.get("consent"), dict) else ""),
                next(iter(self.extractConsentArtefactIds(payload)), ""),
            ),
            "hipId": self.firstNonEmpty(
                loweredHeaders.get("x-hip-id"),
                ((notification.get("consentDetail") or {}).get("hip") or {}).get("id") if isinstance(notification.get("consentDetail"), dict) else "",
                ((consent.get("consentDetail") or {}).get("hip") or {}).get("id") if isinstance(consent.get("consentDetail"), dict) else "",
            ),
            "hiuId": self.firstNonEmpty(
                loweredHeaders.get("x-hiu-id"),
                ((notification.get("consentDetail") or {}).get("hiu") or {}).get("id") if isinstance(notification.get("consentDetail"), dict) else "",
                ((consent.get("consentDetail") or {}).get("hiu") or {}).get("id") if isinstance(consent.get("consentDetail"), dict) else "",
                ((hiRequest.get("hiu") or {}).get("id") if isinstance(hiRequest.get("hiu"), dict) else ""),
            ),
            "hasKeyMaterial": "true" if keyMaterial else "false",
        }

    @staticmethod
    def extractConsentArtefactIds(payload: dict[str, Any]) -> list[str]:
        """Return every consent artefact ID from a HIU consent notify callback.
        A granted consent can carry multiple artefacts (one per HIP) — all of them
        are needed to collect the patient's complete data."""
        notification = payload.get("notification") if isinstance(payload.get("notification"), dict) else {}
        rawArtefacts = (
            notification.get("consentArtefacts")
            or notification.get("consentArtifacts")
            or notification.get("artefacts")
            or notification.get("artifacts")
            or []
        )
        if isinstance(rawArtefacts, dict):
            rawArtefacts = [rawArtefacts]
        elif not isinstance(rawArtefacts, list):
            rawArtefacts = []
        artefactIds: list[str] = []
        for artefact in rawArtefacts:
            if isinstance(artefact, dict):
                artefactId = CallbackCorrelationService.firstNonEmpty(
                    artefact.get("id"), artefact.get("consentId"), artefact.get("artefactId"), artefact.get("artifactId")
                )
            else:
                artefactId = str(artefact or "").strip()
            if artefactId and artefactId not in artefactIds:
                artefactIds.append(artefactId)
        return artefactIds

    @staticmethod
    def firstNonEmpty(*values: Any) -> str:
        for value in values:
            text = str(value or "").strip()
            if text:
                return text
        return ""
