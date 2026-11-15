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


def test_locate_reconnects_once_after_broken_pipe():
    from year_roots import YearRoots

    values = [[], [], ["類別"], ["內勤工作表單", "高雄", "ROOT", "", "{YYYY}專員承攬服務費", "05.高雄專員",
                                 "{YYYY}高雄內勤工作表單", "2026", "", "", "根目錄"]]
    tree = {"ROOT": [{"id": "Y", "name": "2026專員承攬服務費", "mimeType": "application/vnd.google-apps.folder"}],
            "Y": [{"id": "K", "name": "05.高雄專員", "mimeType": "application/vnd.google-apps.folder"}],
            "K": [{"id": "F", "name": "2026高雄內勤工作表單", "mimeType": "application/vnd.google-apps.spreadsheet"}]}

    class Drive:
        def __init__(self, broken):
            self.broken = broken

        def files(self):
            return self

        def list(self, q, **_):
            parent = q.split("'")[1]
            broken = self.broken

            class Req:
                def execute(self_inner):
                    if broken:
                        raise BrokenPipeError(32, "Broken pipe")
                    return {"files": tree.get(parent, [])}
            return Req()

    made = []

    def factory():
        made.append(1)
        return Drive(broken=len(made) == 1)

    roots = YearRoots(values, factory, log=lambda *_: None)
    assert roots.locate("內勤工作表單", "高雄", 2026) == "F"
    assert len(made) == 2


def test_locate_finds_year_folder_shared_directly_when_root_not_visible():
    from year_roots import YearRoots

    values = [[], [], ["類別"], ["內勤工作表單", "高雄", "ROOT", "", "{YYYY}專員承攬服務費", "05.高雄專員",
                                 "{YYYY}高雄內勤工作表單", "2026", "", "", "根目錄"]]
    folder = "application/vnd.google-apps.folder"
    # 服務帳號看不到 ROOT：列 ROOT 底下回空；但 2026 資料夾有直接分享給它
    tree = {"ROOT": [],
            "Y": [{"id": "K", "name": "05.高雄專員", "mimeType": folder}],
            "K": [{"id": "F", "name": "2026高雄內勤工作表單", "mimeType": "application/vnd.google-apps.spreadsheet"}]}
    shared = [{"id": "Y", "name": "2026專員承攬服務費", "parents": ["ROOT"]},
              {"id": "OTHER", "name": "2026專員承攬服務費", "parents": ["ELSEWHERE"]}]

    class Drive:
        def files(self):
            return self

        def list(self, q, **_):
            class Req:
                def execute(self_inner):
                    if q.startswith("name = "):
                        return {"files": shared}
                    return {"files": tree.get(q.split("'")[1], [])}
            return Req()

    roots = YearRoots(values, Drive, log=lambda *_: None)
    assert roots.locate("內勤工作表單", "高雄", 2026) == "F"


def test_shared_folder_fallback_rejects_ambiguous_names():
    import pytest
    from year_roots import _find_shared_folder

    class Drive:
        def files(self):
            return self

        def list(self, **_):
            class Req:
                def execute(self_inner):
                    return {"files": [{"id": "A", "name": "2026專員承攬服務費"}, {"id": "B", "name": "2026專員承攬服務費"}]}
            return Req()

    with pytest.raises(FileNotFoundError):
        _find_shared_folder(Drive(), "ROOT", "2026專員承攬服務費")
