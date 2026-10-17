# ============================================================
# 部署端備援設定（例如 tool-system 的 GitHub 排程，沒有 Streamlit secrets）。
#
# orders-system 本身一律讀 st.secrets／環境變數；部署端若沒有這些設定，
# 可在 import memo_system 之前或之後註冊下面兩個函式：
#   region_sheet(kind, region) -> {"spreadsheet_id", "gid", "worksheet_title"} 或 None
#       kind = "CHANGE"（清潔異動）或 "ATM"
#   service_account() -> 服務帳號 dict 或 None
#   regions(kind) -> 啟用地區清單（可選）
# 沒有註冊時全部回傳 None，行為與原本完全相同。
# ============================================================
region_sheet = None
service_account = None
regions = None


def lookup_region_sheet(kind: str, region: str):
    if region_sheet is None:
        return None
    try:
        return region_sheet(kind, region) or None
    except Exception:
        return None


def lookup_service_account():
    if service_account is None:
        return None
    try:
        return service_account() or None
    except Exception:
        return None


def lookup_regions(kind: str):
    if regions is None:
        return None
    try:
        return list(regions(kind) or [])
    except Exception:
        return None
