"""獨立的已成單預約完成 LINE 通知頁面。"""
import streamlit as st

import orders
from accounts import ACCOUNTS
from shared import notification_service
from shared.line_notice_sheet import filter_groups_by_calendar, groups_from_dataframe, results_tsv


def render(backend_email, backend_password, env):
    st.markdown("### 已成單預約完成通知")
    st.info("只處理 Google 日曆有對應行程的已成單資料；日曆沒有即略過、不通知。通知日期與時段以後台訂單為準。")
    c1, c2 = st.columns(2)
    sheet_name = c1.text_input("工作表名稱", placeholder="例：台北202611", key="completed_notice_sheet")
    row_spec = c2.text_input("列號（選填）", placeholder="例：2,3,5-20；空白＝全部已成單列", key="completed_notice_rows")
    if st.button("檢查日曆並產生 LINE 通知", type="primary", use_container_width=True, key="completed_notice_run"):
        if not backend_email.strip() or not backend_password.strip():
            st.error("請先輸入後台帳號密碼")
        elif not sheet_name.strip():
            st.error("請輸入工作表名稱")
        else:
            try:
                _, df = orders.load_worksheet(sheet_name.strip())
                groups = groups_from_dataframe(df, row_spec)
                groups, skipped = filter_groups_by_calendar(
                    groups, orders, orders.build_gcal_service(), orders.GOOGLE_CALENDAR_MAP, ACCOUNTS,
                )
                results = []
                for group in groups:
                    label = "、".join(group["order_nos"])
                    try:
                        result, text = notification_service.build_combined_line_message_from_order_nos(
                            env_name=env, backend_email=backend_email.strip(),
                            backend_password=backend_password.strip(), order_nos=group["order_nos"],
                        )
                        results.append({"order_no": label, "group": group, "result": result, "text": text, "error": None})
                    except Exception as exc:
                        results.append({"order_no": label, "group": group, "result": None, "text": "", "error": str(exc)})
                st.session_state.completed_notice_results = results
                st.session_state.completed_notice_skipped = skipped
            except Exception as exc:
                st.error(f"產生失敗：{exc}")

    skipped = st.session_state.get("completed_notice_skipped", [])
    results = st.session_state.get("completed_notice_results", [])
    if skipped:
        st.info(f"日曆沒有對應行程，已略過 {len(skipped)} 筆，不產生通知。")
    valid = [item for item in results if not item.get("error")]
    if valid:
        st.caption("以下整段可按右上角複製，直接貼到 Google Sheet。")
        st.code(results_tsv(valid), language=None)
    for index, item in enumerate(results):
        if item.get("error"):
            st.error(f"訂單 {item['order_no']} 產生失敗：{item['error']}")
            continue
        st.text_area(
            f"{item['group'].get('name') or '客戶'}｜{item['order_no']}", item["text"],
            height=360, key=f"completed_notice_text_{index}",
        )
