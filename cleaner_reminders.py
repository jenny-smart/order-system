# -*- coding: utf-8 -*-
"""已付款訂單的專員隔日上班提醒（後台唯讀）。"""

import re
from collections import defaultdict
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

import orders
from weekend_reminders import (
    _address,
    _configure_backend,
    _name_phone,
)


def _listed_service_date_time(lines):
    """本模組自行解析，避免 Streamlit 熱更新仍快取舊 weekend_reminders。"""
    _, service_date, _ = orders._extract_order_dates_from_block_lines(lines)
    service_time = ""
    if service_date:
        for idx, line in enumerate(lines):
            if str(line).strip().startswith(service_date):
                for following in lines[idx + 1:idx + 6]:
                    match = re.search(
                        r"(\d{1,2}:\d{2})\s*[-~～至]\s*(\d{1,2}:\d{2})",
                        str(following),
                    )
                    if match:
                        service_time = f"{match.group(1)}-{match.group(2)}"
                        break
                break
    return service_date or "", service_time


def _sms_service_date_time(lines, fallback_date=""):
    for idx, raw_line in enumerate(lines):
        line = str(raw_line or "").strip()
        if not re.search(r"簡訊.*(?:時間|日期)", line):
            continue
        text = " ".join(
            [line]
            + [str(item or "").strip() for item in lines[idx + 1:idx + 4]]
        )
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


def _preferred_service_date_time(lines):
    listed_date, listed_time = _listed_service_date_time(lines)
    sms_date, sms_time, used = _sms_service_date_time(lines, listed_date)
    return sms_date or listed_date, sms_time or listed_time, used


def extract_cleaner_names(lines):
    staff = orders._extract_staff_line(lines)
    if not staff or staff == "無人力":
        return []
    return [
        name.strip()
        for name in re.split(r"\s+[Xx×]\s+", staff)
        if name.strip() and name.strip() != "無人力"
    ]


def cleaner_profile_ids(raw_html, target_names):
    """由 /cleaner1 表格找專員名稱對應的 user id。"""
    wanted = {re.sub(r"\s+", "", name): name for name in target_names}
    found = {}
    soup = BeautifulSoup(raw_html or "", "html.parser")
    for row in soup.find_all("tr"):
        compact = re.sub(r"\s+", "", row.get_text(" ", strip=True))
        matched = [original for key, original in wanted.items() if key and key in compact]
        if not matched:
            continue
        html = str(row)
        match = re.search(r"/user/edit/(\d+)", html, re.I)
        if not match:
            match = re.search(r"/cleaner1/(\d+)(?=[/'\"?#])", html, re.I)
        if match:
            for name in matched:
                found[name] = match.group(1)
    return found


def extract_cleaner_line(raw_html):
    soup = BeautifulSoup(raw_html or "", "html.parser")
    field = soup.select_one('input[name="line"], input#line')
    return str(field.get("value") or "").strip() if field else ""


def build_cleaner_message(
    name, service_date_s, jobs, service_date_e=None, reference_date=None
):
    start_day = datetime.strptime(service_date_s, "%Y-%m-%d").date()
    end_day = datetime.strptime(
        service_date_e or service_date_s, "%Y-%m-%d"
    ).date()
    weekdays = "一二三四五六日"
    start_text = (
        f"{start_day.month}/{start_day.day}（{weekdays[start_day.weekday()]}）"
    )
    end_text = f"{end_day.month}/{end_day.day}（{weekdays[end_day.weekday()]}）"
    reference_date = reference_date or datetime.now(ZoneInfo("Asia/Taipei")).date()
    if start_day == end_day == reference_date + timedelta(days=1):
        opening = "提醒您明日有排班"
    elif start_day == end_day:
        opening = f"提醒您 {start_text} 有排班"
    else:
        opening = f"提醒您 {start_text}～{end_text} 有排班"
    lines = [f"{name}專員您好，{opening}："]
    sorted_jobs = sorted(
        jobs,
        key=lambda item: (
            item.get("service_date") or service_date_s,
            item.get("service_time") or "",
            item.get("order_no") or "",
        ),
    )
    jobs_by_day = defaultdict(int)
    for idx, job in enumerate(sorted_jobs, 1):
        job_day = datetime.strptime(
            job.get("service_date") or service_date_s, "%Y-%m-%d"
        ).date()
        jobs_by_day[job_day] += 1
        job_day_text = (
            f"{job_day.month}/{job_day.day}（{weekdays[job_day.weekday()]}）"
        )
        lines.extend([
            "",
            f"{idx}. {job_day_text} {job.get('service_time') or '時間待確認'}",
            f"地址：{job.get('address') or '請至後台確認'}",
            f"訂單：{job.get('order_no') or ''}",
        ])
    crowded_days = [
        f"{day.month}/{day.day}" for day, count in sorted(jobs_by_day.items())
        if count > 1
    ]
    if crowded_days:
        lines.extend([
            "",
            f"⚠️ {'、'.join(crowded_days)} 當日有多筆工作，請務必確認 final 時間。",
        ])
    lines.extend(["", "請確認明日行程，收到後請回覆「收到」，謝謝。"])
    return "\n".join(lines)


def _resolve_cleaner_lines(session, base_url, names):
    roster = session.get(
        f"{base_url}/cleaner1",
        params={"area_id": "", "keyword": ""},
        headers=orders.HEADERS,
        allow_redirects=True,
    )
    ids = cleaner_profile_ids(roster.text if roster.status_code == 200 else "", names)
    for name in names:
        if name in ids:
            continue
        response = session.get(
            f"{base_url}/cleaner1",
            params={"area_id": "", "keyword": name},
            headers=orders.HEADERS,
            allow_redirects=True,
        )
        if response.status_code == 200:
            ids.update(cleaner_profile_ids(response.text, [name]))

    result = {}
    for name, user_id in ids.items():
        detail = session.get(
            f"{base_url}/user/edit/{user_id}",
            headers=orders.HEADERS,
            allow_redirects=True,
        )
        result[name] = {
            "user_id": user_id,
            "line_url": extract_cleaner_line(detail.text if detail.status_code == 200 else ""),
        }
    return result


def find_paid_cleaner_reminders(
    env_name, backend_email, backend_password,
    service_date_s, service_date_e=None, max_pages=20
):
    """查詢服務日期區間的已付款訂單，跨日依專員彙整成一筆。"""
    service_date_e = service_date_e or service_date_s
    _configure_backend(env_name)
    session = orders.requests.Session()
    if not orders.login(session, backend_email, backend_password):
        raise RuntimeError("後台登入失敗，請確認帳號密碼")

    jobs_by_name = defaultdict(list)
    hit_page_limit = True
    for page in range(1, max_pages + 1):
        params = dict(orders.PURCHASE_FILTER_PARAMS_TEMPLATE)
        params.update({
            "clean_date_s": service_date_s,
            "clean_date_e": service_date_e,
            "purchase_status": "1",
            "p_board": "on",
            "page": str(page),
        })
        response = session.get(
            orders.PURCHASE_URL,
            params=params,
            headers=orders.HEADERS,
            allow_redirects=True,
        )
        if response.status_code != 200:
            hit_page_limit = False
            break
        blocks = orders.extract_order_cards_from_purchase_html(response.text)
        if not blocks:
            hit_page_limit = False
            break
        for block in blocks:
            lines = block.get("lines", [])
            joined = "\n".join(lines)
            if not re.search(r"付款狀態[：:]\s*已付款", joined):
                continue
            listed_date, _ = _listed_service_date_time(lines)
            if not listed_date or not (service_date_s <= listed_date <= service_date_e):
                continue
            found_date, service_time, sms_time_used = _preferred_service_date_time(lines)
            customer_name, _ = _name_phone(lines)
            job = {
                "order_no": block.get("order_no", ""),
                "service_date": found_date,
                "service_time": service_time,
                "address": _address(lines),
                "customer_name": customer_name,
                "sms_time_used": sms_time_used,
            }
            for cleaner_name in extract_cleaner_names(lines):
                jobs_by_name[cleaner_name].append(job)
        if len(blocks) < 20:
            hit_page_limit = False
            break

    profiles = _resolve_cleaner_lines(session, orders.BASE_URL, sorted(jobs_by_name))
    rows = []
    for name in sorted(jobs_by_name):
        profile = profiles.get(name, {})
        jobs = jobs_by_name[name]
        rows.append({
            "name": name,
            "user_id": profile.get("user_id", ""),
            "line_url": profile.get("line_url", ""),
            "service_date_s": service_date_s,
            "service_date_e": service_date_e,
            "jobs": jobs,
            "message": build_cleaner_message(
                name, service_date_s, jobs, service_date_e=service_date_e
            ),
        })
    return rows, {
        "base_url": orders.BASE_URL,
        "cleaner_count": len(rows),
        "job_count": sum(len(items) for items in jobs_by_name.values()),
        "hit_page_limit": hit_page_limit,
    }
