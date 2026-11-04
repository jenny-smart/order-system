"""週末／例假日服務提醒排程：休假前 2 天 11:00 執行日與查詢區間。"""
from datetime import date, timedelta
from unittest.mock import patch

from shared import weekend_reminder_schedule as sched


def _calendar(off_weekdays=(), workdays=(), start=date(2026, 11, 1), days=120):
    """週六日放假；off_weekdays 為平日假日，workdays 為週末補班日。"""
    cal = {}
    for offset in range(days):
        day = start + timedelta(days=offset)
        cal[day] = (day.weekday() >= 5 or day in off_weekdays) and day not in workdays
    return cal


def test_normal_weekend_runs_on_thursday():
    cal = _calendar()
    assert sched.blocks_due(date(2026, 11, 5), cal) == [(date(2026, 11, 7), date(2026, 11, 8))]
    assert sched.blocks_due(date(2026, 11, 4), cal) == []
    assert sched.blocks_due(date(2026, 11, 6), cal) == []


def test_friday_holiday_moves_run_to_wednesday_and_covers_whole_block():
    cal = _calendar(off_weekdays={date(2026, 12, 25)})
    assert sched.blocks_due(date(2026, 12, 23), cal) == [(date(2026, 12, 25), date(2026, 12, 27))]
    assert sched.blocks_due(date(2026, 12, 24), cal) == []


def test_monday_holiday_extends_block_but_keeps_thursday():
    cal = _calendar(off_weekdays={date(2026, 11, 16)})
    assert sched.blocks_due(date(2026, 11, 12), cal) == [(date(2026, 11, 14), date(2026, 11, 16))]


def test_midweek_holiday_two_days_before_on_weekend_moves_to_previous_workday():
    # 週二假日：前 2 天是週日 → 改週五執行；週五同時也不是週末的執行日。
    cal = _calendar(off_weekdays={date(2026, 11, 17)})
    assert sched.blocks_due(date(2026, 11, 13), cal) == [(date(2026, 11, 17), date(2026, 11, 17))]
    assert sched.blocks_due(date(2026, 11, 12), cal) == [(date(2026, 11, 14), date(2026, 11, 15))]


def test_makeup_saturday_is_workday():
    cal = _calendar(workdays={date(2026, 11, 21)})
    assert sched.blocks_due(date(2026, 11, 20), cal) == [(date(2026, 11, 22), date(2026, 11, 22))]
    assert sched.blocks_due(date(2026, 11, 19), cal) == []


def test_bundled_office_calendar_lunar_new_year_2027():
    cal = sched.load_work_calendar()
    assert sched.blocks_due(date(2027, 2, 2), cal) == [(date(2027, 2, 4), date(2027, 2, 10))]


def test_next_run_finds_upcoming_day():
    cal = _calendar()
    assert sched.next_run(date(2026, 11, 6), cal)[0] == date(2026, 11, 12)


def test_run_skips_when_not_due():
    with patch("function.weekend_reminders.find_paid_weekend_orders") as query:
        result = sched.run(today=date(2026, 11, 4), calendar=_calendar())
    assert result["due"] is False
    query.assert_not_called()


def test_run_saves_only_new_paid_rows():
    orders_found = [{"order_no": "LC1", "service_date": "2026-11-07", "order_status": "已付款", "message": "m"}]
    merged = [
        {"資料狀態": "新增", "訂單編號": "LC1", "服務日期": "2026-11-07"},
        {"資料狀態": "已存在", "訂單編號": "LC0", "服務日期": "2026-11-08"},
    ]
    accounts = {"台北": {"email": "a@example.com", "password": "pw"}}
    with patch("accounts.ACCOUNTS", accounts), \
            patch("function.weekend_reminders.find_paid_weekend_orders",
                  return_value=(orders_found, {"paid": 1, "hit_page_limit": False})) as query, \
            patch("function.weekend_reminders.load_tracking_rows", return_value=[]), \
            patch("function.weekend_reminders.merge_tracking_rows", return_value=merged), \
            patch("function.weekend_reminders.save_tracking_rows", return_value=1) as save, \
            patch.object(sched, "_log"):
        result = sched.run(today=date(2026, 11, 5), calendar=_calendar())
    assert query.call_args.args[3:] == ("2026-11-07", "2026-11-08")
    assert save.call_args.args[0] == [merged[0]]
    assert result["new"] == 1 and result["saved"] == 1
