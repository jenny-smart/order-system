# -*- coding: utf-8 -*-
"""Google Sheets 憑證/連線與讀寫工具，供 orders.py／quick_order.py 共用。"""

import os
import json

import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

from env import GOOGLE_SHEET_ID, GOOGLE_SERVICE_ACCOUNT_FILE

import orders


def get_service_account_info():
    if orders.st is not None:
        try:
            if "gcp_service_account" in orders.st.secrets:
                return dict(orders.st.secrets["gcp_service_account"])
            if "GOOGLE_SERVICE_ACCOUNT" in orders.st.secrets:
                return dict(orders.st.secrets["GOOGLE_SERVICE_ACCOUNT"])
        except Exception:
            pass

    raw_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
    if raw_json:
        try:
            return json.loads(raw_json)
        except Exception as e:
            raise Exception(f"GOOGLE_SERVICE_ACCOUNT_JSON 不是合法 JSON：{e}")

    candidate_files = []
    if GOOGLE_SERVICE_ACCOUNT_FILE:
        candidate_files.append(GOOGLE_SERVICE_ACCOUNT_FILE)
    candidate_files.append("google_service_account.json")

    for fp in candidate_files:
        if fp and os.path.exists(fp):
            with open(fp, "r", encoding="utf-8") as f:
                return json.load(f)

    raise FileNotFoundError(
        "找不到 Google 憑證。請在 Streamlit secrets 設定 gcp_service_account 或 GOOGLE_SERVICE_ACCOUNT，"
        "或提供 GOOGLE_SERVICE_ACCOUNT_JSON，或放置 google_service_account.json。"
    )


def build_gsheet_client():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    service_account_info = get_service_account_info()
    creds = Credentials.from_service_account_info(service_account_info, scopes=scopes)
    return gspread.authorize(creds)


def load_worksheet(sheet_name):
    client = build_gsheet_client()
    sh = client.open_by_key(GOOGLE_SHEET_ID)
    ws = sh.worksheet(sheet_name)

    values = ws.get_all_values()
    if not values:
        raise Exception(f"工作表 {sheet_name} 沒有資料")

    headers = values[0]
    rows = values[1:]
    df = pd.DataFrame(rows, columns=headers)
    df["__sheet_row__"] = range(2, len(df) + 2)
    return ws, df


def ensure_columns_in_sheet(ws):
    headers = ws.row_values(1)
    required = [
        "簡訊實際服務時間",
        "客人備註",
        "客服備註",
        "訂單編號",
        "結果",
        "原因",
        "沒班表日期",
        "餘額不足未送",
        "確認信",
        "日曆改色結果",
        "日曆改色原因",
        "日曆原色",
        "日曆新色",
        "狀態",
        "服務人員",
        "服務狀態",
        "車馬費",
    ]

    changed = False
    for col in required:
        if col not in headers:
            headers.append(col)
            changed = True

    if changed:
        ws.resize(rows=max(ws.row_count, 1), cols=len(headers))
        ws.update("A1", [headers])

    return headers


def set_customer_notice_clip_style(ws, headers=None, row_numbers=None):
    """
    Google Sheet 顯示規則：
    客服備註內容完整保留，但儲存格視覺上使用「自動裁剪 / CLIP」，
    避免長備註自動換行把列高撐高。
    """
    try:
        headers = headers or ws.row_values(1)
        if "客服備註" not in headers:
            return

        col_index = headers.index("客服備註")  # 0-based
        sheet_id = ws.id

        service_account_info = get_service_account_info()
        creds = Credentials.from_service_account_info(
            service_account_info,
            scopes=["https://www.googleapis.com/auth/spreadsheets"],
        )
        service = build("sheets", "v4", credentials=creds)

        requests_body = [
            {
                "repeatCell": {
                    "range": {
                        "sheetId": sheet_id,
                        "startRowIndex": 1,
                        "startColumnIndex": col_index,
                        "endColumnIndex": col_index + 1,
                    },
                    "cell": {
                        "userEnteredFormat": {
                            "wrapStrategy": "CLIP"
                        }
                    },
                    "fields": "userEnteredFormat.wrapStrategy",
                }
            }
        ]

        # 只固定本次有寫入的資料列，避免長備註撐高列高。
        # row_numbers 是 Google Sheet 的 1-based row number；API 是 0-based index。
        if row_numbers:
            for row_num in sorted(set(int(x) for x in row_numbers if int(x) > 1)):
                requests_body.append(
                    {
                        "updateDimensionProperties": {
                            "range": {
                                "sheetId": sheet_id,
                                "dimension": "ROWS",
                                "startIndex": row_num - 1,
                                "endIndex": row_num,
                            },
                            "properties": {
                                "pixelSize": 21
                            },
                            "fields": "pixelSize",
                        }
                    }
                )

        service.spreadsheets().batchUpdate(
            spreadsheetId=GOOGLE_SHEET_ID,
            body={"requests": requests_body},
        ).execute()

    except Exception as e:
        print(f"設定客服備註欄位自動裁剪失敗: {e}")


def update_sheet_rows(ws, row_results):
    headers = ensure_columns_in_sheet(ws)
    header_index = {h: i + 1 for i, h in enumerate(headers)}
    updates = []

    for row_num, info in row_results.items():
        xyz = orders.finalize_xyz(
            {
                "服務人員": info.get("服務人員", ""),
                "服務狀態": info.get("服務狀態", ""),
                "車馬費": info.get("車馬費", ""),
            },
            fallback_fare=info.get("車馬費", "0"),
        )
        info["服務人員"] = xyz["服務人員"]
        info["服務狀態"] = xyz["服務狀態"]
        info["車馬費"] = xyz["車馬費"]

        for key, value in info.items():
            if key not in header_index:
                continue

            # I欄「狀態」只允許在成功完成流程時寫入「已安排」。
            # 其他空白或非已安排值都不覆蓋原本的「未安排」。
            if key == "狀態" and str(value).strip() != "已安排":
                continue

            updates.append({
                "range": gspread.utils.rowcol_to_a1(row_num, header_index[key]),
                "values": [[("" if value is None else str(value))]],
            })

    if updates:
        ws.batch_update(updates)
        set_customer_notice_clip_style(ws, headers=headers, row_numbers=row_results.keys())
