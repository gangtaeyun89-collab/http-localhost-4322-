import os

import pytest

from quant_tool.polymarket.env import PolymarketEnv, from_environ, load_dotenv


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for key in list(os.environ):
        if key.startswith(("POLYMARKET_", "POLYGON_")):
            monkeypatch.delenv(key, raising=False)


def test_from_environ_returns_defaults_when_unset():
    env = from_environ()
    assert env.wallet_address is None
    assert env.proxy_address is None
    assert env.clob_url == "https://clob.polymarket.com"
    assert env.gamma_url == "https://gamma-api.polymarket.com"
    assert env.polygon_rpc_url == "https://polygon-rpc.com"
    assert not env.has_live_credentials()


def test_from_environ_parses_addresses(monkeypatch):
    monkeypatch.setenv("POLYMARKET_WALLET_ADDRESS", "0xAc5c1D6657eef3F0EC2b44b5Ab2d5eDF39caf3F9")
    monkeypatch.setenv("POLYMARKET_PROXY_ADDRESS", "0xa8Fd04Ad1A2FF5a57D850A5bE6Fce5D28848C52f")
    env = from_environ()
    assert env.wallet_address == "0xAc5c1D6657eef3F0EC2b44b5Ab2d5eDF39caf3F9"
    assert env.proxy_address == "0xa8Fd04Ad1A2FF5a57D850A5bE6Fce5D28848C52f"


def test_from_environ_rejects_malformed_address(monkeypatch):
    monkeypatch.setenv("POLYMARKET_WALLET_ADDRESS", "0xnothex")
    with pytest.raises(ValueError, match="POLYMARKET_WALLET_ADDRESS"):
        from_environ()


def test_has_live_credentials_requires_all_three(monkeypatch):
    monkeypatch.setenv("POLYMARKET_CLOB_API_KEY", "k")
    monkeypatch.setenv("POLYMARKET_CLOB_API_SECRET", "s")
    assert not from_environ().has_live_credentials()
    monkeypatch.setenv("POLYMARKET_CLOB_API_PASSPHRASE", "p")
    assert from_environ().has_live_credentials()


def test_load_dotenv_reads_file_and_does_not_override(tmp_path, monkeypatch):
    monkeypatch.setenv("POLYMARKET_CLOB_URL", "https://already-set")
    dotenv = tmp_path / ".env"
    dotenv.write_text(
        "POLYMARKET_WALLET_ADDRESS=0xAc5c1D6657eef3F0EC2b44b5Ab2d5eDF39caf3F9\n"
        "POLYMARKET_CLOB_URL=https://from-file\n"
        "# comment line\n"
        "\n"
    )
    load_dotenv(dotenv)
    assert os.environ["POLYMARKET_WALLET_ADDRESS"] == "0xAc5c1D6657eef3F0EC2b44b5Ab2d5eDF39caf3F9"
    assert os.environ["POLYMARKET_CLOB_URL"] == "https://already-set"  # not overridden


def test_load_dotenv_silent_when_file_missing(tmp_path):
    load_dotenv(tmp_path / "nope.env")  # must not raise


def test_env_dataclass_is_frozen():
    env = PolymarketEnv(
        wallet_address=None, proxy_address=None,
        clob_url="x", gamma_url="x", polygon_rpc_url="x",
        clob_api_key=None, clob_api_secret=None, clob_api_passphrase=None,
    )
    with pytest.raises(Exception):
        env.wallet_address = "0x1"  # type: ignore[misc]
