# -*- coding: utf-8 -*-
"""清潔異動：自檸檬後台補齊缺資料＋ATM 待退款／待收款同步 ATM 工作表（服務異動「階段 C」）。

更新記錄：
2026-11-12
- 新增（Jenny）。規則與 tool-system【整合執行】清潔異動盤點（tools/finance_management/
  change_order_batch.py）相同，tool-system 另有每日 07:50 排程 change_order_fill。

規則：
- 只看登記日期（E 欄）2026/10/16 以後、G 欄有訂單、B 欄還沒完成的列。
- 除 ATM 待退款的 P／Q（銀行代碼／帳號）外，缺的資料自檸檬後台查詢補上「空白格」（不覆蓋人工資料）：
    後台訂單列表：D LINE 連結、F 客戶類別、H 客人姓名、I 服務時間、
                 X 原發票號碼＋Y 二聯／三聯（退款類、待處理發票）、
                 R 付款方式（待退款／VIP待退券，原訂單為 ATM 或信用卡時）、J 車馬費（車馬費發票且 J 空白）
    後台訂單編輯頁：待收款／待扣儲值金 N＝加收金額；待收款 M＝加收日期（後台已標記已收款才補）、R＝加收金流；
                 待退款／VIP待退券／待返儲值金 S＝退款金額
  後台沒有值就不補。
- B＝待退款／待收款、R＝ATM、金額有值、尚未退款（AC）／收款（M）→ 補進同地區 ATM 工作表待配對區
  （I 年月、J 訂單、K 姓名、L 金額：待退款負數＝S、待收款＝N；N/O＝清潔／退款或依內容異動費／工具組），
  ATM 工作表整欄 J 已有同訂單、同金額（不分正負）就不重複。
"""
from __future__ import annotations

import re
from datetime import date
from typing import Any, Callable, Optional

from bs4 import BeautifulSoup

from . import atm, change_order, memo

CUTOFF = date(2026, 10, 16)
REFUND_STATUSES = {"待退款", "VIP待退券"}
STORED_VALUE_STATUSES = {"待扣儲值金", "待返儲值金"}
FILL_STATUSES = REFUND_STATUSES | STORED_VALUE_STATUSES | {"待收款", "待處理發票"}
FILL_LETTERS = ("D", "F", "H", "I", "J", "M", "N", "R", "S", "X", "Y")
INVOICE_NO_RE = re.compile(r"[A-Z]{2}\d{8}")
ORDER_NO_RE = re.compile(r"LC\d{6,}", re.I)
COL = {name: index for index, name in enumerate(
    "A B C D E F G H I J K L M N O P Q R S T U V W X Y Z AA AB AC AD AE".split())}


def _cell(row: list, letter: str) -> str:
    index = COL[letter]
    return str(row[index] if index < len(row) else "").strip()


def _money(value) -> Optional[int]:
    cleaned = re.sub(r"[^0-9.\-]", "", str(value or ""))
    try:
        number = float(cleaned)
    except ValueError:
        return None
    return int(number) if number == int(number) else None


def _reg_date(text: str) -> Optional[date]:
    m = re.search(r"(\d{4})\D(\d{1,2})\D(\d{1,2})", str(text or ""))
    try:
        return date(*(int(p) for p in m.groups())) if m else None
    except ValueError:
        return None


def _sheet_date(value) -> str:
    m = re.search(r"(\d{4})\D(\d{1,2})\D(\d{1,2})", str(value or ""))
    return f"{m.group(1)}/{int(m.group(2)):02d}/{int(m.group(3)):02d}" if m else ""


def _in_scope(row: list) -> bool:
    reg = _reg_date(_cell(row, "E"))
    return bool(_cell(row, "G")) and reg is not None and reg >= CUTOFF


# ------------------------------------------------------------
# 自後台補齊
# ------------------------------------------------------------
def wanted_letters(row: list) -> set[str]:
    """這列有哪些空白欄位可以從後台補。"""
    status, detail = _cell(row, "B"), _cell(row, "C")
    if status not in FILL_STATUSES or not _in_scope(row):
        return set()
    letters = {"D", "F", "H", "I"}
    if status in REFUND_STATUSES or status == "待處理發票":
        letters |= {"X", "Y"}
    if status in REFUND_STATUSES:
        letters |= {"R", "S"}
    if status == "待返儲值金":
        letters.add("S")
    if status in ("待收款", "待扣儲值金"):
        letters.add("N")
    if status == "待收款":
        letters |= {"M", "R"}
    if status == "待處理發票" and detail == "車馬費發票":
        letters.add("J")
    return {letter for letter in letters if not _cell(row, letter)}


def _needs_purchase_state(row: list, letters: set[str]) -> bool:
    return bool(letters & {"M", "N", "S"} or ("R" in letters and _cell(row, "B") == "待收款"))


def backend_fill_values(row: list, order: Optional[dict], state: Optional[dict],
                        customer_type: str = "", service_text: str = "") -> dict[str, Any]:
    """依狀態決定要補的欄位 → {欄: 值}；只補空白格，後台沒有值就不補。"""
    wanted = wanted_letters(row)
    order, state = order or {}, state or {}
    status = _cell(row, "B")
    found: dict[str, Any] = {
        "D": str(order.get("line_url") or "").strip(), "F": customer_type,
        "H": str(order.get("customer_name") or "").strip(), "I": service_text,
    }
    invoice_no = str(order.get("invoice_no") or "").strip().upper()
    if INVOICE_NO_RE.fullmatch(invoice_no):
        found["X"] = invoice_no
        found["Y"] = "三聯" if order.get("carrier_type") == "三聯式" else "二聯"
    payway = str(order.get("payway") or "")
    if status in REFUND_STATUSES:
        if "ATM" in payway.upper():
            found["R"] = "ATM"
        elif payway == "信用卡":
            found["R"] = "信用卡"
    if status in REFUND_STATUSES or status == "待返儲值金":
        refund = _money(state.get("refundAmount"))
        if refund and refund > 0:
            found["S"] = refund
    if status in ("待收款", "待扣儲值金"):
        charge = _money(state.get("chargeAmount"))
        if charge and charge > 0:
            found["N"] = charge
    if status == "待收款":
        if str(state.get("isCharge") or "") == "2":  # 後台已標記已收款才補收款時間
            found["M"] = _sheet_date(state.get("chargeDate"))
        found["R"] = str(state.get("chargePayment") or "").strip()
    if status == "待處理發票":
        fare = _money(order.get("travel_fee"))
        if fare and fare > 0:
            found["J"] = f"車馬費 ${fare}"
    return {letter: found[letter] for letter in FILL_LETTERS
            if letter in wanted and found.get(letter) not in (None, "")}


def _purchase_state(session, order: dict) -> dict:
    purchase_id = str(order.get("purchase_id") or "")
    if not purchase_id:
        return {}
    resp = session.get(f"{change_order.BASE_URL}/purchase/edit/{purchase_id}", timeout=20)
    resp.raise_for_status()
    return change_order._extract_purchase_state(BeautifulSoup(resp.text, "html.parser"))


def fill_from_backend(region: str, ws, values: list[list], session, log: Callable[[str], None] = print,
                      dry_run: bool = False) -> list[dict]:
    """補齊空白格；回傳 [{"row", "order_no", "fills"}]。dry_run 只列出不寫入。"""
    planned, updates = [], []
    for row_no, row in enumerate(values[1:], start=2):
        wanted = wanted_letters(row)
        if not wanted:
            continue
        orders = [m.group(0).upper() for m in ORDER_NO_RE.finditer(_cell(row, "G"))]
        order_no = orders[0] if orders else _cell(row, "G")  # 合併開立以第一張訂單為準
        try:
            order = change_order.fetch_order_basic(order_no, session=session, by="orderNo")
            if not order:
                log(f"⚠️ 第 {row_no} 列 {order_no} 後台查無訂單，未補齊")
                continue
            state = _purchase_state(session, order) if _needs_purchase_state(row, wanted) else {}
            try:
                customer_type = change_order._customer_type_from_order(order) if "F" in wanted else ""
            except Exception:
                customer_type = ""
            service_text = (change_order._format_service_datetime(order.get("service_date"), order.get("period_text", ""))
                            if "I" in wanted else "")
            fills = backend_fill_values(row, order, state, customer_type, service_text)
        except Exception as exc:
            log(f"⚠️ 第 {row_no} 列 {order_no} 後台查詢失敗：{exc}")
            continue
        if not fills:
            continue
        planned.append({"row": row_no, "order_no": order_no, "fills": fills})
        for letter, value in fills.items():
            updates.append({"range": f"{letter}{row_no}", "values": [[value]]})
            while len(row) <= COL[letter]:
                row.append("")
            row[COL[letter]] = str(value)
    if updates and not dry_run:
        memo.with_retry(ws.batch_update, updates, value_input_option="USER_ENTERED")
    for item in planned:
        log(f"{'〔預覽〕會補' if dry_run else '✅ 已補'} 第 {item['row']} 列 {item['order_no']}："
            + "、".join(f"{k}={v}" for k, v in item["fills"].items()))
    log(f"【{region}】{'預覽：會' if dry_run else '已'}自檸檬後台補齊 {len(updates)} 格（{len(planned)} 列）")
    return planned


# ------------------------------------------------------------
# 同步 ATM 工作表
# ------------------------------------------------------------
def atm_candidates(values: list[list]) -> list[dict]:
    rows = []
    for row in values[1:]:
        status = _cell(row, "B")
        if status not in ("待退款", "待收款") or "ATM" not in _cell(row, "R").upper() or not _in_scope(row):
            continue
        is_refund = status == "待退款"
        if _cell(row, "AC" if is_refund else "M"):
            continue  # 已退款／已收款
        amount = _money(_cell(row, "S" if is_refund else "N"))
        if not amount:
            continue
        month = re.search(r"(\d{4})\D(\d{1,2})", _cell(row, "I"))
        rows.append({
            "year_month": f"{month.group(1)}.{int(month.group(2)):02d}" if month else "",
            "order_no": _cell(row, "G"), "name": _cell(row, "H"),
            "amount": -abs(amount) if is_refund else amount,
            "kind": "refund" if is_refund else "charge",
            "change_text": f"{_cell(row, 'C')} {_cell(row, 'J')}",
        })
    return rows


def new_atm_rows(candidates: list[dict], atm_values: list[list]) -> list[dict]:
    """去掉 ATM 工作表已有（同訂單、同金額，不分正負）的資料。"""
    seen = set()
    for row in atm_values:
        order_no = str(row[9] if len(row) > 9 else "").strip().upper()
        amount = _money(row[11] if len(row) > 11 else "")
        if order_no and amount is not None:
            seen.add((order_no, abs(amount)))
    result = []
    for row in candidates:
        key = (str(row["order_no"]).strip().upper(), abs(int(row["amount"])))
        if key not in seen:
            seen.add(key)
            result.append(row)
    return result


def service_fee(row: dict) -> tuple:
    return atm.REFUND_SERVICE_FEE if row["kind"] == "refund" else atm.change_order_service_fee(row["change_text"])


def sync_atm_sheet(region: str, values: list[list], log: Callable[[str], None] = print,
                   dry_run: bool = False) -> list[dict]:
    """ATM 待退款／待收款補進同地區 ATM 工作表；回傳新增（或預覽會新增）的資料。"""
    candidates = atm_candidates(values)
    if not candidates:
        log(f"【{region}】沒有要同步 ATM 工作表的列")
        return []
    ws = atm.get_atm_worksheet(region)
    atm_values = memo.with_retry(ws.get_all_values)
    rows = new_atm_rows(candidates, atm_values)
    if not rows:
        log(f"【{region}】ATM 待退款／待收款 {len(candidates)} 筆都已在 ATM 工作表")
        return []
    last_a_row = max((idx for idx, row in enumerate(atm_values, start=1) if row and str(row[0]).strip()), default=0)
    last_unpaid_row = max((idx for idx, row in enumerate(atm_values, start=1)
                           if any(str(v).strip() for v in row[8:12])), default=0)
    start_row = max(last_a_row + 5, last_unpaid_row + 1)
    end_row = start_row + len(rows) - 1
    for r in rows:
        log(f"{'〔預覽〕會新增' if dry_run else '✅ 新增'} ATM 工作表：{r['year_month']} {r['order_no']} {r['name']} "
            f"{r['amount']} {'／'.join(service_fee(r))}")
    if dry_run:
        log(f"【{region}】預覽：會新增 ATM 工作表 I{start_row}:O{end_row} 共 {len(rows)} 筆")
        return rows
    row_count = int(getattr(ws, "row_count", 0) or len(atm_values))
    if end_row > row_count:
        memo.with_retry(ws.add_rows, end_row - row_count)
    memo.with_retry(ws.update, values=[[r["year_month"], r["order_no"], r["name"], r["amount"]] for r in rows],
                    range_name=f"I{start_row}:L{end_row}", value_input_option="RAW")
    memo.with_retry(ws.update, values=[list(service_fee(r)) for r in rows],
                    range_name=f"N{start_row}:O{end_row}", value_input_option="RAW")
    try:
        atm.ensure_candidate_row_format(ws, list(range(start_row, end_row + 1)), log=log)
    except Exception as exc:
        log(f"⚠️ 補 G 欄公式／下拉選單失敗：{exc}")
    log(f"【{region}】已同步 ATM 工作表 I{start_row}:O{end_row} 共 {len(rows)} 筆")
    return rows


def run(region: str, session, log: Callable[[str], None] = print, dry_run: bool = False) -> dict:
    """服務異動階段 C：讀清潔異動 → 自後台補齊 → 同步 ATM 工作表。"""
    ws = change_order.get_worksheet(region)
    values = memo.with_retry(ws.get_all_values)
    filled = fill_from_backend(region, ws, values, session, log, dry_run=dry_run)
    if filled and not dry_run:
        values = memo.with_retry(ws.get_all_values)
    atm_rows = sync_atm_sheet(region, values, log, dry_run=dry_run)
    return {"filled": filled, "atm_rows": atm_rows}
