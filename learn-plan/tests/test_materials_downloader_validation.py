from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import sys

SKILL_DIR = Path(__file__).resolve().parents[1]
if str(SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(SKILL_DIR))

from learn_materials.downloader import download_file, validate_downloaded_content


class FakeHeaders(dict):
    def get(self, key: str, default=None):
        return super().get(key, default)


class FakeResponse:
    def __init__(self, content: bytes, content_type: str = "application/pdf", url: str = "https://example.com/file.pdf") -> None:
        self.content = content
        self.headers = FakeHeaders({"Content-Type": content_type, "Content-Length": str(len(content))})
        self.url = url

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self) -> bytes:
        return self.content

    def geturl(self) -> str:
        return self.url


class MaterialsDownloaderValidationTest(unittest.TestCase):
    def test_rejects_empty_content(self) -> None:
        valid, _, metadata = validate_downloaded_content(b"", url="https://example.com/a.pdf", content_type="application/pdf", expected_ext=".pdf")
        self.assertFalse(valid)
        self.assertEqual(metadata.get("reason"), "empty-content")

    def test_rejects_login_html_for_pdf(self) -> None:
        valid, _, metadata = validate_downloaded_content(
            b"<html><title>Login</title>Please sign in</html>" + b"x" * 200,
            url="https://example.com/a.pdf",
            content_type="text/html",
            expected_ext=".pdf",
        )
        self.assertFalse(valid)
        self.assertEqual(metadata.get("reason"), "invalid-pdf-signature")

    def test_accepts_pdf_signature(self) -> None:
        valid, _, metadata = validate_downloaded_content(
            b"%PDF-1.4\n" + b"x" * 200,
            url="https://example.com/a.pdf",
            content_type="application/pdf",
            expected_ext=".pdf",
        )
        self.assertTrue(valid)
        self.assertEqual(metadata.get("status"), "valid")

    def test_rejects_invalid_json(self) -> None:
        valid, _, metadata = validate_downloaded_content(b"{bad", url="https://example.com/a.json", content_type="application/json", expected_ext=".json")
        self.assertFalse(valid)
        self.assertEqual(metadata.get("reason"), "invalid-json")

    def test_invalid_download_does_not_write_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir) / "file"
            with patch("learn_materials.downloader.urlopen", return_value=FakeResponse(b"", content_type="application/pdf")):
                success, _, final_path, metadata = download_file("https://example.com/file.pdf", target)
            self.assertFalse(success)
            self.assertFalse(final_path.exists())
            self.assertEqual(metadata.get("reason"), "empty-content")


if __name__ == "__main__":
    unittest.main()
