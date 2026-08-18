# ============================================================
# 檔名：shared/member_service.py
# 功能：會員查詢服務層；提供新模組穩定的會員查詢入口，暫時委派 legacy quick_order。
# 更新時間：2026-08-19
# ============================================================
# -*- coding: utf-8 -*-

"""會員查詢服務。

目前以相容優先：底層仍呼叫 quick_order.quick_lookup_member。
後續可把登入、會員 AJAX、地址資料正規化逐步搬入本模組或 backend_client，
上層功能不需要再次修改呼叫方式。
"""

from __future__ import annotations

import quick_order as _legacy


def lookup_member(
    env_name: str,
    backend_email: str,
    backend_password: str,
    phone: str,
    clean_type_id: str = "1",
) -> dict:
    return _legacy.quick_lookup_member(
        env_name,
        backend_email,
        backend_password,
        phone,
        clean_type_id=clean_type_id,
    )
