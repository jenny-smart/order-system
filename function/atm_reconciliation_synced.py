# -*- coding: utf-8 -*-
"""ATM reconciliation compatibility wrapper for synced unpaid-list behavior."""
from typing import Dict, List

from function import atm_reconciliation as _base


def paste_atm_unpaid_list(region: str, rows: List[Dict], ui_logger=None) -> Dict:
    """Append only new unpaid orders after existing I:L data without overwriting it."""
    log = _base.make_logger(ui_logger)
    result = {"pasted": 0, "skipped_duplicates": 0, "start_row": None, "errors": []}

    if not rows:
        log("沒有資料可以貼")
        return result

    ws = _base.get_atm_worksheet(region)
    all_values = _base.memo.with_retry(ws.get_all_values)

    last_a_row = max(
        (idx for idx, row in enumerate(all_values, start=1)
         if row and str(row[0]).strip()),
        default=0,
    )
    last_b_row = max(
        (idx for idx, row in enumerate(all_values, start=1)
         if len(row) >= 2 and str(row[1]).strip()),
        default=1,
    )

    existing_order_nos = set()
    last_unpaid_row = 0
    for idx, row in enumerate(all_values, start=1):
        if idx <= last_b_row:
            continue
        i_to_l = row[8:12] if len(row) > 8 else []
        if any(str(value).strip() for value in i_to_l):
            last_unpaid_row = idx
        order_no = row[9] if len(row) > 9 else ""
        if str(order_no).strip():
            existing_order_nos.add(str(order_no).strip())

    pending_rows = []
    seen_order_nos = set(existing_order_nos)
    for row in rows:
        order_no = str(row.get("order_no") or "").strip()
        if not order_no:
            log("⚠️ 略過一筆沒有訂單編號的資料")
            continue
        if order_no in seen_order_nos:
            result["skipped_duplicates"] += 1
            continue
        seen_order_nos.add(order_no)
        pending_rows.append(row)

    if not pending_rows:
        log(f"沒有新訂單可新增；已略過 {result['skipped_duplicates']} 筆重複訂單")
        return result

    start_row = max(last_a_row + 5, last_unpaid_row + 1)
    end_row = start_row + len(pending_rows) - 1

    current_row_count = int(getattr(ws, "row_count", 0) or len(all_values))
    if end_row > current_row_count:
        _base.memo.with_retry(ws.add_rows, end_row - current_row_count)

    updates = []
    for offset, row in enumerate(pending_rows):
        row_num = start_row + offset
        updates.append({
            "range": f"I{row_num}:L{row_num}",
            "values": [[
                row["year_month"], row["order_no"], row["name"], row["net_amount"],
            ]],
        })

        existing_h = ""
        if row_num <= len(all_values) and len(all_values[row_num - 1]) >= 8:
            existing_h = str(all_values[row_num - 1][7]).strip()
        if row.get("line_url") and not existing_h:
            updates.append({"range": f"H{row_num}", "values": [[row["line_url"]]]})

    _base.memo.with_retry(ws.batch_update, updates, value_input_option="RAW")

    result["pasted"] = len(pending_rows)
    result["start_row"] = start_row
    log(
        f"✅ 已新增 {len(pending_rows)} 筆至 I{start_row}:L{end_row}；"
        f"略過 {result['skipped_duplicates']} 筆重複訂單"
    )
    return result


def render(backend_email, backend_password, env):
    # Keep the existing ATM module/UI intact; replace only the unpaid-list writer.
    _base.paste_atm_unpaid_list = paste_atm_unpaid_list
    return _base.render(backend_email, backend_password, env)
