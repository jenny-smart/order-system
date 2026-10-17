"""ATM 本機排程；設定與辦公日曆皆由檔案讀取，不使用 AI。"""
import argparse
import fcntl
import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


DEFAULT_CONFIG = Path(__file__).resolve().parents[1] / "config" / "atm_schedule.json"


def load_config():
    path = Path(os.getenv("ATM_SCHEDULE_CONFIG", str(DEFAULT_CONFIG))).expanduser()
    config = json.loads(path.read_text(encoding="utf-8"))
    calendar_path = Path(config["calendar_file"])
    if not calendar_path.is_absolute():
        calendar_path = path.parent / calendar_path
    calendar = json.loads(calendar_path.read_text(encoding="utf-8"))
    return config, calendar


def scheduled_slots(config):
    def minutes(value):
        hour, minute = map(int, value.split(":"))
        if not 0 <= hour <= 23 or not 0 <= minute <= 59:
            raise ValueError("排程時間格式錯誤")
        return hour * 60 + minute
    start, end = minutes(config["start"]), minutes(config["end"])
    interval = int(config["interval_minutes"])
    if interval <= 0 or end < start or (end - start) % interval:
        raise ValueError("排程起迄與間隔設定不一致")
    return list(range(start, end + 1, interval))


def skip_reason(now, config, calendar):
    now = now.astimezone(ZoneInfo(config["timezone"]))
    key = now.date().isoformat()
    if key not in calendar["days"]:
        raise RuntimeError(f"缺少 {now.year} 年辦公日曆；請先更新日曆設定")
    if now.weekday() >= 5 or calendar["days"][key]:
        return "週末／國定假日／補假"
    slots = scheduled_slots(config)
    minute = now.hour * 60 + now.minute
    # 關機或睡眠期間錯過的輪次直接略過，不接受喚醒後的延遲補跑。
    if minute not in slots:
        return "非排程分鐘；錯過的輪次不補跑"
    return ""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scheduled-unpaid", action="store_true")
    parser.add_argument("--check", action="store_true", help="只檢查設定與存取權限，不寫入")
    args = parser.parse_args()
    config, calendar = load_config()
    now = datetime.now(ZoneInfo(config["timezone"]))
    if args.check:
        from accounts import ACCOUNTS
        from . import atm, memo
        for region in ("台北", "台中"):
            account = ACCOUNTS[region]
            memo.set_runtime_credentials(account["email"], account["password"])
            with memo.login() as session:
                atm.get_atm_worksheet(region)
            print(f"{region}：登入及工作表存取正常")
        print(f"日曆日期數：{len(calendar['days'])}；每日輪數：{len(scheduled_slots(config))}")
        return
    reason = skip_reason(now, config, calendar)
    if reason:
        print(f"{now.isoformat()} 略過：{reason}")
        return
    # 避免手動補跑與排程同時插入相同訂單。
    lock_path = Path(tempfile.gettempdir()) / "lemonclean-atm-unpaid.lock"
    with lock_path.open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("已有 ATM 同步執行中，略過")
            return
        from .atm import run_scheduled_unpaid_sync
        result = run_scheduled_unpaid_sync(date_until=now.date().isoformat())
        print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
