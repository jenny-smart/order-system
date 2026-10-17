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


def test_routes_categories():
    from memo_system import atm
    assert atm._atm_root_rule("新竹") == ("名冊薪資", 1)
    assert atm._atm_root_rule("高雄") == ("內勤工作表單", 0)
    assert change_order._change_root_category("桃園") == "服務異動"
    assert change_order._change_root_category("台北") == "內勤工作表單"


def test_half_width_parentheses_are_part_of_file_name():
    assert year_roots._fill("{YYYY}桃園專員薪資(外場)", 2026) == "2026桃園專員薪資(外場)"
    assert year_roots._fill("{YYYY}台北營業額總表（捷徑）", 2026) == "2026台北營業額總表"


def test_locate_ignores_mode_and_reports(monkeypatch):
    header = [["t"], ["d"], ["類別"]]
    row = ["內勤工作表單", "台北", "R", "", "{YYYY}x", "", "{YYYY}台北內勤工作表單｜{YYYY}舊名", "2026", "", "", "原設定", ""]
    written = []
    roots = year_roots.YearRoots(header + [row], lambda: "drive", lambda r, t: written.append((r, t)))
    monkeypatch.setattr(year_roots, "resolve", lambda drive, rule, year, area, idx: ("ID", "2027x/2027台北內勤工作表單"))
    assert roots.locate("內勤工作表單", "台北", 2027) == "ID"
    assert "使用根目錄" in written[-1][1]
    import pytest
    with pytest.raises(FileNotFoundError):
        roots.locate("內勤工作表單", "火星", 2027)


def test_resolve_tries_alternative_names():
    class Drive:
        pass
    rule = year_roots.parse_rules([["t"], ["d"], ["類別"],
        ["服務異動", "桃園", "R", "", "{YYYY}f", "03.桃園", "{YYYY}服務異動-桃園｜{YYYY}桃園退款及儲值金異動", "2026"]])[0]
    tree = {("R", "2026f"): "F1", ("F1", "03.桃園"): "F2", ("F2", "2026桃園退款及儲值金異動"): "FILE"}

    def child(drive, parent, name, folder):
        if (parent, name) not in tree:
            raise FileNotFoundError(name)
        return {"id": tree[(parent, name)]}

    import unittest.mock as m
    with m.patch.object(year_roots, "_child", child):
        assert year_roots.resolve(Drive(), rule, 2026, "桃園")[0] == "FILE"


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
