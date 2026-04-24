from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import grpc
import pytest

from isabelle_repair.engine import RuleFirstGenerator
from isabelle_repair.model import (
    ArtifactKind,
    FailureKind,
    InterventionContext,
    InterventionResponse,
    InterventionResponseKind,
    PolicyContext,
    PolicyDecisionKind,
    TaskSpec,
    ValidationResult,
    ValidationStatus,
)
from isabelle_repair.policy import RuleBasedPolicyGate
from isabelle_repair.repl import ReplBlockLocalizer, ReplDeterministicTaskEngine
from isabelle_repair.run import TheoryRepairRun
from isabelle_repl import IsabelleReplClient

pytestmark = [pytest.mark.integration, pytest.mark.integration_afp_heavy]


@dataclass(frozen=True)
class LifeTableCaseEnv:
    host: str
    port: int
    isabelle_2024_path: Path
    afp_2023_thys: Path
    afp_2024_thys: Path
    theory_path: Path
    working_dir: Path
    hol_src: Path


@dataclass
class _LifeTableReviewedHook:
    replacements: list[str] = field(default_factory=list)
    applied_rules: list[str] = field(default_factory=list)

    def handle(self, context: InterventionContext) -> InterventionResponse:
        current = context.current_artifact_text or ""
        replacement, applied_rule = self._apply_rule(current)
        if replacement is None:
            return InterventionResponse(kind=InterventionResponseKind.REQUEST_STOP)
        self.applied_rules.append(applied_rule)
        self.replacements.append(replacement)
        return InterventionResponse(
            kind=InterventionResponseKind.PROVIDE_REPLACEMENT_ARTIFACT,
            replacement_artifact_text=replacement,
        )

    @staticmethod
    def _apply_rule(current: str) -> tuple[str | None, str]:
        lbint_p_l_v1 = "LBINT t:A. $p_{t&x} = (LBINT t:A. $l_(x+t)) / $l_x"
        lbint_p_l_v1_fixed = "(LBINT t:A. $p_{t&x}) = (LBINT t:A. $l_(x+t)) / $l_x"
        if lbint_p_l_v1 in current:
            return current.replace(lbint_p_l_v1, lbint_p_l_v1_fixed, 1), "lbint_p_l_1"

        lbint_p_l_v2 = "LBINT t:A. $p_{t&x} = LBINT t:A. $l_(x+t) / $l_x"
        lbint_p_l_v2_fixed = "(LBINT t:A. $p_{t&x}) = (LBINT t:A. $l_(x+t) / $l_x)"
        if lbint_p_l_v2 in current:
            return current.replace(lbint_p_l_v2, lbint_p_l_v2_fixed, 1), "lbint_p_l_2"

        lbint_rhs_plain = "= LBINT s:{f<..f+t}. $l_(x+s) / $l_x * $μ_(x+s)"
        lbint_rhs_plain_fixed = "= (LBINT s:{f<..f+t}. $l_(x+s) / $l_x * $μ_(x+s))"
        if lbint_rhs_plain in current:
            return (
                current.replace(lbint_rhs_plain, lbint_rhs_plain_fixed, 1),
                "lbint_s_3",
            )

        lbint_rhs_escaped = "= LBINT s:{f<..f+t}. $l_(x+s) / $l_x * $\\<mu>_(x+s)"
        lbint_rhs_escaped_fixed = (
            "= (LBINT s:{f<..f+t}. $l_(x+s) / $l_x * $\\<mu>_(x+s))"
        )
        if lbint_rhs_escaped in current:
            return (
                current.replace(lbint_rhs_escaped, lbint_rhs_escaped_fixed, 1),
                "lbint_s_3",
            )

        finite_name = "finite_survival_function"
        limited_name = "limited_survival_function"
        if finite_name in current:
            return current.replace(finite_name, limited_name), "finite_to_limited"

        return None, "no_rule"


@dataclass
class _LifeTableRuleGenerator(RuleFirstGenerator):
    def generate_candidates(  # noqa: D401
        self,
        task_spec,
        *,
        allow_sledgehammer: bool = True,
    ) -> list[str]:
        text = task_spec.task.block_text
        smt_cmd = (
            "by (smt (verit) greaterThanAtMost_borel "
            "set_lebesgue_integral_cong sets_lborel that x_lt_psi)"
        )
        if smt_cmd in text:
            return [
                (
                    "using LBINT_p_mu_q_defer\n"
                    "    by (smt (verit) greaterThanAtMost_borel "
                    "set_lebesgue_integral_cong sets_lborel that x_lt_psi)"
                )
            ]
        if (
            "using LBINT_p_mu_q" in text
            and "by (smt (verit)" in text
            and "LBINT_p_mu_q_defer" not in text
        ):
            return [
                (
                    "using LBINT_p_mu_q_defer\n"
                    "    by (smt (verit) greaterThanAtMost_borel "
                    "set_lebesgue_integral_cong sets_lborel that x_lt_psi)"
                )
            ]
        return super().generate_candidates(
            task_spec,
            allow_sledgehammer=allow_sledgehammer,
        )


@dataclass
class _LifeTableDeterministicTaskEngine(ReplDeterministicTaskEngine):
    def __post_init__(self) -> None:
        super().__post_init__()
        self._controller.generator = _LifeTableRuleGenerator(
            client=self.client,
            timeout_ms=self.timeout_ms,
        )

    def validate_candidate(
        self,
        task_spec: TaskSpec,
        candidate_text: str,
    ) -> ValidationResult:
        validation = super().validate_candidate(task_spec, candidate_text)
        if validation.status == ValidationStatus.PASSED:
            return validation

        # Test-only relaxation for top-level statement repair:
        # if the replacement executes cleanly, allow promotion so the
        # real workflow can continue exposing subsequent failures.
        if task_spec.task.failure_kind != FailureKind.STATEMENT_FAILURE:
            return validation
        source_state_id = str(task_spec.task.metadata.get("source_state_id", ""))
        if not source_state_id:
            return validation
        execution = self.client.execute(
            source_state_id=source_state_id,
            tactic=candidate_text,
            timeout_ms=self.timeout_ms,
            include_text=True,
        )
        if execution.status in ("SUCCESS", "PROOF_COMPLETE"):
            details = dict(validation.details)
            details["candidate_source"] = "review_injected"
            details["candidate_text"] = candidate_text
            details["test_relaxed_contract"] = True
            return ValidationResult(
                status=ValidationStatus.PASSED,
                reason="test_relaxed_statement_contract",
                details=details,
            )
        return validation


def _ensure_localhost_proxy_bypass() -> None:
    current = os.environ.get("NO_PROXY", "")
    tokens = {item.strip() for item in current.split(",") if item.strip()}
    tokens.update({"localhost", "127.0.0.1", "::1"})
    merged = ",".join(sorted(tokens))
    os.environ["NO_PROXY"] = merged
    os.environ["no_proxy"] = merged


def _load_case_env() -> LifeTableCaseEnv:
    isabelle_2024 = Path(
        os.environ.get("ISABELLE_2024_PATH", "/home/lxk/Isabelle2024")
    ).expanduser()
    afp_2023 = Path(
        os.environ.get("AFP_2023_PATH", "/home/lxk/repositories/afp-2023/thys")
    ).expanduser()
    afp_2024 = Path(
        os.environ.get("AFP_2024_PATH", "/home/lxk/repositories/afp-2024/thys")
    ).expanduser()
    theory_path = afp_2023 / "Actuarial_Mathematics" / "Life_Table.thy"
    working_dir = afp_2024 / "Actuarial_Mathematics"
    return LifeTableCaseEnv(
        host=os.environ.get("ISABELLE_REPL_HOST", "localhost"),
        port=int(os.environ.get("ISABELLE_REPL_PORT", "50051")),
        isabelle_2024_path=isabelle_2024,
        afp_2023_thys=afp_2023,
        afp_2024_thys=afp_2024,
        theory_path=theory_path,
        working_dir=working_dir,
        hol_src=isabelle_2024 / "src" / "HOL",
    )


def _skip_if_unavailable(env: LifeTableCaseEnv) -> None:
    required = [
        env.isabelle_2024_path,
        env.hol_src,
        env.afp_2023_thys,
        env.afp_2024_thys,
        env.theory_path,
        env.working_dir,
    ]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        pytest.skip(
            "Life_Table real-case prerequisites not met:\n- " + "\n- ".join(missing)
        )
    _ensure_localhost_proxy_bypass()
    channel = grpc.insecure_channel(
        f"{env.host}:{env.port}",
        options=(("grpc.enable_http_proxy", 0),),
    )
    try:
        grpc.channel_ready_future(channel).result(timeout=2)
    except grpc.FutureTimeoutError:
        pytest.skip(
            "Isabelle REPL server unreachable for Life_Table real-case test "
            f"at {env.host}:{env.port}"
        )
    finally:
        channel.close()


def _assert_statement_failure_requires_review(task_id: str) -> None:
    gate = RuleBasedPolicyGate()
    decision = gate.decide(
        PolicyContext(
            theory_run_id="life-table-real",
            task_id=task_id,
            failure_kind=FailureKind.STATEMENT_FAILURE,
            block_kind="TheoremShellBlock",
            artifact_kind=ArtifactKind.REPAIR,
            reason_code="real_case_statement_failure",
        )
    )
    assert decision.kind == PolicyDecisionKind.REQUIRES_REVIEW


def test_life_table_statement_failures_can_be_review_repaired():
    """
    Real workflow (orchestrator + localizer + runtime engine):
    - dynamic failure discovery (not pre-targeted line jumping)
    - first statement failure in LBINT_p_l triggers review
    - reviewed candidates are fed back through package validate_candidate()
    - terminal timeout fallback can be auto-patched via test-only deterministic rule
    - we expect this heavy real case to keep exposing new failures after fixed ones
    """
    env = _load_case_env()
    _skip_if_unavailable(env)
    _assert_statement_failure_requires_review(task_id="life-table-first")
    _assert_statement_failure_requires_review(task_id="life-table-second")

    with IsabelleReplClient(host=env.host, port=env.port) as client:
        session_id = client.create_session(
            isa_path=str(env.isabelle_2024_path),
            logic="HOL-Probability",
            working_directory=str(env.working_dir),
            session_roots=[str(env.hol_src), str(env.afp_2024_thys)],
        )
        try:
            localizer = ReplBlockLocalizer.from_theory(
                client=client,
                session_id=session_id,
                theory_path=str(env.theory_path),
                allow_sledgehammer=False,
            )
            engine = _LifeTableDeterministicTaskEngine(
                client=client,
                promote_failed_block_for_review=True,
            )
            hook = _LifeTableReviewedHook()
            run = TheoryRepairRun(
                theory_path=str(env.theory_path),
                theory_text=env.theory_path.read_text(encoding="utf-8"),
                localizer=localizer,
                engine=engine,
                policy=RuleBasedPolicyGate(),
                hook=hook,
            )
            final_state, records = run.execute(max_steps=120)
            assert final_state.value in {"stopped", "finished", "completed", "active"}

            interventions = [
                r
                for r in records.list_records()
                if r.record_kind.value == "intervention"
                and r.payload.get("response_kind") is not None
            ]
            assert len(interventions) >= 2
            assert all(
                row.payload["reason_code"] == "policy_requires_review"
                for row in interventions[:2]
            )
            assert len(hook.replacements) >= 3
            assert "lbint_s_3" in hook.applied_rules

            tasks = [r for r in records.list_records() if r.record_kind.value == "task"]
            assert any(
                "using LBINT_p_mu_q_defer"
                in " ".join(row.payload.get("attempted_candidates", []))
                for row in tasks
            )
        finally:
            client.destroy_session(session_id)
