"""從既有成單工作表整理 LINE 通知群組與 Google Sheet 貼上格式。"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone


_CHECKED = {"TRUE", "V", "Y", "YES", "1", "是", "✓", "✔", "☑", "勾"}


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
        key = (name or f"__row_{row_no}", address or f"__row_{row_no}", service)
        item = grouped.setdefault(key, {
            "name": name, "address": str(row.get("地址", "") or "").strip(),
            "service": service, "order_nos": [], "rows": [], "entries": [],
        })
        if order_no not in item["order_nos"]:
            item["order_nos"].append(order_no)
        item["rows"].append(row_no)
        item["entries"].append({
            "row": row_no, "order_no": order_no, "name": name,
            "address": str(row.get("地址", "") or "").strip(),
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


def filter_groups_by_calendar(groups, orders_module, service, calendar_map, accounts):
    """只保留日曆確實存在的訂單；代客保留依同日姓名，其餘依日期時段地址。"""
    kept, skipped = [], []
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
            elif not any(item.get("order_no") == entry.get("order_no") for item in skipped):
                skipped.append({**entry, "reason": "日曆無對應行程"})
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
