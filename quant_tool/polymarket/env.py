"""Environment-variable loader for the Polymarket subsystem.

Reads ``.env`` if present and parses the values the runner needs into a typed
container. Keeping this separate from :mod:`config` means user-specific values
(wallet addresses, API keys) stay out of the source tree -- :mod:`config` holds
defaults that ship with the codebase.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

_ADDRESS_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")


def load_dotenv(path: str | Path | None = None) -> None:
    """Best-effort ``.env`` loader. Silently no-ops if the file is missing.

    Values already in ``os.environ`` take precedence so process-level overrides
    win over the file. We avoid the ``python-dotenv`` dependency since the
    format we use is trivially line-oriented.
    """
    target = Path(path) if path else Path.cwd() / ".env"
    if not target.is_file():
        return
    for line in target.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


@dataclass(frozen=True)
class PolymarketEnv:
    """Parsed env vars used by the runner. All fields are optional in paper mode."""

    wallet_address: str | None
    proxy_address: str | None
    clob_url: str
    gamma_url: str
    polygon_rpc_url: str
    clob_api_key: str | None
    clob_api_secret: str | None
    clob_api_passphrase: str | None

    def has_live_credentials(self) -> bool:
        return all((self.clob_api_key, self.clob_api_secret, self.clob_api_passphrase))


def from_environ() -> PolymarketEnv:
    """Build :class:`PolymarketEnv` from current ``os.environ``."""
    return PolymarketEnv(
        wallet_address=_address("POLYMARKET_WALLET_ADDRESS"),
        proxy_address=_address("POLYMARKET_PROXY_ADDRESS"),
        clob_url=os.environ.get("POLYMARKET_CLOB_URL", "https://clob.polymarket.com"),
        gamma_url=os.environ.get("POLYMARKET_GAMMA_URL", "https://gamma-api.polymarket.com"),
        polygon_rpc_url=os.environ.get("POLYGON_RPC_URL", "https://polygon-rpc.com"),
        clob_api_key=_nonempty("POLYMARKET_CLOB_API_KEY"),
        clob_api_secret=_nonempty("POLYMARKET_CLOB_API_SECRET"),
        clob_api_passphrase=_nonempty("POLYMARKET_CLOB_API_PASSPHRASE"),
    )


def _nonempty(key: str) -> str | None:
    value = os.environ.get(key, "").strip()
    return value or None


def _address(key: str) -> str | None:
    value = _nonempty(key)
    if value is None:
        return None
    if not _ADDRESS_RE.match(value):
        raise ValueError(f"{key} is not a valid 0x-prefixed 20-byte address: {value!r}")
    return value
