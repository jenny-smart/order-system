"""Lemon 後台成立訂單的共用契約。

所有入口共用會員、地址、計算時數、查班表及送出後核對流程；這個模組只保留
兩種後台表單真正不同的地方：付款路由、日期欄位與發票欄位。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence


@dataclass(frozen=True)
class BookingRoute:
    payway: str
    payway_code: str
    path: str
    slot_field: str
    allows_multiple_slots: bool
    requires_invoice: bool


_ROUTES = {
    "信用卡": BookingRoute("信用卡", "1", "/booking/single", "datePeriod", False, True),
    "ATM": BookingRoute("ATM", "2", "/booking/single", "datePeriod", False, True),
    "儲值金": BookingRoute("儲值金", "4", "/booking/stored_value_routine", "date_list[]", True, False),
}

INVOICE_FIELDS = (
    "invoice_type",
    "carrier_type_id",
    "carrier_info",
    "company_title",
    "company_no",
    "donate_code",
)


def normalize_payway(value: object) -> str:
    text = str(value or "").strip()
    if text in _ROUTES:
        return text
    if "儲值金" in text:
        return "儲值金"
    if "信用卡" in text or "刷卡" in text:
        return "信用卡"
    if "ATM" in text.upper() or any(word in text for word in ("匯款", "轉帳", "藍新")):
        return "ATM"
    raise ValueError(f"不支援的付款方式：{text or '空白'}")


def route_for(value: object) -> BookingRoute:
    return _ROUTES[normalize_payway(value)]


def booking_url(base_url: str, value: object) -> str:
    return base_url.rstrip("/") + route_for(value).path


def build_submit_data(
    base_data: Mapping[str, object], token: str, payway: object, slots: Sequence[str] | str,
) -> dict:
    """依後台原生表單產生送單資料；一般客只允許一個時段。"""
    route = route_for(payway)
    selected = [slots] if isinstance(slots, str) else list(slots or [])
    selected = [str(slot).strip() for slot in selected if str(slot).strip()]
    if not selected:
        raise ValueError("送出訂單前尚未選擇班表時段")
    if not route.allows_multiple_slots and len(selected) != 1:
        raise ValueError(f"{route.payway}一次只能成立一個時段")

    data = dict(base_data)
    data["_token"] = token
    data["date_s"] = ""
    data["payway"] = route.payway_code
    data.pop("datePeriod", None)
    data.pop("date_list[]", None)

    if route.allows_multiple_slots:
        data[route.slot_field] = selected
        for field in INVOICE_FIELDS:
            data.pop(field, None)
    else:
        _validate_invoice(data)
        data[route.slot_field] = selected[0]
    return data


def _validate_invoice(data: Mapping[str, object]) -> None:
    invoice_type = str(data.get("invoice_type") or "").strip()
    if invoice_type not in {"1", "2", "3"}:
        raise ValueError("ATM／信用卡訂單必須選擇發票類別")
    if invoice_type == "1" and not str(data.get("donate_code") or "").strip():
        raise ValueError("捐贈發票必須填寫捐贈碼")
    if invoice_type == "2":
        carrier_type = str(data.get("carrier_type_id") or "").strip()
        if carrier_type not in {"1", "2", "3", "4"}:
            raise ValueError("個人二聯式發票必須選擇載具或紙本")
        if carrier_type != "4" and not str(data.get("carrier_info") or "").strip():
            raise ValueError("個人二聯式發票缺少載具資訊")
    if invoice_type == "3" and (
        not str(data.get("company_title") or "").strip()
        or not str(data.get("company_no") or "").strip()
    ):
        raise ValueError("三聯式發票必須填寫公司抬頭與統一編號")


def build_submit_pairs(
    base_data: Mapping[str, object], token: str, payway: object, slots: Iterable[str],
) -> list[tuple[str, object]]:
    """保留重複的 ``date_list[]`` 欄位，供 requests 模擬多選 checkbox。"""
    data = build_submit_data(base_data, token, payway, list(slots))
    selected = data.pop("date_list[]", None)
    pairs = list(data.items())
    if selected is not None:
        pairs.extend(("date_list[]", slot) for slot in selected)
    return pairs


def stored_value_failed_count(response) -> int:
    """儲值金回覆的 count 是「未成立筆數」；0 才代表沒有失敗。"""
    try:
        payload = response.json()
        return max(0, int(payload.get("count", 0))) if isinstance(payload, dict) else 0
    except (TypeError, ValueError, AttributeError):
        return 0
