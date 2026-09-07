# ============================================================
# 檔名：function/lemon_staff_replacement.py
# 功能：搜尋含檸檬人的訂單，依後台真實可換班名單推薦正式專員，人工確認後寫入。
# 更新時間：2026-09-08
# ============================================================
# -*- coding: utf-8 -*-
from __future__ import annotations

import re
from datetime import date, timedelta

import pandas as pd
import requests
import streamlit as st

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


def find_lemon_orders(
    env: str,
    email: str,
    password: str,
    date_s: str,
    date_e: str,
    payment_filter: str = "已付款",
    max_pages: int = 80,
) -> list[dict]:
    if not email or not password:
        raise ValueError("請先輸入後台帳號與密碼")
    if not date_s or not date_e or str(date_s) > str(date_e):
        raise ValueError("服務日期區間不正確")
    session, _base_url = _logged_in_session(env, email, password)
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


def _match_names_to_slots(names: list[str], slots: list[dict], target_indexes: list[int]):
    """把一組姓名配到不同的檸檬人槽位；同一人不得重複。"""
    wanted = list(dict.fromkeys(str(x) for x in names if str(x)))
    if len(wanted) != len(target_indexes):
        return None
    by_slot = {index: _candidate_map(slots[index]) for index in target_indexes}

    def walk(position: int, remaining: set[str], assigned: dict):
        if position == len(target_indexes):
            return assigned
        slot_index = target_indexes[position]
        for name in sorted(remaining):
            shift_id = by_slot[slot_index].get(name)
            if shift_id:
                result = walk(
                    position + 1,
                    remaining - {name},
                    {**assigned, slot_index: {"name": name, "shift_id": shift_id}},
                )
                if result:
                    return result
        return None

    return walk(0, set(wanted), {})


def load_recommendations(env: str, email: str, password: str, order: dict, limit: int = 3) -> dict:
    session, base_url = _logged_in_session(env, email, password)
    csrf, origin_ids, slots = _get_schedule_edit_info(
        session, base_url, order["service_date"], order["purchase_id"]
    )
    if not csrf or not origin_ids or not slots:
        raise RuntimeError("無法讀取後台換班頁，可能此訂單沒有可編輯的班表")
    if len(origin_ids) != len(slots):
        raise RuntimeError("後台換班頁槽位資料不完整，已停止推薦")

    target_indexes = _lemon_slot_indexes(order, len(slots))
    candidate_labels = {}
    for index in target_indexes:
        for label in slots[index]:
            name, rating = _staff_name_and_rating(label)
            if name and "檸檬人" not in name:
                candidate_labels[name] = max(candidate_labels.get(name, 0.0), rating)
    if len(candidate_labels) < len(target_indexes):
        raise RuntimeError("目前真實班表沒有足夠的正式專員可替換")

    plan_order = dict(order)
    plan_order["people_needed"] = len(target_indexes)
    candidate_rows = [
        {"staff_id": name, "name": name, "rating": rating, "available": True}
        for name, rating in candidate_labels.items()
    ]
    ranked = build_assignment_plan(plan_order, candidate_rows, limit=max(40, int(limit) * 10))
    recommendations = []
    for result in ranked:
        names = [member.name for member in result.staff]
        assignment = _match_names_to_slots(names, slots, target_indexes)
        if not assignment:
            continue
        recommendations.append({
            "names": names,
            "display": "＋".join(names),
            "score": round(result.score, 2),
            "average_rating": round(sum(x.rating for x in result.staff) / len(result.staff), 2),
            "reasons": "；".join(result.reasons) or "符合真實班表與基本配班規則",
        })
        if len(recommendations) >= max(1, int(limit)):
            break
    if not recommendations:
        raise RuntimeError("班表雖有候選人，但沒有符合『組合平均星等至少 4 分』及槽位限制的組合")
    return {"recommendations": recommendations, "candidate_count": len(candidate_labels)}


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


def replace_lemon_staff(env: str, email: str, password: str, order: dict, selected_names: list[str]) -> dict:
    """送出前重讀換班頁；候選人若已失效就停止，不使用舊畫面資料寫入。"""
    session, base_url = _logged_in_session(env, email, password)
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
    assignment = _match_names_to_slots(selected_names, slots, target_indexes)
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
    return {"success": True, "assigned": [assignment[i]["name"] for i in target_indexes]}


def _order_label(order: dict) -> str:
    return (
        f"{order['service_date']} {order['period']}｜{order['order_no']}｜"
        f"{order.get('name') or '未解析姓名'}｜{order.get('staff') or '無人力'}"
    )


def render(backend_email: str, backend_password: str, env: str) -> None:
    step("3", "檸檬人換正式專員")
    info_panel("操作流程", [
        "依服務日期搜尋含『檸檬人』的訂單；適用一般單與保留單。",
        "系統即時讀取該訂單後台換班頁，只使用當下真正可換班的正式專員。",
        "排除重複人員與平均星等低於 4 分的組合，顯示 Top 3 供人工選擇。",
        "按下確認前會再次讀取班表；候選人已失效時會停止，不會用舊資料強制寫入。",
    ])
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
            with st.spinner("正在搜尋後台訂單…"):
                found = find_lemon_orders(
                    env, backend_email, backend_password,
                    date_s.isoformat(), date_e.isoformat(), payment_filter,
                )
            st.session_state["lemon_replace_orders"] = found
            st.session_state.pop("lemon_replace_recommendations", None)
            if found:
                st.success(f"找到 {len(found)} 筆含檸檬人的訂單")
            else:
                st.info("此條件沒有找到含檸檬人的訂單")
        except Exception as exc:
            st.error(str(exc))

    found = st.session_state.get("lemon_replace_orders") or []
    if not found:
        return
    st.dataframe(pd.DataFrame([{
        "服務日期": x["service_date"], "時段": x["period"], "訂單編號": x["order_no"],
        "姓名": x.get("name", ""), "地址": x.get("address", ""), "目前服務人員": x.get("staff", ""),
    } for x in found]), width="stretch", hide_index=True)

    labels = [_order_label(x) for x in found]
    selected_label = st.selectbox("選擇要處理的訂單", labels, key="lemon_replace_order")
    selected_order = found[labels.index(selected_label)]
    if st.button("產生 Top 3 推薦", use_container_width=True, key="lemon_replace_rank"):
        try:
            with st.spinner("正在讀取真實班表並計算推薦…"):
                result = load_recommendations(env, backend_email, backend_password, selected_order, limit=3)
            st.session_state["lemon_replace_recommendations"] = {
                "order_no": selected_order["order_no"], **result,
            }
        except Exception as exc:
            st.session_state.pop("lemon_replace_recommendations", None)
            st.error(str(exc))

    recommendation_state = st.session_state.get("lemon_replace_recommendations") or {}
    if recommendation_state.get("order_no") != selected_order["order_no"]:
        return
    recommendations = recommendation_state.get("recommendations") or []
    st.caption(f"真實班表候選共 {recommendation_state.get('candidate_count', 0)} 位")
    st.dataframe(pd.DataFrame([{
        "順位": index + 1, "正式專員": item["display"], "平均星等": item["average_rating"],
        "推薦分數": item["score"], "推薦原因": item["reasons"],
    } for index, item in enumerate(recommendations)]), width="stretch", hide_index=True)

    option_labels = [f"Top {i + 1}｜{x['display']}" for i, x in enumerate(recommendations)]
    chosen_label = st.radio(
        "人工選擇換人組合", option_labels,
        key=f"lemon_replace_choice_{selected_order['order_no']}",
    )
    chosen = recommendations[option_labels.index(chosen_label)]
    confirmed = st.checkbox(
        f"我已確認訂單 {selected_order['order_no']}，要將其中檸檬人換成：{chosen['display']}",
        key=f"lemon_replace_confirm_{selected_order['order_no']}_{chosen['display']}",
    )
    if st.button(
        "確認並寫入後台",
        disabled=not confirmed,
        type="primary",
        use_container_width=True,
        key=f"lemon_replace_submit_{selected_order['order_no']}_{chosen['display']}",
    ):
        try:
            with st.spinner("送出前重新確認班表並執行換人…"):
                result = replace_lemon_staff(
                    env, backend_email, backend_password, selected_order, chosen["names"]
                )
            st.success(f"換人完成並已回查確認：{'、'.join(result['assigned'])}")
            st.session_state.pop("lemon_replace_recommendations", None)
            st.session_state["lemon_replace_orders"] = [
                item for item in found if item["order_no"] != selected_order["order_no"]
            ]
        except Exception as exc:
            st.error(str(exc))
