# -*- coding: utf-8 -*-
"""服務訂單系統內的檸檬保留單建單／取消 UI。"""

from datetime import date

import pandas as pd
import streamlit as st

from accounts import ACCOUNTS
from orders import get_region_by_address
from shared.execution_log_service import log_execution
from function import reserve_address
from function.reserve_cancel import PROXY_FILTER, SYSTEM_RESERVE_MEMO, cancel_reserve_orders, find_reserve_orders
from function.reserve_optimizer import (
    PERIOD_HOURS,
    RESERVE_PHONE_DEFAULT,
    ReserveRule,
    build_period_plan,
    create_reserve_orders_for_plan,
    login_reserve_member,
    member_addresses,
    run_reserve_round,
    start_reserve_job,
)


def _require_supported_env(env: str) -> bool:
    if str(env or "").strip().lower() not in {"prod", "dev"}:
        st.error("檸檬保留單只支援 prod 正式機或 dev 測試機。")
        return False
    return True


def _env_label(env: str) -> str:
    return "正式機 prod" if str(env).lower() == "prod" else "測試機 dev"


def _lookup(env: str, backend_email: str, backend_password: str, phone: str):
    key = f"reserve_lookup::{env}::{phone}"
    cached = st.session_state.get(key)
    if cached:
        return cached
    result = login_reserve_member(env, backend_email.strip(), backend_password.strip(), phone.strip())
    st.session_state[key] = result
    return result


def _common_member_header(env: str, backend_email: str, backend_password: str):
    phone = st.text_input("保留單會員手機", value=RESERVE_PHONE_DEFAULT, key="reserve_shared_phone")
    st.info(f"目前執行環境：{_env_label(env)}")
    if not backend_email.strip() or not backend_password.strip():
        st.warning("請先在頁面上方輸入後台帳號與密碼。")
        return phone, None
    try:
        lookup = _lookup(env, backend_email, backend_password, phone)
    except Exception as exc:
        st.error(f"讀取保留會員失敗：{exc}")
        return phone, None
    return phone, lookup


def _parse_plan_row_spec(value, max_row):
    text = str(value or "").strip().replace("，", ",")
    if not text:
        raise ValueError("請輸入分析列號。")
    selected = set()
    for part in text.split(","):
        part = part.strip()
        if "-" in part:
            bounds = [x.strip() for x in part.split("-", 1)]
            if len(bounds) != 2 or not all(x.isdigit() for x in bounds):
                raise ValueError(f"列號格式錯誤：{part}")
            start, end = map(int, bounds)
            if start < 1 or end < start:
                raise ValueError(f"列號範圍錯誤：{part}")
            selected.update(range(start, end + 1))
        elif part.isdigit() and int(part) > 0:
            selected.add(int(part))
        else:
            raise ValueError(f"列號格式錯誤：{part}")
    invalid = sorted(x for x in selected if x > max_row)
    if invalid:
        raise ValueError("超出分析結果列號：" + "、".join(map(str, invalid)))
    return selected


def render_reserve_create(backend_email: str, backend_password: str, env: str) -> None:
    st.markdown("### 🍋 檸檬保留單建單")
    st.caption("依期間統計未配班人力、設定 AM/PM 保留率，再選擇真正要成立訂單的日期範圍。")
    if not _require_supported_env(env):
        return
    phone, lookup = _common_member_header(env, backend_email, backend_password)
    if not lookup:
        return
    addresses = member_addresses(lookup)
    if not addresses:
        st.error(f"保留會員 {phone} 在{_env_label(env)}沒有可用地址。")
        return
    c1, c2 = st.columns(2)
    with c1:
        address = st.selectbox("保留單服務地址", addresses, key="reserve_create_address")
    with c2:
        payway = st.selectbox("保留單付款類型", ["儲值金", "信用卡", "ATM"], index=0, key="reserve_create_payway")
    region = get_region_by_address(address, ACCOUNTS) or "台北"
    st.caption(f"地址判斷區域：{region}｜客人備註會自動寫入「{SYSTEM_RESERVE_MEMO}」｜客服備註固定「大掃除檸檬保留單」")
    st.markdown("#### 1. 分析期間與保留率")
    d1, d2 = st.columns(2)
    with d1:
        start = st.date_input("分析開始日期", value=date(2026, 9, 21), key="reserve_plan_start")
    with d2:
        end = st.date_input("分析結束日期", value=date(2026, 9, 30), key="reserve_plan_end")
    periods = st.multiselect("要分析的時段", list(PERIOD_HOURS.keys()), default=["09:00-12:00", "14:00-17:00"], key="reserve_plan_periods")
    r1, r2 = st.columns(2)
    with r1:
        am_rate = st.slider("AM 保留率", 0, 100, 70, 5, key="reserve_am_rate") / 100.0
    with r2:
        pm_rate = st.slider("PM 保留率", 0, 100, 70, 5, key="reserve_pm_rate") / 100.0
    if st.button("統計班表並產生保留計畫", width="stretch", key="reserve_build_plan"):
        analysis_status = st.status("已收到分析指令，正在讀取班表…", expanded=True)
        try:
            analysis_status.write(f"分析期間：{start}～{end}；時段：{'、'.join(periods) or '未選擇'}")
            rules = [ReserveRule(start=start, end=end, am_rate=am_rate, pm_rate=pm_rate, label="保留區間")]
            plan = build_period_plan(lookup, start, end, rules, periods)
            st.session_state.reserve_menu_plan = [p.__dict__ for p in plan]
            st.session_state.pop("reserve_create_editor_rows", None)
            st.session_state.reserve_create_editor_revision = st.session_state.get("reserve_create_editor_revision", 0) + 1
            analysis_status.update(label=f"分析完成：共 {len(plan)} 個日期／時段", state="complete", expanded=False)
        except Exception as exc:
            message = str(exc).strip() or f"{type(exc).__name__}: {exc!r}"
            analysis_status.update(label="分析失敗", state="error", expanded=True)
            analysis_status.write(message)
            st.error(f"分析失敗：{message}")
    plan_rows = st.session_state.get("reserve_menu_plan") or []
    if not plan_rows:
        return
    editor_rows = st.session_state.get("reserve_create_editor_rows")
    if not editor_rows or len(editor_rows) != len(plan_rows):
        editor_rows = [{"執行": False, "列號": i, "日期": r["service_date"], "時段": r["period"], "未配班人數": r["unassigned_people"], "保留率": f"{int(r['reserve_rate'] * 100)}%", "建議保留張數": r["reserve_order_target"], "建立張數": r["reserve_order_target"], "預計留給市場": r["market_people_target"]} for i, r in enumerate(plan_rows, 1)]
        st.session_state.reserve_create_editor_rows = editor_rows
    st.markdown("#### 2. 選擇日期 × 時段與建立張數")
    st.caption("可逐列勾選、輸入分析列號，或使用全選／全不選；『建立張數』可低於建議值。")
    row_input = st.text_input("執行分析列號（選填）", placeholder="例如：1,2 或 1-5", key="reserve_create_row_spec")
    b1, b2, b3 = st.columns(3)
    action = None
    with b1:
        if st.button("套用列號", width="stretch", key="reserve_create_apply_rows"): action = "rows"
    with b2:
        if st.button("全選", width="stretch", key="reserve_create_select_all"): action = "all"
    with b3:
        if st.button("全不選", width="stretch", key="reserve_create_clear_all"): action = "none"
    if action:
        try:
            picked = _parse_plan_row_spec(row_input, len(editor_rows)) if action == "rows" else (set(range(1, len(editor_rows) + 1)) if action == "all" else set())
            for item in editor_rows:
                item["執行"] = item["列號"] in picked
            st.session_state.reserve_create_editor_rows = editor_rows
            st.session_state.reserve_create_editor_revision = st.session_state.get("reserve_create_editor_revision", 0) + 1
            st.rerun()
        except ValueError as exc:
            st.error(str(exc))
    revision = st.session_state.get("reserve_create_editor_revision", 0)
    edited = st.data_editor(pd.DataFrame(editor_rows), width="stretch", hide_index=True, disabled=["列號", "日期", "時段", "未配班人數", "保留率", "建議保留張數", "預計留給市場"], column_config={"執行": st.column_config.CheckboxColumn("執行"), "建立張數": st.column_config.NumberColumn("建立張數", min_value=0, step=1)}, key=f"reserve_create_editor_{revision}")
    st.session_state.reserve_create_editor_rows = edited.to_dict("records")
    selected_rows = [{"service_date": x["日期"], "period": x["時段"], "reserve_order_target": int(x["建立張數"])} for x in edited.to_dict("records") if x.get("執行") and int(x.get("建立張數") or 0) > 0]
    total_orders = sum(x["reserve_order_target"] for x in selected_rows)
    st.info(f"目前選擇 {len(selected_rows)} 個日期／時段，預計建立 {total_orders} 張保留單。")
    machine = _env_label(env)
    confirm = st.checkbox(f"我確認要在{machine}建立以上 {total_orders} 張檸檬保留單", key="reserve_create_confirm")
    job = st.session_state.get("reserve_create_job")
    running = bool(job) and not job.get("done")
    if st.button("確認建立檸檬保留單", type="primary", width="stretch", disabled=not confirm or total_orders <= 0 or running, key="reserve_create_execute"):
        try:
            job = start_reserve_job(selected_rows, payway)
            job["status"] = "running"
            st.session_state.reserve_create_job = job
            st.rerun()
        except Exception as exc:
            st.error(f"建立失敗：{str(exc).strip() or type(exc).__name__}")
    _render_reserve_create_job(env, lookup, region, address)


def _render_reserve_create_job(env, lookup, region, address) -> None:
    """一輪一輪執行保留單；每輪結束才重繪，此時可按暫停／繼續／結束。"""
    job = st.session_state.get("reserve_create_job")
    if not job:
        return
    status = job.get("status")
    if job.get("done"):
        status = "done"
    left = sum(job["remaining"].values())
    st.markdown("#### 3. 建立進度")
    st.progress(
        min(1.0, job.get("success_count", 0) / max(1, job["target_orders"])),
        text=(f"已完成 {job['round']} 輪；成功 {job.get('success_count', 0)} / {job['target_orders']} 張；"
              f"待建 {left} 張；已停止 {job.get('stopped_orders', 0)} 張（原因見下表 message 欄）"),
    )
    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("⏸️ 暫停生成", width="stretch", key="reserve_create_pause", disabled=status != "running"):
            job["status"] = status = "paused"
    with c2:
        if st.button("▶️ 繼續生成", width="stretch", key="reserve_create_resume", disabled=status != "paused"):
            job["status"] = status = "running"
    with c3:
        if st.button("⏹️ 結束並清除進度", width="stretch", key="reserve_create_stop"):
            st.session_state.pop("reserve_create_job", None)
            st.rerun()
    if status == "paused":
        st.warning(f"已暫停：第 {job['round']} 輪完成後停止，尚餘 {left} 張未建。按「繼續生成」會先重新分析剩餘人力再接著建。")
    elif status == "done":
        stopped = job.get("stopped_orders", 0)
        msg = f"建立完成：成功 {job.get('success_count', 0)} / {job['target_orders']} 張，共 {job['round']} 輪。"
        if stopped:
            st.warning(msg + f" 有 {stopped} 張因時段停止未建立，原因見下表 message 欄。")
        else:
            st.success(msg)
        if not job.get("logged"):
            job["logged"] = True
            log_execution(
                function_name="建立檸檬保留單", status="失敗" if stopped else "成功",
                area=region, target=address,
                message=f"成功 {job.get('success_count', 0)} / {job['target_orders']} 張，共 {job['round']} 輪"
                        + (f"，停止 {stopped} 張" if stopped else ""),
            )
    if job["results"]:
        df = pd.DataFrame(job["results"])
        front = [c for c in ("success", "round", "service_date", "period", "order_no", "staff", "message") if c in df.columns]
        st.dataframe(df[front + [c for c in df.columns if c not in front]], width="stretch", hide_index=True)
    if status == "running":
        st.info(f"正在執行第 {job['round'] + 1} 輪：重新分析各日期剩餘人力後送出…（按「暫停生成」會在本輪結束後暫停）")
        try:
            # 這一輪中間不呼叫畫面元件，避免按鈕觸發重繪時中斷在送單途中。
            run_reserve_round(job, env_name=env, lookup_result=lookup, region=region, address=address)
        except Exception as exc:
            job["status"] = "paused"
            job["results"].append({"success": False, "round": job["round"], "message": f"本輪執行失敗，已暫停：{exc}"})
        st.session_state.reserve_create_job = job
        st.rerun()


def render_reserve_cancel(backend_email: str, backend_password: str, env: str) -> None:
    st.markdown("### 🗑️ 檸檬保留單取消")
    st.caption("依期間、複選時段與客人備註篩選保留單，再勾選實際要取消的訂單。取消前會重新檢查最新客人備註。"
               "代客保留請選「代客保留（客人備註含關鍵字）」，輸入例如「代客保留：王小明」。")
    if not _require_supported_env(env):
        return
    phone, lookup = _common_member_header(env, backend_email, backend_password)
    if not lookup:
        return
    c1, c2 = st.columns(2)
    with c1:
        cancel_start = st.date_input("取消查詢開始日期", value=date(2026, 9, 21), key="reserve_cancel_start")
    with c2:
        cancel_end = st.date_input("取消查詢結束日期", value=date(2026, 9, 30), key="reserve_cancel_end")
    cancel_periods = st.multiselect("取消查詢時段（可複選；不選代表全部時段）", list(PERIOD_HOURS.keys()), default=[], key="reserve_cancel_periods")
    memo_filter = st.selectbox("客人備註篩選", ["僅系統保留單", "系統保留單或空白", "僅空白", PROXY_FILTER, "全部（僅供查看）"], index=0, key="reserve_cancel_memo_filter")
    memo_keyword = ""
    if memo_filter == PROXY_FILTER:
        memo_keyword = st.text_input("客人備註關鍵字（需含「代客保留」）", value="代客保留：", key="reserve_cancel_memo_keyword",
                                     help="例如「代客保留：王小明」只找王小明；只填「代客保留」會找出所有代客保留單。取消後客人備註前面加「取消」。")

    if st.button("查詢可取消保留單", width="stretch", key="reserve_cancel_search"):
        search_status = st.status("已收到查詢指令，正在搜尋保留單…", expanded=True)
        st.session_state.reserve_menu_cancel_rows = []
        st.session_state.reserve_menu_cancel_debug = {}
        st.session_state.reserve_cancel_selected_order_nos = []
        try:
            search_status.write("正在讀取訂單並逐筆確認最新客人備註…")
            with st.spinner("正在查詢保留單：先抓近期訂單，再逐筆確認客人備註..."):
                rows, debug = find_reserve_orders(
                    env, backend_email.strip(), backend_password.strip(), phone.strip(),
                    cancel_start.isoformat(), cancel_end.isoformat(),
                    memo_filter=memo_filter, periods=cancel_periods, return_debug=True,
                    memo_keyword=memo_keyword,
                )
            st.session_state.reserve_menu_cancel_rows = rows
            st.session_state.reserve_menu_cancel_filter = memo_filter
            st.session_state.reserve_menu_cancel_debug = debug
            if rows:
                search_status.update(label=f"查詢完成：找到 {len(rows)} 張", state="complete", expanded=False)
                st.success(f"查詢完成，共找到 {len(rows)} 張符合條件的保留單。")
            else:
                search_status.update(label="查詢完成：沒有符合條件的保留單", state="complete", expanded=False)
                st.warning("查詢完成，但此期間與篩選條件沒有符合的保留單。請查看下方查詢診斷。")
        except Exception as exc:
            message = str(exc).strip() or f"{type(exc).__name__}: {exc!r}"
            st.session_state.reserve_menu_cancel_rows = []
            st.session_state.reserve_menu_cancel_debug = {"error": message}
            search_status.update(label="查詢失敗", state="error", expanded=True)
            search_status.write(message)
            st.error(f"查詢失敗：{message}")

    debug = st.session_state.get("reserve_menu_cancel_debug") or {}
    if debug:
        with st.expander("查詢診斷", expanded=not bool(st.session_state.get("reserve_menu_cancel_rows"))):
            if debug.get("error"):
                st.error(debug["error"])
            else:
                st.write(
                    f"已掃描 {debug.get('pages_scanned', 0)} 頁 / {debug.get('cards_scanned', 0)} 張卡片；"
                    f"解析 {debug.get('orders_parsed', 0)} 張訂單；"
                    f"日期＋時段符合 {debug.get('date_period_candidates', 0)} 張；"
                    f"客人備註符合 {debug.get('memo_matches', 0)} 張；"
                    f"明細讀取失敗 {debug.get('detail_errors', 0)} 張。"
                )

    def _show_cancel_job():
        # 取消進度放在選取區塊下方；清單已全部取消變空時，也要顯示進度與結果。
        _render_reserve_cancel_job(env, backend_email, backend_password, _env_label(env))

    rows = st.session_state.get("reserve_menu_cancel_rows") or []
    if not rows:
        _show_cancel_job()
        return
    df = pd.DataFrame(rows)
    cols = [c for c in ["service_date", "period", "order_no", "customer_memo", "cancel_eligible"] if c in df.columns]
    preview = df[cols].copy()
    preview.rename(columns={"service_date": "日期", "period": "時段", "order_no": "訂單編號", "customer_memo": "客人備註", "cancel_eligible": "安全可取消"}, inplace=True)
    st.dataframe(preview, width="stretch", hide_index=True)

    safe_rows = [r for r in rows if r.get("cancel_eligible")]
    st.write(f"查到 **{len(rows)} 張**；目前符合安全取消條件 **{len(safe_rows)} 張**。")
    if st.session_state.get("reserve_menu_cancel_filter") == "全部（僅供查看）":
        st.warning("『全部（僅供查看）』不開放取消，請改用其他客人備註篩選後重新查詢。")
        _show_cancel_job()
        return
    if not safe_rows:
        _show_cancel_job()
        return

    st.markdown("#### 選擇要取消的保留單")
    order_map = {str(r.get("order_no") or ""): r for r in safe_rows if str(r.get("order_no") or "")}
    order_nos = list(order_map.keys())

    # 取消完成後要清空選取：必須在選單元件建立前處理，不能在建立後修改。
    if st.session_state.pop("reserve_cancel_clear_selection", False):
        st.session_state.reserve_cancel_selected_order_nos = []
        st.session_state.reserve_cancel_confirm = False
    # 清理舊查詢留下、已不存在於目前結果的選取值。
    current_selected = [
        x for x in st.session_state.get("reserve_cancel_selected_order_nos", [])
        if x in order_map
    ]
    st.session_state.reserve_cancel_selected_order_nos = current_selected

    b1, b2, _ = st.columns([1, 1, 3])
    with b1:
        if st.button("✅ 全選可取消單", width="stretch", key="reserve_cancel_select_all"):
            st.session_state.reserve_cancel_selected_order_nos = order_nos[:]
    with b2:
        if st.button("⬜ 全部取消選取", width="stretch", key="reserve_cancel_clear_all"):
            st.session_state.reserve_cancel_selected_order_nos = []

    def _format_cancel_option(order_no: str) -> str:
        row = order_map.get(order_no, {})
        memo = str(row.get("customer_memo") or "").strip() or "空白"
        return f"{row.get('service_date', '')}｜{row.get('period', '')}｜{order_no}｜客人備註：{memo}"

    selected_order_nos = st.multiselect(
        "勾選實際要取消的訂單（可複選）",
        options=order_nos,
        format_func=_format_cancel_option,
        key="reserve_cancel_selected_order_nos",
        placeholder="請選擇要取消的保留單",
    )
    selected_rows = [order_map[order_no] for order_no in selected_order_nos if order_no in order_map]
    st.info(f"目前已選 **{len(selected_rows)} 張**；可取消總數 {len(safe_rows)} 張。")

    if selected_rows:
        selected_df = pd.DataFrame(selected_rows)
        cols2 = [c for c in ["service_date", "period", "order_no", "customer_memo"] if c in selected_df.columns]
        selected_preview = selected_df[cols2].copy()
        selected_preview.rename(columns={"service_date": "日期", "period": "時段", "order_no": "訂單編號", "customer_memo": "客人備註"}, inplace=True)
        st.caption("本次將取消以下訂單：")
        st.dataframe(selected_preview, width="stretch", hide_index=True)

    machine = _env_label(env)
    selected_count = len(selected_rows)
    confirm = st.checkbox(
        f"我確認要在{machine}取消以上 {selected_count} 張檸檬保留單",
        key="reserve_cancel_confirm",
        disabled=selected_count <= 0,
    )
    cancel_job = st.session_state.get("reserve_cancel_job")
    cancel_running = bool(cancel_job) and cancel_job.get("status") != "done"
    if st.button(
        "確認取消檸檬保留單",
        type="primary",
        width="stretch",
        disabled=not confirm or selected_count <= 0 or cancel_running,
        key="reserve_cancel_execute",
    ):
        st.session_state.reserve_cancel_job = {"pending": selected_rows, "results": [], "total": selected_count, "status": "running"}
        st.session_state.reserve_menu_cancel_result = []
        st.session_state.reserve_cancel_clear_selection = True
        st.rerun()
    _show_cancel_job()


CANCEL_CHUNK_SIZE = 3


def _render_reserve_cancel_job(env, backend_email, backend_password, machine) -> None:
    """分批取消（每批 3 張）；每批結束才重繪，此時可按暫停／繼續／結束。"""
    job = st.session_state.get("reserve_cancel_job")
    if not job:
        return
    if not job["pending"]:
        job["status"] = "done"
    status = job["status"]
    done_count = len(job["results"])
    st.markdown("#### 取消進度")
    st.progress(min(1.0, done_count / max(1, job["total"])), text=f"已處理 {done_count} / {job['total']} 張")
    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("⏸️ 暫停取消", width="stretch", key="reserve_cancel_pause", disabled=status != "running"):
            job["status"] = status = "paused"
    with c2:
        if st.button("▶️ 繼續取消", width="stretch", key="reserve_cancel_resume", disabled=status != "paused"):
            job["status"] = status = "running"
    with c3:
        if st.button("⏹️ 結束並清除進度", width="stretch", key="reserve_cancel_stop"):
            st.session_state.pop("reserve_cancel_job", None)
            st.rerun()
    if status == "paused":
        st.warning(f"已暫停：尚有 {len(job['pending'])} 張未取消。")
    elif status == "done":
        ok = sum(1 for r in job["results"] if r.get("ok"))
        st.success(f"取消完成：成功 {ok} / {job['total']} 張；若備註已被改成人工客人保留內容或已取消過，該筆會自動跳過。")
        if not job.get("logged"):
            job["logged"] = True
            log_execution(
                function_name="取消檸檬保留單", status="失敗" if ok < job["total"] else "成功",
                target="、".join(str(r.get("order_no") or "") for r in job["results"] if r.get("ok")),
                message=f"成功 {ok} / {job['total']} 張",
            )
    if job["results"]:
        st.dataframe(pd.DataFrame(job["results"]), width="stretch", hide_index=True)
    if status == "done":
        _render_proxy_address_cleanup(job, env, backend_email, backend_password)
    if status == "running" and job["pending"]:
        chunk = job["pending"][:CANCEL_CHUNK_SIZE]
        st.info(f"正在{machine}取消 {len(chunk)} 張（按「暫停取消」會在這批結束後暫停）…")
        try:
            # 這一批中間不呼叫畫面元件，避免按鈕觸發重繪時中斷在取消途中。
            results = cancel_reserve_orders(env, backend_email.strip(), backend_password.strip(), chunk, len(chunk))
        except Exception as exc:
            results = [{**row, "ok": False, "message": f"取消失敗：{exc}"} for row in chunk]
        job["pending"] = job["pending"][len(chunk):]
        job["results"].extend(results)
        done = {str(r.get("order_no") or "") for r in results if r.get("ok")}
        st.session_state.reserve_menu_cancel_rows = [
            r for r in st.session_state.get("reserve_menu_cancel_rows") or []
            if str(r.get("order_no") or "") not in done
        ]
        st.session_state.reserve_menu_cancel_result = job["results"]
        st.session_state.reserve_cancel_job = job
        st.rerun()



def _render_proxy_address_cleanup(job, env, backend_email, backend_password) -> None:
    """檸檬保留單取消後，順便刪除檸檬保留帳號上固定地址以外的地址。"""
    if not any(r.get("ok") for r in job["results"]):
        return
    if "address_cleanup" not in job:
        with st.spinner("已取消，正在刪除檸檬保留帳號上固定地址以外的地址…"):
            try:
                job["address_cleanup"] = reserve_address.cleanup_after_cancel(
                    env, backend_email.strip(), backend_password.strip(),
                    [{**r, "phone": reserve_address.RESERVE_PHONE} for r in job["results"]])
            except Exception as exc:
                job["address_cleanup"] = [{"地址": "", "處理": "失敗", "結果": "失敗", "說明": f"同步刪除地址失敗：{exc}"}]
        st.session_state.reserve_cancel_job = job
    st.markdown("#### 同步刪除檸檬保留地址")
    if job["address_cleanup"]:
        st.dataframe(pd.DataFrame(job["address_cleanup"]), width="stretch", hide_index=True)
    else:
        st.caption("檸檬保留帳號上只有固定地址，不需刪除。")


def render_reserve_address_cleanup(backend_email: str, backend_password: str, env: str) -> None:
    st.markdown("### 🧹 檸檬保留刪除地址")
    keep = "、".join(reserve_address.KEEP_ADDRESSES)
    st.caption(f"代客保留會替檸檬保留帳號加入很多客人地址。這裡只保留：{keep}；"
               "其他地址直接刪除，不查訂單（刪會員地址不影響已成立的訂單）。")
    if not _require_supported_env(env):
        return
    phone, lookup = _common_member_header(env, backend_email, backend_password)
    if not lookup:
        return
    if st.button("讀取檸檬保留地址", width="stretch", key="reserve_address_load"):
        with st.spinner("正在讀取檸檬保留的地址…"):
            try:
                addresses = reserve_address.list_member_addresses(env, backend_email.strip(), backend_password.strip(), phone.strip())
                st.session_state.reserve_address_plan = reserve_address.plan_cleanup(addresses)
                st.session_state.pop("reserve_address_result", None)
                if not addresses:
                    st.warning("會員管理頁上讀不到可刪除的地址（沒有垃圾桶圖示的地址）。")
            except Exception as exc:
                st.session_state.reserve_address_plan = []
                st.error(f"讀取失敗：{exc}")
    result = st.session_state.get("reserve_address_result")
    if result:
        st.markdown("#### 刪除結果")
        st.dataframe(pd.DataFrame(result), width="stretch", hide_index=True)
    plan = st.session_state.get("reserve_address_plan") or []
    if not plan:
        return
    st.dataframe(pd.DataFrame(plan), width="stretch", hide_index=True)
    targets = [item["地址"] for item in plan if item["處理"] == reserve_address.DELETE]
    if not targets:
        st.info("沒有需要刪除的地址。")
        return
    confirm = st.checkbox(f"我確認要在{_env_label(env)}刪除以上 {len(targets)} 個地址", key="reserve_address_confirm")
    if st.button("確認刪除地址", type="primary", width="stretch", disabled=not confirm, key="reserve_address_delete"):
        with st.spinner(f"正在逐一刪除 {len(targets)} 個地址…"):
            try:
                st.session_state.reserve_address_result = reserve_address.delete_member_addresses(
                    env, backend_email.strip(), backend_password.strip(), targets, phone.strip())
            except Exception as exc:
                st.session_state.reserve_address_result = [{"地址": "", "結果": "失敗", "說明": str(exc)}]
        st.session_state.pop("reserve_address_plan", None)
        st.rerun()


# ordersapp.py 選單入口（order-system 沿用的名稱）
render_create = render_reserve_create
render_cancel = render_reserve_cancel
render_address_cleanup = render_reserve_address_cleanup
