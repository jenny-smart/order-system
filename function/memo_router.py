# ============================================================
# 檔名：function/memo_router.py
# 功能：ordersapp.py 的 memo 類功能（客服作業／排班管理／財務對帳／付款比對／
#       服務異動／評估文字工具）統一入口。
# 更新時間：2026-10-17
#
# - 畫面與業務邏輯一律使用 memo_system/（與 orders-system 完全相同的單一實作，
#   tool-system 也直接 import 同一套），這裡不再自己實作任何 memo 功能。
# - order-system 獨有的「執行 Log」（shared/execution_log_service）以包裝
#   memo_system 模組函式的方式補上，不修改 memo_system 原始碼：
#   * 每次呼叫寫入一筆 Log；巢狀呼叫只記最外層，避免重複。
#   * memo_system/ui.py 每次畫面都會 importlib.reload(atm／payment_match)，
#     reload 會清掉模組上的包裝，因此另外註冊 meta path finder，在模組
#     （重新）載入後自動再包一次。
# ============================================================
# -*- coding: utf-8 -*-
from __future__ import annotations

import functools
import importlib.abc
import inspect
import sys
import threading
import traceback


def log_execution(**kwargs) -> None:
    """延遲 import，避免 shared.gsheet ↔ orders 循環匯入；本身絕不拋例外。"""
    try:
        from shared.execution_log_service import log_execution as _log
    except Exception as exc:  # pragma: no cover
        print(f"⚠ 執行 Log 模組載入失敗：{exc}", flush=True)
        return
    _log(**kwargs)

_STATE = threading.local()


# ------------------------------------------------------------
# 各函式的 Log 內容（args = 已 bind 的參數 dict；result = 回傳值）
# 回傳 None 代表這次呼叫不記 Log。
# ------------------------------------------------------------
def _errors(result) -> bool:
    return bool(isinstance(result, dict) and (result.get("errors") or result.get("failed")))


def _atm_paste(args, result):
    return dict(
        function_name="ATM 待付款清單貼上工作表", area=args.get("region", ""),
        status="失敗" if result.get("errors") else "成功",
        message=(f"貼上 {result.get('pasted', 0)} 筆，從第 {result.get('start_row')} 列開始；"
                 f"略過重複 {result.get('skipped_duplicates', 0)} 筆"),
    )


def _atm_match(args, result):
    return dict(
        function_name="ATM 配對銀行明細", area=args.get("region", ""),
        target=str(args.get("row_spec") or "").strip(),
        status="失敗" if _errors(result) else "成功",
        message=f"成功 {result.get('success', result.get('matched', 0))}，失敗 {result.get('failed', 0)}",
    )


def _atm_reconcile(args, result):
    return dict(
        function_name="ATM 更新系統對帳", area=args.get("region", ""),
        target=str(args.get("row_spec") or ""),
        status="失敗" if _errors(result) else "成功",
        message=(
            f"按已付款:{args.get('do_mark_paid')}／開發票:{args.get('do_issue_invoice')}／"
            f"發確認信:{args.get('do_send_mail')}；"
            f"成功 {result.get('success', 0)}，失敗 {result.get('failed', 0)}"
        ),
    )


def _pm_paste(args, result):
    return dict(
        function_name="付款比對：貼到待比對區", area=args.get("region", ""), status="成功",
        message=f"貼上 {result.get('pasted', 0)} 筆，從第 {result.get('start_row')} 列開始",
    )


def _pm_match(args, result):
    return dict(
        function_name="付款比對：比對銀行明細", area=args.get("region", ""), status="成功",
        message=f"配對 {result.get('matched_orders', 0)} 筆訂單；待人工確認 {result.get('review', 0)} 列",
    )


def _memo_result(name, run_type, target):
    def build(args, result):
        r = result if isinstance(result, dict) else {}
        return dict(
            function_name=name, run_type=run_type, target=target(args),
            status="失敗" if r.get("failed") else "成功",
            message=(f"處理{r.get('processed', 0)}筆，成功{r.get('success', 0)}筆，"
                     f"失敗{r.get('failed', 0)}筆，回寫{r.get('updated_orders', 0)}筆"),
        )
    return build


def _shift_import(args, result):
    if args.get("dry_run", True):
        return None
    return dict(
        function_name="排班匯入：正式儲存", status="失敗" if result.get("errors") else "成功",
        message=f"儲存 {result.get('saved', 0)} 個人/月份",
    )


def _date_range(args):
    return f"{args.get('date_start', '')}~{args.get('date_end', '')}"


def _shift_assign(args, result):
    return dict(
        function_name="檸檬人勾班", status="失敗" if result.get("errors") else "成功",
        date=_date_range(args), target="、".join(args.get("names") or []),
        message=f"班別：{'、'.join(args.get('type_values') or [])}；儲存 {result.get('saved', 0)} 次",
    )


def _shift_clear(args, result):
    return dict(
        function_name="手動清空排班", status="失敗" if result.get("errors") else "成功",
        date=_date_range(args), target=str(args.get("name") or ""),
        message=f"清到 {len(result.get('cleared_dates', []))} 天資料",
    )


def _shift_clear_lemon(args, result):
    if isinstance(result, dict):  # 例外時 _failure_entry 的探測呼叫
        return dict(function_name="自動清除候補檸檬人（未配班清單）", status="失敗")
    results = result or []
    if not results:
        return None
    return dict(
        function_name="自動清除候補檸檬人（未配班清單）",
        status="失敗" if any(r.get("errors") for r in results) else "成功",
        target="、".join(str(r.get("name", "")) for r in results),
        message=f"清空 {len(results)} 人",
    )


def _co_append(args, result):
    errors = result.get("errors") or []
    return dict(
        function_name="服務異動：寫入清潔異動工作表", area=args.get("region", ""),
        target="、".join(str(r.get("G", "")) for r in (args.get("rows") or [])),
        status="失敗" if errors else "成功",
        message="；".join(errors) if errors else
        f"寫入 {result.get('written', 0)} 筆，從第 {result.get('start_row')} 列開始",
    )


def _co_sync(args, result):
    return dict(
        function_name="服務異動：回填系統", area=args.get("region", ""),
        target="、".join(str(it.get("order_no", "")) for it in (args.get("selected_rows") or [])),
        status="失敗" if result.get("failed") else "成功",
        message=f"處理{result.get('processed', 0)}筆，成功{result.get('success', 0)}筆，失敗{result.get('failed', 0)}筆",
    )


# 失敗（拋例外）時沿用同一個 function_name／area／target。
LOG_SPECS = {
    "memo_system.atm": {
        "paste_atm_unpaid_list": _atm_paste,
        "auto_match_bank_rows": _atm_match,
        "process_atm_rows": _atm_reconcile,
    },
    "memo_system.payment_match": {
        "paste_orders": _pm_paste,
        "match_bank_rows": _pm_match,
    },
    "memo_system.memo": {
        "main": _memo_result("客服備註自動回填", "By Google Sheet",
                             lambda a: str(a.get("row_spec") or "")),
        "main_first_n_pending": _memo_result("客服備註自動回填", "By Google Sheet",
                                             lambda a: f"剩餘前 {a.get('limit')} 筆"),
        "main_by_selected_order_ids": _memo_result("客服備註自動回填", "By 電話／搜尋條件",
                                                   lambda a: "、".join(map(str, a.get("order_ids") or []))),
    },
    "memo_system.shift": {
        "process_import_file": _shift_import,
        "assign_person_shift_range": _shift_assign,
        "clear_person_shift_range": _shift_clear,
        "clear_unassigned_lemon_bookings": _shift_clear_lemon,
    },
    "memo_system.change_order": {
        "append_rows_to_sheet": _co_append,
        "sync_pending_rows": _co_sync,
    },
}

# 失敗時要帶的欄位（從成功 spec 的固定欄位推得，不依賴 result）
_FAILURE_FIELDS = ("function_name", "area", "target", "date", "run_type")


def _failure_entry(builder, args):
    """用空結果跑一次 builder 取得 function_name 等固定欄位。"""
    for empty in ({}, []):
        try:
            entry = builder(args, empty)
        except Exception:
            continue
        if entry:
            return {k: entry[k] for k in _FAILURE_FIELDS if k in entry}
    return None


def _wrap(func, builder):
    if getattr(func, "_order_system_exec_log", False):
        return func
    try:
        signature = inspect.signature(func)
    except (TypeError, ValueError):
        signature = None

    @functools.wraps(func)
    def wrapper(*a, **kw):
        if getattr(_STATE, "depth", 0):
            return func(*a, **kw)
        args = {}
        if signature is not None:
            try:
                bound = signature.bind(*a, **kw)
                bound.apply_defaults()
                args = dict(bound.arguments)
            except TypeError:
                args = {}
        _STATE.depth = getattr(_STATE, "depth", 0) + 1
        try:
            result = func(*a, **kw)
        except Exception as exc:
            entry = _failure_entry(builder, args)
            if entry:
                log_execution(status="失敗", message=str(exc),
                              traceback_text=traceback.format_exc(), **entry)
            raise
        finally:
            _STATE.depth -= 1
        try:
            entry = builder(args, result if result is not None else {})
        except Exception:
            entry = None
        if entry:
            log_execution(**entry)
        return result

    wrapper._order_system_exec_log = True
    return wrapper


def _patch_module(module) -> None:
    for name, builder in LOG_SPECS.get(getattr(module, "__name__", ""), {}).items():
        func = getattr(module, name, None)
        if callable(func):
            setattr(module, name, _wrap(func, builder))


class _PatchingLoader:
    def __init__(self, loader):
        self._loader = loader

    def __getattr__(self, item):
        return getattr(self._loader, item)

    def create_module(self, spec):
        create = getattr(self._loader, "create_module", None)
        return create(spec) if create else None

    def exec_module(self, module):
        self._loader.exec_module(module)
        _patch_module(module)


class _PatchingFinder(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path, target=None):
        if fullname not in LOG_SPECS:
            return None
        for finder in sys.meta_path:
            if finder is self or isinstance(finder, _PatchingFinder):
                continue
            find = getattr(finder, "find_spec", None)
            if find is None:
                continue
            spec = find(fullname, path, target)
            if spec is not None:
                if spec.loader is not None and not isinstance(spec.loader, _PatchingLoader):
                    spec.loader = _PatchingLoader(spec.loader)
                return spec
        return None


def install_execution_log() -> None:
    """把執行 Log 包裝套到 memo_system 模組上（可重複呼叫）。"""
    if not any(isinstance(f, _PatchingFinder) for f in sys.meta_path):
        sys.meta_path.insert(0, _PatchingFinder())
    for module_name in LOG_SPECS:
        module = sys.modules.get(module_name)
        if module is None:
            module = importlib.import_module(module_name)
        _patch_module(module)


SECTION_ALIASES = {
    "訂單客服備註": "📋 客服作業",
    "排班管理": "📅 排班管理",
    "評估文字工具": "📐 評估文字工具",
    "台北/台中區對帳": "💰 財務對帳",
    "桃園/新竹區對帳": "💳 付款後5碼及星和診所比對",
    "服務異動": "🔄 服務異動",
}


def render(section: str, email: str, password: str, env: str) -> None:
    """由 ordersapp 主選單呼叫；畫面與 orders-system 的 memo_system 完全一致。"""
    from memo_system.ui import render_memo_system

    install_execution_log()
    render_memo_system(
        forced_main_section=SECTION_ALIASES.get(section, section),
        shared_backend_email=email,
        shared_backend_password=password,
        shared_env=env,
    )
