# -*- coding: utf-8 -*-
"""大掃除保留單規劃與批次建單。"""

from __future__ import annotations

import math
import re
import time
import uuid
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from bs4 import BeautifulSoup

from function import cancel_order as co
import quick_order as qo
from shared.reserve_sheet_log import append_log_rows

RESERVE_PHONE_DEFAULT = "0939592628"
SYSTEM_RESERVE_MEMO = "系統保留單"
CUSTOMER_SERVICE_NOTE = "大掃除檸檬保留單"

PERIOD_HOURS = {
    "08:30-12:30": 4,
    "09:00-11:00": 2,
    "09:00-12:00": 3,
    "14:00-16:00": 2,
    "14:00-17:00": 3,
    "14:00-18:00": 4,
    "09:00-16:00": 6,
    "09:00-18:00": 8,
}
AM_PERIODS = {"08:30-12:30", "09:00-11:00", "09:00-12:00", "09:00-16:00", "09:00-18:00"}
PM_PERIODS = {"14:00-16:00", "14:00-17:00", "14:00-18:00"}


@dataclass(frozen=True)
class ReserveRule:
    start: date
    end: date
    am_rate: float
    pm_rate: float
    label: str = ""

    def rate_for(self, service_date: date, period: str) -> Optional[float]:
        if not (self.start <= service_date <= self.end):
            return None
        return self.am_rate if period in AM_PERIODS else self.pm_rate


@dataclass
class SlotSnapshot:
    service_date: str
    period: str
    unassigned_people: int
    reserve_rate: float
    reserve_people_target: int
    reserve_order_target: int
    market_people_target: int
    raw_text: str = ""


def _assert_supported_env(env_name: str) -> None:
    env = str(env_name or "").strip().lower()
    if env not in {"dev", "prod"}:
        raise RuntimeError("檸檬保留單只支援 prod 正式機或 dev 測試機。")


def _purchase_id_from_order_no(order_no: str) -> str:
    digits = re.sub(r"\D", "", str(order_no or ""))
    return str(int(digits)) if digits else ""


def _mark_customer_memo_as_system_reserve(session, base_url: str, order_no: str) -> Tuple[bool, str]:
    purchase_id = _purchase_id_from_order_no(order_no)
    if not purchase_id:
        return False, "無法由訂單編號取得 purchase_id"
    return co._update_cancel_notes(
        session,
        base_url,
        purchase_id,
        customer_memo=SYSTEM_RESERVE_MEMO,
        charge_note="",
        refund_note="",
    )


def daterange(start: date, end: date) -> Iterable[date]:
    if end < start:
        raise ValueError("結束日期不可早於開始日期")
    cur = start
    while cur <= end:
        yield cur
        cur += timedelta(days=1)


def normalize_rate(value: float) -> float:
    rate = float(value)
    if rate > 1:
        rate = rate / 100.0
    if rate < 0 or rate > 1:
        raise ValueError("保留率必須介於 0% 到 100%")
    return rate


def resolve_rate(service_date: date, period: str, rules: Sequence[ReserveRule], default_rate: float = 0.0) -> float:
    for rule in rules:
        rate = rule.rate_for(service_date, period)
        if rate is not None:
            return normalize_rate(rate)
    return normalize_rate(default_rate)


def calculate_reserve_target(unassigned_people: int, reserve_rate: float) -> Tuple[int, int, int]:
    people = max(0, int(unassigned_people or 0))
    rate = normalize_rate(reserve_rate)
    reserve_orders = int(math.floor((people * rate) / 2.0))
    reserve_people = reserve_orders * 2
    market_people = max(0, people - reserve_people)
    return reserve_people, reserve_orders, market_people


def login_reserve_member(env_name: str, backend_email: str, backend_password: str, phone: str = RESERVE_PHONE_DEFAULT):
    _assert_supported_env(env_name)
    result = qo.quick_lookup_member(env_name, backend_email, backend_password, phone, clean_type_id="1")
    if not result.get("member_payload"):
        machine = "正式機" if str(env_name).lower() == "prod" else "測試機"
        raise RuntimeError(f"保留單手機 {phone} 在{machine}查無會員，請先確認會員資料。")
    return result


def member_addresses(lookup_result) -> List[str]:
    payload = lookup_result.get("member_payload") or {}
    member = payload.get("member") or {}
    rows = member.get("memberAddressList") or []
    addresses: List[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        addr = str(row.get("address") or "").strip()
        if addr and addr not in addresses:
            addresses.append(addr)
    last = payload.get("lastPurchase") or {}
    last_addr = str(last.get("address") or "").strip() if isinstance(last, dict) else ""
    if last_addr and last_addr not in addresses:
        addresses.insert(0, last_addr)
    return addresses


def fetch_schedule_html(lookup_result, service_date: str) -> str:
    session = lookup_result["session"]
    base_url = lookup_result["base_url"]
    resp = session.get(
        f"{base_url}/schedule",
        params={"date": service_date, "staffId": ""},
        headers=getattr(qo, "HEADERS", {}),
        allow_redirects=True,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"讀取班表失敗：{service_date} HTTP {resp.status_code}")
    return resp.text or ""


def _period_from_text(text: str) -> str:
    compact = re.sub(r"\s+", "", str(text or ""))
    for period in sorted(PERIOD_HOURS, key=len, reverse=True):
        if period in compact:
            return period
    return ""


def parse_schedule_unassigned(html_text: str, service_date: str = "") -> Dict[str, Dict[str, object]]:
    soup = BeautifulSoup(html_text or "", "html.parser")
    result: Dict[str, Dict[str, object]] = {}

    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if not rows:
            continue
        header_cells = rows[0].find_all(["th", "td"])
        periods = [_period_from_text(c.get_text(" ", strip=True)) for c in header_cells]
        if not any(periods):
            continue
        for row in rows[1:]:
            cells = row.find_all(["th", "td"])
            if len(cells) < 2:
                continue
            row_text = row.get_text(" ", strip=True)
            if service_date:
                mmdd = service_date[5:]
                if mmdd not in row_text and service_date not in row_text and len(rows) > 2:
                    continue
            for idx, cell in enumerate(cells):
                if idx >= len(periods) or not periods[idx]:
                    continue
                text = cell.get_text(" ", strip=True)
                m = re.search(r"未配班\s*(\d+)\s*人", text)
                if m:
                    result[periods[idx]] = {"unassigned_people": int(m.group(1)), "raw_text": text}

    if not result:
        plain = soup.get_text(" ", strip=True)
        for period in PERIOD_HOURS:
            pos = plain.find(period)
            if pos < 0:
                continue
            window = plain[pos:pos + 1600]
            m = re.search(r"未配班\s*(\d+)\s*人", window)
            if m:
                result[period] = {"unassigned_people": int(m.group(1)), "raw_text": window[:500]}
    return result


def snapshot_day(lookup_result, service_date: date, rules: Sequence[ReserveRule], periods: Sequence[str]) -> List[SlotSnapshot]:
    date_s = service_date.isoformat()
    parsed = parse_schedule_unassigned(fetch_schedule_html(lookup_result, date_s), date_s)
    rows: List[SlotSnapshot] = []
    for period in periods:
        info = parsed.get(period) or {}
        people = int(info.get("unassigned_people") or 0)
        rate = resolve_rate(service_date, period, rules)
        reserve_people, reserve_orders, market_people = calculate_reserve_target(people, rate)
        rows.append(SlotSnapshot(
            service_date=date_s,
            period=period,
            unassigned_people=people,
            reserve_rate=rate,
            reserve_people_target=reserve_people,
            reserve_order_target=reserve_orders,
            market_people_target=market_people,
            raw_text=str(info.get("raw_text") or ""),
        ))
    return rows


def build_period_plan(lookup_result, start: date, end: date, rules: Sequence[ReserveRule], periods: Sequence[str]) -> List[SlotSnapshot]:
    plan: List[SlotSnapshot] = []
    for d in daterange(start, end):
        plan.extend(snapshot_day(lookup_result, d, rules, periods))
    return plan


def _build_batch_id() -> str:
    return f"reserve_{date.today().strftime('%Y%m%d')}_{uuid.uuid4().hex[:8]}"


def _extract_amount(result: dict):
    for key in ("total_amount", "amount", "price", "customer_due", "order_amount"):
        value = result.get(key)
        if value not in (None, ""):
            return value
    return 0


def create_reserve_orders_for_slot(
    *, env_name: str, lookup_result, region: str, address: str,
    service_date: str, period: str, reserve_rate: float, target_orders: int,
    payway: str, clean_type_id: str = "1", batch_id: str = "",
    stop_when_market_people_below: int = 2, sleep_seconds: float = 1.0,
) -> dict:
    _assert_supported_env(env_name)
    if period not in PERIOD_HOURS:
        raise ValueError(f"不支援時段：{period}")
    if not address:
        raise ValueError("請先選擇保留會員的服務地址")

    target_orders = max(0, int(target_orders or 0))
    batch_id = batch_id or _build_batch_id()
    results = []

    for idx in range(target_orders):
        current = parse_schedule_unassigned(fetch_schedule_html(lookup_result, service_date), service_date)
        current_people = int((current.get(period) or {}).get("unassigned_people") or 0)
        if current_people < max(2, int(stop_when_market_people_below) + 2):
            results.append({
                "success": False, "stopped": True,
                "message": f"即時未配班只剩 {current_people} 人，已停止後續保留單，避免吃掉市場安全人力。",
                "service_date": service_date, "period": period,
            })
            break

        try:
            result = qo.quick_create_order(
                env_name=env_name,
                payway=payway,
                region=region,
                lookup_result=lookup_result,
                address=address,
                clean_type_id=clean_type_id,
                date_s=service_date,
                period_s=period,
                hour=str(PERIOD_HOURS[period]),
                person="2",
                allow_auto_lemon_shift=False,
                extra_fields={"notice": CUSTOMER_SERVICE_NOTE},
            )
            base_url = lookup_result.get("base_url") or qo._configure_environment(env_name)

            try:
                customer_memo_ok, customer_memo_msg = _mark_customer_memo_as_system_reserve(
                    result["session"], base_url, result["order_no"]
                )
            except Exception as memo_exc:
                customer_memo_ok = False
                customer_memo_msg = f"客人備註註記失敗：{memo_exc}"

            try:
                note_ok, note_msg = qo._update_order_note(
                    result["session"], base_url, result["order_no"], CUSTOMER_SERVICE_NOTE
                )
            except Exception as note_exc:
                note_ok = False
                note_msg = f"訂單已成立，但客服備註寫入失敗：{note_exc}"

            row = {
                "success": True,
                "order_no": result.get("order_no"),
                "staff": result.get("staff"),
                "service_date": service_date,
                "period": period,
                "order_amount": _extract_amount(result),
                "batch_id": batch_id,
                "customer_memo_ok": customer_memo_ok,
                "customer_memo": SYSTEM_RESERVE_MEMO if customer_memo_ok else "",
                "customer_memo_message": customer_memo_msg,
                "note_ok": note_ok,
                "note_message": note_msg,
            }

            try:
                row["sheet_log_count"] = append_log_rows("成立", [row], batch_id=batch_id)
                row["sheet_log_error"] = ""
            except Exception as log_exc:
                row["sheet_log_count"] = 0
                row["sheet_log_error"] = str(log_exc)

            results.append(row)

            if not customer_memo_ok:
                results.append({
                    "success": False, "stopped": True,
                    "service_date": service_date, "period": period,
                    "message": f"訂單 {result.get('order_no')} 已成立，但客人備註未成功寫入『{SYSTEM_RESERVE_MEMO}』，已停止此時段後續建立。",
                })
                break
        except Exception as exc:
            results.append({"success": False, "message": str(exc), "service_date": service_date, "period": period})
            break

        if sleep_seconds:
            time.sleep(float(sleep_seconds))

    return {
        "batch_id": batch_id,
        "service_date": service_date,
        "period": period,
        "target_orders": target_orders,
        "success_count": sum(1 for r in results if r.get("success")),
        "results": results,
    }


def _mark_reserve_notes(session, base_url: str, order_no: str) -> Tuple[bool, str]:
    """開一次訂單修改頁，同時寫入客人備註「系統保留單」與處理備註，其餘欄位保留原值。"""
    purchase_id = _purchase_id_from_order_no(order_no)
    if not purchase_id:
        return False, "無法由訂單編號取得 purchase_id"
    edit_url = f"{base_url}/purchase/edit/{purchase_id}"
    resp = session.get(edit_url, headers=qo.HEADERS, allow_redirects=True)
    if resp.status_code != 200:
        return False, f"無法開啟訂單修改頁：HTTP {resp.status_code}"
    token = re.search(r'<meta name="csrf-token" content="([^"]+)"', resp.text) or re.search(r'name="_token"[^>]*value="([^"]+)"', resp.text)
    if not token:
        return False, "無法取得訂單修改頁 CSRF token"
    payload = qo._build_purchase_edit_payload_from_page(
        resp.text, token.group(1),
        overrides={"memo": SYSTEM_RESERVE_MEMO, "memoProcess": CUSTOMER_SERVICE_NOTE},
    )
    post = session.post(
        edit_url, data=payload,
        headers={**qo.HEADERS, "Content-Type": "application/x-www-form-urlencoded"},
        allow_redirects=True,
    )
    if post.status_code not in (200, 302):
        return False, f"備註寫入失敗：HTTP {post.status_code}"
    return True, ""


def _finish_reserve_order(session, base_url: str, order_no: str, service_date: str, period: str,
                          staff: str, amount, batch_id: str) -> dict:
    """保留單成立後：一次寫入客人備註「系統保留單」與處理備註（紀錄表由呼叫端整輪一次寫入）。"""
    try:
        customer_memo_ok, customer_memo_msg = _mark_reserve_notes(session, base_url, order_no)
    except Exception as memo_exc:
        customer_memo_ok, customer_memo_msg = False, f"備註寫入失敗：{memo_exc}"
    note_ok, note_msg = customer_memo_ok, customer_memo_msg
    row = {
        "success": True, "order_no": order_no, "staff": staff,
        "service_date": service_date, "period": period, "order_amount": amount,
        "batch_id": batch_id, "customer_memo_ok": customer_memo_ok,
        "customer_memo": SYSTEM_RESERVE_MEMO if customer_memo_ok else "",
        "customer_memo_message": customer_memo_msg, "note_ok": note_ok, "note_message": note_msg,
    }
    return row


def _log_round_rows(rows: List[dict], batch_id: str) -> None:
    """整輪成立的保留單一次寫入紀錄表（原本每張各寫一次）。"""
    if not rows:
        return
    try:
        count = append_log_rows("成立", rows, batch_id=batch_id)
        error = ""
    except Exception as log_exc:
        count, error = 0, str(log_exc)
    for row in rows:
        row["sheet_log_count"] = count
        row["sheet_log_error"] = error


def start_reserve_job(plan_rows: Sequence[dict], payway: str) -> dict:
    """建立保留單工作狀態；之後每呼叫一次 run_reserve_round 執行一輪，可在輪與輪之間暫停。"""
    remaining: Dict[str, int] = {}
    keep_people: Dict[str, int] = {}
    for row in plan_rows or []:
        target = max(0, int(row.get("reserve_order_target") or 0))
        period = str(row.get("period") or "")
        if target <= 0:
            continue
        if period not in PERIOD_HOURS:
            raise ValueError(f"不支援時段：{period}")
        slot = f"{row.get('service_date')}_{period}"
        remaining[slot] = remaining.get(slot, 0) + target
        keep_people[slot] = int(row.get("market_people_target") or 0)
    return {
        "batch_id": _build_batch_id(), "payway": qo.normalize_booking_payway(payway),
        "remaining": remaining, "keep_people": keep_people,
        "target_orders": sum(remaining.values()), "round": 0, "results": [], "done": not remaining,
        "stopped_orders": 0,
    }


def run_reserve_round(
    state: dict, *, env_name: str, lookup_result, region: str, address: str, clean_type_id: str = "1",
) -> dict:
    """執行一輪保留單：先重新分析各日期剩餘未配班人數，再建立每個時段各一張。

    儲值金：這一輪的日期時段一次勾選、一次送出（批次成單）；
    信用卡／ATM：後台一次只能一個時段，逐時段各送一張。
    """
    _assert_supported_env(env_name)
    if not address:
        raise ValueError("請先選擇保留會員的服務地址")
    if state.get("done"):
        return state
    remaining, keep_people, results = state["remaining"], state["keep_people"], state["results"]
    batch_id = state["batch_id"]
    state["round"] += 1
    round_no = state["round"]
    base_url = lookup_result.get("base_url") or qo._configure_environment(env_name)

    def stop(slot, message):
        service_date, period = slot.split("_", 1)
        results.append({"success": False, "stopped": True, "service_date": service_date, "period": period,
                        "round": round_no, "message": f"第 {round_no} 輪：{message}（此時段停止，{remaining[slot]} 張未建）"})
        state["stopped_orders"] = state.get("stopped_orders", 0) + remaining[slot]
        remaining[slot] = 0

    active: List[str] = []
    schedules: Dict[str, Dict[str, Dict[str, object]]] = {}
    pages: List[str] = []
    for slot in [x for x, n in remaining.items() if n > 0]:
        service_date, period = slot.split("_", 1)
        if service_date not in schedules:
            # 班表頁一次顯示一整週；同一週的日期共用同一頁，不重複讀取。
            label = f"{service_date[5:]}（"
            html = next((h for h in pages if label in h), None)
            if html is None:
                html = fetch_schedule_html(lookup_result, service_date)
                pages.append(html)
            schedules[service_date] = parse_schedule_unassigned(html, service_date)
        people = int((schedules[service_date].get(period) or {}).get("unassigned_people") or 0)
        if people < max(2, keep_people.get(slot, 0) + 2):
            stop(slot, f"即時未配班只剩 {people} 人，已停止此時段後續保留單")
            continue
        active.append(slot)

    created = 0
    if state["payway"] == "儲值金":
        by_hour: Dict[int, List[str]] = {}
        for slot in active:
            by_hour.setdefault(PERIOD_HOURS[slot.split("_", 1)[1]], []).append(slot)
        for hour, slots in by_hour.items():
            try:
                outcome = qo.quick_create_stored_value_orders(
                    env_name, region, lookup_result, address, clean_type_id, slots, str(hour),
                    person="2", extra_fields={"notice": CUSTOMER_SERVICE_NOTE},
                )
            except Exception as exc:
                for slot in slots:
                    stop(slot, f"送出失敗：{exc}")
                continue
            session = outcome.get("session") or lookup_result["session"]
            round_rows = []
            for order in outcome.get("orders") or []:
                row = _finish_reserve_order(session, base_url, order["order_no"], order["date"],
                                            order["period_s"], order.get("staff"), 0, batch_id)
                row["round"] = round_no
                results.append(row)
                round_rows.append(row)
                remaining[order["slot"]] -= 1
                created += 1
                if not row["customer_memo_ok"]:
                    stop(order["slot"], f"訂單 {order['order_no']} 已成立，但客人備註未成功寫入『{SYSTEM_RESERVE_MEMO}』，已停止此時段後續建立")
            _log_round_rows(round_rows, batch_id)
            for slot in outcome.get("unavailable") or []:
                stop(slot, f"{slot.replace('_', ' ')} 無可預約人力（後台查詢班表結果沒有這個時段），已停止此時段")
            for slot in outcome.get("not_created") or []:
                reason = "後台回覆儲值金餘額不足" if outcome.get("failed_count") else "送出後未找到新訂單，請至後台確認"
                stop(slot, f"{reason}，已停止此時段")
    else:
        for slot in active:
            service_date, period = slot.split("_", 1)
            one = create_reserve_orders_for_slot(
                env_name=env_name, lookup_result=lookup_result, region=region, address=address,
                service_date=service_date, period=period, reserve_rate=0, target_orders=1,
                payway=state["payway"], clean_type_id=clean_type_id, batch_id=batch_id,
                stop_when_market_people_below=keep_people.get(slot, 0), sleep_seconds=0,
            )
            for row in one.get("results") or []:
                row["round"] = round_no
                if row.get("success"):
                    results.append(row)
                    remaining[slot] -= 1
                    created += 1
                else:
                    stop(slot, str(row.get("message") or "建立失敗"))
    state["success_count"] = sum(1 for r in results if r.get("success"))
    state["done"] = created == 0 or not any(n > 0 for n in remaining.values())
    return state


def create_reserve_orders_batch(
    *, env_name: str, lookup_result, region: str, address: str,
    plan_rows: Sequence[dict], clean_type_id: str = "1", sleep_seconds: float = 1.0,
    payway: str = "儲值金",
) -> dict:
    """不需暫停時，一次跑完所有輪。"""
    _assert_supported_env(env_name)
    if not address:
        raise ValueError("請先選擇保留會員的服務地址")
    state = start_reserve_job(plan_rows, payway)
    while not state["done"]:
        run_reserve_round(state, env_name=env_name, lookup_result=lookup_result, region=region,
                          address=address, clean_type_id=clean_type_id)
        if not state["done"] and sleep_seconds:
            time.sleep(float(sleep_seconds))
    return {
        "batch_id": state["batch_id"], "target_orders": state["target_orders"], "rounds": state["round"],
        "success_count": sum(1 for r in state["results"] if r.get("success")),
        "slot_count": len(state["remaining"]), "results": state["results"],
    }


def create_reserve_orders_for_plan(
    *, env_name: str, lookup_result, region: str, address: str,
    plan_rows: Sequence[dict], payway: str, clean_type_id: str = "1",
    continue_after_slot_error: bool = True, sleep_seconds: float = 1.0,
) -> dict:
    _assert_supported_env(env_name)
    if qo.normalize_booking_payway(payway) == "儲值金":
        # 儲值金頁可一次勾多個日期時段：照批次成單邏輯分輪一次送出。
        return create_reserve_orders_batch(
            env_name=env_name, lookup_result=lookup_result, region=region, address=address,
            plan_rows=plan_rows, clean_type_id=clean_type_id, sleep_seconds=sleep_seconds,
        )
    batch_id = _build_batch_id()
    slot_results = []
    flat_results = []
    total_target = 0

    for row in plan_rows or []:
        target_orders = max(0, int(row.get("reserve_order_target") or 0))
        if target_orders <= 0:
            continue
        total_target += target_orders
        service_date = str(row.get("service_date") or "")
        period = str(row.get("period") or "")
        try:
            slot_result = create_reserve_orders_for_slot(
                env_name=env_name,
                lookup_result=lookup_result,
                region=region,
                address=address,
                service_date=service_date,
                period=period,
                reserve_rate=float(row.get("reserve_rate") or 0),
                target_orders=target_orders,
                payway=payway,
                clean_type_id=clean_type_id,
                batch_id=batch_id,
                stop_when_market_people_below=int(row.get("market_people_target") or 0),
                sleep_seconds=sleep_seconds,
            )
        except Exception as exc:
            slot_result = {
                "batch_id": batch_id,
                "service_date": service_date,
                "period": period,
                "target_orders": target_orders,
                "success_count": 0,
                "results": [{"success": False, "service_date": service_date, "period": period, "message": str(exc)}],
            }
        slot_results.append(slot_result)
        flat_results.extend(slot_result.get("results") or [])
        has_failure = any(not r.get("success") for r in (slot_result.get("results") or []))
        if has_failure and not continue_after_slot_error:
            break

    return {
        "batch_id": batch_id,
        "target_orders": total_target,
        "success_count": sum(1 for r in flat_results if r.get("success")),
        "slot_count": len(slot_results),
        "slot_results": slot_results,
        "results": flat_results,
    }
