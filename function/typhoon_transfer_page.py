# -*- coding: utf-8 -*-
"""服務訂單系統內的「颱風假訂單移轉」UI。"""

import pandas as pd
import streamlit as st

from function import typhoon_transfer as tt


def _rows_to_frame(rows):
    notes = tt.attention_notes(rows)
    return pd.DataFrame([
        {
            "移轉": True,
            "順序": idx,
            "注意": ("⚠️ " + notes[row["order_no"]]) if row["order_no"] in notes else "",
            "日期": row["service_date"],
            "時段": row["period"],
            "訂單編號": row["order_no"],
            "姓名": row["name"],
            "LINE": row.get("line_url", ""),
            "電話": row["phone"],
            "人數": row["person"],
            "專員": row["staff"],
            "付款狀態": row["payment_status"],
        }
        for idx, row in enumerate(rows, 1)
    ])


def render(backend_email, backend_password, env, copy_button=None):
    tab_transfer, tab_track = st.tabs(["🌀 移轉", "🔎 追蹤／↩️ 返回原班表"])
    with tab_transfer:
        _render_transfer(backend_email, backend_password, env, copy_button)
    with tab_track:
        _render_tracking(backend_email, backend_password, env, copy_button)


def _copy(copy_button, label, text, key):
    if copy_button:
        copy_button(label, text, key)
    else:
        st.caption(label)
        st.code(text, language=None)


def _render_tracking(backend_email, backend_password, env, copy_button=None):
    st.caption(
        "後台沒有訂單修改時間，這裡改查每筆訂單「目前」的服務日期／時段，"
        "與表單上的新日期／新時段比對，找出移轉後又被改過的訂單。"
    )
    _render_sheet_sync(backend_email, backend_password, env)
    with st.expander("改用貼上內容比對（不寫回表單）", expanded=False):
        _render_paste_tracking(backend_email, backend_password, env, copy_button)
    st.divider()
    _render_restore(backend_email, backend_password, env, copy_button)


def _render_restore(backend_email, backend_password, env, copy_button=None):
    from function import typhoon_sheet_sync as tss

    st.markdown("**↩️ 返回原班表**（誤傳颱風假時使用）")
    st.caption(
        "依上方 Google 表單設定，讀每列的原日期／原時段／原專員，一筆一筆處理：用「修改日期」改回原日期與原時段後，"
        "馬上到「排班修改」選回原專員並確認專員姓名，才做下一筆。配不回原專員的位置會改配不影響其他訂單的人，"
        "避免一筆錯其他筆跟著錯；全部跑完後再補試還沒完成的訂單，仍無法完成的列出請手動處理。"
    )
    account = backend_email.strip()
    if not account:
        return
    settings = {key: st.session_state.get(f"tt_sheet_{key}", "") for key in tss.DEFAULT_SETTINGS}
    if st.button("🔎 檢查要返回的訂單（不修改）", use_container_width=True, key="tt_restore_plan"):
        if not backend_password.strip():
            st.error("請先在上方輸入後台帳號密碼")
            return
        bar = st.progress(0.0)

        def _progress(index, total, item):
            bar.progress((index - 1) / max(total, 1))

        try:
            st.session_state.tt_restore_rows = tss.plan_restore(
                env, account, backend_password.strip(), settings, progress=_progress,
            )
            st.session_state.pop("tt_restore_results", None)
        except Exception as exc:
            st.error(f"檢查失敗：{exc}")
            return
        bar.progress(1.0)

    rows = st.session_state.get("tt_restore_rows")
    if rows is None:
        return
    results = st.session_state.get("tt_restore_results")
    shown = results if results is not None else rows

    def _fmt(r):
        return {
            "列": r["row"], "訂單編號": r["order_no"], "姓名": r.get("name", ""),
            "原日期": r["orig_date"], "原時段": r["orig_period"], "原專員": "、".join(r["orig_staff"]),
            "目前日期": r["now_date"], "目前時段": r["now_period"], "目前專員": "、".join(r["now_staff"]),
            "核對": tss.check_mark(r), "狀態": r["status"],
        }

    pending = [r for r in rows if r["status"] in tss.RESTORE_PENDING]
    if results is None:
        (st.warning if pending else st.success)(
            f"共 {len(rows)} 筆：待返回 {sum(r['status'] == '待返回' for r in rows)} 筆、"
            f"待配回原專員 {sum(r['status'] == '待配回原專員' for r in rows)} 筆、"
            f"已在原班表 {sum(r['status'] == '已在原班表' for r in rows)} 筆"
        )
    else:
        done = sum(r["status"].startswith("已返回原班表") for r in results)
        (st.success if done == len(results) else st.warning)(f"返回完成：{done}／{len(results)} 筆已返回原班表，其餘請看狀態")
    st.dataframe(pd.DataFrame([_fmt(r) for r in shown]), hide_index=True, use_container_width=True)
    _copy(copy_button, "複製返回結果（含標題列，貼到 Google Sheets 會自動分欄）" if results is not None
          else "複製檢查結果（含標題列，貼到 Google Sheets 會自動分欄）",
          tss.restore_tsv(shown), "tt_copy_restore")

    if results is None and pending:
        confirm = st.checkbox(
            f"確認把 {len(pending)} 筆訂單改回原日期／原時段並配回原專員", key="tt_restore_confirm",
        )
        if st.button("↩️ 開始返回原班表", type="primary", use_container_width=True,
                     disabled=not confirm, key="tt_restore_run"):
            bar = st.progress(0.0)
            status = st.empty()

            def _progress_run(index, total, row):
                bar.progress((index - 1) / max(total, 1))
                status.write(f"返回第 {index}/{total} 筆：{row['order_no']} → {row['orig_date']} {row['orig_period']}")

            try:
                st.session_state.tt_restore_results = tss.execute_restore(
                    env, account, backend_password.strip(), rows, progress=_progress_run,
                )
            except Exception as exc:
                st.error(f"返回失敗：{exc}")
                return
            st.rerun()


_SHEET_FIELD_LABELS = {
    "order_col": "訂單編號欄", "orig_date_col": "原日期欄", "orig_period_col": "原時段欄", "orig_staff_col": "原專員欄",
    "new_date_col": "新日期欄", "new_period_col": "新時段欄",
    "change_date_col": "異動日期欄", "change_period_col": "異動時段欄", "start_row": "起始列",
}


def _render_sheet_sync(backend_email, backend_password, env):
    from function import typhoon_sheet_sync as tss

    account = backend_email.strip()
    if not account:
        st.info("請先在上方輸入後台帳號密碼，才能讀取暫存的表單設定。")
        return
    if st.session_state.get("tt_sheet_settings_account") != account:
        try:
            saved = tss.load_settings(account)
        except Exception as exc:
            saved = dict(tss.DEFAULT_SETTINGS)
            st.warning(f"讀取暫存設定失敗，先使用預設值：{exc}")
        for key, value in saved.items():
            st.session_state[f"tt_sheet_{key}"] = str(value)
        st.session_state.tt_sheet_settings_account = account

    st.markdown("**Google 表單設定**（會依後台帳號暫存，下次自動帶入）")
    try:
        import orders as _orders
        _sa_email = _orders.get_service_account_info().get("client_email", "")
    except Exception:
        _sa_email = ""
    if _sa_email:
        st.caption(f"表單需共用給 {_sa_email}（編輯者），程式才能讀取與寫入。")
    c1, c2 = st.columns([2, 1])
    with c1:
        st.text_input("Google 試算表 ID（或貼整個網址）", key="tt_sheet_spreadsheet_id")
    with c2:
        st.text_input("工作表名稱", key="tt_sheet_worksheet")
    # 第一列：訂單編號欄＋起始列；第二列：日期／時段欄（原、新、異動）
    layout = [
        ["order_col", "start_row"],
        ["orig_date_col", "orig_period_col", "orig_staff_col", "new_date_col", "new_period_col",
         "change_date_col", "change_period_col"],
    ]
    for row_keys in layout:
        for col, key in zip(st.columns(7), row_keys):
            with col:
                st.text_input(_SHEET_FIELD_LABELS[key], key=f"tt_sheet_{key}")
    st.caption("新日期／新時段只用來比對、不會修改；有異動的訂單把目前日期／時段填進異動欄，沒有異動的維持空白。")
    settings = {key: st.session_state.get(f"tt_sheet_{key}", "") for key in tss.DEFAULT_SETTINGS}

    b1, b2 = st.columns(2)
    with b1:
        if st.button("💾 暫存設定", use_container_width=True, key="tt_sheet_save"):
            try:
                tss.save_settings(account, settings)
                st.success("已暫存設定")
            except Exception as exc:
                st.error(f"暫存失敗：{exc}")
    with b2:
        compare = st.button("🔎 比對表單與後台目前日期", type="primary", use_container_width=True, key="tt_sheet_compare")

    if compare:
        if not backend_password.strip():
            st.error("請先在上方輸入後台帳號密碼")
            return
        bar = st.progress(0.0)
        status = st.empty()

        def _progress(index, total, item):
            bar.progress((index - 1) / max(total, 1))
            status.write(f"查詢第 {index}/{total} 筆：第 {item['row']} 列 {item['order_no']}")

        try:
            st.session_state.tt_sheet_rows = tss.compare_sheet_orders(
                env, account, backend_password.strip(), settings, progress=_progress,
            )
            st.session_state.tt_sheet_compared_settings = tss.validate_settings(settings)
            st.session_state.pop("tt_sheet_applied", None)
        except Exception as exc:
            st.error(f"比對失敗：{exc}")
            return
        bar.progress(1.0)
        status.empty()

    rows = st.session_state.get("tt_sheet_rows")
    if rows is None:
        return
    def _count(status):
        return sum(1 for r in rows if r["status"] == status)

    pending = [r for r in rows if r["status"] in tss.PENDING_STATUSES]
    failed = [r for r in rows if r["status"].startswith("查詢失敗")]
    summary = (
        f"共 {len(rows)} 筆：待填異動 {_count('待填異動')} 筆、待清除異動欄 {_count('待清除異動欄')} 筆、"
        f"已填異動 {_count('已填異動')} 筆、已清除 {_count('已清除異動欄')} 筆、未變動 {_count('未變動')} 筆、"
        f"查詢失敗 {len(failed)} 筆"
    )
    (st.warning if pending or failed else st.success)(summary)
    only_changed = st.checkbox("不顯示未變動", value=True, key="tt_sheet_only_changed")
    shown = [r for r in rows if r["status"] not in ("未變動", "已清除異動欄")] if only_changed else rows
    st.dataframe(pd.DataFrame([
        {
            "列": r["row"], "訂單編號": r["order_no"], "姓名": r["name"],
            "原日期": r["orig_date"], "原時段": r["orig_period"],
            "新日期": r["sheet_date"], "新時段": r["sheet_period"],
            "目前日期": r["now_date"], "目前時段": r["now_period"],
            "異動欄（表單）": f"{r.get('change_date', '')} {r.get('change_period', '')}".strip(),
            "付款狀態": r["payment_status"], "狀態": r["status"],
        }
        for r in shown
    ]), hide_index=True, use_container_width=True)

    compared = st.session_state.get("tt_sheet_compared_settings", {})
    if pending:
        target = f"{compared.get('worksheet', '')} 的 {compared.get('change_date_col', '')}／{compared.get('change_period_col', '')} 欄"
        if st.button(f"✍️ 更新 {len(pending)} 筆異動到 {target}", type="primary",
                     use_container_width=True, key="tt_sheet_apply"):
            try:
                applied = tss.apply_sheet_updates(compared, rows)
            except Exception as exc:
                st.error(f"寫入失敗：{exc}")
            else:
                result_by_row = {r["row"]: r for r in applied}
                st.session_state.tt_sheet_rows = [result_by_row.get(r["row"], r) for r in rows]
                st.session_state.tt_sheet_applied = applied
                st.rerun()
    applied = st.session_state.get("tt_sheet_applied")
    if applied is not None:
        filled = sum(1 for r in applied if r["status"] == "已填異動")
        cleared = sum(1 for r in applied if r["status"] == "已清除異動欄")
        written = next((r for r in applied if r.get("written_to")), None)
        where = ""
        if written:
            col_d, col_p = compared.get("change_date_col", ""), compared.get("change_period_col", "")
            where = f"（已讀回確認：{written['written_to']} 的 {col_d}／{col_p} 欄）"
        st.success(f"已填入 {filled} 筆異動、清除 {cleared} 筆{where}")
        if written and written.get("sheet_url"):
            st.link_button("開啟寫入的工作表", written["sheet_url"])
        for r in applied:
            if r["status"] not in ("已填異動", "已清除異動欄"):
                st.warning(f"第 {r['row']} 列 {r['order_no']}：{r['status']}")


def _render_paste_tracking(backend_email, backend_password, env, copy_button=None):
    text = st.text_area(
        "貼上表單內容（含標題列，整段複製貼上）或訂單編號（一行一筆）",
        height=220, key="tt_track_input",
        placeholder="訂單編號\t姓名\tLINE@連結\t電話\t客戶地址\t原日期\t原時段\t服務時數\t新日期\t新時段\t結果\t說明\n"
                    "LC00215208\t王璿瑋\t…\t2027-03-03\t08:30-12:30\t成功\t…",
    )
    items = tt.parse_tracking_input(text)
    if text.strip():
        with_expected = sum(1 for item in items if item.get("expected_date"))
        st.caption(f"讀到 {len(items)} 筆訂單，其中 {with_expected} 筆有表單新日期可比對")
        if items and with_expected < len(items):
            st.warning(
                f"有 {len(items) - with_expected} 筆讀不到新日期，只會查目前日期、不會比對。"
                "請連同標題列（含「訂單編號」「新日期」「新時段」）一起貼上，"
                "或每行只貼：訂單編號、姓名、新日期、新時段。"
            )
    if st.button("🔎 查詢目前日期", type="primary", use_container_width=True, key="tt_track_run", disabled=not items):
        if not backend_email.strip() or not backend_password.strip():
            st.error("請先在上方輸入後台帳號密碼")
            return
        bar = st.progress(0.0)
        status = st.empty()

        def _progress(index, total, item):
            bar.progress((index - 1) / total)
            status.write(f"查詢第 {index}/{total} 筆：{item['order_no']}")

        try:
            st.session_state.tt_track_rows = tt.track_orders(
                env, backend_email.strip(), backend_password.strip(), items, progress=_progress,
            )
        except Exception as exc:
            st.error(f"查詢失敗：{exc}")
            return
        bar.progress(1.0)
        status.empty()

    rows = st.session_state.get("tt_track_rows")
    if not rows:
        return
    changed = [r for r in rows if r["狀態"] == "已變動"]
    failed = [r for r in rows if str(r["狀態"]).startswith("查詢失敗")]
    summary = f"共 {len(rows)} 筆：已變動 {len(changed)} 筆、查詢失敗 {len(failed)} 筆"
    (st.warning if changed or failed else st.success)(summary)
    only_changed = st.checkbox("只顯示已變動／查詢失敗", value=bool(changed or failed), key="tt_track_only_changed")
    shown = changed + failed if only_changed else rows
    st.dataframe(pd.DataFrame(shown, columns=tt.TRACK_HEADERS), hide_index=True, use_container_width=True)
    _copy(copy_button, "複製追蹤結果（貼到 Google Sheets 會自動分欄）", tt.tracking_tsv(shown), "tt_copy_track")


def _render_transfer(backend_email, backend_password, env, copy_button=None):
    st.caption(
        "依颱風假的時段，逐筆用後台「修改日期」移到移轉區間：先選日期、時段維持原時段。"
        "名單為後台「服務日期＋已付款」搜尋結果由上而下的順序，依序排入，第一天排不下才換下一天。"
        "颱風假連放多天時輸入區間，例如 2026/10/22-2026/10/23。"
    )
    c1, c2 = st.columns(2)
    with c1:
        typhoon_text = st.text_input("颱風假日期（一天或區間）", value="", placeholder="2026/10/23 或 2026/10/22-2026/10/23",
                                     key="tt_typhoon_date")
    with c2:
        range_text = st.text_input("移轉日期區間", value="", placeholder="2027/03/01-2027/03/05", key="tt_range")
    day_type = st.selectbox("移轉日別", tt.DAY_TYPES, key="tt_day_type",
                            help="平日（週一～五，國定假日也算平日）與週末（週六、日）價格不同，預設只移到與颱風假相同日別的日期。")

    st.markdown("**檸檬人排班**（執行時先勾檸檬人排班，再做訂單移轉）")
    do_shift = st.checkbox("移轉前先勾檸檬人排班", value=True, key="tt_shift_enabled")
    if do_shift:
        shift_names_text = st.text_input("檸檬人名單（逗號分隔）", value=tt.DEFAULT_LEMON_NAMES, key="tt_shift_names")
        sc1, sc2 = st.columns(2)
        with sc1:
            from memo_system import shift as _shift
            shift_types = st.multiselect(
                "排班班別", [k for k in _shift.TYPE_MAP if k != _shift.CLEAR_TYPE],
                default=tt.DEFAULT_LEMON_SHIFT_TYPES, key="tt_shift_types",
            )
        with sc2:
            shift_day_mode = st.selectbox(
                "排班日期", tt.SHIFT_DAY_MODES, key="tt_shift_day_mode",
                help="預設和移轉候選日期相同（依上方移轉日別）；也可改成移轉區間內僅平日／僅週末／平日＋週末。",
            )
        st.caption("注意：排班日期內檸檬人原本勾選的全日／上午／下午／晚上班別，會先清掉再套用這次選的班別。")

    if st.button("🔍 查詢颱風假訂單", type="primary", use_container_width=True, key="tt_search"):
        if not backend_email.strip() or not backend_password.strip():
            st.error("請先在上方輸入後台帳號密碼")
            return
        try:
            typhoon_start, typhoon_end = tt.parse_date_range(typhoon_text, allow_single=True)
        except Exception:
            st.error("颱風假日期格式請輸入：2026/10/23 或 2026/10/22-2026/10/23")
            return
        try:
            with st.spinner("登入後台並查詢訂單…"):
                rows, debug = tt.find_typhoon_orders(
                    env, backend_email.strip(), backend_password.strip(), typhoon_start, typhoon_end,
                )
        except Exception as exc:
            st.error(f"查詢失敗：{exc}")
            return
        st.session_state.tt_rows = rows
        st.session_state.tt_debug = debug
        st.session_state.tt_loaded_range = (typhoon_start.strftime("%Y-%m-%d"), typhoon_end.strftime("%Y-%m-%d"))
        st.session_state.pop("tt_results", None)
        st.session_state.pop("tt_editor", None)

    rows = st.session_state.get("tt_rows")
    if rows is None:
        return
    debug = st.session_state.get("tt_debug", {})
    typhoon_start, typhoon_end = st.session_state.get("tt_loaded_range", ("", ""))
    typhoon_label = typhoon_start if typhoon_start == typhoon_end else f"{typhoon_start}～{typhoon_end}"
    st.caption(f"後台：{debug.get('base_url', '')}｜{typhoon_label} 共 {len(rows)} 筆已付款服務訂單")
    if debug.get("hit_page_limit"):
        st.warning("查詢已達頁數上限，名單可能不完整，請到後台確認。")
    if not rows:
        st.success("颱風假期間沒有已付款的服務訂單。")
        return

    st.markdown("**移轉名單**（依後台列表由上而下；可取消勾選，或改「順序」調整先後）")
    notes = tt.attention_notes(rows)
    if notes:
        st.warning(
            f"有 {len(notes)} 筆需要留意（同一客人多筆訂單、或專員含檸檬人），"
            "請確認是合併訂單還是獨立訂單，再決定是否移轉："
        )
        for row in rows:
            if row["order_no"] in notes:
                st.caption(f"⚠️ {row['order_no']} {row['name']}｜{row['service_date']} {row['period']}｜{notes[row['order_no']]}")
    edited = st.data_editor(
        _rows_to_frame(rows), hide_index=True, use_container_width=True, key="tt_editor",
        disabled=["注意", "日期", "時段", "訂單編號", "姓名", "LINE", "電話", "人數", "專員", "付款狀態"],
        column_config={
            "移轉": st.column_config.CheckboxColumn("移轉"),
            "順序": st.column_config.NumberColumn("順序", min_value=1, step=1),
            "LINE": st.column_config.LinkColumn("LINE", display_text="開啟聊天"),
        },
    )

    by_order = {row["order_no"]: row for row in rows}
    selected = edited[edited["移轉"]].copy()
    selected = selected.sort_values("順序", kind="stable")
    plan = [by_order[no] for no in selected["訂單編號"]]

    st.markdown("**先通知客人**（移轉前可先複製名單，用 LINE 或電話通知客人）")
    _copy(copy_button, f"複製 {len(plan)} 筆通知名單（訂單編號～原專員，含標題列）",
          tt.notice_tsv(plan), "tt_copy_notice")

    try:
        start, end = tt.parse_date_range(range_text)
        dates_by_day = tt.candidate_dates_by_day([row["service_date"] for row in rows], start, end, day_type)
    except Exception as exc:
        st.info(f"請輸入移轉日期區間：{exc}" if range_text.strip() else "請輸入移轉日期區間，例如 2027/03/01-2027/03/05")
        return
    if start.strftime("%Y-%m-%d") <= typhoon_end and typhoon_start <= end.strftime("%Y-%m-%d"):
        st.error("移轉區間不可和颱風假日期重疊")
        return
    for day, dates in dates_by_day.items():
        st.caption(f"{day} 的訂單候選日期（依序嘗試）：" + ("、".join(dates) or "無符合日別的日期"))
    all_dates = sorted({d for dates in dates_by_day.values() for d in dates})
    if not all_dates:
        st.error("移轉區間內沒有符合日別的日期")
        return

    shift_names, shift_day_list = [], []
    if do_shift:
        shift_names = tt.parse_lemon_names(shift_names_text)
        shift_day_list = tt.shift_dates(start, end, shift_day_mode, all_dates)
        st.caption(
            f"檸檬人排班：{len(shift_names)} 人 × {'＋'.join(shift_types) or '（未選班別）'}，"
            f"日期：{'、'.join(shift_day_list) or '無'}"
        )
        if not shift_names or not shift_types or not shift_day_list:
            st.error("檸檬人排班需要名單、班別與排班日期；不需要排班請取消勾選「移轉前先勾檸檬人排班」。")
            return

    confirm_text = f"確認要把 {len(plan)} 筆訂單的服務日期改到 {all_dates[0]}～{all_dates[-1]}（時段不變）"
    if do_shift:
        confirm_text = f"確認先替 {len(shift_names)} 位檸檬人勾班，再" + confirm_text[3:]
    confirm = st.checkbox(confirm_text, key="tt_confirm")
    if st.button("🌀 開始移轉", type="primary", use_container_width=True, disabled=not (confirm and plan), key="tt_run"):
        st.session_state.pop("tt_shift_result", None)
        st.session_state.pop("tt_results", None)
        if do_shift:
            shift_log = st.empty()
            shift_lines = []

            def _shift_logger(msg):
                shift_lines.append(str(msg))
                shift_log.text("\n".join(shift_lines[-12:]))

            try:
                with st.spinner("先勾檸檬人排班…"):
                    shift_result = tt.assign_lemon_shifts(
                        env, backend_email.strip(), backend_password.strip(),
                        shift_names, shift_types, shift_day_list, logger=_shift_logger,
                    )
            except Exception as exc:
                st.error(f"檸檬人排班失敗，未進行訂單移轉：{exc}")
                return
            shift_log.empty()
            st.session_state.tt_shift_result = shift_result
            if shift_result.get("errors"):
                st.error("檸檬人排班有錯誤，未進行訂單移轉；請確認後再執行（或取消勾選排班）。")
                return

        bar = st.progress(0.0)
        status = st.empty()

        def _progress(index, total, row):
            bar.progress((index - 1) / total)
            status.write(f"處理第 {index}/{total} 筆：{row['service_date']} {row['period']} {row['name']}（{row['order_no']}）")

        try:
            results = tt.transfer_typhoon_orders(
                env, backend_email.strip(), backend_password.strip(), plan, dates_by_day, progress=_progress,
            )
        except Exception as exc:
            st.error(f"移轉失敗：{exc}")
            return
        bar.progress(1.0)
        status.empty()
        st.session_state.tt_results = results

    shift_result = st.session_state.get("tt_shift_result")
    if shift_result:
        errors = shift_result.get("errors") or []
        (st.error if errors else st.success)(
            f"檸檬人排班：處理 {shift_result.get('processed_people', 0)} 人、"
            f"儲存 {shift_result.get('saved', 0)} 個人／月份、錯誤 {len(errors)} 筆"
        )
        for err in errors:
            st.error(err)
        warnings = shift_result.get("warnings") or []
        if warnings:
            with st.expander(f"排班提醒（{len(warnings)} 筆）", expanded=True):
                for w in warnings:
                    st.caption(w)

    results = st.session_state.get("tt_results")
    if results:
        ok = sum(1 for r in results if r.get("success"))
        (st.success if ok == len(results) else st.warning)(f"完成：成功 {ok} 筆，失敗 {len(results) - ok} 筆")
        copy_rows = tt.result_copy_rows(results)
        st.dataframe(pd.DataFrame([
            {
                "結果": "✅" if r.get("success") else "❌",
                **{k: v for k, v in c.items() if k not in ("結果", "說明")},
                "新專員": r.get("new_staff", ""),
                "說明": r.get("message", ""),
                "略過日期": "；".join(r.get("attempts") or []),
            }
            for r, c in zip(results, copy_rows)
        ]), hide_index=True, use_container_width=True,
            column_config={"LINE@連結": st.column_config.LinkColumn("LINE@連結", display_text="開啟聊天")})
        _copy(copy_button, "複製原日期時段／移轉後日期時段（貼到 Google Sheets 會自動分欄）",
              tt.results_tsv(results), "tt_copy_results")
