#!/bin/bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-$(command -v python3)}"
PYTHON_BIN="$("$PYTHON_BIN" -c 'import sys; print(sys.executable)')"
ACCOUNTS_FILE="${LEMON_ACCOUNTS_FILE:-$HOME/lemon/accounts.py}"
LABEL="com.lemonclean.orders-system.atm-unpaid"
PLIST_PATH="$HOME/Library/LaunchAgents/$LABEL.plist"
LOG_PATH="$HOME/Library/Logs/lemonclean-atm-unpaid.log"

if [ ! -f "$ACCOUNTS_FILE" ]; then
  echo "找不到本機帳密：$ACCOUNTS_FILE"
  exit 1
fi

(
  cd "$REPO_DIR"
  "$PYTHON_BIN" -c "import gspread, requests; from accounts import ACCOUNTS; assert ACCOUNTS['台北']['email'] and ACCOUNTS['台北']['password']; assert ACCOUNTS['台中']['email'] and ACCOUNTS['台中']['password']"
)

mkdir -p "$HOME/Library/LaunchAgents" "$HOME/Library/Logs"

"$PYTHON_BIN" - "$PLIST_PATH" "$REPO_DIR" "$PYTHON_BIN" "$ACCOUNTS_FILE" "$LOG_PATH" <<'PY'
import plistlib
import sys

plist_path, repo_dir, python_bin, accounts_file, log_path = sys.argv[1:]
payload = {
    "Label": "com.lemonclean.orders-system.atm-unpaid",
    "ProgramArguments": [
        python_bin,
        "-m",
        "memo_system.atm",
        "--scheduled-unpaid",
    ],
    "WorkingDirectory": repo_dir,
    "EnvironmentVariables": {
        "LEMON_ACCOUNTS_FILE": accounts_file,
        "PYTHONPATH": repo_dir,
    },
    "StartCalendarInterval": [],
    "StandardOutPath": log_path,
    "StandardErrorPath": log_path,
    "ProcessType": "Background",
}
import os
import json
import shutil
from pathlib import Path
os.chdir(repo_dir)
sys.path.insert(0, repo_dir)
from memo_system.atm_schedule import load_config, scheduled_slots
config, calendar = load_config()
from datetime import datetime
from zoneinfo import ZoneInfo
assert datetime.now(ZoneInfo(config["timezone"])).date().isoformat() in calendar["days"], "請先更新辦公日曆"
# macOS 不允許 LaunchAgent 存取 Documents；使用獨立執行副本。
runtime_dir = Path(os.getenv("ATM_RUNTIME_DIR", str(
    Path.home() / "Library" / "Application Support" / "LemonClean" / "atm-runtime"
))).expanduser().resolve()
runtime_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
runtime_dir.chmod(0o700)
for name in ("memo_system", "config"):
    (runtime_dir / name).mkdir(exist_ok=True)
for name in ("__init__.py", "atm.py", "atm_schedule.py", "memo.py", "env.py"):
    shutil.copy2(Path(repo_dir) / "memo_system" / name, runtime_dir / "memo_system" / name)
shutil.copy2(Path(repo_dir) / "accounts.py", runtime_dir / "accounts.py")
runtime_config = dict(config, calendar_file="taiwan_work_calendar.json")
(runtime_dir / "config" / "atm_schedule.json").write_text(json.dumps(runtime_config, ensure_ascii=False), encoding="utf-8")
(runtime_dir / "config" / "taiwan_work_calendar.json").write_text(json.dumps(calendar, ensure_ascii=False), encoding="utf-8")
secrets = Path(repo_dir) / ".streamlit" / "secrets.toml"
if secrets.is_file():
    (runtime_dir / ".streamlit").mkdir(exist_ok=True, mode=0o700)
    target = runtime_dir / ".streamlit" / "secrets.toml"
    shutil.copy2(secrets, target)
    target.chmod(0o600)
payload["WorkingDirectory"] = str(runtime_dir)
payload["EnvironmentVariables"]["PYTHONPATH"] = str(runtime_dir)
payload["EnvironmentVariables"]["ATM_SCHEDULE_CONFIG"] = str(runtime_dir / "config" / "atm_schedule.json")
payload["StartCalendarInterval"] = [
    {"Hour": slot // 60, "Minute": slot % 60}
    for slot in scheduled_slots(config)
]
with open(plist_path, "wb") as handle:
    plistlib.dump(payload, handle)
PY

launchctl bootout "gui/$UID/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$UID" "$PLIST_PATH"

echo "已安裝 ATM 本機排程：依設定檔執行，週末／國定假日／補假自動略過"
echo "帳密來源：$ACCOUNTS_FILE"
echo "執行記錄：$LOG_PATH"
