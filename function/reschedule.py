# -*- coding: utf-8 -*-
"""訂單批次調班：把執行日期區間的已付款訂單，移到返回日期區間的同時段，並配回原本的專員。

供排班要調班時使用（不需 Google 表單，直接查後台）：
1. 查執行日期區間內的已付款服務訂單（沿用颱風假移轉的查詢），記下每筆原日期／原時段／原專員。
2. 一筆一筆處理：用「修改日期」移到返回日期區間中第一個選得到同時段的日期，
   馬上到「排班修改」選回原專員並回查確認姓名，才做下一筆。
3. 原專員配不回的位置，改配不是其他待調班訂單原專員、也沒被占用的人，避免連鎖錯誤；
   全部跑完後對專員未全部配回的訂單再補試。
"""

from function import typhoon_sheet_sync as tss
from function import typhoon_transfer as tt


def rows_from_orders(orders_found):
    """查詢結果 → 調班用的列（原日期／原時段／原專員）。"""
    return [
        {
            "row": index,
            "order_no": row["order_no"],
            "name": row.get("name", ""),
            "phone": row.get("phone", ""),
            "orig_date": row["service_date"],
            "orig_period": row["period"],
            "orig_staff": tt.parse_staff_text(tt.staff_text(row.get("staff", ""))),
            "now_date": row["service_date"],
            "now_period": row["period"],
            "now_staff": tt.parse_staff_text(tt.staff_text(row.get("staff", ""))),
            "status": "待調班",
        }
        for index, row in enumerate(orders_found, 1)
    ]


def execute_reschedule(env_name, backend_email, backend_password, rows, dates_by_day, progress=None, retry_rounds=2):
    """依 rows 順序逐筆調班；dates_by_day：{原日期: [候選返回日期...]}。"""
    session, base_url = tt._login(env_name, backend_email, backend_password)
    results = {}
    unfinished = []

    def reserved_for(row):
        names = set()
        for other in rows:
            if other["order_no"] == row["order_no"]:
                continue
            done = results.get(other["order_no"])
            if done is not None and done["status"] == "已調班並配回原專員":
                continue
            names.update(other["orig_staff"])
        return names

    def assign_and_record(row, result):
        outcome = tss._assign_original_staff(
            session, base_url, row["order_no"], result["now_date"], row["orig_period"], row["orig_staff"],
            reserved=reserved_for(row),
        )
        _d, _p, now_staff, _n = tss._order_now(session, row["order_no"])
        result["now_staff"] = now_staff
        if outcome["all_original"] and sorted(now_staff) == sorted(row["orig_staff"]):
            result["status"] = "已調班並配回原專員"
            result["restored_at"] = tss._now_text()
            return True
        if outcome["all_original"]:
            result["status"] = f"已改日期，但專員是 {'、'.join(now_staff) or '無'}，請到後台確認"
        else:
            result["status"] = f"已改日期，專員未全部配回：{outcome['message']}，請手動處理"
        return False

    for index, row in enumerate(rows, 1):
        if progress:
            progress(index, len(rows), row)
        result = dict(row)
        results[row["order_no"]] = result
        try:
            moved = tt.transfer_one_order(
                session, base_url, env_name,
                {"order_no": row["order_no"], "period": row["orig_period"], "phone": row.get("phone", ""),
                 "person": len(row["orig_staff"]), "service_date_before": row["orig_date"]},
                dates_by_day.get(row["orig_date"], []),
            )
            now_date, now_period, now_staff, _n = tss._order_now(session, row["order_no"])
            result.update({"now_date": now_date, "now_period": now_period, "now_staff": now_staff})
            if not moved.get("success"):
                result["status"] = f"調班失敗：{moved.get('message', '')}"
                if moved.get("attempts"):
                    result["status"] += f"（{'；'.join(moved['attempts'])}）"
                continue
            if not row["orig_staff"]:
                result["status"] = "已改日期（原訂單沒有專員，未配專員）"
                result["restored_at"] = tss._now_text()
                continue
            if not assign_and_record(row, result):
                unfinished.append(row)
        except Exception as exc:
            result["status"] = f"調班失敗：{exc}"

    for _round in range(retry_rounds):
        if not unfinished:
            break
        still = []
        for row in unfinished:
            try:
                if not assign_and_record(row, results[row["order_no"]]):
                    still.append(row)
            except Exception as exc:
                results[row["order_no"]]["status"] = f"已改日期，補配專員失敗：{exc}"
                still.append(row)
        if len(still) == len(unfinished):
            break
        unfinished = still

    return [results[r["order_no"]] for r in rows]
