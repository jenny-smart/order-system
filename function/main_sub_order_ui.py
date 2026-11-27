# -*- coding: utf-8 -*-
"""主單＋補單 UI：建立舊客／新客訂單共用。

- render_person_hour_coupon：主單用「依人時建立優惠券」，建好自動填入優惠代碼欄。
- render_main_sub_section：主單建好後，設定主單檸檬人數＋補單，一鍵建立補單並寫合併備註。
"""
from __future__ import annotations

import traceback
from datetime import date, datetime

import streamlit as st

import quick_order as qo
from function.ui_common import copy_button
from shared import main_sub_order as ms
from shared.execution_log_service import log_execution

PERIOD_OPTIONS = [
    "08:30-12:30", "09:00-11:00", "09:00-12:00",
    "14:00-16:00", "14:00-17:00", "14:00-18:00",
    "09:00-16:00", "09:00-18:00",
]
PERIOD_HOUR_MAP = {
    "08:30-12:30": 4, "09:00-11:00": 2, "09:00-12:00": 3,
    "14:00-16:00": 2, "14:00-17:00": 3, "14:00-18:00": 4,
    "09:00-16:00": 6, "09:00-18:00": 8,
}
SERVICE_LABELS = ["居家清潔", "辦公室清潔", "裝修細清"]


def _as_date(value):
    if isinstance(value, date):
        return value
    try:
        return datetime.strptime(str(value)[:10].replace("/", "-"), "%Y-%m-%d").date()
    except Exception:
        return date.today()


def render_person_hour_coupon(backend_email, backend_password, env, key_prefix, target_key,
                              default_region="台北", default_tier="regular", member_name=""):
    """主單優惠券：輸入優惠人時（例 1人2小時）→ 依服務日期單價建券 → 填入 target_key 的優惠代碼欄。

    必須在優惠代碼 text_input（key=target_key）之前呼叫。
    """
    k = f"{key_prefix}_phc"
    with st.expander("🎟️ 依人時建立優惠券（主單折抵用，例：1人2小時）", expanded=False):
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            svc_date = st.date_input("服務日期（決定單價）", value=date.today(), key=f"{k}_date")
        with c2:
            person = st.number_input("優惠人數", min_value=1, max_value=8, value=1, key=f"{k}_person")
        with c3:
            hour = st.number_input("優惠時數", min_value=1, max_value=8, value=2, key=f"{k}_hour")
        with c4:
            tier_label = st.selectbox("計價", ["VIP", "一般客"], index=0 if default_tier == "vip" else 1, key=f"{k}_tier")
        c5, c6, c7 = st.columns(3)
        with c5:
            region = st.selectbox("地區", ["台北", "台中"], index=1 if default_region == "台中" else 0, key=f"{k}_region")
        with c6:
            svc_label = st.selectbox("服務類別", SERVICE_LABELS, key=f"{k}_svc")
        with c7:
            title_name = st.text_input("訂購人姓名（券標題）", value=member_name or "", key=f"{k}_name")
        tier = "vip" if tier_label == "VIP" else "regular"
        ph = int(person) * int(hour)
        try:
            amount = ms.coupon_amount_for_person_hours(svc_date.strftime("%Y-%m-%d"), ph, tier)
        except Exception as e:
            amount = 0
            st.error(f"單價讀取失敗：{e}")
        st.caption(f"優惠 {ph} 人時 × 每人時單價 → 折抵 {amount:,} 元（標題：{title_name}{amount}）")

        def _create():
            try:
                res = qo.create_coupon(
                    env, backend_email.strip(), backend_password.strip(),
                    title=f"{title_name.strip()}{amount}", discount=amount,
                    date_s=date.today().strftime("%Y-%m-%d"), date_e=svc_date.strftime("%Y-%m-%d"),
                    prefix=qo._coupon_prefix(region, "cp" + date.today().strftime("%m%d")),
                    piece=1, regions=[region], service_items=[svc_label],
                )
                code = res.get("coupon_code") or ""
                if not code:
                    raise Exception("後台未回傳優惠碼")
                st.session_state[target_key] = code
                st.session_state[f"{k}_msg"] = ("ok", f"✅ 已建立優惠券 {code}（折 {amount:,} 元），已填入優惠代碼欄")
                log_execution(function_name="主單依人時建立優惠券", status="成功", area=region,
                              target=code, message=f"{ph}人時 {amount}元")
            except Exception as e:
                st.session_state[f"{k}_msg"] = ("err", f"優惠券建立失敗：{e}")
                log_execution(function_name="主單依人時建立優惠券", status="失敗", area=region,
                              message=str(e), traceback_text=traceback.format_exc())

        disabled = not (backend_email.strip() and backend_password.strip() and amount > 0 and title_name.strip())
        st.button("建立優惠券並填入", key=f"{k}_btn", on_click=_create, disabled=disabled)
        msg = st.session_state.get(f"{k}_msg")
        if msg:
            (st.success if msg[0] == "ok" else st.error)(msg[1])
        st.caption("若主單最後沒建立成功，這張券不會被使用；可在重試時沿用同一個優惠碼。")


def render_main_sub_section(backend_email, backend_password, env, key_prefix, main_order_no="",
                            main_date=None, main_person=4, main_hour=8, main_period_s=""):
    """主單建好後：主單檸檬人數＋補單（實際出班人數／時段），建補單並寫合併備註。"""
    k = f"{key_prefix}_ms"
    st.markdown("<hr>", unsafe_allow_html=True)
    with st.expander("➕ 主單＋補單（大單一次刷卡：主單收款、補單補實際人數時數）", expanded=False):
        st.caption(
            "主單可先放檸檬人（還沒排班可放多位），佔位的檸檬人時數由補單補；檸檬人人時須少於主單＋補單。"
            "補單用優惠券折到 0 → 已付款＋不開立發票；主單＋補單客人備註寫合併訂單與每個時段幾人，有檸檬人的訂單客服備註加「檸檬人勿動」。"
        )
        c1, c2, c3, c4, c5, c6 = st.columns(6)
        with c1:
            order_no = st.text_input("主單編號", value=main_order_no or "", key=f"{k}_no")
        with c2:
            m_person = st.number_input("主單人數", min_value=1, max_value=10, value=int(main_person or 4), key=f"{k}_mp")
        with c3:
            m_hour = st.number_input("主單時數", min_value=1, max_value=8, value=int(main_hour or 8), key=f"{k}_mh")
        with c4:
            lemon = st.number_input("主單檸檬人數", min_value=0, max_value=10, value=1, key=f"{k}_lemon",
                                    help="成單時還沒排班可先放多位（甚至全部）檸檬人，再由排班人員置換")
        with c5:
            placeholder = st.number_input("其中佔位人數", min_value=0, max_value=10, value=1, key=f"{k}_ph",
                                          help="時數由補單補、不會有人去上班的檸檬人；備註的每時段人數會扣掉")
        with c6:
            coupon_ph = st.number_input("主單優惠人時", min_value=0, max_value=80, value=0, key=f"{k}_cph",
                                        help="主單用優惠券折掉的人時（例：1人2小時填 2），只用來核對付費人時")
        n = st.number_input("補單筆數", min_value=1, max_value=6, value=1, key=f"{k}_n")
        subs = []
        for i in range(int(n)):
            s1, s2, s3, s4 = st.columns([2, 2, 1, 2])
            with s1:
                d = st.date_input(f"補單{i+1} 日期", value=_as_date(main_date), key=f"{k}_d{i}")
            with s2:
                p = st.selectbox(f"補單{i+1} 時段", PERIOD_OPTIONS, index=2, key=f"{k}_p{i}")
            with s3:
                ppl = st.number_input(f"補單{i+1} 人數", min_value=1, max_value=8, value=1, key=f"{k}_ppl{i}")
            with s4:
                h = PERIOD_HOUR_MAP.get(p, 3)
                allow = st.checkbox(f"{h}小時｜無人力時補檸檬人", value=False, key=f"{k}_al{i}")
            subs.append({"date_s": d.strftime("%Y-%m-%d"), "period_s": p, "person": int(ppl), "hour": h, "allow_lemon": allow})

        plan = ms.summarize_plan(m_person, m_hour, lemon, coupon_ph, subs, placeholder)
        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("客人付費", f"{plan['paid_ph']} 人時")
        m2.metric("主單＋補單", f"{plan['total_ph']} 人時")
        m3.metric("檸檬人", f"{plan['lemon_ph']} 人時")
        m4.metric("實際出班", f"{plan['actual_ph']} 人時")
        m5.metric("贈送", f"{max(plan['gift_ph'], 0)} 人時")
        if not plan["errors"]:
            st.caption("備註預覽：" + ms.build_merge_note(order_no or "主單", ["補單…"], m_person, main_period_s or "09:00-18:00", plan["placeholder"], subs))
        for e in plan["errors"]:
            st.error(e)

        if st.button("🚀 調整主單檸檬人＋建立補單＋寫合併備註", key=f"{k}_run", type="primary",
                     use_container_width=True, disabled=bool(plan["errors"] or not order_no.strip())):
            st.session_state[f"{k}_result"] = None
            try:
                with st.spinner("讀取主單 → 調整檸檬人 → 建補單優惠券 → 建補單 → 標記已付款 → 寫合併備註…"):
                    res = ms.run_main_sub(env, backend_email.strip(), backend_password.strip(), order_no.strip(),
                                          int(lemon), subs, coupon_person_hours=int(coupon_ph),
                                          placeholder_count=int(placeholder))
                st.session_state[f"{k}_result"] = res
                ok_nos = [r["order_no"] for r in res["sub_results"] if r.get("order_no")]
                log_execution(function_name="主單＋補單", status="成功" if len(ok_nos) == len(subs) else "部分失敗",
                              target=order_no.strip(), message=f"補單：{'、'.join(ok_nos) or '（無）'}")
            except Exception as e:
                st.error(f"主單＋補單失敗：{e}")
                log_execution(function_name="主單＋補單", status="失敗", target=order_no.strip(),
                              message=str(e), traceback_text=traceback.format_exc())

        res = st.session_state.get(f"{k}_result")
        if res:
            if res["main_person"] != int(m_person) or res["main_hour"] != int(m_hour):
                st.warning(f"後台主單實際為 {res['main_person']}人{res['main_hour']}小時，已以後台資料核算。")
            st.info(res["lemon_result"].get("message", ""))
            for r in res["sub_results"]:
                if r.get("order_no"):
                    paid = "已付款＋不開立發票" if r.get("paid_ok") and r.get("invoice_ok") else f"⚠️ {r.get('paid_msg')}／{r.get('invoice_msg')}"
                    st.success(f"✅ 補單{r['index']}：{r['order_no']}　{r['date_s']} {r['period_s']}　{r['person']}人{r['hour']}小時　"
                               f"券 {r.get('coupon_code') or '—'}（折 {r.get('price', 0):,}）　{paid}　專員：{r.get('staff') or '—'}")
                else:
                    st.error(f"❌ 補單{r['index']}（{r['date_s']} {r['period_s']} {r['person']}人）失敗：{r.get('error')}")
            if res["note_results"]:
                st.markdown(f"**合併備註**：{res['note']}")
                for nr in res["note_results"]:
                    (st.caption if nr["ok"] else st.warning)(f"{nr['order_no']} 備註：{'✅ ' if nr['ok'] else '⚠️ 需手動貼上 '}{nr['msg']}")
            if res.get("line_message"):
                st.text_area("合併 LINE 訊息", res["line_message"], height=320, label_visibility="collapsed")
                copy_button("複製合併 LINE 訊息", res["line_message"], f"{k}_copy_line")
