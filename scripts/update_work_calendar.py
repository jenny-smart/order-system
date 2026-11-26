"""每年 12/25 起：把隔年政府辦公日曆補進 config/taiwan_work_calendar.json。

  python scripts/update_work_calendar.py            # 隔年（台北時間）
  python scripts/update_work_calendar.py --year 2028
已有完整一年就不動；抓不到或不完整時結束碼 1（Actions 顯示失敗，隔天排程再試）。
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import tw_holidays  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--year", type=int, default=0)
    args = parser.parse_args()
    year = args.year or datetime.now(ZoneInfo("Asia/Taipei")).year + 1
    try:
        changed = tw_holidays.update_calendar_file(year)
    except RuntimeError as exc:
        print(f"❌ {exc}", flush=True)
        return 1
    print(f"{'✅ 已補上' if changed else '✔ 已有'} {year} 年辦公日曆：{tw_holidays.CALENDAR_FILE}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
