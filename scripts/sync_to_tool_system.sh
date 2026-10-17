#!/usr/bin/env bash
# 把 order-system 同步到 tool-system 的 tools/orders_system/（由 .github/workflows/sync-to-tool-system.yml 呼叫）
# 用法：scripts/sync_to_tool_system.sh <order-system 目錄> <tool-system 目錄>
set -euo pipefail
SRC="$1"
DEST="$2/tools/orders_system"
# tool-system 自己維護、不能被覆蓋或刪除的檔案
KEEP=" __init__.py ui.py env.py atm_reconcile.py calendar_notify.py change_order_daily_check.py "

mkdir -p "$DEST"
# 根目錄：刪掉 order-system 已經沒有的舊檔（含舊的 test_*.py），保留 tool-system 專用檔
for f in "$DEST"/*.py; do
  [ -e "$f" ] || continue
  name="$(basename "$f")"
  case "$KEEP" in *" $name "*) continue ;; esac
  if [ ! -f "$SRC/$name" ] || [[ "$name" == test_* ]]; then
    rm -f "$f"
    echo "已移除：$name"
  fi
done
# 根目錄：複製 .py（env.py 由 tool-system 維護、測試不同步）
for f in "$SRC"/*.py; do
  name="$(basename "$f")"
  case "$name" in env.py|test_*) continue ;; esac
  cp "$f" "$DEST/$name"
done
# 套件整個同步；memo_system/env.py 由 tool-system 維護
TMP="$(mktemp -d)"
for pkg in function shared memo_system config; do
  [ -d "$SRC/$pkg" ] || continue
  # 目的端的 env.py（tool-system 維護）先保留，整個資料夾換成來源版本後再放回
  [ -f "$DEST/$pkg/env.py" ] && cp "$DEST/$pkg/env.py" "$TMP/$pkg-env.py"
  rm -rf "${DEST:?}/$pkg"
  cp -R "$SRC/$pkg" "$DEST/$pkg"
  find "$DEST/$pkg" -name '__pycache__' -prune -exec rm -rf {} +
  rm -f "$DEST/$pkg/env.py"
  [ -f "$TMP/$pkg-env.py" ] && cp "$TMP/$pkg-env.py" "$DEST/$pkg/env.py"
done
rm -rf "$TMP"
echo "同步完成：$SRC → $DEST"
