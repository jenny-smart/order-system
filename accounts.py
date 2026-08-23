# -*- coding: utf-8 -*-
"""統一本機私密設定入口；Repo 內不保存帳密或 API Key。"""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path
from types import ModuleType
from typing import Any


LOCAL_ACCOUNTS_FILE = Path(
    os.getenv("LEMON_ACCOUNTS_FILE", str(Path.home() / "lemon" / "accounts.py"))
).expanduser()

_DEFAULT_ACCOUNTS = {
    "台北": {"folder": "01.台北專員", "address_keywords": ["台北市", "新北市"]},
    "台中": {"folder": "02.台中專員", "address_keywords": ["台中"]},
    "桃園": {"folder": "04.桃園專員", "address_keywords": ["桃園", "新北市"]},
    "新竹": {"folder": "05.新竹專員", "address_keywords": ["新竹"]},
    "高雄": {"folder": "0.高雄專員", "address_keywords": ["高雄", "台南"]},
}
_REGION_ENV = {
    "台北": ("TAIPEI_EMAIL", "TAIPEI_PASSWORD"),
    "台中": ("TAICHUNG_EMAIL", "TAICHUNG_PASSWORD"),
    "桃園": ("TAOYUAN_EMAIL", "TAOYUAN_PASSWORD"),
    "新竹": ("HSINCHU_EMAIL", "HSINCHU_PASSWORD"),
    "高雄": ("KAOHSIUNG_EMAIL", "KAOHSIUNG_PASSWORD"),
}


def _load_local_module() -> ModuleType | None:
    try:
        if not LOCAL_ACCOUNTS_FILE.is_file():
            return None
        if LOCAL_ACCOUNTS_FILE.resolve() == Path(__file__).resolve():
            return None
        spec = importlib.util.spec_from_file_location(
            "_lemon_local_accounts",
            LOCAL_ACCOUNTS_FILE,
        )
        if spec is None or spec.loader is None:
            return None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    except Exception:
        return None


_LOCAL_MODULE = _load_local_module()
_LOCAL_ACCOUNTS = getattr(_LOCAL_MODULE, "ACCOUNTS", {}) if _LOCAL_MODULE else {}


def _local_value(name: str, default: Any = "") -> Any:
    value = os.getenv(name)
    if value is not None and str(value).strip():
        return value
    return getattr(_LOCAL_MODULE, name, default) if _LOCAL_MODULE else default


ACCOUNTS = {}
for _region, _defaults in _DEFAULT_ACCOUNTS.items():
    _local = _LOCAL_ACCOUNTS.get(_region, {}) if isinstance(_LOCAL_ACCOUNTS, dict) else {}
    _email_env, _password_env = _REGION_ENV[_region]
    ACCOUNTS[_region] = {
        **_defaults,
        **(_local if isinstance(_local, dict) else {}),
        "email": os.getenv(_email_env, "").strip()
        or str((_local or {}).get("email", "")).strip(),
        "password": os.getenv(_password_env, "").strip()
        or str((_local or {}).get("password", "")).strip(),
    }


GOOGLE_MAPS_API_KEY = str(_local_value("GOOGLE_MAPS_API_KEY", "") or "").strip()
GOOGLE_SERVICE_ACCOUNT_FILE = str(
    _local_value("GOOGLE_SERVICE_ACCOUNT_FILE", "google_service_account.json")
    or "google_service_account.json"
).strip()
