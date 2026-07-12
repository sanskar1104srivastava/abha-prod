from __future__ import annotations

import json
import unittest
from pathlib import Path


class DeployContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(__file__).resolve().parents[1]
        self.registry = json.loads((self.root / "deploy" / "moduleRegistry.json").read_text(encoding="utf-8"))

    def test_registry_has_fixed_aws_defaults(self) -> None:
        self.assertEqual("algoflow", self.registry["aws"]["profile"])
        self.assertEqual("ap-south-1", self.registry["aws"]["region"])
        self.assertEqual("Image", self.registry["packageType"])

    def test_registry_has_four_modules(self) -> None:
        self.assertEqual(
            {
                "externalApi",
                "callbackRouter",
                "dataFlow",
                "webhookDispatcher",
            },
            set(self.registry["modules"].keys()),
        )

    def test_registry_has_dev_and_prod_secret_environments(self) -> None:
        self.assertEqual({"dev", "prod"}, set(self.registry["environments"].keys()))
        self.assertEqual("sahai/production-backend/dev", self.registry["environments"]["dev"]["secretName"])
        self.assertEqual("sahai/production-backend/prod", self.registry["environments"]["prod"]["secretName"])

    def test_registry_resource_names_match_plan(self) -> None:
        expectedRepos = {
            "sahai-production-external-api",
            "sahai-production-callback-router",
            "sahai-production-data-flow",
            "sahai-production-webhook-dispatcher",
        }
        modules = self.registry["modules"].values()
        self.assertEqual(expectedRepos, {module["ecrRepository"] for module in modules})
        self.assertEqual(
            {
                "external-api",
                "callback-router",
                "data-flow",
                "webhook-dispatcher",
            },
            {module["lambdaNameSuffix"] for module in modules},
        )

    def test_deploy_scripts_only_use_image_package_type(self) -> None:
        combined = "\n".join(
            [
                (self.root / "deploy" / "deploy.ps1").read_text(encoding="utf-8"),
                (self.root / "deploy" / "deploy.sh").read_text(encoding="utf-8"),
            ]
        )
        self.assertIn("--package-type Image", combined)
        self.assertIn("ImageUri=", combined)
        self.assertIn("configSecretName", combined)
        forbidden = [".zip", "zip-file", "package-type Zip"]
        for token in forbidden:
            self.assertNotIn(token, combined)


if __name__ == "__main__":
    unittest.main()
