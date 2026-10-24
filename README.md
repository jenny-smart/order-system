# order-system

## 會員手機查詢

查詢依據可選「後台會員連結」「LINE 連結」「純姓名文字」。後台模式解析姓名格內 `/member?keyword=…` 的關鍵字，沿用上方環境查詢，不將後台網址誤當 LINE。沒有連結的列改用姓名並標示；錯誤類型的連結會提示切換依據。

在「E. 會員／客戶管理 → 會員手機查詢」使用：

- 貼上姓名（每行一筆），可在同一行附上 LINE 連結；或貼上 Google Sheet 網址，按「讀取欄位」，從下拉選單選擇姓名依據欄與選填的 LINE 欄，再指定列數（最多 100 列）。
- 讀取姓名儲存格的超連結／HYPERLINK 公式，先以姓名查後台，再核對 LINE 聊天識別碼。後台不支援 LINE 關鍵字搜尋，只有 LINE 時須補姓名。
- 姓名唯一相符、姓名＋LINE 相符、同名多筆、LINE 不符、查無會員分別標示；不自動選取同名會員。每個姓名最多查 10 頁，未查完會明確標示。
- 結果可複製／下載 TSV；電話欄貼入前設為純文字，保留開頭 0。只讀取資料，不回填 Sheet、不更新會員、不發送 LINE。
- 沿用頁首正式／測試環境及後台帳密；Sheet 沿用既有 Google 服務帳號，須有來源試算表讀取權限。


## 服務金額設定

登入區下方「服務金額設定」提供非大掃除、大掃除 PART1、PART2，
每期各有 VIP／非VIP × 平日／週末四組含稅每人時單價。
PART1／PART2起訖日期包含當日，禁止重疊，空白不啟用；範圍外適用非大掃除。
初始單價沿用600／700，須填妥並勾選啟用後儲存才覆蓋原計價。
批次固定VIP；新客固定非VIP；舊客、訂單轉換、補價差依查詢餘額是否大於0判定。
補價差兩段沿用原餘額資格，零餘額略過清零單及優惠券。
加減時共用服務單價；非VIP提前異動費以新單價乘人時，再套用原30%／50%。
VIP提前異動費目前保留每2人1小時200／300元，待確認是否改為服務費比例。

設定預設寫入本機 `service_pricing.json`；可用 `SERVICE_PRICING_FILE` 指向持久磁碟，
或以 `SERVICE_PRICING_JSON` 提供唯讀設定。主機重建前須備份本機設定。
（雲端批次尚未移植到 order-system，價目快照部分待雲端批次移植時一併處理。）
會員餘額沿用 get_member 的 storedValue；若另回傳 shoppingValue則加總，若回傳 totalBalance則優先使用總額。

## Google Sheets 配額節流

`shared/gsheet.py` 的 `build_gsheet_client()` 使用 `shared/sheets_quota.py` 的 `QuotaHTTPClient`：讀／寫各自至少間隔 2 秒，只有 429 配額錯誤會指數退避重試（最多 7 次），其他錯誤與後台建單一律不重試。

## 批次建單三入口與雲端批次成單

- **批次建單（Google Sheet）**：`function/order_creation.render_batch` → `shared/hybrid_batch_runner.run_process_web_direct_single`，逐列單筆成單、每列完成立即回填，不分組。
- **批次建單優化**：`function/batch_booking_optimized.render` → `run_process_web_hybrid`，依正規化電話＋地址分組；2 筆以上同組先批次、整組一次回填，單筆組再逐筆；Google 日曆在訂單回填後才 lazy 初始化。範圍內不符合條件或非本區的列略過，不中止整批。
- **批次建單優化＋雲端批次成單**：`function/cloud_batch_booking.py` 以 `workflow_dispatch` 觸發 `.github/workflows/optimized-cloud-batch-booking.yml`，雲端執行 `python -m shared.cloud_batch_booking --sheet <分頁> ...`；進度寫入 `_雲端成單進度` 工作表（每個 run／attempt 一列，不含客戶資料），頁面每 15 秒更新。雲端預設排除 N 欄「失敗」列，需勾選「我確認已調整，重試失敗列」才重試。啟動時把目前服務金額設定（`service_pricing.load_config()`）以 `pricing_json` 傳給 workflow（環境變數 `SERVICE_PRICING_JSON`）。
- 共用防呆（`shared/batch_booking_safety.py`、`shared/selected_row_status_guard.py`、`shared/batch_recovery_meta.py`）：建單前先反查後台，已成立但未回填者依訂單編號精確補回（不重建、不重寄信）；同條件後台訂單多於空白列時整批擋下待人工確認；只建立 I 欄「未安排」＋M 欄空白的列；重複欄名一律以第一個欄位為準；「每月確認」事件不改日曆、I 欄寫「待確認」；勾選補檸檬人時只有「無班表」列才補班並重試。

雲端批次需在 **jenny-smart/order-system** 的 GitHub Actions secrets 設定：`GOOGLE_SERVICE_ACCOUNT_JSON`、`TAIPEI_EMAIL`／`TAIPEI_PASSWORD`、`TAICHUNG_EMAIL`／`TAICHUNG_PASSWORD`、`TAOYUAN_EMAIL`／`TAOYUAN_PASSWORD`、`HSINCHU_EMAIL`／`HSINCHU_PASSWORD`、`KAOHSIUNG_EMAIL`／`KAOHSIUNG_PASSWORD`、`GOOGLE_MAPS_API_KEY`；Streamlit 端需設定 `ORDERS_GITHUB_TOKEN`（可對 order-system 執行 Actions workflow_dispatch／讀取 runs 與 logs）。workflow 以 `ref: main` 啟動，須合併到 main 後才可使用。

### 本次預約對象、O 欄內容與測試副本（三種批次共用）

- 可建單＝訂單編號空白＋狀態「未安排」＋排程「預約條件」空白或屬於本次預約對象（`shared/booking_eligibility.py`）。畫面可勾選可約／改加／人時不足／已確認／未回覆，預設只有「可約」；未選入的列略過並顯示筆數與列號。雲端以 `STAGES_JSON` 傳入。
- 「O欄找不到訂單編號」改為 O 欄沒有單號，可再勾選 O 欄目前內容（雲端以 `O_TEXTS_JSON` 傳入）。
- 測試機 dev：執行前先把工作表分頁複製成「原名_devMMDD-HHMMSS」，讀取與回填都在副本（`shared/dev_sheet_copy.py`）；雲端 dev 只建單。
- 雲端批次成單可「暫停成單」（做完目前這一組並回填後停止，寫入 `_雲端成單進度` 的「控制」欄）或「立即停止」（取消 Actions 執行）。
- 已退款／取消訂單不視為已成單：中斷復原與比對新單號都排除。
- 工作表「代客保留」打勾的列改用檸檬保留帳號建單，客人備註寫「代客保留：客人姓名」（`shared/proxy_reserve.py`）。
- 回填時沿用排程既有短欄名（沒班表日／餘額不足／日曆改色內容），不再另開欄位。

## 檸檬保留單

- 建單（`function/reserve_menu.py`、`function/reserve_optimizer.py`）：一輪一輪執行，每輪先重新分析各日期剩餘未配班人數；儲值金一次勾選所有日期時段送出。可暫停、繼續、結束。
- 取消（`function/reserve_cancel.py`）：每批 3 張、可暫停；可用客人備註關鍵字搜尋並批次取消代客保留，取消後同步刪除檸檬保留帳號上不再使用的客人地址。
- 檸檬保留刪除地址（`function/reserve_address.py`）：只留信義路、館前路兩個地址，其他地址不查訂單直接刪除；取消檸檬保留單時也順便清。
- 成立／取消紀錄寫入「保留單紀錄」工作表（`shared/reserve_sheet_log.py`）。

## 颱風假訂單移轉

`function/typhoon_transfer.py`（邏輯）＋ `function/typhoon_transfer_page.py`（畫面）：颱風假日期（一天或區間）當天已付款訂單，依後台列表由上而下逐筆用「修改日期」移到指定日期區間，時段不變、日別只分平日與週末；結果可複製原／移轉後日期時段，並可追蹤目前日期（可貼沒有標題列的內容或上次追蹤結果）。

比對 Google 表單（`function/typhoon_sheet_sync.py`）：讀客服的表單，逐筆查後台目前日期／時段，和表單的新日期／新時段比對；確認後只在有異動時填入「異動日期／異動時段」欄（相同但異動欄有舊值則清空），寫入前重讀避免覆蓋手動修改。表單欄位設定依後台帳號暫存在主控試算表「颱風移轉設定」分頁；表單須共用給服務帳號（編輯者）。

## 其他同步項目（orders-system #103～#141）

- 取消訂單：手機號碼可留空改查日期區間內全部客人、全選／全部取消選取、確認視窗下方顯示進度。
- 新客／舊客：多筆日期時段、優惠代碼、紙本／捐贈發票；單筆與批次共用建單流程（`shared/booking_flow.py`，見 `docs/order-creation-flow.md`）。
- 訂單轉換／儲值金補價差：查到班表時段後才建立優惠券，優惠券標題為訂購人姓名＋原訂單末4碼－面額；補價差第一段固定換成檸檬人，可重試。
- 週末服務 LINE 提醒可加入颱風停班提醒；檸檬人勾班新增「僅勾週末」。
- 網頁上按下的每個功能都記入主控表「order-system執行Log-年度」（執行／成功／失敗）。
