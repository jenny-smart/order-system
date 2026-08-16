# -*- coding: utf-8 -*-
"""通用文字/日期/地址/時段解析工具，供 orders.py／quick_order.py 及其他模組共用。

純函式集合，不含業務邏輯、不連後台/Google API。
"""

import re
from datetime import date, datetime

import requests
import pandas as pd

import orders

PAYWAY_MAP = {"信用卡": "1", "ATM": "2", "儲值金": "4"}
CLEAN_TYPE_LABELS = ["居家清潔", "辦公室清潔", "裝修細清", "大掃除"]
PERIOD_DISPLAY_INFO = {
    "08:30-12:30": ("4小時", False), "09:00-11:00": ("2小時", False),
    "09:00-12:00": ("3小時", False), "14:00-16:00": ("2小時", False),
    "14:00-17:00": ("3小時", False), "14:00-18:00": ("4小時", False),
    "09:00-16:00": ("6小時", True), "09:00-18:00": ("8小時", True),
}


def is_blank(value):
    return str(value).strip() in ("", "nan", "None")


def normalize_phone(phone_value):
    phone = str(phone_value).strip().replace(".0", "")
    phone = re.sub(r"\D", "", phone)
    if len(phone) == 9:
        phone = "0" + phone
    return phone


def normalize_text_for_parse(text):
    return re.sub(r"\s+", "", str(text or ""))


def normalize_addr_for_match(addr):
    return re.sub(r"\s+", "", str(addr or "")).strip()


def same_address(a, b):
    return normalize_addr_for_match(a) == normalize_addr_for_match(b)


def first_nonzero(*values, default="0"):
    for value in values:
        text = str(value if value is not None else "").strip()
        if text not in ("", "0", "0.0", "nan", "None"):
            return text
    return str(default)


def find_nested_value(obj, keys):
    key_set = {str(k) for k in keys}

    if isinstance(obj, dict):
        for key, value in obj.items():
            if str(key) in key_set and value not in (None, ""):
                return value

        for value in obj.values():
            found = find_nested_value(value, key_set)
            if found not in (None, ""):
                return found

    elif isinstance(obj, list):
        for item in obj:
            found = find_nested_value(item, key_set)
            if found not in (None, ""):
                return found

    return ""


def parse_date_value(date_value):
    if isinstance(date_value, pd.Timestamp):
        return date_value.to_pydatetime()

    text = str(date_value).strip()
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            pass

    raise Exception(f"無法解析日期: {date_value}")


def get_date_str(date_value):
    return parse_date_value(date_value).strftime("%Y-%m-%d")


def normalize_sheet_date(date_value):
    return get_date_str(date_value)


def is_weekend(date_value):
    return parse_date_value(date_value).weekday() >= 5


def parse_time_slot(start_time_str, end_time_str):
    if not str(start_time_str).strip() or not str(end_time_str).strip():
        raise Exception(f"開始時間或結束時間為空：{start_time_str} / {end_time_str}")

    def to_hm(t):
        text = str(t).strip()
        parts = text.split(":")
        if not parts or not parts[0].strip():
            raise Exception(f"時間格式錯誤：{t}")
        h = int(parts[0])
        m = int(parts[1]) if len(parts) > 1 and parts[1].strip() else 0
        return h, m

    sh, sm = to_hm(start_time_str)
    eh, em = to_hm(end_time_str)
    return sh, sm, eh, em


def calc_hours_from_time(start_time_str, end_time_str):
    sh, sm, eh, em = parse_time_slot(start_time_str, end_time_str)
    hours = (eh - sh) + (em - sm) / 60.0
    return hours if hours > 0 else None


def calc_effective_hours_from_time(start_time_str, end_time_str):
    hours = calc_hours_from_time(start_time_str, end_time_str)
    if hours is None:
        return None
    if hours >= 7:
        hours -= 1
    return hours


def normalize_period_text(start_time_str, end_time_str):
    sh, sm, eh, em = parse_time_slot(start_time_str, end_time_str)
    return f"{sh:02d}:{sm:02d}-{eh:02d}:{em:02d}"


def display_period_text(start_time_str, end_time_str):
    sh, sm, eh, em = parse_time_slot(start_time_str, end_time_str)
    return f"{sh:02d}:{sm:02d} - {eh:02d}:{em:02d}"


def normalize_sheet_period(start_time_str, end_time_str):
    return normalize_period_text(start_time_str, end_time_str)


def slot_duration_hours(slot_text):
    start_text, end_text = slot_text.split("-")
    return calc_effective_hours_from_time(start_text, end_text)


def slot_start_hour(slot_text):
    return int(slot_text.split("-")[0].split(":")[0])


def is_morning_slot(slot_text):
    return slot_start_hour(slot_text) < 12


def map_to_system_slot(start_time_str, end_time_str, service_text=None):
    """
    重要規則：
    1. Google Sheet 的開始/結束時間 = 客戶實際要約的服務時段，也用來查班表。
       例如 Sheet 是 09:00-12:00，就一定查 09:00-12:00。
    2. calculate_hour 回傳的 hour 只用來算價格，不用來反推班表時段。
    3. 只有特殊時段 10:00-12:00，要送系統 09:00-11:00，並在簡訊/客備註記原始時間。
    """
    original_slot = normalize_period_text(start_time_str, end_time_str)

    if original_slot == "10:00-12:00":
        return {
            "original_slot": original_slot,
            "system_slot": "09:00-11:00",
            "need_note": True,
            "sms_time": original_slot,
            "customer_time_note": f"服務時間：{original_slot}",
        }

    # 標準時段直接用 Sheet 原始時段，不用 hour 反推
    if original_slot in orders.STANDARD_SLOTS:
        return {
            "original_slot": original_slot,
            "system_slot": original_slot,
            "need_note": False,
            "sms_time": "",
            "customer_time_note": "",
        }

    # 非標準時段才用服務時數對應系統可送時段
    actual_hours = None

    if service_text and str(service_text).strip():
        match = re.search(r"(\d+)\s*人\s*(\d+(?:\.\d+)?)\s*小時", str(service_text))
        if match:
            actual_hours = float(match.group(2))
        else:
            match = re.search(r"(\d+(?:\.\d+)?)\s*小時", str(service_text))
            if match:
                actual_hours = float(match.group(1))

    if actual_hours is None:
        actual_hours = calc_effective_hours_from_time(start_time_str, end_time_str)

    if actual_hours is None:
        raise Exception(f"無法解析服務時段: {start_time_str}-{end_time_str}")

    sh, sm, eh, em = parse_time_slot(start_time_str, end_time_str)
    original_is_morning = sh < 12

    matched_slot = None
    for slot in orders.STANDARD_SLOTS:
        if is_morning_slot(slot) == original_is_morning and abs(slot_duration_hours(slot) - actual_hours) < 1e-9:
            matched_slot = slot
            break

    if not matched_slot:
        raise Exception(f"找不到可對應的系統時段：原始時段 {original_slot}，時數 {actual_hours}")

    return {
        "original_slot": original_slot,
        "system_slot": matched_slot,
        "need_note": True,
        "sms_time": original_slot,
        "customer_time_note": f"服務時間：{original_slot}",
    }


def parse_service_human_hour(service_text, start_time, end_time):
    """
    最終規則：
    1. 預設 2 人。
    2. 預設時數 = Google Sheet 開始/結束時間換算。
    3. 若 A欄/服務人時 有明確寫「3人4小時」，則人數與時數都以 A欄為準。
    """
    people = 2
    hours = calc_effective_hours_from_time(start_time, end_time)

    if service_text and str(service_text).strip():
        text = str(service_text).strip()

        people_match = re.search(r"(\d+)\s*人", text)
        if people_match:
            people = int(people_match.group(1))

        hour_match = re.search(r"(\d+(?:\.\d+)?)\s*小時", text)
        if hour_match:
            hours = float(hour_match.group(1))

    if hours is None:
        return people, None

    return people, int(hours) if float(hours).is_integer() else hours


def normalize_hours_text(cell_value, start_time_str=None, end_time_str=None):
    people, hours = parse_service_human_hour(cell_value, start_time_str, end_time_str)
    if hours is None:
        return f"{people}人"
    htxt = f"{int(hours)}小時" if float(hours).is_integer() else f"{hours}小時"
    return f"{people}人{htxt}"


def normalize_booking_payway(payway):
    text = str(payway or "").strip()
    if text in PAYWAY_MAP:
        return text
    if "儲值金" in text:
        return "儲值金"
    if "信用卡" in text or "刷卡" in text:
        return "信用卡"
    if "ATM" in text.upper() or "匯款" in text or "轉帳" in text or "藍新" in text:
        return "ATM"
    return text

def _format_period_display(period_raw, person="", display_override=""):
    compact = str(period_raw or "").replace(" ", "")
    display = str(display_override or "").replace(" ", "") or compact
    info = PERIOD_DISPLAY_INFO.get(compact)
    person_str = str(person or "").strip()
    if info:
        hour_str, has_break = info
        break_note = "，中間休息1小時" if has_break else ""
        if person_str and person_str != "0":
            inner = f"{person_str}人{hour_str}{break_note}"
            # 計算並加上「共X人時」
            try:
                h = int(float(hour_str.replace("小時", "")))
                p = int(person_str)
                ph = h * p
                ph_note = f"，共{ph}人時"
            except Exception:
                ph_note = ""
        else:
            inner = f"{hour_str}{break_note}"
            ph_note = ""
        return f"{display}（{inner}）{ph_note}"
    if person_str and person_str != "0":
        return f"{display}（{person_str}人）"
    return display

def _extract_actual_service_time(joined_text):
    m = re.search(r"簡訊實際服務時間\s*[：:]?\s*(\d{1,2}:\d{2})\s*[-~～]\s*(\d{1,2}:\d{2})", joined_text)
    if m:
        start, end = m.groups()
        return f"{start} - {end}"
    return ""

def _extract_phone_from_block_lines(lines):
    joined = "\n".join(lines)
    m = re.search(r"(?:\+?886[-\s]?)?0?9[\d\-\s]{8,10}", joined)
    if m:
        return normalize_phone(m.group(0))
    return ""

def _parse_service_date_time_loose(joined_text):
    date_match = re.search(r"(\d{4}-\d{2}-\d{2})\s*[（(][一二三四五六日][）)]", joined_text)
    if not date_match:
        for m in re.finditer(r"(\d{4}-\d{2}-\d{2})", joined_text):
            tail = joined_text[m.end():m.end() + 12]
            if not re.match(r"\s*\d{1,2}:\d{2}:\d{2}", tail):
                date_match = m
                break
    if not date_match:
        return "", ""
    service_date = date_match.group(1)
    tail = joined_text[date_match.end():date_match.end() + 600]
    time_match = re.search(r"(\d{1,2}:\d{2})\s*[-~～]\s*(\d{1,2}:\d{2})(?!:\d)", tail)
    if not time_match:
        time_match = re.search(r"(\d{1,2}:\d{2})\s*[-~～]\s*(\d{1,2}:\d{2})(?!:\d)", joined_text)
    if not time_match:
        return service_date, ""
    start, end = time_match.groups()
    return service_date, f"{start} - {end}"

def _extract_money_line(joined_text, labels):
    text = str(joined_text or "").replace(",", "")
    for label in labels:
        m = re.search(rf"{re.escape(label)}\s*[：:]?\s*\$?\s*(-?\d+(?:\.\d+)?)", text)
        if m:
            value = m.group(1)
            try:
                number = float(value)
                return str(int(number)) if number.is_integer() else str(number)
            except Exception:
                return value
    return ""

def _extract_total_amount_line(joined_text):
    return _extract_money_line(joined_text, ["訂單總金額", "總金額", "合計", "總計"])

def _extract_person_hour_line(joined_text):
    text = str(joined_text or "")
    compact_match = re.search(r"(\d+)\s*人\s*(\d+(?:\.\d+)?)\s*(?:小時|時)", text)
    if compact_match:
        return compact_match.group(1), compact_match.group(2)
    person = ""
    hour = ""
    person_match = re.search(r"(?:服務人數|人數|專員人數)\s*[：:]?\s*(\d+)", text)
    hour_match = re.search(r"(?:服務時數|時數)\s*[：:]?\s*(\d+(?:\.\d+)?)", text)
    if person_match:
        person = person_match.group(1)
    if hour_match:
        hour = hour_match.group(1)
    return person, hour

def _count_staff_from_lines(lines):
    staff_str = orders._extract_staff_line(lines)
    if not staff_str:
        return ""
    parts = [p.strip() for p in re.split(r"\s*X\s*", staff_str) if p.strip()]
    count = sum(1 for p in parts if "檸檬人" not in p)
    return str(count) if count > 0 else ""

def _fix_address_district_order(address, fallback_district=""):
    """
    v8.6：確保地址格式為「市/縣 → 區/鄉/鎮 → 其餘地址」。
    - 情況一：區/鄉/鎮 出現在 市/縣 之前（例如「大安區台北市羅斯福路...」，順序錯誤），
      自動對調為「台北市大安區羅斯福路...」。
    - 情況二：市/縣 後方已經有區/鄉/鎮，順序正確，不需處理。
    - 情況三：地址完全沒有區/鄉/鎮，若有提供 fallback_district（例如查詢取得），
      補在「市/縣」之後。
    任何情況解析失敗都直接回傳原始地址，不擋住建單流程。
    """
    address = str(address or "").strip()
    if not address:
        return address
    try:
        city_m = re.search(r"(?P<city>[^市縣區鄉鎮]{1,6}[市縣])", address)
        if not city_m:
            return address
        city = city_m.group("city")
        before_city = address[:city_m.start()]
        after_city = address[city_m.end():]
        district_m = re.match(r"^(?P<district>[^區鄉鎮市]{1,6}[區鄉鎮])", before_city)
        if district_m:
            district = district_m.group("district")
            rest_before = before_city[district_m.end():]
            if re.match(r"^[^區鄉鎮]{0,6}[區鄉鎮]", after_city):
                return f"{rest_before}{city}{after_city}".strip()
            return f"{rest_before}{city}{district}{after_city}".strip()
        if re.match(r"^[^區鄉鎮]{0,6}[區鄉鎮]", after_city):
            return address
        if fallback_district:
            return f"{before_city}{city}{fallback_district}{after_city}".strip()
        return address
    except Exception:
        return address

def _extract_district_from_address(address):
    address = str(address or "").strip()
    city_m = re.search(r"[^市縣區鄉鎮]{1,6}[市縣]", address)
    if not city_m:
        return ""
    after_city = address[city_m.end():]
    district_m = re.match(r"(?P<district>[^區鄉鎮市]{1,6}[區鄉鎮])", after_city)
    return district_m.group("district") if district_m else ""

def _normalize_city_for_country_id(city):
    return str(city or "").strip().replace("臺", "台")

def _extract_address_line(lines):
    for line in lines:
        text = str(line or "").strip()
        if not text or "@" in text or text.upper() == "LINE":
            continue
        if re.search(r"(台|臺|新北|桃園|台中|臺中|台南|臺南|高雄|基隆|新竹|嘉義|苗栗|彰化|南投|雲林|屏東|宜蘭|花蓮|台東|臺東|澎湖|金門|連江).*(市|縣).*(區|鄉|鎮|市)", text):
            return _fix_address_district_order(text)
    return ""

def _date_not_after_today(date_text):
    try:
        return datetime.strptime(str(date_text), "%Y-%m-%d").date() <= date.today()
    except Exception:
        return False

def _extract_label_value(lines, label, stop_labels):
    try:
        idx = lines.index(label)
    except ValueError:
        return ""
    value_lines = []
    for line in lines[idx + 1:]:
        if line in stop_labels or line in CLEAN_TYPE_LABELS:
            break
        value_lines.append(line)
    return " ".join(value_lines).strip()

def _is_target_day(d, day_type="不限"):
    weekday = d.weekday()
    if day_type == "平日":
        return weekday < 5
    if day_type == "週末":
        return weekday >= 5
    return True

def _filter_periods_by_preference(periods, time_preference="不限"):
    selected = []
    for period in periods or []:
        try:
            start_hour = int(str(period).split("-", 1)[0].split(":", 1)[0])
        except Exception:
            start_hour = 0
        if time_preference == "上午" and start_hour >= 12:
            continue
        if time_preference == "下午" and start_hour < 12:
            continue
        selected.append(period)
    return selected

def lookup_company_name_by_tax_id(tax_id):
    """
    用統編查公司名稱，透過經濟部商工開放資料平台。
    回傳公司名稱字串，查無則回傳空字串。
    """
    try:
        import urllib.parse
        tax_id = str(tax_id).strip()
        # 商業登記（行號）
        url_biz = (
            f"https://data.gcis.nat.gov.tw/od/data/api/5F64D864-61CB-4D0D-8AD9-492047CC1EA6"
            f"?%24format=json&%24filter=Business_Accounting_NO%20eq%20{tax_id}&%24top=1"
        )
        resp = requests.get(url_biz, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            if data and data[0].get("Company_Name"):
                return data[0]["Company_Name"]
        # 公司登記（有限公司/股份有限公司）
        url_co = (
            f"https://data.gcis.nat.gov.tw/od/data/api/236EE382-4942-41A9-BD03-CA0709025E7C"
            f"?%24format=json&%24filter=Business_Accounting_NO%20eq%20{tax_id}&%24top=1"
        )
        resp2 = requests.get(url_co, timeout=5)
        if resp2.status_code == 200:
            data2 = resp2.json()
            if data2 and data2[0].get("Company_Name"):
                return data2[0]["Company_Name"]
    except Exception:
        pass
    return ""

def _day_type_from_date(date_text):
    try:
        d = datetime.strptime(str(date_text), "%Y-%m-%d").date()
    except Exception:
        return "平日"
    return "週末" if d.weekday() >= 5 else "平日"
