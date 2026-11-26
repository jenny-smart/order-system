# -*- coding: utf-8 -*-
"""
服務異動：待處理發票情境（鯨躍電子發票後台的處理方式）

規則（2026-11-25 Jenny 確認）
- 發票不直接作廢；金額、二聯三聯互轉、合併開立一律走「折讓＋重開」。
- 統編打錯只要改統編，不用開折讓（2026-11-25 Jenny 確認）。
- 鯨躍「變更發票資料」只能改買家名稱／地址／Email／電話／備註，統編鎖住不能改。
- 載具：會員載具（預設 Email）／手機條碼／自然人憑證／鯨躍發票卡／紙本；
  能否在鯨躍直接改還不確定，J 欄兩種做法都寫（2026-11-26）。
- 變更完成 6 小時後才能補通知：有統編（三聯）→ 買家發票補通知（B2B）；
  沒統編（二聯）→ 發票補通知。
- 重複付款只開過一張發票，只要退款、不用處理發票。
- 信用卡付款超過 3 個月無法刷退，只能 ATM 退回。

VIP 退券
- 客人主動退：購物金不返還。
- 若之前是「VIP 時數轉儲值金」：已使用的服務一律反推原價（非 VIP 價），
  可退＝實付儲值金 − 已使用服務原價合計（不足以 0 計）。
  非大掃除：每 2 人 2 小時平日 $2,310、週末 $2,710；大掃除期間依各年度一般客價格。
- 我方主動退：購物金是否按比例返還另外協商，金額人工輸入。
"""

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Optional

INVOICE_RENT_URL = "https://www.ei.com.tw/InvoiceRent"
NOTIFY_URL_B2B = f"{INVOICE_RENT_URL}/invoicesendb2b.jsp"   # 買家發票補通知（三聯）
NOTIFY_URL_B2C = f"{INVOICE_RENT_URL}/invoicesend.jsp"      # 發票補通知（二聯）
NOTIFY_DELAY = timedelta(hours=6)

STATUS_PENDING_INVOICE = "待處理發票"
STATUS_VIP_REFUND = "VIP待退券"

TYPE_INVOICE_INFO = "發票資料變更"
TYPE_CARRIER = "發票載具變更"
TYPE_REISSUE = "發票折讓重開"
TYPE_TAX_ID = "發票更正統編"
TYPE_TRIPLICATE = "二聯轉三聯"   # tool-system TRIPLICATE_DETAILS
TYPE_MERGE = "合併開立發票"
TYPE_VIP_REFUND = "VIP退券"

SCENARIO_INVOICE_INFO = "發票資料變更(地址/名稱/Email/電話)"
SCENARIO_CARRIER = "發票載具變更"
SCENARIO_REISSUE = "統編錯誤/二聯三聯互轉"
SCENARIO_MERGE = "合併開立發票"
SCENARIO_VIP_REFUND_CUSTOMER = "VIP退券(客人主動)"
SCENARIO_VIP_REFUND_COMPANY = "VIP退券(我方主動)"

INVOICE_SCENARIOS = [SCENARIO_INVOICE_INFO, SCENARIO_CARRIER, SCENARIO_REISSUE, SCENARIO_MERGE]
VIP_REFUND_SCENARIOS = [SCENARIO_VIP_REFUND_CUSTOMER, SCENARIO_VIP_REFUND_COMPANY]

INFO_FIELDS = ["買家名稱", "買家地址", "買家Email", "買家電話"]
MEMBER_CARRIER = "會員載具"
CARRIER_TYPES = [MEMBER_CARRIER, "手機條碼", "自然人憑證", "鯨躍發票卡", "紙本發票"]
REISSUE_KINDS = ["更正統編", "二聯轉三聯", "三聯轉二聯"]

_MOBILE_BARCODE_RE = re.compile(r"^/[0-9A-Z.+\-]{7}$")
_CITIZEN_CERT_RE = re.compile(r"^[A-Z]{2}[0-9]{14}$")
_TAX_ID_RE = re.compile(r"^\d{8}$")
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


# ------------------------------------------------------------
# 共用
# ------------------------------------------------------------
def is_triplicate(order: dict) -> bool:
    return (order or {}).get("carrier_type") == "三聯式"


def invoice_copy_label(order: dict) -> str:
    return "三聯" if is_triplicate(order) else "二聯"


def notify_target(has_tax_id: bool) -> tuple[str, str]:
    """有統編 → 買家發票補通知（B2B）；沒統編 → 發票補通知。"""
    if has_tax_id:
        return "買家發票補通知", NOTIFY_URL_B2B
    return "發票補通知", NOTIFY_URL_B2C


def notify_after(changed_at: datetime) -> datetime:
    """鯨躍變更完成時間 + 6 小時 = 最早可補通知時間。"""
    return changed_at + NOTIFY_DELAY


def notify_text(has_tax_id: bool) -> str:
    label, _ = notify_target(has_tax_id)
    return f"鯨躍變更完成 6 小時後至「{label}」補通知"


def validate_tax_id(value: str) -> str:
    """統編 8 碼數字；格式不對回傳錯誤訊息，正確回傳空字串。"""
    if not _TAX_ID_RE.fullmatch(str(value or "").strip()):
        return "統編須為 8 碼數字"
    return ""


def validate_carrier(carrier_type: str, code: str) -> str:
    code = str(code or "").strip()
    if carrier_type == MEMBER_CARRIER:
        return "" if _EMAIL_RE.fullmatch(code) else "會員載具請輸入 Email"
    if carrier_type == "手機條碼" and not _MOBILE_BARCODE_RE.fullmatch(code):
        return "手機條碼須為 8 碼：第 1 碼為 /，其餘為數字、大寫英文或 . - +"
    if carrier_type == "自然人憑證" and not _CITIZEN_CERT_RE.fullmatch(code):
        return "自然人憑證條碼須為 2 碼大寫英文＋14 碼數字"
    if carrier_type in ("手機條碼", "自然人憑證", "鯨躍發票卡") and not code:
        return "請輸入載具號碼"
    return ""


def _base_row(order: dict, service_text: str, today_text: str, customer_type: str) -> dict:
    return {
        "A": "清潔", "D": order.get("line_url", ""), "E": today_text,
        "F": customer_type, "G": order["order_no"], "H": order.get("customer_name", ""),
        "I": service_text, "X": order.get("invoice_no", ""), "Y": invoice_copy_label(order),
    }


# ------------------------------------------------------------
# 發票情境 → 清潔異動列（B 欄：待處理發票）
# ------------------------------------------------------------
def build_info_change_row(order, changes: dict, service_text: str,
                          today_text: str, customer_type: str) -> dict:
    """鯨躍「變更發票資料」直接改，不動金額。changes：{欄位: 新內容}"""
    changes = {k: str(v).strip() for k, v in (changes or {}).items() if str(v or "").strip()}
    if not changes:
        raise ValueError("請至少填一個要變更的發票資料")
    detail = "、".join(f"{k}改為「{v}」" for k, v in changes.items())
    row = _base_row(order, service_text, today_text, customer_type)
    row.update({
        "B": STATUS_PENDING_INVOICE, "C": TYPE_INVOICE_INFO,
        "J": f"鯨躍「變更發票資料」：{detail}；{notify_text(is_triplicate(order))}",
        "_calc_amount": 0, "_calc_note": "金額不變，直接改發票資料",
    })
    return row


def build_carrier_change_row(order, carrier_type: str, carrier_code: str,
                             service_text: str, today_text: str, customer_type: str) -> dict:
    error = validate_carrier(carrier_type, carrier_code)
    if error:
        raise ValueError(error)
    code = f" {carrier_code.strip()}" if carrier_code and carrier_type != "紙本發票" else ""
    # 2026-11-26 Jenny：還不確定鯨躍能否直接改載具 → 不指定做法，由處理的人決定
    row = _base_row(order, service_text, today_text, customer_type)
    row.update({
        "B": STATUS_PENDING_INVOICE, "C": TYPE_CARRIER,
        "J": (f"載具改為{carrier_type}{code}（鯨躍能直接改就用「載具變更／變更紙本發票」，"
              f"不能改則全額折讓重開）；{notify_text(is_triplicate(order))}"),
        "_calc_amount": 0, "_calc_note": "金額不變，只改載具",
    })
    return row


def build_reissue_row(order, kind: str, tax_id: str, company: str,
                      service_text: str, today_text: str, customer_type: str, service_note: str = "") -> dict:
    """
    更正統編：直接改統編，不開折讓（2026-11-25 Jenny）。
    二聯轉三聯：C 欄寫「二聯轉三聯」、K 欄寫「統編 公司名稱」→ tool-system 清潔異動整合執行自動處理
    （原發票全額折讓＋開新三聯，K 欄格式同 tools/invoice_center/triplicate.parse_requirements）。
    三聯轉二聯：tool-system 尚無自動處理，J 欄寫做法。
    """
    if kind not in REISSUE_KINDS:
        raise ValueError(f"不支援的重開類型：{kind}")
    new_has_tax_id = kind != "三聯轉二聯"
    buyer = ""
    if new_has_tax_id:
        error = validate_tax_id(tax_id)
        if error:
            raise ValueError(error)
        if not str(company or "").strip():
            raise ValueError("請輸入公司名稱（發票抬頭）")
        buyer = f"{tax_id.strip()} {company.strip()}"
    note = str(service_note or "").strip()
    row = _base_row(order, service_text, today_text, customer_type)
    if kind == "更正統編":
        row.update({
            "B": STATUS_PENDING_INVOICE, "C": TYPE_TAX_ID, "K": note,
            "J": f"更正統編：原發票{order.get('invoice_no') or ''}改為統編{buyer}；{notify_text(True)}",
            "_calc_amount": 0, "_calc_note": "金額不變，只改統編（不開折讓）",
        })
        return row
    amount = int(order.get("total") or 0)
    if kind == "二聯轉三聯":
        row.update({
            "B": STATUS_PENDING_INVOICE, "C": TYPE_TRIPLICATE,
            "K": "\n".join(x for x in (buyer, note) if x),
            "J": f"二聯轉三聯：原發票{order.get('invoice_no') or ''}全額折讓 ${amount:,}，重開三聯；新發票{notify_text(True)}",
            "_calc_amount": amount, "_calc_note": f"全額折讓 ${amount:,} ＋ 重開三聯 ${amount:,}（整合執行自動處理）",
        })
        return row
    row.update({
        "B": STATUS_PENDING_INVOICE, "C": TYPE_REISSUE, "K": note,
        "J": (f"三聯轉二聯：原發票{order.get('invoice_no') or ''}全額折讓 ${amount:,}，"
              f"重開二聯；新發票{notify_text(False)}"),
        "_calc_amount": amount, "_calc_note": f"全額折讓 ${amount:,} ＋ 重開 ${amount:,}（不作廢）",
    })
    return row


def build_merge_rows(orders: list, service_text: str, today_text: str, customer_type: str,
                     service_note: str = "") -> list:
    """
    合併開立：只寫一列（G＝第一張訂單，J 列出全部訂單），由 tool-system 清潔異動整合執行處理：
    每張原發票全額折讓，再以第一張訂單的發票資料合開一張（金額＝各訂單合計），回寫時每張訂單都寫發票號碼。
    """
    if len(orders) < 2:
        raise ValueError("合併開立請至少勾選 2 筆訂單")
    first = orders[0]
    order_nos = [o["order_no"] for o in orders]
    total = sum(int(o.get("total") or 0) for o in orders)
    row = _base_row(first, service_text, today_text, customer_type)
    row.update({
        "B": STATUS_PENDING_INVOICE, "C": TYPE_MERGE, "K": str(service_note or "").strip(),
        "J": (f"合併開立發票：{'、'.join(order_nos)}（原發票全額折讓，以 {first['order_no']} 的發票資料合開一張 "
              f"共 ${total:,}）；新發票{notify_text(is_triplicate(first))}"),
        "_calc_amount": total, "_calc_note": f"{len(orders)} 筆合計 ${total:,}，合開一張",
    })
    return [row]


# ------------------------------------------------------------
# 退款方式：信用卡超過 3 個月只能 ATM
# ------------------------------------------------------------
def _add_months(d: date, months: int) -> date:
    y, m = divmod(d.month - 1 + months, 12)
    y, m = d.year + y, m + 1
    for day in (d.day, 30, 29, 28):
        try:
            return date(y, m, day)
        except ValueError:
            continue
    raise ValueError("日期錯誤")


def refund_payway(original_payway: str, paid_on: Optional[date], today: date) -> str:
    payway = str(original_payway or "").strip()
    if "ATM" in payway.upper():
        return "ATM"
    if payway == "信用卡":
        if paid_on is None or today > _add_months(paid_on, 3):
            return "ATM"
        return "信用卡"
    return payway or "ATM"


# ------------------------------------------------------------
# VIP 退券：反推原價
# ------------------------------------------------------------
# 非大掃除原價：每 2 人 2 小時平日 $2,310、週末 $2,710 → 每人時
NORMAL_RATE_WEEKDAY = 577.5
NORMAL_RATE_WEEKEND = 677.5


@dataclass(frozen=True)
class DeepCleanPeriod:
    start: date
    end: date
    weekday: float   # 一般客每人時（含稅）
    weekend: float
    derived: bool = False   # True＝比較表沒有總額，用「平日原價＋年節加價」推算


# 依「平日與大掃除服務金額比較表」一般客欄（2人4小時 ÷ 8 人時）。
# 2020～2022 表上只有年節加價：平日原價 $577.5／人時＋加價（2人4小時加價 ÷ 8），
# 2023 起的總額也都等於「平日原價＋加價」，大掃除期間週末不另加週末價。
DEEP_CLEAN_PERIODS = [
    DeepCleanPeriod(date(2020, 12, 21), date(2021, 2, 10), 662.5, 662.5, derived=True),
    DeepCleanPeriod(date(2021, 12, 8), date(2022, 1, 31), 682.5, 682.5, derived=True),
    DeepCleanPeriod(date(2022, 12, 1), date(2023, 1, 20), 702.5, 702.5, derived=True),
    DeepCleanPeriod(date(2023, 12, 20), date(2024, 1, 24), 717.5, 727.5),
    DeepCleanPeriod(date(2024, 1, 25), date(2024, 2, 8), 727.5, 727.5),
    DeepCleanPeriod(date(2024, 12, 9), date(2025, 1, 12), 727.5, 740.0),
    # 比較表寫「2025/01/13-2024/01/27」，迄日應為 2025/01/27
    DeepCleanPeriod(date(2025, 1, 13), date(2025, 1, 27), 765.0, 765.0),
    DeepCleanPeriod(date(2025, 12, 25), date(2026, 1, 31), 737.5, 765.0),
    DeepCleanPeriod(date(2026, 2, 1), date(2026, 2, 15), 775.0, 800.0),
    DeepCleanPeriod(date(2026, 12, 15), date(2027, 1, 21), 750.0, 775.0),
    DeepCleanPeriod(date(2027, 1, 22), date(2027, 2, 4), 775.0, 800.0),
]


def original_rate(service_date: date) -> dict:
    """服務日期的一般客原價（每人時）。週六日為週末。"""
    weekend = service_date.weekday() >= 5
    day_label = "週末" if weekend else "平日"
    for p in DEEP_CLEAN_PERIODS:
        if p.start <= service_date <= p.end:
            return {
                "rate": p.weekend if weekend else p.weekday,
                "label": f"大掃除 {p.start:%Y/%m/%d}～{p.end:%Y/%m/%d} {day_label}",
                "derived": p.derived,
            }
    return {"rate": NORMAL_RATE_WEEKEND if weekend else NORMAL_RATE_WEEKDAY,
            "label": f"非大掃除 {day_label}", "derived": False}


def original_price(service_date: date, persons: float, hours: float) -> dict:
    info = original_rate(service_date)
    amount = int(round(info["rate"] * float(persons or 0) * float(hours or 0)))
    return {**info, "amount": amount, "service_date": service_date,
            "persons": persons, "hours": hours}


def calc_vip_refund(initiated_by: str, paid_amount: int = 0, used_services: list = None,
                    converted_from_hours: bool = False, stored_balance: int = 0,
                    shopping_credit_refund: int = 0) -> dict:
    """
    initiated_by：'customer'（客人主動）或 'company'（我方主動）
    converted_from_hours=True：可退＝實付儲值金 − 已使用服務原價合計
    converted_from_hours=False：可退＝目前儲值金餘額（不含購物金）
    shopping_credit_refund：我方主動時協商返還的購物金（客人主動一律 0）
    """
    if initiated_by not in ("customer", "company"):
        raise ValueError("initiated_by 須為 customer 或 company")
    lines = []
    if converted_from_hours:
        priced = [original_price(s["service_date"], s["persons"], s["hours"]) for s in (used_services or [])]
        used_total = sum(p["amount"] for p in priced)
        stored_refund = max(int(paid_amount or 0) - used_total, 0)
        for p in priced:
            lines.append(f"{p['service_date']:%Y/%m/%d} {p['label']} {p['persons']:g}人{p['hours']:g}小時 "
                         f"× ${p['rate']:g}/人時 = ${p['amount']:,}")
        note = f"實付儲值金 ${int(paid_amount or 0):,} − 已使用服務原價 ${used_total:,} = ${stored_refund:,}"
    else:
        priced, used_total = [], 0
        stored_refund = max(int(stored_balance or 0), 0)
        note = f"儲值金餘額 ${stored_refund:,}（不含購物金）"
    credit = int(shopping_credit_refund or 0) if initiated_by == "company" else 0
    if credit:
        note += f"；協商返還購物金 ${credit:,}"
    elif initiated_by == "customer":
        note += "；客人主動退，購物金不返還"
    return {
        "stored_refund": stored_refund,          # 原儲值發票要折讓的金額
        "shopping_credit_refund": credit,        # 購物金沒開過發票，不折讓
        "total_refund": stored_refund + credit,  # 實際退款
        "used_total": used_total,
        "has_derived_price": any(p["derived"] for p in priced),
        "lines": lines,
        "note": note,
    }


def build_vip_refund_row(order, refund: dict, initiated_by: str, original_invoice: str,
                         payway: str, has_tax_id: bool,
                         service_text: str, today_text: str, service_note: str = "") -> dict:
    who = "客人主動" if initiated_by == "customer" else "我方主動"
    invoice = str(original_invoice or "").strip().upper()
    allowance = (f"原儲值發票{invoice}折讓 ${refund['stored_refund']:,}；{notify_text(has_tax_id)}"
                 if refund["stored_refund"] else "不需折讓")
    j = f"VIP退券（{who}）：{refund['note']}，退款 ${refund['total_refund']:,}（{payway}）；{allowance}"
    if service_note:
        j = f"{j}；{service_note}"
    row = _base_row(order, service_text, today_text, "VIP")
    row.update({
        "B": STATUS_VIP_REFUND, "C": TYPE_VIP_REFUND, "J": j, "K": service_note or "",
        "R": payway, "S": refund["total_refund"], "X": invoice,
        "Y": "三聯" if has_tax_id else "二聯",
        "_calc_amount": refund["total_refund"], "_refund_amount": refund["total_refund"],
        "_calc_note": "；".join(refund["lines"] + [refund["note"]]) + (
            "（含 2020～2022 大掃除推算價，請確認）" if refund["has_derived_price"] else ""),
    })
    return row
