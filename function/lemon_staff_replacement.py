# ============================================================
# 檔名：function/lemon_staff_replacement.py
# 功能：任何訂單只要含「檸檬人」占位，即進入正式專員推薦／換人流程；不限定保留單。
# 更新時間：2026-08-19
# ============================================================
# -*- coding: utf-8 -*-
from __future__ import annotations

import pandas as pd
import streamlit as st

from function.ui_common import step, info_panel
from shared.staff_assignment_core import AssignmentContext, StaffCandidate, rank_combinations


def build_assignment_plan(order: dict, candidate_rows: list[dict], limit: int = 20):
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
    step("3", "檸檬人換正式專員")
    info_panel("功能說明", [
        "適用所有訂單，不限定保留單；只要目前服務人員含『檸檬人』就可進入換人流程。",
        "第一優先是正式專員實際能到達客人地址，再考慮星等、熟客、喜愛專員與案件適配。",
        "交通分三段評估：家→案場、上一案場→本案場、本案場→家。",
        "多人訂單比較的是整組搭配，不會重複使用同一位專員；組合平均星等不得低於 4 分。",
        "目前先提供推薦／模擬模式，不會自動修改正式機；下一階段接後台訂單搜尋與實際換人寫入。",
    ])
    st.info("推薦核心已可使用；下一步會接『期間搜尋含檸檬人的訂單 → 真實班表候選 → Top 3 推薦 → 人工確認換人』。")
    st.caption(f"目前環境：{'正式機 prod' if env == 'prod' else '測試機 dev'}；本頁目前不會修改後台資料。")
    preview = st.session_state.get("lemon_staff_replacement_preview") or []
    if preview:
        st.dataframe(pd.DataFrame(preview), width="stretch", hide_index=True)
