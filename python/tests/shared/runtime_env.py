from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RuntimeEnv:
    server_host: str
    server_port: int
    isabelle_path: Path
    afp_path: Path
    theories_dir: Path
    completeness_workdir: Path
    query_optimization_workdir: Path
    hol_src: Path


def load_test_env() -> RuntimeEnv:
    tests_dir = Path(__file__).resolve().parents[1]
    isabelle_path = Path(
        os.environ.get("ISABELLE_PATH", "/home/lxk/Isabelle2025")
    ).expanduser()
    afp_path = Path(
        os.environ.get("AFP_PATH", "/home/lxk/repositories/afp-2025/thys")
    ).expanduser()
    return RuntimeEnv(
        server_host=os.environ.get("ISABELLE_REPL_HOST", "localhost"),
        server_port=int(os.environ.get("ISABELLE_REPL_PORT", "50051")),
        isabelle_path=isabelle_path,
        afp_path=afp_path,
        theories_dir=tests_dir / "theories",
        completeness_workdir=afp_path / "Completeness",
        query_optimization_workdir=afp_path / "Query_Optimization",
        hol_src=isabelle_path / "src" / "HOL",
    )


def missing_local_prereqs(env: RuntimeEnv, require_afp: bool) -> list[str]:
    missing: list[str] = []

    if not env.theories_dir.is_dir():
        missing.append(f"Missing local theories dir: {env.theories_dir}")

    if not env.isabelle_path.is_dir():
        missing.append(f"Missing ISABELLE_PATH dir: {env.isabelle_path}")
    elif not env.hol_src.is_dir():
        missing.append(f"Missing HOL source dir: {env.hol_src}")

    if require_afp:
        if not env.afp_path.is_dir():
            missing.append(f"Missing AFP_PATH dir: {env.afp_path}")
        if not env.completeness_workdir.is_dir():
            missing.append(
                f"Missing AFP Completeness workdir: {env.completeness_workdir}"
            )
        if not env.query_optimization_workdir.is_dir():
            missing.append(
                "Missing AFP Query_Optimization workdir: "
                f"{env.query_optimization_workdir}"
            )

    return missing
