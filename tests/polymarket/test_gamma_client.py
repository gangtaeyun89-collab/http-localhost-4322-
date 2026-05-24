import io
import json

from quant_tool.polymarket.data.gamma_client import GammaClient


def _fake_opener(payload):
    body = json.dumps(payload).encode()
    def opener(request, timeout):  # noqa: ARG001
        return io.BytesIO(body)
    return opener


def test_active_markets_parses_typical_payload():
    payload = [{
        "conditionId": "0xabc",
        "question": "Will it rain?",
        "clobTokenIds": json.dumps(["111", "222"]),
        "outcomes": json.dumps(["Yes", "No"]),
        "orderPriceMinTickSize": "0.01",
        "orderMinSize": "5",
        "endDate": "2026-12-31T00:00:00Z",
        "closed": False,
        "active": True,
    }]
    client = GammaClient(opener=_fake_opener(payload))
    markets = client.active_markets()
    assert len(markets) == 1
    market = markets[0]
    assert market.condition_id == "0xabc"
    assert market.yes_token().token_id == "111"
    assert market.no_token().token_id == "222"
    assert market.tick_size == 0.01


def test_active_markets_skips_malformed_entries():
    payload = [
        {"conditionId": "0xok", "question": "q", "clobTokenIds": ["1", "2"], "outcomes": ["Yes", "No"]},
        {"conditionId": "0xbad"},  # missing required fields
        "not a dict",
    ]
    client = GammaClient(opener=_fake_opener(payload))
    markets = client.active_markets()
    assert len(markets) == 1
    assert markets[0].condition_id == "0xok"
