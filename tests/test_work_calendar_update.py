import json
from datetime import date, timedelta

import tw_holidays


def _year_rows(year):
    day, rows = date(year, 1, 1), []
    while day.year == year:
        rows.append({"date": day.strftime("%Y%m%d"), "isHoliday": day.weekday() >= 5 or day == date(year, 1, 1)})
        day += timedelta(days=1)
    return rows


def test_update_adds_next_year_and_keeps_existing(tmp_path):
    path = tmp_path / "cal.json"
    path.write_text(json.dumps({"source": "x", "days": {"2027-12-31": True}}), encoding="utf-8")
    assert tw_holidays.update_calendar_file(2028, path, rows=_year_rows(2028)) is True
    days = json.loads(path.read_text(encoding="utf-8"))["days"]
    assert days["2027-12-31"] is True and days["2028-01-01"] is True and days["2028-01-03"] is False
    assert len([k for k in days if k.startswith("2028-")]) == 366
    assert tw_holidays.update_calendar_file(2028, path, rows=[]) is False   # 已有完整一年不動


def test_update_rejects_incomplete_year(tmp_path):
    path = tmp_path / "cal.json"
    path.write_text(json.dumps({"days": {}}), encoding="utf-8")
    try:
        tw_holidays.update_calendar_file(2028, path, rows=_year_rows(2028)[:100])
    except RuntimeError as exc:
        assert "不完整" in str(exc)
    else:
        raise AssertionError("不完整應該報錯")


def test_offline_falls_back_to_local_json(tmp_path, monkeypatch):
    path = tmp_path / "cal.json"
    path.write_text(json.dumps({"days": {"2029-02-12": True, "2029-02-10": False}}), encoding="utf-8")
    monkeypatch.setattr(tw_holidays, "CALENDAR_FILE", path)
    monkeypatch.setattr(tw_holidays, "_fetch", lambda year, timeout=10: None)
    monkeypatch.setattr(tw_holidays, "local_calendar",
                        lambda year, p=None, _f=tw_holidays.local_calendar: _f(year, path))
    monkeypatch.setitem(tw_holidays.__dict__, "_CACHE", {})
    assert tw_holidays.is_workday(date(2029, 2, 12)) is False       # json 寫放假（線上抓不到）
    assert tw_holidays.is_workday(date(2029, 2, 13)) is True
    holidays, makeup, official = tw_holidays.calendar_for(2029)
    assert official and makeup == {date(2029, 2, 10)}
