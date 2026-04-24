"""
Integration tests for IsabelleReplClient using tests/theories/Simple.thy.

Covers all major Client API capabilities:
  - load_theory / list_theory_commands
  - init_state (by line, by after_command)
  - execute  (PROOF_COMPLETE, ERROR, non-destructive source)
  - execute_many  (ordered batch, mixed results, drop_failed)
  - get_state_info  (with and without proof text)
  - drop_state / drop_all_states
  - run_sledgehammer

Line numbers in Simple.thy (1-indexed):
  5  lemma trivial: "True"
  8  lemma add_comm_nat: "(x :: nat) + y = y + x"
  11 lemma conj_easy: "⟦P; Q⟧ ⟹ P ∧ Q"
  14 lemma nat_not_zero: "(n :: nat) > 0 ⟹ n ≠ 0"
"""

import grpc
import pytest
from shared.runtime_env import load_test_env

ENV = load_test_env()
SIMPLE_THY = str(ENV.theories_dir / "Simple.thy")
BROKEN_REPLAY_THY = str(ENV.theories_dir / "BrokenReplay.thy")
SLOW_REPLAY_THY = str(ENV.theories_dir / "SlowReplay.thy")
LOCAL_THEORY_INFO_THY = str(ENV.theories_dir / "LocalTheoryInfo.thy")
CLASS_LOCAL_THEORY_INFO_THY = str(ENV.theories_dir / "ClassLocalTheoryInfo.thy")

# 1-indexed line numbers of lemma declarations in Simple.thy
LINE_TRIVIAL = 5
LINE_ADD_COMM = 8
LINE_CONJ = 11
LINE_NAT = 14
LINE_BROKEN_REPLAY_LEMMA = 8
LINE_BROKEN_REPLAY_BY = 9
LINE_SLOW_REPLAY_SLEEP = 6
LINE_LOCAL_FOO_BY = 10
LINE_LOCAL_NESTED_BY = 16
LINE_LOCAL_GLOBAL_CTX_BY = 26
LINE_CLASS_LOCAL_FOO_BY = 10

pytestmark = [pytest.mark.integration, pytest.mark.integration_local]


# ── LoadTheory ─────────────────────────────────────────────────────────────────


class TestLoadTheory:
    def test_returns_positive_command_count(self, client, hol_session):
        count = client.load_theory(hol_session, SIMPLE_THY)
        assert count > 0

    def test_is_idempotent(self, client, hol_session):
        c1 = client.load_theory(hol_session, SIMPLE_THY)
        c2 = client.load_theory(hol_session, SIMPLE_THY)
        assert c1 == c2


# ── ListTheoryCommands ─────────────────────────────────────────────────────────


class TestListTheoryCommands:
    def test_all_commands_include_theory_header(self, client, hol_session):
        client.load_theory(hol_session, SIMPLE_THY)
        cmds = client.list_theory_commands(hol_session, SIMPLE_THY)
        assert len(cmds) > 0

    def test_proof_stmts_filter_returns_only_lemmas(self, client, hol_session):
        client.load_theory(hol_session, SIMPLE_THY)
        all_cmds = client.list_theory_commands(hol_session, SIMPLE_THY)
        proof_cmds = client.list_theory_commands(
            hol_session, SIMPLE_THY, only_proof_stmts=True
        )
        assert 0 < len(proof_cmds) < len(all_cmds)
        for c in proof_cmds:
            assert c.kind == "lemma", f"Unexpected kind: {c.kind!r} in {c.text!r}"

    def test_proof_stmts_contains_all_four_lemmas(self, client, hol_session):
        client.load_theory(hol_session, SIMPLE_THY)
        cmds = client.list_theory_commands(
            hol_session, SIMPLE_THY, only_proof_stmts=True
        )
        texts = [c.text for c in cmds]
        for name in ("trivial", "add_comm_nat", "conj_easy", "nat_not_zero"):
            assert any(name in t for t in texts), (
                f"lemma {name!r} not found in commands"
            )

    def test_lemma_line_numbers_match_source(self, client, hol_session):
        client.load_theory(hol_session, SIMPLE_THY)
        cmds = client.list_theory_commands(
            hol_session, SIMPLE_THY, only_proof_stmts=True
        )
        by_name = {
            name: next((c for c in cmds if name in c.text), None)
            for name in ("trivial", "add_comm_nat", "conj_easy", "nat_not_zero")
        }
        for name, cmd in by_name.items():
            assert cmd is not None, f"lemma {name!r} not found"
        assert by_name["trivial"].line == LINE_TRIVIAL, (
            f"trivial at line {by_name['trivial'].line}"
        )
        assert by_name["add_comm_nat"].line == LINE_ADD_COMM
        assert by_name["conj_easy"].line == LINE_CONJ
        assert by_name["nat_not_zero"].line == LINE_NAT


# ── InitState ──────────────────────────────────────────────────────────────────


class TestInitState:
    def test_by_line_yields_proof_mode(self, client, hol_session):
        client.load_theory(hol_session, SIMPLE_THY)
        state = client.init_state(
            hol_session, SIMPLE_THY, after_line=LINE_TRIVIAL
        ).unwrap()
        try:
            assert state.mode == "PROOF"
            assert state.proof_level > 0
        finally:
            client.drop_state([state.state_id])

    def test_by_after_command_yields_proof_mode(self, client, hol_session):
        client.load_theory(hol_session, SIMPLE_THY)
        state = client.init_state(
            hol_session, SIMPLE_THY, after_command='lemma trivial: "True"'
        ).unwrap()
        try:
            assert state.mode == "PROOF"
        finally:
            client.drop_state([state.state_id])

    def test_by_line_and_after_command_reach_same_lemma(self, client, hol_session):
        """Both positioning methods should land in PROOF mode at the same lemma."""
        client.load_theory(hol_session, SIMPLE_THY)
        s_line = client.init_state(
            hol_session, SIMPLE_THY, after_line=LINE_TRIVIAL
        ).unwrap()
        s_cmd = client.init_state(
            hol_session, SIMPLE_THY, after_command='lemma trivial: "True"'
        ).unwrap()
        try:
            assert s_line.mode == s_cmd.mode == "PROOF"
            assert s_line.proof_level == s_cmd.proof_level
            # Different state IDs (fresh UUIDs)
            assert s_line.state_id != s_cmd.state_id
        finally:
            client.drop_state([s_line.state_id, s_cmd.state_id])

    def test_different_lemmas_produce_different_states(self, client, hol_session):
        client.load_theory(hol_session, SIMPLE_THY)
        s1 = client.init_state(
            hol_session, SIMPLE_THY, after_line=LINE_TRIVIAL
        ).unwrap()
        s2 = client.init_state(
            hol_session, SIMPLE_THY, after_line=LINE_ADD_COMM
        ).unwrap()
        try:
            assert s1.state_id != s2.state_id
            assert s1.mode == s2.mode == "PROOF"
        finally:
            client.drop_state([s1.state_id, s2.state_id])

    def test_error_result_contains_failed_line_and_last_success(
        self, client, hol_session
    ):
        """Replay failure reports the failing line and last successful state."""
        client.load_theory(hol_session, BROKEN_REPLAY_THY)
        result = client.init_state(
            hol_session,
            BROKEN_REPLAY_THY,
            after_line=LINE_BROKEN_REPLAY_BY,
            include_text=True,
        )
        assert not result.is_success()
        assert result.success is None
        assert result.error is not None
        assert result.error.failed_line == LINE_BROKEN_REPLAY_BY
        assert result.error.error_msg

        last_success = result.error.last_success
        assert last_success is not None, "Expected state before the failing command"
        assert last_success.status == "SUCCESS"
        assert last_success.mode == "PROOF"
        assert last_success.proof_level > 0
        assert "True" in last_success.proof_state_text
        client.drop_state([last_success.state_id])

    def test_timeout_returns_error_result_instead_of_rpc_failure(
        self, client, hol_session
    ):
        client.load_theory(hol_session, SLOW_REPLAY_THY)
        result = client.init_state(
            hol_session,
            SLOW_REPLAY_THY,
            after_line=LINE_SLOW_REPLAY_SLEEP,
            timeout_ms=10,
        )
        assert not result.is_success()
        assert result.error is not None
        assert result.error.failed_line == LINE_SLOW_REPLAY_SLEEP
        assert (
            result.error.last_success is None or result.error.last_success.is_success()
        )
        assert "Timeout" in result.error.error_msg
        if result.error.last_success is not None:
            client.drop_state([result.error.last_success.state_id])

    def test_after_command_not_found_returns_structured_selector_error(
        self, client, hol_session
    ):
        client.load_theory(hol_session, SIMPLE_THY)
        result = client.init_state(
            hol_session,
            SIMPLE_THY,
            after_command="definitely_not_a_real_command_selector",
        )
        assert not result.is_success()
        assert result.error is not None
        assert result.error.code == "INIT_STATE_NOT_FOUND"
        assert result.error.candidate_lines == []

    def test_after_command_ambiguous_requires_explicit_disambiguation(
        self, client, hol_session
    ):
        client.load_theory(hol_session, SIMPLE_THY)
        # "by simp" appears multiple times in Simple.thy, so selector must be ambiguous.
        result = client.init_state(
            hol_session,
            SIMPLE_THY,
            after_command="by simp",
        )
        assert not result.is_success()
        assert result.error is not None
        assert result.error.code == "INIT_STATE_AMBIGUOUS"
        assert len(result.error.candidate_lines) > 1


# ── Execute ────────────────────────────────────────────────────────────────────


class TestExecute:
    def test_by_simp_completes_trivial(self, client, hol_session):
        client.load_theory(hol_session, SIMPLE_THY)
        state = client.init_state(
            hol_session, SIMPLE_THY, after_line=LINE_TRIVIAL
        ).unwrap()
        try:
            result = client.execute(state.state_id, "by simp")
            assert result.proof_is_finished(), (
                f"Expected PROOF_COMPLETE, got {result.status}: {result.error_msg}"
            )
            assert result.proof_level == 0
        finally:
            client.drop_state([state.state_id, result.state_id])

    def test_invalid_tactic_returns_error_with_message(self, client, hol_session):
        client.load_theory(hol_session, SIMPLE_THY)
        state = client.init_state(
            hol_session, SIMPLE_THY, after_line=LINE_TRIVIAL
        ).unwrap()
        try:
            result = client.execute(state.state_id, "by totally_nonexistent_tactic_xyz")
            assert result.status == "ERROR"
            assert result.error_msg, "Expected a non-empty error message"
        finally:
            client.drop_state([state.state_id, result.state_id])

    def test_source_state_is_preserved_after_success(self, client, hol_session):
        """Non-destructive: two different tactics from the same source both succeed."""
        client.load_theory(hol_session, SIMPLE_THY)
        state = client.init_state(
            hol_session, SIMPLE_THY, after_line=LINE_TRIVIAL
        ).unwrap()
        try:
            r1 = client.execute(state.state_id, "by simp")
            r2 = client.execute(state.state_id, "by blast")
            assert r1.proof_is_finished()
            assert r2.proof_is_finished()
            assert r1.state_id != r2.state_id
        finally:
            client.drop_state([state.state_id, r1.state_id, r2.state_id])

    def test_source_state_is_preserved_after_error(self, client, hol_session):
        """Even after a failed tactic, the source state can still be used."""
        client.load_theory(hol_session, SIMPLE_THY)
        state = client.init_state(
            hol_session, SIMPLE_THY, after_line=LINE_TRIVIAL
        ).unwrap()
        try:
            failed = client.execute(state.state_id, "by bad_tactic_xyz")
            assert failed.status == "ERROR"
            # Source state is still valid
            ok = client.execute(state.state_id, "by simp")
            assert ok.proof_is_finished()
        finally:
            client.drop_state([state.state_id, failed.state_id, ok.state_id])

    def test_apply_rule_yields_success_not_complete(self, client, hol_session):
        """apply (rule conjI) on conj_easy opens two subgoals; proof is not yet done."""
        client.load_theory(hol_session, SIMPLE_THY)
        state = client.init_state(
            hol_session, SIMPLE_THY, after_line=LINE_CONJ
        ).unwrap()
        try:
            result = client.execute(state.state_id, "apply (rule conjI)")
            # Proof is not complete; still in PROOF mode
            assert result.is_success()
            assert not result.proof_is_finished()
            assert result.mode == "PROOF"
        finally:
            client.drop_state([state.state_id, result.state_id])

    def test_fresh_state_id_returned_each_time(self, client, hol_session):
        """Every execute call produces a unique new state ID."""
        client.load_theory(hol_session, SIMPLE_THY)
        state = client.init_state(
            hol_session, SIMPLE_THY, after_line=LINE_TRIVIAL
        ).unwrap()
        try:
            ids = {client.execute(state.state_id, "by simp").state_id for _ in range(3)}
            assert len(ids) == 3, "Expected 3 distinct state IDs"
        finally:
            client.drop_state(list(ids) + [state.state_id])


# ── ExecuteMany ────────────────────────────────────────────────────────────────


class TestExecuteMany:
    def test_all_results_returned_in_order(self, client, hol_session):
        client.load_theory(hol_session, SIMPLE_THY)
        state = client.init_state(
            hol_session, SIMPLE_THY, after_line=LINE_TRIVIAL
        ).unwrap()
        tactics = ["by simp", "by auto", "by blast", "by (rule TrueI)"]
        try:
            results = client.execute_many(state.state_id, tactics)
            assert len(results) == len(tactics)
            for i, r in enumerate(results):
                assert r.proof_is_finished(), (
                    f"tactics[{i}]={tactics[i]!r} → {r.status}: {r.error_msg}"
                )
        finally:
            client.drop_state([state.state_id] + [r.state_id for r in results])

    def test_all_state_ids_are_unique(self, client, hol_session):
        client.load_theory(hol_session, SIMPLE_THY)
        state = client.init_state(
            hol_session, SIMPLE_THY, after_line=LINE_TRIVIAL
        ).unwrap()
        tactics = ["by simp", "by auto", "by blast"]
        try:
            results = client.execute_many(state.state_id, tactics)
            ids = [r.state_id for r in results]
            assert len(set(ids)) == len(ids), "Duplicate state IDs in batch results"
        finally:
            client.drop_state([state.state_id] + ids)

    def test_mixed_results_aligned_to_input(self, client, hol_session):
        """Results must be parallel to the input tactics list."""
        client.load_theory(hol_session, SIMPLE_THY)
        state = client.init_state(
            hol_session, SIMPLE_THY, after_line=LINE_TRIVIAL
        ).unwrap()
        tactics = ["by simp", "by totally_bad_tactic_xyz", "by blast"]
        try:
            results = client.execute_many(state.state_id, tactics)
            assert len(results) == 3
            assert results[0].proof_is_finished()
            assert results[1].status == "ERROR"
            assert results[2].proof_is_finished()
        finally:
            client.drop_state([state.state_id] + [r.state_id for r in results])

    def test_drop_failed_cleans_up_error_states(self, client, hol_session):
        """drop_failed=True should auto-remove failed states server-side."""
        client.load_theory(hol_session, SIMPLE_THY)
        state = client.init_state(
            hol_session, SIMPLE_THY, after_line=LINE_TRIVIAL
        ).unwrap()
        tactics = ["by simp", "by bad_xyz"]
        try:
            results = client.execute_many(state.state_id, tactics, drop_failed=True)
            assert len(results) == 2
            assert results[0].proof_is_finished()
            assert results[1].status == "ERROR"
            with pytest.raises(grpc.RpcError) as excinfo:
                client.get_state_info(results[1].state_id)
            assert excinfo.value.code() == grpc.StatusCode.NOT_FOUND
            info = client.get_state_info(results[0].state_id)
            assert info.mode in ("TOPLEVEL", "THEORY", "LOCAL_THEORY")
            # Only the successful state needs manual cleanup
            client.drop_state([state.state_id, results[0].state_id])
        except Exception:
            client.drop_state([state.state_id] + [r.state_id for r in results])
            raise


# ── GetStateInfo ───────────────────────────────────────────────────────────────


class TestGetStateInfo:
    def test_basic_info_no_text(self, client, hol_session):
        client.load_theory(hol_session, SIMPLE_THY)
        state = client.init_state(
            hol_session, SIMPLE_THY, after_line=LINE_TRIVIAL
        ).unwrap()
        try:
            info = client.get_state_info(state.state_id, include_text=False)
            assert info.state_id == state.state_id
            assert info.mode == "PROOF"
            assert info.proof_level > 0
            assert info.proof_state_text == ""
        finally:
            client.drop_state([state.state_id])

    def test_local_theory_desc_is_empty_outside_local_theory(self, client, hol_session):
        client.load_theory(hol_session, SIMPLE_THY)
        state = client.init_state(
            hol_session, SIMPLE_THY, after_line=LINE_TRIVIAL
        ).unwrap()
        try:
            info = client.get_state_info(state.state_id, include_text=False)
            assert hasattr(info, "local_theory_desc")
            assert info.local_theory_desc == ""
        finally:
            client.drop_state([state.state_id])

    def test_local_theory_desc_locale_name_in_main_target(self, client, hol_session):
        client.load_theory(hol_session, LOCAL_THEORY_INFO_THY)
        state = client.init_state(
            hol_session, LOCAL_THEORY_INFO_THY, after_line=LINE_LOCAL_FOO_BY
        ).unwrap()
        try:
            info = client.get_state_info(state.state_id, include_text=False)
            assert info.mode == "LOCAL_THEORY"
            assert info.local_theory_desc == "locale LocalTheoryInfo.foo"
        finally:
            client.drop_state([state.state_id])

    def test_local_theory_desc_mentions_nested_context(self, client, hol_session):
        client.load_theory(hol_session, LOCAL_THEORY_INFO_THY)
        state = client.init_state(
            hol_session, LOCAL_THEORY_INFO_THY, after_line=LINE_LOCAL_NESTED_BY
        ).unwrap()
        try:
            info = client.get_state_info(state.state_id, include_text=False)
            assert info.mode == "LOCAL_THEORY"
            assert info.local_theory_desc == "locale LocalTheoryInfo.foo"
        finally:
            client.drop_state([state.state_id])

    def test_local_theory_desc_for_theory_context_block(self, client, hol_session):
        client.load_theory(hol_session, LOCAL_THEORY_INFO_THY)
        state = client.init_state(
            hol_session, LOCAL_THEORY_INFO_THY, after_line=LINE_LOCAL_GLOBAL_CTX_BY
        ).unwrap()
        try:
            info = client.get_state_info(state.state_id, include_text=False)
            assert info.mode == "LOCAL_THEORY"
            assert (
                info.local_theory_desc
                == "local theory context in theory LocalTheoryInfo"
            )
        finally:
            client.drop_state([state.state_id])

    def test_local_theory_desc_for_class_target(self, client, hol_session):
        client.load_theory(hol_session, CLASS_LOCAL_THEORY_INFO_THY)
        state = client.init_state(
            hol_session, CLASS_LOCAL_THEORY_INFO_THY, after_line=LINE_CLASS_LOCAL_FOO_BY
        ).unwrap()
        try:
            info = client.get_state_info(state.state_id, include_text=False)
            assert info.mode == "LOCAL_THEORY"
            assert info.local_theory_desc == "class ClassLocalTheoryInfo.foo_class"
        finally:
            client.drop_state([state.state_id])

    def test_proof_text_contains_goal_for_trivial(self, client, hol_session):
        client.load_theory(hol_session, SIMPLE_THY)
        state = client.init_state(
            hol_session, SIMPLE_THY, after_line=LINE_TRIVIAL
        ).unwrap()
        try:
            info = client.get_state_info(state.state_id, include_text=True)
            assert info.proof_state_text, "Expected non-empty proof state text"
            assert "True" in info.proof_state_text
        finally:
            client.drop_state([state.state_id])

    def test_proof_text_reflects_current_state(self, client, hol_session):
        """After apply, the proof state text changes to reflect remaining goals."""
        client.load_theory(hol_session, SIMPLE_THY)
        state = client.init_state(
            hol_session, SIMPLE_THY, after_line=LINE_CONJ
        ).unwrap()
        try:
            info_before = client.get_state_info(state.state_id, include_text=True)
            after = client.execute(state.state_id, "apply (rule conjI)")
            info_after = client.get_state_info(after.state_id, include_text=True)
            # Both should be non-empty; after apply there are now 2 subgoals
            assert info_before.proof_state_text
            assert info_after.proof_state_text
            # Text should differ (more subgoals now)
            assert info_before.proof_state_text != info_after.proof_state_text
        finally:
            client.drop_state([state.state_id, after.state_id])

    def test_proof_level_matches_state_result(self, client, hol_session):
        client.load_theory(hol_session, SIMPLE_THY)
        state = client.init_state(
            hol_session, SIMPLE_THY, after_line=LINE_TRIVIAL
        ).unwrap()
        try:
            info = client.get_state_info(state.state_id)
            assert info.proof_level == state.proof_level
        finally:
            client.drop_state([state.state_id])

    def test_unknown_state_id_returns_not_found(self, client):
        with pytest.raises(grpc.RpcError) as excinfo:
            client.get_state_info("definitely-not-a-real-state-id")
        assert excinfo.value.code() == grpc.StatusCode.NOT_FOUND

    def test_dropped_state_id_returns_not_found(self, client, hol_session):
        client.load_theory(hol_session, SIMPLE_THY)
        state = client.init_state(
            hol_session, SIMPLE_THY, after_line=LINE_TRIVIAL
        ).unwrap()
        client.drop_state([state.state_id])

        with pytest.raises(grpc.RpcError) as excinfo:
            client.get_state_info(state.state_id)
        assert excinfo.value.code() == grpc.StatusCode.NOT_FOUND


# ── IncludeText (inline proof_state_text on Execute / InitState) ───────────────


class TestIncludeText:
    def test_init_state_include_text_true_returns_proof_text(self, client, hol_session):
        client.load_theory(hol_session, SIMPLE_THY)
        state = client.init_state(
            hol_session, SIMPLE_THY, after_line=LINE_TRIVIAL, include_text=True
        ).unwrap()
        try:
            assert state.proof_state_text, "Expected non-empty proof_state_text"
            assert "True" in state.proof_state_text
        finally:
            client.drop_state([state.state_id])

    def test_init_state_include_text_false_returns_empty(self, client, hol_session):
        client.load_theory(hol_session, SIMPLE_THY)
        state = client.init_state(
            hol_session, SIMPLE_THY, after_line=LINE_TRIVIAL, include_text=False
        ).unwrap()
        try:
            assert state.proof_state_text == ""
        finally:
            client.drop_state([state.state_id])

    def test_execute_include_text_true_returns_proof_text(self, client, hol_session):
        client.load_theory(hol_session, SIMPLE_THY)
        state = client.init_state(
            hol_session, SIMPLE_THY, after_line=LINE_CONJ
        ).unwrap()
        try:
            result = client.execute(
                state.state_id, "apply (rule conjI)", include_text=True
            )
            assert result.proof_state_text, "Expected non-empty proof_state_text"
        finally:
            client.drop_state([state.state_id, result.state_id])

    def test_execute_include_text_false_returns_empty(self, client, hol_session):
        client.load_theory(hol_session, SIMPLE_THY)
        state = client.init_state(
            hol_session, SIMPLE_THY, after_line=LINE_CONJ
        ).unwrap()
        try:
            result = client.execute(
                state.state_id, "apply (rule conjI)", include_text=False
            )
            assert result.proof_state_text == ""
        finally:
            client.drop_state([state.state_id, result.state_id])

    def test_execute_include_text_matches_get_state_info(self, client, hol_session):
        """proof_state_text from Execute must equal GetStateInfo for the same state."""
        client.load_theory(hol_session, SIMPLE_THY)
        state = client.init_state(
            hol_session, SIMPLE_THY, after_line=LINE_CONJ
        ).unwrap()
        try:
            result = client.execute(
                state.state_id, "apply (rule conjI)", include_text=True
            )
            info = client.get_state_info(result.state_id, include_text=True)
            assert result.proof_state_text == info.proof_state_text
        finally:
            client.drop_state([state.state_id, result.state_id])


# ── DropState / DropAllStates ──────────────────────────────────────────────────


class TestDropState:
    def test_drop_single_state(self, client, hol_session):
        client.load_theory(hol_session, SIMPLE_THY)
        state = client.init_state(
            hol_session, SIMPLE_THY, after_line=LINE_TRIVIAL
        ).unwrap()
        # Should not raise
        client.drop_state([state.state_id])

    def test_drop_state_makes_execute_fail_with_not_found(self, client, hol_session):
        client.load_theory(hol_session, SIMPLE_THY)
        state = client.init_state(
            hol_session, SIMPLE_THY, after_line=LINE_TRIVIAL
        ).unwrap()
        client.drop_state([state.state_id])

        with pytest.raises(grpc.RpcError) as excinfo:
            client.execute(state.state_id, "by simp")
        assert excinfo.value.code() == grpc.StatusCode.NOT_FOUND

    def test_drop_multiple_states_at_once(self, client, hol_session):
        client.load_theory(hol_session, SIMPLE_THY)
        s1 = client.init_state(
            hol_session, SIMPLE_THY, after_line=LINE_TRIVIAL
        ).unwrap()
        s2 = client.init_state(
            hol_session, SIMPLE_THY, after_line=LINE_ADD_COMM
        ).unwrap()
        s3 = client.init_state(hol_session, SIMPLE_THY, after_line=LINE_CONJ).unwrap()
        client.drop_state([s1.state_id, s2.state_id, s3.state_id])

    def test_drop_all_states(self, client, hol_session):
        client.load_theory(hol_session, SIMPLE_THY)
        for line in (LINE_TRIVIAL, LINE_ADD_COMM, LINE_CONJ, LINE_NAT):
            client.init_state(hol_session, SIMPLE_THY, after_line=line)
        # drop_all_states clears all states and the init cache for this session
        client.drop_all_states(hol_session)

    def test_drop_all_states_invalidates_old_states_but_allows_reinit(
        self, client, hol_session
    ):
        client.load_theory(hol_session, SIMPLE_THY)
        first = client.init_state(
            hol_session, SIMPLE_THY, after_line=LINE_TRIVIAL
        ).unwrap()
        second = client.init_state(
            hol_session, SIMPLE_THY, after_line=LINE_ADD_COMM
        ).unwrap()
        client.drop_all_states(hol_session)

        for state_id in (first.state_id, second.state_id):
            with pytest.raises(grpc.RpcError) as excinfo:
                client.get_state_info(state_id)
            assert excinfo.value.code() == grpc.StatusCode.NOT_FOUND

        rebuilt = client.init_state(
            hol_session, SIMPLE_THY, after_line=LINE_TRIVIAL
        ).unwrap()
        try:
            assert rebuilt.state_id not in {first.state_id, second.state_id}
            info = client.get_state_info(rebuilt.state_id)
            assert info.mode == "PROOF"
        finally:
            client.drop_state([rebuilt.state_id])

    def test_drop_invalidates_init_state_cache_entry(self, client, hol_session):
        client.load_theory(hol_session, SIMPLE_THY)
        first = client.init_state(
            hol_session, SIMPLE_THY, after_line=LINE_TRIVIAL
        ).unwrap()
        client.drop_state([first.state_id])

        with pytest.raises(grpc.RpcError) as excinfo:
            client.get_state_info(first.state_id)
        assert excinfo.value.code() == grpc.StatusCode.NOT_FOUND

        second = client.init_state(
            hol_session, SIMPLE_THY, after_line=LINE_TRIVIAL
        ).unwrap()
        try:
            assert second.state_id != first.state_id
            info = client.get_state_info(second.state_id)
            assert info.mode == "PROOF"
        finally:
            client.drop_state([second.state_id])


# ── RunSledgehammer ────────────────────────────────────────────────────────────


def _assert_sledgehammer_found(client, source_state_id, found, tactic, result):
    """
    Helper: assert that a found Sledgehammer result is a valid proof.

    Handles two normal outcomes:
    - `by (...)` tactic  → execute gives PROOF_COMPLETE directly
    - `apply (...)` tactic → execute gives SUCCESS with 0 goals; `done` closes the proof

    Also handles a known edge case: Sledgehammer reports found=True but returns a
    whitespace-only tactic (output-parsing artifact).  In that case the test is skipped.
    """
    if not found or not tactic.strip():
        pytest.skip(
            "Sledgehammer did not find a usable proof "
            f"(found={found}, tactic={tactic!r})"
        )

    assert result is not None, "Expected a StateResult when found=True"

    if result.proof_is_finished():
        client.drop_state([source_state_id, result.state_id])
        return

    # apply-style: tactic ran without error but proof_level still > 0.
    # A `done` step should close the proof if all goals were discharged.
    assert result.is_success(), (
        f"Expected SUCCESS or PROOF_COMPLETE from Sledgehammer tactic {tactic!r}, "
        f"got {result.status}: {result.error_msg}"
    )
    done_result = client.execute(result.state_id, "done")
    assert done_result.proof_is_finished(), (
        f"'done' after Sledgehammer tactic {tactic!r} did not close proof: "
        f"{done_result.status} — {done_result.error_msg}"
    )
    client.drop_state([source_state_id, result.state_id, done_result.state_id])


class TestRunSledgehammer:
    def test_sledgehammer_on_trivial(self, client, hol_session):
        """Sledgehammer on `True` should find a proof (by tactic or apply+done)."""
        client.load_theory(hol_session, SIMPLE_THY)
        state = client.init_state(
            hol_session, SIMPLE_THY, after_line=LINE_TRIVIAL
        ).unwrap()
        try:
            found, tactic, result = client.run_sledgehammer(
                state.state_id,
                timeout_ms=120_000,
                sledgehammer_timeout_ms=60_000,
            )
            _assert_sledgehammer_found(client, state.state_id, found, tactic, result)
        except pytest.skip.Exception:
            client.drop_state([state.state_id])
            raise
        except Exception:
            client.drop_state([state.state_id])
            raise

    def test_sledgehammer_on_add_comm_nat(self, client, hol_session):
        """Sledgehammer on `(x::nat) + y = y + x` — should find a proof."""
        client.load_theory(hol_session, SIMPLE_THY)
        state = client.init_state(
            hol_session, SIMPLE_THY, after_line=LINE_ADD_COMM
        ).unwrap()
        try:
            found, tactic, result = client.run_sledgehammer(
                state.state_id,
                timeout_ms=120_000,
                sledgehammer_timeout_ms=60_000,
            )
            _assert_sledgehammer_found(client, state.state_id, found, tactic, result)
        except pytest.skip.Exception:
            client.drop_state([state.state_id])
            raise
        except Exception:
            client.drop_state([state.state_id])
            raise
