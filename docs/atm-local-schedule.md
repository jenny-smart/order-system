# ATM 待付款本機排程

台北／台中分別重新登入，訂購日期迄為台灣當日，沿用現有查詢、去重及工作表追加流程。只執行①待付款清單，不執行銀行配對或系統對帳。

時區、起迄與間隔讀取 `config/atm_schedule.json`（亦可用 `ATM_SCHEDULE_CONFIG` 指定檔案）。預設工作日 09:00–18:00 每 30 分鐘，共 19 輪。工作表沿用 ATM Secrets／環境設定／既有 env 設定；帳密與 Google 憑證沿用本機 accounts 設定。相對憑證路徑依帳密設定檔目錄解析。

`config/taiwan_work_calendar.json` 包含 2026–2027 政府行政機關辦公日曆資料（來源：taiwan-holidays 0.2027.0，授權見同目錄 calendar-LICENSE.txt）。週末、假日、補假略過；缺少日期資料時停止並記錄錯誤，不能把未知年份當工作日。2028 年前需更新日曆。

安裝或修改時段後重新載入：`bash scripts/install_atm_local_schedule.sh`。只檢查登入／工作表權限：`python3 -m memo_system.atm_schedule --check`。

安裝程式會將排程所需程式及設定部署至 `~/Library/Application Support/LemonClean/atm-runtime`，避免 macOS 阻擋背景程式存取 Documents。帳密仍讀取原本的本機 accounts 檔案；不在程式內新增工作表連結。修改排程程式或設定後需重新執行安裝，以更新執行副本。可用 `ATM_RUNTIME_DIR` 指定其他背景可存取的目錄。

此排程使用 macOS LaunchAgent，不呼叫 AI。Mac 必須開機、使用者登入並保持喚醒及網路連線。關機或睡眠期間錯過的輪次直接略過，不補跑；程式只在排程指定的分鐘內執行，其他分鐘的延遲喚醒觸發也略過。執行紀錄位於 `~/Library/Logs/lemonclean-atm-unpaid.log`，同時執行以檔案鎖阻擋。
