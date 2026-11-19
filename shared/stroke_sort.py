"""依姓名筆劃排序（台灣習慣：先比姓氏筆劃，再比名字各字筆劃）。

筆劃資料 shared/stroke_counts_tw.txt 由 Unicode Unihan（kTotalStrokes、kRSUnicode）產生，
並把「阝（阜／邑）」算 3 劃、「艹」「辶」算 4 劃，對齊教育部國語辭典的總筆畫（例：陳 11、蔡 15、邱 8）。
檔案內容：U+3400～U+9FFF 每個字一個字元，值為 chr(0x30 + 筆劃數)；查不到為 0。
"""

from functools import lru_cache
from pathlib import Path

_START = 0x3400
_END = 0x9FFF


@lru_cache(maxsize=1)
def _table():
    path = Path(__file__).with_name("stroke_counts_tw.txt")
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def stroke_count(char):
    """單一中文字的筆劃數；非中文或查不到回傳 0。"""
    if not char:
        return 0
    cp = ord(char[0])
    table = _table()
    if _START <= cp <= _END and cp - _START < len(table):
        return ord(table[cp - _START]) - 0x30
    return 0


def name_stroke_key(name):
    """排序用 key：中文姓名依姓氏筆劃→名字各字筆劃；英文等非中文姓名排在中文之後，依字母。"""
    text = str(name or "").strip()
    if not text:
        return (2, (), "")
    counts = tuple(stroke_count(ch) for ch in text)
    if counts[0] == 0:
        return (1, (), text.lower())
    return (0, counts, text)
