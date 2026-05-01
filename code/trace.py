"""Per-row decision trace, written to run_trace.jsonl."""
import json
from pathlib import Path
from typing import Any


class TraceWriter:
    """Append-mode JSONL writer. Truncates the file at construction time."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text("", encoding="utf-8")

    def write(self, row_index: int, **fields: Any) -> None:
        rec = {"row": row_index, **fields}
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
