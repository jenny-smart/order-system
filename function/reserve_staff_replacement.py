# ============================================================
# 檔名：function/reserve_staff_replacement.py
# 功能：檸檬保留單換正式專員；先產生可行專員組合與推薦原因，確認後才進入實際換人階段。
# 更新時間：2026-08-19
# ============================================================
# -*- coding: utf-8 -*-
from __future__ import annotations

import pandas as pd
import streamlit as st

from function.ui_common import step, info_panel
from shared.staff_assignment_core import AssignmentContext, StaffCandidate, rank_combinations


def build_assignment_plan(order: dict, candidate_rows: list[dict], limit: int = 20):
    """純函式入口：供 UI／未來自動排班共用。candidate_rows 可由班表、專員資料、交通服務組合後傳入。"""
    ctx = AssignmentContext(
        order_no=str(order.get("order_no") or ""),
        service_date=str(order.get("service_date") or ""),
        period=str(order.get("period") or ""),
        address=str(order.get("address") or ""),
        people_needed=int(order.get("people_needed") or 2),
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
    candidates = []
    for row in candidate_rows or []:
        candidates.append(StaffCandidate(
            staff_id=str(row.get("staff_id") or ""),
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
        ))
    return rank_combinations(ctx, candidates, limit=limit)


def render(backend_email: str, backend_password: str, env: str) -> None:
    step("3", "檸檬保留單換正式專員")
    info_panel("功能說明", [
        "目標是把保留單目前占位的『檸檬人』換成真正適合服務客戶的正式專員。",
        "第一優先不是『有空就排』，而是專員能合理到達客人地址：家→案場、上一案場→本案場、本案場→家。",
        "先套硬性限制，再比較多人專員組合；不會把同一位專員重複安排在同一張多人訂單。",
        "目前第一版先建立『推薦／規則引擎』，不會自動改後台排班；確認資料來源與推薦結果後再開啟實際換人寫入。",
    ])
    info_panel("已納入第一版規則", [
        "星等組合不得低於 4 分；VIP／舊客優先安排曾服務過的專員。",
        "性別、身高／體型、客訴禁排、特殊技能、專員不擅長案場屬硬性限制。",
        "喜愛專員、客戶個性適配、案場適配、特殊清潔、減少機器調度、夥伴互補納入排序。",
        "避開不能一起排的夥伴；觀察名單與實習專員會降低排序，之後可再補更細的搭配規則。",
    ])

    st.info("第一版核心已建立。下一步會接：保留單查詢 → 真實專員班表 → 地址交通資料 → 推薦組合 → 人工確認 → 後台換人。")
    st.caption(f"目前環境：{'正式機 prod' if env == 'prod' else '測試機 dev'}；此頁目前不會修改後台資料。")

    demo = st.session_state.get("reserve_staff_replacement_preview") or []
    if demo:
        st.dataframe(pd.DataFrame(demo), width="stretch", hide_index=True)
