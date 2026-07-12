from __future__ import annotations

import json
from typing import Any


class JsonUtils:
    @staticmethod
    def dumps(value: Any) -> str:
        return json.dumps(value, default=str, separators=(",", ":"), sort_keys=True)

    @staticmethod
    def loadsObject(text: str) -> dict[str, Any]:
        parsed = json.loads(text or "{}")
        return parsed if isinstance(parsed, dict) else {}
