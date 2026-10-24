"""Prevent broken local links in the bilingual GitHub documentation."""

from __future__ import annotations

import re
import unittest
from pathlib import Path
from urllib.parse import unquote


ROOT = Path(__file__).resolve().parents[1]
DOCUMENTS = (
    ROOT / "README.md",
    ROOT / "README.en.md",
    ROOT / "docs/guide.zh-CN.md",
    ROOT / "docs/guide.en.md",
)


class DocumentationLinksTests(unittest.TestCase):
    def test_relative_links_resolve(self):
        for document in DOCUMENTS:
            with self.subTest(document=document.name):
                source = document.read_text(encoding="utf-8")
                for target in re.findall(r"(?<!!)\[[^\]]+\]\(([^)]+)\)", source):
                    if target.startswith(("http://", "https://", "mailto:", "#")):
                        continue
                    filename = unquote(target.split("#", 1)[0])
                    with self.subTest(target=target):
                        self.assertTrue((document.parent / filename).exists())

    def test_every_guide_can_switch_language(self):
        chinese = (ROOT / "docs/guide.zh-CN.md").read_text(encoding="utf-8")
        english = (ROOT / "docs/guide.en.md").read_text(encoding="utf-8")
        self.assertIn("(guide.en.md)", chinese)
        self.assertIn("(guide.zh-CN.md)", english)
        self.assertIn("(README.en.md)", (ROOT / "README.md").read_text(encoding="utf-8"))
        self.assertIn("(README.md)", (ROOT / "README.en.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
