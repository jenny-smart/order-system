"""獨立的已成單預約完成 LINE 通知頁面。"""
import streamlit as st

import orders
from accounts import ACCOUNTS
from shared import notification_service
from shared.line_notice_sheet import (
    filter_groups_by_calendar, groups_from_dataframe, results_tsv,
    write_results_to_source,
)


def render(backend_email, backend_password, env):
    st.markdown("### 已成單預約完成通知")
    st.info("只處理 Google 日曆有對應行程的已成單資料；通知會直接寫入原排程工作表每個地址群組的第一列。")
    c1, c2 = st.columns(2)
    sheet_name = c1.text_input("工作表名稱", placeholder="例：台北202611", key="completed_notice_sheet")
    row_spec = c2.text_input("列號（選填）", placeholder="例：2,3,5-20；空白＝全部已成單列", key="completed_notice_rows")
    if st.button("檢查日曆並產生 LINE 通知", type="primary", use_container_width=True, key="completed_notice_run"):
        if not backend_email.strip() or not backend_password.strip():
            st.error("請先輸入後台帳號密碼")
        elif not sheet_name.strip():
            st.error("請輸入工作表名稱")
        else:
            st.session_state.completed_notice_results = []
            st.session_state.completed_notice_skipped = []
            st.session_state.completed_notice_summary = {}
            st.session_state.completed_notice_writeback = {}
            status = st.status("✅ 已按到按鈕｜正在讀取工作表…", expanded=True)
            progress = st.progress(0, text="準備中")
            live = st.empty()
            try:
                worksheet, df = orders.load_worksheet(sheet_name.strip())
                groups = groups_from_dataframe(df, row_spec)
                source_groups = groups
                total = sum(len(group.get("entries") or []) for group in groups)
                status.write(f"工作表讀取完成：找到 {total} 筆已有訂單編號的資料。")
                live.markdown(f"**共 {total} 筆｜日曆已檢查 0 筆｜日曆確認 0 筆｜略過 0 筆**")

                def calendar_progress(checked, calendar_total, matched, skipped_count, entry):
                    ratio = checked / calendar_total if calendar_total else 1
                    progress.progress(min(ratio * 0.7, 0.7), text=f"日曆檢查 {checked}/{calendar_total}｜已確認 {matched}｜略過 {skipped_count}")
                    live.markdown(
                        f"**共 {calendar_total} 筆｜日曆已檢查 {checked} 筆｜"
                        f"日曆確認 {matched} 筆｜略過 {skipped_count} 筆**  \n"
                        f"目前：第 {entry.get('row', '')} 列／{entry.get('order_no', '')}"
                    )

                status.write("正在逐筆比對 Google 日曆…")
                groups, skipped = filter_groups_by_calendar(
                    groups, orders, orders.build_gcal_service(), orders.GOOGLE_CALENDAR_MAP, ACCOUNTS,
                    progress_callback=calendar_progress,
                )
                results = []
                confirmed_orders = sum(len(group["order_nos"]) for group in groups)
                status.write(f"日曆比對完成：確認 {confirmed_orders} 筆；開始向後台核對並產生通知。")
                backend_confirmed = 0
                backend_session = notification_service.prepare_notification_session(
                    env, backend_email.strip(), backend_password.strip()
                )
                for index, group in enumerate(groups, 1):
                    label = "、".join(group["order_nos"])
                    progress.progress(
                        0.7 + 0.3 * ((index - 1) / max(len(groups), 1)),
                        text=f"後台確認與通知產生 {index}/{len(groups)} 組｜{label}",
                    )
                    try:
                        result, text = notification_service.build_combined_line_message_from_order_nos(
                            env_name=env, backend_email=backend_email.strip(),
                            backend_password=backend_password.strip(), order_nos=group["order_nos"],
                            session=backend_session,
                        )
                        results.append({"order_no": label, "group": group, "result": result, "text": text, "error": None})
                        backend_confirmed += len(group["order_nos"])
                    except Exception as exc:
                        results.append({"order_no": label, "group": group, "result": None, "text": "", "error": str(exc)})
                st.session_state.completed_notice_results = results
                st.session_state.completed_notice_skipped = skipped
                status.write("正在把通知與異動檢查直接寫回原排程工作表…")
                written_rows, inserted_rows, reduction_count = write_results_to_source(
                    worksheet, source_groups, results, skipped
                )
                st.session_state.completed_notice_writeback = {
                    "sheet": sheet_name.strip(), "written": written_rows,
                    "inserted": inserted_rows, "reduced": reduction_count,
                }
                valid_count = sum(not item.get("error") for item in results)
                failed_count = len(results) - valid_count
                st.session_state.completed_notice_summary = {
                    "total": total, "checked": total, "calendar_confirmed": confirmed_orders,
                    "backend_confirmed": backend_confirmed, "skipped": len(skipped),
                    "notices": valid_count, "failed": failed_count,
                }
                progress.progress(1.0, text="執行完成")
                live.markdown(
                    f"**共 {total} 筆｜日曆已檢查 {total} 筆｜日曆確認 {confirmed_orders} 筆｜"
                    f"後台確認 {backend_confirmed} 筆｜略過 {len(skipped)} 筆｜通知 {valid_count} 組**"
                )
                status.update(label=f"✅ 執行完成｜產生 {valid_count} 組通知｜已直接寫回 {sheet_name.strip()}", state="complete", expanded=False)
            except Exception as exc:
                st.error(f"產生失敗：{exc}")
                status.update(label=f"❌ 執行失敗：{exc}", state="error", expanded=True)

    skipped = st.session_state.get("completed_notice_skipped", [])
    results = st.session_state.get("completed_notice_results", [])
    summary = st.session_state.get("completed_notice_summary") or {}
    writeback = st.session_state.get("completed_notice_writeback") or {}
    if summary:
        columns = st.columns(6)
        for column, label, key in zip(
            columns,
            ("已成單總筆數", "日曆已檢查", "日曆有行程", "後台已確認", "略過", "通知組數"),
            ("total", "checked", "calendar_confirmed", "backend_confirmed", "skipped", "notices"),
        ):
            column.metric(label, summary.get(key, 0))
    if writeback:
        st.success(
            f"已直接寫回原工作表「{writeback['sheet']}」：{writeback['written']} 列；"
            f"新增安排 {writeback['inserted']} 列；減少警示 {writeback['reduced']} 組。"
        )
    if skipped:
        st.info(f"日曆沒有對應行程，已略過 {len(skipped)} 筆，不產生通知。")
    valid = [item for item in results if not item.get("error")]
    if valid:
        st.caption("通知已直接寫入工作表；以下僅供預覽或備用複製。")
        st.code(results_tsv(valid), language=None)
    for index, item in enumerate(results):
        if item.get("error"):
            st.error(f"訂單 {item['order_no']} 產生失敗：{item['error']}")
            continue
        st.text_area(
            f"{item['group'].get('name') or '客戶'}｜{item['order_no']}", item["text"],
            height=360, key=f"completed_notice_text_{index}",
        )
