"""
Integration tests against the AFP Completeness theory.

Based on the test scenario described in TASK2.md:

  Theory file: /home/lxk/repositories/afp-2025/thys/Completeness/Completeness.thy
  Session:     HOL  (with AFP session roots)
  Working dir: .../afp-2025/thys/Completeness/

  Key lemmas (1-indexed line numbers):
    131: lemma finite_subs: "finite (subs γ)"
           by (simp add: subs_def ...)
    134: lemma fansSubs: "fans subs"
           by (simp add: fans_def finite_subs)

Test scenario (from TASK2.md):
  1. init_state at line 134 → should be in PROOF mode, goal contains "fans subs"
  2. try "by simp" → may fail (fans_def not in default simp set)
  3. if (2) fails, try "by (simp add: fans_def finite_subs)" → must succeed
"""

import os

import pytest
from conftest import (
    AFP_PATH,
    COMPLETENESS_WORKDIR,
    HOL_SRC,
    ISABELLE_PATH,
    QUERY_OPTIMIZATION_WORKDIR,
)

COMPLETENESS_THY = os.path.join(AFP_PATH, "Completeness", "Completeness.thy")
QUERY_OPTIMIZATION_THY = os.path.join(
    AFP_PATH, "Query_Optimization", "Graph_Additions.thy"
)

# 1-indexed line numbers in Completeness.thy (verified in TASK2.md)
LINE_FINITE_SUBS = 131
LINE_FANS_SUBS = 134

pytestmark = [pytest.mark.integration, pytest.mark.integration_afp_heavy]


# ── Theory loading ─────────────────────────────────────────────────────────────


class TestLoadCompleteness:
    def test_load_returns_positive_command_count(self, client, hol_afp_session):
        count = client.load_theory(hol_afp_session, COMPLETENESS_THY)
        assert count > 0, "Expected at least one command in Completeness.thy"

    def test_load_is_idempotent(self, client, hol_afp_session):
        c1 = client.load_theory(hol_afp_session, COMPLETENESS_THY)
        c2 = client.load_theory(hol_afp_session, COMPLETENESS_THY)
        assert c1 == c2

    def test_afp_session_roots_enable_loading_from_fresh_session(self, client):
        session_id = client.create_session(
            isa_path=ISABELLE_PATH,
            logic="HOL",
            working_directory=COMPLETENESS_WORKDIR,
            session_roots=[HOL_SRC, AFP_PATH],
        )
        try:
            assert client.load_theory(session_id, COMPLETENESS_THY) > 0
        finally:
            client.destroy_session(session_id)


# ── ListTheoryCommands ─────────────────────────────────────────────────────────


class TestListCompleteness:
    def test_proof_stmts_include_fans_subs(self, client, hol_afp_session):
        client.load_theory(hol_afp_session, COMPLETENESS_THY)
        cmds = client.list_theory_commands(
            hol_afp_session, COMPLETENESS_THY, only_proof_stmts=True
        )
        texts = [c.text for c in cmds]
        assert any("fansSubs" in t for t in texts), (
            "Expected 'fansSubs' lemma in proof statements"
        )
        assert any("finite_subs" in t for t in texts), (
            "Expected 'finite_subs' lemma in proof statements"
        )

    def test_fans_subs_at_line_134(self, client, hol_afp_session):
        client.load_theory(hol_afp_session, COMPLETENESS_THY)
        cmds = client.list_theory_commands(
            hol_afp_session, COMPLETENESS_THY, only_proof_stmts=True
        )
        fans_cmd = next((c for c in cmds if "fansSubs" in c.text), None)
        assert fans_cmd is not None, "lemma fansSubs not found"
        assert fans_cmd.line == LINE_FANS_SUBS, (
            f"Expected fansSubs at line {LINE_FANS_SUBS}, got line {fans_cmd.line}"
        )

    def test_finite_subs_at_line_131(self, client, hol_afp_session):
        client.load_theory(hol_afp_session, COMPLETENESS_THY)
        cmds = client.list_theory_commands(
            hol_afp_session, COMPLETENESS_THY, only_proof_stmts=True
        )
        fsubs_cmd = next((c for c in cmds if "finite_subs" in c.text), None)
        assert fsubs_cmd is not None, "lemma finite_subs not found"
        assert fsubs_cmd.line == LINE_FINITE_SUBS, (
            f"Expected finite_subs at line {LINE_FINITE_SUBS},"
            f" got line {fsubs_cmd.line}"
        )


# ── InitState at fansSubs (line 134) ───────────────────────────────────────────


class TestInitStateFansSubs:
    def test_proof_mode_at_line_134(self, client, hol_afp_session):
        """After init_state at line 134, we are in PROOF mode for fansSubs."""
        client.load_theory(hol_afp_session, COMPLETENESS_THY)
        state = client.init_state(
            hol_afp_session, COMPLETENESS_THY, after_line=LINE_FANS_SUBS
        ).unwrap()
        try:
            assert state.mode == "PROOF", f"Expected PROOF mode, got {state.mode!r}"
            assert state.proof_level > 0
        finally:
            client.drop_state([state.state_id])

    def test_proof_state_text_contains_fans_subs_goal(self, client, hol_afp_session):
        """
        The proof state text at line 134 must mention the goal 'fans subs'.
        """
        client.load_theory(hol_afp_session, COMPLETENESS_THY)
        state = client.init_state(
            hol_afp_session, COMPLETENESS_THY, after_line=LINE_FANS_SUBS
        ).unwrap()
        try:
            info = client.get_state_info(state.state_id, include_text=True)
            assert info.proof_state_text, "Expected non-empty proof state text"
            text = info.proof_state_text
            assert "fans" in text and "subs" in text, (
                f"Expected 'fans subs' in proof state, got:\n{text}"
            )
        finally:
            client.drop_state([state.state_id])

    def test_init_by_after_command_fans_subs(self, client, hol_afp_session):
        """after_command positioning should also reach the fansSubs proof."""
        client.load_theory(hol_afp_session, COMPLETENESS_THY)
        state = client.init_state(
            hol_afp_session,
            COMPLETENESS_THY,
            after_command='lemma fansSubs: "fans subs"',
        ).unwrap()
        try:
            assert state.mode == "PROOF"
        finally:
            client.drop_state([state.state_id])


# ── Tactic attempts on fansSubs ────────────────────────────────────────────────


class TestFansSubsProof:
    def test_by_simp_then_simp_add(self, client, hol_afp_session):
        """
        TASK2.md scenario:
          1. Try 'by simp'
             - If it succeeds: good (simp can prove it without hints)
             - If it fails: expected, fans_def not in default simp set
          2. Try 'by (simp add: fans_def finite_subs)' — must succeed
        """
        client.load_theory(hol_afp_session, COMPLETENESS_THY)
        state = client.init_state(
            hol_afp_session, COMPLETENESS_THY, after_line=LINE_FANS_SUBS
        ).unwrap()
        try:
            r_simp = client.execute(state.state_id, "by simp")
            if r_simp.proof_is_finished():
                # Simp succeeded directly — acceptable
                return

            # Simp failed or made partial progress: try the complete proof
            assert r_simp.status in ("ERROR", "SUCCESS"), (
                f"Unexpected status from 'by simp': {r_simp.status}"
            )

            r_simp_add = client.execute(
                state.state_id, "by (simp add: fans_def finite_subs)"
            )
            assert r_simp_add.proof_is_finished(), (
                f"'by (simp add: fans_def finite_subs)' failed: "
                f"{r_simp_add.status} — {r_simp_add.error_msg}"
            )
        finally:
            client.drop_all_states(hol_afp_session)

    def test_correct_proof_from_theory_file(self, client, hol_afp_session):
        """
        The exact proof tactic from Completeness.thy must work:
          lemma fansSubs: "fans subs"
            by (simp add: fans_def finite_subs)
        """
        client.load_theory(hol_afp_session, COMPLETENESS_THY)
        state = client.init_state(
            hol_afp_session, COMPLETENESS_THY, after_line=LINE_FANS_SUBS
        ).unwrap()
        try:
            result = client.execute(
                state.state_id, "by (simp add: fans_def finite_subs)"
            )
            assert result.proof_is_finished(), (
                f"Proof failed: {result.status} — {result.error_msg}"
            )
            assert result.proof_level == 0
        finally:
            client.drop_all_states(hol_afp_session)

    def test_wrong_tactic_gives_clear_error(self, client, hol_afp_session):
        """A clearly wrong tactic must return ERROR with a non-empty message."""
        client.load_theory(hol_afp_session, COMPLETENESS_THY)
        state = client.init_state(
            hol_afp_session, COMPLETENESS_THY, after_line=LINE_FANS_SUBS
        ).unwrap()
        try:
            result = client.execute(
                state.state_id, "by (simp add: nonexistent_lemma_xyz)"
            )
            assert result.status == "ERROR"
            assert result.error_msg, "Expected a non-empty error message"
        finally:
            client.drop_all_states(hol_afp_session)


# ── Batch execution on fansSubs ────────────────────────────────────────────────


class TestFansSubsBatch:
    def test_execute_many_candidates(self, client, hol_afp_session):
        """
        Run several candidate tactics in one batch request.
        The correct one ('by (simp add: fans_def finite_subs)') must succeed.
        """
        client.load_theory(hol_afp_session, COMPLETENESS_THY)
        state = client.init_state(
            hol_afp_session, COMPLETENESS_THY, after_line=LINE_FANS_SUBS
        ).unwrap()
        tactics = [
            "by simp",  # may fail
            "by auto",  # may fail
            "by (simp add: fans_def finite_subs)",  # must succeed
            "by blast",  # may fail
        ]
        try:
            results = client.execute_many(state.state_id, tactics, drop_failed=True)
            assert len(results) == len(tactics)
            correct = results[2]  # "by (simp add: fans_def finite_subs)"
            assert correct.proof_is_finished(), (
                f"Expected PROOF_COMPLETE for correct tactic, got "
                f"{correct.status}: {correct.error_msg}"
            )
        finally:
            client.drop_all_states(hol_afp_session)


# ── finite_subs lemma (line 131) ───────────────────────────────────────────────


class TestFiniteSubs:
    def test_proof_mode_at_line_131(self, client, hol_afp_session):
        client.load_theory(hol_afp_session, COMPLETENESS_THY)
        state = client.init_state(
            hol_afp_session, COMPLETENESS_THY, after_line=LINE_FINITE_SUBS
        ).unwrap()
        try:
            assert state.mode == "PROOF"
        finally:
            client.drop_state([state.state_id])

    def test_finite_subs_correct_proof(self, client, hol_afp_session):
        """
        The exact proof from Completeness.thy:
          lemma finite_subs: "finite (subs γ)"
            by (simp add: subs_def subsFAtom_def subsFConj_def subsFAll_def
                          split_beta split: list.split formula.split signs.split)
        """
        client.load_theory(hol_afp_session, COMPLETENESS_THY)
        state = client.init_state(
            hol_afp_session, COMPLETENESS_THY, after_line=LINE_FINITE_SUBS
        ).unwrap()
        tactic = (
            "by (simp add: subs_def subsFAtom_def subsFConj_def subsFAll_def"
            " split_beta split: list.split formula.split signs.split)"
        )
        try:
            result = client.execute(state.state_id, tactic)
            assert result.proof_is_finished(), (
                f"finite_subs proof failed: {result.status} — {result.error_msg}"
            )
        finally:
            client.drop_all_states(hol_afp_session)


class TestCrossAfpRegression:
    def test_query_optimization_loads_with_cross_afp_session_dependency(
        self, client, query_optimization_afp_session
    ):
        count = client.load_theory(
            query_optimization_afp_session, QUERY_OPTIMIZATION_THY
        )
        assert count > 0, "Expected at least one command in Graph_Additions.thy"

    def test_query_optimization_session_roots_enable_loading_from_fresh_session(
        self, client
    ):
        session_id = client.create_session(
            isa_path=ISABELLE_PATH,
            logic="HOL",
            working_directory=QUERY_OPTIMIZATION_WORKDIR,
            session_roots=[HOL_SRC, AFP_PATH],
        )
        try:
            assert client.load_theory(session_id, QUERY_OPTIMIZATION_THY) > 0
        finally:
            client.destroy_session(session_id)

    def test_query_optimization_replay_runs_to_end(
        self, client, query_optimization_afp_session
    ):
        client.load_theory(query_optimization_afp_session, QUERY_OPTIMIZATION_THY)
        state = client.init_state(
            query_optimization_afp_session, QUERY_OPTIMIZATION_THY
        ).unwrap()
        try:
            assert state.proof_level == 0
            assert state.mode == "TOPLEVEL"
        finally:
            client.drop_state([state.state_id])
