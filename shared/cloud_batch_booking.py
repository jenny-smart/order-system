# -*- coding: utf-8 -*-
"""批次建單優化＋雲端批次成單（CLI；GitHub Actions 執行）。

移植自 orders-system cloud_batch_booking.py。執行方式：

    python -m shared.cloud_batch_booking --sheet 台北202610 [--chunk-size 50] ...

原版 import 時呼叫 install_selected_row_status_guard()／install_recovery_meta_patch()
以 monkeypatch 改寫 orders；order-system 已把這些行為直接寫進 orders.py／
shared/gsheet.py／shared/hybrid_batch_runner.py，因此這裡不再安裝任何 patch。
"""
from __future__ import annotations
import argparse
import time
from collections import defaultdict
from accounts import ACCOUNTS
import function.batch_booking_optimized as batch_opt
from orders import get_region_by_address
from shared.cloud_booking_progress import Progress
from shared.selected_row_status_guard import _auto_filter_rows, _safe_load_candidates
from shared.hybrid_batch_runner import run_process_web_hybrid

ACTIONS = ["建單", "寄確認信", "改 Google 日曆"]


def _bool_text(value) -> bool:
    return str(value or "").strip().lower() in ("1", "true", "yes", "y", "on")


def load_pending(sheet_name: str, excluded=None, filter_mode: str = "all", selected_region: str = "", allow_auto_lemon=False, retry_failed=False):
    excluded = excluded or set()
    candidates = _safe_load_candidates(batch_opt, sheet_name, allow_failed=retry_failed)
    allowed_rows = None
    if filter_mode != "all":
        allowed_rows = set()
        if filter_mode in ("no_schedule", "both"):
            allowed_rows.update(_auto_filter_rows(batch_opt, sheet_name, "no_schedule", region=selected_region or None, allow_failed=retry_failed, candidates=candidates))
        if filter_mode in ("missing_order", "both"):
            allowed_rows.update(_auto_filter_rows(batch_opt, sheet_name, "missing_order", region=selected_region or None, allow_failed=retry_failed, candidates=candidates))
    result = []
    for _, row in candidates.sort_values("__sheet_row__").iterrows():
        row_no = int(row["__sheet_row__"])
        if row_no in excluded or (allowed_rows is not None and row_no not in allowed_rows):
            continue
        if batch_opt._text(row.get("訂單編號")):
            continue
        address = batch_opt._text(row.get("地址"))
        region = get_region_by_address(address, ACCOUNTS)
        if selected_region and region != selected_region:
            continue
        result.append((row_no, region or "", "" if region else f"無法依地址判斷地區：{address}"))
    return result


def run(sheet_name: str, chunk_size=50, max_rows=0, pause_seconds=5, filter_mode="all", selected_region="", allow_auto_lemon=False, retry_failed=False) -> int:
    attempted = set()
    success_total = fail_total = 0
    progress = Progress(sheet_name)
    processed = 0
    target_total = None
    candidate_total = 0
    started = time.monotonic()
    print(f"FILTER mode={filter_mode}; region={selected_region or 'auto'}; auto_lemon_shift={'ON' if allow_auto_lemon else 'OFF'}; retry_failed={'ON' if retry_failed else 'OFF'}", flush=True)
    print("STRATEGY multi-row-groups-first -> single-rows; Calendar only after order writeback", flush=True)
    while True:
        pending = load_pending(sheet_name, attempted, filter_mode, selected_region, allow_auto_lemon, retry_failed)
        if target_total is None:
            candidate_total = len(pending)
            target_total = min(len(pending), max_rows) if max_rows else len(pending)
            progress.publish('準備成單', 0, 0, 0, len(pending), target_total)
        if max_rows:
            left = max_rows - len(attempted)
            if left <= 0:
                break
            pending = pending[:left]
        batch = pending[:chunk_size]
        if not batch:
            break
        by_region = defaultdict(list)
        for row_no, region, error in batch:
            attempted.add(row_no)
            if error:
                fail_total += 1
                processed += 1
                print(f"SKIP row={row_no}: {error}", flush=True)
            else:
                by_region[region].append(row_no)
        for region, rows in by_region.items():
            group_snapshot = [0, 0, 0]
            account = ACCOUNTS.get(region) or {}
            try:
                email = str(account.get("email") or "").strip()
                password = str(account.get("password") or "").strip()
                if not email or not password:
                    raise RuntimeError(f"{region} 尚未設定後台帳號密碼")
                progress.publish('成單中', processed, success_total, fail_total,
                                 max(candidate_total - processed, 0), target_total, ','.join(map(str, rows)))
                print(f"START {region}: rows={','.join(map(str, rows))}", flush=True)
                processed_base, success_base, fail_base = processed, success_total, fail_total
                def report_group(done, ok, bad, current):
                    group_snapshot[:] = [done, ok, bad]
                    progress.publish('成單中', processed_base + done, success_base + ok, fail_base + bad,
                                     max(candidate_total - processed_base - done, 0), target_total, str(current))
                result = run_process_web_hybrid(
                    env_name="prod", region=region, backend_email=email, backend_password=password,
                    sheet_name=sheet_name, start_row=min(rows), end_row=max(rows), selected_actions=ACTIONS,
                    logger=lambda msg: print(str(msg), flush=True), allow_auto_lemon_shift=allow_auto_lemon,
                    selected_rows=rows, progress_callback=report_group,
                ) or {}
                success = int(result.get("success_count", 0) or 0)
                fail = int(result.get("fail_count", 0) or 0)
                success_total += success
                fail_total += fail
                print(f"DONE {region}: success={success} fail={fail} recovered={int(result.get('recovered_count', 0) or 0)} blocked={int(result.get('blocked_count', 0) or 0)}", flush=True)
            except Exception as exc:
                # Only count rows whose results were actually reported; a sheet
                # failure can occur AFTER the backend has created an order.
                done, ok, bad = group_snapshot
                progress.publish('中止，未回報列待核對', processed + done, success_total + ok, fail_total + bad,
                                 max(candidate_total - processed - done, 0), target_total)
                print(f"INTERRUPTED processed={processed + done} success={success_total + ok} fail={fail_total + bad} unconfirmed={len(rows) - done}", flush=True)
                print(f"ERROR {region}: {exc}", flush=True)
                return 2
            processed += len(rows)
            progress.publish('成單中', processed, success_total, fail_total,
                             max(candidate_total - processed, 0), target_total)
        elapsed = max(time.monotonic() - started, .001)
        print(f"PROGRESS attempted={len(attempted)} success={success_total} fail={fail_total} rate={len(attempted)/elapsed*60:.1f}/min", flush=True)
        if pause_seconds:
            time.sleep(pause_seconds)
    remaining = len(load_pending(sheet_name, attempted, filter_mode, selected_region, allow_auto_lemon, retry_failed))
    progress.publish('完成' if not fail_total else '部分失敗', processed, success_total, fail_total,
                     remaining, target_total or 0)
    print(f"FINISH attempted={len(attempted)} success={success_total} fail={fail_total} remaining={remaining}", flush=True)
    return 0 if fail_total == 0 else 2


def main():
    p = argparse.ArgumentParser(prog="python -m shared.cloud_batch_booking", description="批次建單優化＋雲端批次成單")
    p.add_argument("--sheet", required=True)
    p.add_argument("--chunk-size", type=int, default=50)
    p.add_argument("--max-rows", type=int, default=0)
    p.add_argument("--pause-seconds", type=int, default=5)
    p.add_argument("--filter-mode", choices=["all", "no_schedule", "missing_order", "both"], default="all")
    p.add_argument("--region", default="")
    p.add_argument("--allow-auto-lemon", default="false")
    p.add_argument("--retry-failed", default="false", help="已調整後，明確允許重試 N 欄失敗列")
    a = p.parse_args()
    if a.chunk_size < 1:
        p.error("--chunk-size 必須 >= 1")
    return run(a.sheet.strip(), a.chunk_size, max(a.max_rows, 0), max(a.pause_seconds, 0), a.filter_mode, a.region.strip(), _bool_text(a.allow_auto_lemon), _bool_text(a.retry_failed))


if __name__ == "__main__":
    raise SystemExit(main())
