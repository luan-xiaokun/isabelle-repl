from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from isabelle_repair.model import (
    Localizer,
    PolicyGate,
    RecordFactory,
    RecordStore,
    ReviewHook,
    RunMode,
    RunRecordKind,
    RunState,
    TaskEngine,
)
from isabelle_repair.records import (
    CompositeRecordStore,
    InMemoryRecordStore,
    JsonlRecordSink,
    RunRecordFactory,
)

from .observability import MultiEventLogger, default_stdout_logger, file_logger
from .orchestrator import TheoryRepairOrchestrator
from .working_snapshot import WorkingTheorySnapshot


@dataclass
class TheoryRepairRun:
    theory_path: str
    theory_text: str
    localizer: Localizer
    engine: TaskEngine
    policy: PolicyGate
    hook: ReviewHook

    def execute(
        self,
        *,
        max_steps: int = 100,
        run_id: str | None = None,
        record_store: RecordStore | None = None,
        record_factory: RecordFactory | None = None,
        records_path: Path | None = None,
        log_file: Path | None = None,
        logger: MultiEventLogger | None = None,
        run_mode: RunMode = RunMode.THEORY_WIDE,
        target_max_tasks: int | None = None,
    ) -> tuple[RunState, InMemoryRecordStore]:
        resolved_run_id = run_id or f"run-{uuid4().hex}"
        snapshot = WorkingTheorySnapshot(
            theory_path=self.theory_path,
            original_text=self.theory_text,
        )
        memory_store = InMemoryRecordStore()
        resolved_factory = record_factory or RunRecordFactory(
            theory_run_id=resolved_run_id
        )
        resolved_store = record_store or self._default_store(
            memory_store=memory_store,
            records_path=records_path
            or Path(".artifacts") / "repair_runs" / f"{resolved_run_id}.jsonl",
        )
        resolved_logger = logger or self._default_logger(
            run_id=resolved_run_id, log_file=log_file
        )
        resolved_store.append(
            resolved_factory.create(
                record_kind=RunRecordKind.RUN_METADATA,
                task_id=None,
                payload={
                    "theory_path": self.theory_path,
                    "theory_text_bytes": len(self.theory_text.encode("utf-8")),
                    "run_mode": run_mode.value,
                    "target_max_tasks": target_max_tasks,
                },
            )
        )
        orchestrator = TheoryRepairOrchestrator(
            theory_run_id=resolved_run_id,
            localizer=self.localizer,
            engine=self.engine,
            policy=self.policy,
            hook=self.hook,
            record_store=resolved_store,
            record_factory=resolved_factory,
            snapshot=snapshot,
            logger=resolved_logger,
            run_mode=run_mode,
            target_max_tasks=target_max_tasks,
        )
        final_state = orchestrator.run_until_terminal(max_steps=max_steps)
        self._export_patch_artifacts(
            run_id=resolved_run_id,
            final_state=final_state,
            snapshot=snapshot,
            records_path=records_path
            or Path(".artifacts") / "repair_runs" / f"{resolved_run_id}.jsonl",
            record_store=resolved_store,
            record_factory=resolved_factory,
        )
        return final_state, memory_store

    @staticmethod
    def _default_store(
        *,
        memory_store: InMemoryRecordStore,
        records_path: Path,
    ) -> CompositeRecordStore:
        return CompositeRecordStore(
            stores=[memory_store, JsonlRecordSink(path=records_path)]
        )

    @staticmethod
    def _default_logger(
        *,
        run_id: str,
        log_file: Path | None,
    ) -> MultiEventLogger:
        loggers = [default_stdout_logger(run_id)]
        if log_file is not None:
            loggers.append(file_logger(run_id, log_file))
        return MultiEventLogger(loggers=loggers)

    @staticmethod
    def _export_patch_artifacts(
        *,
        run_id: str,
        final_state: RunState,
        snapshot: WorkingTheorySnapshot,
        records_path: Path,
        record_store: RecordStore,
        record_factory: RecordFactory,
    ) -> None:
        if final_state not in (RunState.COMPLETED, RunState.FINISHED):
            return
        if not snapshot.applied_replacements:
            return

        output_dir = records_path.parent
        output_dir.mkdir(parents=True, exist_ok=True)
        patch_path = output_dir / f"{run_id}.patch"
        patch_json_path = output_dir / f"{run_id}.patch.json"
        patch_path.write_text(snapshot.export_unified_diff(), encoding="utf-8")
        patch_json_path.write_text(
            json.dumps(snapshot.export_json_patch(), ensure_ascii=True, indent=2),
            encoding="utf-8",
        )
        record_store.append(
            record_factory.create(
                record_kind=RunRecordKind.PROVENANCE,
                task_id=None,
                payload={
                    "linked_to": "patch_entries",
                    "unified_diff_path": str(patch_path),
                    "json_patch_path": str(patch_json_path),
                    "entries": snapshot.export_patch_provenance_links(),
                },
            )
        )
