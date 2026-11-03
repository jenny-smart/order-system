"""從既有成單工作表整理 LINE 通知群組與 Google Sheet 貼上格式。"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone


_CHECKED = {"TRUE", "V", "Y", "YES", "1", "是", "✓", "✔", "☑", "勾"}
OUTPUT_SPREADSHEET_ID = "1de41gNvBZCGdfy0qNouRNEaQD7R019VAvz2cfq88ZrE"
OUTPUT_HEADERS = ["姓名", "電話", "mail", "LINE連結", "通知內容", "來源工作表", "來源列", "地址", "訂單編號", "日曆比對", "後台確認", "說明", "產生時間"]


def parse_row_spec(spec):
    rows = set()
    for part in re.split(r"[,，\s]+", str(spec or "").strip()):
        if not part:
            continue
        if "-" in part:
            start, end = (int(value) for value in part.split("-", 1))
            if start < 2 or end < start:
                raise ValueError(f"列號範圍錯誤：{part}")
            rows.update(range(start, end + 1))
        else:
            row = int(part)
            if row < 2:
                raise ValueError(f"列號錯誤：{part}")
            rows.add(row)
    return rows


def groups_from_dataframe(df, row_spec=""):
    """只取已有訂單編號且非失敗列，依姓名＋地址＋服務類型合併訂單。"""
    wanted = parse_row_spec(row_spec)
    grouped = {}
    for offset, (_, row) in enumerate(df.iterrows(), 2):
        row_no = int(row.get("__sheet_row__", offset) or offset)
        if wanted and row_no not in wanted:
            continue
        order_no = str(row.get("訂單編號", "") or "").strip()
        if not order_no or str(row.get("結果", "") or "").strip() == "失敗":
            continue
        name = str(row.get("姓名", "") or "").strip()
        address = re.sub(r"\s+", "", str(row.get("地址", "") or ""))
        service = str(row.get("購買項目", "") or "").strip()
        phone = str(row.get("電話", "") or row.get("手機", "") or "").strip()
        email = str(row.get("mail", "") or row.get("Email", "") or row.get("email", "") or row.get("電子信箱", "") or "").strip()
        line_url = str(row.get("LINE連結", "") or row.get("LINE 連結", "") or row.get("LINE@連結", "") or row.get("line_url", "") or row.get("LINE", "") or "").strip()
        key = (name or f"__row_{row_no}", address or f"__row_{row_no}", service)
        item = grouped.setdefault(key, {
            "name": name, "address": str(row.get("地址", "") or "").strip(),
            "service": service, "phone": phone, "email": email, "line_url": line_url,
            "order_nos": [], "rows": [], "entries": [],
        })
        for field, value in (("phone", phone), ("email", email), ("line_url", line_url)):
            if value and not item.get(field):
                item[field] = value
        if order_no not in item["order_nos"]:
            item["order_nos"].append(order_no)
        item["rows"].append(row_no)
        item["entries"].append({
            "row": row_no, "order_no": order_no, "name": name,
            "address": str(row.get("地址", "") or "").strip(),
            "phone": phone, "email": email, "line_url": line_url,
            "date": row.get("日期", ""), "start": row.get("開始時間", ""), "end": row.get("結束時間", ""),
            "proxy": str(row.get("代客保留", "") or "").strip().upper() in _CHECKED,
        })
    return list(grouped.values())


def _proxy_name_exists(service, calendar_id, orders_module, entry):
    name = str(entry.get("name") or "").strip()
    date_s = orders_module.get_date_str(entry.get("date"))
    if not name or not date_s:
        return False
    start = datetime.strptime(date_s, "%Y-%m-%d").replace(tzinfo=timezone(timedelta(hours=8)))
    events = service.events().list(
        calendarId=calendar_id, timeMin=start.isoformat(), timeMax=(start + timedelta(days=1)).isoformat(),
        singleEvents=True, orderBy="startTime",
    ).execute().get("items", [])
    return any(name in "\n".join(str(event.get(field) or "") for field in ("summary", "description", "location")) for event in events)


def filter_groups_by_calendar(groups, orders_module, service, calendar_map, accounts, progress_callback=None):
    """只保留日曆確實存在的訂單；代客保留依同日姓名，其餘依日期時段地址。"""
    kept, skipped = [], []
    total = sum(len(group.get("entries") or []) for group in groups or [])
    checked = matched = 0
    for group in groups or []:
        matched_nos = []
        for entry in group.get("entries") or []:
            try:
                region = orders_module.get_region_by_address(entry.get("address", ""), accounts)
                calendar_id = calendar_map.get(region)
                if not calendar_id:
                    raise ValueError("找不到地區日曆")
                if entry.get("proxy"):
                    found = _proxy_name_exists(service, calendar_id, orders_module, entry)
                else:
                    found = bool(orders_module.find_matching_calendar_event(
                        service, calendar_id, entry.get("address", ""), entry.get("date", ""),
                        str(entry.get("start", "")), str(entry.get("end", "")),
                    ))
            except Exception as exc:
                found = False
                skipped.append({**entry, "reason": f"日曆檢查失敗：{exc}"})
            if found:
                matched_nos.append(entry["order_no"])
                matched += 1
            elif not any(item.get("order_no") == entry.get("order_no") for item in skipped):
                skipped.append({**entry, "reason": "日曆無對應行程"})
            checked += 1
            if progress_callback:
                progress_callback(checked, total, matched, len(skipped), entry)
        if matched_nos:
            copy = dict(group)
            copy["order_nos"] = list(dict.fromkeys(matched_nos))
            kept.append(copy)
    return kept, skipped


def results_tsv(results):
    def cell(value):
        text = str(value or "")
        if any(char in text for char in ('\t', '\n', '"')):
            return '"' + text.replace('"', '""') + '"'
        return text

    rows = [["姓名", "地址", "訂單編號", "LINE預約完成通知", "日曆檢查"]]
    for item in results or []:
        if item.get("error"):
            continue
        group = item.get("group") or {}
        rows.append([
            group.get("name"), group.get("address"), item.get("order_no"),
            item.get("text"), item.get("calendar_status", "未檢查（日曆不影響通知產生）"),
        ])
    return "\n".join("\t".join(cell(value) for value in row) for row in rows)


def comparison_rows(source_sheet, source_groups, results, skipped):
    """輸出每張訂單的日曆／後台／通知結果，供自動寫回指定試算表。"""
    skipped_by_order = {str(item.get("order_no") or ""): item for item in skipped or []}
    result_by_order = {}
    for item in results or []:
        for order_no in (item.get("group") or {}).get("order_nos") or []:
            result_by_order[str(order_no)] = item
    generated_at = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S")
    rows = []
    for group in source_groups or []:
        for entry in group.get("entries") or []:
            order_no = str(entry.get("order_no") or "")
            skipped_item = skipped_by_order.get(order_no)
            result_item = result_by_order.get(order_no)
            if skipped_item:
                calendar_status, backend_status, notice = "無對應行程", "未執行", ""
                reason = skipped_item.get("reason", "日曆無對應行程")
            elif result_item and not result_item.get("error"):
                calendar_status, backend_status = "有對應行程", "已確認"
                notice, reason = result_item.get("text", ""), ""
            else:
                calendar_status, backend_status, notice = "有對應行程", "確認失敗", ""
                reason = (result_item or {}).get("error", "無法取得結果")
            backend = (result_item or {}).get("result") or {}
            rows.append([
                entry.get("name", ""), entry.get("phone") or group.get("phone", "") or backend.get("phone", ""),
                entry.get("email") or group.get("email", "") or backend.get("email", ""),
                entry.get("line_url") or group.get("line_url", "") or backend.get("line_url", ""), notice,
                source_sheet, entry.get("row", ""), entry.get("address", ""), order_no,
                calendar_status, backend_status, reason, generated_at,
            ])
    return rows


def write_comparison_results(orders_module, source_sheet, rows):
    """將本次比對結果覆寫到指定主試算表的來源專用分頁。"""
    spreadsheet = orders_module.build_gsheet_client().open_by_key(OUTPUT_SPREADSHEET_ID)
    safe_source = str(source_sheet or "未命名").replace("/", "-").replace("\\", "-")
    title = ("已成單通知-" + safe_source)[:100]
    try:
        worksheet = spreadsheet.worksheet(title)
    except Exception as exc:
        if exc.__class__.__name__ != "WorksheetNotFound":
            raise
        worksheet = spreadsheet.add_worksheet(title=title, rows=max(len(rows) + 10, 100), cols=len(OUTPUT_HEADERS))
    worksheet.clear()
    worksheet.update(range_name="A1", values=[OUTPUT_HEADERS] + list(rows or []))
    worksheet.freeze(rows=1)
    return title
