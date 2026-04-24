from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import grpc
import pytest
from shared.runtime_env import load_test_env, missing_local_prereqs

pytestmark = [pytest.mark.integration, pytest.mark.integration_local]


def _skip_if_unavailable() -> None:
    env = load_test_env()
    missing = missing_local_prereqs(env, require_afp=False)
    if missing:
        pytest.skip("Missing local prereqs: " + "; ".join(missing))
    channel = grpc.insecure_channel(
        f"{env.server_host}:{env.server_port}",
        options=(("grpc.enable_http_proxy", 0),),
    )
    try:
        grpc.channel_ready_future(channel).result(timeout=2)
    except grpc.FutureTimeoutError:
        pytest.skip("Isabelle REPL server unreachable for script integration test")
    finally:
        channel.close()


def _run_script(
    tmp_path: Path,
    candidate_tactic: str,
    *,
    disable_sledgehammer: bool = False,
    theory_name: str = "Simple.thy",
) -> subprocess.CompletedProcess[str]:
    env = load_test_env()
    records_path = tmp_path / "records.jsonl"
    cmd = [
        sys.executable,
        "scripts/run_repair_once.py",
        str(env.theories_dir / theory_name),
        "--isa-path",
        str(env.isabelle_path),
        "--host",
        env.server_host,
        "--port",
        str(env.server_port),
        "--working-dir",
        str(env.theories_dir),
        "--candidate-tactic",
        candidate_tactic,
        "--records-path",
        str(records_path),
    ]
    if disable_sledgehammer:
        cmd.append("--disable-sledgehammer")
    run_env = dict(os.environ)
    run_env["PYTHONPATH"] = "src"
    run_env["NO_PROXY"] = "localhost,127.0.0.1,::1"
    run_env["no_proxy"] = run_env["NO_PROXY"]
    return subprocess.run(
        cmd,
        cwd=Path(__file__).resolve().parents[3],
        env=run_env,
        check=False,
        text=True,
        capture_output=True,
    )


def test_run_repair_once_happy_path(tmp_path):
    _skip_if_unavailable()
    result = _run_script(tmp_path, "by simp")
    assert result.returncode == 0, result.stderr
    assert "final_state=finished" in result.stdout
    records_line = next(
        line for line in result.stdout.splitlines() if line.startswith("records_file=")
    )
    records_path = Path(records_line.split("=", 1)[1].strip())
    assert records_path.is_file()
    lines = records_path.read_text(encoding="utf-8").splitlines()
    first = json.loads(lines[0])
    assert first["theory_run_id"].startswith("run-")
    assert first["schema_version"] == "v1.5"
    terminal = [
        json.loads(line)
        for line in lines
        if json.loads(line)["record_kind"] == "terminal"
    ]
    assert terminal
    assert terminal[-1]["payload"]["terminal_reason"] == "theory_wide_finished"
    task_records = [
        json.loads(line) for line in lines if json.loads(line)["record_kind"] == "task"
    ]
    if task_records:
        payload = task_records[0]["payload"]
        assert "block_kind" in payload
        assert "selected_generator" in payload
        assert "validation_status" in payload


def test_run_repair_once_stops_on_first_failure(tmp_path):
    _skip_if_unavailable()
    result = _run_script(
        tmp_path,
        "by totally_nonexistent_tactic_xyz",
        disable_sledgehammer=True,
        theory_name="Unprovable.thy",
    )
    assert result.returncode == 0, result.stderr
    assert "final_state=stopped" in result.stdout
