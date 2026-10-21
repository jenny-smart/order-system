import orders  # noqa: F401  先載入 orders，避免 shared.gsheet 循環匯入
from unittest.mock import MagicMock, patch

from shared import unified_log


def test_row_layout_matches_other_systems():
    row = unified_log.build_row(function="建立訂單", area="台北", status="成功", message="LC001")
    assert len(row) == len(unified_log.HEADERS) == 11
    assert row[1:5] == ["訂單系統", "建立訂單", "", "台北"] and row[8] == "成功"
    assert unified_log.sheet_title(year=2027) == "order-system執行Log-2027"


def test_log_execution_also_writes_unified_log():
    from shared import execution_log_service as service

    with patch.object(unified_log, "write") as write, patch.object(service, "build_gsheet_client", side_effect=RuntimeError("x")):
        service.log_execution(function_name="取消訂單", status="failed", area="台中", message="m", traceback_text="tb")
    kwargs = write.call_args.kwargs
    assert kwargs["function"] == "取消訂單" and kwargs["status"] == "失敗" and kwargs["message"] == "m\ntb"


def test_write_never_raises():
    client = MagicMock()
    client.open_by_key.side_effect = RuntimeError("no access")
    unified_log.write(client=client, function="測試")


def test_web_click_logs_start_success_and_errors():
    import types

    st = types.SimpleNamespace(session_state={}, button=lambda label, **kw: label == "執行",
                               success=lambda body, **kw: body, error=lambda body, **kw: body)
    with patch.object(unified_log, "write") as write:
        unified_log.install_streamlit_hooks(st, "批次成單", "Jenny")
        unified_log.install_streamlit_hooks(st, "批次成單", "Jenny")
        st.error("沒按按鈕不記")
        st.button("執行")
        st.success("完成")
        st.success("不重複記")
    assert [c.kwargs["status"] for c in write.call_args_list] == ["執行", "成功"]
    assert write.call_args_list[0].kwargs["function"] == "批次成單／執行"
