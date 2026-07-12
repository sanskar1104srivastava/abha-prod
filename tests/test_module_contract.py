from __future__ import annotations

import unittest
from pathlib import Path


class ModuleContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(__file__).resolve().parents[1]

    def test_expected_module_files_exist(self) -> None:
        expected = {
            "externalApi": ["main.py", "routes.py", "apiService.py", "dbService.py", "requests.py", "responses.py", "constants.py", "Dockerfile"],
            "callbackRouter": ["main.py", "routes.py", "apiService.py", "dbService.py", "requests.py", "responses.py", "constants.py", "Dockerfile"],
            "dataFlow": ["main.py", "routes.py", "apiService.py", "dbService.py", "requests.py", "responses.py", "constants.py", "Dockerfile"],
            "webhookDispatcher": ["main.py", "apiService.py", "dbService.py", "requests.py", "responses.py", "constants.py", "Dockerfile"],
        }
        missing: list[str] = []
        for moduleName, files in expected.items():
            modulePath = self.root / "modules" / moduleName
            for fileName in files:
                if not (modulePath / fileName).exists():
                    missing.append(f"{moduleName}/{fileName}")
        self.assertEqual([], missing)

    def test_dockerfiles_use_lambda_image_commands(self) -> None:
        for dockerfile in sorted((self.root / "modules").glob("*/Dockerfile")):
            text = dockerfile.read_text(encoding="utf-8")
            self.assertIn("public.ecr.aws/lambda/python:3.12", text)
            self.assertIn("CMD [", text)
            self.assertIn("COPY common common", text)
            self.assertIn("COPY modules modules", text)


if __name__ == "__main__":
    unittest.main()
