# -*- coding: utf-8 -*-
"""清潔細項 UI（建立新客／舊客訂單共用）：依服務類別顯示居家或辦公室欄位，可貼評估備註自動補填。"""
from __future__ import annotations

import streamlit as st

from shared import cleaning_pattern as cp

KEEP_PING = "依客人資料"


def _ping_key(k, clean_type_id):
    return f"{k}_ping_{'office' if cp.is_office(clean_type_id) else 'home'}"


def _apply_assessment(k, clean_type_id):
    text = st.session_state.get(f"{k}_assess", "")
    r = cp.parse_assessment(text, clean_type_id)
    for key, _label in cp.count_fields(clean_type_id):
        st.session_state[f"{k}_cnt_{key}"] = int(r["counts"].get(key, 0))
    for key, _label in cp.flag_fields(clean_type_id):
        st.session_state[f"{k}_flag_{key}"] = r["flags"].get(key) == "1"
    if r["ping"]:
        labels = dict(cp.ping_options(clean_type_id))
        st.session_state[_ping_key(k, clean_type_id)] = labels.get(r["ping"], KEEP_PING)
    st.session_state[f"{k}_assess_result"] = r


def render_pattern_inputs(key_prefix, clean_type_id, title="🏠 清潔項目細節（選填，用於計算時數）",
                          ping_keep_label=KEEP_PING, expanded=False):
    """回傳 {"used": 是否有填, "ping": 代號或 ""（沿用客人資料／舊單）, "fields": pattern_fields 結果}。"""
    k = f"{key_prefix}_pat"
    office = cp.is_office(clean_type_id)
    with st.expander(title + ("（辦公室）" if office else ""), expanded=expanded):
        st.text_area(
            "貼上評估備註（可選）", key=f"{k}_assess", height=140,
            placeholder="評估項目：\n31-40p\n3房間\n2衛浴\n廚房\n書房\n4窗戶\n3落地窗" if not office
            else "評估項目：\n21-40p\n2辦公室\n會議室\n1廁所\n茶水間\n20座位\n6窗戶",
        )
        st.button("📋 依評估備註填入下方細項", key=f"{k}_apply", on_click=_apply_assessment, args=(k, clean_type_id))
        st.caption("換算：書房＝房間＋1、餐廳＝客廳＋1、落地窗算窗戶；沒寫數字算 1；坪數「31-40p」取上限。")
        r = st.session_state.get(f"{k}_assess_result")
        if r:
            if r["details"]:
                st.caption("已判讀：" + "、".join(f"{a}→{b}" for a, b in r["details"]))
            if r["unknown"]:
                st.warning("看不懂、未填入的項目（請手動確認）：" + "、".join(r["unknown"]))

        opts = [ping_keep_label] + [label for _code, label in cp.ping_options(clean_type_id)]
        pk = _ping_key(k, clean_type_id)
        if st.session_state.get(pk) not in opts:
            st.session_state.pop(pk, None)
        ping_sel = st.selectbox("室內總坪數", opts, key=pk)
        code_by_label = {label: code for code, label in cp.ping_options(clean_type_id)}

        counts = {}
        cfields = cp.count_fields(clean_type_id)
        cols = st.columns(len(cfields))
        for col, (key, label) in zip(cols, cfields):
            with col:
                counts[key] = st.number_input(label, min_value=0, max_value=200, key=f"{k}_cnt_{key}")
        st.markdown("**加購／其他**")
        flags = {}
        ffields = cp.flag_fields(clean_type_id)
        fcols = st.columns(min(len(ffields), 6))
        for i, (key, label) in enumerate(ffields):
            with fcols[i % len(fcols)]:
                flags[key] = "1" if st.checkbox(label, key=f"{k}_flag_{key}") else "0"

    ping = code_by_label.get(ping_sel, "")
    used = bool(ping or any(counts.values()) or any(v == "1" for v in flags.values()))
    return {"used": used, "ping": ping, "fields": cp.pattern_fields(clean_type_id, counts, flags, ping or None)}
