# ============================================================
# 檔名：function/lemon_staff_replacement.py
# 功能：搜尋含檸檬人的訂單，批量分析真實可換班候選，人工確認後逐筆寫入。
# 更新時間：2026-09-08
# ============================================================
# -*- coding: utf-8 -*-
from __future__ import annotations

import re
from collections import defaultdict
from datetime import date, timedelta

import pandas as pd
import requests
import streamlit as st
from bs4 import BeautifulSoup

import orders
from function.ui_common import info_panel, step
from shared.cleaner_shift import _get_schedule_edit_info
from shared.env_config import apply_env
from shared.staff_assignment_core import AssignmentContext, StaffCandidate, rank_combinations
from shared.text_parsing import (
    _extract_address_line,
    _extract_phone_from_block_lines,
    _parse_service_date_time_loose,
)

GENDER_LABELS = {
    0: "不限",
    1: "限女",
    2: "1女",
    3: "限男",
    4: "1男",
    5: "1男1女",
}
UNQUALIFIED_REASON = "專員詳細資料的區域未含此地址編號"


def preferred_gender_label(value) -> str:
    try:
        index = int(str(value).strip())
    except Exception:
        return str(value or "").strip() or "不限"
    return GENDER_LABELS.get(index, str(value or "").strip() or "不限")


def _text(value) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass
    return str(value).strip()


def _split_staff(staff_text: str) -> list[str]:
    return [x.strip() for x in re.split(r"\s*[Xx×]\s*", str(staff_text or "")) if x.strip()]


def _staff_name_and_rating(label: str) -> tuple[str, float]:
    text = re.sub(r"\s+", "", str(label or "")).strip()
    match = re.match(r"^(.*?)[（(](\d+(?:\.\d+)?)[）)]$", text)
    if not match:
        return text, 0.0
    return match.group(1).strip(), float(match.group(2))


def _order_from_block(block: dict) -> dict | None:
    order_no = str(block.get("order_no") or "").strip()
    lines = list(block.get("lines") or [])
    joined = "\n".join(lines)
    service_date, period = _parse_service_date_time_loose(joined)
    staff_text = orders._extract_staff_line(lines)
    current_staff = _split_staff(staff_text)
    lemon_count = sum("檸檬人" in x for x in current_staff)
    if not order_no or not service_date or not lemon_count:
        return None

    phone = _extract_phone_from_block_lines(lines)
    name = ""
    if phone:
        phone_compact = re.sub(r"\D", "", phone)
        for index, line in enumerate(lines):
            if phone_compact and phone_compact in re.sub(r"\D", "", str(line)):
                if index:
                    name = str(lines[index - 1]).strip()
                break

    digits = re.sub(r"\D", "", order_no)
    return {
        "purchase_id": str(int(digits)) if digits else "",
        "order_no": order_no,
        "name": name,
        "phone": phone,
        "service_date": service_date,
        "period": re.sub(r"\s+", "", period),
        "address": _extract_address_line(lines),
        "staff": staff_text,
        "current_staff": current_staff,
        "lemon_count": lemon_count,
        "people_needed": lemon_count,
    }


def build_assignment_plan(order: dict, candidate_rows: list[dict], limit: int = 20):
    ctx = AssignmentContext(
        order_no=str(order.get("order_no") or ""),
        service_date=str(order.get("service_date") or ""),
        period=str(order.get("period") or ""),
        address=str(order.get("address") or ""),
        people_needed=int(order.get("people_needed") or 1),
        is_vip=bool(order.get("is_vip")),
        is_returning_customer=bool(order.get("is_returning_customer")),
        gender_requirement=str(order.get("gender_requirement") or ""),
        height_requirement=str(order.get("height_requirement") or ""),
        body_requirement=str(order.get("body_requirement") or ""),
        preferred_staff_ids=set(order.get("preferred_staff_ids") or []),
        visited_staff_ids=set(order.get("visited_staff_ids") or []),
        complained_staff_ids=set(order.get("complained_staff_ids") or []),
        customer_tags=set(order.get("customer_tags") or []),
        required_skills=set(order.get("required_skills") or []),
        case_tags=set(order.get("case_tags") or []),
    )
    candidates = [
        StaffCandidate(
            staff_id=str(row.get("staff_id") or row.get("name") or ""),
            name=str(row.get("name") or ""),
            rating=float(row.get("rating") or 0),
            gender=str(row.get("gender") or ""),
            height_cm=row.get("height_cm"),
            body_tags=set(row.get("body_tags") or []),
            skills=set(row.get("skills") or []),
            customer_fit_tags=set(row.get("customer_fit_tags") or []),
            case_fit_tags=set(row.get("case_fit_tags") or []),
            unavailable_case_tags=set(row.get("unavailable_case_tags") or []),
            incompatible_staff_ids=set(row.get("incompatible_staff_ids") or []),
            similarity_tags=set(row.get("similarity_tags") or []),
            observation=bool(row.get("observation")),
            intern=bool(row.get("intern")),
            machine_required=bool(row.get("machine_required")),
            home_to_case_minutes=row.get("home_to_case_minutes"),
            previous_case_to_case_minutes=row.get("previous_case_to_case_minutes"),
            case_to_home_minutes=row.get("case_to_home_minutes"),
            available=bool(row.get("available", True)),
            availability_reason=str(row.get("availability_reason") or ""),
        )
        for row in (candidate_rows or [])
    ]
    return rank_combinations(ctx, candidates, limit=limit)


def _logged_in_session(env: str, email: str, password: str):
    base_url = apply_env(orders, env)
    session = requests.Session()
    if not orders.login(session, email, password):
        raise RuntimeError("後台登入失敗，請確認帳號密碼")
    return session, base_url


def _find_lemon_orders_with_session(session, date_s: str, date_e: str, payment_filter: str = "已付款", max_pages: int = 80) -> list[dict]:
    if not date_s or not date_e or str(date_s) > str(date_e):
        raise ValueError("服務日期區間不正確")
    status_map = {"全部": "", "待付款": "0", "已付款": "1"}
    blocks = orders._fetch_all_purchase_blocks_by_date_range(
        session,
        str(date_s),
        str(date_e),
        purchase_status=status_map.get(payment_filter, "1"),
        max_pages=max_pages,
    )
    found = []
    seen = set()
    for block in blocks:
        item = _order_from_block(block)
        if not item or item["order_no"] in seen:
            continue
        if not (str(date_s) <= item["service_date"] <= str(date_e)):
            continue
        seen.add(item["order_no"])
        found.append(item)
    found.sort(key=lambda x: (x["service_date"], x["period"], x["order_no"]))
    return found


def find_lemon_orders(
    env: str,
    email: str,
    password: str,
    date_s: str,
    date_e: str,
    payment_filter: str = "已付款",
    max_pages: int = 80,
    session=None,
    base_url=None,
) -> list[dict]:
    if not email or not password:
        raise ValueError("請先輸入後台帳號與密碼")
    if session is None:
        session, base_url = _logged_in_session(env, email, password)
        own_session = True
    else:
        own_session = False
        if base_url is None:
            base_url = apply_env(orders, env)
    try:
        return _find_lemon_orders_with_session(session, date_s, date_e, payment_filter, max_pages)
    finally:
        if own_session:
            session.close()


def _period_key(text) -> str:
    return re.sub(r"\s+", "", str(text or ""))


def parse_unassigned_names(html_text: str, service_date: str, period: str) -> list[str] | None:
    """班表頁（/schedule?date=）中，該日期列、該時段欄「未配班 N 人」深灰框裡的人。

    名單每行像「48宋品鈞3」（前面數字＋姓名＋星等），只取姓名；找不到該格回傳 None。
    """
    soup = BeautifulSoup(html_text or "", "html.parser")
    mmdd = str(service_date or "")[5:]
    target = _period_key(period)
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if not rows:
            continue
        header = [_period_key(c.get_text(" ", strip=True)) for c in rows[0].find_all(["th", "td"])]
        if target not in header:
            continue
        col = header.index(target)
        for row in rows[1:]:
            cells = row.find_all(["th", "td"])
            if len(cells) <= col or not cells[0].get_text(" ", strip=True).startswith(mmdd):
                continue
            lines = [x.strip() for x in cells[col].get_text("\n").split("\n") if x.strip()]
            for i, line in enumerate(lines):
                m = re.fullmatch(r"未配班\s*(\d+)\s*人", line)
                if not m:
                    continue
                names = []
                for entry in lines[i + 1:i + 1 + int(m.group(1))]:
                    name = re.sub(r"\d+$", "", re.sub(r"^\d+", "", entry)).strip()
                    if name:
                        names.append(name)
                return names
            return []  # 有這一格但沒有未配班框：當天這時段沒有未配班的人
    return None


def _unassigned_for_order(session, base_url: str, order: dict, cache: dict) -> list[str] | None:
    service_date = str(order.get("service_date") or "")
    if service_date not in cache:
        try:
            resp = session.get(f"{base_url}/schedule", params={"date": service_date, "staffId": ""},
                               headers=orders.HEADERS, allow_redirects=True)
            cache[service_date] = resp.text if resp.status_code == 200 else ""
        except Exception:
            cache[service_date] = ""
    return parse_unassigned_names(cache[service_date], service_date, order.get("period", ""))


def _order_area_id(session, base_url: str, order: dict) -> str:
    """訂單地址的區域編號（訂單修改頁地址下方的編號，例如 44）。"""
    purchase_id = str(order.get("purchase_id") or "")
    if not purchase_id:
        return ""
    for path in (f"/purchase/change_date/{purchase_id}", f"/purchase/edit/{purchase_id}"):
        try:
            resp = session.get(f"{base_url}{path}", headers=orders.HEADERS, allow_redirects=True)
        except Exception:
            continue
        if resp.status_code != 200:
            continue
        match = re.search(r'name=["\'](?:area_id|areaId)["\'][^>]*value=["\'](\d+)["\']', resp.text) or \
            re.search(r'value=["\'](\d+)["\'][^>]*name=["\'](?:area_id|areaId)["\']', resp.text)
        if match:
            return match.group(1)
    return ""


def _parse_cleaner_rows(html: str) -> dict[str, dict]:
    """居家專員列表（/cleaner1）：每列第一欄是區域編號清單，第二欄第一行是姓名。"""
    rows = {}
    soup = BeautifulSoup(html or "", "html.parser")
    for tr in soup.find_all("tr"):
        cells = tr.find_all("td")
        if len(cells) < 2:
            continue
        lines = [x.strip() for x in cells[1].stripped_strings if x.strip()]
        if not lines:
            continue
        name = re.sub(r"\s+", "", lines[0])
        user_m = re.search(r"/user/edit/(\d+)", str(tr))
        rows[name] = {
            "areas": set(re.findall(r"\d+", cells[0].get_text(" "))),
            "user_id": user_m.group(1) if user_m else "",
        }
    return rows


_TW_ID_PATTERN = re.compile(r"^[A-Z]([12])\d{8}$")


def _gender_from_user_edit(html: str) -> str:
    """專員詳細資料（/user/edit/{id}）的性別：看身分證字號英文後第 1 個數字，1＝男、2＝女。

    只用來判斷性別，身分證字號本身不顯示、不保存；讀不到回傳空字串。
    """
    soup = BeautifulSoup(html or "", "html.parser")
    values = []
    # 先找「身份證字號／身分證字號」標題後面的輸入框
    for node in soup.find_all(string=re.compile(r"身[份分]證字號")):
        field = node.find_next("input")
        if field is not None:
            values.append(str(field.get("value") or ""))
    # 找不到標題時，退而找格式符合身分證字號的輸入框
    values += [str(tag.get("value") or "") for tag in soup.find_all("input")]
    for value in values:
        match = _TW_ID_PATTERN.match(value.strip().upper())
        if match:
            return "男" if match.group(1) == "1" else "女"
    return ""


def _staff_profile(session, base_url: str, name: str, cache: dict, need_gender: bool = False) -> dict:
    """查專員的服務區域編號（居家專員列表）與性別（詳細資料）；同一次分析共用 cache。"""
    name = re.sub(r"\s+", "", str(name or ""))
    profile = cache.get(name)
    if profile is None:
        profile = {"areas": None, "user_id": "", "gender": None, "error": ""}
        try:
            resp = session.get(f"{base_url}/cleaner1", params={"area_id": "", "keyword": name},
                               headers=orders.HEADERS, allow_redirects=True)
            row = _parse_cleaner_rows(resp.text).get(name) if resp.status_code == 200 else None
            if row:
                profile.update(row)
            else:
                profile["error"] = "居家專員列表查無此人"
        except Exception as exc:
            profile["error"] = f"查詢居家專員失敗：{exc}"
        cache[name] = profile
    if need_gender and profile["gender"] is None:
        profile["gender"] = ""
        if profile.get("user_id"):
            try:
                resp = session.get(f"{base_url}/user/edit/{profile['user_id']}", headers=orders.HEADERS,
                                   allow_redirects=True)
                if resp.status_code == 200:
                    profile["gender"] = _gender_from_user_edit(resp.text)
            except Exception:
                pass
    return profile


def gender_rule_ok(label: str, genders: list[str]) -> bool:
    """喜愛專員性別：限女＝全部女生；1女＝至少 1 位女生（2 女或 1 女 1 男都可以）；男生同理。
    genders 是整組服務人員（含訂單上保留的正式專員）的性別，讀不到的是空字串。"""
    label = str(label or "").strip()
    females = sum(1 for g in genders if g == "女")
    males = sum(1 for g in genders if g == "男")
    if label in ("", "不限", "無法取得"):
        return True
    if label == "限女":
        return bool(genders) and females == len(genders)
    if label == "限男":
        return bool(genders) and males == len(genders)
    if label == "1女":
        return females >= 1
    if label == "1男":
        return males >= 1
    if label == "1男1女":
        return females >= 1 and males >= 1
    return True


def _lemon_slot_indexes(order: dict, slot_count: int) -> list[int]:
    current_staff = list(order.get("current_staff") or _split_staff(order.get("staff", "")))
    indexes = [i for i, name in enumerate(current_staff) if "檸檬人" in name]
    if current_staff and len(current_staff) == slot_count and indexes:
        return indexes
    lemon_count = int(order.get("lemon_count") or order.get("people_needed") or 0)
    if lemon_count == slot_count and lemon_count:
        return list(range(slot_count))
    raise RuntimeError("訂單人員槽位與服務人員數量不一致，為避免換錯人已停止，請改至後台人工確認")


def _candidate_map(slot_map: dict) -> dict[str, str]:
    result = {}
    for label, shift_id in (slot_map or {}).items():
        name, _rating = _staff_name_and_rating(label)
        if name and "檸檬人" not in name:
            result[name] = str(shift_id)
    return result


def _match_names_to_slots(names: list[str], slots: list[dict], target_indexes: list[int], allow_partial: bool = False):
    """把一組姓名配到不同的檸檬人槽位；同一人不得重複。

    allow_partial：人數可少於檸檬人槽位（先放入選好的人，其餘槽位維持檸檬人）。
    """
    wanted = list(dict.fromkeys(str(x) for x in names if str(x)))
    if not wanted or len(wanted) > len(target_indexes):
        return None
    if not allow_partial and len(wanted) != len(target_indexes):
        return None
    by_slot = {index: _candidate_map(slots[index]) for index in target_indexes}

    def walk(position: int, free_slots: list[int], assigned: dict):
        if position == len(wanted):
            return assigned
        name = wanted[position]
        for slot_index in free_slots:
            shift_id = by_slot[slot_index].get(name)
            if shift_id:
                result = walk(
                    position + 1,
                    [x for x in free_slots if x != slot_index],
                    {**assigned, slot_index: {"name": name, "shift_id": shift_id}},
                )
                if result:
                    return result
        return None

    return walk(0, list(target_indexes), {})


def _available_names(slots: list[dict], target_indexes: list[int]) -> dict[str, float]:
    """排班修改頁檸檬人槽位可選的正式專員（該日期時段有空）與星等。"""
    candidate_labels = {}
    for index in target_indexes:
        for label in slots[index]:
            name, rating = _staff_name_and_rating(label)
            if name and "檸檬人" not in name:
                candidate_labels[name] = max(candidate_labels.get(name, 0.0), rating)
    return candidate_labels


def _build_candidate_rows_and_names(slots: list[dict], target_indexes: list[int], allowed_names=None) -> tuple[list[dict], list[str]]:
    candidate_labels = _available_names(slots, target_indexes)
    if allowed_names is not None:
        candidate_labels = {k: v for k, v in candidate_labels.items() if k in set(allowed_names)}
    if len(candidate_labels) < len(target_indexes):
        raise RuntimeError("當天該時段未配班、且符合該地址資格的正式專員不足")
    candidate_rows = [
        {"staff_id": name, "name": name, "rating": rating, "available": True}
        for name, rating in sorted(candidate_labels.items(), key=lambda item: (-item[1], item[0]))
    ]
    return candidate_rows, sorted(candidate_labels)


def _build_recommendations(order: dict, slots: list[dict], target_indexes: list[int], limit: int = 3,
                           allowed_names=None, gender_label: str = "", gender_of=None) -> tuple[list[dict], list[str]]:
    candidate_rows, candidate_names = _build_candidate_rows_and_names(slots, target_indexes, allowed_names)
    current_staff = list(order.get("current_staff") or _split_staff(order.get("staff", "")))
    kept = [_staff_name_and_rating(current_staff[i])[0] for i in range(len(current_staff)) if i not in target_indexes]
    gender_of = gender_of or (lambda _name: "")
    gender_rejected = 0
    plan_order = dict(order)
    plan_order["people_needed"] = len(target_indexes)
    ranked = build_assignment_plan(plan_order, candidate_rows, limit=max(40, int(limit) * 10))
    recommendations = []
    for result in ranked:
        names = [member.name for member in result.staff]
        if not gender_rule_ok(gender_label, [gender_of(n) for n in kept + names]):
            gender_rejected += 1
            continue
        assignment = _match_names_to_slots(names, slots, target_indexes)
        if not assignment:
            continue
        recommendations.append(
            {
                "names": names,
                "display": "＋".join(names),
                "score": round(result.score, 2),
                "average_rating": round(sum(x.rating for x in result.staff) / len(result.staff), 2),
                "reasons": "；".join(result.reasons) or "符合真實班表與基本配班規則",
            }
        )
        if len(recommendations) >= max(1, int(limit)):
            break
    if not recommendations:
        if gender_rejected:
            raise RuntimeError(f"沒有符合喜愛專員性別「{gender_label}」的組合（含訂單上保留的專員一起判斷）")
        raise RuntimeError("班表雖有候選人，但沒有符合『組合平均星等至少 4 分』及槽位限制的組合")
    return recommendations, candidate_names


MIN_AVERAGE_RATING = 4.0


def validate_manual_pick(order: dict, names: list[str]) -> str:
    """檢查手動選的放入人員；回傳錯誤原因，空字串代表可以放入。

    - 只能選「可放入人員」（未配班、符合地址資格、排班修改選得到）；人數不可超過檸檬人位置，
      少於時其餘位置先留檸檬人；
    - 星等：放入的人加上訂單上保留的正式專員，平均至少 4 分；
    - 喜愛專員性別：限女／限男一律檢查；1女、1男、1男1女在檸檬人位置都放滿時才檢查。
    """
    names = list(dict.fromkeys(str(x) for x in names or [] if str(x)))
    pickable = {item["name"]: item for item in order.get("可放入人員") or []}
    slots = int(order.get("lemon_count") or order.get("people_needed") or 0)
    if not names:
        return "沒有選擇放入人員"
    if len(names) > slots:
        return f"選了 {len(names)} 位，但只有 {slots} 個檸檬人位置"
    outside = [n for n in names if n not in pickable]
    if outside:
        return f"{'、'.join(outside)} 不在可放入人員（未配班且符合地址資格）"
    kept = order.get("保留專員") or []
    ratings = [float(item.get("rating") or 0) for item in kept] + [float(pickable[n].get("rating") or 0) for n in names]
    average = sum(ratings) / len(ratings)
    if average < MIN_AVERAGE_RATING:
        return f"放入後整組平均星等 {average:.2f}，未達 {MIN_AVERAGE_RATING:g} 分"
    label = str(order.get("喜愛專員性別") or "").strip()
    genders = [str(item.get("gender") or "") for item in kept] + [str(pickable[n].get("gender") or "") for n in names]
    if label in ("限女", "限男") or len(names) == slots:
        if not gender_rule_ok(label, genders):
            return f"不符合喜愛專員性別「{label}」"
    return ""


def _parse_period_range(period_text: str) -> tuple[int, int] | None:
    text = re.sub(r"\s+", "", str(period_text or ""))
    match = re.fullmatch(r"(\d{2}):(\d{2})-(\d{2}):(\d{2})", text)
    if not match:
        return None
    start = int(match.group(1)) * 60 + int(match.group(2))
    end = int(match.group(3)) * 60 + int(match.group(4))
    if end <= start:
        return None
    return start, end


def _periods_overlap(period_a: str, period_b: str) -> bool:
    bounds_a = _parse_period_range(period_a)
    bounds_b = _parse_period_range(period_b)
    if not bounds_a or not bounds_b:
        return False
    start_a, end_a = bounds_a
    start_b, end_b = bounds_b
    return start_a < end_b and start_b < end_a


def _batch_entry_conflicts(left: dict, right: dict) -> bool:
    if str(left.get("service_date") or "") != str(right.get("service_date") or ""):
        return False
    if not _periods_overlap(left.get("period", ""), right.get("period", "")):
        return False
    return bool(set(left.get("selected_names") or []) & set(right.get("selected_names") or []))


def _get_schedule_context(session, base_url: str, order: dict, limit: int = 3, gender_label: str = "",
                          staff_cache: dict | None = None, schedule_cache: dict | None = None) -> dict:
    try:
        csrf, origin_ids, slots = _get_schedule_edit_info(
            session, base_url, order["service_date"], order["purchase_id"]
        )
    except Exception as exc:
        return {
            "ok": False,
            "error": f"讀取 schedule/edit 失敗：{exc}",
            "recommendations": [],
            "candidate_names": [],
            "candidate_count": 0,
            "slots": [],
            "target_indexes": [],
            "csrf": "",
            "origin_ids": [],
        }
    if not csrf or not origin_ids or not slots:
        return {
            "ok": False,
            "error": "無法讀取後台換班頁，可能此訂單沒有可編輯的班表",
            "recommendations": [],
            "candidate_names": [],
            "candidate_count": 0,
            "slots": slots or [],
            "target_indexes": [],
            "csrf": csrf or "",
            "origin_ids": origin_ids or [],
        }
    if len(origin_ids) != len(slots):
        return {
            "ok": False,
            "error": "後台換班頁槽位資料不完整，已停止推薦",
            "recommendations": [],
            "candidate_names": [],
            "candidate_count": 0,
            "slots": slots,
            "target_indexes": [],
            "csrf": csrf,
            "origin_ids": origin_ids,
        }
    staff_cache = {} if staff_cache is None else staff_cache
    schedule_cache = {} if schedule_cache is None else schedule_cache
    area_id = ""
    qualified_names: list[str] = []
    unqualified_names: list[str] = []
    unknown_names: list[str] = []
    pickable: list[dict] = []
    kept: list[dict] = []
    try:
        target_indexes = _lemon_slot_indexes(order, len(slots))
        area_id = _order_area_id(session, base_url, order)
        if not area_id:
            raise RuntimeError("讀不到訂單地址的區域編號（訂單修改頁地址下方），無法判斷專員地址資格")
        # 只看訂單當天、該時段「未配班」的人；已配班的人不動。
        unassigned = _unassigned_for_order(session, base_url, order, schedule_cache)
        if unassigned is None:
            raise RuntimeError(f"讀不到班表 {order.get('service_date')} {order.get('period')} 的未配班名單")
        for name in sorted(set(n for n in unassigned if "檸檬人" not in n)):
            profile = _staff_profile(session, base_url, name, staff_cache)
            if profile.get("areas") is None:
                unknown_names.append(f"{name}（{profile.get('error') or '查不到區域'}）")
            elif area_id in profile["areas"]:
                qualified_names.append(name)
            else:
                unqualified_names.append(name)
        need_gender = str(gender_label or "").strip() not in ("", "不限", "無法取得")

        def gender_of(name):
            return _staff_profile(session, base_url, name, staff_cache, need_gender=True).get("gender") or "" if need_gender else ""

        # 可放入人員：未配班、符合地址資格、排班修改頁選得到（依星等高到低），供手動選擇
        available = _available_names(slots, target_indexes)
        pickable = [
            {"name": name, "rating": available[name], "gender": gender_of(name)}
            for name in sorted((n for n in qualified_names if n in available), key=lambda n: (-available[n], n))
        ]
        current_staff = list(order.get("current_staff") or _split_staff(order.get("staff", "")))
        for i, label in enumerate(current_staff):
            if i in target_indexes:
                continue
            kept_name, kept_rating = _staff_name_and_rating(label)
            kept.append({"name": kept_name, "rating": kept_rating, "gender": gender_of(kept_name)})

        recommendations, candidate_names = _build_recommendations(
            order, slots, target_indexes, limit=limit, allowed_names=qualified_names,
            gender_label=gender_label, gender_of=gender_of,
        )
    except Exception as exc:
        return {
            "ok": False,
            "error": f"班表解析/推薦失敗：{exc}",
            "recommendations": [],
            "candidate_names": qualified_names,
            "unqualified_names": unqualified_names,
            "unknown_names": unknown_names,
            "area_id": area_id,
            "pickable": pickable,
            "kept": kept,
            "candidate_count": 0,
            "slots": slots,
            "target_indexes": [],
            "csrf": csrf,
            "origin_ids": origin_ids,
        }
    return {
        "ok": True,
        "error": "",
        "recommendations": recommendations,
        "candidate_names": candidate_names,
        "unqualified_names": unqualified_names,
        "unknown_names": unknown_names,
        "area_id": area_id,
        "pickable": pickable,
        "kept": kept,
        "candidate_count": len(candidate_names),
        "slots": slots,
        "target_indexes": target_indexes,
        "csrf": csrf,
        "origin_ids": origin_ids,
    }


def _resolve_member_context(session, phone: str, member_token: str, member_cache: dict, token_error: str = "") -> dict:
    phone_norm = re.sub(r"\D", "", str(phone or ""))
    if len(phone_norm) == 9:
        phone_norm = "0" + phone_norm
    if not phone_norm:
        return {"ok": False, "error": "電話號碼缺失", "phone": ""}
    if phone_norm in member_cache:
        return member_cache[phone_norm]

    if not member_token:
        error = token_error or "無法取得會員查詢 token"
        payload = {"ok": False, "error": error, "phone": phone_norm, "member_id": "", "roster": {}, "roster_names": [], "preferred_gender_value": "", "preferred_gender_label": "無法取得"}
        member_cache[phone_norm] = payload
        return payload

    try:
        member_payload = orders.get_member(session, phone_norm, member_token, "1")
    except Exception as exc:
        payload = {"ok": False, "error": f"查詢會員失敗：{exc}", "phone": phone_norm, "member_id": "", "roster": {}, "roster_names": [], "preferred_gender_value": "", "preferred_gender_label": "無法取得"}
        member_cache[phone_norm] = payload
        return payload
    if not member_payload:
        payload = {"ok": False, "error": f"查無此會員：{phone_norm}", "phone": phone_norm, "member_id": "", "roster": {}, "roster_names": [], "preferred_gender_value": "", "preferred_gender_label": "無法取得"}
        member_cache[phone_norm] = payload
        return payload

    member = member_payload.get("member", {}) if isinstance(member_payload, dict) else {}
    member_id = str(member.get("member_id") or "").strip()
    if not member_id:
        payload = {"ok": False, "error": f"查詢會員成功但缺少 member_id：{phone_norm}", "phone": phone_norm, "member_id": "", "roster": {}, "roster_names": [], "preferred_gender_value": "", "preferred_gender_label": "無法取得"}
        member_cache[phone_norm] = payload
        return payload

    try:
        edit_page = orders.fetch_member_edit_page(session, member_id)
    except Exception as exc:
        payload = {"ok": False, "error": f"讀取會員編輯頁失敗：{exc}", "phone": phone_norm, "member_id": member_id, "roster": {}, "roster_names": [], "preferred_gender_value": "", "preferred_gender_label": "無法取得"}
        member_cache[phone_norm] = payload
        return payload

    roster = edit_page.get("roster") or {}
    roster_names = sorted(
        {
            str(info.get("name") or "").strip()
            for info in roster.values()
            if str(info.get("name") or "").strip() and "檸檬人" not in str(info.get("name") or "")
        }
    )
    preferred_gender_value = str(edit_page.get("fields", {}).get("preferredGender") or "0")
    payload = {
        "ok": True,
        "error": "",
        "phone": phone_norm,
        "member_id": member_id,
        "member_name": str(member.get("name") or ""),
        "roster": roster,
        "roster_names": roster_names,
        "preferred_gender_value": preferred_gender_value,
        "preferred_gender_label": preferred_gender_label(preferred_gender_value),
        "edit_page": edit_page,
    }
    member_cache[phone_norm] = payload
    return payload


def _build_qualification_text(candidate_names: list[str], unqualified_names: list[str], schedule_error: str = "",
                               member_error: str = "", area_id: str = "", unknown_names: list[str] | None = None) -> tuple[str, str]:
    """只看訂單當天該時段的未配班人員：符合＝詳細資料區域含此地址編號；未符合＝未含此編號。"""
    qualified_list = sorted(dict.fromkeys(str(x) for x in candidate_names if str(x)))
    unqualified_list = sorted(dict.fromkeys(str(x) for x in unqualified_names if str(x)))
    area_note = f"區域編號 {area_id}" if area_id else "此地址區域編號"

    if qualified_list:
        qualified_text = "、".join(qualified_list)
        if member_error:
            qualified_text += "（會員資料缺失，喜愛專員性別未判斷）"
    elif schedule_error and not area_id:
        qualified_text = f"無法判定：{schedule_error}"
    else:
        qualified_text = "無"

    if unqualified_list:
        unqualified_text = "、".join(unqualified_list) + f"（詳細資料區域未含{area_note}）"
    elif schedule_error and not area_id:
        unqualified_text = f"無法判定：{schedule_error}"
    else:
        unqualified_text = "無"
    if unknown_names:
        unqualified_text += "；無法判定：" + "、".join(unknown_names)
    return qualified_text, unqualified_text


def analyze_lemon_orders(
    session,
    base_url: str,
    found_orders: list[dict],
    member_token: str = "",
    token_error: str = "",
    limit: int = 3,
) -> list[dict]:
    member_cache: dict[str, dict] = {}
    staff_cache: dict[str, dict] = {}
    schedule_cache: dict[str, str] = {}
    analyzed: list[dict] = []
    for order in found_orders or []:
        row = dict(order)
        member_context = _resolve_member_context(session, order.get("phone", ""), member_token, member_cache, token_error=token_error)
        schedule_context = _get_schedule_context(
            session, base_url, order, limit=limit,
            gender_label=member_context.get("preferred_gender_label", "") if member_context.get("ok") else "",
            staff_cache=staff_cache, schedule_cache=schedule_cache,
        )

        qualified_text, unqualified_text = _build_qualification_text(
            schedule_context.get("candidate_names", []),
            schedule_context.get("unqualified_names", []),
            schedule_error=schedule_context.get("error", ""),
            member_error=member_context.get("error", ""),
            area_id=schedule_context.get("area_id", ""),
            unknown_names=schedule_context.get("unknown_names", []),
        )

        row.update(
            {
                "member_id": member_context.get("member_id", ""),
                "喜愛專員性別": member_context.get("preferred_gender_label", "無法取得"),
                "地址區域編號": schedule_context.get("area_id", ""),
                "可放入人員": schedule_context.get("pickable", []),
                "保留專員": schedule_context.get("kept", []),
                "會員狀態": member_context.get("error", "") or "OK",
                "班表狀態": schedule_context.get("error", "") or "OK",
                "符合該地址資格人員": qualified_text,
                "未符合資格人員": unqualified_text,
                "真實候選數": schedule_context.get("candidate_count", 0),
                "Top1": schedule_context.get("recommendations", [{}])[0].get("display", "") if schedule_context.get("recommendations") else "",
                "Top2": schedule_context.get("recommendations", [{}])[1].get("display", "") if len(schedule_context.get("recommendations") or []) > 1 else "",
                "Top3": schedule_context.get("recommendations", [{}])[2].get("display", "") if len(schedule_context.get("recommendations") or []) > 2 else "",
                "推薦列表": schedule_context.get("recommendations", []),
                "批次預設順位": "",
                "批次狀態": "",
                "處理": False,
                "可批次": False,
            }
        )

        analysis_ok = bool(schedule_context.get("ok")) and bool(member_context.get("ok"))
        if analysis_ok:
            row["批次狀態"] = "待分配"
            row["可批次"] = True
        else:
            reasons = [x for x in [schedule_context.get("error", ""), member_context.get("error", "")] if x]
            row["批次狀態"] = "；".join(reasons) if reasons else "資料不足"
            row["可批次"] = False

        analyzed.append(row)

    selected_by_date: dict[str, list[dict]] = defaultdict(list)
    for row in analyzed:
        if not row.get("可批次"):
            continue
        service_date = str(row.get("service_date") or "")
        chosen_index = None
        for index, recommendation in enumerate(row.get("推薦列表") or [], start=1):
            candidate_entry = {
                "service_date": service_date,
                "period": row.get("period", ""),
                "selected_names": list(recommendation.get("names") or []),
            }
            if any(_batch_entry_conflicts(candidate_entry, existing) for existing in selected_by_date[service_date]):
                continue
            chosen_index = index
            selected_by_date[service_date].append(candidate_entry)
            break
        if chosen_index is None:
            row["批次狀態"] = "同一服務日期＋時段的 Top1~Top3 都與其他訂單衝突，請人工分批處理"
            row["可批次"] = False
            row["處理"] = False
            row["批次預設順位"] = ""
            continue
        row["處理"] = True
        row["批次預設順位"] = f"Top{chosen_index}"
        row["批次狀態"] = "可勾選"

    return analyzed


def search_and_analyze_lemon_orders(
    env: str,
    email: str,
    password: str,
    date_s: str,
    date_e: str,
    payment_filter: str = "已付款",
    max_pages: int = 80,
) -> dict:
    session, base_url = _logged_in_session(env, email, password)
    token_error = ""
    member_token = ""
    try:
        try:
            member_token = orders.get_csrf_token(session)
        except Exception as exc:
            token_error = f"無法取得會員查詢 token：{exc}"
        found = _find_lemon_orders_with_session(session, date_s, date_e, payment_filter, max_pages)
        analyzed = analyze_lemon_orders(session, base_url, found, member_token=member_token, token_error=token_error)
        return {"found": found, "analyzed": analyzed, "member_token_error": token_error}
    finally:
        session.close()


def load_recommendations(env: str, email: str, password: str, order: dict, limit: int = 3, session=None, base_url=None) -> dict:
    own_session = session is None
    if session is None:
        session, base_url = _logged_in_session(env, email, password)
    else:
        if base_url is None:
            base_url = apply_env(orders, env)
    try:
        context = _get_schedule_context(session, base_url, order, limit=limit,
                                        gender_label=str(order.get("喜愛專員性別") or ""))
        if not context.get("ok"):
            raise RuntimeError(context.get("error") or "無法讀取後台換班頁，可能此訂單沒有可編輯的班表")
        return {
            "recommendations": context.get("recommendations", []),
            "candidate_count": context.get("candidate_count", 0),
        }
    finally:
        if own_session:
            session.close()


def _fetch_current_order(session, order_no: str) -> dict | None:
    params = dict(orders.PURCHASE_FILTER_PARAMS_TEMPLATE)
    params["orderNo"] = str(order_no)
    response = session.get(orders.PURCHASE_URL, params=params, headers=orders.HEADERS, allow_redirects=True)
    if response.status_code != 200:
        raise RuntimeError(f"送出前重查訂單失敗：HTTP {response.status_code}")
    for block in orders.extract_order_cards_from_purchase_html(response.text):
        if block.get("order_no") == order_no:
            return _order_from_block(block)
    return None


def replace_lemon_staff(env: str, email: str, password: str, order: dict, selected_names: list[str],
                        allow_partial: bool = False) -> dict:
    """送出前重讀換班頁；候選人若已失效就停止，不使用舊畫面資料寫入。"""
    session, base_url = _logged_in_session(env, email, password)
    try:
        current_order = _fetch_current_order(session, order["order_no"])
        if not current_order:
            raise RuntimeError("送出前已找不到這筆含檸檬人的訂單，請重新搜尋")
        if (
            current_order.get("service_date") != order.get("service_date")
            or current_order.get("period") != order.get("period")
            or current_order.get("current_staff") != order.get("current_staff")
        ):
            raise RuntimeError("訂單日期、時段或服務人員已變更，為避免覆蓋他人操作已停止，請重新搜尋")
        csrf, origin_ids, slots = _get_schedule_edit_info(
            session, base_url, order["service_date"], order["purchase_id"]
        )
        if not csrf or not origin_ids or len(origin_ids) != len(slots):
            raise RuntimeError("送出前無法重新確認換班頁，已停止寫入")
        target_indexes = _lemon_slot_indexes(order, len(slots))
        assignment = _match_names_to_slots(selected_names, slots, target_indexes, allow_partial=allow_partial)
        if not assignment:
            raise RuntimeError("推薦名單已不在目前可換班候選中，請重新產生推薦")

        selected_shift_ids = []
        fields = [("_token", csrf), ("_method", "PUT")]
        for origin_id in origin_ids:
            fields.append(("originShiftId[]", str(origin_id)))
        for index, origin_id in enumerate(origin_ids):
            shift_id = assignment[index]["shift_id"] if index in assignment else str(origin_id)
            fields.append((f"shiftId[{index}]", shift_id))
            selected_shift_ids.append(shift_id)

        response = session.post(
            f"{base_url}/schedule/edit",
            params={"date": order["service_date"], "purchase_id": order["purchase_id"]},
            data=fields,
            headers=orders.HEADERS,
            allow_redirects=True,
        )
        if response.status_code not in (200, 302):
            raise RuntimeError(f"後台換人失敗：HTTP {response.status_code}")

        _csrf_after, origin_after, _slots_after = _get_schedule_edit_info(
            session, base_url, order["service_date"], order["purchase_id"]
        )
        if [str(x) for x in origin_after] != selected_shift_ids:
            raise RuntimeError("後台已回應，但重新讀取後未確認到完整換人結果，請立即人工檢查")
        return {"success": True, "assigned": [assignment[i]["name"] for i in target_indexes if i in assignment],
                "lemon_left": len(target_indexes) - len(assignment)}
    finally:
        session.close()


def _order_label(order: dict) -> str:
    return (
        f"{order['service_date']} {order['period']}｜{order['order_no']}｜"
        f"{order.get('name') or '未解析姓名'}｜{order.get('staff') or '無人力'}"
    )


def _rank_label_to_index(label: str) -> int | None:
    text = str(label or "").strip()
    match = re.fullmatch(r"Top\s*([1-3])", text, flags=re.I)
    if match:
        return int(match.group(1))
    return None


def _build_batch_display_df(analyzed_orders: list[dict]) -> pd.DataFrame:
    rows = []
    for index, item in enumerate(analyzed_orders, start=1):
        rows.append(
            {
                "序號": index,
                "處理": bool(item.get("處理")),
                "採用順位": item.get("批次預設順位") or (item.get("Top1") and "Top1") or "",
                "批次預設": item.get("批次預設順位") or "",
                "批次狀態": item.get("批次狀態") or "",
                "服務日期": item.get("service_date", ""),
                "時段": item.get("period", ""),
                "訂單編號": item.get("order_no", ""),
                "姓名": item.get("name", ""),
                "電話": item.get("phone", ""),
                "地址": item.get("address", ""),
                "地址區域編號": item.get("地址區域編號", ""),
                "目前服務人員": item.get("staff", ""),
                "喜愛專員性別": item.get("喜愛專員性別", ""),
                "符合該地址資格人員": item.get("符合該地址資格人員", ""),
                "未符合資格人員": item.get("未符合資格人員", ""),
                "Top1": item.get("Top1", ""),
                "Top2": item.get("Top2", ""),
                "Top3": item.get("Top3", ""),
                "真實候選數": item.get("真實候選數", 0),
            }
        )
    return pd.DataFrame(rows)


def _run_batch_replacements(env: str, email: str, password: str, analyzed_orders: list[dict], edited_df: pd.DataFrame,
                            manual_picks: dict | None = None) -> list[dict]:
    """manual_picks：{列索引: [姓名…]}，有手動選人就用手動選的（可少於檸檬人位置）。"""
    manual_picks = manual_picks or {}
    planned = []
    for index, order in enumerate(analyzed_orders):
        row = edited_df.iloc[index] if index < len(edited_df) else None
        should_process = bool(row["處理"]) if row is not None and "處理" in row else False
        allowed = str(order.get("批次狀態") or "") == "可勾選"
        chosen_rank = _rank_label_to_index(row["採用順位"]) if row is not None and "採用順位" in row else None
        recommendations = order.get("推薦列表") or []
        manual_names = list(manual_picks.get(index) or [])
        if should_process and manual_names:
            error = validate_manual_pick(order, manual_names)
            planned.append({
                "序號": index + 1,
                "訂單編號": order.get("order_no", ""),
                "service_date": order.get("service_date", ""),
                "period": order.get("period", ""),
                "服務日期": order.get("service_date", ""),
                "時段": order.get("period", ""),
                "結果": "失敗" if error else "待寫入",
                "原因": error,
                "寫入專員": "",
                "writeable": not error,
                "order": order,
                "selected_names": manual_names,
                "allow_partial": True,
            })
            continue
        if not should_process:
            planned.append({
                "序號": index + 1,
                "訂單編號": order.get("order_no", ""),
                "service_date": order.get("service_date", ""),
                "period": order.get("period", ""),
                "服務日期": order.get("service_date", ""),
                "時段": order.get("period", ""),
                "結果": "略過",
                "原因": "使用者未勾選",
                "寫入專員": "",
                "writeable": False,
            })
        elif not allowed:
            planned.append({
                "序號": index + 1,
                "訂單編號": order.get("order_no", ""),
                "service_date": order.get("service_date", ""),
                "period": order.get("period", ""),
                "服務日期": order.get("service_date", ""),
                "時段": order.get("period", ""),
                "結果": "失敗",
                "原因": order.get("批次狀態", "不可處理"),
                "寫入專員": "",
                "writeable": False,
            })
        else:
            if chosen_rank is None:
                chosen_rank = 1
            if chosen_rank < 1 or chosen_rank > len(recommendations):
                planned.append({
                    "序號": index + 1,
                    "訂單編號": order.get("order_no", ""),
                    "service_date": order.get("service_date", ""),
                    "period": order.get("period", ""),
                    "服務日期": order.get("service_date", ""),
                    "時段": order.get("period", ""),
                    "結果": "失敗",
                    "原因": f"選擇的順位 Top{chosen_rank} 不存在",
                    "寫入專員": "",
                    "writeable": False,
                })
            else:
                selected = recommendations[chosen_rank - 1]
                planned.append({
                    "序號": index + 1,
                    "訂單編號": order.get("order_no", ""),
                    "service_date": order.get("service_date", ""),
                    "period": order.get("period", ""),
                    "服務日期": order.get("service_date", ""),
                    "時段": order.get("period", ""),
                    "結果": "待寫入",
                    "原因": "",
                    "寫入專員": "",
                    "writeable": True,
                    "order": order,
                    "selected_names": list(selected.get("names") or []),
                })

    conflicted_indexes = set()
    for left_index, left in enumerate(planned):
        if not left.get("writeable"):
            continue
        for right_index in range(left_index + 1, len(planned)):
            right = planned[right_index]
            if not right.get("writeable"):
                continue
            if _batch_entry_conflicts(left, right):
                conflicted_indexes.update({left_index, right_index})

    for index in conflicted_indexes:
        entry = planned[index]
        entry["結果"] = "失敗"
        entry["原因"] = "與其他同日重疊列共用正式專員，已擋下避免重複寫入"
        entry["寫入專員"] = ""
        entry["writeable"] = False

    results = []
    for entry in planned:
        if not entry.get("writeable"):
            results.append({k: v for k, v in entry.items() if k not in {"writeable", "order", "selected_names", "allow_partial"}})
        else:
            order = entry["order"]
            selected_names = entry["selected_names"]
            try:
                result = replace_lemon_staff(env, email, password, order, selected_names,
                                             allow_partial=bool(entry.get("allow_partial")))
                lemon_left = int(result.get("lemon_left") or 0)
                results.append(
                    {
                        "序號": entry["序號"],
                        "訂單編號": entry["訂單編號"],
                        "服務日期": entry["服務日期"],
                        "時段": entry["時段"],
                        "結果": "成功",
                        "原因": f"仍有 {lemon_left} 個檸檬人位置待補" if lemon_left else "",
                        "寫入專員": "、".join(result.get("assigned") or selected_names or []),
                    }
                )
            except Exception as exc:
                results.append(
                    {
                        "序號": entry["序號"],
                        "訂單編號": entry["訂單編號"],
                        "服務日期": entry["服務日期"],
                        "時段": entry["時段"],
                        "結果": "失敗",
                        "原因": str(exc),
                        "寫入專員": "",
                    }
                )
    return results


def _render_manual_picks(analyzed_orders: list[dict], edited_df: pd.DataFrame) -> dict:
    """勾選的列：可手動從「可放入人員」選要放誰（人數少於檸檬人位置時，其餘位置先留檸檬人）。"""
    picks = {}
    if edited_df is None or edited_df.empty or "處理" not in edited_df:
        return picks
    ticked = [i for i in range(min(len(analyzed_orders), len(edited_df))) if bool(edited_df.iloc[i]["處理"])]
    rows = [i for i in ticked if analyzed_orders[i].get("可放入人員")]
    if not ticked:
        return picks
    st.markdown("#### 手動選擇放入人員")
    st.caption("只列出當天該時段未配班、且符合地址資格的人（星等高到低）。有選人就用手動選的，不選則用『採用順位』的推薦。"
               "放入後整組平均星等需至少 4 分；喜愛專員性別一樣檢查。")
    for i in ticked:
        order = analyzed_orders[i]
        if i not in rows:
            st.caption(f"{_order_label(order)}：沒有可放入的人員（未配班且符合地址資格）")
            continue
        options = [item["name"] for item in order["可放入人員"]]
        info = {item["name"]: item for item in order["可放入人員"]}
        slots = int(order.get("lemon_count") or order.get("people_needed") or 0)
        chosen = st.multiselect(
            f"{_order_label(order)}（檸檬人 {slots} 位）",
            options,
            format_func=lambda n, info=info: f"{n}（{info[n]['rating']:g}星{'・' + info[n]['gender'] if info[n].get('gender') else ''}）",
            max_selections=slots or None,
            key=f"lemon_replace_manual_{order.get('order_no')}",
        )
        if chosen:
            error = validate_manual_pick(order, chosen)
            if error:
                st.warning(f"{order.get('order_no')}：{error}，這筆不會寫入")
            elif len(chosen) < slots:
                st.info(f"{order.get('order_no')}：先放入 {'、'.join(chosen)}，其餘 {slots - len(chosen)} 個位置留檸檬人")
            picks[i] = chosen
    return picks


def render(backend_email: str, backend_password: str, env: str) -> None:
    step("3", "檸檬人換正式專員")
    info_panel(
        "操作流程",
        [
            "依服務日期搜尋含『檸檬人』的訂單；適用一般單與保留單。",
            "搜尋後讀取每筆訂單地址的區域編號（訂單修改頁地址下方），以及班表上當天該時段「未配班」的人員。",
            "只檢查未配班人員：居家專員詳細資料的區域含此編號才符合；推薦只從符合的未配班人員挑，已配班的人不動。",
            "喜愛專員性別連同訂單上保留的專員一起判斷：限女＝全部女生、1女＝至少 1 位女生（男生同理）；專員性別看詳細資料的身分證字號（英文後第 1 碼 1＝男、2＝女）。",
            "表格會先自動套用同日同時段不衝突的 Top1~Top3 預設方案，讓你可直接批次勾選處理。",
            "按下批次寫入前仍需手動勾選確認；每筆送出前都會重新讀取後台，候選人若失效會停止該筆。",
        ],
    )
    st.caption(f"目前環境：{'正式機 prod' if env == 'prod' else '測試機 dev'}；只有最後確認按鈕會修改後台。")

    today = date.today()
    col1, col2, col3 = st.columns([1, 1, 1])
    with col1:
        date_s = st.date_input("服務日期起", value=today, key="lemon_replace_date_s")
    with col2:
        date_e = st.date_input("服務日期迄", value=today + timedelta(days=14), key="lemon_replace_date_e")
    with col3:
        payment_filter = st.selectbox("付款狀態", ["已付款", "待付款", "全部"], key="lemon_replace_payment")

    if st.button("搜尋含檸檬人的訂單", use_container_width=True, key="lemon_replace_search"):
        try:
            with st.spinner("正在一次登入並分析真實班表…"):
                result = search_and_analyze_lemon_orders(
                    env,
                    backend_email,
                    backend_password,
                    date_s.isoformat(),
                    date_e.isoformat(),
                    payment_filter,
                )
            found = result.get("found") or []
            analyzed = result.get("analyzed") or []
            st.session_state["lemon_replace_orders"] = found
            st.session_state["lemon_replace_analyzed_orders"] = analyzed
            st.session_state["lemon_replace_batch_results"] = []
            st.session_state["lemon_replace_analysis_key"] = (
                f"lemon_replace_editor_{date_s.isoformat()}_{date_e.isoformat()}_{payment_filter}_{len(analyzed)}"
            )
            if result.get("member_token_error"):
                st.warning(result["member_token_error"])
            if found:
                st.success(f"找到 {len(found)} 筆含檸檬人的訂單，並完成批量分析")
            else:
                st.info("此條件沒有找到含檸檬人的訂單")
        except Exception as exc:
            st.error(str(exc))

    analyzed_orders = st.session_state.get("lemon_replace_analyzed_orders") or []
    if not analyzed_orders:
        return

    st.dataframe(
        pd.DataFrame(
            [
                {
                    "服務日期": x["service_date"],
                    "時段": x["period"],
                    "訂單編號": x["order_no"],
                    "姓名": x.get("name", ""),
                    "電話": x.get("phone", ""),
                    "地址": x.get("address", ""),
                    "地址區域編號": x.get("地址區域編號", ""),
                    "目前服務人員": x.get("staff", ""),
                    "喜愛專員性別": x.get("喜愛專員性別", ""),
                    "符合該地址資格人員": x.get("符合該地址資格人員", ""),
                    "未符合資格人員": x.get("未符合資格人員", ""),
                    "Top1": x.get("Top1", ""),
                    "Top2": x.get("Top2", ""),
                    "Top3": x.get("Top3", ""),
                    "批次狀態": x.get("批次狀態", ""),
                }
                for x in analyzed_orders
            ]
        ),
        width="stretch",
        hide_index=True,
    )

    display_df = _build_batch_display_df(analyzed_orders)
    if not display_df.empty:
        editable_columns = ["處理", "採用順位"]
        column_config = {}
        column_config_api = getattr(st, "column_config", None)
        checkbox_column = getattr(column_config_api, "CheckboxColumn", None)
        selectbox_column = getattr(column_config_api, "SelectboxColumn", None)
        if checkbox_column:
            column_config["處理"] = checkbox_column("處理", help="勾選才會寫入後台")
        if selectbox_column:
            column_config["採用順位"] = selectbox_column(
                "採用順位",
                options=["Top1", "Top2", "Top3"],
                help="單筆可切換要使用哪個推薦順位",
            )
        disabled_columns = [col for col in display_df.columns if col not in editable_columns]
        edited_df = st.data_editor(
            display_df,
            use_container_width=True,
            hide_index=True,
            num_rows="fixed",
            column_config=column_config,
            disabled=disabled_columns,
            key=st.session_state.get("lemon_replace_analysis_key", "lemon_replace_editor"),
        )
        st.caption("可在『採用順位』欄改 Top2 / Top3；沒有推薦的列可在下方手動選擇要放入的人。")
    else:
        edited_df = display_df

    manual_picks = _render_manual_picks(analyzed_orders, edited_df)

    if analyzed_orders:
        with st.expander("單筆 Top1~3 詳情"):
            detail_labels = [
                f"{row['service_date']} {row['period']}｜{row['order_no']}｜{row.get('name') or '未解析姓名'}"
                for row in analyzed_orders
            ]
            detail_choice = st.selectbox("選擇單筆訂單", detail_labels, key="lemon_replace_detail_choice")
            detail_row = analyzed_orders[detail_labels.index(detail_choice)]
            st.write(
                {
                    "批次狀態": detail_row.get("批次狀態", ""),
                    "喜愛專員性別": detail_row.get("喜愛專員性別", ""),
                    "地址區域編號": detail_row.get("地址區域編號", ""),
                    "符合該地址資格人員": detail_row.get("符合該地址資格人員", ""),
                    "未符合資格人員": detail_row.get("未符合資格人員", ""),
                }
            )
            detail_options = [x for x in [detail_row.get("Top1"), detail_row.get("Top2"), detail_row.get("Top3")] if x]
            if detail_options:
                st.radio("單筆推薦組合", detail_options, key=f"lemon_replace_detail_rank_{detail_row['order_no']}")

    batch_confirm = st.checkbox("我已確認以上批次內容，允許寫入後台", key="lemon_replace_batch_confirm")
    can_submit = (
        batch_confirm
        and not edited_df.empty
        and (
            bool(((edited_df["處理"].fillna(False)) & (edited_df["批次狀態"].eq("可勾選"))).any())
            or any(not validate_manual_pick(analyzed_orders[i], names) for i, names in manual_picks.items())
        )
    )
    if st.button(
        "批次確認並寫入",
        type="primary",
        use_container_width=True,
        disabled=not can_submit,
        key="lemon_replace_batch_submit",
    ):
        try:
            with st.spinner("逐筆重新確認班表並執行換人…"):
                batch_results = _run_batch_replacements(env, backend_email, backend_password, analyzed_orders, edited_df,
                                                        manual_picks=manual_picks)
            st.session_state["lemon_replace_batch_results"] = batch_results
            result_df = pd.DataFrame(batch_results)
            success_count = sum(1 for item in batch_results if item.get("結果") == "成功")
            fail_count = sum(1 for item in batch_results if item.get("結果") == "失敗")
            skip_count = sum(1 for item in batch_results if item.get("結果") == "略過")
            st.success(f"批次完成：成功 {success_count}、失敗 {fail_count}、略過 {skip_count}")
            st.dataframe(result_df, width="stretch", hide_index=True)
        except Exception as exc:
            st.error(str(exc))

    batch_results = st.session_state.get("lemon_replace_batch_results") or []
    if batch_results:
        st.subheader("最近一次批次結果")
        st.dataframe(pd.DataFrame(batch_results), width="stretch", hide_index=True)
