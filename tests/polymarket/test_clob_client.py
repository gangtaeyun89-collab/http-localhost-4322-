"""ClobClient tests use an injected fake opener so no network calls are made."""

import io
import json
from contextlib import contextmanager

from quant_tool.polymarket.data.clob_client import ClobClient


@contextmanager
def _fake_response(payload):
    body = json.dumps(payload).encode()
    yield io.BytesIO(body)


def make_opener(payload):
    def opener(request, timeout):  # noqa: ARG001
        return _fake_response(payload).__enter__()
    return opener


def test_orderbook_parses_and_sorts_levels():
    payload = {
        "bids": [{"price": "0.40", "size": "10"}, {"price": "0.45", "size": "5"}],
        "asks": [{"price": "0.55", "size": "8"}, {"price": "0.50", "size": "12"}],
        "timestamp": "1716548400000",
    }
    client = ClobClient(opener=make_opener(payload))
    book = client.orderbook("tok-1")
    assert book.token_id == "tok-1"
    assert [b.price for b in book.bids] == [0.45, 0.40]  # highest first
    assert [a.price for a in book.asks] == [0.50, 0.55]  # lowest first
    assert book.best_bid().price == 0.45
    assert book.best_ask().price == 0.50
    assert book.mid() == 0.475


def test_midpoint_returns_float():
    client = ClobClient(opener=make_opener({"mid": "0.42"}))
    assert client.midpoint("tok-1") == 0.42


def test_midpoint_missing_returns_none():
    client = ClobClient(opener=make_opener({}))
    assert client.midpoint("tok-1") is None
