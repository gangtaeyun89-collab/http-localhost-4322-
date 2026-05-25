"""Bot-control helpers -- PID file lifecycle, start/stop without the network."""

import os
import sys
import time
from pathlib import Path

# The Streamlit page module isn't normally importable (filename starts with a
# digit). Load it directly so we can unit-test the helpers.
import importlib.util


def _load_module():
    repo_root = Path(__file__).resolve().parents[2]
    page = repo_root / "quant_tool" / "polymarket" / "dashboard" / "pages" / "9_Bot_control.py"
    spec = importlib.util.spec_from_file_location("bot_control_page", page)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def test_get_running_pid_returns_none_when_no_file(tmp_path, monkeypatch):
    mod = _load_module()
    monkeypatch.setattr(mod, "PID_FILE", tmp_path / "bot.pid")
    assert mod.get_running_pid() is None


def test_get_running_pid_returns_pid_when_alive(tmp_path, monkeypatch):
    mod = _load_module()
    monkeypatch.setattr(mod, "PID_FILE", tmp_path / "bot.pid")
    mod.PID_FILE.write_text(str(os.getpid()))  # our own pid is definitely alive
    assert mod.get_running_pid() == os.getpid()


def test_get_running_pid_cleans_up_stale_file(tmp_path, monkeypatch):
    mod = _load_module()
    monkeypatch.setattr(mod, "PID_FILE", tmp_path / "bot.pid")
    # PID 2**22 is almost certainly not a running process.
    mod.PID_FILE.write_text(str(2**22))
    assert mod.get_running_pid() is None
    assert not mod.PID_FILE.exists()


def test_get_running_pid_handles_malformed_file(tmp_path, monkeypatch):
    mod = _load_module()
    monkeypatch.setattr(mod, "PID_FILE", tmp_path / "bot.pid")
    mod.PID_FILE.write_text("not a number")
    assert mod.get_running_pid() is None


def test_start_then_stop_bot(tmp_path, monkeypatch):
    """End-to-end: spawn a tiny subprocess, confirm PID file, kill it.

    We don't run the real polymarket_live.py because that would need network.
    Instead we monkey-patch the command builder to spawn a long-lived sleep.
    """
    mod = _load_module()
    monkeypatch.setattr(mod, "PID_FILE", tmp_path / "bot.pid")
    monkeypatch.setattr(mod, "LOG_FILE", tmp_path / "bot.log")

    original_popen = mod.subprocess.Popen
    spawned: list = []

    def fake_popen(cmd, **kwargs):
        proc = original_popen([sys.executable, "-c",
                                "import time; time.sleep(30)"], **kwargs)
        spawned.append(proc)
        return proc

    monkeypatch.setattr(mod.subprocess, "Popen", fake_popen)

    pid = mod.start_bot(db="x.sqlite", bankroll=1000, interval=60,
                         markets=10, max_per_market=0.5, max_total=1.0,
                         strategies=["market_maker"])
    assert pid > 0
    assert mod.PID_FILE.exists()
    assert mod.PID_FILE.read_text() == str(pid)
    time.sleep(0.2)
    assert mod._is_alive(pid)

    mod.stop_bot(pid)
    assert not mod.PID_FILE.exists()
    # Reap the child so it doesn't linger as a zombie (which os.kill(pid, 0)
    # treats as alive, even though the process has exited).
    spawned[0].wait(timeout=5)
    assert spawned[0].returncode is not None  # process actually terminated


def test_on_streamlit_cloud_detection(monkeypatch):
    mod = _load_module()
    # Default test environment: no /mount/src, no STREAMLIT_COMMUNITY_CLOUD
    monkeypatch.delenv("STREAMLIT_COMMUNITY_CLOUD", raising=False)
    # Can't easily prevent /mount/src from existing if it does on the host;
    # but on a normal dev box it won't.
    if not Path("/mount/src").exists():
        assert mod.on_streamlit_cloud() is False
    monkeypatch.setenv("STREAMLIT_COMMUNITY_CLOUD", "true")
    assert mod.on_streamlit_cloud() is True
