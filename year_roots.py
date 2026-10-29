"""（與 tool-system tools/common/year_roots.py 相同邏輯）年度根目錄設定：依「根目錄／年度資料夾／子資料夾／檔名」找當年度檔，並可切換模式。

設定放在主控表（Jenny's Lemonhometools）的「年度根目錄設定」分頁，三個系統共用。
第 3 列為標題，第 4 列起每列一條規則：
  類別、地區、根目錄ID、根目錄名稱、年度資料夾、子資料夾、檔名、適用起年、使用系統／功能、備註、模式、最近比對結果

K 欄「模式」：
  原設定：只用原本各設定工作表的 ID（跟改版前一樣）。
  比對：  仍用原設定，但同時依根目錄找一次，把結果寫在 L 欄（一致／不一致／找不到）。
  根目錄：改用根目錄找到的檔；找不到時退回原設定，並在 L 欄註明。
適用起年之前的年度一律用原設定。

所有錯誤都不會中斷原本流程：讀不到設定表、找不到資料夾時一律回傳原設定的 ID。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable, Dict, List, Optional, Tuple

ROOT_SHEET = "年度根目錄設定"
HEADER_ROW = 3
FOLDER_MIME = "application/vnd.google-apps.folder"
SHORTCUT_MIME = "application/vnd.google-apps.shortcut"
TZ = timezone(timedelta(hours=8))

MODE_ORIGINAL = "原設定"
MODE_COMPARE = "比對"
MODE_ROOT = "根目錄"

_EMPTY = {"", "—", "-", "－"}
_ALL_AREAS = {"共用", "各地區", "全區"}


@dataclass
class Rule:
    row: int
    category: str
    areas: List[str]
    root_id: str
    year_folder: str
    sub_folder: str
    file_names: List[str]
    since_year: int
    mode: str
    results: Dict[str, str] = None  # L 欄：{「地區 年度」: 該行文字}，每個地區一行


def taipei_year() -> int:
    return datetime.now(TZ).year


def _clean(text: str) -> str:
    """去掉全形括號說明，例如「{YYYY}台北營業額總表（捷徑）」→「{YYYY}台北營業額總表」。
    半形括號是檔名的一部分（例如「2026桃園專員薪資(外場)」），保留。"""
    return re.sub(r"（.*?）", "", str(text or "")).strip()


# 檔名的地區舊稱：找不到時再試（2026 年家電區的財報叫「電器2026財報」，其他年度用「家電」）
_AREA_OLD_NAMES = {"家電": ("電器",)}


def _fill(template: str, year: int, area: str = "") -> str:
    return _clean(template).replace("{YYYY}", str(year)).replace("{地區}", area)


def _norm(name: str) -> str:
    return re.sub(r"\s+", "", str(name or "")).replace("_", "-")


def parse_rules(values: List[List[str]]) -> List[Rule]:
    rules: List[Rule] = []
    for offset, row in enumerate(values[HEADER_ROW:], start=HEADER_ROW + 1):
        cell = lambda i: str(row[i]).strip() if i < len(row) else ""  # noqa: E731
        if not cell(0) or not cell(2):
            continue
        try:
            since = int(cell(7) or 0)
        except ValueError:
            since = 0
        rules.append(Rule(
            row=offset,
            category=cell(0),
            areas=[a for a in re.split(r"[／/、,，]", cell(1)) if a.strip()],
            root_id=cell(2),
            year_folder="" if cell(4) in _EMPTY or cell(4).startswith("—") else cell(4),
            sub_folder="" if cell(5) in _EMPTY or cell(5).startswith("—") else cell(5),
            file_names=[] if cell(6) in _EMPTY or cell(6).startswith("—") else
            [n for n in (s.strip() for s in _clean(cell(6)).split("；")) if n],
            since_year=since,
            mode=cell(10) or MODE_ORIGINAL,
            results=_parse_results(cell(11)),
        ))
    return rules


def _parse_results(text: str) -> Dict[str, str]:
    """L 欄每行格式：「YYYY/MM/DD HH:MM 地區 年度 結果…」，以「地區 年度」為鍵。"""
    results: Dict[str, str] = {}
    for line in str(text or "").splitlines():
        parts = line.split()
        if len(parts) >= 4:
            results[f"{parts[2]} {parts[3]}"] = line
    return results


def row_status(rule: Rule) -> str:
    """整列比對狀態：全部一致／有不一致／尚未比對。"""
    lines = list((rule.results or {}).values())
    if not lines:
        return "尚未比對"
    bad = ("不一致", "找不到", "空白", "改用原設定")
    if any(any(b in line for b in bad) for line in lines):
        return "有不一致"
    if all(line.endswith("一致") or "使用根目錄" in line for line in lines):
        return "全部一致"
    return "有不一致"


def find_rule(rules: List[Rule], category: str, area: str) -> Optional[Rule]:
    fallback = None
    for rule in rules:
        if rule.category != category:
            continue
        if area in rule.areas:
            return rule
        if fallback is None and (_ALL_AREAS & set(rule.areas) or not rule.areas):
            fallback = rule
    return fallback


def _children(drive, parent_id: str) -> List[Dict]:
    items, token = [], None
    while True:
        res = drive.files().list(
            q=f"'{parent_id}' in parents and trashed=false",
            fields="nextPageToken,files(id,name,mimeType,shortcutDetails)",
            pageSize=1000, pageToken=token,
            supportsAllDrives=True, includeItemsFromAllDrives=True,
        ).execute()
        items.extend(res.get("files", []))
        token = res.get("nextPageToken")
        if not token:
            return items


def _child(drive, parent_id: str, name: str, folder: bool) -> Dict:
    """在 parent 底下找名稱完全相同的項目（不吃「的副本」等相似名稱）。"""
    target = _norm(name)
    hits = []
    for item in _children(drive, parent_id):
        if _norm(item.get("name")) != target:
            continue
        mime = item.get("mimeType", "")
        if mime == SHORTCUT_MIME:  # 捷徑：改用它指向的檔案／資料夾
            details = item.get("shortcutDetails") or {}
            if not details.get("targetId"):
                continue
            mime = details.get("targetMimeType", "")
            item = {**item, "id": details["targetId"], "mimeType": mime}
        if folder != (mime == FOLDER_MIME):
            continue
        if any(h["id"] == item["id"] for h in hits):  # 原檔與指向它的捷徑只算一個
            continue
        hits.append(item)
    if not hits:
        raise FileNotFoundError(f"找不到「{name}」")
    if len(hits) > 1:
        raise RuntimeError(f"「{name}」有 {len(hits)} 個同名項目")
    return hits[0]


def resolve(drive, rule: Rule, year: int, area: str = "", file_index: int = 0) -> Tuple[str, str]:
    """依規則找出 year 年度的檔案，回傳 (檔案ID, 路徑說明)。"""
    if not rule.file_names or rule.file_names[0].startswith("工作表"):
        # 固定檔（例如行銷費用總管理）：根目錄 ID 本身就是檔案
        return rule.root_id, "固定檔"
    node = rule.root_id
    path = []
    for template in (rule.year_folder, rule.sub_folder):
        if not template:
            continue
        name = _fill(template, year, area)
        node = _child(drive, node, name, folder=True)["id"]
        path.append(name)
    entry = rule.file_names[min(file_index, len(rule.file_names) - 1)]
    # 同一個檔可登記多種寫法，用「｜」分隔，依序找（例如 2027 起改名的新檔名｜2026 的舊檔名）
    candidates = []
    for template in (t.strip() for t in entry.split("｜") if t.strip()):
        candidates.append(_fill(template, year, area))
        if "{地區}" in template:
            candidates += [_fill(template, year, old) for old in _AREA_OLD_NAMES.get(area, ())]
    for name in candidates:
        try:
            found = _child(drive, node, name, folder=False)
        except FileNotFoundError:
            continue
        path.append(name)
        return found["id"], "/".join(path)
    raise FileNotFoundError(f"找不到「{'」或「'.join(candidates)}」")


class YearRoots:
    """讀一次設定表後重複使用；writer(row, text) 用來把比對結果寫回 L 欄。"""

    def __init__(self, values: List[List[str]], drive_factory: Callable[[], object],
                 writer: Optional[Callable[[int, str], None]] = None, log=print):
        self.rules = parse_rules(values)
        self._drive_factory = drive_factory
        self._drive = None
        self._writer = writer
        self._log = log
        self._written: set = set()
        self._resolved: Dict[tuple, Tuple[str, str]] = {}

    @property
    def drive(self):
        if self._drive is None:
            self._drive = self._drive_factory()
        return self._drive

    def _report(self, rule: Rule, text: str) -> None:
        """text 以「地區 年度」開頭；同一列每個地區保留一行，寫回 L 欄。"""
        key = (rule.row, text)
        if self._writer is None or key in self._written:
            return
        self._written.add(key)
        stamp = datetime.now(TZ).strftime("%Y/%m/%d %H:%M")
        parts = text.split()
        if rule.results is None:
            rule.results = {}
        rule.results[" ".join(parts[:2])] = f"{stamp} {text}"
        try:
            self._writer(rule.row, "\n".join(rule.results[k] for k in sorted(rule.results)))
        except Exception as exc:  # 寫不回去不影響主流程
            self._log(f"⚠ 年度根目錄設定 L{rule.row} 寫入失敗：{exc}")

    def choose(self, category: str, area: str, year: int, configured_id: str,
               file_index: int = 0) -> str:
        """依模式回傳要用的檔案 ID；任何錯誤都退回 configured_id。"""
        configured_id = str(configured_id or "").strip()
        rule = find_rule(self.rules, category, area)
        if rule is None or rule.mode == MODE_ORIGINAL or (rule.since_year and year < rule.since_year):
            return configured_id
        label = f"{area or '共用'} {year}"
        key = (rule.row, year, area, file_index)
        try:
            if key not in self._resolved:
                self._resolved[key] = resolve(self.drive, rule, year, area, file_index)
            found, path = self._resolved[key]
        except Exception as exc:
            if rule.mode == MODE_ROOT:
                self._report(rule, f"{label} 找不到（{exc}），已改用原設定")
            else:
                self._report(rule, f"{label} 找不到：{exc}")
            return configured_id
        if rule.mode == MODE_ROOT:
            self._report(rule, f"{label} 使用根目錄：{path}")
            return found
        if not configured_id:
            self._report(rule, f"{label} 原設定空白；根目錄找到 {path}（{found}）")
        elif found == configured_id:
            self._report(rule, f"{label} 一致")
        else:
            self._report(rule, f"{label} 不一致：根目錄找到 {path}（{found}），原設定 {configured_id}")
        return configured_id


    def locate(self, category: str, area: str, year: int, file_index: int = 0) -> str:
        """只依根目錄找檔（不看模式、不退回原設定）；找不到就丟出錯誤。"""
        rule = find_rule(self.rules, category, area)
        if rule is None:
            raise FileNotFoundError(f"年度根目錄設定沒有「{category}／{area or '共用'}」這一列")
        label = f"{area or '共用'} {year}"
        key = (rule.row, year, area, file_index)
        try:
            if key not in self._resolved:
                self._resolved[key] = resolve(self.drive, rule, year, area, file_index)
        except Exception as exc:
            self._report(rule, f"{label} 找不到：{exc}")
            raise FileNotFoundError(f"年度根目錄找不到「{category}／{area or '共用'}」{year} 年度檔：{exc}") from exc
        found, path = self._resolved[key]
        self._report(rule, f"{label} 使用根目錄：{path}")
        return found


MASTER_SPREADSHEET_ID = "1nNAXy6rvBnGR8ACnqKKzKNA4-UwZtZp47i806EPmR_8"

_INSTANCE: Optional[YearRoots] = None
_LOADED_AT = 0.0
RELOAD_SECONDS = 600  # 常駐程式每 10 分鐘重讀一次，改 K 欄模式不必重啟


def _get_service_account_info() -> dict:
    """自帶一份服務帳號憑證解析，不依賴 orders.py／shared.gsheet（shared.gsheet
    本身又 import orders，一樣會循環帶到整個 orders.py）。ATM 本機排程等
    獨立執行環境沒有部署 orders.py，若在這裡 import orders 會讓整段年度
    根目錄查詢 ModuleNotFoundError，連帶讓呼叫方（例如 ATM 待付款複查）
    整個失敗。內容與 shared/gsheet.py 的 get_service_account_info 一致。"""
    import json
    import os

    try:
        import streamlit as st

        if "gcp_service_account" in st.secrets:
            return dict(st.secrets["gcp_service_account"])
        if "GOOGLE_SERVICE_ACCOUNT" in st.secrets:
            return dict(st.secrets["GOOGLE_SERVICE_ACCOUNT"])
    except Exception:
        pass

    raw_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
    if raw_json:
        return json.loads(raw_json)

    candidate_files = []
    try:
        from accounts import GOOGLE_SERVICE_ACCOUNT_FILE

        if GOOGLE_SERVICE_ACCOUNT_FILE:
            candidate_files.append(GOOGLE_SERVICE_ACCOUNT_FILE)
    except Exception:
        pass
    candidate_files.append("google_service_account.json")

    for fp in candidate_files:
        if fp and os.path.exists(fp):
            with open(fp, "r", encoding="utf-8") as f:
                return json.load(f)

    raise FileNotFoundError(
        "找不到 Google 憑證。請在 Streamlit secrets 設定 gcp_service_account 或 "
        "GOOGLE_SERVICE_ACCOUNT，或提供 GOOGLE_SERVICE_ACCOUNT_JSON，或放置 "
        "google_service_account.json。"
    )


def _master_id() -> str:
    import os

    try:
        import streamlit as st

        value = str(st.secrets.get("MASTER_SPREADSHEET_ID", "") or "").strip()
        if value:
            return value
    except Exception:
        pass
    return os.getenv("MASTER_SPREADSHEET_ID", "").strip() or MASTER_SPREADSHEET_ID


# 部署端可指定找檔用的 Drive 連線（例如 tool-system 用擁有資料夾的 Jenny OAuth；
# 服務帳號看不到沒分享給它的資料夾，會誤判「找不到」）。未指定時用服務帳號。
drive_factory: Optional[Callable[[], object]] = None


def get_year_roots() -> Optional[YearRoots]:
    """orders-system 實例：用服務帳號讀寫主控表、找雲端檔。讀不到設定時回傳 None。"""
    global _INSTANCE, _LOADED_AT
    import time

    if _LOADED_AT and time.time() - _LOADED_AT < RELOAD_SECONDS:
        return _INSTANCE
    try:
        from google.oauth2.service_account import Credentials
        from googleapiclient.discovery import build

        creds = Credentials.from_service_account_info(
            _get_service_account_info(),
            scopes=["https://www.googleapis.com/auth/spreadsheets",
                    "https://www.googleapis.com/auth/drive.readonly"],
        )
        sheets = build("sheets", "v4", credentials=creds, cache_discovery=False)
        master_id = _master_id()
        values = sheets.spreadsheets().values().get(
            spreadsheetId=master_id, range=f"'{ROOT_SHEET}'!A1:L"
        ).execute().get("values", [])

        def writer(row: int, text: str) -> None:
            sheets.spreadsheets().values().update(
                spreadsheetId=master_id, range=f"'{ROOT_SHEET}'!L{row}",
                valueInputOption="RAW", body={"values": [[text]]},
            ).execute()

        _INSTANCE = YearRoots(
            values, drive_factory or (lambda: build("drive", "v3", credentials=creds, cache_discovery=False)),
            writer,
        )
        _LOADED_AT = time.time()
    except Exception as exc:
        print(f"⚠ 讀取「{ROOT_SHEET}」失敗，沿用原設定：{exc}", flush=True)
        _LOADED_AT = time.time()
        return _INSTANCE
    return _INSTANCE


def choose_file_id(category: str, area: str, configured_id: str,
                   year: Optional[int] = None, file_index: int = 0) -> str:
    """依年度根目錄設定的模式回傳檔案 ID，失敗一律回傳原設定。"""
    roots = get_year_roots()
    if roots is None:
        return str(configured_id or "").strip()
    try:
        return roots.choose(category, area, year or taipei_year(), configured_id, file_index)
    except Exception as exc:
        print(f"⚠ 年度根目錄比對失敗，沿用原設定：{exc}", flush=True)
        return str(configured_id or "").strip()


def root_file_id(category: str, area: str, year: Optional[int] = None, file_index: int = 0) -> str:
    """只用年度根目錄找檔（不讀 secrets／原設定 ID）；設定讀不到或找不到檔都會報錯。"""
    roots = get_year_roots()
    if roots is None:
        raise RuntimeError(f"讀不到主控表「{ROOT_SHEET}」，無法依根目錄找檔")
    return roots.locate(category, area, year or taipei_year(), file_index)
