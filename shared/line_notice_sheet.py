"""從既有成單工作表整理 LINE 通知群組與 Google Sheet 貼上格式。"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone


_CHECKED = {"TRUE", "V", "Y", "YES", "1", "是", "✓", "✔", "☑", "勾"}
SOURCE_OUTPUT_HEADERS = ["mail", "LINE連結", "通知內容", "異動檢查", "通知處理狀態"]


class _CachedRequest:
    def __init__(self, request, cache, key):
        self.request, self.cache, self.key = request, cache, key

    def execute(self):
        if self.key not in self.cache:
            self.cache[self.key] = self.request.execute()
        return self.cache[self.key]


class _CachedEvents:
    def __init__(self, events, cache):
        self.events, self.cache = events, cache

    def list(self, **kwargs):
        key = tuple(sorted((name, str(value)) for name, value in kwargs.items()))
        return _CachedRequest(self.events.list(**kwargs), self.cache, key)


class _CachedCalendarService:
    """同一日曆＋日期只向 Google Calendar 查一次。"""
    def __init__(self, service):
        self.service, self.cache = service, {}

    def events(self):
        return _CachedEvents(self.service.events(), self.cache)


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
        # 通知以「姓名＋地址」為單位；同地址不要因服務類型欄位差異重複查詢／顯示。
        key = (name or f"__row_{row_no}", address or f"__row_{row_no}")
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
            "service": service,
            "phone": phone, "email": email, "line_url": line_url,
            "date": row.get("日期", ""), "start": row.get("開始時間", ""), "end": row.get("結束時間", ""),
            "proxy": str(row.get("代客保留", "") or "").strip().upper() in _CHECKED,
        })
    return list(grouped.values())


def filter_completed_address_groups(groups, df):
    """續跑時略過原工作表已標記完成的姓名＋地址。"""
    if "通知處理狀態" not in getattr(df, "columns", []):
        return list(groups or []), 0
    completed = set()
    for _, row in df.iterrows():
        if str(row.get("通知處理狀態", "") or "").strip().startswith("完成"):
            completed.add((str(row.get("姓名", "") or "").strip(), re.sub(r"\s+", "", str(row.get("地址", "") or ""))))
    pending = [group for group in groups or [] if _customer_address_key(group) not in completed]
    return pending, len(list(groups or [])) - len(pending)


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
    service = _CachedCalendarService(service)
    total = sum(len(group.get("entries") or []) for group in groups or [])
    checked = matched = 0
    for group in groups or []:
        matched_nos, matched_entries = [], []
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
                matched_entries.append(entry)
                matched += 1
            elif not any(item.get("order_no") == entry.get("order_no") for item in skipped):
                skipped.append({**entry, "reason": "日曆無對應行程"})
            checked += 1
            if progress_callback:
                progress_callback(checked, total, matched, len(skipped), entry)
        if matched_nos:
            copy = dict(group)
            copy["order_nos"] = list(dict.fromkeys(matched_nos))
            copy["entries"] = matched_entries
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


def _group_key(group):
    return (str(group.get("name") or "").strip(), re.sub(r"\s+", "", str(group.get("address") or "")), str(group.get("service") or "").strip())


def _customer_address_key(group):
    return (str(group.get("name") or "").strip(), re.sub(r"\s+", "", str(group.get("address") or "")))


def _slot(date_value, start_value, end_value=""):
    date_s = str(date_value or "")[:10].replace("-", "/")
    period = str(start_value or "") if not end_value else f"{start_value}-{end_value}"
    period = re.sub(r"\s+", "", period).replace("～", "-").replace("~", "-")
    period = re.sub(r"(?<!\d)(\d{1,2}):(\d{2})", lambda match: f"{int(match.group(1)):02d}:{match.group(2)}", period)
    return date_s, period


def build_source_writeback(source_groups, results, skipped):
    """建立原排程工作表回寫計畫；通知只寫每組第一列。"""
    result_by_key = {_group_key(item.get("group") or {}): item for item in results or []}
    skipped_by_key = {}
    for entry in skipped or []:
        key = (str(entry.get("name") or "").strip(), re.sub(r"\s+", "", str(entry.get("address") or "")), str(entry.get("service") or "").strip())
        skipped_by_key.setdefault(key, []).append(entry)
    row_updates, insertions, reduction_rows = {}, [], []
    address_states = {}
    for item in results or []:
        key = _customer_address_key(item.get("group") or {})
        address_states.setdefault(key, []).append("失敗" if item.get("error") else "完成")
    for group in source_groups or []:
        entries = group.get("entries") or []
        if not entries:
            continue
        first_row = min(int(entry["row"]) for entry in entries)
        result_item = result_by_key.get(_group_key(group))
        backend = (result_item or {}).get("result") or {}
        actual = backend.get("orders_info") or []
        original_slots = [_slot(entry.get("date"), entry.get("start"), entry.get("end")) for entry in entries]
        actual_slots = [_slot(item.get("service_date"), item.get("period_s")) for item in actual]
        notice = result_item.get("text", "") if result_item and not result_item.get("error") else ""
        if result_item and result_item.get("error"):
            change = f"確認失敗：{result_item['error']}"
        elif len(actual_slots) < len(original_slots):
            change = f"減少：原工作表 {len(original_slots)} 筆，日曆＋後台確認 {len(actual_slots)} 筆"
            if first_row not in reduction_rows:
                reduction_rows.append(first_row)
        elif len(actual_slots) > len(original_slots):
            change = f"增加：原工作表 {len(original_slots)} 筆，日曆＋後台確認 {len(actual_slots)} 筆"
            for item in actual[len(original_slots):]:
                insertions.append({"after_row": max(int(entry["row"]) for entry in entries), "group": group, "order": item})
        elif sorted(actual_slots) != sorted(original_slots):
            before = "、".join(f"{date} {period}" for date, period in original_slots)
            after = "、".join(f"{date} {period}" for date, period in actual_slots)
            change = f"日期／時段異動：原 {before}；確認 {after}"
        else:
            change = "一致"
        if not actual and skipped_by_key.get(_group_key(group)) and not result_item:
            change = f"減少：原工作表 {len(original_slots)} 筆，日曆＋後台確認 0 筆"
            if first_row not in reduction_rows:
                reduction_rows.append(first_row)
        row_updates[first_row] = {
            "mail": group.get("email") or backend.get("email", ""),
            "LINE連結": group.get("line_url") or backend.get("line_url", ""),
            "通知內容": notice, "異動檢查": change,
        }
        if first_row in reduction_rows:
            row_updates[first_row]["狀態"] = "安排減少"
        for entry in entries:
            if int(entry["row"]) != first_row:
                row_updates[int(entry["row"])] = {"通知內容": "", "異動檢查": ""}
    # 顯示層級只看「姓名＋地址」：即使同地址分成不同服務類型，通知也只放最上方第一列。
    address_groups = {}
    for group in source_groups or []:
        entries = group.get("entries") or []
        if entries:
            address_groups.setdefault(_customer_address_key(group), []).extend(int(entry["row"]) for entry in entries)
    for customer_key, raw_rows in address_groups.items():
        rows = sorted(set(raw_rows)); first_row = rows[0]
        candidates = [row_updates.get(row, {}) for row in rows]
        combined = {
            "mail": next((item.get("mail") for item in candidates if item.get("mail")), ""),
            "LINE連結": next((item.get("LINE連結") for item in candidates if item.get("LINE連結")), ""),
            "通知內容": next((item.get("通知內容") for item in candidates if item.get("通知內容")), ""),
        }
        changes = list(dict.fromkeys(item.get("異動檢查") for item in candidates if item.get("異動檢查")))
        combined["異動檢查"] = "；".join(changes)
        if any(item.get("狀態") == "安排減少" for item in candidates): combined["狀態"] = "安排減少"
        states = address_states.get(customer_key, [])
        if "失敗" in states:
            combined["通知處理狀態"] = "失敗（下次將自動續跑）"
        elif "完成" in states:
            combined["通知處理狀態"] = "完成"
        else:
            combined["通知處理狀態"] = "完成（無日曆行程，略過）"
        row_updates[first_row] = combined
        for row in rows[1:]:
            row_updates.setdefault(row, {}).update({"通知內容": "", "異動檢查": "", "mail": "", "LINE連結": "", "通知處理狀態": ""})
    return row_updates, insertions, reduction_rows


def write_results_to_source(worksheet, source_groups, results, skipped):
    """一次批次回寫原排程工作表，並將減少安排的狀態標成紅底白字。"""
    headers = list(worksheet.row_values(1))
    for header in SOURCE_OUTPUT_HEADERS:
        if header not in headers:
            headers.append(header)
    worksheet.update(range_name="A1", values=[headers])
    header_index = {name: index + 1 for index, name in enumerate(headers) if name}
    row_updates, insertions, reduction_rows = build_source_writeback(source_groups, results, skipped)
    for insertion in sorted(insertions, key=lambda item: item["after_row"], reverse=True):
        values = [""] * len(headers)
        group, order = insertion["group"], insertion["order"]
        data = {"姓名": group.get("name", ""), "電話": group.get("phone", ""), "地址": group.get("address", ""),
                "購買項目": group.get("service", ""), "訂單編號": order.get("order_no", ""),
                "日期": order.get("service_date", ""), "開始時間": str(order.get("period_s", "")).split("-")[0].strip(),
                "結束時間": str(order.get("period_s", "")).split("-")[-1].strip(),
                "狀態": "待安排", "異動檢查": "新增安排列"}
        for name, value in data.items():
            if name in header_index:
                values[header_index[name] - 1] = value
        worksheet.insert_rows([values], row=insertion["after_row"] + 1, value_input_option="USER_ENTERED", inherit_from_before=True)
    shifts = lambda row: sum(1 for item in insertions if item["after_row"] < row)
    updates = []
    for row, values in row_updates.items():
        target_row = row + shifts(row)
        for name, value in values.items():
            if name in header_index:
                updates.append({"range": _a1(target_row, header_index[name]), "values": [[value]]})
    if updates:
        worksheet.batch_update(updates, value_input_option="USER_ENTERED")
    status_col = header_index.get("狀態")
    if status_col and reduction_rows:
        requests = []
        for row in reduction_rows:
            target_row = row + shifts(row)
            requests.append({"repeatCell": {"range": {"sheetId": worksheet.id, "startRowIndex": target_row - 1, "endRowIndex": target_row,
                "startColumnIndex": status_col - 1, "endColumnIndex": status_col}, "cell": {"userEnteredFormat": {
                    "backgroundColor": {"red": 0.85, "green": 0.0, "blue": 0.0},
                    "textFormat": {"foregroundColor": {"red": 1.0, "green": 1.0, "blue": 1.0}, "bold": True}}},
                "fields": "userEnteredFormat(backgroundColor,textFormat)"}})
        worksheet.spreadsheet.batch_update({"requests": requests})
    return len(row_updates), len(insertions), len(reduction_rows)


def _a1(row, column):
    letters = ""
    while column:
        column, remainder = divmod(column - 1, 26)
        letters = chr(65 + remainder) + letters
    return f"{letters}{row}"
