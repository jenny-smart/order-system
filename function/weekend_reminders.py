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
TRACKED_ORDER_STATUSES = {"待付款", "已付款", "取消訂單", "已退款"}
# 提醒名單只列待付款／已付款（取消、退款只用來更新既有列的狀態）
REMINDER_ORDER_STATUSES = ("待付款", "已付款")
# 內勤工作表單（台北）「週末提醒」分頁：A:H 由程式直接寫入（不再用 IMPORTRANGE，才能保留超連結），
# 訂購人連到 LINE 聊天、電話連到後台電話搜尋結果；I 欄起（回覆狀態等）為手動／其他排程填寫，
# 每次寫入都依「訂單編號＋服務日期」重新對齊，排序變動也不會錯位。
STAFF_SHEET_CATEGORY = "內勤工作表單"
STAFF_SHEET_AREA = "台北"
STAFF_SHEET_TITLE = "週末提醒"
STAFF_HEADERS = ["訂單編號", "服務日期", "服務時間", "訂購人", "電話", "地址", "付款狀態", "通知內容"]


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


WEEKDAYS = "一二三四五六日"
LEMON_STAFF_RE = re.compile(r"檸檬人\s*\d+")
MERGED_NOTE_PREFIX = "併入 "
OVERLAP_SKIP_NOTE_PREFIX = "時段重疊不另發"
OVERLAP_CHECK_NOTE_PREFIX = "時段重疊待確認"


def _when_text(service_date_text, service_time=""):
    service_date = datetime.strptime(service_date_text, "%Y-%m-%d").date()
    when = f"{service_date.month}/{service_date.day}（{WEEKDAYS[service_date.weekday()]}）"
    return f"{when} {service_time}" if service_time else when


def _confirm_url(order_no, service_date):
    """訂單的「確認收到」連結；未設定 LINE_REMINDER_API_KEY 時為空字串（訊息維持原樣）。"""
    try:
        from shared.reminder_confirm import confirm_url

        return confirm_url(order_no, service_date)
    except Exception:
        return ""


def _reminder_text(detail, typhoon_reminder=False, confirm_url=""):
    confirm_line = (
        f"為確認您已收到提醒，請回覆「已收到」，或點以下連結確認：\n{confirm_url}\n謝謝您。"
        if confirm_url else "為確認您已收到提醒，請回覆「已收到」，謝謝您。"
    )
    message = (
        f"您好，這是週末/例假日的清潔服務提醒：\n\n"
        f"{detail}\n\n"
        "專員會在服務前5-10分鐘，以電話／門鈴／透過管理員等方式與您聯繫，"
        "煩請留意聯繫訊息。\n\n"
        f"{confirm_line}"
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


def build_reminder_message(row, typhoon_reminder=False):
    address_line = f"\n服務地址：{row['address']}" if row.get("address") else ""
    detail = f"服務時間：{_when_text(row['service_date'], row.get('service_time', ''))}{address_line}"
    return _reminder_text(detail, typhoon_reminder, _confirm_url(row.get("order_no"), row["service_date"]))


def build_combined_reminder_message(rows, typhoon_reminder=False):
    """同一人多筆：時間（與地址）併在同一則；地址都相同時只列一次。"""
    rows = sorted(rows, key=lambda item: (item.get("service_date", ""), item.get("service_time", "")))
    addresses = {_compact(item.get("address")) for item in rows}
    if len(addresses) <= 1:
        lines = [_when_text(item["service_date"], item.get("service_time", "")) for item in rows]
        address = rows[0].get("address", "")
        detail = "服務時間：\n" + "\n".join(lines) + (f"\n服務地址：{address}" if address else "")
    else:
        lines = [
            f"{_when_text(item['service_date'], item.get('service_time', ''))}　{item.get('address', '')}".rstrip()
            for item in rows
        ]
        detail = "服務時間及地址：\n" + "\n".join(lines)
    # 合併提醒只附主單（最早那筆）的連結；被併入的訂單由同步程式跟著主單記為已回覆。
    return _reminder_text(detail, typhoon_reminder, _confirm_url(rows[0].get("order_no"), rows[0]["service_date"]))


def _compact(value):
    return re.sub(r"\s+", "", str(value or ""))


def _time_range(value):
    match = re.search(r"(\d{1,2}):(\d{2})\s*[-~～]\s*(\d{1,2}):(\d{2})", str(value or ""))
    if not match:
        return None
    h1, m1, h2, m2 = (int(part) for part in match.groups())
    return h1 * 60 + m1, h2 * 60 + m2


def _overlapping(a, b):
    """同地址、同服務日、時段有交集。"""
    if a.get("service_date") != b.get("service_date") or _compact(a.get("address")) != _compact(b.get("address")):
        return False
    ra, rb = _time_range(a.get("service_time")), _time_range(b.get("service_time"))
    if not ra or not rb:
        return True  # 同地址同日但時間看不懂，當作重疊交給規則／人工判斷
    return ra[0] < rb[1] and rb[0] < ra[1]


def _customer_key(item):
    phone = re.sub(r"\D", "", str(item.get("phone") or ""))
    return phone or str(item.get("name") or "").strip()


def combine_customer_reminders(items, fixed_keys=(), typhoon_reminder=False):
    """同一人多筆已付款訂單合併成一則提醒。

    - 同地址且時間重疊：一筆有檸檬人、另一筆沒有 → 以沒有檸檬人的那筆時間為主，檸檬人那筆不另發；
      兩筆都有或都沒有 → 兩個時段都列出，在主列備註「時段重疊待確認」。
    - 其他（時間或地址不重疊）→ 時間與地址併在同一則，放在最早那筆；其他筆通知內容留空、備註「併入 主單號」。
    fixed_keys：追蹤表已存在的列（不改內容，只用來判斷重疊）。
    回傳 {order_key: {"message": ..., "note": ...}}，只含需要改變的新列。
    """
    fixed = set(fixed_keys or ())
    groups = {}
    for item in items:
        if item.get("order_status", "已付款") != "已付款" or not item.get("service_date"):
            continue
        groups.setdefault(_customer_key(item), []).append(item)

    result = {}
    for group in groups.values():
        if len(group) < 2:
            continue
        group = sorted(group, key=lambda item: (item.get("service_date", ""), item.get("service_time", ""), item.get("order_no", "")))
        excluded, flagged = {}, set()
        for i, a in enumerate(group):
            for b in group[i + 1:]:
                if not _overlapping(a, b):
                    continue
                if bool(a.get("has_lemon")) != bool(b.get("has_lemon")):
                    loser, winner = (a, b) if a.get("has_lemon") else (b, a)
                    excluded[_order_key(loser)] = winner.get("order_no", "")
                else:
                    flagged.update({_order_key(a), _order_key(b)})
        new_items = [item for item in group if _order_key(item) not in fixed]
        kept_new = [item for item in new_items if _order_key(item) not in excluded]
        for item in new_items:
            key = _order_key(item)
            if key in excluded:
                winner = excluded[key]
                result[key] = {
                    "message": "",
                    "note": f"{OVERLAP_SKIP_NOTE_PREFIX}：與 {winner} 時段重疊（此筆為檸檬人），以 {winner} 時間為準",
                }
        if not kept_new:
            continue
        primary = kept_new[0]
        flagged_nos = [item.get("order_no", "") for item in kept_new if _order_key(item) in flagged]
        note = f"{OVERLAP_CHECK_NOTE_PREFIX}：{'、'.join(flagged_nos)}" if len(flagged_nos) > 1 else ""
        if len(kept_new) > 1:
            result[_order_key(primary)] = {
                "message": build_combined_reminder_message(kept_new, typhoon_reminder),
                "note": note or f"合併 {len(kept_new)} 筆：{'、'.join(item.get('order_no', '') for item in kept_new)}",
            }
            for item in kept_new[1:]:
                result[_order_key(item)] = {"message": "", "note": f"{MERGED_NOTE_PREFIX}{primary.get('order_no', '')}"}
    return result


def is_merged_note(note):
    text = str(note or "").strip()
    return text.startswith(MERGED_NOTE_PREFIX) or text.startswith(OVERLAP_SKIP_NOTE_PREFIX)


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
                "has_lemon": bool(LEMON_STAFF_RE.search(joined)),
                "typhoon_reminder": bool(typhoon_reminder),
            }
            row["message"] = (
                build_reminder_message(row, typhoon_reminder=typhoon_reminder)
                if order_status in REMINDER_ORDER_STATUSES else ""
            )
            found[order_no] = row
        if len(blocks) < 20:
            hit_page_limit = False
            break

    rows = sorted(found.values(), key=lambda item: (item["service_date"], item["service_time"], item["name"]))
    paid_count = sum(1 for item in rows if item.get("order_status") == "已付款")
    pending_count = sum(1 for item in rows if item.get("order_status") == "待付款")
    return rows, {
        "scanned": len(found),
        "paid": paid_count,
        "pending": pending_count,
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

    paid = [item for item in order_rows if item.get("order_status") in REMINDER_ORDER_STATUSES]
    fixed_keys = {_order_key(item) for item in paid if _order_key(item) in existing}
    typhoon = any(item.get("typhoon_reminder") for item in paid)
    combined = combine_customer_reminders(paid, fixed_keys, typhoon_reminder=typhoon)

    merged = []
    for item in paid:
        old = existing.get(_order_key(item), {})
        message = item.get("message", "")
        note = old.get("回覆備註", "")
        if not old and _order_key(item) in combined:
            message = combined[_order_key(item)]["message"]
            note = combined[_order_key(item)]["note"]
        merged.append({
            "資料狀態": "已存在" if old else "新增",
            "訂單編號": item["order_no"], "服務日期": item["service_date"],
            "服務時間": item.get("service_time", ""), "姓名": item.get("name", ""),
            "電話": item.get("phone", ""), "地址": item.get("address", ""),
            "LINE": item.get("line_url", ""), "通知內容": (
                (old.get("通知內容") or ("" if is_merged_note(old.get("回覆備註")) else message)) if old else message
            ),
            "訂單狀態": item.get("order_status") or "已付款",
            "預約發送時間": old.get("預約發送時間") or scheduled_at,
            "通知狀態": old.get("通知狀態") or "待通知",
            "通知時間": old.get("通知時間", ""), "回覆狀態": old.get("回覆狀態") or "未回覆",
            "回覆時間": old.get("回覆時間", ""), "回覆備註": note,
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
            "order_no": str(raw.get("訂單編號") or old.get("訂單編號") or "").strip(),
            "service_date": service_date,
            "service_time": str(raw.get("服務時間") or old.get("服務時間") or "").strip(),
            "address": str(raw.get("地址") or old.get("地址") or "").strip(),
        })
    except (TypeError, ValueError):
        return ""


def _name_order(row):
    return (str(row.get("姓名", "") or ""), str(row.get("訂單編號", "") or ""))


def order_tracking_rows(old_rows, new_rows, resort=False):
    """服務日期新→舊；同一天內既有列維持原順序，新增列依訂購人、訂單編號排在該日最下方。
    resort=True（第一次改版）時，同一天全部依訂購人、訂單編號重排。"""
    blocks = {}
    for row in old_rows:
        blocks.setdefault(row.get("服務日期", ""), []).append(row)
    if resort:
        for rows in blocks.values():
            rows.sort(key=_name_order)
    for row in sorted(new_rows, key=_name_order):
        blocks.setdefault(row.get("服務日期", ""), []).append(row)
    return [row for day in sorted(blocks, reverse=True) for row in blocks[day]]


def plan_tracking_rows(existing_rows, rows, now, resort=False):
    """依訂單編號＋服務日期 upsert；回傳（排序後全部列, 新增列的工作表列號, 本次寫入筆數）。"""
    existing = {}
    for row in existing_rows:
        existing.setdefault(reminder_key(row), row)
    incoming = {}
    if hasattr(rows, "to_dict"):
        rows = rows.to_dict("records")
    for raw in rows:
        row = {header: str(raw.get(header, "") or "") for header in TRACKING_HEADERS}
        old = existing.get(reminder_key(row), {})
        if not row["通知內容"] and not is_merged_note(row["回覆備註"] or old.get("回覆備註")):
            row["通知內容"] = _tracking_message(raw, old)
        if not row["訂單狀態"]:
            row["訂單狀態"] = str(raw.get("訂單狀態") or old.get("訂單狀態") or "已付款")
        if row["通知狀態"] == "已通知" and not row["通知時間"]:
            row["通知時間"] = old.get("通知時間") or now
        if row["回覆狀態"] == "已回覆" and not row["回覆時間"]:
            row["回覆時間"] = old.get("回覆時間") or now
        row["最後更新"] = now
        incoming[reminder_key(row)] = row
    new_keys = [key for key in incoming if key not in existing]
    old_keys = list(existing)
    existing.update(incoming)
    all_rows = order_tracking_rows(
        [existing[key] for key in old_keys], [incoming[key] for key in new_keys], resort=resort,
    )
    new_set = set(new_keys)
    new_positions = [index + 2 for index, row in enumerate(all_rows) if reminder_key(row) in new_set]
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


def _text_cell(value):
    """USER_ENTERED 寫入時保持純文字（日期、0 開頭電話、= 開頭文字都不被轉換）。"""
    text = str(value or "")
    return f"'{text}" if text else ""


def _manual_cell(raw, formatted):
    """I 欄起手動欄位重寫時的值：公式照舊、文字保持文字、數字／日期用顯示值重新解析。"""
    if isinstance(raw, str):
        return raw if raw.startswith("=") else _text_cell(raw)
    if raw is None or raw == "":
        return ""
    return str(formatted if formatted not in (None, "") else raw)


def staff_data_cells(row, base_url):
    """「週末提醒」A:H：訂購人連 LINE 聊天、電話連後台電話搜尋結果。"""
    from shared.customer_memo_schedule import name_cell, phone_cell

    name = str(row.get("姓名", "") or "")
    line_url = str(row.get("LINE", "") or "").strip()
    phone = str(row.get("電話", "") or "").strip()
    return [
        _text_cell(row.get("訂單編號")), _text_cell(row.get("服務日期")), _text_cell(row.get("服務時間")),
        name_cell(name, line_url) if line_url and name else _text_cell(name),
        phone_cell(base_url, phone) if phone else "",
        _text_cell(row.get("地址")), _text_cell(row.get("訂單狀態")), _text_cell(row.get("通知內容")),
    ]


def plan_staff_sheet(formatted, raw, tracking_rows, base_url):
    """內勤「週末提醒」整頁要寫入的值：A:H 依追蹤表重建，I 欄起依訂單編號＋服務日期對齊搬移。
    分頁上有、追蹤表沒有的列（手動加的）保留在最下方，不會遺失。"""
    width = len(STAFF_HEADERS)
    total = max([len(r) for r in formatted] + [len(r) for r in raw] + [width])

    def cell(rows, i, j):
        return rows[i][j] if i < len(rows) and j < len(rows[i]) else ""

    def manual(i):
        return [_manual_cell(cell(raw, i, j), cell(formatted, i, j)) for j in range(width, total)]

    by_key, extras = {}, []
    for i in range(1, max(len(formatted), len(raw))):
        order_no, day = str(cell(formatted, i, 0)).strip(), str(cell(formatted, i, 1)).strip()
        cells = manual(i)
        key = f"{order_no}|{day}"
        if order_no and key not in by_key:
            by_key[key] = (i, cells)
        elif order_no or any(cells):
            extras.append((i, cells))

    matrix = [STAFF_HEADERS + manual(0)]
    used = set()
    for row in tracking_rows:
        key = reminder_key(row)
        found = by_key.get(key)
        used.add(key)
        matrix.append(staff_data_cells(row, base_url) + (found[1] if found else [""] * (total - width)))
    leftovers = [item for key, item in by_key.items() if key not in used] + extras
    for i, cells in sorted(leftovers):
        data = [_manual_cell(cell(raw, i, j), cell(formatted, i, j)) for j in range(width)]
        matrix.append(data + cells)
    return matrix


def _staff_worksheet():
    from year_roots import root_file_id

    client = orders.build_gsheet_client()
    return client.open_by_key(root_file_id(STAFF_SHEET_CATEGORY, STAFF_SHEET_AREA)).worksheet(STAFF_SHEET_TITLE)


def read_staff_sheet(worksheet):
    from gspread.utils import ValueRenderOption

    formatted = worksheet.get_values()
    raw = worksheet.get_values(value_render_option=ValueRenderOption.formula)
    return formatted, raw


def is_importrange_layout(raw):
    first = str(raw[0][0]) if raw and raw[0] else ""
    return first.lstrip().lower().startswith("=importrange")


def write_staff_sheet(worksheet, matrix, old_row_count):
    from gspread.utils import rowcol_to_a1

    width = max(len(row) for row in matrix)
    matrix = [row + [""] * (width - len(row)) for row in matrix]
    if worksheet.row_count < len(matrix):
        worksheet.add_rows(len(matrix) - worksheet.row_count + 50)
    if worksheet.col_count < width:
        worksheet.resize(cols=width)
    worksheet.update(range_name="A1", values=matrix, value_input_option="USER_ENTERED")
    if old_row_count > len(matrix):
        worksheet.batch_clear([f"A{len(matrix) + 1}:{rowcol_to_a1(old_row_count, width)}"])


def save_tracking_rows(rows):
    """依訂單編號＋服務日期 upsert；狀態首次改變時自動補台北時間。
    寫入追蹤表後，同步重建內勤工作表單「週末提醒」A:H（I 欄起依訂單編號＋服務日期對齊）。"""
    worksheet = _tracking_worksheet()
    existing_rows = load_tracking_rows()
    staff = _staff_worksheet()
    formatted, raw = read_staff_sheet(staff)  # 先讀：之後追蹤表重排，IMPORTRANGE 會跟著變
    now = datetime.now(ZoneInfo("Asia/Taipei")).strftime("%Y-%m-%d %H:%M")
    all_rows, _, count = plan_tracking_rows(existing_rows, rows, now, resort=is_importrange_layout(raw))
    matrix = [TRACKING_HEADERS] + [[row.get(header, "") for header in TRACKING_HEADERS] for row in all_rows]
    old_row_count = len(worksheet.get_all_values())
    worksheet.update(range_name="A1", values=matrix)
    if old_row_count > len(matrix):
        worksheet.batch_clear([f"A{len(matrix) + 1}:Q{old_row_count}"])
    write_staff_sheet(
        staff, plan_staff_sheet(formatted, raw, all_rows, orders.BASE_URL), max(len(formatted), len(raw)),
    )
    return count
