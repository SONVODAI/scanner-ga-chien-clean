"""
Configuration for the intraday memory collector.

Storage root and provider credentials are read from environment variables.
No secrets are hard-coded.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

VN_TZ_NAME = "Asia/Ho_Chi_Minh"
DEFAULT_DATA_ROOT = "intraday_memory"
DEFAULT_PROVIDER = "KBS"
DEFAULT_SOURCE_TAG = "vnstock4_kbs"
COLLECTOR_VERSION = "1.0.0-a"

# Conservative rate-limit ceilings (requests per minute).
GUEST_RPM = 18
COMMUNITY_RPM = 55

MAX_RETRIES = 3
RETRY_BASE_DELAY_SEC = 2.0


@dataclass(frozen=True)
class IntradayConfig:
    """Runtime configuration for collector, storage, and provider."""

    data_root: Path = field(default_factory=lambda: Path(DEFAULT_DATA_ROOT))
    provider_source: str = DEFAULT_PROVIDER
    source_tag: str = DEFAULT_SOURCE_TAG
    requests_per_minute: int = GUEST_RPM
    max_retries: int = MAX_RETRIES
    retry_base_delay_sec: float = RETRY_BASE_DELAY_SEC
    app_py_path: Path = field(
        default_factory=lambda: Path(__file__).resolve().parents[2] / "app.py"
    )
    collector_version: str = COLLECTOR_VERSION

    @classmethod
    def from_env(cls) -> IntradayConfig:
        root = os.getenv("MRBOT_INTRADAY_DATA_ROOT", DEFAULT_DATA_ROOT)
        rpm_env = os.getenv("MRBOT_INTRADAY_RPM")
        rpm = int(rpm_env) if rpm_env else (
            COMMUNITY_RPM if os.getenv("VNSTOCK_API_KEY") else GUEST_RPM
        )
        app_path = os.getenv("MRBOT_APP_PY_PATH")
        return cls(
            data_root=Path(root),
            requests_per_minute=min(rpm, COMMUNITY_RPM),
            app_py_path=Path(app_path) if app_path else cls().app_py_path,
        )


def detect_tier() -> str:
    """
    Return provider tier label without exposing credentials.

    Community if VNSTOCK_API_KEY is set or a persisted key file exists.
    """
    if os.getenv("VNSTOCK_API_KEY", "").strip():
        return "community"

    key_file = Path.home() / ".vnstock" / "api_key.json"
    if key_file.exists() and key_file.stat().st_size > 0:
        return "community"

    return "guest"
