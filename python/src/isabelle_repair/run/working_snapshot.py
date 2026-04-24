from __future__ import annotations

from dataclasses import dataclass, field
from difflib import unified_diff
from typing import Any

from isabelle_repair.model import ArtifactKind


@dataclass
class WorkingTheorySnapshot:
    """Run-scoped mutable theory snapshot history."""

    theory_path: str
    original_text: str
    current_text: str | None = None
    applied_artifacts: list[tuple[ArtifactKind, str]] = field(default_factory=list)
    current_anchor_state_id: str | None = None
    command_cursor: int = -1
    mode: str | None = None
    proof_level: int | None = None
    applied_replacements: list[dict[str, Any]] = field(default_factory=list)
    last_failure_digest: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        if self.current_text is None:
            self.current_text = self.original_text
        if self.command_cursor < -1:
            raise ValueError("command_cursor must be >= -1")

    def set_anchor(
        self,
        *,
        state_id: str,
        command_cursor: int,
        mode: str,
        proof_level: int,
    ) -> None:
        if command_cursor < self.command_cursor:
            raise ValueError("command_cursor must be monotonic")
        self.current_anchor_state_id = state_id
        self.command_cursor = command_cursor
        self.mode = mode
        self.proof_level = proof_level

    def set_last_failure_digest(self, digest: dict[str, Any] | None) -> None:
        self.last_failure_digest = dict(digest) if digest is not None else None

    def apply_artifact(
        self,
        artifact_kind: ArtifactKind,
        artifact_text: str,
        *,
        task_id: str | None = None,
        command_line: int | None = None,
        original_text: str | None = None,
    ) -> None:
        if command_line is None:
            raise ValueError("command_line is required for patchable artifacts")
        self.applied_artifacts.append((artifact_kind, artifact_text))
        self.applied_replacements.append(
            {
                "patch_entry_id": f"pe-{len(self.applied_replacements) + 1}",
                "task_id": task_id,
                "command_line": command_line,
                "artifact_kind": artifact_kind.value,
                "replacement_text": artifact_text,
                "original_text": original_text,
                "artifact_record_id": None,
            }
        )
        self.current_text = self._render_patched_text()

    def replacement_for_line(self, command_line: int) -> str | None:
        for item in reversed(self.applied_replacements):
            if int(item.get("command_line", -1)) == command_line:
                return str(item.get("replacement_text", ""))
        return None

    def to_metadata(self) -> dict[str, Any]:
        return {
            "anchor_state_id": self.current_anchor_state_id,
            "command_cursor": self.command_cursor,
            "mode": self.mode,
            "proof_level": self.proof_level,
            "applied_replacement_count": len(self.applied_replacements),
            "last_failure_digest": self.last_failure_digest,
        }

    def attach_artifact_record_id(self, *, task_id: str, record_id: str) -> None:
        for item in reversed(self.applied_replacements):
            if (
                item.get("task_id") == task_id
                and item.get("artifact_record_id") is None
            ):
                item["artifact_record_id"] = record_id
                return

    def export_json_patch(self) -> dict[str, Any]:
        return {
            "format": "isabelle_repair_patch/v1",
            "theory_path": self.theory_path,
            "entries": [dict(entry) for entry in self.applied_replacements],
        }

    def export_patch_provenance_links(self) -> list[dict[str, Any]]:
        links: list[dict[str, Any]] = []
        for entry in self.applied_replacements:
            links.append(
                {
                    "patch_entry_id": entry.get("patch_entry_id"),
                    "task_id": entry.get("task_id"),
                    "artifact_record_id": entry.get("artifact_record_id"),
                }
            )
        return links

    def export_unified_diff(self) -> str:
        before = self.original_text
        after = self._render_patched_text()
        before_lines = before.splitlines(keepends=True)
        after_lines = after.splitlines(keepends=True)
        return "".join(
            unified_diff(
                before_lines,
                after_lines,
                fromfile=f"a/{self.theory_path}",
                tofile=f"b/{self.theory_path}",
                lineterm="",
            )
        )

    def _render_patched_text(self) -> str:
        lines = self.original_text.splitlines()
        by_line: dict[int, str] = {}
        for entry in self.applied_replacements:
            line = int(entry.get("command_line", 0))
            replacement = str(entry.get("replacement_text", ""))
            if line > 0:
                by_line[line] = replacement
        for line_number, replacement in sorted(by_line.items()):
            index = line_number - 1
            if 0 <= index < len(lines):
                lines[index] = replacement
        return "\n".join(lines) + ("\n" if self.original_text.endswith("\n") else "")
