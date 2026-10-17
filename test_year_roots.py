from datetime import date

import tw_holidays
import year_roots
from memo_system import change_order


def test_compare_mode_keeps_configured(monkeypatch):
    class Roots:
        def choose(self, category, area, year, configured, file_index=0):
            return configured

    monkeypatch.setattr(year_roots, "get_year_roots", lambda: Roots())
    assert year_roots.choose_file_id("內勤工作表單", "台北", "X") == "X"


def test_routes_categories(monkeypatch):
    calls = []
    monkeypatch.setattr(year_roots, "choose_file_id",
                        lambda cat, area, cid, file_index=0: calls.append((cat, area, file_index)) or cid)
    change_order._year_root_id("CHANGE", "桃園", "A")
    change_order._year_root_id("CHANGE", "台北", "B")
    from memo_system import atm
    atm._year_root_id("ATM", "新竹", "C")
    atm._year_root_id("ATM", "高雄", "D")
    assert calls == [("服務異動", "桃園", 0), ("內勤工作表單", "台北", 0),
                     ("名冊薪資", "新竹", 1), ("內勤工作表單", "高雄", 0)]


def test_no_settings_returns_configured(monkeypatch):
    monkeypatch.setattr(year_roots, "get_year_roots", lambda: None)
    assert year_roots.choose_file_id("內勤工作表單", "台北", " X ") == "X"


def test_workday_uses_calendar_then_builtin(monkeypatch):
    tw_holidays._CACHE.clear()
    monkeypatch.setattr(tw_holidays, "_fetch",
                        lambda year, timeout=10: [{"date": "20270105", "isHoliday": True}] if year == 2027 else None)
    assert not change_order._is_workday(date(2027, 1, 5))
    assert change_order._is_workday(date(2027, 1, 6))
    assert not change_order._is_workday(date(2026, 9, 25))  # 抓不到 2026 日曆時用內建清單
