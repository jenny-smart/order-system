# -*- coding: utf-8 -*-
"""週末服務前 LINE 提醒：後台查詢、訊息產生與 Google Sheet 追蹤。"""

import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup
import requests

import orders
from shared.env_config import apply_env


TRACKING_SHEET_TITLE = "週末服務提醒"
LEGACY_TRACKING_HEADERS = [
    "訂單編號", "服務日期", "服務時間", "姓名", "電話", "地址", "LINE",
    "通知狀態", "通知時間", "回覆狀態", "回覆時間", "回覆備註", "最後更新",
]
SCHEDULED_TRACKING_HEADERS = [
    "訂單編號", "服務日期", "服務時間", "姓名", "電話", "地址", "LINE",
    "預約發送時間", "通知狀態", "通知時間", "回覆狀態", "回覆時間", "回覆備註", "最後更新",
]
TRACKING_HEADERS = [
    "訂單編號", "服務日期", "服務時間", "姓名", "電話", "地址", "LINE", "通知內容",
    "訂單狀態", "預約發送時間", "通知狀態", "通知時間", "回覆狀態", "回覆時間", "回覆備註",
    "發送錯誤", "最後更新",
]
NOTICE_STATUSES = ["待通知", "已排程", "已通知", "發送失敗"]
REPLY_STATUSES = ["未回覆", "已回覆", "需追蹤"]
TRACKED_ORDER_STATUSES = {"已付款", "取消訂單", "已退款"}
# 內勤工作表單（台北）的「週末提醒」分頁以 IMPORTRANGE 帶入追蹤表 A:H，I 欄回覆狀態為手動填寫；
# 新增追蹤列前要先在該分頁插入同樣位置的空白列，I 欄才不會錯位。
STAFF_SHEET_CATEGORY = "內勤工作表單"
STAFF_SHEET_AREA = "台北"
STAFF_SHEET_TITLE = "週末提醒"


def upcoming_weekend(reference=None):
    """回傳下一個週六、週日；週一至週五會指向當週週末。"""
    reference = reference or datetime.now(ZoneInfo("Asia/Taipei")).date()
    days_to_saturday = (5 - reference.weekday()) % 7
    if days_to_saturday == 0 and reference.weekday() >= 5:
        days_to_saturday = 7
    saturday = reference + timedelta(days=days_to_saturday)
    return saturday, saturday + timedelta(days=1)


def previous_workday(day_value, holidays=None):
    holidays = set(holidays or [])
    candidate = day_value - timedelta(days=1)
    while candidate.weekday() >= 5 or candidate in holidays:
        candidate -= timedelta(days=1)
    return candidate


def _configure_backend(env_name):
    apply_env(orders, env_name)


def _line_urls_from_html(raw_html):
    result = {}
    soup = BeautifulSoup(raw_html, "html.parser")
    for tr in soup.find_all("tr"):
        text = tr.get_text(" ", strip=True)
        match = re.search(orders.ORDER_NO_REGEX, text)
        if not match:
            continue
        link = tr.find("a", href=re.compile(r"chat\.line\.biz"))
        if link:
            result[match.group(0)] = str(link.get("href") or "").strip()
    return result


def line_id_from_chat_url(line_url):
    """從 LINE Official Account Manager 聊天網址取出客人的 LINE user ID。"""
    match = re.search(r"/chat/(U[0-9A-Za-z_-]+)(?:[/?#]|$)", str(line_url or ""))
    return match.group(1) if match else ""


def reminder_key(row):
    return f"{str(row.get('訂單編號', '')).strip()}|{str(row.get('服務日期', '')).strip()}"


def _taipei_schedule_iso(value):
    parsed = datetime.strptime(str(value).strip(), "%Y-%m-%d %H:%M")
    return parsed.replace(tzinfo=ZoneInfo("Asia/Taipei")).isoformat()


def _reminder_api(api_url, api_key, path, payload):
    if not str(api_url or "").strip() or not str(api_key or "").strip():
        raise RuntimeError("尚未設定 LINE_REMINDER_API_URL／LINE_REMINDER_API_KEY")
    response = requests.post(
        f"{str(api_url).rstrip('/')}{path}",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json=payload,
        timeout=20,
    )
    try:
        data = response.json()
    except ValueError:
        data = {}
    if not response.ok:
        raise RuntimeError(data.get("error") or f"LINE 提醒服務回傳 HTTP {response.status_code}")
    return data


def schedule_line_reminders(rows, api_url, api_key):
    payload = []
    skipped = []
    for row in rows:
        line_id = str(row.get("LINE ID") or "").strip() or line_id_from_chat_url(row.get("LINE"))
        if not line_id:
            skipped.append({"訂單編號": row.get("訂單編號", ""), "原因": "LINE 聊天網址沒有 LINE ID"})
            continue
        try:
            scheduled_at = _taipei_schedule_iso(row.get("預約發送時間"))
        except (TypeError, ValueError):
            skipped.append({"訂單編號": row.get("訂單編號", ""), "原因": "預約發送時間格式錯誤"})
            continue
        message = str(row.get("LINE訊息") or row.get("通知內容") or "").strip()
        if not message:
            skipped.append({"訂單編號": row.get("訂單編號", ""), "原因": "提醒訊息空白"})
            continue
        payload.append({
            "order_no": row.get("訂單編號", ""),
            "service_date": row.get("服務日期", ""),
            "line_user_id": line_id,
            "message_text": message,
            "scheduled_at": scheduled_at,
        })
    saved = []
    if payload:
        saved = _reminder_api(api_url, api_key, "/api/reminders/schedule", {"reminders": payload}).get("reminders", [])
    return saved, skipped


def fetch_line_reminder_statuses(rows, api_url, api_key):
    keys = [reminder_key(row) for row in rows if row.get("訂單編號") and row.get("服務日期")]
    if not keys:
        return []
    return _reminder_api(api_url, api_key, "/api/reminders/status", {"keys": keys}).get("reminders", [])


def fetch_line_recipients(query, api_url, api_key):
    """依客人最近傳入的文字或 LINE 名稱，取得 Webhook 真正的 userId。"""
    return _reminder_api(
        api_url, api_key, "/api/reminders/recipients", {"query": str(query or "").strip()}
    ).get("recipients", [])


def _display_taipei(iso_value):
    if not iso_value:
        return ""
    try:
        parsed = datetime.fromisoformat(str(iso_value).replace("Z", "+00:00"))
        return parsed.astimezone(ZoneInfo("Asia/Taipei")).strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return str(iso_value)


def apply_line_reminder_statuses(rows, statuses):
    status_map = {str(item.get("reminder_key", "")): item for item in statuses}
    merged = []
    for raw in rows:
        row = dict(raw)
        remote = status_map.get(reminder_key(row))
        if remote:
            remote_status = remote.get("status")
            row["LINE ID"] = remote.get("line_user_id") or row.get("LINE ID", "")
            row["預約發送時間"] = _display_taipei(remote.get("scheduled_at")) or row.get("預約發送時間", "")
            row["通知時間"] = _display_taipei(remote.get("sent_at")) or row.get("通知時間", "")
            row["回覆時間"] = _display_taipei(remote.get("replied_at")) or row.get("回覆時間", "")
            row["發送錯誤"] = remote.get("last_error") or ""
            if remote_status == "scheduled":
                row["通知狀態"] = "已排程"
            elif remote_status in ("sent", "replied"):
                row["通知狀態"] = "已通知"
            elif remote_status == "failed":
                row["通知狀態"] = "發送失敗"
            if remote_status == "replied":
                row["回覆狀態"] = "已回覆"
        merged.append(row)
    return merged


def tracking_rows_tsv(rows):
    headers = TRACKING_HEADERS
    lines = ["\t".join(headers)]
    for row in rows:
        lines.append("\t".join(str(row.get(header, "") or "").replace("\t", " ").replace("\n", " ") for header in headers))
    return "\n".join(lines)


def _name_phone(lines):
    for idx, line in enumerate(lines):
        if re.fullmatch(r"09\d{8}", str(line).strip()):
            return (str(lines[idx - 1]).strip() if idx else "", str(line).strip())
    return "", ""


def _address(lines):
    for line in lines:
        text = str(line or "").strip()
        if not text or "@" in text or text.upper() == "LINE":
            continue
        if re.search(r"(台|臺|新北|桃園|台中|臺中|台南|臺南|高雄|基隆|新竹|嘉義|苗栗|彰化|南投|雲林|屏東|宜蘭|花蓮|台東|臺東|澎湖|金門|連江).*(市|縣).*(區|鄉|鎮|市)", text):
            return text
    return ""


def _listed_service_date_time(lines):
    """訂單服務日期欄原始日期／時間（不套用簡訊時間）。"""
    _, service_date, _ = orders._extract_order_dates_from_block_lines(lines)
    service_time = ""
    if service_date:
        for idx, line in enumerate(lines):
            if str(line).strip().startswith(service_date):
                for following in lines[idx + 1:idx + 6]:
                    compact = str(following).replace(" ", "")
                    match = re.search(r"(\d{2}:\d{2})[-~～](\d{2}:\d{2})", compact)
                    if match:
                        service_time = f"{match.group(1)}-{match.group(2)}"
                        break
                break
    return service_date or "", service_time


def _sms_service_date_time(lines, fallback_date=""):
    """解析「簡訊時間／簡訊日期」欄位，可接受 YYYY-MM-DD 或 M/D。"""
    for idx, raw_line in enumerate(lines):
        line = str(raw_line or "").strip()
        if not re.search(r"簡訊.*(?:時間|日期)", line):
            continue
        value_lines = [line]
        value_lines.extend(str(item or "").strip() for item in lines[idx + 1:idx + 4])
        text = " ".join(value_lines)

        date_value = ""
        full_date = re.search(r"(\d{4})[/-](\d{1,2})[/-](\d{1,2})", text)
        if full_date:
            date_value = (
                f"{int(full_date.group(1)):04d}-"
                f"{int(full_date.group(2)):02d}-"
                f"{int(full_date.group(3)):02d}"
            )
        else:
            short_date = re.search(r"(?<!\d)(\d{1,2})/(\d{1,2})(?!\d)", text)
            if short_date and fallback_date:
                date_value = (
                    f"{str(fallback_date)[:4]}-"
                    f"{int(short_date.group(1)):02d}-"
                    f"{int(short_date.group(2)):02d}"
                )

        time_value = ""
        time_match = re.search(
            r"(?<!\d)(\d{1,2}:\d{2})\s*[-~～至]\s*(\d{1,2}:\d{2})(?!\d)",
            text,
        )
        if time_match:
            start_h, start_m = time_match.group(1).split(":")
            end_h, end_m = time_match.group(2).split(":")
            time_value = f"{int(start_h):02d}:{start_m}-{int(end_h):02d}:{end_m}"
        return date_value, time_value, True
    return "", "", False


def _service_date_time(lines):
    """提醒顯示時間：有簡訊時間就優先，否則使用訂單服務日期欄。"""
    service_date, service_time = _listed_service_date_time(lines)
    sms_date, sms_time, _ = _sms_service_date_time(lines, service_date)
    return sms_date or service_date, sms_time or service_time


def build_reminder_message(row, typhoon_reminder=False):
    service_date = datetime.strptime(row["service_date"], "%Y-%m-%d").date()
    weekdays = "一二三四五六日"
    when = f"{service_date.month}/{service_date.day}（{weekdays[service_date.weekday()]}）"
    if row.get("service_time"):
        when += f" {row['service_time']}"
    address_line = f"\n服務地址：{row['address']}" if row.get("address") else ""
    message = (
        f"您好，這是週末/例假日的清潔服務提醒：\n\n"
        f"服務時間：{when}{address_line}\n\n"
        "專員會在服務前5-10分鐘，以電話／門鈴／透過管理員等方式與您聯繫，"
        "煩請留意聯繫訊息。\n\n"
        "為確認您已收到提醒，請回覆「已收到」，謝謝您。"
    )
    if typhoon_reminder:
        return (
            f"{message}\n\n"
            "💡 貼心提醒：\n"
            "📅 例假日內勤人員休息通常不會處理訊息，建議您可以先留訊息待工作日上班時間處理喔，謝謝～\n"
            "🌀 若人事行政局公告放假，則該日服務取消，待工作日上班時間與您協調時間，"
            "造成不便，尚請見諒～"
        )
    return (
        f"{message}\n\n"
        "💡 貼心提醒：\n"
        "📅 例假日內勤人員休息通常不會處理訊息，您可以先留訊息待上班日上班時間處理喔，"
        "造成不便，尚請見諒，謝謝～"
    )


def find_paid_weekend_orders(
    env_name, backend_email, backend_password, clean_date_s, clean_date_e,
    max_pages=20, typhoon_reminder=False,
):
    """查詢服務日期區間內已付款／取消／已退款訂單；回傳後由 merge 只顯示已付款提醒。"""
    _configure_backend(env_name)
    session = orders.requests.Session()
    if not orders.login(session, backend_email, backend_password):
        raise RuntimeError("後台登入失敗，請確認帳號密碼")

    found = {}
    hit_page_limit = True
    for page in range(1, max_pages + 1):
        params = dict(orders.PURCHASE_FILTER_PARAMS_TEMPLATE)
        params.update({
            "clean_date_s": clean_date_s,
            "clean_date_e": clean_date_e,
            "p_board": "on",
            "page": str(page),
        })
        params.pop("purchase_status", None)
        response = session.get(orders.PURCHASE_URL, params=params, headers=orders.HEADERS, allow_redirects=True)
        if response.status_code != 200:
            hit_page_limit = False
            break
        blocks = orders.extract_order_cards_from_purchase_html(response.text)
        if not blocks:
            hit_page_limit = False
            break
        line_urls = _line_urls_from_html(response.text)
        for block in blocks:
            lines = block.get("lines", [])
            joined = "\n".join(lines)
            status_match = re.search(r"付款狀態[：:]\s*([^\n]+)", joined)
            order_status = status_match.group(1).strip() if status_match else ""
            if order_status not in TRACKED_ORDER_STATUSES:
                continue
            listed_date, _ = _listed_service_date_time(lines)
            if not listed_date or not (clean_date_s <= listed_date <= clean_date_e):
                continue
            service_date, service_time = _service_date_time(lines)
            name, phone = _name_phone(lines)
            order_no = block.get("order_no", "")
            row = {
                "order_no": order_no,
                "service_date": service_date,
                "service_time": service_time,
                "name": name,
                "phone": phone,
                "address": _address(lines),
                "line_url": line_urls.get(order_no, ""),
                "order_status": order_status,
            }
            row["message"] = (
                build_reminder_message(row, typhoon_reminder=typhoon_reminder)
                if order_status == "已付款" else ""
            )
            found[order_no] = row
        if len(blocks) < 20:
            hit_page_limit = False
            break

    rows = sorted(found.values(), key=lambda item: (item["service_date"], item["service_time"], item["name"]))
    paid_count = sum(1 for item in rows if item.get("order_status") == "已付款")
    return rows, {
        "scanned": len(found),
        "paid": paid_count,
        "hit_page_limit": hit_page_limit,
        "base_url": orders.BASE_URL,
    }


def _tracking_worksheet():
    client = orders.build_gsheet_client()
    spreadsheet = client.open_by_key(orders.GOOGLE_SHEET_ID)
    try:
        worksheet = spreadsheet.worksheet(TRACKING_SHEET_TITLE)
    except orders.gspread.WorksheetNotFound:
        worksheet = spreadsheet.add_worksheet(title=TRACKING_SHEET_TITLE, rows=1000, cols=len(TRACKING_HEADERS))
    current_headers = worksheet.row_values(1)
    while current_headers and not str(current_headers[-1]).strip():
        current_headers.pop()
    if worksheet.col_count < len(TRACKING_HEADERS):
        worksheet.resize(cols=len(TRACKING_HEADERS))
    if not current_headers:
        worksheet.update(range_name="A1", values=[TRACKING_HEADERS])
    elif (
        current_headers in (LEGACY_TRACKING_HEADERS, SCHEDULED_TRACKING_HEADERS)
        or (
            current_headers
            and current_headers[0] == "訂單編號"
            and len(current_headers) == len(set(current_headers))
        )
    ):
        old_values = worksheet.get_all_values()
        unknown_headers = [header for header in current_headers if header not in TRACKING_HEADERS]
        if unknown_headers:
            backup_title = (
                f"{TRACKING_SHEET_TITLE}_備份_"
                f"{datetime.now(ZoneInfo('Asia/Taipei')).strftime('%Y%m%d_%H%M%S_%f')}"
            )
            backup_cols = max((len(row) for row in old_values), default=1)
            backup = spreadsheet.add_worksheet(
                title=backup_title,
                rows=max(len(old_values), 1),
                cols=max(backup_cols, 1),
            )
            if old_values:
                backup.update(range_name="A1", values=old_values)
        migrated = [TRACKING_HEADERS]
        for values in old_values[1:]:
            old = dict(zip(current_headers, values + [""] * (len(current_headers) - len(values))))
            if not str(old.get("通知內容") or "").strip():
                old["通知內容"] = _tracking_message(old, {})
            if not str(old.get("訂單狀態") or "").strip():
                old["訂單狀態"] = "已付款"
            migrated.append([old.get(header, "") for header in TRACKING_HEADERS])
        worksheet.update(range_name="A1", values=migrated)
        if worksheet.col_count != len(TRACKING_HEADERS):
            worksheet.resize(cols=len(TRACKING_HEADERS))
    elif current_headers != TRACKING_HEADERS:
        raise RuntimeError(f"Google Sheet「{TRACKING_SHEET_TITLE}」欄位格式不符，為避免覆蓋既有資料，已停止寫入")
    return worksheet


def load_tracking_rows():
    worksheet = _tracking_worksheet()
    values = worksheet.get_all_values()
    return [dict(zip(TRACKING_HEADERS, row + [""] * (len(TRACKING_HEADERS) - len(row)))) for row in values[1:] if row and row[0]]


def _order_key(item):
    return reminder_key({"訂單編號": item.get("order_no", ""), "服務日期": item.get("service_date", "")})


def merge_tracking_rows(order_rows, existing_rows, scheduled_at=""):
    """以「訂單編號＋服務日期」比對；訂單改期後的新日期視為新增，避免漏提醒。"""
    existing = {reminder_key(row): dict(row) for row in existing_rows}

    status_updates = []
    for item in order_rows:
        key = _order_key(item)
        old = existing.get(key)
        order_status = item.get("order_status", "")
        if old and order_status and old.get("訂單狀態") != order_status:
            updated = dict(old)
            updated["訂單狀態"] = order_status
            status_updates.append(updated)
            existing[key] = updated
    if status_updates:
        save_tracking_rows(status_updates)

    merged = []
    for item in order_rows:
        if item.get("order_status") != "已付款":
            continue
        old = existing.get(_order_key(item), {})
        message = item.get("message", "")
        merged.append({
            "資料狀態": "已存在" if old else "新增",
            "訂單編號": item["order_no"], "服務日期": item["service_date"],
            "服務時間": item.get("service_time", ""), "姓名": item.get("name", ""),
            "電話": item.get("phone", ""), "地址": item.get("address", ""),
            "LINE": item.get("line_url", ""), "通知內容": old.get("通知內容") or message,
            "訂單狀態": "已付款",
            "預約發送時間": old.get("預約發送時間") or scheduled_at,
            "通知狀態": old.get("通知狀態") or "待通知",
            "通知時間": old.get("通知時間", ""), "回覆狀態": old.get("回覆狀態") or "未回覆",
            "回覆時間": old.get("回覆時間", ""), "回覆備註": old.get("回覆備註", ""),
            "發送錯誤": old.get("發送錯誤", ""),
            "最後更新": old.get("最後更新", ""), "LINE訊息": message,
        })
    return merged


def _tracking_message(raw, old):
    message = str(raw.get("通知內容") or raw.get("LINE訊息") or old.get("通知內容") or "").strip()
    if message:
        return message
    service_date = str(raw.get("服務日期") or old.get("服務日期") or "").strip()
    if not service_date:
        return ""
    try:
        return build_reminder_message({
            "service_date": service_date,
            "service_time": str(raw.get("服務時間") or old.get("服務時間") or "").strip(),
            "address": str(raw.get("地址") or old.get("地址") or "").strip(),
        })
    except (TypeError, ValueError):
        return ""


def plan_tracking_rows(existing_rows, rows, now):
    """依訂單編號＋服務日期 upsert；回傳（排序後全部列, 新增列的工作表列號, 本次寫入筆數）。"""
    existing = {reminder_key(row): row for row in existing_rows}
    incoming = {}
    if hasattr(rows, "to_dict"):
        rows = rows.to_dict("records")
    for raw in rows:
        row = {header: str(raw.get(header, "") or "") for header in TRACKING_HEADERS}
        old = existing.get(reminder_key(row), {})
        if not row["通知內容"]:
            row["通知內容"] = _tracking_message(raw, old)
        if not row["訂單狀態"]:
            row["訂單狀態"] = str(raw.get("訂單狀態") or old.get("訂單狀態") or "已付款")
        if row["通知狀態"] == "已通知" and not row["通知時間"]:
            row["通知時間"] = old.get("通知時間") or now
        if row["回覆狀態"] == "已回覆" and not row["回覆時間"]:
            row["回覆時間"] = old.get("回覆時間") or now
        row["最後更新"] = now
        incoming[reminder_key(row)] = row
    new_keys = set(incoming) - set(existing)
    existing.update(incoming)
    all_rows = list(existing.values())
    all_rows.sort(key=lambda item: (item.get("服務日期", ""), item.get("服務時間", ""), item.get("訂單編號", "")), reverse=True)
    new_positions = [index + 2 for index, row in enumerate(all_rows) if reminder_key(row) in new_keys]
    return all_rows, new_positions, len(incoming)


def _row_runs(positions):
    """把遞增列號合併成連續區段 [(起始列, 列數)]。"""
    runs = []
    for position in sorted(positions):
        if runs and runs[-1][0] + runs[-1][1] == position:
            runs[-1] = (runs[-1][0], runs[-1][1] + 1)
        else:
            runs.append((position, 1))
    return runs


def insert_staff_sheet_rows(positions):
    """在內勤工作表單「週末提醒」分頁插入空白列（列號為新增後的最終位置，由上往下插入）。"""
    if not positions:
        return
    from year_roots import root_file_id

    client = orders.build_gsheet_client()
    spreadsheet = client.open_by_key(root_file_id(STAFF_SHEET_CATEGORY, STAFF_SHEET_AREA))
    worksheet = spreadsheet.worksheet(STAFF_SHEET_TITLE)
    spreadsheet.batch_update({"requests": [
        {"insertDimension": {
            "range": {
                "sheetId": worksheet.id, "dimension": "ROWS",
                "startIndex": start - 1, "endIndex": start - 1 + count,
            },
            "inheritFromBefore": False,
        }}
        for start, count in _row_runs(positions)
    ]})


def save_tracking_rows(rows):
    """依訂單編號＋服務日期 upsert；狀態首次改變時自動補台北時間。
    有新增列時，先在內勤工作表單「週末提醒」插入對應空白列再寫入追蹤表。"""
    worksheet = _tracking_worksheet()
    existing_rows = load_tracking_rows()
    now = datetime.now(ZoneInfo("Asia/Taipei")).strftime("%Y-%m-%d %H:%M")
    all_rows, new_positions, count = plan_tracking_rows(existing_rows, rows, now)
    insert_staff_sheet_rows(new_positions)
    matrix = [TRACKING_HEADERS] + [[row.get(header, "") for header in TRACKING_HEADERS] for row in all_rows]
    old_row_count = len(worksheet.get_all_values())
    worksheet.update(range_name="A1", values=matrix)
    if old_row_count > len(matrix):
        worksheet.batch_clear([f"A{len(matrix) + 1}:Q{old_row_count}"])
    return count
