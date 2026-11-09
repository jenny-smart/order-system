"""ATM 本機排程執行副本自動更新。"""
import pytest

from memo_system import atm_schedule


def _files(**override):
    data = {p: (b"{}" if p.endswith(".json") else b"x = 1\n") for p in atm_schedule.RUNTIME_FILES}
    data.update(override)
    return data


def test_self_update_writes_only_changed(tmp_path):
    for path, data in _files().items():
        (tmp_path / path).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / path).write_bytes(data)
    remote = _files(**{"memo_system/atm.py": b"x = 2\n"})
    changed = atm_schedule.self_update(tmp_path, fetch=remote.__getitem__)
    assert changed == ["memo_system/atm.py"]
    assert (tmp_path / "memo_system/atm.py").read_bytes() == b"x = 2\n"


def test_self_update_all_or_nothing(tmp_path):
    (tmp_path / "memo_system").mkdir()
    (tmp_path / "memo_system/atm.py").write_bytes(b"old = 1\n")
    remote = _files(**{"memo_system/memo.py": b"def broken(:\n"})
    with pytest.raises(SyntaxError):
        atm_schedule.self_update(tmp_path, fetch=remote.__getitem__)
    assert (tmp_path / "memo_system/atm.py").read_bytes() == b"old = 1\n"
