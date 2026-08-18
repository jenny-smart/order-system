# ============================================================
# 檔名：shared/backend_session_service.py
# 功能：後台 Session／登入／CSRF 統一入口；逐步隔離 orders.py 網路連線邏輯。
# 更新時間：2026-08-19
# ============================================================
# -*- coding: utf-8 -*-
from __future__ import annotations
import requests
import orders as _legacy


def create_logged_in_session(email: str, password: str):
    session = requests.Session()
    if not _legacy.login(session, email, password):
        raise RuntimeError("後台登入失敗，請確認帳號密碼")
    return session


def get_csrf_token(session):
    return _legacy.get_csrf_token(session)
