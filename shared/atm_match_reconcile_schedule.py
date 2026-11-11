# -*- coding: utf-8 -*-
"""ATM 對帳 ② 配對銀行明細＋③ 更新系統對帳（雲端排程；2026-11-12 起跟在 ① 待付款清單後 10 分鐘，
上班日 08:30～18:00 每 30 分鐘，時間見主控表「排程設定」atm_match_reconcile）。

由 tool-system 的 Cloud Schedule Router 依主控表「排程設定」（功能代號 atm_match_reconcile）
派送 .github/workflows/atm-match-reconcile-schedule.yml。

台北／台中各自：
  ② memo_system.atm.auto_match_bank_rows：M 欄末碼（後 5 碼）或 K 欄姓名比對 F 欄備註＋金額；
     G 欄補公式、I／N／O 補下拉選單；N/O 空白時 2000 → 清潔／新訓費、其他 → 清潔／服務費用。
  ③ memo_system.atm.process_atm_rows：只處理 T 欄「已配對」（含多訂單加總）、J 欄有訂單編號、
     M 欄不是取消訂單、B 欄入帳日不早於 2026/11/06 的列；按已付款＋開立發票＋發確認信。
     訂單本來就已付款的不再發確認信；未開立發票的不發確認信。
     需確認／疑似拆單／非訂單收入一律留給人工。
行事曆（預設 jenny@hers.com.tw，寫不進去改寫 jenny@lemonclean.com.tw；可用 ATM_CALENDAR_ID 指定）：
  當日完成對帳的訂單記一則「【ATM對帳】今日完成」（只留紀錄，不跳提醒；一天跑多次會累加，不會蓋掉早上的）；
  已付款但未開立發票的另記「【ATM對帳】未開立發票」（30 分鐘後、提前 20／10 分鐘跳提醒）；
  ② 需確認／疑似拆單／未配對／清潔異動未回填等記「【ATM對帳】需人工處理」（同上提醒）。
  這兩種內容和當天已記的一樣就不重建，避免每 30 分鐘重複跳通知；有新的項目才換成最新一則。

Actions 紀錄只印各區筆數，不印客戶姓名、訂單編號；逐筆明細寫進行事曆與統一執行 Log。
"""
from __future__ import annotations

import argparse
import contextlib
import io
import os
import re
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

TOOL_NAME = "ATM 配對銀行明細＋更新系統對帳"
TZ = ZoneInfo("Asia/Taipei")
CALENDAR_IDS = ("jenny@hers.com.tw", "jenny@lemonclean.com.tw")
DONE_PREFIX = "【ATM對帳】今日完成"
NO_INVOICE_PREFIX = "【ATM對帳】未開立發票"
REVIEW_PREFIX = "【ATM對帳】需人工處理"


def summary_lines(result: dict) -> list[str]:
    lines = []
    for region, item in (result or {}).items():
        item = item or {}
        m = item.get("match") or {}
        r = item.get("reconcile") or {}
        line = (
            f"{region}：② 配對成功 {m.get('success', 0)}、需確認 {m.get('confirm_required', 0)}、"
            f"未配對 {m.get('unmatched', 0)}、多筆候選 {m.get('ambiguous', 0)}；"
            f"③ 更新系統 {r.get('success', 0)}／{len(item.get('reconcile_rows') or [])} 列、"
            f"失敗 {r.get('failed', 0)}、略過 {r.get('skipped', 0)}、"
            f"未開發票 {len(r.get('no_invoice') or [])}"
        )
        if item.get("error"):
            line += "（發生錯誤）"
        lines.append(line)
    return lines


def collect(result: dict, key: str) -> list[dict]:
    items = []
    for item in (result or {}).values():
        items.extend(((item or {}).get("reconcile") or {}).get(key) or [])
    return items


def _line(d: dict) -> str:
    text = f"{d.get('region', '')} 第{d.get('row')}列 {d.get('order_no', '')} {d.get('name', '')} ${d.get('amount', '')}"
    if d.get("invoice_no"):
        text += f"　發票 {d['invoice_no']}"
    if d.get("already_paid"):
        text += "　（原已付款，未發確認信）"
    elif d.get("mail_sent"):
        text += "　已發確認信"
    if d.get("reason"):
        text += f"　{d['reason']}"
    return text


def collect_review(result: dict) -> list[str]:
    lines = []
    for region, item in (result or {}).items():
        for r in ((item or {}).get("match") or {}).get("review") or []:
            lines.append(f"{region} 第{r['列號']}列【{r['類型']}】{r['訂單']} {r['姓名']} ${r['金額']}　{r['說明']}")
    return lines


def build_calendar_events(result: dict, now: datetime) -> list[dict]:
    done = collect(result, "completed")
    no_invoice = collect(result, "no_invoice")
    review = collect_review(result)
    events = []
    if done:
        events.append(dict(
            summary=f"{DONE_PREFIX} {len(done)} 筆（{now:%m/%d}）",
            description="\n".join(_line(d) for d in done),
            start=now, reminder_minutes=[], replace_prefix=DONE_PREFIX, merge=True,
        ))
    if no_invoice:
        events.append(dict(
            summary=f"{NO_INVOICE_PREFIX} {len(no_invoice)} 筆，請到後台開立",
            description="\n".join(_line(d) for d in no_invoice),
            start=now + timedelta(minutes=30), reminder_minutes=[20, 10], replace_prefix=NO_INVOICE_PREFIX,
        ))
    if review:
        # 需確認／疑似拆單／未配對／清潔異動未回填：排程沒有畫面，改記在行事曆
        events.append(dict(
            summary=f"{REVIEW_PREFIX} {len(review)} 列",
            description="\n".join(review),
            start=now + timedelta(minutes=30), reminder_minutes=[20, 10], replace_prefix=REVIEW_PREFIX,
        ))
    return events


HERS_CALENDAR_ID = "jenny@hers.com.tw"


def _oauth_calendar_credentials(calendar_id: str):
    """
    Jenny 本人授權的行事曆憑證（與 tool-system calendar_notify 相同的 Secrets）：
    jenny@hers.com.tw → GOOGLE_HERS_CALENDAR_REFRESH_TOKEN；其他 → GOOGLE_CALENDAR_REFRESH_TOKEN。
    用戶端：GOOGLE_CALENDAR_CLIENT_ID／SECRET，沒有就用 GOOGLE_OAUTH_CLIENT_ID／SECRET。
    沒設定回傳 None（服務帳號沒有 Jenny 行事曆的寫入權，會回 404）。
    """
    from google.oauth2.credentials import Credentials as OAuthCredentials

    key = "GOOGLE_HERS_CALENDAR_REFRESH_TOKEN" if calendar_id == HERS_CALENDAR_ID else "GOOGLE_CALENDAR_REFRESH_TOKEN"
    refresh_token = os.getenv(key, "").strip()
    client_id = (os.getenv("GOOGLE_CALENDAR_CLIENT_ID", "") or os.getenv("GOOGLE_OAUTH_CLIENT_ID", "")).strip()
    client_secret = (os.getenv("GOOGLE_CALENDAR_CLIENT_SECRET", "") or os.getenv("GOOGLE_OAUTH_CLIENT_SECRET", "")).strip()
    if not (refresh_token and client_id and client_secret):
        return None
    return OAuthCredentials(token=None, refresh_token=refresh_token, token_uri="https://oauth2.googleapis.com/token",
                            client_id=client_id, client_secret=client_secret,
                            scopes=["https://www.googleapis.com/auth/calendar.events"])


def _calendar_service(calendar_id: str = ""):
    """行事曆連線：有 Jenny 本人授權就用（寫得進她的行事曆），沒有才用服務帳號。"""
    from google.oauth2.service_account import Credentials
    from googleapiclient.discovery import build

    creds = _oauth_calendar_credentials(calendar_id)
    if creds is None:
        from shared.gsheet import get_service_account_info

        creds = Credentials.from_service_account_info(
            get_service_account_info(), scopes=["https://www.googleapis.com/auth/calendar"])
    return build("calendar", "v3", credentials=creds, cache_discovery=False)


def service_for(service_factory, calendar_id: str):
    """依行事曆取得連線（相容只收 0 個參數的 factory）。"""
    try:
        return service_factory(calendar_id)
    except TypeError:
        return service_factory()


def _insert_event(service, calendar_id: str, summary: str, description: str, start: datetime,
                  reminder_minutes: list, replace_prefix: str, merge: bool = False) -> None:
    """同一天同一種紀錄只留一則。
    merge=True（今日完成）：把當天舊事件的明細和這次的合併（去重），筆數重算，不會蓋掉早上的紀錄。
    merge=False（未開立發票／需人工處理）：內容和當天舊事件一樣就不動（不會每 30 分鐘重複跳通知），有變才換成最新。"""
    day_start = start.astimezone(TZ).replace(hour=0, minute=0, second=0, microsecond=0)
    old = service.events().list(calendarId=calendar_id, timeMin=day_start.isoformat(),
                                timeMax=(day_start + timedelta(days=1)).isoformat(), q=replace_prefix,
                                singleEvents=True, maxResults=50).execute().get("items", [])
    old = [e for e in old if str(e.get("summary", "")).startswith(replace_prefix)]
    if merge:
        lines = []
        for event in old:
            lines += [x for x in str(event.get("description", "")).splitlines() if x.strip()]
        lines += [x for x in description.splitlines() if x.strip()]
        lines = list(dict.fromkeys(lines))
        description = "\n".join(lines)
        summary = re.sub(r"\d+ 筆", f"{len(lines)} 筆", summary, count=1)
    elif any(str(e.get("description", "")) == description for e in old):
        return
    for event in old:
        service.events().delete(calendarId=calendar_id, eventId=event["id"]).execute()
    body = {
        "summary": summary,
        "description": description,
        "start": {"dateTime": start.isoformat(), "timeZone": "Asia/Taipei"},
        "end": {"dateTime": (start + timedelta(minutes=30)).isoformat(), "timeZone": "Asia/Taipei"},
        "reminders": {"useDefault": False,
                      "overrides": [{"method": "popup", "minutes": m} for m in reminder_minutes]},
    }
    service.events().insert(calendarId=calendar_id, body=body, sendUpdates="none").execute()


def write_calendar(result: dict, now: datetime | None = None, service_factory=_calendar_service) -> list[str]:
    """寫行事曆；失敗只回報，不影響對帳結果。回傳要印出的訊息（不含個資）。"""
    now = now or datetime.now(TZ)
    events = build_calendar_events(result, now)
    if not events:
        return []
    preferred = os.getenv("ATM_CALENDAR_ID", "").strip()
    calendar_ids = (preferred,) if preferred else CALENDAR_IDS
    messages = []
    for kwargs in events:
        title = kwargs["replace_prefix"]
        last_error = None
        for calendar_id in calendar_ids:
            try:
                _insert_event(service_for(service_factory, calendar_id), calendar_id, **kwargs)
                messages.append(f"已記入行事曆 {calendar_id}：{title}")
                last_error = None
                break
            except Exception as exc:
                last_error = exc
        if last_error is not None:
            messages.append(f"⚠️ 記入行事曆失敗（{title}）：{last_error}")
    return messages


def _log(status: str, message: str) -> None:
    try:
        from shared.execution_log_service import log_execution

        log_execution(function_name=TOOL_NAME, area="台北／台中", run_type="排程",
                      status=status, message=message)
    except Exception:  # 記錄失敗不影響對帳
        pass


def run(env: str = "prod") -> int:
    from memo_system import atm, memo

    memo.set_env(env)
    detail = io.StringIO()
    error = None
    result: dict = {}
    try:
        with contextlib.redirect_stdout(detail):
            result = atm.run_scheduled_match_and_reconcile()
    except Exception as exc:
        error = exc
        result = getattr(exc, "results", {}) or {}
    lines = summary_lines(result)
    with contextlib.redirect_stdout(io.StringIO()):
        lines += write_calendar(result)
    for line in lines:
        print(f"{'✅' if not error else '•'} {line}", flush=True)
    if error:
        print(f"❌ {TOOL_NAME}失敗：{error}", flush=True)
        _log("失敗", f"{error}\n" + "；".join(lines))
        return 1
    failed = any(((item or {}).get("reconcile") or {}).get("failed") for item in result.values()) \
        or bool(collect(result, "no_invoice"))
    _log("有失敗" if failed else "成功", "；".join(lines))
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=TOOL_NAME)
    parser.add_argument("--env", default="prod", choices=["prod", "dev"])
    args = parser.parse_args(argv)
    return run(args.env)


if __name__ == "__main__":
    sys.exit(main())
