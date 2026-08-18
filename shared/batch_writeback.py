# -*- coding: utf-8 -*-
"""Optimized batch Google Sheet writeback buffer.

The legacy batch flow is intentionally untouched. New/optimized flows can stage
row results here and flush them through the existing shared.gsheet.update_sheet_rows
implementation. Default checkpoint size is 10 rows.
"""

from __future__ import annotations

from typing import Dict, Optional

from shared.gsheet import update_sheet_rows

DEFAULT_CHECKPOINT_SIZE = 10


class BatchWritebackBuffer:
    """Accumulate Sheet row updates and flush every N rows.

    Each Google Sheet row is written at most once per checkpoint. Adding another
    payload for the same row merges fields until the next flush.
    """

    def __init__(self, worksheet, checkpoint_size: int = DEFAULT_CHECKPOINT_SIZE, logger=None):
        self.worksheet = worksheet
        self.checkpoint_size = max(1, int(checkpoint_size or DEFAULT_CHECKPOINT_SIZE))
        self.logger = logger
        self.pending: Dict[int, dict] = {}
        self.total_flushed_rows = 0
        self.flush_count = 0
        self.last_error = ""

    def _log(self, message: str) -> None:
        if callable(self.logger):
            self.logger(str(message))

    def add(self, row_num: int, payload: Optional[dict] = None) -> bool:
        """Stage/merge one row. Returns True when this add triggered a flush."""
        row_num = int(row_num)
        if row_num <= 1:
            raise ValueError("Google Sheet 資料列必須大於 1")
        current = self.pending.setdefault(row_num, {})
        current.update(dict(payload or {}))
        if len(self.pending) >= self.checkpoint_size:
            self.flush()
            return True
        return False

    def flush(self) -> int:
        """Write all pending rows in one batch_update. Returns flushed row count."""
        if not self.pending:
            return 0
        batch = {row: dict(info) for row, info in sorted(self.pending.items())}
        try:
            update_sheet_rows(self.worksheet, batch)
        except Exception as exc:
            self.last_error = str(exc)
            self._log(f"❌ Google Sheet checkpoint 回寫失敗：{exc}")
            # Keep pending rows so caller may retry/finalize later.
            raise
        count = len(batch)
        self.pending.clear()
        self.total_flushed_rows += count
        self.flush_count += 1
        self.last_error = ""
        self._log(
            f"✅ Google Sheet checkpoint #{self.flush_count}：一次批次回寫 {count} 列；"
            f"累計已回寫 {self.total_flushed_rows} 列。"
        )
        return count

    def finalize(self) -> int:
        """Flush the final partial checkpoint (e.g. remaining 1-9 rows)."""
        return self.flush()

    def status(self) -> dict:
        return {
            "checkpoint_size": self.checkpoint_size,
            "pending_rows": len(self.pending),
            "flush_count": self.flush_count,
            "total_flushed_rows": self.total_flushed_rows,
            "last_error": self.last_error,
        }
