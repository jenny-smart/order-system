# ============================================================
# 檔名：function/reserve_optimizer.py
# 功能：檸檬保留單班表分析、保留率計算、即時未配班檢查、批次建立與紀錄回寫。
# 更新時間：2026-08-19
# ============================================================
# -*- coding: utf-8 -*-
"""檸檬保留單：班表分析與批次建單。"""
from __future__ import annotations
import math, re, time, uuid
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional
from bs4 import BeautifulSoup
from shared import booking_service as booking
from shared.reserve_log_service import append_logs, make_log_row, service_amount_from_result
from function import cancel_order as co

RESERVE_PHONE_DEFAULT = "0939592628"
SYSTEM_RESERVE_MEMO = "系統保留單"
CUSTOMER_SERVICE_NOTE = "大掃除檸檬保留單"
PERIOD_HOURS = {"08:30-12:30":4,"09:00-11:00":2,"09:00-12:00":3,"14:00-16:00":2,"14:00-17:00":3,"14:00-18:00":4,"09:00-16:00":6,"09:00-18:00":8}
AM_PERIODS = {"08:30-12:30","09:00-11:00","09:00-12:00","09:00-16:00","09:00-18:00"}

@dataclass(frozen=True)
class ReserveRule:
    start: date; end: date; am_rate: float; pm_rate: float; label: str = ""
    def rate_for(self, service_date: date, period: str) -> Optional[float]:
        if not self.start <= service_date <= self.end: return None
        return self.am_rate if period in AM_PERIODS else self.pm_rate

@dataclass
class SlotSnapshot:
    service_date: str; period: str; unassigned_people: int; reserve_rate: float
    reserve_people_target: int; reserve_order_target: int; market_people_target: int; raw_text: str = ""

def _assert_supported_env(env_name):
    if str(env_name or "").strip().lower() not in {"dev","prod"}: raise RuntimeError("檸檬保留單只支援 prod 正式機或 dev 測試機。")
def daterange(start,end):
    if end < start: raise ValueError("結束日期不可早於開始日期")
    cur=start
    while cur<=end: yield cur; cur+=timedelta(days=1)
def normalize_rate(value):
    rate=float(value); rate=rate/100.0 if rate>1 else rate
    if not 0<=rate<=1: raise ValueError("保留率必須介於 0% 到 100%")
    return rate
def resolve_rate(service_date,period,rules,default_rate=0.0):
    for rule in rules:
        rate=rule.rate_for(service_date,period)
        if rate is not None: return normalize_rate(rate)
    return normalize_rate(default_rate)
def calculate_reserve_target(unassigned_people,reserve_rate):
    people=max(0,int(unassigned_people or 0)); orders=int(math.floor((people*normalize_rate(reserve_rate))/2.0)); reserved=orders*2
    return reserved,orders,max(0,people-reserved)
def login_reserve_member(env_name,backend_email,backend_password,phone=RESERVE_PHONE_DEFAULT):
    _assert_supported_env(env_name); result=booking.lookup_member(env_name,backend_email,backend_password,phone,clean_type_id="1")
    if not result.get("member_payload"): raise RuntimeError(f"保留單手機 {phone} 查無會員。")
    return result
def member_addresses(lookup_result):
    payload=lookup_result.get("member_payload") or {}; member=payload.get("member") or {}; addresses=[]
    for row in member.get("memberAddressList") or []:
        if isinstance(row,dict):
            addr=str(row.get("address") or "").strip()
            if addr and addr not in addresses: addresses.append(addr)
    last=payload.get("lastPurchase") or {}; last_addr=str(last.get("address") or "").strip() if isinstance(last,dict) else ""
    if last_addr and last_addr not in addresses: addresses.insert(0,last_addr)
    return addresses
def fetch_schedule_html(lookup_result,service_date):
    resp=lookup_result["session"].get(f"{lookup_result['base_url']}/schedule",params={"date":service_date,"staffId":""},headers=booking.request_headers(),allow_redirects=True,timeout=20)
    if resp.status_code!=200: raise RuntimeError(f"讀取班表失敗：{service_date} HTTP {resp.status_code}")
    return resp.text or ""
def _period_from_text(text):
    compact=re.sub(r"\s+","",str(text or ""))
    for period in sorted(PERIOD_HOURS,key=len,reverse=True):
        if period in compact: return period
    return ""
def parse_schedule_unassigned(html_text,service_date=""):
    soup=BeautifulSoup(html_text or "","html.parser"); result={}
    for table in soup.find_all("table"):
        rows=table.find_all("tr")
        if not rows: continue
        periods=[_period_from_text(c.get_text(" ",strip=True)) for c in rows[0].find_all(["th","td"])]
        if not any(periods): continue
        for row in rows[1:]:
            cells=row.find_all(["th","td"])
            for idx,cell in enumerate(cells):
                if idx>=len(periods) or not periods[idx]: continue
                text=cell.get_text(" ",strip=True); m=re.search(r"未配班\s*(\d+)\s*人",text)
                if m: result[periods[idx]]={"unassigned_people":int(m.group(1)),"raw_text":text}
    return result
def snapshot_day(lookup_result,service_date,rules,periods):
    date_s=service_date.isoformat(); parsed=parse_schedule_unassigned(fetch_schedule_html(lookup_result,date_s),date_s); rows=[]
    for period in periods:
        info=parsed.get(period) or {}; people=int(info.get("unassigned_people") or 0); rate=resolve_rate(service_date,period,rules); rp,ro,mp=calculate_reserve_target(people,rate)
        rows.append(SlotSnapshot(date_s,period,people,rate,rp,ro,mp,str(info.get("raw_text") or "")))
    return rows
def build_period_plan(lookup_result,start,end,rules,periods):
    plan=[]
    for d in daterange(start,end): plan.extend(snapshot_day(lookup_result,d,rules,periods))
    return plan
def _purchase_id_from_order_no(order_no):
    digits=re.sub(r"\D","",str(order_no or "")); return str(int(digits)) if digits else ""
def _mark_customer_memo(session,base_url,order_no):
    purchase_id=_purchase_id_from_order_no(order_no)
    if not purchase_id: return False,"無法取得 purchase_id"
    return co._update_cancel_notes(session,base_url,purchase_id,customer_memo=SYSTEM_RESERVE_MEMO,charge_note="",refund_note="")
def _build_batch_id(): return f"reserve_{date.today().strftime('%Y%m%d')}_{uuid.uuid4().hex[:8]}"

def create_reserve_orders_for_plan(*,env_name,lookup_result,region,address,plan_rows,payway,clean_type_id="1",continue_after_slot_error=True,sleep_seconds=0.5):
    _assert_supported_env(env_name); batch_id=_build_batch_id(); flat=[]; target=0; log_rows=[]
    for row in plan_rows or []:
        qty=max(0,int(row.get("reserve_order_target") or 0))
        if qty<=0: continue
        target+=qty; date_s=str(row.get("service_date") or ""); period=str(row.get("period") or "")
        for seq in range(1,qty+1):
            try:
                current=parse_schedule_unassigned(fetch_schedule_html(lookup_result,date_s),date_s); people=int((current.get(period) or {}).get("unassigned_people") or 0)
                if people<2:
                    msg=f"即時未配班只剩 {people} 人，停止此時段"; flat.append({"success":False,"service_date":date_s,"period":period,"message":msg}); break
                result=booking.create_order(env_name=env_name,payway=payway,region=region,lookup_result=lookup_result,address=address,clean_type_id=clean_type_id,date_s=date_s,period_s=period,hour=str(PERIOD_HOURS[period]),person="2",allow_auto_lemon_shift=False,extra_fields={"notice":CUSTOMER_SERVICE_NOTE})
                base_url=lookup_result.get("base_url") or booking.configure_environment(env_name); memo_ok,memo_msg=_mark_customer_memo(result["session"],base_url,result.get("order_no"))
                try: note_ok,note_msg=booking.update_order_note(result["session"],base_url,result.get("order_no"),CUSTOMER_SERVICE_NOTE)
                except Exception as exc: note_ok,note_msg=False,str(exc)
                amount=service_amount_from_result(result)
                item={"success":True,"order_no":result.get("order_no"),"staff":result.get("staff"),"service_date":date_s,"period":period,"batch_id":batch_id,"order_amount":amount,"customer_memo_ok":memo_ok,"customer_memo_message":memo_msg,"note_ok":note_ok,"note_message":note_msg}
                flat.append(item); log_rows.append(make_log_row(operation="成立",order_no=item["order_no"],service_date=date_s,period=period,staff=item["staff"],amount=amount,batch_id=batch_id,success=True,note=memo_msg or note_msg))
                if not memo_ok: break
            except Exception as exc:
                flat.append({"success":False,"service_date":date_s,"period":period,"message":str(exc)})
                if not continue_after_slot_error:
                    if log_rows: append_logs(log_rows,batch_size=10)
                    return {"batch_id":batch_id,"target_orders":target,"success_count":sum(1 for x in flat if x.get("success")),"results":flat}
                break
            if sleep_seconds: time.sleep(float(sleep_seconds))
    log_status={"written":0,"batches":0}
    if log_rows:
        try: log_status=append_logs(log_rows,batch_size=10)
        except Exception as exc: log_status={"written":0,"batches":0,"error":str(exc)}
    return {"batch_id":batch_id,"target_orders":target,"success_count":sum(1 for x in flat if x.get("success")),"results":flat,"log_status":log_status}
