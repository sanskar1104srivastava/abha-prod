from __future__ import annotations

import ast
import unittest
from pathlib import Path


class StaticSyntaxTest(unittest.TestCase):
    def test_all_python_files_parse(self) -> None:
        root = Path(__file__).resolve().parents[1]
        failures: list[str] = []
        for path in sorted(root.rglob("*.py")):
            try:
                ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            except SyntaxError as exc:
                failures.append(f"{path.relative_to(root)}: {exc}")
        self.assertEqual([], failures)


if __name__ == "__main__":
    unittest.main()
