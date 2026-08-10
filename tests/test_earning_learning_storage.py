"""Regression tests for GitHubLocalStorage large-file read behavior."""

from __future__ import annotations

import base64
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from modules.earning_learning import GitHubConfig, GitHubLocalStorage, LIFECYCLE_FILE


def _enabled_github() -> GitHubConfig:
    return GitHubConfig(
        token="test-token",
        owner="SONVODAI",
        repo="scanner-ga-chien-clean",
        branch="main",
        remote_dir="data/earning_learning",
    )


class GitHubLocalStorageReadTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.local_dir = Path(self.temp_dir.name)
        self.storage = GitHubLocalStorage(self.local_dir, _enabled_github())

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _mock_contents_response(self, payload: dict) -> mock.Mock:
        response = mock.Mock()
        response.status_code = 200
        response.json.return_value = payload
        return response

    def test_a_normal_base64_content_reads_correctly(self) -> None:
        content = "symbol,price\nAAA,10\n"
        encoded = base64.b64encode(content.encode("utf-8")).decode("ascii")
        api_response = self._mock_contents_response(
            {
                "size": len(content),
                "encoding": "base64",
                "content": encoded,
            }
        )

        with mock.patch.object(
            self.storage,
            "_request",
            return_value=api_response,
        ) as request_mock:
            result = self.storage.read_text("observations.csv")

        self.assertEqual(result.source, "GITHUB")
        self.assertEqual(result.text, content)
        request_mock.assert_called_once()

    def test_b_large_file_uses_download_url(self) -> None:
        large_content = "observation_id,t3_return_pct\nabc,1.23\n" * 50000
        download_url = (
            "https://raw.githubusercontent.com/SONVODAI/"
            "scanner-ga-chien-clean/main/data/earning_learning/"
            "pattern_lifecycle.csv"
        )
        api_response = self._mock_contents_response(
            {
                "size": len(large_content.encode("utf-8")),
                "encoding": "none",
                "content": "",
                "download_url": download_url,
            }
        )
        download_response = mock.Mock()
        download_response.status_code = 200
        download_response.content = large_content.encode("utf-8")
        download_response.text = large_content

        with mock.patch.object(
            self.storage,
            "_request",
            side_effect=[api_response, download_response],
        ) as request_mock:
            result = self.storage.read_text(LIFECYCLE_FILE)

        self.assertEqual(result.source, "GITHUB")
        self.assertEqual(result.text, large_content)
        self.assertEqual(request_mock.call_count, 2)
        self.assertEqual(
            request_mock.call_args_list[1].args[1],
            download_url,
        )

    def test_c_empty_large_response_does_not_poison_local_cache(self) -> None:
        local_path = self.local_dir / LIFECYCLE_FILE
        local_path.parent.mkdir(parents=True, exist_ok=True)
        preserved = "observation_id,t3_return_pct\nkeep-me,9.99\n"
        local_path.write_text(preserved, encoding="utf-8")

        api_response = self._mock_contents_response(
            {
                "size": 2_070_500,
                "encoding": "none",
                "content": "",
                "download_url": None,
            }
        )

        with mock.patch.object(
            self.storage,
            "_request",
            return_value=api_response,
        ):
            result = self.storage.read_text(LIFECYCLE_FILE)

        self.assertEqual(result.source, "LOCAL")
        self.assertEqual(result.text, preserved)
        self.assertEqual(local_path.read_text(encoding="utf-8"), preserved)

    def test_d_download_failure_falls_back_to_valid_local_cache(self) -> None:
        local_path = self.local_dir / LIFECYCLE_FILE
        local_path.parent.mkdir(parents=True, exist_ok=True)
        preserved = "observation_id,t3_return_pct\nlocal-fallback,4.56\n"
        local_path.write_text(preserved, encoding="utf-8")

        api_response = self._mock_contents_response(
            {
                "size": 2_070_500,
                "encoding": "none",
                "content": "",
                "download_url": "https://example.test/large.csv",
            }
        )
        download_response = mock.Mock()
        download_response.status_code = 503
        download_response.text = "Service unavailable"

        with mock.patch.object(
            self.storage,
            "_request",
            side_effect=[api_response, download_response],
        ):
            result = self.storage.read_text(LIFECYCLE_FILE)

        self.assertEqual(result.source, "LOCAL")
        self.assertEqual(result.text, preserved)
        self.assertEqual(local_path.read_text(encoding="utf-8"), preserved)

    def test_e_genuinely_empty_remote_file_returns_empty_content(self) -> None:
        api_response = self._mock_contents_response(
            {
                "size": 0,
                "encoding": "base64",
                "content": "",
            }
        )

        with mock.patch.object(
            self.storage,
            "_request",
            return_value=api_response,
        ):
            result = self.storage.read_text("empty.csv")

        self.assertEqual(result.source, "GITHUB")
        self.assertEqual(result.text, "")


if __name__ == "__main__":
    unittest.main()
