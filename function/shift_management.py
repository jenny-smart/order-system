# -*- coding: utf-8 -*-
"""排班管理（排班匯入／檸檬人勾班／清空排班）。"""

import re

import streamlit as st

from memo_system import shift
from function.ui_common import step
from function.memo_shared import get_session


def render_shift_import_section(email, env_option):
    step("3", "上傳排班匯入檔")
    st.markdown('<div class="info-strip"><b>檔案欄位</b><ul><li>地區、日期、類型、時段、名稱</li></ul><b>支援類型</b><ul><li>全6、全8、上4、上3、上2、下4、下3、下2、晚2、清</li></ul></div>', unsafe_allow_html=True)
    st.markdown('<div class="warn-strip"><b>注意</b><ul><li>正式儲存會直接修改後台排班</li><li>請先用 Dry Run 確認結果</li></ul></div>', unsafe_allow_html=True)

    uploaded_file = st.file_uploader("選擇 Excel / CSV 檔案", type=["xlsx", "xls", "csv"])
    c1, c2 = st.columns(2)
    with c1:
        dry_run_btn = st.button("🔍 Dry Run 預覽（不會寫入）", use_container_width=True, disabled=not (st.session_state.credentials_ready and uploaded_file is not None))
    with c2:
        execute_btn = st.button("🚀 正式儲存", use_container_width=True, disabled=not (st.session_state.credentials_ready and st.session_state.shift_dry_run_result is not None))

    with st.expander("執行 LOG", expanded=True):
        log_box_local = st.empty()
        log_box_local.text("\n".join(st.session_state.logs[-3000:]) if st.session_state.logs else "尚未執行")

    def shift_ui_log(msg):
        st.session_state.logs.append(str(msg))
        try: log_box_local.text("\n".join(st.session_state.logs[-3000:]))
        except: pass

    if dry_run_btn and uploaded_file is not None:
        try:
            st.session_state.logs = []; st.session_state.shift_dry_run_result = None
            shift_ui_log("===== 開始解析匯入檔 =====")
            rows = shift.parse_import_file(uploaded_file, uploaded_file.name)
            shift_ui_log(f"解析完成，共 {len(rows)} 筆有效資料")
            st.session_state.shift_import_rows = rows
            with st.spinner("Dry Run 中，請稍候…"):
                session = get_session(email, env_option, ui_logger=shift_ui_log)
                result = shift.process_import_file(rows, dry_run=True, ui_logger=shift_ui_log, session=session)
            st.session_state.shift_dry_run_result = result
            shift_ui_log("===== Dry Run 完成 =====")
        except Exception as e:
            shift_ui_log(f"❌ Dry Run 失敗：{e}"); st.error(str(e))

    if st.session_state.shift_dry_run_result:
        result = st.session_state.shift_dry_run_result
        st.markdown("---"); step("4", "Dry Run 結果預覽")
        m1, m2, m3 = st.columns(3)
        m1.metric("處理人數", result.get("processed_people", 0))
        m2.metric("處理月份數", result.get("processed_months", 0))
        m3.metric("略過人數", len(result.get("skipped", [])))
        if result.get("errors"):
            with st.expander(f"⚠️ 訊息（{len(result['errors'])} 筆）", expanded=True):
                for i, err in enumerate(result["errors"], 1): st.markdown(f"**{i}.** {err}")
        for name, month, merged in result.get("dry_run_payloads", []):
            with st.expander(f"{name} — {month}（合併後共 {len(merged)} 筆勾選）", expanded=False):
                if merged: st.text("\n".join(f"{k} = {v}" for k, v in sorted(merged.items())))
                else: st.caption("這個月份合併後沒有任何勾選（可能是被「清」全部清空了）")
        st.caption("確認上面合併後的結果沒有問題，再按「正式儲存」送出。")

    if execute_btn:
        try:
            st.session_state.logs = []; shift_ui_log("===== 開始正式儲存 =====")
            rows = st.session_state.shift_import_rows
            with st.spinner("儲存中，請稍候…"):
                session = get_session(email, env_option, ui_logger=shift_ui_log)
                result = shift.process_import_file(rows, dry_run=False, ui_logger=shift_ui_log, session=session)
            shift_ui_log("===== 儲存完成 =====")
            st.success(f"✅ 完成，共儲存 {result.get('saved', 0)} 個人/月份")
            if result.get("errors"): st.error("\n".join(result["errors"][:20]))
            st.session_state.shift_dry_run_result = None
        except Exception as e:
            shift_ui_log(f"❌ 儲存失敗：{e}"); st.error(str(e))


def render_lemon_assign_section(email, env_option):
    step("3", "設定檸檬人勾班條件")
    st.markdown("""
    <div class="warn-strip">
    <b>注意</b>
    <ul>
    <li>會直接修改後台排班</li>
    <li>指定日期內原本已勾選的全日/上午/下午/晚上，會先清掉再套用本次選擇的班別</li>
    <li>請確認檸檬人名單、日期區間與班別後再執行</li>
    <li>多人請用逗號分隔，例如：<code>檸檬人1,檸檬人2,檸檬人3,檸檬人4,檸檬人5,檸檬人6,檸檬人7,檸檬人8,檸檬人9,檸檬人10,檸檬人11,檸檬人12</code></li>
    </ul>
    </div>
    """, unsafe_allow_html=True)

    c1, c2, c3 = st.columns([2, 1.3, 1.3])
    with c1:
        lemon_names_raw = st.text_input("檸檬人名單", placeholder="檸檬人1,檸檬人2,檸檬人3", key="lemon_assign_names")
    with c2:
        assign_start = st.date_input("開始日期", key="lemon_assign_start")
    with c3:
        assign_end = st.date_input("結束日期", key="lemon_assign_end")

    assign_types = st.multiselect(
        "要勾選的班別",
        [k for k in shift.TYPE_MAP.keys() if k != shift.CLEAR_TYPE],
        default=["全8"],
        key="lemon_assign_types",
    )

    lemon_names = [n.strip() for n in re.split(r"[,，]", lemon_names_raw) if n.strip()]
    if lemon_names:
        st.caption(f"將處理 {len(lemon_names)} 人：{'、'.join(lemon_names)}")
    if assign_types:
        st.caption(f"將勾選班別：{'、'.join(assign_types)}")

    execute_btn = st.button(
        "🚀 執行檸檬人勾班",
        use_container_width=True,
        type="primary",
        disabled=not (st.session_state.credentials_ready and bool(lemon_names) and bool(assign_types)),
    )

    with st.expander("執行 LOG", expanded=True):
        log_box_local = st.empty()
        log_box_local.text("\n".join(st.session_state.logs[-3000:]) if st.session_state.logs else "尚未執行")

    def lemon_assign_log(msg):
        st.session_state.logs.append(str(msg))
        try:
            log_box_local.text("\n".join(st.session_state.logs[-3000:]))
        except Exception:
            pass

    if execute_btn:
        try:
            st.session_state.logs = []
            st.session_state.lemon_assign_result = None
            lemon_assign_log(
                f"===== 開始檸檬人勾班：{len(lemon_names)} 人，"
                f"{assign_start.strftime('%Y-%m-%d')} ~ {assign_end.strftime('%Y-%m-%d')}，"
                f"班別：{'、'.join(assign_types)} ====="
            )
            with st.spinner("勾班中，請稍候…"):
                session = get_session(email, env_option, ui_logger=lemon_assign_log)
                result = shift.assign_person_shift_range(
                    session=session,
                    names=lemon_names,
                    date_start=assign_start.strftime("%Y-%m-%d"),
                    date_end=assign_end.strftime("%Y-%m-%d"),
                    type_values=assign_types,
                    ui_logger=lemon_assign_log,
                )
            st.session_state.lemon_assign_result = result
            lemon_assign_log("===== 檸檬人勾班完成 =====")
            st.rerun()
        except Exception as e:
            lemon_assign_log(f"❌ 勾班失敗：{e}")
            st.error(str(e))

    result = st.session_state.get("lemon_assign_result")
    if result is not None:
        st.markdown("---")
        step("4", "勾班結果")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("處理人數", result.get("processed_people", 0))
        c2.metric("處理月份數", result.get("processed_months", 0))
        c3.metric("儲存次數", result.get("saved", 0))
        c4.metric("錯誤數", len(result.get("errors", [])))

        if result.get("warnings"):
            with st.expander(f"⚠️ 衝突提醒（{len(result['warnings'])} 筆）", expanded=True):
                for w in result["warnings"]:
                    st.warning(w)

        if result.get("errors"):
            with st.expander(f"❌ 錯誤明細（{len(result['errors'])} 筆）", expanded=True):
                for err in result["errors"]:
                    st.error(err)
        else:
            st.success("✅ 檸檬人勾班完成")


def render_clear_shift_section(email, env_option):
    clear_mode = st.radio("", ["手動清空（某人 / 某段期間）", "自動清除候補檸檬人（從未配班清單）"], horizontal=True, label_visibility="collapsed", key="clear_shift_mode")

    if clear_mode == "手動清空（某人 / 某段期間）":
        step("3", "設定要清空的人員與期間")
        st.markdown('<div class="warn-strip"><b>注意</b><ul><li>會直接覆寫後台排班</li><li>沒有預覽機制</li><li>請確認姓名與日期區間</li><li>多人範例：<code>檸檬人1,檸檬人2,檸檬人3,檸檬人4,檸檬人5,檸檬人6,檸檬人7,檸檬人8,檸檬人9,檸檬人10,檸檬人11,檸檬人12,檸檬人13</code></li></ul></div>', unsafe_allow_html=True)
        c1, c2, c3 = st.columns([2, 1.3, 1.3])
        with c1: target_names_raw = st.text_input("人員姓名", placeholder="例如：蔡立娟 或 檸檬人3，多人用逗號分隔：檸檬人2,檸檬人4")
        with c2: range_start = st.date_input("開始日期", key="clear_range_start")
        with c3: range_end = st.date_input("結束日期", key="clear_range_end")
        target_names = [n.strip() for n in re.split(r"[,，]", target_names_raw) if n.strip()]
        if len(target_names) > 1: st.caption(f"將清空 {len(target_names)} 人：{'、'.join(target_names)}")
        execute_btn = st.button("🚀 執行清空", use_container_width=True, disabled=not (st.session_state.credentials_ready and bool(target_names)))

        with st.expander("執行 LOG", expanded=True):
            log_box_local = st.empty()
            log_box_local.text("\n".join(st.session_state.logs[-3000:]) if st.session_state.logs else "尚未執行")

        def clear_ui_log(msg):
            st.session_state.logs.append(str(msg))
            try: log_box_local.text("\n".join(st.session_state.logs[-3000:]))
            except: pass

        if st.session_state.clear_person_result is not None:
            results = st.session_state.clear_person_result
            if isinstance(results, dict): results = [results]
            st.markdown("---"); step("4", "執行結果")
            c1, c2, c3 = st.columns(3)
            c1.metric("清到資料的天數", sum(len(r.get("cleared_dates", [])) for r in results))
            c2.metric("原本就沒勾選的天數", sum(len(r.get("untouched_dates", [])) for r in results))
            c3.metric("移除的勾選筆數", sum(r.get("cleared_slot_count", 0) for r in results))
            for r in results:
                if r.get("errors"):
                    with st.expander(f"⚠️ 「{r.get('name', '')}」錯誤明細（{len(r['errors'])} 筆）", expanded=True):
                        for i, err in enumerate(r["errors"], 1): st.markdown(f"**{i}.** {err}")
                else:
                    st.success(f"✅ 已清空「{r.get('name', '')}」指定期間的排班（{len(r.get('cleared_dates', []))} 天有清到資料）。")

        if execute_btn:
            try:
                st.session_state.logs = []; st.session_state.clear_person_result = None
                clear_ui_log(f"===== 開始清空 {len(target_names)} 人的排班：{'、'.join(target_names)} =====")
                results = []
                with st.spinner("執行中，請稍候…"):
                    session = get_session(email, env_option, ui_logger=clear_ui_log)
                    for n in target_names:
                        clear_ui_log(f"\n----- 清空「{n}」-----")
                        results.append(shift.clear_person_shift_range(session=session, name=n, date_start=range_start.strftime("%Y-%m-%d"), date_end=range_end.strftime("%Y-%m-%d"), ui_logger=clear_ui_log))
                clear_ui_log("===== 執行完成 =====")
                st.session_state.clear_person_result = results
                st.rerun()
            except Exception as e:
                clear_ui_log(f"❌ 執行錯誤：{e}"); st.error(str(e))

    else:
        step("3", "設定要掃描並清空的日期區間")
        c1, c2 = st.columns(2)
        with c1: scan_start = st.date_input("開始日期", key="lemon_scan_start")
        with c2: scan_end = st.date_input("結束日期", key="lemon_scan_end")
        scan_btn = st.button("🔍 掃描並清空未配班清單", use_container_width=True, disabled=not st.session_state.credentials_ready)

        with st.expander("執行 LOG", expanded=True):
            log_box_local = st.empty()
            log_box_local.text("\n".join(st.session_state.logs[-3000:]) if st.session_state.logs else "尚未執行")

        def clear_ui_log(msg):
            st.session_state.logs.append(str(msg))
            try: log_box_local.text("\n".join(st.session_state.logs[-3000:]))
            except: pass

        if scan_btn:
            try:
                st.session_state.logs = []; st.session_state.lemon_scan_entries = None; st.session_state.lemon_clear_results = None
                clear_ui_log("===== 開始掃描未配班清單中的檸檬人 =====")
                with st.spinner("掃描並清空中，請稍候…"):
                    session = get_session(email, env_option, ui_logger=clear_ui_log)
                    entries = shift.find_unassigned_lemon_bookings_range(
                        session=session,
                        date_start=scan_start.strftime("%Y-%m-%d"),
                        date_end=scan_end.strftime("%Y-%m-%d"),
                        ui_logger=clear_ui_log,
                    )
                    st.session_state.lemon_scan_entries = entries
                    if entries:
                        clear_ui_log("===== 開始清空候補檸檬人佔用的時段 =====")
                        results = shift.clear_unassigned_lemon_bookings(session=session, entries=entries, ui_logger=clear_ui_log)
                        st.session_state.lemon_clear_results = results
                        clear_ui_log("===== 清空完成，請重新整理後台班表確認 =====")
                    else:
                        st.session_state.lemon_clear_results = []
                        clear_ui_log("===== 掃描完成，沒有需要清空的檸檬人 =====")
                st.rerun()
            except Exception as e:
                clear_ui_log(f"❌ 掃描/清空失敗：{e}"); st.error(str(e))

        entries = st.session_state.lemon_scan_entries
        if entries is not None:
            st.markdown("---"); step("4", "掃描結果")
            if not entries:
                st.info("這個日期區間的未配班清單裡沒有發現檸檬人。")
            else:
                by_name = {}
                for e in entries: by_name.setdefault(e["name"], []).append(e["date"])
                st.metric("發現的檸檬人數", len(by_name))
                for name, dates in by_name.items():
                    st.markdown(f'<div class="preview-card preview-ok"><div class="preview-title">{name}</div><div class="preview-sub"><b>佔用日期：</b>{"、".join(sorted(set(dates)))}</div></div>', unsafe_allow_html=True)
                st.markdown('<div class="warn-strip"><b>已自動執行清空</b><ul><li>請重新整理後台班表確認結果</li><li>若仍顯示，請確認是否是未配班訂單本身尚未重新整理</li></ul></div>', unsafe_allow_html=True)

        if st.session_state.lemon_clear_results is not None:
            st.markdown("---"); step("5", "清空結果")
            for r in st.session_state.lemon_clear_results:
                if r.get("errors"): st.error(f"❌ {r['name']}：{'；'.join(r['errors'])}")
                else: st.success(f"✅ {r['name']}：清空 {len(r.get('cleared_dates', []))} 天，移除 {r.get('cleared_slot_count', 0)} 筆勾選")


def render(backend_email, backend_password, env):
    email, env_option = backend_email, env
    step("3", "選擇排班子功能")
    shift_sub_section = st.radio(
        "排班子功能",
        ["📥 排班匯入", "🍋 檸檬人勾班", "🧹 清空排班"],
        horizontal=True,
        label_visibility="collapsed",
        key="shift_sub_section",
    )
    SHIFT_SUB_HELP = {
        "📥 排班匯入": '<div class="info-strip"><b>操作流程</b><ol><li>上傳 Excel / CSV</li><li>執行 Dry Run 預覽</li><li>確認合併結果</li><li>正式儲存</li></ol></div>',
        "🍋 檸檬人勾班": '<div class="info-strip"><b>操作流程</b><ol><li>輸入檸檬人名單</li><li>選擇起迄日期</li><li>選擇要勾的班別</li><li>批次勾班</li></ol></div>',
        "🧹 清空排班": '<div class="warn-strip"><b>危險操作</b><ul><li>會直接修改後台排班</li><li>沒有逐筆預覽機制</li><li>請確認人員與日期後再執行</li></ul></div>',
    }
    st.markdown(SHIFT_SUB_HELP.get(shift_sub_section, ""), unsafe_allow_html=True)
    st.markdown("---")

    if shift_sub_section == "📥 排班匯入":
        render_shift_import_section(email, env_option)
    elif shift_sub_section == "🍋 檸檬人勾班":
        render_lemon_assign_section(email, env_option)
    else:
        render_clear_shift_section(email, env_option)
