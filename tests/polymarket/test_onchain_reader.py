"""WalletReader tests use injected openers so no network is touched."""

import io
import json

import pytest

from quant_tool.polymarket.onchain.reader import (
    USDC_E_CONTRACT,
    WalletReader,
    _pad_address,
    _parse_position,
)


def _opener_for(responses: list[bytes]):
    """Return an opener that yields each response in order."""
    it = iter(responses)

    def opener(request, timeout):  # noqa: ARG001
        body = next(it)

        class _R:
            def __enter__(self_): return io.BytesIO(body)
            def __exit__(self_, *a): return False

        return _R()
    return opener


def test_pad_address_left_pads_to_32_bytes():
    assert _pad_address("0xAc5c1D6657eef3F0EC2b44b5Ab2d5eDF39caf3F9") == (
        "000000000000000000000000ac5c1d6657eef3f0ec2b44b5ab2d5edf39caf3f9"
    )


def test_pad_address_rejects_wrong_length():
    with pytest.raises(ValueError, match="20 bytes"):
        _pad_address("0xabc")


def test_usdc_balance_decodes_hex_result():
    # 1.234567 USDC = 1_234_567 wei (6 decimals) = 0x12d687 in hex
    response = json.dumps({"jsonrpc": "2.0", "id": 1,
                            "result": "0x000000000000000000000000000000000000000000000000000000000012d687"})
    reader = WalletReader(opener=_opener_for([response.encode()]))
    balance = reader.usdc_balance("0xAc5c1D6657eef3F0EC2b44b5Ab2d5eDF39caf3F9")
    assert balance == pytest.approx(1.234567)


def test_usdc_balance_zero_when_empty_result():
    response = json.dumps({"jsonrpc": "2.0", "id": 1, "result": "0x0"})
    reader = WalletReader(opener=_opener_for([response.encode()]))
    assert reader.usdc_balance("0x" + "0" * 40) == 0.0


def test_usdc_balance_raises_on_rpc_error():
    response = json.dumps({"jsonrpc": "2.0", "id": 1,
                            "error": {"code": -32000, "message": "boom"}})
    reader = WalletReader(opener=_opener_for([response.encode()]))
    with pytest.raises(RuntimeError, match="RPC error"):
        reader.usdc_balance("0x" + "0" * 40)


def test_parse_position_handles_camel_and_snake_case():
    camel = {
        "conditionId": "0xabc",
        "asset": "12345",
        "outcome": "Yes",
        "title": "Will X happen?",
        "size": "50",
        "avgPrice": "0.42",
        "curPrice": "0.55",
        "currentValue": "27.5",
        "realizedPnl": "0",
        "cashPnl": "6.5",
    }
    p = _parse_position(camel)
    assert p is not None
    assert p.size == 50.0
    assert p.outcome == "Yes"
    assert p.current_value == pytest.approx(27.5)
    assert p.unrealised_pnl == pytest.approx(6.5)


def test_parse_position_skips_zero_size():
    assert _parse_position({"size": 0}) is None


def test_parse_position_skips_malformed():
    assert _parse_position({"size": "not_a_number"}) is None
    assert _parse_position("not a dict") is None


def test_snapshot_combines_cash_and_positions():
    # First response: RPC balance call returns 100 USDC.
    rpc = json.dumps({"jsonrpc": "2.0", "id": 1,
                       "result": "0x0000000000000000000000000000000000000000000000000000000005f5e100"})
    # Second response: data-api returns two positions
    positions = [
        {"conditionId": "c1", "asset": "t1", "outcome": "Yes", "title": "Market 1",
         "size": "10", "avgPrice": "0.40", "curPrice": "0.55", "currentValue": "5.5",
         "realizedPnl": "0", "cashPnl": "1.5"},
        {"conditionId": "c2", "asset": "t2", "outcome": "No", "title": "Market 2",
         "size": "20", "avgPrice": "0.30", "curPrice": "0.20", "currentValue": "4.0",
         "realizedPnl": "0", "cashPnl": "-2.0"},
    ]
    reader = WalletReader(opener=_opener_for([rpc.encode(), json.dumps(positions).encode()]))
    snap = reader.snapshot("0xAc5c1D6657eef3F0EC2b44b5Ab2d5eDF39caf3F9")
    assert snap.usdc_balance == 100.0
    assert len(snap.positions) == 2
    assert snap.total_position_value == pytest.approx(9.5)
    assert snap.total_equity == pytest.approx(109.5)
    assert snap.unrealised_pnl_total == pytest.approx(-0.5)


def test_snapshot_falls_back_when_rpc_fails():
    """A wallet that can't be reached returns zeros rather than crashing the dashboard."""
    def bad_opener(request, timeout):  # noqa: ARG001
        raise ConnectionError("network down")
    reader = WalletReader(opener=bad_opener)
    snap = reader.snapshot("0xAc5c1D6657eef3F0EC2b44b5Ab2d5eDF39caf3F9")
    assert snap.usdc_balance == 0.0
    assert snap.positions == ()
