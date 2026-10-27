"""Streamlit 重新部署時 memo_router 會被當成新模組重新 import；舊版本留下的 import finder
不能和新版本互相呼叫（曾發生 RecursionError，所有備忘系統頁面無法開啟）。"""
import importlib
import sys


def _reimport_router():
    for name in list(sys.modules):
        if name.startswith("memo_system.") or name == "function.memo_router":
            sys.modules.pop(name)
    return importlib.import_module("function.memo_router")


def _finders():
    return [f for f in sys.meta_path if type(f).__name__ == "_PatchingFinder"]


def test_reimported_router_replaces_stale_finder_without_recursion():
    import orders  # noqa: F401  先載入 orders，避免 shared.gsheet 循環匯入

    saved = list(sys.meta_path)
    try:
        _reimport_router().install_execution_log()
        router = _reimport_router()
        router.install_execution_log()  # 舊版本 finder 還在 sys.meta_path：不能遞迴
        assert len(_finders()) == 1 and isinstance(_finders()[0], router._PatchingFinder)
        import memo_system.change_order as co
        assert getattr(co.append_rows_to_sheet, "_order_system_exec_log", False)
    finally:
        sys.meta_path[:] = saved
