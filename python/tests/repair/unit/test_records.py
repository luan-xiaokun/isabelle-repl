from __future__ import annotations

import json

from isabelle_repair.model import RunRecordKind
from isabelle_repair.records import (
    CompositeRecordStore,
    InMemoryRecordStore,
    JsonlRecordSink,
    RunRecordFactory,
)


def test_records_are_append_only_and_monotonic_sequence():
    factory = RunRecordFactory(theory_run_id="run-1")
    store = InMemoryRecordStore()
    r1 = factory.create(RunRecordKind.TASK, "task-1", {"outcome": "accepted"})
    r2 = factory.create(
        RunRecordKind.PROVENANCE,
        "task-1",
        {"linked_to": "task/artifact/policy/continuation"},
    )
    store.append(r1)
    store.append(r2)

    records = store.list_records()
    assert [r.run_local_sequence_number for r in records] == [1, 2]
    assert records[1].record_kind == RunRecordKind.PROVENANCE
    assert all(r.schema_version == "v1.5" for r in records)


def test_composite_store_dual_writes_jsonl_and_memory(tmp_path):
    factory = RunRecordFactory(theory_run_id="run-2")
    memory = InMemoryRecordStore()
    jsonl_path = tmp_path / "records.jsonl"
    store = CompositeRecordStore(stores=[memory, JsonlRecordSink(path=jsonl_path)])
    for idx in range(3):
        store.append(
            factory.create(
                RunRecordKind.TASK,
                "task-a",
                {"index": idx},
            )
        )

    assert len(memory.list_records()) == 3
    lines = jsonl_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 3
    parsed = [json.loads(line) for line in lines]
    assert [row["run_local_sequence_number"] for row in parsed] == [1, 2, 3]
    assert all(row["schema_version"] == "v1.5" for row in parsed)
