"""從既有成單工作表整理 LINE 通知群組與 Google Sheet 貼上格式。"""
from __future__ import annotations

import re


def parse_row_spec(spec):
    rows = set()
    for part in re.split(r"[,，\s]+", str(spec or "").strip()):
        if not part:
            continue
        if "-" in part:
            start, end = (int(value) for value in part.split("-", 1))
            if start < 2 or end < start:
                raise ValueError(f"列號範圍錯誤：{part}")
            rows.update(range(start, end + 1))
        else:
            row = int(part)
            if row < 2:
                raise ValueError(f"列號錯誤：{part}")
            rows.add(row)
    return rows


def groups_from_dataframe(df, row_spec=""):
    """只取已有訂單編號且非失敗列，依姓名＋地址＋服務類型合併訂單。"""
    wanted = parse_row_spec(row_spec)
    grouped = {}
    for offset, (_, row) in enumerate(df.iterrows(), 2):
        row_no = int(row.get("__sheet_row__", offset) or offset)
        if wanted and row_no not in wanted:
            continue
        order_no = str(row.get("訂單編號", "") or "").strip()
        if not order_no or str(row.get("結果", "") or "").strip() == "失敗":
            continue
        name = str(row.get("姓名", "") or "").strip()
        address = re.sub(r"\s+", "", str(row.get("地址", "") or ""))
        service = str(row.get("購買項目", "") or "").strip()
        key = (name or f"__row_{row_no}", address or f"__row_{row_no}", service)
        item = grouped.setdefault(key, {
            "name": name, "address": str(row.get("地址", "") or "").strip(),
            "service": service, "order_nos": [], "rows": [],
        })
        if order_no not in item["order_nos"]:
            item["order_nos"].append(order_no)
        item["rows"].append(row_no)
    return list(grouped.values())


def results_tsv(results):
    def cell(value):
        text = str(value or "")
        if any(char in text for char in ('\t', '\n', '"')):
            return '"' + text.replace('"', '""') + '"'
        return text

    rows = [["姓名", "地址", "訂單編號", "LINE預約完成通知", "日曆檢查"]]
    for item in results or []:
        if item.get("error"):
            continue
        group = item.get("group") or {}
        rows.append([
            group.get("name"), group.get("address"), item.get("order_no"),
            item.get("text"), item.get("calendar_status", "未檢查（日曆不影響通知產生）"),
        ])
    return "\n".join("\t".join(cell(value) for value in row) for row in rows)
