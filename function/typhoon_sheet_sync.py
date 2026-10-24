# -*- coding: utf-8 -*-
"""颱風假訂單移轉：讀客服的 Google 表單，查後台目前日期／時段，有異動才填入「異動日期／異動時段」欄。

流程：
1. 依設定（試算表 ID、工作表名稱、訂單編號／原日期／原時段／新日期／新時段／
   異動日期／異動時段欄、起始列）讀取表單。
2. 逐筆查後台目前的服務日期／時段，和表單的新日期／新時段比對（compare_sheet_orders）。
   新日期／新時段只讀不改。
3. 客服確認後才寫入（apply_sheet_updates）：
   - 和新日期／新時段不同 → 異動欄填入目前日期／時段；
   - 相同但異動欄還有舊值 → 清成空白；
   - 相同且異動欄空白 → 不動。
   寫入前重讀這些格子，若比對後被手動改過就跳過，不覆蓋。

設定存在主控試算表「颱風移轉設定」分頁，每個後台帳號一列。
"""

import re
from datetime import datetime
from zoneinfo import ZoneInfo

import orders
import quick_order as qo
from function import typhoon_transfer as tt


SETTINGS_SHEET_TITLE = "颱風移轉設定"
SETTING_FIELDS = [
    ("spreadsheet_id", "試算表ID"),
    ("worksheet", "工作表名稱"),
    ("order_col", "訂單編號欄"),
    ("orig_date_col", "原日期欄"),
    ("orig_period_col", "原時段欄"),
    ("orig_staff_col", "原專員欄"),
    ("new_date_col", "新日期欄"),
    ("new_period_col", "新時段欄"),
    ("change_date_col", "異動日期欄"),
    ("change_period_col", "異動時段欄"),
    ("start_row", "起始列"),
]
SETTINGS_HEADERS = ["後台帳號"] + [label for _key, label in SETTING_FIELDS] + ["更新時間"]
DEFAULT_SETTINGS = {
    "spreadsheet_id": "", "worksheet": "", "order_col": "A",
    "orig_date_col": "F", "orig_period_col": "G", "orig_staff_col": "I",
    "new_date_col": "J", "new_period_col": "K",
    "change_date_col": "O", "change_period_col": "P", "start_row": "2",
}


def _now_text():
    return datetime.now(ZoneInfo("Asia/Taipei")).strftime("%Y-%m-%d %H:%M")


def spreadsheet_id_from_text(text):
    """接受試算表網址或 ID。"""
    text = str(text or "").strip()
    match = re.search(r"/spreadsheets/d/([A-Za-z0-9_-]+)", text)
    return match.group(1) if match else text


def column_index(letter):
    """欄位英文字母 → 0 起算的索引（A=0、AA=26）。"""
    letter = str(letter or "").strip().upper()
    if not re.fullmatch(r"[A-Z]{1,3}", letter):
        raise ValueError(f"欄位請輸入英文字母（例如 A、I、AA），收到：{letter or '空白'}")
    index = 0
    for ch in letter:
        index = index * 26 + (ord(ch) - 64)
    return index - 1


def validate_settings(settings):
    settings = {**DEFAULT_SETTINGS, **(settings or {})}
    settings["spreadsheet_id"] = spreadsheet_id_from_text(settings["spreadsheet_id"])
    if not settings["spreadsheet_id"]:
        raise ValueError("請輸入 Google 試算表 ID 或網址")
    if not str(settings["worksheet"]).strip():
        raise ValueError("請輸入工作表名稱")
    required = ("order_col", "new_date_col", "new_period_col", "change_date_col", "change_period_col")
    for key in required:
        column_index(settings[key])
    for key in ("orig_date_col", "orig_period_col", "orig_staff_col"):
        if str(settings[key]).strip():
            column_index(settings[key])
    used = [str(settings[k]).strip().upper() for k in required]
    if str(settings["orig_staff_col"]).strip():
        used.append(str(settings["orig_staff_col"]).strip().upper())
    if len(set(used)) != len(used):
        raise ValueError("訂單編號欄、原專員欄、新日期欄、新時段欄、異動日期欄、異動時段欄不可重複")
    protected = {str(settings[k]).strip().upper() for k in ("order_col", "orig_date_col", "orig_period_col", "orig_staff_col", "new_date_col", "new_period_col") if str(settings[k]).strip()}
    for key in ("change_date_col", "change_period_col"):
        if str(settings[key]).strip().upper() in protected:
            raise ValueError("異動日期欄／異動時段欄不可和訂單編號、原日期時段、原專員、新日期時段同一欄")
    try:
        start_row = int(settings["start_row"])
    except Exception:
        raise ValueError("起始列請輸入數字")
    if start_row < 1:
        raise ValueError("起始列需大於 0")
    settings["start_row"] = str(start_row)
    return settings


# ---------------------------------------------------------
# 設定暫存（主控試算表「颱風移轉設定」分頁）
# ---------------------------------------------------------

def _settings_worksheet(client=None):
    client = client or orders.build_gsheet_client()
    spreadsheet = client.open_by_key(orders.GOOGLE_SHEET_ID)
    try:
        worksheet = spreadsheet.worksheet(SETTINGS_SHEET_TITLE)
    except orders.gspread.WorksheetNotFound:
        worksheet = spreadsheet.add_worksheet(title=SETTINGS_SHEET_TITLE, rows=100, cols=len(SETTINGS_HEADERS))
        worksheet.update(range_name="A1", values=[SETTINGS_HEADERS])
    return worksheet


def _row_to_settings(headers, row):
    """依標題名稱讀值，舊版設定（少了新欄位）也讀得到。"""
    by_header = {h: (row[i] if i < len(row) else "") for i, h in enumerate(headers)}
    saved = {key: by_header.get(label, "") for key, label in SETTING_FIELDS}
    settings = {**DEFAULT_SETTINGS, **{k: v for k, v in saved.items() if str(v).strip() != ""}}
    if any(h for h in headers) and "原專員欄" not in headers:
        # 舊版設定沒有原專員欄：留空，避免預設的 I 和既有新日期欄撞欄
        settings["orig_staff_col"] = ""
    return settings


def load_settings(account, client=None):
    """讀這個後台帳號上次存的設定；沒有就回傳預設值。"""
    values = _settings_worksheet(client).get_all_values()
    headers = values[0] if values else SETTINGS_HEADERS
    for row in values[1:]:
        if row and row[0].strip() == str(account or "").strip():
            return _row_to_settings(headers, row)
    return dict(DEFAULT_SETTINGS)


def save_settings(account, settings, client=None):
    settings = validate_settings(settings)
    worksheet = _settings_worksheet(client)
    values = worksheet.get_all_values()
    headers = values[0] if values else []
    if headers != SETTINGS_HEADERS:
        # 舊版標題：依標題名稱轉成新格式後整份重寫
        migrated = [SETTINGS_HEADERS]
        for row in values[1:]:
            if row and row[0].strip():
                old = _row_to_settings(headers, row)
                by_header = {h: (row[i] if i < len(row) else "") for i, h in enumerate(headers)}
                migrated.append([row[0].strip()] + [str(old[k]) for k, _l in SETTING_FIELDS] + [by_header.get("更新時間", "")])
        worksheet.update(range_name="A1", values=migrated)
        values = migrated
    row_values = [str(account or "").strip()] + [str(settings[key]) for key, _label in SETTING_FIELDS] + [_now_text()]
    for row_no, row in enumerate(values[1:], 2):
        if row and row[0].strip() == row_values[0]:
            worksheet.update(range_name=f"A{row_no}", values=[row_values])
            return settings
    worksheet.append_row(row_values, value_input_option="RAW")
    return settings


# ---------------------------------------------------------
# 比對與寫回
# ---------------------------------------------------------

def _open_target(settings, client=None):
    client = client or orders.build_gsheet_client()
    return client.open_by_key(settings["spreadsheet_id"]).worksheet(settings["worksheet"])


def _cell(row, index):
    return str(row[index]).strip() if index is not None and index < len(row) else ""


def read_sheet_orders(values, settings):
    """從工作表全部值取出要比對的列。"""
    start_row = int(settings["start_row"])
    idx = {key: column_index(settings[key]) if str(settings.get(key, "")).strip() else None
           for key in ("order_col", "orig_date_col", "orig_period_col", "orig_staff_col", "new_date_col",
                       "new_period_col", "change_date_col", "change_period_col")}
    items, seen = [], set()
    for row_no in range(start_row, len(values) + 1):
        row = values[row_no - 1]
        order_no = _cell(row, idx["order_col"])
        if not re.fullmatch(orders.ORDER_NO_REGEX, order_no) or order_no in seen:
            continue
        seen.add(order_no)
        items.append({
            "row": row_no,
            "order_no": order_no,
            "orig_date": _cell(row, idx["orig_date_col"]),
            "orig_period": _cell(row, idx["orig_period_col"]),
            "orig_staff": _cell(row, idx["orig_staff_col"]),
            "sheet_date": _cell(row, idx["new_date_col"]),
            "sheet_period": _cell(row, idx["new_period_col"]),
            "change_date": _cell(row, idx["change_date_col"]),
            "change_period": _cell(row, idx["change_period_col"]),
        })
    return items


def _same_date(left, right):
    return tt._normalize_date_text(left) == tt._normalize_date_text(right)


def compare_sheet_orders(env_name, backend_email, backend_password, settings, client=None, progress=None):
    """讀表單並逐筆查後台目前日期／時段；不寫入。"""
    settings = validate_settings(settings)
    worksheet = _open_target(settings, client)
    items = read_sheet_orders(worksheet.get_all_values(), settings)
    session, _base_url = tt._login(env_name, backend_email, backend_password)
    rows = []
    for index, item in enumerate(items, 1):
        if progress:
            progress(index, len(items), item)
        row = {**item, "now_date": "", "now_period": "", "payment_status": "", "status": "", "name": ""}
        try:
            block = qo._fetch_purchase_block_for_order_no(session, item["order_no"])
            lines = block.get("lines", [])
            joined = "\n".join(lines)
            now_date, now_period = qo._parse_service_date_time_loose(joined)
            row["now_date"], row["now_period"] = now_date, tt._compact_period(now_period)
            status_match = re.search(r"付款狀態[：:]\s*([^\n]+)", joined)
            row["payment_status"] = status_match.group(1).strip() if status_match else ""
            for i, line in enumerate(lines):
                if re.fullmatch(r"09\d{8}", str(line).strip()):
                    row["name"] = str(lines[i - 1]).strip() if i else ""
                    break
            if not row["now_date"] or not row["now_period"]:
                row["status"] = "查詢失敗：讀不到目前日期／時段"
            elif _same_date(row["now_date"], item["sheet_date"]) and row["now_period"] == tt._compact_period(item["sheet_period"]):
                row["status"] = "待清除異動欄" if (item["change_date"] or item["change_period"]) else "未變動"
            elif _same_date(row["now_date"], item["change_date"]) and row["now_period"] == tt._compact_period(item["change_period"]):
                row["status"] = "已填異動"
            else:
                row["status"] = "待填異動"
        except Exception as exc:
            row["status"] = f"查詢失敗：{exc}"
        rows.append(row)
    return rows


PENDING_STATUSES = ("待填異動", "待清除異動欄")


def apply_sheet_updates(settings, rows, client=None):
    """寫入異動欄：「待填異動」填入目前日期／時段，「待清除異動欄」清成空白。

    只寫異動日期／異動時段兩欄。寫入前重讀格子；和比對時讀到的值不同
    （比對後被手動改過）或該列訂單編號已變動就跳過。回傳每列結果。
    """
    settings = validate_settings(settings)
    worksheet = _open_target(settings, client)
    values = worksheet.get_all_values()
    order_idx = column_index(settings["order_col"])
    date_idx = column_index(settings["change_date_col"])
    period_idx = column_index(settings["change_period_col"])
    date_col = settings["change_date_col"].strip().upper()
    period_col = settings["change_period_col"].strip().upper()
    updates, results = [], []
    for row in rows:
        if row.get("status") not in PENDING_STATUSES:
            continue
        current = values[row["row"] - 1] if row["row"] - 1 < len(values) else []
        if _cell(current, order_idx) != row["order_no"]:
            results.append({**row, "status": "已跳過：該列訂單編號已變動"})
            continue
        if _cell(current, date_idx) != row["change_date"] or _cell(current, period_idx) != row["change_period"]:
            results.append({**row, "status": "已跳過：比對後異動欄已被修改"})
            continue
        if row["status"] == "待填異動":
            new_values, done = (row["now_date"], row["now_period"]), "已填異動"
        else:
            new_values, done = ("", ""), "已清除異動欄"
        updates.append({"range": f"{date_col}{row['row']}", "values": [[new_values[0]]]})
        updates.append({"range": f"{period_col}{row['row']}", "values": [[new_values[1]]]})
        results.append({**row, "status": done, "change_date": new_values[0], "change_period": new_values[1]})
    if updates:
        worksheet.batch_update(updates, value_input_option="USER_ENTERED")
        results = _verify_written(worksheet, results, date_idx, period_idx)
    return results


def _target_label(worksheet):
    try:
        book_title = worksheet.spreadsheet.title
    except Exception:
        book_title = ""
    return f"{book_title}／{worksheet.title}" if book_title else worksheet.title


def _verify_written(worksheet, results, date_idx, period_idx):
    """寫入後重讀工作表，確認異動欄真的變成要寫的值；不符就標示出來，不假裝成功。"""
    values = worksheet.get_all_values()
    label = _target_label(worksheet)
    url = getattr(worksheet, "url", "")
    checked = []
    for row in results:
        if row["status"] not in ("已填異動", "已清除異動欄"):
            checked.append(row)
            continue
        current = values[row["row"] - 1] if row["row"] - 1 < len(values) else []
        got_date, got_period = _cell(current, date_idx), _cell(current, period_idx)
        ok = _same_date(got_date, row["change_date"]) and tt._compact_period(got_period) == tt._compact_period(row["change_period"])
        if not row["change_date"] and not row["change_period"]:
            ok = not got_date and not got_period
        if ok:
            checked.append({**row, "written_to": label, "sheet_url": url})
        else:
            checked.append({
                **row, "written_to": label, "sheet_url": url,
                "status": f"寫入後讀回不符（讀到：{got_date} {got_period}）",
            })
    return checked


# ---------------------------------------------------------
# 誤傳颱風假：把已移轉訂單改回原日期／原時段並配回原專員
# ---------------------------------------------------------

def _order_now(session, order_no):
    block = qo._fetch_purchase_block_for_order_no(session, order_no)
    lines = block.get("lines", [])
    now_date, now_period = qo._parse_service_date_time_loose("\n".join(lines))
    staff = tt.parse_staff_text(tt.staff_text(orders._extract_staff_line(lines) or ""))
    name = ""
    for i, line in enumerate(lines):
        if re.fullmatch(r"09\d{8}", str(line).strip()):
            name = str(lines[i - 1]).strip() if i else ""
            break
    return now_date, tt._compact_period(now_period), staff, name


def plan_restore(env_name, backend_email, backend_password, settings, client=None, progress=None):
    """讀表單的原日期／原時段／原專員，查後台目前狀態，列出要返回的訂單；不修改後台。"""
    settings = validate_settings(settings)
    for key, label in (("orig_date_col", "原日期欄"), ("orig_period_col", "原時段欄"), ("orig_staff_col", "原專員欄")):
        if not str(settings.get(key, "")).strip():
            raise ValueError(f"返回原班表需要設定{label}")
    worksheet = _open_target(settings, client)
    items = read_sheet_orders(worksheet.get_all_values(), settings)
    return plan_restore_items(env_name, backend_email, backend_password, items, progress=progress)


def plan_restore_items(env_name, backend_email, backend_password, items, progress=None):
    """依 items（row／order_no／orig_date／orig_period／orig_staff）查後台目前狀態，
    列出要返回的訂單；不修改後台。orig_staff 可為「、」分隔文字或姓名清單。"""
    session, _base_url = tt._login(env_name, backend_email, backend_password)
    rows = []
    for index, item in enumerate(items, 1):
        if progress:
            progress(index, len(items), item)
        row = {
            "row": item["row"], "order_no": item["order_no"], "name": "",
            "orig_date": tt._normalize_date_text(item["orig_date"]) if item["orig_date"] else "",
            "orig_period": tt._compact_period(item["orig_period"]),
            "orig_staff": (list(item["orig_staff"]) if isinstance(item["orig_staff"], (list, tuple))
                           else tt.parse_staff_text(item["orig_staff"])),
            "now_date": "", "now_period": "", "now_staff": [], "status": "",
        }
        if not row["orig_date"] or not row["orig_period"]:
            row["status"] = "缺原日期／原時段"
        elif not row["orig_staff"]:
            row["status"] = "缺原專員"
        else:
            try:
                row["now_date"], row["now_period"], row["now_staff"], row["name"] = _order_now(session, item["order_no"])
                at_orig = row["now_date"] == row["orig_date"] and row["now_period"] == row["orig_period"]
                same_staff = sorted(row["now_staff"]) == sorted(row["orig_staff"])
                if at_orig and same_staff:
                    row["status"] = "已在原班表"
                elif at_orig:
                    row["status"] = "待配回原專員"
                else:
                    row["status"] = "待返回"
            except Exception as exc:
                row["status"] = f"查詢失敗：{exc}"
        rows.append(row)
    return rows


RESTORE_PENDING = ("待返回", "待配回原專員")


def _assign_original_staff(session, base_url, order_no, service_date, period, wanted, reserved=()):
    """在排班修改頁把訂單專員換回原專員（每個配班位置選名字）。

    - 原專員可選（不被同時段其他訂單占用）就選原專員；
    - 選不到的位置不留著後台自動配的人（可能正好是其他待返回訂單的原專員），
      改選一位不在 reserved（其他待返回訂單的原專員）裡、也沒被占用的人；
      都沒有就維持目前的人。
    回傳 dict：all_original（全部配回原專員）、missing（沒配回的原專員）、message。
    """
    purchase_id = qo._fetch_order_edit_id(session, order_no)
    if not purchase_id:
        return {"all_original": False, "missing": list(wanted), "message": f"找不到訂單 {order_no} 的後台 ID"}
    csrf, origin_ids, slots = qo._get_schedule_edit_info(session, base_url, service_date, purchase_id)
    if not slots or not origin_ids:
        return {"all_original": False, "missing": list(wanted), "message": "無法開啟排班修改頁"}
    if len(wanted) != len(origin_ids):
        return {"all_original": False, "missing": list(wanted),
                "message": f"原專員 {len(wanted)} 位，但訂單目前需要 {len(origin_ids)} 位，請手動處理"}
    occupied = qo._get_occupied_staff_for_period(
        session, base_url, service_date, period, exclude_purchase_id=purchase_id,
    )
    reserved = {name for name in reserved if name not in wanted}
    slot_options = [{qo._staff_name_key(label): sid for label, sid in slot_map.items()} for slot_map in slots[:len(wanted)]]
    choices = [None] * len(slot_options)
    used = set()
    # 第一輪：每個位置先選原專員
    for i, options in enumerate(slot_options):
        pick = next((n for n in wanted if n not in used and n in options and n not in occupied), None)
        if pick:
            choices[i] = options[pick]
            used.add(pick)
    missing = [n for n in wanted if n not in used]
    # 第二輪：沒選到原專員的位置，改選不會擋到其他待返回訂單的人
    fallback_names = []
    for i, options in enumerate(slot_options):
        if choices[i] is not None:
            continue
        pick = next((n for n in options if n not in used and n not in occupied and n not in reserved), None)
        if pick:
            choices[i] = options[pick]
            used.add(pick)
            fallback_names.append(pick)
        else:
            choices[i] = origin_ids[i]  # 沒有可替換的人：維持目前
    fields = [("_token", csrf), ("_method", "PUT")]
    for oid in origin_ids:
        fields.append(("originShiftId[]", oid))
    for j, sid in enumerate(choices):
        fields.append((f"shiftId[{j}]", sid))
    resp = session.post(
        f"{base_url}/schedule/edit", params={"date": service_date, "purchase_id": purchase_id},
        data=fields, headers=orders.HEADERS, allow_redirects=True,
    )
    if resp.status_code not in (200, 302):
        return {"all_original": False, "missing": list(wanted), "message": f"排班送出失敗（HTTP {resp.status_code}）"}
    message = ""
    if missing:
        busy = [n for n in missing if n in occupied]
        unseen = [n for n in missing if n not in occupied]
        parts = []
        if busy:
            parts.append(f"{'、'.join(busy)} 已被同時段其他訂單安排")
        if unseen:
            parts.append(f"排班修改頁選不到 {'、'.join(unseen)}（可能勾班時段不同或當天沒排班）")
        if fallback_names:
            parts.append(f"暫配 {'、'.join(fallback_names)}")
        message = "；".join(parts)
    return {"all_original": not missing, "missing": missing, "message": message}


def execute_restore(env_name, backend_email, backend_password, rows, progress=None, retry_rounds=6):
    """逐筆返回：每一筆先用修改日期改回原日期／原時段，馬上到排班修改配回原專員，才做下一筆。

    配不回原專員的位置不留著後台自動配的人（避免占到後面訂單的原專員造成連鎖錯誤）；
    全部跑完後，對還沒配回原專員的訂單再補試（retry_rounds 輪）。每步都回查確認。
    """
    session, base_url = tt._login(env_name, backend_email, backend_password)
    pending = [r for r in rows if r.get("status") in RESTORE_PENDING]
    results = {}
    unfinished = []  # 已改回原日期但專員未全部配回的訂單

    def reserved_for(row):
        names = set()
        for other in pending:
            if other["order_no"] == row["order_no"]:
                continue
            done = results.get(other["order_no"])
            if done is not None and done["status"] == "已返回原班表":
                continue
            names.update(other["orig_staff"])
        return names

    def assign_and_record(row, result):
        outcome = _assign_original_staff(
            session, base_url, row["order_no"], row["orig_date"], row["orig_period"], row["orig_staff"],
            reserved=reserved_for(row),
        )
        _d, _p, now_staff, _n = _order_now(session, row["order_no"])
        result["now_staff"] = now_staff
        if outcome["all_original"] and sorted(now_staff) == sorted(row["orig_staff"]):
            result["status"] = "已返回原班表"
            result["restored_at"] = _now_text()
            return True
        if outcome["all_original"]:
            result["status"] = f"已改回原日期，但專員是 {'、'.join(now_staff) or '無'}，請到後台確認"
        else:
            result["status"] = f"已改回原日期，專員未全部配回：{outcome['message']}，請手動處理"
        return False

    date_failed = []  # 修改日期選不到原日期時段，等其他訂單處理完再試
    placeholder_tried = set()

    def add_placeholders(stuck_rows):
        """每個卡住的日期時段補一位暫時頂替的檸檬人（只用當天沒有任何班別的檸檬人）。"""
        added = False
        for row in stuck_rows:
            key = (row["orig_date"], row["orig_period"])
            if key in placeholder_tried:
                continue
            placeholder_tried.add(key)
            try:
                shift = qo.ensure_lemon_cleaner_shifts(session, base_url, row["orig_date"], row["orig_period"], "1")
            except Exception:
                continue
            names = shift.get("assigned") or []
            if names:
                added = True
                for other in stuck_rows:
                    if (other["orig_date"], other["orig_period"]) == key:
                        results[other["order_no"]]["placeholder"] = "、".join(names)
        return added

    opened_tried = set()

    def open_lemon_slots(stuck_rows):
        """修改日期選不到原日期時段（當天該時段沒有空的人）：比照手動做法，先替檸檬人勾原日期
        班別（人數＝原專員人數，只用當天沒有任何班別的檸檬人），讓訂單能先改回原日期、
        暫配檸檬人，再到排班修改換回原專員。"""
        added = False
        for row in stuck_rows:
            key = (row["orig_date"], row["orig_period"], row["order_no"])
            if key in opened_tried:
                continue
            opened_tried.add(key)
            try:
                shift = qo.ensure_lemon_cleaner_shifts(
                    session, base_url, row["orig_date"], row["orig_period"], str(max(1, len(row["orig_staff"]))),
                )
            except Exception:
                continue
            names = shift.get("assigned") or []
            if names:
                added = True
                results[row["order_no"]]["lemon_opened"] = "、".join(names)
        return added

    def move_back(row, result):
        """改回原日期並配回原專員；回傳 'done'／'unfinished'／'date_failed'／'stop'。"""
        now_date, now_period, _staff, _name = _order_now(session, row["order_no"])
        if (now_date, now_period) not in ((row["now_date"], row["now_period"]), (row["orig_date"], row["orig_period"])):
            result["status"] = f"已跳過：比對後訂單日期已變動（目前 {now_date} {now_period}）"
            return "stop"
        if (now_date, now_period) != (row["orig_date"], row["orig_period"]):
            options = tt._change_date_options(session, base_url, row["order_no"])
            if row["orig_period"] not in options.get(row["orig_date"], {}):
                result["status"] = f"返回失敗：修改日期選不到 {row['orig_date']} {row['orig_period']}，請手動處理"
                return "date_failed"
            qo._update_order_service_date(session, base_url, row["order_no"], row["orig_date"], row["orig_period"])
            now_date, now_period, _staff, _name = _order_now(session, row["order_no"])
            if (now_date, now_period) != (row["orig_date"], row["orig_period"]):
                result["status"] = f"返回失敗：送出後訂單是 {now_date} {now_period}，請到後台確認"
                return "stop"
        result.update({"now_date": now_date, "now_period": now_period})
        return "done" if assign_and_record(row, result) else "unfinished"

    for index, row in enumerate(pending, 1):
        if progress:
            progress(index, len(pending), row)
        result = dict(row)
        results[row["order_no"]] = result
        try:
            outcome = move_back(row, result)
        except Exception as exc:
            result["status"] = f"返回失敗：{exc}"
            continue
        if outcome == "unfinished":
            unfinished.append(row)
        elif outcome == "date_failed":
            date_failed.append(row)

    for _round in range(retry_rounds):
        if not unfinished and not date_failed:
            break
        progressed = False
        still_unfinished, still_date_failed = [], []
        for row in date_failed:
            try:
                outcome = move_back(row, results[row["order_no"]])
            except Exception as exc:
                results[row["order_no"]]["status"] = f"返回失敗：{exc}"
                continue
            if outcome == "date_failed":
                still_date_failed.append(row)
            else:
                progressed = True
                if outcome == "unfinished":
                    still_unfinished.append(row)
        for row in unfinished:
            try:
                if assign_and_record(row, results[row["order_no"]]):
                    progressed = True
                else:
                    still_unfinished.append(row)
            except Exception as exc:
                results[row["order_no"]]["status"] = f"已改回原日期，補配專員失敗：{exc}"
                still_unfinished.append(row)
        unfinished, date_failed = still_unfinished, still_date_failed
        if date_failed and open_lemon_slots(date_failed):
            progressed = True
        if not progressed and unfinished:
            # 卡住（例如兩組人員同時段對調、又沒有空閒人員可暫時頂替）：用安全補檸檬人
            # 找當天沒有任何班別的檸檬人勾這個時段，讓卡住的訂單先換給檸檬人騰出位置
            progressed = add_placeholders(unfinished)
        if not progressed:
            break

    # 全部跑完後，每一筆再和記錄的日期／時段／專員姓名核對一次
    for row in pending:
        result = results[row["order_no"]]
        try:
            now_date, now_period, now_staff, _n = _order_now(session, row["order_no"])
        except Exception as exc:
            result["status"] = f"{result['status']}（最後核對失敗：{exc}）"
            continue
        result.update({"now_date": now_date, "now_period": now_period, "now_staff": now_staff})
        if result["status"] == "已返回原班表" and not matches_record(result):
            result["status"] = (
                f"最後核對不一致：目前 {now_date} {now_period} {'、'.join(now_staff) or '無'}，請到後台確認"
            )
            result.pop("restored_at", None)
        if result.get("lemon_opened"):
            result["status"] += (
                f"（原日期時段沒有空的人，已先替 {result['lemon_opened']} 勾 {row['orig_date']} 班別讓訂單改回原日期；"
                "如不需要請到排班管理清除）"
            )
        if result.get("placeholder"):
            result["status"] += (
                f"（曾借 {result['placeholder']} 暫時頂替，已替其勾 {row['orig_date']} 班別；"
                "如不需要請到排班管理清除）"
            )
    return [results[r["order_no"]] for r in pending]


def matches_record(row):
    """目前日期／時段／專員姓名是否和記錄（原）完全一致。"""
    return (
        row.get("now_date") == row.get("orig_date")
        and row.get("now_period") == row.get("orig_period")
        and sorted(row.get("now_staff") or []) == sorted(row.get("orig_staff") or [])
    )


def check_mark(row):
    return "✅ 一致" if matches_record(row) else "❌ 不一致"


RESTORE_COPY_HEADERS = [
    "訂單編號", "姓名", "原日期", "原時段", "原專員", "目前日期", "目前時段", "目前專員", "狀態", "返回時間",
]


def restore_tsv(rows):
    """返回結果（或檢查結果）複製用，含標題列，Tab 分隔。"""
    lines = ["\t".join(RESTORE_COPY_HEADERS)]
    for r in rows:
        values = [
            r.get("order_no", ""), r.get("name", ""), r.get("orig_date", ""), r.get("orig_period", ""),
            "、".join(r.get("orig_staff") or []), r.get("now_date", ""), r.get("now_period", ""),
            "、".join(r.get("now_staff") or []), r.get("status", ""), r.get("restored_at", ""),
        ]
        lines.append("\t".join(str(v or "").replace("\t", " ").replace("\n", " ") for v in values))
    return "\n".join(lines)
