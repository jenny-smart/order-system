# -*- coding: utf-8 -*-
"""會員喜好設定。"""

import traceback

import streamlit as st

import quick_order as qo
from orders import fetch_member_edit_page, submit_member_preferences, fetch_recent_service_records
from function.ui_common import step, info_panel
from shared.execution_log_service import log_execution


def render(backend_email, backend_password, env):
    step("3", "會員喜好設定")
    info_panel("使用說明", [
        "輸入電話查詢會員，會列出目前設定的喜愛專員性別。",
        "下方會列出近 N 次「有排班」的服務紀錄（日期＋專員姓名），可針對每位出現過的專員勾選「喜愛」或「不喜愛」。",
        "按下「更新會員喜好設定」才會真的送出，其餘會員資料（姓名/電話/備註等）不會被更動。",
    ])
    mp_phone = st.text_input("客人電話", key="mp_phone")
    mp_n = st.number_input("列出近幾次服務紀錄", min_value=1, max_value=20, value=5, key="mp_n")
    if st.button("🔍 查詢會員", key="mp_lookup_btn"):
        if not mp_phone.strip():
            st.error("請輸入電話")
        elif not backend_email.strip() or not backend_password.strip():
            st.error("請先在上方輸入後台帳號密碼")
        else:
            try:
                with st.spinner("查詢會員中…"):
                    lookup = qo.quick_lookup_member(
                        env_name=env, backend_email=backend_email.strip(),
                        backend_password=backend_password.strip(),
                        phone=mp_phone.strip(),
                    )
                    if not lookup.get("member_payload"):
                        st.error("查無此會員")
                        st.session_state.mp_data = None
                    else:
                        member = lookup["member_payload"]["member"]
                        member_id = member["member_id"]
                        edit_page = fetch_member_edit_page(lookup["session"], member_id)
                        records = fetch_recent_service_records(
                            lookup["session"], mp_phone.strip(), member.get("name", ""), n=int(mp_n),
                        )
                        st.session_state.mp_data = {
                            "session": lookup["session"], "member_id": member_id,
                            "member_name": member.get("name", ""), "edit_page": edit_page,
                            "records": records,
                        }
            except Exception as e:
                st.error(f"查詢失敗：{e}")
                st.session_state.mp_data = None

    mp_data = st.session_state.get("mp_data")
    if mp_data:
        st.success(f"✅ 會員：{mp_data['member_name']}")
        gender_labels = ["不限", "限女", "1女", "限男", "1男", "1男1女"]
        current_gender = int(mp_data["edit_page"]["fields"].get("preferredGender") or "0")
        mp_gender_choice = st.radio(
            "喜愛專員性別", gender_labels, index=current_gender, key="mp_gender", horizontal=True,
        )

        roster = mp_data["edit_page"]["roster"]
        # 依姓名建立 name -> cleaner_id 對照（同名時取第一個符合的，並在畫面上提醒可能有同名狀況）
        name_to_ids = {}
        for cid, info in roster.items():
            name_to_ids.setdefault(info["name"], []).append(cid)

        if not mp_data["records"]:
            st.info("查無近期有排班的服務紀錄。")
        else:
            st.markdown("**近期服務紀錄：**")
            unique_names = []
            for rec in mp_data["records"]:
                date_part = f"{rec['date_clean']}（{rec['order_no']}）" if rec["order_no"] else rec["date_clean"]
                st.caption(f"{date_part}：{' X '.join(rec['cleaner_names']) or '（無資料）'}")
                for cn in rec["cleaner_names"]:
                    if cn not in unique_names:
                        unique_names.append(cn)

            st.markdown("**設定喜愛/不喜愛專員：**（同一位不能同時勾選兩個，若都勾了送出前會被擋下並提示）")
            pref_choices = {}
            has_conflict = False
            for cn in unique_names:
                ids = name_to_ids.get(cn, [])
                if not ids:
                    st.warning(f"⚠️「{cn}」在會員編輯頁的專員名單裡找不到對應資料，無法設定（可能是離職或名字打法不同）。")
                    continue
                if len(ids) > 1:
                    st.caption(f"（注意：「{cn}」有 {len(ids)} 位同名專員，將套用到第一位，麻煩人工確認是否正確）")
                cid = ids[0]

                # v2026.07.07 修正：改成兩個獨立的勾選框放在姓名前面
                # （喜愛專員／不喜愛專員），取代原本的單選按鈕。
                col_like, col_dislike, col_name = st.columns([1, 1.3, 3])
                with col_like:
                    is_liked = st.checkbox("喜愛專員", value=roster[cid]["liked"], key=f"mp_like_{cid}")
                with col_dislike:
                    is_disliked = st.checkbox("不喜愛專員", value=roster[cid]["disliked"], key=f"mp_dislike_{cid}")
                with col_name:
                    st.markdown(f"　{cn}")

                if is_liked and is_disliked:
                    st.error(f"「{cn}」不能同時勾選喜愛和不喜愛，請取消其中一個。")
                    has_conflict = True

                pref_choices[cid] = "喜愛" if is_liked else ("不喜愛" if is_disliked else "不變")

            if st.button("✅ 更新會員喜好設定", key="mp_submit_btn", type="primary", disabled=has_conflict):
                try:
                    liked_ids = {cid for cid, info in roster.items() if info["liked"]}
                    disliked_ids = {cid for cid, info in roster.items() if info["disliked"]}
                    for cid, choice in pref_choices.items():
                        liked_ids.discard(cid)
                        disliked_ids.discard(cid)
                        if choice == "喜愛":
                            liked_ids.add(cid)
                        elif choice == "不喜愛":
                            disliked_ids.add(cid)
                    with st.spinner("更新中…"):
                        submit_member_preferences(
                            mp_data["session"], mp_data["member_id"], mp_data["edit_page"],
                            preferred_gender=gender_labels.index(mp_gender_choice),
                            liked_ids=liked_ids, disliked_ids=disliked_ids,
                        )
                    st.success("✅ 已更新會員喜好設定。")
                    log_execution(
                        function_name="更新會員喜好設定", status="成功",
                        target=mp_data["member_name"],
                        message=f"手機：{mp_phone.strip()}；性別偏好：{mp_gender_choice}",
                    )
                    st.session_state.mp_data = None
                except Exception as e:
                    st.error(f"更新失敗：{e}")
                    log_execution(
                        function_name="更新會員喜好設定", status="失敗",
                        target=mp_data["member_name"],
                        message=str(e), traceback_text=traceback.format_exc(),
                    )
