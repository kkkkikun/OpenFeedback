"""Runtime configuration.

Every value has a working default so the service starts without a .env file.
Secrets that must never reach an APK or the repo are read from the
environment only; nothing here is a client-visible credential.
"""

from __future__ import annotations

import os
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_data_dir() -> Path:
    return Path(os.environ.get("OF_DATA_DIR", "/var/lib/openfeedback")).resolve()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="OF_", env_file=".env", extra="ignore")

    # --- storage -----------------------------------------------------------
    data_dir: Path = _default_data_dir()
    database_url: str = ""  # derived from data_dir when empty
    attachments_dir: Path = ""  # derived from data_dir when empty

    # --- server ------------------------------------------------------------
    host: str = "0.0.0.0"
    port: int = 8080
    environment: str = "production"
    base_url: str = ""  # public origin, used in admin links
    trusted_proxy_headers: bool = False

    # --- admin bootstrap ---------------------------------------------------
    # Used only to create the first admin row. Rotate after first login.
    admin_username: str = "admin"
    admin_password: str = ""

    # --- limits ------------------------------------------------------------
    max_body_bytes: int = 12 * 1024 * 1024
    max_attachment_bytes: int = 2 * 1024 * 1024
    max_attachments: int = 3
    max_title_length: int = 120
    max_description_length: int = 4000
    max_contact_length: int = 120
    max_diagnostics_length: int = 4000

    # --- rate limiting -----------------------------------------------------
    # Per (app_id, client ip) per hour. A single worker keeps this in memory.
    submissions_per_hour: int = 10
    admin_login_attempts_per_15min: int = 10

    # --- sessions ----------------------------------------------------------
    session_ttl_hours: int = 12
    cookie_secure: bool = True
    cookie_name: str = "of_admin_session"

    # --- privacy -----------------------------------------------------------
    # Client IPs are stored hashed; the raw IP never reaches the database.
    ip_hash_salt: str = ""

    def model_post_init(self, __context) -> None:  # noqa: D105
        if not self.database_url:
            self.database_url = f"sqlite:///{self.data_dir / 'openfeedback.db'}"
        if not self.attachments_dir:
            self.attachments_dir = self.data_dir / "attachments"
        if not self.base_url:
            self.base_url = f"http://localhost:{self.port}"
        if not self.ip_hash_salt:
            # Stable across restarts so rate-limit buckets survive a restart.
            self.ip_hash_salt = "openfeedback-local-salt"

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


def get_settings() -> Settings:
    return Settings()
