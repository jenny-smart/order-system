# ============================================================
# 檔名：ordersapp.py
# 版本：v8.76
# 模組：服務訂單系統主畫面
# 最後更新：2026-08-14
#
# Change Log
# v8.76
# - 功能選單全面重新分組與精簡文字說明：原本 24 項依開發先後順序累積，
#   讀起來凌亂，部分說明落落長。改成依使用情境分成 6 大類依序排列：
#   A. 建單／成單流程　B. 訂單附屬功能　C. 稽核比對工具　D. LINE 通知／提醒
#   E. 會員／客戶管理　F. 財務功能。原本掛在「備忘系統」底下的排班管理／
#   客服作業（改名「訂單客服備註」）／評估文字工具三項移進 A/B；財務對帳
#   （改名「台北/台中區對帳」）／付款後5碼及星和診所比對（改名「桃園/新竹
#   對帳」）／服務異動三項獨立成 F。下拉選單文字統一成「簡短標題：一句話
#   說明」，不再是長句堆疊。內部功能代號（mode/single_feature 判斷式用的
#   字串）除了明確要求改名的 6 個 memo 項目外全部不變；改名的 memo 項目另外
#   用新增的 _MEMO_SECTION_MAP 對應回 memo_system 內部原本的分類名稱，
#   memo_system/ui.py 完全不用改動。
# v8.75
# - 取消訂單新增「月份／日期區間」兩種服務日期查詢方式；月份模式自動帶入當月起迄日。
# - 取消訂單付款狀態新增「待付款」，預設仍為「已付款」。
# - 「取消訂單」與「VIP 訂單／Google 日曆同步」補上與其他功能一致的功能說明。
# v8.74
# - 新增「取消訂單」功能：一般訂單皆可使用，不限定 VIP；可依手機號碼、服務日期區間
#   查詢已付款訂單，並處理不需退款／待退款／待收異動、客人備註及加收／待退備註。
# - 新增「VIP 訂單／Google 日曆同步」功能：同步查詢後台訂單與 Google 日曆，
#   支援異動日期／時段、取消／暫停、僅新增日曆、先預約再新增日曆及修改日曆資訊。
# - VIP 同步不自動判斷訂單對應的既有日曆事件；需要修改既有事件時由使用者自行選擇。
# - VIP 操作畫面統一為左側「訂單資訊」、右側「日曆資訊」，日期與時段欄位水平對齊。
# - Google 日曆欄位統一包含日期、時段、確認文字與顏色／安排狀態；
#   紫色＝未安排、黃色＝已安排、綠色＝暫停。
# v8.73
# - 週末提醒移除 LINE 預約發送與 Quick Reply 測試功能。
# - 勾選後只將追蹤資料寫入 Google Sheet，不會透過程式發送 LINE。
# - 名單新增「資料狀態」，以訂單編號辨識新增／已存在並避免重複列。
# v8.72
# - 恢復週末提醒的 LINE Messaging API、Quick Reply 測試、全選與逐筆勾選排程。
# - 測試機與正式機使用相同的已付款／服務日期篩選規則。
# v8.70
# - 新增「週末服務 LINE 提醒」：篩選週末已付款訂單、產生提醒訊息，
#   並用 Google Sheet 記錄通知與客人回覆狀態。
# v8.68
# - 新客勾選自動樸檬人時，建單後必須將本單專員置換為樸檬人；
#   置換失敗會明確報錯並禁止發送確認信。
# v8.67
# - 批次、舊客、新客、訂單轉換、儲值金補價差恢復「自動補檸檬人」
#   勾選功能。補班只能使用當日無任何班別的檸檬人；已服務其他客人的
#   專員不會被改班、換走或覆寫。
# v8.66
# - 批次建單、舊客建單、新客建單、訂單轉換、儲值金補價差全面禁止
#   自動補班；移除畫面上的自動補檸檬人選項。只使用已有可用人力，
#   人力不足時停止，不得改動其他本來已配班人員。
# v8.65
# - 訂單轉換的舊單A與新單B全面禁止自動補班，移除新單B的
#   「自動補檸檬人」選項。轉換只能使用後台當下已有可用班表，
#   人力不足時停止，不得改動未配班名單或已配班人員班別。
# v8.64
# - 訂單轉換第二段：每筆新訂單 B1/B2/B3... 新增「若無人力，可自動補檸檬人
#   排班」勾選框（預設打勾，維持原行為），可個別關閉；對應
#   quick_order.py v8.49，新增 new_orders_input 的 allow_lemon 欄位。
# v8.63
# - 舊客快速建單付款方式混合選項由「信用卡/ATM」改為「信用卡/ATM/儲值金」；
#   選此混合選項時沿用客人上回付款方式（信用卡、ATM、儲值金皆可），
#   若單獨選信用卡/ATM/儲值金，則以目前選擇的付款方式建單。
# v8.61
# - 訂單轉換第二段結果調整顯示順序：先顯示第三階段金額比對，再顯示 LINE 訊息。
# - 訂單轉換與儲值金補價差若不自動標記已付款，畫面改顯示說明，不再提示要手動改已付款。
# v8.60
# - 將原本「儲值金搜尋」與「儲值金備註」整併為單一功能「儲值獎金備註」。
# - 配合 orders.py v2026.07.08-1：搜尋結果保留 edit_id，套用獎金備註時直接使用
#   已搜尋到的 edit_id，不再每筆重新搜尋訂單編號，降低等待時間。
#   功能序號會自動遞補：原 16 變成 15，後方功能依序往前。
# - 「儲值獎金備註」改成同一頁完成：先搜尋並顯示名單，再用已搜尋結果套用
#   獎金客服備註，不需要確認名單後重新搜尋，減少等待時間。
# - 搜尋結果會暫存在 st.session_state.bn_results，畫面顯示搜尋時間與筆數；
#   只有按「重新搜尋」才會重新打後台查詢。
# v8.59
# - 批次建單保留原本「自動篩選：狀態未安排＋訂單編號空白＋無班表」，
#   另外新增「自動篩選：狀態未安排＋訂單編號空白＋O欄找不到訂單編號」。
#   兩個篩選可單獨使用，也可同時勾選；同時勾選時會合併列號並去除重複。
# v8.58
# - 「儲值獎金備註」改回完全自己獨立運作，不再依賴「儲值金搜尋」的結果。
#   日期區間欄位直接放在同一個畫面，貼上獎金名單後按「查詢並套用獎金備註」
#   一次做完查詢＋比對＋套用，不用先去別的分頁搜尋、也不用先看過搜尋結果
#   才能貼名單。「儲值金搜尋」功能保留，是完全獨立的單純查詢工具（不套用
#   任何東西），跟這裡各自運作、互不影響。
# v8.57
# - 「儲值獎金備註」拿掉重複的搜尋步驟，改成直接沿用「儲值金搜尋」的結果
#   （session_state.bs_results），畫面上只剩貼獎金名單＋套用；沒有先去
#   「儲值金搜尋」查過就會顯示提示，不會誤導成可以直接用。
# v8.56
# - 把「15.儲值獎金備註」拆成兩個獨立功能：新增「儲值金搜尋」（只查詢、
#   列出名單，不寫入任何東西），原本的「儲值獎金備註」維持完整流程
#   （搜尋＋貼獎金名單＋套用寫入客服備註）。兩者各自獨立的搜尋條件與
#   session_state（bs_ 開頭 vs bn_ 開頭），互不影響。
# v8.55
# - 新增「建立筆數」：舊客快速建單（已知日期模式）與新客資料拆解，都可以
#   設定 1~10 筆，各自獨立選日期/時段/人數，一次送出建立多筆訂單（同一個
#   客人/地址，付款方式與發票設定共用）。多筆時畫面下方會列出每一筆的
#   成功/失敗狀態，各自可複製 LINE 訊息。
#   目前只涵蓋「已知日期」模式；「依需求搜尋可服務日期」模式，以及舊客
#   快速建單裡「電話查無會員→直接建新客」那個內嵌子流程，還是只能建一筆。
# v8.54
# - 「整理預約下次服務」表格/複製結果補上遺漏的「訂單編號」欄；貼到 Google
#   Sheets 用的 Tab 分隔版本另外補上 LINE 網址欄（原本只有給網頁表格的姓名
#   超連結用，貼到 Sheets 後 LINE 連結會不見）；排序改成評價日期愈新愈下方
#   （實際排序邏輯在 quick_order.py）。
# v8.53
# - 「整理預約下次服務」結果表格的姓名改成可點擊連到客人 LINE 聊天視窗
#   （改用 markdown 表格呈現，姓名欄是 [姓名](LINE網址) 超連結）。
# v8.52
# - 「整理預約下次服務」新增一個 Tab 分隔版本的複製按鈕，貼到 Google Sheets
#   時會自動分欄（原本斜線分隔的版本貼上去整行只會在同一格，不會分欄）。
# v8.51
# - 會員喜好設定：把每位專員的「不變/喜愛/不喜愛」單選按鈕改成姓名前面
#   兩個獨立勾選框（喜愛專員／不喜愛專員）；同時勾選兩者時擋下送出按鈕
#   並提示衝突。
# v8.50
# - 新增「整理預約下次服務」分頁：搜尋評價日期區間，列出有預約下次服務的
#   客人清單（評價日期/姓名/電話/地址/預約下次日期時間/服務日期時數人數），
#   可複製整理結果。
# v8.49
# - 新增「會員喜好設定」分頁：輸入電話查會員，設定喜愛專員性別，並列出近N次
#   有排班的服務紀錄（日期＋專員姓名），可逐一勾選設為喜愛/不喜愛專員，更新
#   時只改動性別/喜好，不動其他會員資料欄位。
# v8.48
# - 批次建單「執行過程」的日誌顯示改用 st.text() 取代 st.code()，拿掉每行
#   日誌的黑底樣式。
# v8.47
# - 「新客資料拆解」拿掉手動查詢會員的按鈕，改成按「建立新客訂單」時自動
#   先查電話是否為既有會員。是既有會員的話不繼續走新客流程，改成在按鈕
#   下方顯示提醒＋一個「➡️ 用舊客身份送出此預約」按鈕，把已收集到的電話/
#   地址/人時/付款/發票資訊直接帶進舊客建單流程送出，不用客服重填。
# v8.46
# - 「新客資料拆解」（貼上整段文字建單）加上明確的電話查會員步驟：解析出
#   電話後可按鈕查詢是否已是既有會員，是的話直接告知（含既有地址），
#   不用等建單失敗/成功才知道，跟「舊客快速建單」一樣先查電話再繼續。
# v8.45
# - 顯示新客建單流程回傳的 existing_member_warning（電話其實已是舊客會員
#   時的提醒）。
# - 舊客服務地址欄位新增「➕ 輸入新地址」選項：原本只能從既有地址下拉選單
#   挑選，選了新地址選項後會跳出文字輸入框，供客服直接輸入新地址。
# - 14/15 搜尋結果加上除錯資訊顯示（候選訂單數、是否撞到頁數上限）。
# 舊版：v8.44（最後更新誤植為 2026-07-13，今天實際日期為 2026-07-07）
# - 儲值獎金備註的付款狀態下拉選單新增「待付款＋已付款」組合選項。
# v8.43
# - 配合 orders.py v2026.07.13：儲值獎金備註畫面新增「付款狀態」篩選
#   下拉選單，移除原本寫死的處理狀態篩選；搜尋結果表格新增「付款狀態」
#   欄位；套用成功訊息補充說明「服務狀態已改為已處理」。
# v8.42
# - 修正 NameError: name 're' is not defined——儲值獎金備註套用按鈕裡用了
#   re.split 解析獎金人員名字，但 ordersapp.py 頂部沒有 import re。已補上。
# v8.41
# - 選單新增第15項「儲值獎金備註」：① 搜尋購買項目儲值金/已付款/未處理的
#   訂單，列出客戶姓名名單 ② 貼上「客戶姓名：獎金人員1X獎金人員2」的名單
#   （一行一筆）③ 依姓名比對，把「獎金：獎金人員1X獎金人員2」加進該筆
#   訂單的客服備註（保留原本備註內容）。呼叫 orders.py 新增的
#   find_pending_stored_value_orders / apply_bonus_notes。
# v8.40
# - 選單新增第14項「查詢無LINE連結訂單」：搜尋訂購資訊裡沒有LINE連結的
#   訂單，列出訂單編號/姓名/電話，可用訂購日期/付款日期/服務日期三種
#   區間分別篩選（都可留空）。呼叫 orders.py 新增的
#   find_orders_without_line_link。
# v8.39
# - 配合 quick_order.py v8.39：修正合併訂單 LINE 訊息裡「實際服務時間」
#   那行人時說明重複顯示兩次的問題（_format_period_display 本身就會組好
#   完整格式，不用再手動補一次）。
# - 確認訂單轉換／儲值金補價差的「不開立發票」標註機制兩邊呼叫方式完全
#   一致（都是呼叫 _update_order_invoice_no_text），程式碼層面沒有不對稱
#   的地方。
# v8.38
# - 修正儲值金補價差第二段的畫面確認訊息文字：後端實際寫入後台的是
#   「不開立發票」，畫面確認訊息卻還顯示舊字「不用開發票」，兩邊文字
#   不一致容易讓人誤以為標註失敗。已改成跟後端一致的「不開立發票」。
# v8.37
# - 修正訂單轉換第二段的 LINE 訊息被藏在預設收合的「🔍 細項」裡看起來像
#   不見了的問題：改成跟其他流程（新客建單/儲值金補價差/儲值金購買）一致，
#   直接顯示在畫面上，不用多點一次展開。細項只留原訂單A後台連結跟備註文字。
# v8.36
# - 訂單轉換的第三階段（比對金額差額）改回第二段完成後直接自動顯示，
#   不用再另外按按鈕（配合 quick_order.py v8.38 的 LINE 訊息格式調整）。
# v8.35
# - 訂單轉換第二段結果補上顯示每筆新訂單「已標記為已付款」「發票號碼已
#   標註不開立發票」的狀態（跟儲值金補價差一致）。
# - 金額比對獨立成第三階段按鈕「③ 比對金額差額」，不再是第二段完成後自動
#   顯示，讓三個階段的操作跟畫面呈現更清楚對應。
# v8.34
# - 修正訂單轉換第一段結果區塊呼叫了未載入的私有函式 _configure_
#   environment，導致「NameError: name '_configure_environment' is not
#   defined」。改用 convert_order_stage1_reassign_original 回傳結果裡
#   本來就有的 base_url，不用再呼叫一次。
# v8.33
# - 修正 v8.32 的疏漏：訂單轉換分階段介面用到的
#   convert_order_stage1_reassign_original / convert_order_stage2_create_
#   new_orders 忘記加進 _REQUIRED_QUICK_ORDER_NAMES 清單，導致這兩個函式
#   沒被自動載入進來，畫面按下①按鈕會報「name 'convert_order_stage1_
#   reassign_original' is not defined」。已補上。
# v8.32
# - 訂單轉換畫面改成跟儲值金補價差一致的分階段介面：
#   ① 修改原訂單日期並換成檸檬人排班（呼叫 convert_order_stage1_
#   reassign_original，一律自動補檸檬人，此單必須全是檸檬人）
#   ② 建立新訂單（優惠券折抵）（呼叫 convert_order_stage2_create_new_
#   orders，用第一段的結果建折價券＋建新訂單，並比對金額差額）。
#   兩段分開儲存在 session_state（conv_stage1／conv_stage2），跟儲值金
#   補價差的 sv_stored_stage／sv_paid_stage 模式一致。
# v8.31
# - 訂單轉換移除「查無班表時自動補檸檬人排班」勾選框，改成一律自動開啟
#   （跟儲值金補價差一致），人數不夠時不用客服另外勾選就會先嘗試補檸檬人，
#   補不到才會被擋單。
# v8.30
# - 舊客建單/新客建單/訂單轉換/儲值金補價差（含兩段）這 4 個成單流程，
#   結果訊息都補上「👤 專員：xxx」，成單後可以直接看到實際配班的專員名字，
#   不用另外點開後台訂單才看得到。資料本來就有（quick_create_order 早就有
#   回傳 staff 欄位），這次是補上畫面顯示；新客建單原本完全沒有回傳這個
#   資訊，配合 quick_order.py v8.31 一併補上。
# v8.29
# - 「雙向訂單檢查」補上服務日期區間輸入，修正方向二原本的邏輯漏洞：舊版
#   方向二是拿工作表裡已出現的電話去查後台，如果某張後台訂單的客人電話
#   整筆漏登記進工作表，從一開始就不會被查到。現在填了日期區間的話，會
#   直接掃過後台在這段期間「全部」已付款訂單（處理分頁），逐筆核對訂單編號
#   有沒有出現在工作表裡，才能真正抓到「工作表完全沒登記」的情況。
#   配合 orders.py 新增的 _fetch_all_purchase_blocks_by_date_range。
# v8.28
# - 功能選單的下拉選項加上編號（1. 2. 3. ...），選項文字比較長時方便一眼
#   對照要選第幾項，不用整段文字讀完才能定位。編號是動態產生的，之後增減
#   選項不用手動改號碼。
# v8.27
# - 新增獨立的「雙向訂單檢查」功能（選單第13項），不再只能依附在批次建單
#   的「全部執行完後做一次訂單一致性檢查」勾選框裡。這個功能可以直接針對
#   一份已經有「訂單編號」欄位的成單工作表（不限定是不是這次批次剛跑過的
#   列），單獨跟後台系統重新做一次雙向比對：
#   方向一：工作表寫的訂單編號，回查後台是否真的存在、電話/地址/日期/時段
#           是否相符。
#   方向二：工作表涉及的每支電話，查後台在該日期範圍內的實際訂單，抓出
#           「後台其實已經成單，但工作表沒有正確記錄」的情況。
#   對應 orders.py 新增的 run_standalone_consistency_check，共用既有的
#   verify_batch_order_consistency 核心比對邏輯，只是不用先跑一次批次建單。
#   可選擇只檢查特定區域，或檢查整份工作表。
# v8.26
# - 把 memo-system（備忘系統：排班管理/客服作業/財務對帳/服務異動/評估文字
#   工具）整併進 orders-system，新增 memo_system/ 套件（memo.py/atm.py/
#   shift.py/change_order.py/ui.py，import 改成套件內相對匯入）。
# - 功能選單從橫向 radio 改成下拉選單（跟 memo-system 原本風格一致），並把
#   訂單系統原本 7 個功能跟備忘系統 5 個功能合併成同一份下拉清單共 12 項，
#   選項文字直接帶簡短說明（不用另外看功能說明面板）：
#   批次建單／舊客建單／新客建單／儲值金建單／訂單轉換／儲值金補價差／
#   排班管理／LINE通知訊息／訂單備註／對帳管理／異動管理／評估工具。
# - 後台帳號/密碼/環境維持只有一組（Step 1 登入），備忘系統的功能呼叫
#   render_memo_system(shared_backend_email=..., ...) 沿用同一組登入資訊，
#   不會再顯示備忘系統自己原本的登入欄位。
# - 已用全部 12 個選項逐一實際執行測試過，皆無例外。
# v8.25
# - 配合 quick_order.py v8.28（嚴格依序查儲值金→VIP→專業清潔，並跳過付款
#   方式是儲值金的訂單），「查詢明細」展開區塊補上「被跳過的儲值金折抵訂單」
#   表格，並更新說明文字。
# v8.24
# - 配合 quick_order.py v8.26 改用伺服器端「購買項目/付款狀態」篩選查詢，
#   同步更新「查詢明細」展開區塊的表格欄位（改成顯示依序查了哪些類別、
#   各查到幾筆已付款訂單、有哪些訂單編號），取代舊版「自己分類全部訂單」
#   的顯示格式。
# v8.23
# - 「儲值金購買」查無可用付款方式/發票設定時，新增「查詢明細」展開區塊，
#   用表格顯示這支電話實際查到的每一張訂單卡片（訂單編號/分類結果/是否
#   已付款），配合 quick_order.py v8.25 的 search_debug，讓查不到資料的
#   原因可以直接從畫面上判斷，不用再靠反覆截圖來回排查。
# v8.22
# - 「儲值金購買」結果區塊補上「發送確認信」按鈕，跟其他成單流程一致：
#   建單成功後不自動發信，由客服確認資料無誤後手動按下再發送
#   （沿用既有 send_confirmation，成功後畫面切換為「已發送」狀態）。
#   LINE 通知訊息這部分從 v8.21 起本來就會自動產生並顯示，本次沒有改動。
# v8.21
# - 修正 _missing_quick_order_names 檢查跳出的錯誤訊息：原本寫死「請用 v8.5
#   覆蓋 GitHub 上的 quick_order.py」，是很久以前版本號還是 v8.5 時寫的字串，
#   之後版本一路往上加卻沒跟著更新，導致畫面一直誤導使用者要覆蓋成「v8.5」。
#   改成不寫死版本號的通用說明，並提醒可能是 Streamlit 快取沒重新載入，
#   建議手動 Reboot app。
# v8.20
# - 新增「儲值金購買」功能選單，對應 quick_order.py 新增的
#   create_stored_value_purchase_order：輸入手機號碼、選地區、選金額即可
#   建單，付款方式/發票自動沿用會員歷史訂單設定，不用手動選；查無可用設定
#   時會明確提示需人工確認，不會默默送出錯誤的付款/發票組合。
# v8.19
# - 批次建單的訂單一致性檢查改成「全部列都跑完後才統一做一次」，不再是每一列
#   各自比對一次（原本掛在 run_process_web 裡，會讓同一支電話在多列批次裡被
#   重複查詢很多次，配合 orders.py 新增的獨立函式 run_batch_consistency_check）。
# - 一致性檢查改成看得到的獨立勾選框「全部執行完後做一次訂單一致性檢查」，
#   預設開啟，並在執行結果下方另外顯示獨立的「步驟5：訂單一致性檢查」區塊，
#   不管有沒有異常都會顯示執行狀態，不會讓人以為系統根本沒做這件事。
# - 「批次建單」的功能說明加入雙向比對的說明文字。
# v8.18
# - 批次建單的訂單一致性檢查結果顯示，配合 orders.py 的雙向比對更新：
#   1. 方向一比對項目加入地址，訊息文字同步更新為「電話/地址/日期/時段」。
#   2. 方向二（系統反查 Sheet）查到的異常沒有對應到特定列（row_num 為
#      None），畫面改顯示「（系統反查）」而不是「第 None 列」。
# v8.17
# - 修正「新客資料拆解」與「訂單轉換」的 LINE 訊息文字框，成立新訂單後畫面還
#   停留在上一張訂單內容的問題：這幾個 st.text_area 原本帶了固定 key
#   （nc_line_out / conv_line_{index} / conv_combined_line），Streamlit 的
#   規則是「帶 key 的 widget 只有第一次渲染時吃 value 參數，之後即使傳入新的
#   value，畫面仍以 session_state 裡的舊值為準」，導致訂單編號/金額/日期都已經
#   換成新訂單了，LINE 訊息內文卻還是前一張訂單的。修法：拿掉這三處不需要保留
#   使用者編輯狀態的固定 key，改成跟舊客快速建單、儲值金補價差的 LINE 訊息
#   一樣不帶 key，每次都用最新的 value 重新渲染。
# v8.16
# - 修正 v8.15 造成的 AttributeError：清空舊結果時原本寫成
#   `st.session_state.nc_result = None`，但下面讀取是
#   `st.session_state.get("nc_result", {})` 再接 `.get("order_no")`——
#   get() 的預設值只在「key 不存在」時生效，key 存在但值是 None 時直接拿到
#   None，後面 `.get()` 就會炸出 AttributeError。修法：五個成單流程清空舊結果
#   時一律改成清成 `{}` 而不是 `None`（空字典一樣是 falsy，所有 if 判斷維持
#   正常，但不會再有 None.get() 的問題）。
# v8.15
# - 修正五個成單流程（舊客快速建單、新客資料拆解、訂單轉換、儲值金補價差兩段）
#   按下執行按鈕時沒有先清空上一次殘留在 session_state 的舊結果，導致這次執行
#   失敗（或還在拆解資料階段）時，畫面下方還顯示上一次成功的舊訂單資訊，
#   跟這次的錯誤訊息重疊在一起造成混淆。現在改為：每個「執行」按鈕一按下，
#   立刻清空自己那個結果區塊，再開始新的一次嘗試。
# v8.14
# - 批次建單（Google Sheet）補上「查無班表時自動補檸檬人排班」勾選框，預設不勾選，
#   與舊客快速建單、新客資料拆解、訂單轉換三個流程行為一致（配合 orders.py
#   process_one_group / run_process_web 新增的 allow_auto_lemon_shift 參數）。
#   　※上次 v8.13 只更新了 quick_order.py，批次建單走的是 orders.py，
#   　　這次才一併補上，五個成單功能現在才真的共用同一套邏輯。
# - 批次建單執行完畢後，顯示訂單一致性檢查結果：若 Google Sheet 上寫回的訂單編號
#   跟該列電話/日期/時段對不上（例如訂單編號重複寫入兩列、或該列其實沒有真的
#   成單），會直接在畫面上列出異常，不用再自己肉眼比對（配合 orders.py 新增的
#   verify_batch_order_consistency）。
# v8.13
# - 新增訂單編號重複提醒視窗（show_duplicate_order_warning）：建單成功後若偵測到
#   訂單編號重複（配合 quick_order v8.13 的 order_no_duplicated），會用
#   st.dialog 跳出提醒視窗（不支援 st.dialog 的 Streamlit 版本則退回醒目的
#   st.error），涵蓋舊客快速建單、新客資料拆解、訂單轉換、儲值金補價差四個流程。
# - 舊客快速建單、新客資料拆解、訂單轉換三個流程都新增「查無班表時自動補檸檬人
#   排班」勾選框，預設不勾選；未勾選時查無班表不會自動嘗試勾檸檬人（配合
#   quick_order v8.13 的 allow_auto_lemon_shift 參數）。
# v8.12
# - 「新客資料拆解」貼上文字後即時顯示拆解預覽（姓名/電話/地址）；若判斷不出付款
#   方式，直接顯示手動選擇的下拉選單，未選擇前擋下「建立新客訂單」按鈕，
#   不再默默預設成信用卡（配合 quick_order v8.12 的 need_ask_payway）。
# v8.10
# - 「新客資料拆解」流程的 LINE 訊息旁補上「複製 N-J Memo」區塊，
#   與「舊客快速建單」版面一致（原本只有舊單有，新單沒有）。
# v8.9
# - 新客建單結果加上「地址比對警示」：若後台實際地址與送出地址不同（例如後台自動
#   判斷區域時加了不正確的市/區前綴），會直接顯示警示文字並附上後台實際地址，
#   方便立即發現、回報或至後台手動修正（配合 quick_order v8.9 的
#   address_mismatch_warning）。經確認此類情況是後台端自身的地址正規化行為，
#   並非本系統送出的地址資料有誤。
# v8.8
# - 修正「舊客快速建單」結果區塊（訂單編號/金額/車馬費/確認信 metrics + LINE 訊息）
#   原本沒有限定分頁，導致切到「新客資料拆解」等其他分頁後，session_state 裡
#   殘留的舊訂單結果還黏在畫面下方，跟當前分頁剛建立的訂單混在一起顯示
#   （例如畫面同時出現兩筆不同訂單、不同日期、不同金額，造成混淆）。
#   現在改為只在「舊客快速建單」分頁才顯示。
# v8.7
# - 新客建單結果（舊客快速建單>查無會員 / 新客資料拆解）加上金額比對警示：
#   若後台實際金額與人時公式（600平日/700週末，不含車馬費）算出的金額不同，
#   會直接顯示警示文字，方便立即發現金額被後台另行計價覆蓋的情況
#   （配合 quick_order v8.7 的 price_mismatch_warning）。
# v8.6
# - 舊客快速建單：付款方式選單改為「信用卡/ATM」「信用卡」「ATM」「儲值金」四選一。
#   選「信用卡/ATM」時沿用上次付款紀錄（僅限信用卡或ATM，查無則預設信用卡）；
#   選「信用卡」或「ATM」則直接以該選項作為付款方式；「儲值金」維持獨立選項。
#   實際送單一律解析為信用卡／ATM／儲值金三者之一，caption 同步顯示解析結果。
# - 修正「新客資料拆解」流程從未組出 LINE 訊息的問題（配合 quick_order v8.6
#   quick_create_new_customer_order 補齊回傳欄位，這裡改為直接呼叫 build_line_message）。
# v8.5
# - 舊客快速建單：付款方式選單改為永遠顯示（信用卡／ATM／儲值金），
#   預設值帶上次付款紀錄，但客服可隨時切換，不再被歷史紀錄鎖死。
# - 建單介面 caption 加上送單網址顯示，方便確認 /booking/single 或
#   /booking/stored_value_routine 是否選對。
# v8.4
# - 訂單轉換改為一對多：可設定多筆新訂單（日期/時段/人數各自選）。
#   每筆新單各建一張折價券（面額=該筆含稅金額）。
#   原單A配班：一般專員優先，不足補檸檬人。
#   新單配班：同上。備註：A+B1+B2+B3 合併服務。
# - _REQUIRED_QUICK_ORDER_NAMES 加入 convert_order_multi。
# v8.3 - 排班換人必須勾選足夠不同的檸檬人
# v8.2 - 檸檬人依序補勾多位不同檸檬人
# v8.1 - 第二段補價差單沿用第一段原儲值金餘額
# v8.0 - 檸檬人清單解析新增 shift 頁掃描備援
# v7.9 - 配合 quick_order v7.9
# v7.8 - 儲值金清零說明與計算修正
# v7.7 - 儲值金補價差拆兩段按鈕
# ============================================================
# -*- coding: utf-8 -*-
__version__ = "8.76"

import html
import re
import json
import streamlit as st
import streamlit.components.v1 as components
from datetime import date, timedelta, datetime

from orders import run_process_web, get_region_by_address, run_standalone_consistency_check, run_backend_calendar_consistency_check, find_orders_without_line_link, find_pending_stored_value_orders, add_bonus_note_to_order, apply_bonus_notes, load_worksheet, fetch_member_edit_page, submit_member_preferences, fetch_recent_service_records
from env import GOOGLE_CALENDAR_MAP
from weekend_reminders import (
    upcoming_weekend, previous_workday, find_paid_weekend_orders,
    load_tracking_rows, merge_tracking_rows, save_tracking_rows,
    tracking_rows_tsv,
    NOTICE_STATUSES, REPLY_STATUSES,
)
from cleaner_reminders import find_paid_cleaner_reminders
from accounts import ACCOUNTS
from memo_system.ui import render_memo_system

try:
    import quick_order as qo
except Exception as e:
    st.error(f"quick_order.py 載入失敗：{type(e).__name__}: {e}")
    st.stop()

if not hasattr(qo, "stored_value_makeup_convert") and hasattr(qo, "stored_value_makeup"):
    qo.stored_value_makeup_convert = qo.stored_value_makeup

_REQUIRED_QUICK_ORDER_NAMES = [
    "quick_lookup_member",
    "quick_create_order",
    "quick_check_available_slots",
    "send_confirmation",
    "build_line_message",
    "build_line_message_from_order_no",
    "build_combined_line_message_from_order_nos",
    "get_last_paid_summary",
    "get_last_paid_per_address",
    "get_unserved_paid_orders",
    "get_last_purchase_fetch_debug",
    "build_equivalent_plans",
    "search_available_service_dates",
    "parse_new_customer_order_text",
    "create_coupon",
    "convert_order",
    "convert_order_multi",
    "convert_order_stage1_reassign_original",
    "convert_order_stage2_create_new_orders",
    "get_stored_value",
    "calc_stored_value_plan",
    "stored_value_makeup_convert",
    "stored_value_makeup_create_stored_order",
    "stored_value_makeup_create_paid_order",
    "create_stored_value_purchase_order",
    "COUPON_COMPANY_ID_MAP",
    "COUPON_SERVICE_ITEM_MAP",
    "COUPON_TYPE_MAP",
]

_missing_quick_order_names = [name for name in _REQUIRED_QUICK_ORDER_NAMES if not hasattr(qo, name)]
if _missing_quick_order_names:
    st.error(
        f"quick_order.py 目前版本不完整（缺少必要函式），請確認 GitHub 上的 quick_order.py 是最新版本"
        f"（本檔 ordersapp.py 為 v{__version__}），並確認 Streamlit 有重新載入最新內容"
        f"（若剛覆蓋過檔案，畫面右下角選單可手動 Reboot app）。"
        + "\n缺少：" + "、".join(_missing_quick_order_names)
    )
    st.stop()

for _name in _REQUIRED_QUICK_ORDER_NAMES:
    globals()[_name] = getattr(qo, _name)

st.set_page_config(page_title="服務訂單系統", page_icon="🧹", layout="wide")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+TC:wght@400;500;700&family=Space+Grotesk:wght@500;700&display=swap');

:root {
    --lemon: #F5C518;
    --lemon-dark: #D4A017;
    --lemon-soft: #FFFBEA;
    --lemon-mid: #FFF3C4;
    --charcoal: #1C1C1E;
    --ink: #3A3A3C;
    --muted: #8E8E93;
    --border: #E5E5EA;
    --surface: #FFFFFF;
    --success: #34C759;
    --danger: #FF3B30;
    --radius: 14px;
}

html, body, [class*="css"] { font-family: 'Noto Sans TC', sans-serif; color: var(--charcoal); }
#MainMenu, footer, header { visibility: hidden; }
[data-testid="stAppViewContainer"] { background: #FAFAFA; }
.block-container { padding-top: 2rem !important; padding-bottom: 2rem !important; max-width: 1180px !important; }

.hero { background: linear-gradient(135deg, #FFFDF0 0%, #FFFBEA 100%); border: 1.5px solid var(--lemon-mid); border-radius: var(--radius); padding: 2rem 2.5rem 1.6rem; margin-bottom: 2rem; display: flex; align-items: center; gap: 1.2rem; box-shadow: 0 2px 12px rgba(245,197,24,0.10); }
.hero-emoji { font-size: 3rem; line-height: 1; }
.hero-title { font-family: 'Space Grotesk', sans-serif; font-size: 1.9rem; font-weight: 700; color: var(--charcoal); letter-spacing: -0.5px; }
.hero-sub { color: var(--ink); font-size: 0.92rem; margin-top: 0.3rem; opacity: 0.78; }

.step-pill { display: inline-flex; align-items: center; gap: 0.5rem; background: var(--lemon-mid); border: 1.5px solid var(--lemon); border-radius: 30px; padding: 0.28rem 0.9rem; font-size: 0.78rem; font-weight: 700; color: var(--charcoal); margin-bottom: 0.9rem; letter-spacing: 0.02em; }
.step-num { background: var(--lemon); border-radius: 50%; width: 20px; height: 20px; display: inline-flex; align-items: center; justify-content: center; font-size: 0.72rem; font-weight: 700; }
.sec-label { font-size: 12px; font-weight: 700; color: var(--muted); letter-spacing: .04em; margin-bottom: 8px; }
.hint-box { background: var(--lemon-soft); border-left: 4px solid var(--lemon); border-radius: 0 8px 8px 0; padding: 0.75rem 1rem; font-size: 0.9rem; color: var(--ink); margin-top: 0.6rem; }

[data-testid="stTextInput"] label, [data-testid="stNumberInput"] label, [data-testid="stSelectbox"] label, [data-testid="stMultiSelect"] label, [data-testid="stDateInput"] label, [data-testid="stRadio"] label { font-size: 13px !important; color: var(--ink) !important; font-weight: 700 !important; }
[data-testid="stTextInput"] input, [data-testid="stNumberInput"] input, [data-testid="stSelectbox"] > div > div, [data-testid="stMultiSelect"] > div > div, [data-testid="stDateInput"] input { border-radius: 10px !important; border: 1.5px solid var(--border) !important; background: white !important; font-size: 15px !important; }
[data-testid="stTextInput"] input:focus { border-color: var(--lemon-dark) !important; box-shadow: 0 0 0 2px rgba(245,197,24,0.22) !important; }
[data-testid="stButton"] > button { background: var(--lemon) !important; color: var(--charcoal) !important; border: none !important; border-radius: 10px !important; font-size: 15px !important; font-weight: 700 !important; padding: 0.55rem 1.2rem !important; box-shadow: 0 2px 10px rgba(245,197,24,0.28) !important; }
[data-testid="stButton"] > button:hover { background: var(--lemon-dark) !important; transform: translateY(-1px) !important; }
[data-testid="stButton"] > button:disabled { background: #D1D5DB !important; color: #777 !important; }
[data-testid="stExpander"] { border: 1px solid #ececec !important; border-radius: 14px !important; background: white !important; overflow: hidden !important; box-shadow: 0 2px 12px rgba(0,0,0,0.04); }
[data-testid="stExpander"] summary { font-size: 14px !important; font-weight: 700 !important; color: var(--charcoal) !important; padding: 12px 16px !important; }
[data-testid="stCode"] { font-size: 13px !important; border-radius: 0 0 12px 12px !important; min-height: 420px !important; max-height: 560px !important; overflow-y: auto !important; background: #1C1C1E !important; margin: 0 !important; white-space: pre-wrap !important; }
[data-testid="stMetric"] { background: white !important; border: 1px solid #ececec !important; border-radius: 14px !important; padding: 14px 16px !important; text-align: center !important; box-shadow: 0 2px 12px rgba(0,0,0,0.04); }
[data-testid="stMetricLabel"] { font-size: 12px !important; color: var(--muted) !important; font-weight: 700 !important; }
[data-testid="stMetricValue"] { font-family: 'Space Grotesk', sans-serif; font-size: 32px !important; font-weight: 700 !important; color: var(--charcoal) !important; }
[data-testid="stAlert"] { border-radius: 10px !important; font-size: 14px !important; }
hr { border-color: #e8e8e8 !important; margin: 1.4rem 0 !important; }

.history-card { background: var(--lemon-soft); border-left: 4px solid var(--lemon); border-radius: 0 10px 10px 0; padding: 1rem 1.1rem; margin-top: 0.85rem; font-size: 0.94rem; color: var(--ink); }
.history-title { font-size: 1rem; font-weight: 800; color: var(--charcoal); margin-bottom: 0.75rem; }
.history-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0.45rem 1.2rem; }
.history-field { display: grid; grid-template-columns: 5.5rem minmax(0, 1fr); gap: 0.35rem; align-items: start; }
.history-label { color: var(--muted); font-weight: 700; white-space: nowrap; }
.history-value { color: var(--charcoal); font-weight: 600; overflow-wrap: anywhere; }
.history-subtitle { margin-top: 0.9rem; padding-top: 0.75rem; border-top: 1px solid var(--lemon-mid); font-weight: 800; color: var(--charcoal); }
.history-order { margin-top: 0.55rem; padding: 0.65rem 0.75rem; background: rgba(255,255,255,0.58); border: 1px solid var(--lemon-mid); border-radius: 8px; }
.history-order-main { font-weight: 800; color: var(--charcoal); margin-bottom: 0.35rem; }
.history-order-meta { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0.25rem 1rem; color: var(--ink); }
.history-note { margin-top: 0.75rem; color: var(--muted); }
@media (max-width: 720px) { .history-grid, .history-order-meta { grid-template-columns: 1fr; } }
</style>
""", unsafe_allow_html=True)

CLEAN_TYPE_ID_MAP = {"居家清潔": "1", "辦公室清潔": "2", "裝修細清": "3"}

PERIOD_OPTIONS = [
    "08:30-12:30", "09:00-11:00", "09:00-12:00",
    "14:00-16:00", "14:00-17:00", "14:00-18:00",
    "09:00-16:00", "09:00-18:00",
]

PERIOD_HOUR_MAP = {
    "08:30-12:30": 4, "09:00-11:00": 2, "09:00-12:00": 3,
    "14:00-16:00": 2, "14:00-17:00": 3, "14:00-18:00": 4,
    "09:00-16:00": 6, "09:00-18:00": 8,
}

NJ_MEMO = (
    "**N-J**\n"
    "請現場跟客戶溝通清潔優先順序,並請回報以下內容\n"
    "*工作項目+時間分配\n"
    "*特別注意事項\n"
    "*服務小貼心"
)


def compact_period(value):
    return str(value or "").replace(" ", "")


def nonzero_money(value):
    try:
        return float(str(value or "0").replace(",", "")) != 0
    except Exception:
        return bool(str(value or "").strip())


def payment_invoice_display(payway, invoice_text):
    if payway == "儲值金":
        return "儲值金客（無付款方式/發票資訊）"
    return f"付款：{payway or '未知'}　發票：{invoice_text or '未知'}"


def booking_route_display(payway):
    if payway == "儲值金":
        return "儲值金客", "/booking/stored_value_routine"
    return "一般客", "/booking/single"


def h(value, default="未知"):
    text = str(value or "").strip()
    return html.escape(text if text else default)


def person_hour_display(person, hour):
    return f"{person}人{hour}小時" if (person or hour) else "未知"


def history_field(label, value):
    return (
        '<div class="history-field">'
        f'<span class="history-label">{h(label, "")}</span>'
        f'<span class="history-value">{h(value)}</span>'
        '</div>'
    )


def order_history_row(order):
    ph_text = person_hour_display(order.get("person"), order.get("hour"))
    payment_text = payment_invoice_display(order.get("payway"), order.get("invoice_text"))
    notice = order.get("service_notice") or "無"
    fare = order.get("fare") or ""
    fare_part = f'<div>車馬費：{h(fare, "")}</div>' if nonzero_money(fare) else ""
    return (
        '<div class="history-order">'
        f'<div class="history-order-main">{h(order.get("order_no"))}　{h(order.get("date"))} {h(order.get("time"), "")}</div>'
        '<div class="history-order-meta">'
        f'<div>人時：{h(ph_text)}</div>'
        f'<div>服務人員：{h(order.get("staff"))}</div>'
        f'<div>地址：{h(order.get("address"))}</div>'
        f'<div>{h(payment_text)}</div>'
        f'<div>客服備註：{h(notice)}</div>'
        f'{fare_part}'
        '</div>'
        '</div>'
    )


def last_summary_card_html(summary):
    ph_text = person_hour_display(summary.get("person"), summary.get("hour"))
    payment_text = payment_invoice_display(summary.get("payway"), summary.get("invoice_text"))
    fields = [
        ("訂單", summary.get("order_no")),
        ("服務時間", f'{summary.get("date") or ""} {summary.get("time") or ""}'.strip()),
        ("地址", summary.get("address") or "無法判斷地址"),
        ("類別", summary.get("clean_type")),
        ("服務人員", summary.get("staff")),
        ("人時", ph_text),
        ("付款/發票", payment_text),
        ("客服備註", summary.get("service_notice") or "無"),
    ]
    if nonzero_money(summary.get("fare")):
        fields.append(("車馬費", summary.get("fare")))
    same_date_orders = summary.get("same_date_orders") or []
    same_date_html = ""
    if len(same_date_orders) > 1:
        same_date_html = (
            f'<div class="history-subtitle">該日期共有 {len(same_date_orders)} 筆已付款訂單</div>'
            + "".join(order_history_row(order) for order in same_date_orders)
        )
    return (
        '<div class="history-card">'
        '<div class="history-title">📌 上次（已付款）服務</div>'
        '<div class="history-grid">'
        + "".join(history_field(label, value) for label, value in fields)
        + '</div>'
        + same_date_html
        + '<div class="history-note">以上已預設帶入，如有變動請手動調整對應欄位。</div>'
        + '</div>'
    )


def copy_button(label, text, key):
    payload = json.dumps(text, ensure_ascii=False)
    label_payload = json.dumps(label, ensure_ascii=False)
    components.html(
        f"""
        <button id="{key}" style="width:100%;padding:0.65rem 1rem;border:0;border-radius:10px;background:#F5C518;color:#1C1C1E;font-size:15px;font-weight:700;cursor:pointer;">{html.escape(label)}</button>
        <script>
        const btn = document.getElementById({json.dumps(key)});
        const text = {payload};
        const label = {label_payload};
        btn.addEventListener("click", async () => {{
            try {{ await navigator.clipboard.writeText(text); btn.textContent = "已複製"; }}
            catch (err) {{ const ta = document.createElement("textarea"); ta.value = text; document.body.appendChild(ta); ta.select(); document.execCommand("copy"); document.body.removeChild(ta); btn.textContent = "已複製"; }}
            setTimeout(() => {{ btn.textContent = label; }}, 1600);
        }});
        </script>
        """,
        height=54,
    )


def show_duplicate_order_warning(order_no, count, dedup_key=""):
    """
    v8.13：訂單編號重複提醒視窗。
    優先使用 st.dialog 跳出真正的提醒視窗（Streamlit 1.31+）；
    若目前版本不支援 st.dialog，退回使用醒目的 st.error 區塊，
    確保任何 Streamlit 版本都看得到警示，不會被畫面其他內容淹沒。
    dedup_key 用來避免同一筆訂單在同一次畫面重繪中重複跳出視窗。
    """
    _seen_key = f"_dup_order_seen_{dedup_key or order_no}"
    if st.session_state.get(_seen_key):
        return
    st.session_state[_seen_key] = True

    message = (
        f"訂單編號 **{order_no}** 目前查詢到 **{count}** 張不同的訂單卡片，"
        f"這是後台偶發的「訂單編號重複」問題。\n\n"
        f"請務必至後台人工確認這幾張訂單卡片的實際內容，避免訂單資料互相搞混或覆蓋！"
    )

    if hasattr(st, "dialog"):
        @st.dialog("⚠️ 訂單編號重複警示")
        def _dup_order_dialog():
            st.error(message)
            if st.button("我知道了", use_container_width=True, key=f"dup_ack_{dedup_key or order_no}"):
                st.rerun()
        _dup_order_dialog()
    else:
        st.error(f"⚠️ 訂單編號重複警示\n\n{message}")


def step(num, title):
    st.markdown(f'<div class="step-pill"><span class="step-num">{num}</span>{title}</div>', unsafe_allow_html=True)


def info_panel(title, bullets):
    items = "".join(f"<li>{html.escape(str(item))}</li>" for item in bullets)
    st.markdown(f'<div class="hint-box"><b>{html.escape(str(title))}</b><ul style="margin:0.45rem 0 0 1.1rem; padding:0;">{items}</ul></div>', unsafe_allow_html=True)


def parse_row_input(row_text: str):
    if not row_text or not row_text.strip():
        raise ValueError("請輸入列號，例如：2,3,5-7")
    rows = set()
    for part in [p.strip() for p in row_text.split(",") if p.strip()]:
        if "-" in part:
            s, e = part.split("-", 1)
            s, e = int(s.strip()), int(e.strip())
            if s <= 0 or e <= 0:
                raise ValueError("列號必須大於 0")
            if s > e:
                raise ValueError(f"區間錯誤：{part}")
            rows.update(range(s, e + 1))
        else:
            n = int(part)
            if n <= 0:
                raise ValueError("列號必須大於 0")
            rows.add(n)
    return sorted(rows)


def find_no_slot_rows(sheet_name, region, candidate_rows=None):
    _, df = load_worksheet(sheet_name)
    candidate_set = set(candidate_rows or [])
    if candidate_set:
        df = df[df["__sheet_row__"].isin(candidate_set)]
    rows = []
    for _, row in df.iterrows():
        status = str(row.get("狀態", "")).strip()
        order_no = str(row.get("訂單編號", "")).strip()
        reason_text = f"{row.get('原因', '')} {row.get('沒班表日期', '')}"
        if status == "未安排" and not order_no and "無班表" in str(reason_text):
            if get_region_by_address(str(row.get("地址", "")), ACCOUNTS) == region:
                rows.append(int(row["__sheet_row__"]))
    return rows


def find_missing_order_in_o_rows(sheet_name, region, candidate_rows=None):
    _, df = load_worksheet(sheet_name)
    candidate_set = set(candidate_rows or [])
    if candidate_set:
        df = df[df["__sheet_row__"].isin(candidate_set)]
    rows = []
    for _, row in df.iterrows():
        status = str(row.get("狀態", "")).strip()
        order_no = str(row.get("訂單編號", "")).strip()
        o_text = str(row.iloc[14] if len(row) > 14 else "")
        if status == "未安排" and not order_no and not re.search(r"(LC|TT|KK)\d+", o_text):
            if get_region_by_address(str(row.get("地址", "")), ACCOUNTS) == region:
                rows.append(int(row["__sheet_row__"]))
    return rows


def format_log_message(msg):
    text = str(msg)
    text = text.replace("\\n", "\n")
    text = text.replace("目前環境：", "\n目前環境：")
    text = text.replace("BASE_URL：", "\nBASE_URL：")
    text = text.replace("執行區域：", "\n執行區域：")
    text = text.replace("執行工作表：", "\n執行工作表：")
    text = text.replace("執行列範圍：", "\n執行列範圍：")
    text = text.replace("處理第", "\n處理第")
    text = text.replace("已回填 Google Sheet。", "\n已回填 Google Sheet。")
    if text.startswith("▶"):
        text = "\n" + text
    return text.strip()


# =========================================================
# 主畫面
# =========================================================

st.markdown("""
<div class="hero">
  <div class="hero-emoji">🧹</div>
  <div>
    <div class="hero-title">服務訂單系統</div>
    <div class="hero-sub">支援批次建單、建立舊客訂單、建立新客訂單、LINE 通知、確認信與 Google 日曆同步。</div>
  </div>
</div>
""", unsafe_allow_html=True)

step("1", "登入與環境設定")
col_e, col_p, col_env = st.columns([3.2, 3.2, 1.2])
with col_e:
    backend_email = st.text_input("後台帳號")
with col_p:
    backend_password = st.text_input("後台密碼", type="password")
with col_env:
    env_label = st.selectbox("環境", ["prod（正式機 backend）", "dev（測試機 backend-dev）"], index=0)
    env = "dev" if env_label.startswith("dev") else "prod"

st.markdown("<hr>", unsafe_allow_html=True)

step("2", "功能選單")

# v8.26：功能選單改成下拉形式（跟 memo-system 一致），並把備忘系統
# （排班管理/訂單備註/對帳管理/異動管理/評估工具）合併進同一個選單，
# 選項文字直接帶簡短說明，不用另外看上面的功能說明面板。
# v8.76：功能選單全面重新分組與精簡文字說明（原本 24 項照開發先後順序累積，
# 讀起來凌亂，部分說明落落長）。改成依使用情境分成 6 大類、依序排列：
# A. 建單／成單流程　B. 訂單附屬功能　C. 稽核比對工具　D. LINE 通知／提醒
# E. 會員／客戶管理　F. 財務功能（原本掛在「備忘系統」底下的排班管理／
# 客服作業／評估文字工具三項移進 A/B；財務對帳／付款後5碼及星和診所比對／
# 服務異動三項獨立成 F，並依客服需求把財務對帳、付款後5碼分別改名為
# 「台北/台中區對帳」「桃園/新竹區對帳」）。
# 每一項的下拉選單文字（第一個欄位）統一成「簡短標題：一句話說明」，不再是
# 長句堆疊。第三個欄位（內部用的功能代號）除了明確要求改名的 6 個 memo 項目
# 外，全部維持原字串不變，避免影響後面 mode/single_feature 判斷式；memo
# 項目改名後的代號另外用 _MEMO_SECTION_MAP 對應回 memo_system 內部原本的
# 分類名稱（見下方 _system_key == "memo" 的呼叫處）。
FUNCTION_OPTIONS = [
    # ---------- A. 建單／成單流程 ----------
    ("批次建單：從 Google Sheet 逐列建立訂單、寄確認信、同步日曆。",
     "orders", "批次建單（Google Sheet）"),
    ("建立舊客訂單：電話查會員、帶入歷史資料建單；需求搜尋整合在此流程內。",
     "orders", "建立舊客訂單"),
    ("建立新客訂單：貼上制式文字拆成欄位，供客服修改後複製，不直接送單。",
     "orders", "建立新客訂單"),
    ("建立儲值金訂單：客人自行儲值／購買金額建單，付款方式與發票自動沿用會員最近一次設定。",
     "orders", "建立儲值金訂單"),
    ("訂單轉換：原單轉多筆新單，各建折價券，混合配班。",
     "orders", "訂單轉換"),
    ("儲值金補價差：兩段式流程，先建儲值金清零單，再建客付補差價單。",
     "orders", "儲值金補價差"),
    # ---------- B. 訂單附屬功能 ----------
    ("取消訂單：依電話、服務月份／日期區間與付款狀態搜尋訂單，處理退款與備註。",
     "orders", "取消訂單"),
    ("VIP 訂單／Google 日曆同步：同時查詢後台訂單與 Google 日曆，支援異動日期／時段、"
     "取消／暫停、新增或修改日曆事件。",
     "orders", "VIP 訂單／Google 日曆同步"),
    ("訂單客服備註：舊客回購備註回填、新成單提醒建立、客服備忘錄整理。",
     "memo", "訂單客服備註"),
    ("儲值獎金備註：搜尋購買項目儲值金、客服備註空白的訂單，依姓名把獎金專員名字加進客服備註。",
     "orders", "儲值獎金備註"),
    ("排班管理：排班匯入、檸檬人空檔查詢、清空排班。",
     "memo", "排班管理"),
    ("評估文字工具：貼入評估內容，自動產生含時數／移除時數兩種版本文字，金額自動計算。",
     "memo", "評估文字工具"),
    # ---------- C. 稽核比對工具 ----------
    ("雙向訂單檢查：Google Sheet vs. 後台，針對已有訂單編號的成單工作表跟後台做雙向比對。",
     "orders", "雙向訂單檢查"),
    ("後台／Google 日曆雙向比對：後台 vs. Google 日曆，以日曆事件時間與顏色為基準做雙向比對。",
     "orders", "後台／Google 日曆雙向比對"),
    ("查詢無LINE連結訂單：搜尋訂購資訊裡沒有LINE連結的訂單，可依訂購／付款／服務日期分別篩選。",
     "orders", "查詢無LINE連結訂單"),
    # ---------- D. LINE 通知／提醒 ----------
    ("LINE 通知產生器：用已成立訂單編號補產生通知訊息，支援多筆同時產生。",
     "orders", "LINE 通知產生器"),
    ("週末服務 LINE 提醒：篩選週末已付款訂單、產生提醒訊息，並追蹤客人是否回覆。",
     "orders", "週末服務 LINE 提醒"),
    ("專員隔日上班提醒：依服務日期篩選已付款訂單、彙整每位專員班次與 LINE 聊天連結。",
     "orders", "專員隔日上班提醒"),
    # ---------- E. 會員／客戶管理 ----------
    ("會員喜好設定：輸入電話查會員，設定喜愛專員性別，並可勾選設為喜愛／不喜愛專員。",
     "orders", "會員喜好設定"),
    ("整理預約下次服務：搜尋評價日期區間內有填「預約下次服務」的評價，整理成一份名單。",
     "orders", "整理預約下次服務"),
    ("更新建議下次服務時間：依地址＋電話查後台最近3次服務日期，寫入 Google Sheet 對應欄位。",
     "orders", "更新建議下次服務時間"),
    # ---------- F. 財務功能 ----------
    ("台北/台中區對帳：ATM 待付款清單查詢、配對銀行明細、更新系統對帳。",
     "memo", "台北/台中區對帳"),
    ("桃園/新竹區對帳：依付款日期、付款狀態搜尋 ATM 訂單，寫入欄位並比對銀行明細，"
     "支援一筆匯款對多筆訂單。",
     "memo", "桃園/新竹區對帳"),
    ("服務異動：車馬費／異動費、服務前後加減時、退款／客訴退款／物損退款，"
     "分階段查詢試算後回填後台。",
     "memo", "服務異動"),
]

# v8.76：上面 6 個改名過的 memo 類項目，內部呼叫 render_memo_system 時仍要
# 用 memo_system/ui.py 原本認得的分類名稱（含 emoji 前綴），才能正確導向
# 對應功能；這裡只是外部選單顯示用的新名稱，不動 memo_system 內部程式。
_MEMO_SECTION_MAP = {
    "訂單客服備註": "📋 客服作業",
    "排班管理": "📅 排班管理",
    "評估文字工具": "📐 評估文字工具",
    "台北/台中區對帳": "💰 財務對帳",
    "桃園/新竹區對帳": "💳 付款後5碼及星和診所比對",
    "服務異動": "🔄 服務異動",
}

# v8.76：在下拉選單裡插入「大類標題列」（不可真的選取，純粹視覺分隔），
# 讓 A~F 六大類在畫面上看得出分界，不用另外拆成兩層選單。標題列前面加
# 「──」跟一般編號選項區分；萬一使用者真的選到標題列，下面會擋下並提示
# 改選功能項目，不會誤跑到任何功能。
_CATEGORY_HEADERS_BY_INDEX = {
    0: "A. 建單／成單流程",
    6: "B. 訂單附屬功能",
    12: "C. 稽核比對工具",
    15: "D. LINE 通知／提醒",
    18: "E. 會員／客戶管理",
    21: "F. 財務功能",
}
_menu_display_options = []
_menu_option_targets = []  # 與 _menu_display_options 一一對應；None 代表該列是標題列
_menu_counter = 0
for _opt_idx, _opt in enumerate(FUNCTION_OPTIONS):
    if _opt_idx in _CATEGORY_HEADERS_BY_INDEX:
        _menu_display_options.append(f"── {_CATEGORY_HEADERS_BY_INDEX[_opt_idx]} ──")
        _menu_option_targets.append(None)
    _menu_counter += 1
    _menu_display_options.append(f"{_menu_counter}. {_opt[0]}")
    _menu_option_targets.append(_opt_idx)
_menu_default_index = next(i for i, t in enumerate(_menu_option_targets) if t is not None)

selected_label = st.selectbox(
    "功能選單",
    _menu_display_options,
    index=_menu_default_index,
    key="unified_function_select",
)
_selected_pos = _menu_display_options.index(selected_label)
_selected_target = _menu_option_targets[_selected_pos]
if _selected_target is None:
    st.info("這是分類標題，請改選下面的功能項目。")
    st.stop()
_selected_option = FUNCTION_OPTIONS[_selected_target]
_system_key, mode = _selected_option[1], _selected_option[2]

st.markdown("<hr>", unsafe_allow_html=True)

if _system_key == "memo":
    # 備忘系統的功能：直接沿用同一組後台帳號/密碼/環境，不再重複顯示登入欄位。
    render_memo_system(
        forced_main_section=_MEMO_SECTION_MAP.get(mode, mode),
        shared_backend_email=backend_email,
        shared_backend_password=backend_password,
        shared_env=env,
    )
    st.stop()

# =========================================================
# v8.74：一般取消訂單
# =========================================================
if mode == "取消訂單":
    from cancel_order import render_cancel_order

    step("3", "取消訂單")
    info_panel("功能說明", [
        "依手機號碼搜尋一般訂單，不限定 VIP。",
        "服務日期可用「月份」或「日期區間」查詢；月份模式會自動帶入該月起日與迄日。",
        "付款狀態可選「已付款」或「待付款」，預設為已付款。",
        "搜尋後可勾選一筆或多筆訂單，再選擇不需退款／待退款／待收異動。",
        "取消時可同時寫入客人備註、加收備註與待退備註。",
    ])
    render_cancel_order(
        backend_email.strip(),
        backend_password.strip(),
        env,
    )
    st.stop()

# =========================================================
# v8.74：VIP 訂單／Google 日曆同步
# =========================================================
if mode == "VIP 訂單／Google 日曆同步":
    import calendar as _calendar
    import vip_calendar_sync as _vcs
    import vip_calendar_patch as _vcp
    from vip_calendar_patch import apply_patch as _apply_patch1
    from vip_calendar_patch2 import apply_patch as _apply_patch2
    from vip_calendar_patch3 import apply_patch as _apply_patch3
    from vip_calendar_patch4 import apply_patch as _apply_patch4
    from vip_calendar_patch5 import apply_patch as _apply_patch5

    # Streamlit 會重跑腳本；同一程序只套一次 patch。
    if not getattr(_vcs, "_ordersapp_vip_patches_applied", False):
        _apply_patch1(_vcs)
        _apply_patch2(_vcs, _vcp)
        _apply_patch3(_vcs, _vcp)
        _apply_patch4(_vcs, _vcp)
        _apply_patch5(_vcs, _vcp)
        _vcs._ordersapp_vip_patches_applied = True

    step("3", "VIP 訂單／Google 日曆同步")
    info_panel("功能說明", [
        "依 VIP 客戶手機號碼及月份／日期區間，同時查詢後台訂單與 Google 日曆。",
        "畫面左側固定為訂單資訊、右側固定為日曆資訊，日期與時段欄位水平對齊。",
        "支援異動日期／時段、取消／暫停、僅新增日曆、先預約再新增日曆及修改日曆資訊。",
        "異動或新增訂單時會先確認後台該日期／時段可用，再進行後續日曆同步。",
        "Google 日曆顏色：紫色＝未安排、黃色＝已安排、綠色＝暫停。",
        "系統不會自行決定訂單應對應哪一筆既有日曆事件；修改既有事件時由使用者自行選擇。",
    ])

    _query_mode = st.radio(
        "查詢方式",
        ["月份", "日期區間"],
        horizontal=True,
        key="vipcal_query_mode",
    )
    _today = date.today()

    if _query_mode == "月份":
        _year_options = list(range(_today.year - 1, _today.year + 3))
        _q1, _q2 = st.columns(2)
        with _q1:
            _query_year = st.selectbox(
                "年份",
                _year_options,
                index=_year_options.index(_today.year),
                key="vipcal_query_year",
            )
        with _q2:
            _query_month = st.selectbox(
                "月份",
                list(range(1, 13)),
                index=_today.month - 1,
                format_func=lambda m: f"{m} 月",
                key="vipcal_query_month",
            )
        _last_day = _calendar.monthrange(int(_query_year), int(_query_month))[1]
        _query_date_s = date(int(_query_year), int(_query_month), 1)
        _query_date_e = date(int(_query_year), int(_query_month), _last_day)
    else:
        _r1, _r2 = st.columns(2)
        with _r1:
            _query_date_s = st.date_input(
                "查詢起日",
                value=_today - timedelta(days=30),
                key="vipcal_range_s",
            )
        with _r2:
            _query_date_e = st.date_input(
                "查詢迄日",
                value=_today + timedelta(days=90),
                key="vipcal_range_e",
            )
        if _query_date_s > _query_date_e:
            st.error("查詢起日不可晚於查詢迄日")
            st.stop()

    st.session_state["vipcal_query_date_s"] = _query_date_s.isoformat()
    st.session_state["vipcal_query_date_e"] = _query_date_e.isoformat()
    st.caption(f"查詢範圍：{_query_date_s.isoformat()} ～ {_query_date_e.isoformat()}")

    _vcs.render_vip_calendar_sync(
        backend_email.strip(),
        backend_password.strip(),
        env,
    )
    st.stop()

# =========================================================
# 模式一：批次建單
# =========================================================
if mode == "批次建單（Google Sheet）":
    step("3", "批次建單")
    info_panel("功能說明", [
        "適合已將多筆訂單整理在 Google Sheet 的批次處理情境。",
        "可依列號建立訂單、寄確認信、改 Google 日曆，並回填結果。",
        "勾自動篩選時，可在輸入的列號範圍內篩出「未安排、訂單編號空白、無班表」或「O欄找不到訂單編號」的列。",
    ])
    info_panel("使用說明", ["先選擇執行區域與工作表名稱。", "輸入要執行的列號，例如 2、2,3,5 或 5-10。", "勾選要執行的項目後按開始執行。"])
    step("4", "執行設定")
    c1, c2, c3 = st.columns(3)
    with c1:
        region = st.selectbox("執行區域", ["台北", "台中", "桃園", "新竹", "高雄"])
    with c2:
        sheet_name = st.text_input("工作表名稱", value="", placeholder="例：202604")
    with c3:
        row_input = st.text_input("執行列號", value="", placeholder="例：2,3,5-7")
    st.markdown('<div class="hint-box">💡 列號支援：單列 <code>2</code>、逗號分隔 <code>2,3,5</code>、區間 <code>2,3,5-7</code></div>', unsafe_allow_html=True)
    st.markdown("<hr>", unsafe_allow_html=True)
    step("3", "執行項目")
    default_actions = (["建單", "寄確認信", "改 Google 日曆"] if env == "prod" else ["建單"])
    selected_actions = st.multiselect("執行項目", options=["建單", "寄確認信", "改 Google 日曆"], default=default_actions, label_visibility="collapsed")
    st.markdown('<div class="hint-box">可自由組合，例如只寄確認信、只改日曆，或全流程一起跑。</div>', unsafe_allow_html=True)
    batch_allow_auto_lemon = st.checkbox("查無班表時自動補檸檬人（不動其他客人已配班專員）", value=False, key="batch_allow_auto_lemon")
    auto_no_slot_rows = st.checkbox("自動篩選：狀態未安排＋訂單編號空白＋無班表", value=False, key="auto_no_slot_rows")
    auto_missing_o_rows = st.checkbox("自動篩選：狀態未安排＋訂單編號空白＋O欄找不到訂單編號", value=False, key="auto_missing_o_rows")
    st.markdown("<hr>", unsafe_allow_html=True)
    run_clicked = st.button("🚀  開始執行", use_container_width=True)
    with st.expander("📄  執行過程", expanded=True):
        log_box = st.empty()
        log_box.text("尚未執行")
    result_container = st.container()
    if run_clicked:
        if not backend_email.strip():
            st.error("請輸入後台帳號"); st.stop()
        if not backend_password.strip():
            st.error("請輸入後台密碼"); st.stop()
        if not sheet_name.strip():
            st.error("請輸入工作表名稱"); st.stop()
        if not selected_actions:
            st.error("請至少選擇一個執行項目"); st.stop()
        if auto_no_slot_rows or auto_missing_o_rows:
            try:
                candidate_rows = parse_row_input(row_input) if row_input.strip() else []
            except Exception as e:
                st.error(f"列號格式錯誤：{e}"); st.stop()
            try:
                target_set = set()
                if auto_no_slot_rows:
                    target_set.update(find_no_slot_rows(sheet_name.strip(), region, candidate_rows))
                if auto_missing_o_rows:
                    target_set.update(find_missing_order_in_o_rows(sheet_name.strip(), region, candidate_rows))
                target_rows = sorted(target_set)
            except Exception as e:
                st.error(f"自動篩選列號失敗：{e}"); st.stop()
            if not target_rows:
                st.info("沒有符合自動篩選條件的列。"); st.stop()
        else:
            try:
                target_rows = parse_row_input(row_input)
            except Exception as e:
                st.error(f"列號格式錯誤：{e}"); st.stop()
        logs = []
        def ui_log(msg):
            logs.append(format_log_message(msg))
            display_text = "\n\n".join(logs[-120:])
            log_box.text(display_text)
        total_success = 0
        total_fail = 0
        total_processed = 0
        with st.spinner("執行中，請稍候…"):
            for row_no in target_rows:
                ui_log(f"▶ 開始執行第 {row_no} 列…")
                try:
                    result = run_process_web(
                        env_name=env, region=region,
                        backend_email=backend_email.strip(), backend_password=backend_password.strip(),
                        sheet_name=sheet_name.strip(), start_row=row_no, end_row=row_no,
                        selected_actions=selected_actions, logger=ui_log,
                        allow_auto_lemon_shift=batch_allow_auto_lemon,
                    )
                    if isinstance(result, dict):
                        total_success += result.get("success_count", 0)
                        total_fail += result.get("fail_count", 0)
                        total_processed += result.get("total_processed", 0)
                except Exception as e:
                    total_fail += 1
                    ui_log(f"❌ 第 {row_no} 列失敗：{e}")
        ui_log("===== 建單流程執行完成 =====")
        ui_log("===== 全部執行完成 =====")

        with result_container:
            st.markdown("<hr>", unsafe_allow_html=True)
            step("4", "執行結果")
            c1, c2, c3 = st.columns(3)
            c1.metric("執行筆數", total_processed)
            c2.metric("成功", total_success)
            c3.metric("失敗", total_fail)
            if total_fail == 0 and total_processed > 0:
                st.success(f"✅ 全部完成，共處理 **{total_processed}** 筆，成功 **{total_success}** 筆。")
            elif total_fail > 0:
                st.warning(f"⚠️ 執行完成，但有 **{total_fail}** 筆失敗，請查看執行過程。")
            else:
                st.info("執行完成，無資料被處理。")



elif mode == "雙向訂單檢查":
    step("3", "雙向訂單檢查")
    info_panel("功能說明", [
        "不用重新跑一次批次建單，直接針對一份已經有「訂單編號」欄位的成單工作表，"
        "跟後台系統做一次雙向比對。",
        "方向一：工作表寫的訂單編號，回查後台是否真的存在，電話/地址/日期/時段是否跟這一列相符。",
        "方向二（加強版，需要填服務日期區間）：不是只查工作表裡已出現的電話，"
        "而是直接抓後台這段日期區間內的『全部』已付款訂單，逐筆核對訂單編號有沒有"
        "出現在工作表裡——這樣才抓得到「客人電話整筆漏登記進工作表」這種情況。",
        "沒有填日期區間的話，方向二只會用舊方式（工作表裡已出現的電話）去查，"
        "抓不到完全沒登記進工作表的訂單，建議務必填上服務日期區間。",
    ])

    dc_sheet_name = st.text_input("工作表名稱", value="", placeholder="例：202604", key="dc_sheet_name")
    dc_region = st.selectbox("只檢查特定區域（不指定則檢查全部）", ["全部"] + list(ACCOUNTS.keys()), key="dc_region")

    st.markdown("**方向二用：服務日期區間**（建議務必填寫，才能抓到工作表完全漏登記的訂單）")
    dc_col1, dc_col2 = st.columns(2)
    with dc_col1:
        dc_date_start = st.date_input("服務日期-起", value=None, key="dc_date_start")
    with dc_col2:
        dc_date_end = st.date_input("服務日期-迄", value=None, key="dc_date_end")

    if st.button("🔍 開始雙向比對", use_container_width=True, key="dc_run_btn", type="primary"):
        if not backend_email.strip() or not backend_password.strip():
            st.error("請先在上方輸入後台帳號密碼")
        elif not dc_sheet_name.strip():
            st.error("請輸入工作表名稱")
        else:
            try:
                with st.spinner("讀取工作表 → 登入後台 → 雙向比對中（有填日期區間的話會多花一點時間掃後台整段期間的訂單）…"):
                    dc_problems = run_standalone_consistency_check(
                        env_name=env,
                        backend_email=backend_email.strip(),
                        backend_password=backend_password.strip(),
                        sheet_name=dc_sheet_name.strip(),
                        region=None if dc_region == "全部" else dc_region,
                        date_range_start=dc_date_start.strftime("%Y-%m-%d") if dc_date_start else None,
                        date_range_end=dc_date_end.strftime("%Y-%m-%d") if dc_date_end else None,
                    )
                st.session_state.dc_result = {"problems": dc_problems, "sheet_name": dc_sheet_name.strip()}
            except Exception as e:
                st.error(f"檢查失敗：{e}")

    dc_result = st.session_state.get("dc_result")
    if dc_result:
        st.markdown("#### 檢查結果")
        _problems = dc_result.get("problems") or []
        if _problems:
            st.error(f"⚠️ 工作表「{dc_result.get('sheet_name')}」發現 {len(_problems)} 筆異常，請人工確認：")
            for _p in _problems:
                _row_label = f"第 {_p.get('row_num')} 列" if _p.get("row_num") is not None else "（系統反查，不是特定一列）"
                st.warning(f"{_row_label}（訂單 {_p.get('order_no', '') or '（無）'}）：{_p.get('issue')}")
        else:
            st.success(f"✅ 工作表「{dc_result.get('sheet_name')}」檢查通過，訂單編號皆與電話/地址/日期/時段相符，後台也沒有查到工作表未記錄的訂單。")

elif mode == "後台／Google 日曆雙向比對":
    step("3", "後台／Google 日曆雙向比對")
    info_panel("功能說明", [
        "以 Google 日曆事件的時間與顏色為比對基準（沿用既有慣例：紫色＝未安排、"
        "黃色＝已安排、綠色＝暫停），只有黃色事件代表「已安排／應該已成單」，"
        "才會拿來跟後台已付款訂單互相比對。",
        "方向一（後台有、日曆沒有）：後台這段服務日期區間內的已付款訂單，"
        "找不到日期／時段完全相符的黃色日曆事件。",
        "方向二（日曆有、後台沒有）：日曆這段期間的黃色事件，找不到日期／時段"
        "相符的後台已付款訂單。",
        "只能比對已設定 Google Calendar ID 的區域（目前為：" + "、".join(GOOGLE_CALENDAR_MAP.keys()) + "）。",
    ])

    cc_date_c1, cc_date_c2 = st.columns(2)
    with cc_date_c1:
        cc_date_s = st.date_input("服務日期-起", value=date.today(), key="cc_date_s")
    with cc_date_c2:
        cc_date_e = st.date_input("服務日期-迄", value=date.today() + timedelta(days=7), key="cc_date_e")
    cc_region = st.selectbox("只檢查特定區域（不指定則檢查全部已設定日曆的區域）", ["全部"] + list(GOOGLE_CALENDAR_MAP.keys()), key="cc_region")

    if st.button("🔍 開始雙向比對", use_container_width=True, key="cc_run_btn", type="primary"):
        if not backend_email.strip() or not backend_password.strip():
            st.error("請先在上方輸入後台帳號密碼")
        elif cc_date_s > cc_date_e:
            st.error("服務日期起日不可晚於迄日")
        else:
            try:
                with st.spinner("登入後台、查詢已付款訂單並讀取 Google 日曆事件，雙向比對中…"):
                    cc_result = run_backend_calendar_consistency_check(
                        env_name=env,
                        backend_email=backend_email.strip(),
                        backend_password=backend_password.strip(),
                        date_range_start=cc_date_s.strftime("%Y-%m-%d"),
                        date_range_end=cc_date_e.strftime("%Y-%m-%d"),
                        region=None if cc_region == "全部" else cc_region,
                    )
                st.session_state.cc_result = cc_result
            except Exception as e:
                st.error(f"檢查失敗：{e}")

    cc_result = st.session_state.get("cc_result")
    if cc_result:
        st.markdown("#### 檢查結果")
        _backend_missing = cc_result.get("backend_missing_in_calendar") or []
        _calendar_missing = cc_result.get("calendar_missing_in_backend") or []
        if not _backend_missing and not _calendar_missing:
            st.success("✅ 檢查通過，後台已付款訂單與 Google 日曆黃色事件皆一一對應。")
        else:
            if _backend_missing:
                st.error(f"⚠️ 後台有、日曆沒有：{len(_backend_missing)} 筆")
                for _p in _backend_missing:
                    st.warning(f"訂單 {_p.get('order_no')}：{_p.get('issue')}")
            if _calendar_missing:
                st.error(f"⚠️ 日曆有、後台沒有：{len(_calendar_missing)} 筆")
                for _p in _calendar_missing:
                    st.warning(_p.get("issue"))
                    if _p.get("event_link"):
                        st.link_button("開啟日曆事件", _p["event_link"], key=f"cc_event_{_p.get('event_link')}")

elif mode == "專員隔日上班提醒":
    step("3", "專員隔日上班提醒")
    info_panel("操作方式", [
        "可設定服務日期區間；只納入已付款訂單，並把同一位專員跨日工作整合成一則訊息。",
        "系統會由專員名單及詳細資料讀取 LINE 連結；勾選名單後逐筆複製訊息並開啟聊天。",
        "此頁使用 LINE 官方帳號管理後台連結，因此由客服確認後人工送出。",
    ])
    cr_date_c1, cr_date_c2 = st.columns(2)
    with cr_date_c1:
        cr_service_date_s = st.date_input(
            "服務日期-起",
            value=date.today() + timedelta(days=1),
            key="cr_service_date_s",
        )
    with cr_date_c2:
        cr_service_date_e = st.date_input(
            "服務日期-迄",
            value=date.today() + timedelta(days=2),
            key="cr_service_date_e",
        )
    if st.button(
        "🔍 查詢已付款訂單並整合專員名單",
        use_container_width=True,
        type="primary",
        key="cr_search",
    ):
        if not backend_email.strip() or not backend_password.strip():
            st.error("請先在上方輸入後台帳號密碼")
        elif cr_service_date_s > cr_service_date_e:
            st.error("服務日期起日不可晚於迄日")
        else:
            try:
                with st.spinner("查詢已付款訂單與專員 LINE 資料…"):
                    _cleaner_rows, _cleaner_debug = find_paid_cleaner_reminders(
                        env,
                        backend_email.strip(),
                        backend_password.strip(),
                        cr_service_date_s.strftime("%Y-%m-%d"),
                        cr_service_date_e.strftime("%Y-%m-%d"),
                    )
                st.session_state.cr_rows = _cleaner_rows
                st.session_state.cr_debug = _cleaner_debug
                st.session_state.pop("cr_editor", None)
            except Exception as e:
                st.error(f"查詢失敗：{e}")

    cr_rows = st.session_state.get("cr_rows")
    if cr_rows is not None:
        _debug = st.session_state.get("cr_debug", {})
        st.caption(
            f"找到 {_debug.get('cleaner_count', 0)} 位專員，"
            f"共 {_debug.get('job_count', 0)} 筆專員工作"
        )
        if _debug.get("hit_page_limit"):
            st.warning("查詢已達 20 頁上限，請確認是否有漏單。")
        if not cr_rows:
            st.success("此服務日期沒有已付款且已排專員的訂單。")
        else:
            cr_select_all = st.checkbox(
                "全選有 LINE 連結的專員（取消勾選可全部取消）",
                value=True,
                key="cr_select_all",
            )
            if st.session_state.get("cr_select_all_previous") != cr_select_all:
                st.session_state.cr_select_all_previous = cr_select_all
                st.session_state.pop("cr_editor", None)
            _cleaner_table = [{
                "選取": bool(cr_select_all and row.get("line_url")),
                "專員": row["name"],
                "工作筆數": len(row["jobs"]),
                "服務日期": "、".join(sorted({
                    job.get("service_date", "") for job in row["jobs"]
                    if job.get("service_date")
                })),
                "LINE狀態": "已有連結" if row.get("line_url") else "查無連結",
            } for row in cr_rows]
            _cleaner_edited = st.data_editor(
                _cleaner_table,
                hide_index=True,
                use_container_width=True,
                disabled=["專員", "工作筆數", "服務日期", "LINE狀態"],
                key="cr_editor",
            )
            _cleaner_records = (
                _cleaner_edited.to_dict("records")
                if hasattr(_cleaner_edited, "to_dict")
                else list(_cleaner_edited or [])
            )
            _selected_names = {
                row["專員"] for row in _cleaner_records if row.get("選取")
            }
            st.markdown("#### 專員提醒訊息")
            for _idx, _row in enumerate(cr_rows):
                if _row["name"] not in _selected_names:
                    continue
                with st.expander(
                    f"{_row['name']}｜{len(_row['jobs'])} 筆工作｜"
                    f"{'已有 LINE' if _row.get('line_url') else '查無 LINE'}"
                ):
                    _message = st.text_area(
                        "訊息",
                        _row["message"],
                        height=260,
                        key=(
                            f"cr_msg_{_row['name']}_"
                            f"{_row['service_date_s']}_{_row['service_date_e']}"
                        ),
                    )
                    copy_button("複製訊息", _message, f"cr_copy_{_idx}")
                    if _row.get("line_url"):
                        st.link_button("開啟專員 LINE 聊天", _row["line_url"])
                    else:
                        st.warning("專員詳細資料沒有 LINE 連結，請改用電話聯絡。")

elif mode == "週末服務 LINE 提醒":
    step("3", "週末服務 LINE 提醒")
    info_panel("建議流程", [
        "在畫面顯示的『建議執行日』查詢名單；系統只列服務日期區間內的已付款訂單。",
        "名單中的『新增』代表尚未寫入追蹤表；『已存在』代表訂單編號已記錄。",
        "勾選後按『儲存勾選名單』，只會寫入 Google Sheet，不會發送 LINE。",
        "需要通知時請開啟 LINE、複製訊息並由客服人工送出。",
        "客人回覆後改為『已回覆』；當天下班前仍未回覆者改為『需追蹤』。",
        "追蹤狀態會保存到既有 Google 試算表的『週末服務提醒』分頁。",
    ])
    _default_sat, _default_sun = upcoming_weekend()
    try:
        from memo_system.change_order import TAIWAN_PUBLIC_HOLIDAYS
        _holidays = TAIWAN_PUBLIC_HOLIDAYS
    except Exception:
        _holidays = set()
    _suggested_run_day = previous_workday(_default_sat, _holidays)
    st.info(f"建議執行日：{_suggested_run_day.strftime('%Y-%m-%d')}；預設服務區間：{_default_sat}～{_default_sun}")
    st.caption("此頁不會透過程式發送 LINE；只保存勾選名單與人工追蹤狀態。")

    st.markdown("**服務日期區間**")
    wr_c1, wr_c2 = st.columns(2)
    with wr_c1:
        wr_date_s = st.date_input("服務日期-起", value=_default_sat, key="wr_date_s")
    with wr_c2:
        wr_date_e = st.date_input("服務日期-迄", value=_default_sun, key="wr_date_e")

    if st.button("🔍 查詢已付款名單", use_container_width=True, type="primary", key="wr_search"):
        if not backend_email.strip() or not backend_password.strip():
            st.error("請先在上方輸入後台帳號密碼")
        elif wr_date_s > wr_date_e:
            st.error("服務日期起日不可晚於迄日")
        else:
            try:
                with st.spinner("登入後台並查詢已付款訂單…"):
                    _orders, _debug = find_paid_weekend_orders(
                        env, backend_email.strip(), backend_password.strip(),
                        wr_date_s.strftime("%Y-%m-%d"), wr_date_e.strftime("%Y-%m-%d"),
                    )
                    _tracking = load_tracking_rows()
                st.session_state.wr_rows = merge_tracking_rows(_orders, _tracking)
                st.session_state.wr_debug = _debug
                st.session_state.pop("wr_editor", None)
            except Exception as e:
                st.error(f"查詢失敗：{e}")

    wr_rows = st.session_state.get("wr_rows")
    if wr_rows is not None:
        _debug = st.session_state.get("wr_debug", {})
        st.caption(f"後台：{_debug.get('base_url', '')}｜找到 {len(wr_rows)} 筆已付款服務")
        if _debug.get("hit_page_limit"):
            st.warning("查詢已達 20 頁上限，請縮小日期範圍後再查，避免漏單。")
        if not wr_rows:
            st.success("此服務日期區間沒有已付款訂單。")
        else:
            wr_select_all = st.checkbox(
                "全選名單（取消勾選可全部取消）",
                value=False,
                key="wr_select_all",
            )
            if st.session_state.get("wr_select_all_previous") != wr_select_all:
                st.session_state.wr_select_all_previous = wr_select_all
                st.session_state.pop("wr_editor", None)
            _editable = [
                {
                    "選取": wr_select_all,
                    **{k: v for k, v in row.items() if k != "LINE訊息"},
                }
                for row in wr_rows
            ]
            _edited = st.data_editor(
                _editable, use_container_width=True, hide_index=True, key="wr_editor",
                column_order=[
                    "選取", "資料狀態", "訂單編號", "服務日期", "姓名",
                    "通知狀態", "通知時間",
                    "回覆狀態", "回覆時間", "LINE",
                    "服務時間", "電話", "地址", "LINE ID",
                    "回覆備註", "發送錯誤", "最後更新",
                ],
                disabled=[
                    "訂單編號", "服務日期", "服務時間", "姓名", "電話", "地址",
                    "LINE", "LINE ID", "資料狀態", "通知時間", "回覆時間",
                    "發送錯誤", "最後更新",
                ],
                column_config={
                    "選取": st.column_config.CheckboxColumn("儲存", help="只儲存勾選訂單，不會發送 LINE"),
                    "資料狀態": st.column_config.TextColumn(
                        "資料狀態", help="新增＝Google Sheet 尚無此訂單編號；已存在＝將更新原列，不會重複新增。",
                    ),
                    "LINE": st.column_config.LinkColumn("LINE", display_text="開啟聊天"),
                    "LINE ID": st.column_config.TextColumn("LINE ID", help="由 LINE 聊天網址／客人回覆自動記錄"),
                    "通知狀態": st.column_config.SelectboxColumn("通知狀態", options=NOTICE_STATUSES, required=True),
                    "通知時間": st.column_config.TextColumn(
                        "實際發送時間",
                        help="客服人工確認已送出後，將通知狀態改為「已通知」並儲存時自動記錄。",
                    ),
                    "回覆狀態": st.column_config.SelectboxColumn("回覆狀態", options=REPLY_STATUSES, required=True),
                },
            )
            _edited_records = _edited.to_dict("records") if hasattr(_edited, "to_dict") else _edited
            _message_by_order = {row["訂單編號"]: row.get("LINE訊息", "") for row in wr_rows}
            _rows_with_messages = [
                {**row, "LINE訊息": _message_by_order.get(row.get("訂單編號"), "")}
                for row in _edited_records
            ]

            if st.button(
                "💾 儲存勾選名單（不發送 LINE）",
                use_container_width=True,
                type="primary",
                key="wr_save_selected",
            ):
                _selected = [row for row in _rows_with_messages if row.get("選取")]
                if not _selected:
                    st.warning("請至少勾選一筆訂單。")
                else:
                    try:
                        _new_count = sum(row.get("資料狀態") == "新增" for row in _selected)
                        _updated_count = len(_selected) - _new_count
                        save_tracking_rows(_selected)
                        _selected_order_nos = {
                            row.get("訂單編號") for row in _selected
                        }
                        for row in _edited_records:
                            if row.get("訂單編號") in _selected_order_nos:
                                row["資料狀態"] = "已存在"
                        st.session_state.wr_rows = [
                            {**row, "LINE訊息": _message_by_order.get(row.get("訂單編號"), "")}
                            for row in _edited_records
                        ]
                        st.success(
                            f"已儲存 {len(_selected)} 筆：新增 {_new_count} 筆、"
                            f"更新 {_updated_count} 筆；同訂單編號不會重複。"
                        )
                    except Exception as e:
                        st.error(f"儲存失敗：{e}")

            if st.button("💾 儲存通知／回覆狀態", use_container_width=True, key="wr_save"):
                try:
                    count = save_tracking_rows(_edited_records)
                    st.success(f"已保存 {count} 筆追蹤狀態。")
                except Exception as e:
                    st.error(f"儲存失敗：{e}")

            copy_button(
                "複製追蹤紀錄（貼到 Google Sheets 會自動分欄）",
                tracking_rows_tsv(_edited_records),
                "wr_copy_tracking",
            )

            st.markdown("#### LINE 提醒訊息")
            for _idx, _row in enumerate(wr_rows):
                with st.expander(f"{_row['服務日期']} {_row['服務時間']}｜{_row['姓名']}｜{_row['訂單編號']}"):
                    st.text_area("訊息", _row["LINE訊息"], height=220, key=f"wr_msg_{_row['訂單編號']}")
                    copy_button("複製訊息", _row["LINE訊息"], f"wr_copy_{_idx}")
                    if _row.get("LINE"):
                        st.link_button("開啟 LINE 聊天", _row["LINE"])
                    else:
                        st.warning("此訂單沒有 LINE 聊天連結，請改用電話聯絡。")

elif mode == "查詢無LINE連結訂單":
    step("3", "查詢無LINE連結訂單")
    info_panel("功能說明", [
        "搜尋訂購資訊裡沒有LINE連結的訂單，列出訂單編號/姓名/電話。",
        "三種日期區間都可以留空不篩，訂購日期/付款日期/服務日期各自獨立，"
        "可以只填其中一種，也可以同時填多種（會同時套用）。",
    ])

    st.markdown("**訂購日期區間**")
    nl_col1, nl_col2 = st.columns(2)
    with nl_col1:
        nl_date_s = st.date_input("訂購日期-起", value=None, key="nl_date_s")
    with nl_col2:
        nl_date_e = st.date_input("訂購日期-迄", value=None, key="nl_date_e")

    st.markdown("**付款日期區間**")
    nl_col3, nl_col4 = st.columns(2)
    with nl_col3:
        nl_paid_s = st.date_input("付款日期-起", value=None, key="nl_paid_s")
    with nl_col4:
        nl_paid_e = st.date_input("付款日期-迄", value=None, key="nl_paid_e")

    st.markdown("**服務日期區間**")
    nl_col5, nl_col6 = st.columns(2)
    with nl_col5:
        nl_clean_s = st.date_input("服務日期-起", value=None, key="nl_clean_s")
    with nl_col6:
        nl_clean_e = st.date_input("服務日期-迄", value=None, key="nl_clean_e")

    if st.button("🔍 開始搜尋", use_container_width=True, key="nl_run_btn", type="primary"):
        if not backend_email.strip() or not backend_password.strip():
            st.error("請先在上方輸入後台帳號密碼")
        else:
            try:
                with st.spinner("登入後台 → 搜尋訂單中（依篩選範圍大小，可能需要一點時間）…"):
                    nl_results, nl_debug = find_orders_without_line_link(
                        env_name=env,
                        backend_email=backend_email.strip(),
                        backend_password=backend_password.strip(),
                        date_s=nl_date_s.strftime("%Y-%m-%d") if nl_date_s else None,
                        date_e=nl_date_e.strftime("%Y-%m-%d") if nl_date_e else None,
                        paid_at_s=nl_paid_s.strftime("%Y-%m-%d") if nl_paid_s else None,
                        paid_at_e=nl_paid_e.strftime("%Y-%m-%d") if nl_paid_e else None,
                        clean_date_s=nl_clean_s.strftime("%Y-%m-%d") if nl_clean_s else None,
                        clean_date_e=nl_clean_e.strftime("%Y-%m-%d") if nl_clean_e else None,
                        return_debug=True,
                    )
                st.session_state.nl_results = nl_results
                st.session_state.nl_debug = nl_debug
            except Exception as e:
                st.error(f"搜尋失敗：{e}")

    nl_results = st.session_state.get("nl_results")
    nl_debug = st.session_state.get("nl_debug")
    if nl_debug is not None:
        st.caption(
            f"🔧 除錯資訊：環境＝{nl_debug['env']}，實際連線＝{nl_debug['base_url']}，"
            f"後台掃描到候選訂單 {nl_debug['scanned_candidates']} 筆，"
            f"符合「沒有LINE連結」{nl_debug['matched_without_line']} 筆。"
            "（如果候選訂單是 0 筆，代表問題出在登入/篩選這一關，不是真的都有 LINE 連結）"
        )
        if nl_debug.get("hit_page_limit"):
            st.warning(
                f"⚠️ 掃描撞到頁數上限（80 頁）就停了，代表符合篩選條件的候選訂單可能還有更多"
                "沒掃到，結果可能不完整。建議縮小日期範圍，或請 Claude 調高 max_pages。"
            )
    if nl_results is not None:
        if nl_results:
            st.warning(f"⚠️ 找到 {len(nl_results)} 筆沒有LINE連結的訂單：")
            st.dataframe(
                [{"訂單編號": r["order_no"], "姓名": r["name"], "電話": r["phone"]} for r in nl_results],
                use_container_width=True, hide_index=True,
            )
        else:
            st.success("✅ 這個篩選範圍內的訂單都有LINE連結。")

elif mode == "儲值獎金備註":
    step("3", "儲值獎金備註")
    info_panel("功能說明", [
        "同一個功能內完成「搜尋儲值金訂單 → 確認名單 → 套用獎金客服備註」。",
        "搜尋結果會暫存在畫面狀態裡，確認獎金內容後可直接套用，不需要再重新搜尋一次。",
        "套用時會依姓名比對，把「獎金：獎金人員1X獎金人員2」加進該筆訂單的客服備註，保留原本內容，並把服務狀態改為「已處理」。",
    ])

    st.markdown("**訂購日期區間**")
    bn_col1, bn_col2 = st.columns(2)
    with bn_col1:
        bn_date_s = st.date_input("訂購日期-起", value=None, key="bn_date_s")
    with bn_col2:
        bn_date_e = st.date_input("訂購日期-迄", value=None, key="bn_date_e")

    st.markdown("**付款日期區間**")
    bn_col3, bn_col4 = st.columns(2)
    with bn_col3:
        bn_paid_s = st.date_input("付款日期-起", value=None, key="bn_paid_s")
    with bn_col4:
        bn_paid_e = st.date_input("付款日期-迄", value=None, key="bn_paid_e")

    bn_status_map = {
        "待付款": "0", "已付款": "1",
        "待付款＋已付款": ["0", "1"],
    }
    bn_status_label = st.selectbox("付款狀態", list(bn_status_map.keys()), index=1, key="bn_status")

    if st.button("🔍 搜尋儲值金訂單", use_container_width=True, key="bn_search_btn", type="primary"):
        st.session_state.bn_apply_results = []
        st.session_state.bn_parse_errors = []
        if not backend_email.strip() or not backend_password.strip():
            st.error("請先在上方輸入後台帳號密碼")
        else:
            try:
                with st.spinner("登入後台 → 搜尋客服備註空白的儲值金訂單中…"):
                    bn_results, bn_debug = find_pending_stored_value_orders(
                        env_name=env,
                        backend_email=backend_email.strip(),
                        backend_password=backend_password.strip(),
                        date_s=bn_date_s.strftime("%Y-%m-%d") if bn_date_s else None,
                        date_e=bn_date_e.strftime("%Y-%m-%d") if bn_date_e else None,
                        paid_at_s=bn_paid_s.strftime("%Y-%m-%d") if bn_paid_s else None,
                        paid_at_e=bn_paid_e.strftime("%Y-%m-%d") if bn_paid_e else None,
                        purchase_status=bn_status_map[bn_status_label],
                        notice_status="blank",
                        return_debug=True,
                    )
                st.session_state.bn_results = bn_results
                st.session_state.bn_debug = bn_debug
                st.session_state.bn_search_meta = {
                    "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "date_s": bn_date_s.strftime("%Y-%m-%d") if bn_date_s else "",
                    "date_e": bn_date_e.strftime("%Y-%m-%d") if bn_date_e else "",
                    "paid_at_s": bn_paid_s.strftime("%Y-%m-%d") if bn_paid_s else "",
                    "paid_at_e": bn_paid_e.strftime("%Y-%m-%d") if bn_paid_e else "",
                    "purchase_status": bn_status_label,
                }
            except Exception as e:
                st.error(f"搜尋失敗：{e}")

    bn_results = st.session_state.get("bn_results")
    bn_debug = st.session_state.get("bn_debug")
    bn_search_meta = st.session_state.get("bn_search_meta") or {}

    if bn_debug is not None:
        st.caption(
            f"🔧 除錯資訊：後台掃描到候選訂單 {bn_debug['scanned_candidates']} 筆，"
            f"符合條件（客服備註空白）{bn_debug['matched']} 筆。"
        )
        if bn_debug.get("hit_page_limit"):
            st.warning("⚠️ 掃描撞到頁數上限（80 頁）就停了，結果可能不完整，建議縮小日期範圍。")

    if bn_results is not None:
        st.markdown("#### 搜尋結果")
        if bn_search_meta.get("time"):
            st.caption(
                f"使用搜尋結果：{len(bn_results)} 筆｜搜尋時間：{bn_search_meta.get('time')}｜"
                f"付款狀態：{bn_search_meta.get('purchase_status', '')}"
            )

        if not bn_results:
            st.info("這個篩選範圍內沒有客服備註空白的儲值金訂單。")
        else:
            st.success(f"✅ 找到 {len(bn_results)} 筆客服備註空白的儲值金訂單：")
            st.dataframe(
                [
                    {
                        "訂單編號": r["order_no"],
                        "客戶姓名": r["name"],
                        "電話": r.get("phone", ""),
                        "付款狀態": r.get("purchase_status", ""),
                        "客服備註": r.get("notice", ""),
                    }
                    for r in bn_results
                ],
                use_container_width=True,
                hide_index=True,
            )

    st.markdown("**貼上獎金名單**（格式：客戶姓名：獎金人員1X獎金人員2，一行一筆）")
    bn_mapping_text = st.text_area(
        "獎金名單", height=150, key="bn_mapping_text",
        placeholder="李怡萱：李佩蓉X宋品鈞\n王小明：陳大文X林小華",
    )

    if st.button("✅ 套用到上方搜尋結果", use_container_width=True, key="bn_apply_btn", type="primary"):
        if bn_results is None:
            st.error("請先按「搜尋儲值金訂單」，確認名單後再套用。")
        elif not bn_results:
            st.error("目前搜尋結果沒有可套用的訂單。")
        elif not bn_mapping_text.strip():
            st.error("請先貼上獎金名單")
        elif not backend_email.strip() or not backend_password.strip():
            st.error("請先在上方輸入後台帳號密碼")
        else:
            name_to_order = {r["name"]: r for r in bn_results if r.get("name")}
            mapping = []
            parse_errors = []
            for line in bn_mapping_text.splitlines():
                line = line.strip()
                if not line:
                    continue
                sep = "：" if "：" in line else (":" if ":" in line else None)
                if not sep:
                    parse_errors.append(f"❌ {line}：格式錯誤，找不到「：」分隔")
                    continue
                cust_name, bonus_part = line.split(sep, 1)
                cust_name = cust_name.strip()
                bonus_names = [n.strip() for n in re.split(r"[XxＸ]", bonus_part.strip()) if n.strip()]
                matched = name_to_order.get(cust_name)
                if not matched:
                    parse_errors.append(f"❌ {line}：上方搜尋結果裡找不到客戶「{cust_name}」")
                    continue
                if not bonus_names:
                    parse_errors.append(f"❌ {line}：沒有解析到獎金人員名字")
                    continue
                mapping.append({
                    "order_no": matched["order_no"],
                    "edit_id": matched.get("edit_id", ""),
                    "cust_name": cust_name,
                    "bonus_names": bonus_names,
                })

            apply_results = []
            if mapping:
                try:
                    with st.spinner("寫入客服備註中…"):
                        apply_results = apply_bonus_notes(env, backend_email.strip(), backend_password.strip(), mapping)
                except Exception as e:
                    st.error(f"套用失敗：{e}")
            st.session_state.bn_apply_results = apply_results
            st.session_state.bn_parse_errors = parse_errors

    for err in st.session_state.get("bn_parse_errors", []) or []:
        st.error(err)

    bn_apply_results = st.session_state.get("bn_apply_results")
    if bn_apply_results:
        st.markdown("#### 套用結果")
        for r in bn_apply_results:
            if r["ok"]:
                st.success(f"✅ {r['order_no']}（{r['cust_name']}）：已寫入「獎金：{'X'.join(r['bonus_names'])}」，服務狀態已改為已處理")
            else:
                st.error(f"❌ {r['order_no']}（{r['cust_name']}）：{r['msg']}")


# =========================================================
# 其他功能
# =========================================================
else:
    single_feature = mode
    step("3", single_feature)

    # --------------------------------------------------
    # LINE 通知產生器
    # --------------------------------------------------
    if single_feature == "LINE 通知產生器":
        col_left, col_right = st.columns([3, 1])
        with col_left:
            info_panel("使用說明", ["輸入已成立訂單編號，每行一個，可一次輸入多筆。", "系統讀取訂單日期、地址、付款方式與金額，區域由地址自動判斷。"])
            line_order_nos_input = st.text_area("訂單編號（每行一個）", value="", height=120, placeholder="LC00211537\nLC00211538", key="line_order_nos")
            if st.button("產生 LINE 訊息", use_container_width=True, key="make-line-from-order-no"):
                if not backend_email.strip() or not backend_password.strip():
                    st.error("請先輸入後台帳號密碼")
                else:
                    raw_lines = [x.strip() for x in line_order_nos_input.splitlines() if x.strip()]
                    order_groups = []
                    for line in raw_lines:
                        nos = [n.strip() for n in line.split(",") if n.strip()]
                        if nos:
                            order_groups.append(nos)
                    if not order_groups:
                        st.error("請輸入至少一個訂單編號")
                    else:
                        st.session_state.line_from_order_nos_results = []
                        for _k in list(st.session_state.keys()):
                            if _k.startswith("line_text_") or _k.startswith("nj_memo_"):
                                del st.session_state[_k]
                        results_list = []
                        for nos in order_groups:
                            label = "、".join(nos)
                            try:
                                with st.spinner(f"查詢訂單 {label}…"):
                                    line_result, line_text = build_combined_line_message_from_order_nos(
                                        env_name=env, backend_email=backend_email.strip(),
                                        backend_password=backend_password.strip(), order_nos=nos,
                                    )
                                safe_result = {k: v for k, v in line_result.items() if k != "session"}
                                results_list.append({"order_no": label, "result": safe_result, "text": line_text, "error": None})
                            except Exception as e:
                                results_list.append({"order_no": label, "result": None, "text": "", "error": str(e)})
                        st.session_state.line_from_order_nos_results = results_list
                        st.rerun()
        with col_right:
            st.markdown('<div class="sec-label">N-J Memo</div>', unsafe_allow_html=True)
            st.text_area("N-J Memo", NJ_MEMO, height=220, key="nj_memo_fixed", label_visibility="collapsed")
            copy_button("複製 N-J Memo", NJ_MEMO, "copy-nj-memo-fixed")
        results_list = st.session_state.get("line_from_order_nos_results", [])
        for idx, item in enumerate(results_list):
            if item["error"]:
                st.error(f"訂單 {item['order_no']} 產生失敗：{item['error']}")
                continue
            line_result = item["result"]
            line_text = item["text"]
            all_nos = line_result.get("all_order_nos") or [line_result.get("order_no")]
            order_no_display = "、".join(str(n) for n in all_nos if n)
            is_combined = len(all_nos) > 1
            is_multi_date = line_result.get("multi_date", False)
            combined_note = "　⚠️ 跨日合併單" if (is_combined and is_multi_date) else ("　⚠️ 同日合併單" if is_combined else "")
            st.caption(f"訂單：{order_no_display}{combined_note}　付款方式：{line_result.get('payway')}　區域：{line_result.get('region')}　金額：{line_result.get('service_amount') or '—'}　車馬費：{line_result.get('fare') or '0'}")
            st.text_area(f"LINE 訊息（{line_result.get('order_no')}）", line_text, height=380, label_visibility="collapsed")
            copy_button("複製 LINE 訊息", line_text, f"copy-line-msg-{idx}")
            if idx < len(results_list) - 1:
                st.markdown("<hr>", unsafe_allow_html=True)

    # --------------------------------------------------
    # 建立舊客訂單
    # --------------------------------------------------
    elif single_feature == "建立舊客訂單":
        info_panel("功能說明", ["用電話查詢會員與歷史已付款服務。", "多地址客人會顯示各地址近一年紀錄，請先跟客人確認地址。", "可選已知日期查班表，也可依客人需求搜尋可服務日期。"])
        q1, q2 = st.columns(2)
        with q1:
            q_phone = st.text_input("客人電話", key="old_phone")
        with q2:
            q_clean_type = st.selectbox("購買項目", list(CLEAN_TYPE_ID_MAP.keys()), key="old_clean_type")
        if st.button("🔍  查詢會員", use_container_width=True, key="old_lookup_btn"):
            if not backend_email.strip() or not backend_password.strip():
                st.error("請先輸入後台帳號密碼"); st.stop()
            if not q_phone.strip():
                st.error("請輸入客人電話"); st.stop()
            try:
                with st.spinner("查詢中…"):
                    st.session_state.q_lookup = quick_lookup_member(env_name=env, backend_email=backend_email.strip(), backend_password=backend_password.strip(), phone=q_phone.strip(), clean_type_id=CLEAN_TYPE_ID_MAP[q_clean_type])
                st.session_state.q_order_result = {}
            except Exception as e:
                st.error(f"查詢失敗：{e}")
                st.session_state.q_lookup = None
        lookup = st.session_state.get("q_lookup")
        if lookup is not None:
            member_payload = lookup.get("member_payload")
            st.markdown("<hr>", unsafe_allow_html=True)
            if not member_payload:
                st.warning("查無此會員，請填寫下方資料建立新客訂單。")
                st.markdown("**新客資料**")
                nc1, nc2, nc3 = st.columns(3)
                with nc1:
                    nc_name = st.text_input("姓名", key="nc_name")
                with nc2:
                    nc_email = st.text_input("Email", key="nc_email")
                with nc3:
                    nc_tel = st.text_input("市內電話（選填）", key="nc_tel")
                nc_address = st.text_input("服務地址", key="nc_address")
                na1, na2, na3, na4 = st.columns(4)
                with na1:
                    nc_date = st.date_input("服務日期", value=date.today() + timedelta(days=1), key="nc_date")
                with na2:
                    nc_period = st.selectbox("時段", PERIOD_OPTIONS, key="nc_period")
                with na3:
                    nc_person = st.number_input("人數", min_value=1, max_value=8, value=2, key="nc_person")
                with na4:
                    nc_hour = PERIOD_HOUR_MAP.get(nc_period, 3)
                    st.markdown(f"<br><b>{nc_hour} 小時</b>", unsafe_allow_html=True)
                nb1, nb2 = st.columns(2)
                with nb1:
                    nc_payway = st.selectbox("付款方式", ["信用卡", "ATM"], key="nc_payway")
                with nb2:
                    nc_invoice = st.selectbox("發票", ["會員載具（email）", "手機載具", "三聯式統編"], key="nc_invoice")
                nc_carrier = ""
                nc_company_title = ""
                nc_company_no = ""
                if nc_invoice == "手機載具":
                    nc_carrier = st.text_input("手機條碼", placeholder="/ABC1234", key="nc_carrier")
                elif nc_invoice == "三聯式統編":
                    nci1, nci2 = st.columns(2)
                    with nci1:
                        nc_company_title = st.text_input("公司抬頭", key="nc_company_title")
                    with nci2:
                        nc_company_no = st.text_input("統一編號", key="nc_company_no")
                nc_clean_type = st.selectbox("服務類別", list(CLEAN_TYPE_ID_MAP.keys()), key="nc_clean_type")
                nc_allow_auto_lemon = st.checkbox("查無班表時自動補檸檬人（不動其他客人已配班專員）", value=False, key="nc_allow_auto_lemon")
                if st.button("🚀 建立新客訂單", use_container_width=True, key="nc_create_btn"):
                    # v8.15：開始新的一次建單嘗試前，先清空上一次殘留在畫面下方的舊結果，
                    # 避免這次失敗時，舊的成功訊息還留在畫面上跟新的錯誤訊息重疊混淆。
                    st.session_state.q_order_result = {}
                    if not nc_name.strip() or not nc_email.strip() or not nc_address.strip():
                        st.error("請填寫姓名、Email、服務地址")
                    elif not backend_email.strip() or not backend_password.strip():
                        st.error("請先輸入後台帳號密碼")
                    else:
                        try:
                            with st.spinner("建立會員 → 查詢地址 → 建立訂單…"):
                                nc_result = qo.quick_create_new_customer_order(
                                    env_name=env,
                                    backend_email=backend_email.strip(),
                                    backend_password=backend_password.strip(),
                                    allow_auto_lemon_shift=nc_allow_auto_lemon,
                                    customer={
                                        "name": nc_name.strip(),
                                        "phone": q_phone.strip(),
                                        "email": nc_email.strip(),
                                        "tel": nc_tel.strip(),
                                        "address": nc_address.strip(),
                                        "payway": nc_payway,
                                        "clean_type_id": CLEAN_TYPE_ID_MAP[nc_clean_type],
                                        "date_s": nc_date.strftime("%Y-%m-%d"),
                                        "period_s": nc_period,
                                        "hour": str(nc_hour),
                                        "person": str(int(nc_person)),
                                        "carrier": nc_carrier,
                                        "company_title": nc_company_title,
                                        "company_no": nc_company_no,
                                    }
                                )
                                # 不立即發確認信，等 user 確認後再發
                                nc_result["mail_sent"] = False
                                nc_result["mail_msg"] = "尚未發送"
                            st.session_state.q_order_result = nc_result
                            if nc_result.get("lemon_assignment_ok") is False:
                                st.error(nc_result.get("lemon_assignment_warning") or "訂單已建立，但樸檬人置換失敗，請先處理班表。")
                            else:
                                st.success(f"✅ 訂單建立成功：{nc_result['order_no']}")
                        except Exception as e:
                            st.error(f"建單失敗：{e}")
            else:
                member = member_payload.get("member", {})
                addr_list = member_payload.get("member", {}).get("memberAddressList", [])
                addr_options = [a.get("address", "") for a in addr_list if a.get("address")]
                st.markdown(f"**會員姓名：** {member.get('name', '')}　|　**會員電話：** {lookup.get('phone', '')}")
                step("3", "舊客服務資訊")
                info_panel("使用說明", ["先確認服務地址。", "確認服務類別、付款方式與區域。", "依客人狀況選擇『已知日期』或『依需求搜尋』。"])
                if not addr_options:
                    # v2026.07.06 修正：原本會員沒有留存地址就直接擋下、要求改走
                    # 新客建單，但後端（quick_create_order／quick_check_available_slots）
                    # 現在已經支援舊客約新地址，這裡改成給一個文字輸入框讓客服直接輸入。
                    st.warning("此會員沒有留存地址，請直接輸入本次服務的新地址。")
                    q_address = st.text_input("服務地址（新地址）", key="old_address_new_only").strip()
                    last_summary = None
                else:
                    last_summary = get_last_paid_summary(lookup["session"], lookup["phone"], member_payload, addr_options)
                    default_addr_index = addr_options.index(last_summary["address"]) if last_summary and last_summary.get("address") in addr_options else 0
                    NEW_ADDRESS_OPTION = "➕ 輸入新地址（不在下面清單裡）"
                    q_address_choice = st.selectbox(
                        "服務地址", addr_options + [NEW_ADDRESS_OPTION],
                        index=default_addr_index, key="old_address",
                    )
                    if q_address_choice == NEW_ADDRESS_OPTION:
                        # v2026.07.06 修正：原本這裡只能從會員既有地址清單挑選，
                        # 舊客要約沒約過的新地址完全沒有輸入管道，只能被迫走新客
                        # 建單流程。現在加一個「輸入新地址」選項，選了之後給文字
                        # 輸入框，讓客服直接打新地址，後端會用 geocode+查詢區域
                        # 的方式處理（跟新客建單新地址邏輯一致）。
                        q_address = st.text_input("新服務地址", key="old_address_new").strip()
                    else:
                        q_address = q_address_choice
                if not q_address:
                    st.info("請輸入或選擇服務地址。")
                elif True:
                    if len(addr_options) > 1:
                        st.caption(f"⚠️ 此客人留存 {len(addr_options)} 個地址，請務必跟客人確認本次地點是否正確。")
                        per_addr_summary = get_last_paid_per_address(lookup["session"], lookup["phone"], member_payload, addr_options, within_days=365)
                        addr_rows = []
                        for addr in addr_options:
                            info = per_addr_summary.get(addr)
                            if not info:
                                addr_rows.append(f"・{addr}　——　近一年內查無已付款服務紀錄")
                            else:
                                ph_text = f"{info['person']}人{info['hour']}小時" if (info["person"] or info["hour"]) else "未知"
                                payment_text = payment_invoice_display(info.get("payway"), info.get("invoice_text"))
                                addr_rows.append(f"・{addr}　——　{info['date']} {info['time']}　類別：{info['clean_type'] or '未知'}　人時：{ph_text}　{payment_text}")
                        st.markdown('<div class="hint-box">📍 <b>各地址近一年內最近一次已付款服務</b>：<br>' + "<br>".join(addr_rows) + '</div>', unsafe_allow_html=True)
                    default_clean_type = last_summary["clean_type"] if last_summary and last_summary.get("clean_type") in CLEAN_TYPE_ID_MAP else "居家清潔"
                    default_person = int(last_summary["person"]) if last_summary and str(last_summary.get("person", "")).isdigit() else 2
                    q_clean_type_confirm = st.selectbox("服務類別", list(CLEAN_TYPE_ID_MAP.keys()), index=list(CLEAN_TYPE_ID_MAP.keys()).index(default_clean_type), key="old_clean_confirm")
                    # v8.63：付款方式混合選項改為「信用卡/ATM/儲值金」——維持上次付款方式
                    # 選單顯示：信用卡/ATM/儲值金、信用卡、ATM、儲值金
                    # 實際送單時一律解析成「信用卡」「ATM」或「儲值金」三者之一
                    _payway_ui_options = ["信用卡/ATM/儲值金", "信用卡", "ATM", "儲值金"]
                    _last_payway = last_summary.get("payway") if last_summary else ""
                    _default_ui_payway = "信用卡/ATM/儲值金"
                    _q_payway_ui = st.selectbox(
                        "付款方式",
                        _payway_ui_options,
                        index=_payway_ui_options.index(_default_ui_payway),
                        key="old_payway",
                    )
                    if _q_payway_ui == "信用卡/ATM/儲值金":
                        # 沿用上次付款方式；若查無可用紀錄，預設信用卡
                        q_payway = _last_payway if _last_payway in ("信用卡", "ATM", "儲值金") else "信用卡"
                        _payway_note = f"（沿用上次：{q_payway}）"
                    else:
                        q_payway = _q_payway_ui
                        _payway_note = ""
                    q_region = get_region_by_address(q_address, ACCOUNTS) or "台北"
                    _route_label, _route_url = booking_route_display(q_payway)
                    st.caption(f"建單介面：{_route_label}　｜　送單網址：{_route_url}　｜　實際付款方式：{q_payway}{_payway_note}　｜　區域：{q_region}")
                    if last_summary:
                        st.markdown(last_summary_card_html(last_summary), unsafe_allow_html=True)

                    # 舊客原本只能沿用歷史訂單的發票設定，無法在本次建單時修正。
                    # 儲值金訂單本身不開立發票，因此只在信用卡／ATM 顯示此功能。
                    q_invoice_mode = "沿用上次發票設定"
                    q_invoice_carrier = ""
                    q_invoice_company_title = ""
                    q_invoice_company_no = ""
                    if q_payway != "儲值金":
                        q_invoice_mode = st.selectbox(
                            "本次發票資訊",
                            ["沿用上次發票設定", "會員載具", "手機載具", "三聯式"],
                            key="old_invoice_mode",
                            help="選擇非「沿用上次」時，會以本次填寫資料覆蓋歷史發票設定。",
                        )
                        if q_invoice_mode == "手機載具":
                            q_invoice_carrier = st.text_input(
                                "手機載具條碼",
                                placeholder="/ABC1234",
                                key="old_invoice_carrier",
                            )
                        elif q_invoice_mode == "三聯式":
                            _old_inv_c1, _old_inv_c2 = st.columns(2)
                            with _old_inv_c1:
                                q_invoice_company_title = st.text_input(
                                    "公司抬頭", key="old_invoice_company_title"
                                )
                            with _old_inv_c2:
                                q_invoice_company_no = st.text_input(
                                    "統一編號", key="old_invoice_company_no"
                                )
                    else:
                        st.caption("發票資訊：儲值金訂單不開立發票")

                    upcoming_orders = get_unserved_paid_orders(lookup["session"], lookup["phone"], member_payload, addr_options, today_value=date.today())
                    if upcoming_orders:
                        st.markdown('<div class="hint-box"><b>⚠️ 目前已付款但尚未服務訂單</b><br>請先確認客人是否要異動既有訂單，避免重複建單。</div>', unsafe_allow_html=True)
                        for idx, order in enumerate(upcoming_orders, start=1):
                            ph_text = person_hour_display(order.get("person"), order.get("hour"))
                            payment_text = payment_invoice_display(order.get("payway"), order.get("invoice_text"))
                            address_text = order.get("address") or "未能對應留存地址，請至後台確認"
                            staff_text = order.get("staff") or "待確認"
                            fare_text = f"｜車馬費：{order.get('fare')}" if nonzero_money(order.get("fare")) else ""
                            st.markdown(f'<div class="history-order"><div class="history-order-main">{idx}. {h(order.get("order_no"))}　{h(order.get("date"))} {h(order.get("time"), "")}</div><div class="history-order-meta"><div>地址：{h(address_text)}</div><div>類別：{h(order.get("clean_type"))}</div><div>服務人員：{h(staff_text)}</div><div>人時：{h(ph_text)}{h(fare_text, "")}</div><div>{h(payment_text)}</div></div></div>', unsafe_allow_html=True)
                    date_mode = st.radio("日期/班表查詢方式", ["已知日期", "依需求搜尋可服務日期"], horizontal=True, key="old_date_mode")
                    if date_mode == "已知日期":
                        info_panel("已知日期使用說明", ["客人已指定某一天時使用。", "此模式才需要選服務日期與時段。", "若客人只說平日、週末、不限或幾小時，請改選『依需求搜尋可服務日期』。", "同一個客人/地址要一次約多筆（例如每週固定服務），可以調整下面的「建立筆數」，各自設定日期/時段/人數。"])
                        old_n_orders = st.number_input("建立筆數", min_value=1, max_value=10, value=1, key="old_n_orders")
                        old_entries = []
                        for _i in range(int(old_n_orders)):
                            if int(old_n_orders) > 1:
                                st.markdown(f"**第 {_i + 1} 筆**")
                            d1, d2, d3, d4 = st.columns(4)
                            with d1:
                                _q_date = st.date_input("服務日期", value=date.today(), key=f"old_known_date_{_i}")
                            with d2:
                                _q_period = st.selectbox("時段", PERIOD_OPTIONS, key=f"old_known_period_{_i}")
                            with d3:
                                _q_person = st.number_input("人數", min_value=1, max_value=8, value=default_person, key=f"old_known_person_{_i}")
                            with d4:
                                _q_hour = PERIOD_HOUR_MAP.get(_q_period, 3)
                                st.markdown(f'<br><b>{_q_hour} 小時</b>（依時段自動帶出）<br><span style="color:#8E8E93;font-size:13px;">人時：{int(_q_person) * int(_q_hour)}</span>', unsafe_allow_html=True)
                            old_entries.append({"date": _q_date, "period": _q_period, "person": _q_person, "hour": _q_hour})
                        # v2026.07.07：多筆時沿用第一筆的設定去查班表預覽，實際各筆送單時
                        # 各自帶自己的日期/時段/人數；查班表這裡只是先讓客服有個底，
                        # 真正是否可排班仍以送單當下的實際結果為準。
                        q_date, q_period, q_person, q_hour = (
                            old_entries[0]["date"], old_entries[0]["period"],
                            old_entries[0]["person"], old_entries[0]["hour"],
                        )
                        if st.button("🔎 查詢該日班表", use_container_width=True, key="old_check_known"):
                            try:
                                with st.spinner("查詢班表中…"):
                                    rows = quick_check_available_slots(env_name=env, payway=q_payway, lookup_result=lookup, address=q_address, clean_type_id=CLEAN_TYPE_ID_MAP[q_clean_type_confirm], date_s=q_date.strftime("%Y-%m-%d"), hour=q_hour, person=q_person, periods=[q_period], period_hours=PERIOD_HOUR_MAP)
                                st.session_state.old_known_slots = rows
                            except Exception as e:
                                st.session_state.old_known_slots = []
                                st.error(f"查詢班表失敗：{e}")
                        rows = st.session_state.get("old_known_slots")
                        if rows:
                            if any(r.get("available") for r in rows):
                                for r in rows:
                                    st.success(f"{r.get('date')} {r.get('period')} 可安排　服務人員：{r.get('staff') or '待確認'}")
                            else:
                                st.warning("此日期/時段目前無可安排班表。")
                        old_allow_auto_lemon = st.checkbox("查無班表時自動補檸檬人（不動其他客人已配班專員）", value=False, key="old_allow_auto_lemon")
                        _old_create_label = "🚀 建立訂單" if int(old_n_orders) == 1 else f"🚀 建立 {int(old_n_orders)} 筆訂單"
                        if st.button(_old_create_label, use_container_width=True, key="old_create_known"):
                            # v8.15：開始新的一次建單嘗試前，先清空上一次殘留的舊結果。
                            st.session_state.q_order_result = {}
                            st.session_state.old_results_multi = []
                            _multi_results = []
                            try:
                                _old_invoice_kwargs = (
                                    {}
                                    if q_invoice_mode == "沿用上次發票設定"
                                    else qo._invoice_payload(
                                        q_invoice_mode,
                                        member_email=member.get("email") or "",
                                        mobile_carrier=q_invoice_carrier,
                                        company_title=q_invoice_company_title,
                                        company_no=q_invoice_company_no,
                                    )
                                )
                            except Exception as e:
                                st.error(f"發票資訊錯誤：{e}")
                                _old_invoice_kwargs = None
                            if _old_invoice_kwargs is None:
                                st.stop()
                            for _i, entry in enumerate(old_entries, start=1):
                                try:
                                    with st.spinner(f"建單中（第 {_i}/{len(old_entries)} 筆），請稍候…"):
                                        result = quick_create_order(env_name=env, payway=q_payway, region=q_region, lookup_result=lookup, address=q_address, clean_type_id=CLEAN_TYPE_ID_MAP[q_clean_type_confirm], date_s=entry["date"].strftime("%Y-%m-%d"), period_s=entry["period"], hour=entry["hour"], person=entry["person"], allow_auto_lemon_shift=old_allow_auto_lemon, **_old_invoice_kwargs)
                                        # 不立即發確認信，等 user 確認後再發
                                        result["mail_sent"] = False
                                        result["mail_msg"] = "尚未發送"
                                        try:
                                            result["line_message"] = build_line_message(result)
                                        except Exception:
                                            result["line_message"] = ""
                                    _multi_results.append({"ok": True, "result": result})
                                except Exception as e:
                                    _multi_results.append({"ok": False, "error": str(e), "date": entry["date"].strftime("%Y-%m-%d"), "period": entry["period"]})
                            st.session_state.old_results_multi = _multi_results
                            if len(_multi_results) == 1 and _multi_results[0]["ok"]:
                                # 只有 1 筆時，沿用原本單筆的詳細結果卡呈現方式
                                st.session_state.q_order_result = _multi_results[0]["result"]
                    else:
                        info_panel("依需求搜尋使用說明", ["客人尚未指定日期時使用。", "可選平日 / 週末 / 不限，也可選上午 / 下午 / 不限。"])
                        a1, a2, a3, a4 = st.columns(4)
                        with a1:
                            day_type = st.selectbox("日期類型", ["平日", "週末", "不限"], key="old_day_type")
                        with a2:
                            time_pref = st.selectbox("時段偏好", ["上午", "下午", "不限"], key="old_time_pref")
                        with a3:
                            base_person = st.number_input("人數", min_value=1, max_value=8, value=2, key="old_search_person")
                        with a4:
                            base_hour = st.number_input("每人時數", min_value=2, max_value=8, value=4, key="old_search_hour")
                        search_days = st.slider("往後搜尋天數", min_value=7, max_value=60, value=30, step=1, key="old_search_days")
                        plans = build_equivalent_plans(base_person, base_hour)
                        total_ph = int(base_person) * int(base_hour)
                        st.caption(f"人時 = {int(base_person)} 人 × {int(base_hour)} 小時 = {total_ph} 人時")
                        st.caption("將查詢方案：" + "、".join([f"{p['person']}人{p['hour']}小時" for p in plans]))
                        if st.button("🔎 搜尋可服務日期", use_container_width=True, key="old_search_dates"):
                            try:
                                with st.spinner("搜尋可服務日期中…"):
                                    rows = search_available_service_dates(env_name=env, payway=q_payway, lookup_result=lookup, address=q_address, clean_type_id=CLEAN_TYPE_ID_MAP[q_clean_type_confirm], start_date=date.today(), days=search_days, day_type=day_type, time_preference=time_pref, plans=plans, periods=PERIOD_OPTIONS, period_hours=PERIOD_HOUR_MAP)
                                st.session_state.old_search_results = rows
                            except Exception as e:
                                st.session_state.old_search_results = []
                                st.error(f"搜尋失敗：{e}")
                        rows = st.session_state.get("old_search_results")
                        if rows is not None:
                            if rows:
                                st.markdown("**可服務日期搜尋結果**")
                                for idx, r in enumerate(rows[:20]):
                                    st.write(f"{idx+1}. 方案：{r['person']}人{r['hour']}小時　{r['date']} {r['period']}　服務人員：{r.get('staff') or '待確認'}")
                            else:
                                st.warning("目前依條件搜尋不到可服務日期，請放寬日期類型、時段偏好或延長搜尋天數。")

    # --------------------------------------------------
    # 建立新客訂單
    # --------------------------------------------------
    elif single_feature == "建立新客訂單":
        info_panel("功能說明", [
            "貼上客人提供的完整資料（含姓名/電話/email/地址/坪數/付款/發票），",
            "填入服務日期與人時後按建單，系統自動拆解、建會員、建單，",
            "班表無人時自動勾檸檬人，完成後顯示訂單資訊與 LINE 訊息。",
        ])

        step("1", "貼上客人資料")
        nc_raw = st.text_area(
            "客人提供的資料（直接整段貼入）",
            height=200, key="nc_raw_input",
            placeholder="訂購人姓名：XXX\n訂購人電話：09XXXXXXXX\n訂購人Email：xxx@xxx.com\n服務地址：台北市...\n室內坪數：約25坪\n付款方式：信用卡\n發票載具：手機載具 /XXXXXXX",
        )

        # v8.12：不管有沒有「訂購人姓名：」等標籤都要能辨識欄位，貼上後即時拆解預覽。
        # 付款方式若判斷不出來，不可默默預設，直接請客服在這裡手動選擇。
        _nc_live_parsed = {}
        if nc_raw.strip():
            try:
                _nc_live_parsed = qo.parse_new_customer_text(nc_raw)
            except Exception:
                _nc_live_parsed = {}
        if _nc_live_parsed:
            _preview_bits = []
            if _nc_live_parsed.get("name"):
                _preview_bits.append(f"姓名：{_nc_live_parsed['name']}")
            if _nc_live_parsed.get("phone"):
                _preview_bits.append(f"電話：{_nc_live_parsed['phone']}")
            if _nc_live_parsed.get("address"):
                _preview_bits.append(f"地址：{_nc_live_parsed['address']}")
            if _preview_bits:
                st.caption("已辨識　" + "　".join(_preview_bits))
            if _nc_live_parsed.get("need_ask_payway"):
                st.warning("⚠️ 無法從貼上的資料中判斷付款方式，請手動選擇：")
                st.selectbox("付款方式（手動選擇）", ["信用卡", "ATM"], key="nc_payway_manual_select")
            elif _nc_live_parsed.get("payway"):
                st.caption(f"✅ 已偵測付款方式：{_nc_live_parsed['payway']}")

        step("2", "服務設定")
        sc1, sc2, sc3 = st.columns(3)
        with sc1:
            nc_clean_type = st.selectbox("服務類別", list(CLEAN_TYPE_ID_MAP.keys()), key="nc_clean_type_d")
        with sc2:
            nc_service_type = ""
            if nc_clean_type == "裝修細清":
                _stype_map = {"裝修細清": "1", "搬出清潔": "2", "搬入清潔": "3"}
                _stype_sel = st.selectbox("裝修類型", list(_stype_map.keys()), key="nc_stype_d")
                nc_service_type = _stype_map[_stype_sel]
        with sc3:
            pass

        # 清潔項目細節
        with st.expander("🏠 清潔項目細節（選填，用於計算時數）", expanded=False):
            _ci1, _ci2, _ci3, _ci4, _ci5, _ci6 = st.columns(6)
            with _ci1:
                nc_room = st.number_input("房間", min_value=0, value=0, key="nc_room_d")
            with _ci2:
                nc_bathroom = st.number_input("衛浴", min_value=0, value=0, key="nc_bathroom_d")
            with _ci3:
                nc_balcony = st.number_input("陽台", min_value=0, value=0, key="nc_balcony_d")
            with _ci4:
                nc_livingroom = st.number_input("客廳", min_value=0, value=0, key="nc_livingroom_d")
            with _ci5:
                nc_kitchen = st.number_input("廚房", min_value=0, value=0, key="nc_kitchen_d")
            with _ci6:
                nc_window = st.text_input("窗戶", value="", placeholder="數量", key="nc_window_d")
            _ci7, _ci8 = st.columns([1, 5])
            with _ci7:
                nc_shutter = st.text_input("百葉窗", value="", placeholder="數量", key="nc_shutter_d")
            st.markdown("**加購項目**")
            _bv1, _bv2, _bv3, _bv4, _bv5, _bv6, _bv7, _bv8, _bv9 = st.columns(9)
            with _bv1:
                nc_clothes = "1" if st.checkbox("衣物洗晾", key="nc_clothes_d") else "0"
            with _bv2:
                nc_dyson = "1" if st.checkbox("DYSON除蟎", key="nc_dyson_d") else "0"
            with _bv3:
                nc_refrigerator = "1" if st.checkbox("冰箱清理", key="nc_fridge_d") else "0"
            with _bv4:
                nc_disinfection = "1" if st.checkbox("簡易消毒", key="nc_disinfect_d") else "0"
            with _bv5:
                nc_go_abroad = "1" if st.checkbox("30日內出國", key="nc_abroad_d") else "0"
            with _bv6:
                nc_home_move = "1" if st.checkbox("搬家打包", key="nc_move_d") else "0"
            with _bv7:
                nc_storage = "1" if st.checkbox("收納整理", key="nc_storage_d") else "0"
            with _bv8:
                nc_cabinet = "1" if st.checkbox("櫥櫃清潔", key="nc_cabinet_d") else "0"
            with _bv9:
                nc_quintuple = "1" if st.checkbox("五倍券", key="nc_quintuple_d") else "0"

        step("3", "日期與人時")
        nc_n_orders = st.number_input("建立筆數", min_value=1, max_value=10, value=1, key="nc_n_orders_d")
        nc_entries = []
        for _i in range(int(nc_n_orders)):
            if int(nc_n_orders) > 1:
                st.markdown(f"**第 {_i + 1} 筆**")
            sd1, sd2, sd3, sd4 = st.columns(4)
            with sd1:
                _nc_date = st.date_input("服務日期", value=date.today() + timedelta(days=1), key=f"nc_date_d_{_i}")
            with sd2:
                _nc_period = st.selectbox("時段", PERIOD_OPTIONS, key=f"nc_period_d_{_i}")
            with sd3:
                _nc_person = st.number_input("人數", min_value=1, max_value=8, value=2, key=f"nc_person_d_{_i}")
            with sd4:
                _nc_hour = PERIOD_HOUR_MAP.get(_nc_period, 3)
                _day_type_nc = "週末" if _nc_date.weekday() >= 5 else "平日"
                _unit_nc = 700 if _day_type_nc == "週末" else 600
                _total_nc = int(_nc_person) * _nc_hour * _unit_nc
                st.markdown(f"**{_nc_hour}小時 / {_day_type_nc}**")
                st.markdown(f"預估：**{_total_nc:,}元**")
            nc_entries.append({"date": _nc_date, "period": _nc_period, "person": _nc_person, "hour": _nc_hour})
        # 沿用第一筆設定作為備註/發票等共用欄位的預設情境（人時試算已在上面各自顯示）
        nc_date, nc_period, nc_person, nc_hour = (
            nc_entries[0]["date"], nc_entries[0]["period"], nc_entries[0]["person"], nc_entries[0]["hour"],
        )

        step("4", "備註欄位（選填）")
        nb1, nb2, nb3 = st.columns(3)
        with nb1:
            nc_actual_time = st.text_input("簡訊實際服務時間", placeholder="例：09:00-12:00", key="nc_actual_time_d")
        with nb2:
            nc_memo = st.text_area("客人備註", height=80, key="nc_memo_d")
        with nb3:
            nc_notice = st.text_area("客服備註", height=80, key="nc_notice_d")

        nc_d_allow_auto_lemon = st.checkbox("查無班表時自動補檸檬人（不動其他客人已配班專員）", value=False, key="nc_d_allow_auto_lemon")

        if st.button("🚀 建立新客訂單", use_container_width=True, key="nc_create_d", type="primary"):
            # v8.15：開始新的一次建單嘗試前，先清空上一次殘留在畫面下方的舊結果
            # （包含成功訊息、LINE 訊息），避免這次失敗/拆解失敗時，
            # 舊的成功結果還留在畫面上跟新的錯誤訊息重疊混淆。
            st.session_state.nc_result = {}
            st.session_state.nc_results_multi = []
            st.session_state.nc_pending_old = None
            if not nc_raw.strip():
                st.error("請貼上客人資料")
            elif not backend_email.strip() or not backend_password.strip():
                st.error("請先在上方輸入後台帳號密碼")
            else:
                # 拆解客人資料
                try:
                    _parsed = qo.parse_new_customer_text(nc_raw)
                except Exception:
                    _parsed = {}
                _nc_name = _parsed.get("name", "")
                _nc_phone = _parsed.get("phone", "")
                _nc_email = _parsed.get("email", "")
                _nc_address = _parsed.get("address", "")
                _nc_ping = _parsed.get("ping", "4")
                # v8.12：付款方式偵測不到時，改用上方手動選擇的值；兩者皆無則擋下建單，
                # 不可默默預設成信用卡。
                _nc_payway = _parsed.get("payway", "") or st.session_state.get("nc_payway_manual_select", "")
                _nc_carrier = _parsed.get("carrier", "")
                _nc_company_title = _parsed.get("company_title", "")
                _nc_company_no = _parsed.get("company_no", "")

                _missing = [k for k, v in [("姓名", _nc_name), ("電話", _nc_phone), ("Email", _nc_email), ("地址", _nc_address)] if not v.strip()]
                if not _nc_payway:
                    st.error("無法判斷付款方式，請於上方「付款方式（手動選擇）」選單選擇信用卡或ATM後再建單。")
                elif _missing:
                    st.error(f"資料拆解失敗，請確認以下欄位：{'、'.join(_missing)}\n\n拆解結果：{_parsed}")
                else:
                    # v2026.07.07：送出前先查這支電話是不是既有會員，不再需要另外手動查詢。
                    # 是既有會員的話，不繼續走新客建立流程（避免漏看歷史訂單/地址），
                    # 改成把已收集到的電話/地址/人時/付款/發票資訊存起來，讓客服按下面
                    # 的按鈕直接用舊客身份送出這筆預約。
                    try:
                        with st.spinner("查詢電話是否為既有會員…"):
                            _nc_lookup = qo.quick_lookup_member(
                                env_name=env, backend_email=backend_email.strip(),
                                backend_password=backend_password.strip(),
                                phone=_nc_phone.strip(),
                                clean_type_id=CLEAN_TYPE_ID_MAP[nc_clean_type],
                            )
                    except Exception as e:
                        st.error(f"查詢會員失敗：{e}")
                        _nc_lookup = None

                    if _nc_lookup is not None and _nc_lookup.get("member_payload"):
                        _m_existing = _nc_lookup["member_payload"].get("member", {})
                        _addrs_existing = [a.get("address", "") for a in _nc_lookup["member_payload"].get("member", {}).get("memberAddressList", []) if a.get("address")]
                        st.session_state.nc_pending_old = {
                            "lookup": _nc_lookup,
                            "member_name": _m_existing.get("name", ""),
                            "existing_addresses": _addrs_existing,
                            "phone": _nc_phone.strip(),
                            "address": _nc_address.strip(),
                            "clean_type_id": CLEAN_TYPE_ID_MAP[nc_clean_type],
                            "date_s": nc_date.strftime("%Y-%m-%d"),
                            "period_s": nc_period,
                            "hour": str(nc_hour),
                            "person": str(int(nc_person)),
                            "payway": _nc_payway,
                            "carrier": _nc_carrier,
                            "company_title": _nc_company_title,
                            "company_no": _nc_company_no,
                            "member_email": _m_existing.get("email", ""),
                            "allow_auto_lemon_shift": nc_d_allow_auto_lemon,
                        }
                        st.rerun()
                    elif _nc_lookup is not None:
                        try:
                            st.session_state.nc_results_multi = []
                            _nc_multi_results = []
                            for _ei, _entry in enumerate(nc_entries, start=1):
                                with st.spinner(f"建立會員 → 查詢地址 → 建單（第 {_ei}/{len(nc_entries)} 筆：{_entry['date']} {_entry['period']} {_entry['person']}人{_entry['hour']}小時）…"):
                                    try:
                                        nc_result = qo.quick_create_new_customer_order(
                                            env_name=env,
                                            backend_email=backend_email.strip(),
                                            backend_password=backend_password.strip(),
                                            allow_auto_lemon_shift=nc_d_allow_auto_lemon,
                                            customer={
                                                "name": _nc_name, "phone": _nc_phone,
                                                "email": _nc_email, "address": _nc_address,
                                                "ping": _nc_ping, "payway": _nc_payway,
                                                "clean_type_id": CLEAN_TYPE_ID_MAP[nc_clean_type],
                                                "service_type": nc_service_type,
                                                "room": str(nc_room), "bathroom": str(nc_bathroom),
                                                "balcony": str(nc_balcony), "livingroom": str(nc_livingroom),
                                                "kitchen": str(nc_kitchen), "window": nc_window,
                                                "shutter": nc_shutter, "clothes": nc_clothes,
                                                "dyson": nc_dyson, "refrigerator": nc_refrigerator,
                                                "disinfection": nc_disinfection, "go_abord": nc_go_abroad,
                                                "home_move": nc_home_move, "storage": nc_storage,
                                                "cabinet": nc_cabinet, "quintuple": nc_quintuple,
                                                "date_s": _entry["date"].strftime("%Y-%m-%d"),
                                                "period_s": _entry["period"],
                                                "hour": str(_entry["hour"]),
                                                "person": str(int(_entry["person"])),
                                                "carrier": _nc_carrier,
                                                "company_title": _nc_company_title,
                                                "company_no": _nc_company_no,
                                                "memo": nc_memo,
                                                "notice": nc_notice,
                                                "actual_time": nc_actual_time,
                                            }
                                        )
                                        # 不立即發確認信，等 user 確認後再發
                                        nc_result["mail_sent"] = False
                                        nc_result["mail_msg"] = "尚未發送"
                                        # v8.6：quick_create_new_customer_order 已回傳 build_line_message
                                        # 所需的完整欄位（date/period/region/fare 等），這裡直接組出 LINE 訊息，
                                        # 修正原本此流程從未產生 line_message、畫面永遠不顯示的問題。
                                        try:
                                            nc_result["line_message"] = build_line_message(nc_result)
                                        except Exception:
                                            nc_result["line_message"] = ""
                                        _nc_multi_results.append({"ok": True, "result": nc_result})
                                    except Exception as _e_entry:
                                        _nc_multi_results.append({"ok": False, "error": str(_e_entry), "date": _entry["date"].strftime("%Y-%m-%d"), "period": _entry["period"]})
                            st.session_state.nc_results_multi = _nc_multi_results
                            if len(_nc_multi_results) == 1 and _nc_multi_results[0]["ok"]:
                                # 只有 1 筆時，沿用原本單筆的詳細結果卡呈現方式
                                st.session_state.nc_result = _nc_multi_results[0]["result"]
                            st.rerun()
                        except Exception as e:
                            st.error(f"建單失敗：{e}")

        # v2026.07.07：查到既有會員時，顯示在「建立新客訂單」按鈕下方，
        # 提供一個按鈕直接改用舊客身份、帶著已收集的電話/地址/人時/付款/
        # 發票資訊送出這筆預約，不用客服重新輸入一次。
        _nc_pending = st.session_state.get("nc_pending_old")
        if _nc_pending:
            st.warning(
                f"⚠️ 這支電話（{_nc_pending['phone']}）其實已經是舊客會員"
                f"（姓名：{_nc_pending['member_name']}），不是新客！"
                + (f" 既有地址：{'、'.join(_nc_pending['existing_addresses'])}" if _nc_pending['existing_addresses'] else "")
            )
            if st.button("➡️ 用舊客身份送出此預約", use_container_width=True, key="nc_to_old_submit_btn", type="primary"):
                try:
                    with st.spinner("以舊客身份建立訂單…"):
                        _invoice = qo._invoice_payload(
                            "三聯式" if (_nc_pending["company_title"] and _nc_pending["company_no"]) else ("手機載具" if _nc_pending["carrier"] else "會員載具"),
                            member_email=_nc_pending["member_email"] or "",
                            mobile_carrier=_nc_pending["carrier"],
                            company_title=_nc_pending["company_title"],
                            company_no=_nc_pending["company_no"],
                        )
                        _region_pending = get_region_by_address(_nc_pending["address"], ACCOUNTS) or "台北"
                        old_result = qo.quick_create_order(
                            env_name=env, payway=_nc_pending["payway"], region=_region_pending,
                            lookup_result=_nc_pending["lookup"], address=_nc_pending["address"],
                            clean_type_id=_nc_pending["clean_type_id"],
                            date_s=_nc_pending["date_s"], period_s=_nc_pending["period_s"],
                            hour=_nc_pending["hour"], person=_nc_pending["person"],
                            carrier_info=_invoice["carrier_info"], company_no=_invoice["company_no"],
                            company_title=_invoice["company_title"],
                            invoice_type_override=_invoice["invoice_type_override"],
                            carrier_type_id_override=_invoice["carrier_type_id_override"],
                            allow_auto_lemon_shift=_nc_pending["allow_auto_lemon_shift"],
                        )
                        old_result["mail_sent"] = False
                        try:
                            old_result["line_message"] = build_line_message(old_result)
                        except Exception as _e_line_old:
                            old_result["line_message"] = ""
                    st.session_state.nc_result = old_result
                    st.session_state.nc_pending_old = None
                    st.rerun()
                except Exception as e:
                    st.error(f"以舊客身份建單失敗：{e}")

        # v2026.07.07：多筆訂單結果顯示（建立筆數 > 1，或有任何一筆失敗時）
        _nc_multi = st.session_state.get("nc_results_multi") or []
        if _nc_multi and not (len(_nc_multi) == 1 and _nc_multi[0]["ok"]):
            st.markdown("<hr>", unsafe_allow_html=True)
            _nc_ok_count = sum(1 for r in _nc_multi if r["ok"])
            st.info(f"共 {len(_nc_multi)} 筆，成功 {_nc_ok_count} 筆，失敗 {len(_nc_multi) - _nc_ok_count} 筆。")
            for _i, r in enumerate(_nc_multi, start=1):
                if r["ok"]:
                    res = r["result"]
                    if res.get("lemon_assignment_ok") is False:
                        st.error(f"⚠️ 第{_i}筆訂單已建立：{res.get('order_no')}，{res.get('lemon_assignment_warning') or '樸檬人置換失敗'}")
                    else:
                        st.success(f"✅ 第{_i}筆：{res.get('order_no')}　{res.get('date_s')} {res.get('period_s')}")
                    if res.get("existing_member_warning"):
                        st.warning(res["existing_member_warning"])
                    if res.get("address_mismatch_warning"):
                        st.warning(res["address_mismatch_warning"])
                    if res.get("line_message"):
                        copy_button(f"複製第{_i}筆 LINE 訊息", res["line_message"], f"copy_nc_multi_line_{_i}")
                else:
                    st.error(f"❌ 第{_i}筆（{r.get('date')} {r.get('period')}）失敗：{r.get('error')}")

        # 顯示建單結果
        _r = st.session_state.get("nc_result", {})
        if _r.get("order_no"):
            _lemon_failed = _r.get("lemon_assignment_ok") is False
            _result_msg = (
                f"訂單：{_r['order_no']}　{_r.get('date_s')} {_r.get('period_s')}　"
                f"{_r.get('person')}人{_r.get('hour')}小時　{_r.get('price_with_tax', 0):,}元　"
                f"👤 專員：{_r.get('staff') or '（無班表資料）'}"
            )
            if _lemon_failed:
                st.error(f"⚠️ {_result_msg}\n\n{_r.get('lemon_assignment_warning') or '樸檬人置換失敗'}")
            else:
                st.success(f"✅ {_result_msg}")
            if _r.get("price_mismatch_warning"):
                st.warning(_r["price_mismatch_warning"])
            if _r.get("address_mismatch_warning"):
                st.warning(_r["address_mismatch_warning"])
            if _r.get("existing_member_warning"):
                st.warning(_r["existing_member_warning"])
            if _r.get("order_no_duplicated"):
                show_duplicate_order_warning(_r.get("order_no"), _r.get("order_no_duplicate_count", 2), dedup_key=f"nc_{_r.get('order_no')}")
            if _lemon_failed:
                st.warning("樸檬人置換完成前，不可發送確認信。")
            elif not _r.get("mail_sent"):
                if st.button("📧 發送確認信", key="nc_send_mail_btn", type="primary"):
                    try:
                        ok_m2, msg_m2 = send_confirmation(_r)
                        if ok_m2:
                            _r["mail_sent"] = True
                            st.session_state.nc_result = _r
                            st.success("✅ 確認信已發送")
                            st.rerun()
                        else:
                            st.error(f"確認信發送失敗：{msg_m2}")
                    except Exception as e:
                        st.error(f"確認信發送失敗：{e}")
            else:
                st.success("✅ 確認信已發送")
            if _r.get("line_message"):
                col_nc_msg, col_nc_memo = st.columns([3, 1])
                with col_nc_msg:
                    # v8.17：拿掉固定 key——帶 key 的 st.text_area 一旦畫過一次，
                    # 之後即使傳入新的 value 也不會更新畫面，只會顯示 session_state
                    # 裡的舊內容，導致新訂單成立後 LINE 訊息還停留在上一張訂單。
                    st.text_area("LINE 訊息", _r["line_message"], height=320, label_visibility="collapsed")
                    copy_button("複製 LINE 訊息", _r["line_message"], "copy_nc_line_d")
                with col_nc_memo:
                    st.text_area("N-J Memo", NJ_MEMO, height=200, label_visibility="collapsed", key="nj_memo_nc_result")
                    copy_button("複製 N-J Memo", NJ_MEMO, "copy-nj-memo-nc-result")


    elif single_feature == "訂單轉換":
        info_panel(
            "流程說明",
            [
                "此功能拆成兩段：先修改原訂單A的日期並使用既有班表換成檸檬人，再建立新訂單（優惠券折抵原訂單金額）。",
                "舊單A與新單B均可勾選安全自動補檸檬人；已有任何班別的專員一律跳過，不動其他客人已配班專員。",
                "第二段：逐筆新訂單建立折價券，所有新單券額加總必須等於原訂單A服務金額；若新單金額超過原單，超出部分保留為應付差額。",
                "備註自動寫入：A+B1+B2+B3 合併服務。",
            ],
        )

        step("4", "第一段：原訂單A 改日期＋全部換檸檬人")
        col_a1, col_a2, col_a3 = st.columns(3)
        with col_a1:
            conv_order_no_a = st.text_input("原訂單A編號", placeholder="LC002115551", key="conv_order_no_a")
        with col_a2:
            conv_clean_type = st.selectbox("服務類別", list(CLEAN_TYPE_ID_MAP.keys()), key="conv_clean_type")
        with col_a3:
            conv_target_date = st.date_input("原訂單A要改到的新日期", value=date.today() + timedelta(days=1), key="conv_target_date")
        conv_stage1_allow_lemon = True
        st.caption("原訂單 A 固定全部換成檸檬人；不足時系統會自動補檸檬人班表。")

        if st.button("① 修改原訂單日期並全部換成檸檬人", use_container_width=True, key="conv_stage1_btn"):
            # 開始新的一次轉換前，先清空上一次殘留的舊結果（含第二、三段）。
            st.session_state.conv_stage1 = {}
            st.session_state.conv_stage2 = {}
            if not backend_email.strip() or not backend_password.strip():
                st.error("請先輸入後台帳號密碼")
            elif not conv_order_no_a.strip():
                st.error("請輸入原訂單A編號")
            else:
                try:
                    with st.spinner("第一段執行中：查原訂單A → 改日期 → 用既有班表換成檸檬人…"):
                        stage1 = convert_order_stage1_reassign_original(
                            env_name=env,
                            backend_email=backend_email.strip(),
                            backend_password=backend_password.strip(),
                            order_no_a=conv_order_no_a.strip(),
                            target_date_s=conv_target_date.strftime("%Y-%m-%d"),
                            clean_type_id=CLEAN_TYPE_ID_MAP[conv_clean_type],
                            allow_auto_lemon_shift=conv_stage1_allow_lemon,
                        )
                    st.session_state.conv_stage1 = stage1
                    st.session_state.conv_stage2 = {}
                except Exception as e:
                    st.session_state.conv_stage1 = {}
                    st.error(f"第一段執行失敗：{e}")

        conv_stage1 = st.session_state.get("conv_stage1")
        if conv_stage1:
            lr_a = conv_stage1.get("lemon_result_a", {}) or {}
            lemon_names = lr_a.get("assigned", [])
            actual_count = int(lr_a.get("actual_person_count", 0) or len(lemon_names) or conv_stage1.get("person_a", 0) or 0)
            new_svc_date = lr_a.get("new_service_date", "")
            date_ok = lr_a.get("date_change_ok", True)
            orig_date = conv_stage1.get("service_date_a", "")
            period_a = str(conv_stage1.get("period_a_raw", "")).replace(" ", "")

            if date_ok and new_svc_date:
                date_str = f"{orig_date} → {new_svc_date}"
            elif not date_ok:
                date_str = f"❌ 日期修改失敗，請手動改為 {new_svc_date}"
            else:
                date_str = orig_date

            if lr_a.get("success") and lemon_names:
                lemon_str = "X".join(lemon_names)
                st.success(
                    f"✅ 第一段完成：原訂單 {conv_stage1['order_no_a']} 服務日期 {date_str} {period_a}，"
                    f"{lemon_str}，{actual_count}人，全部為檸檬人"
                )
            else:
                st.warning(f"⚠️ 第一段：原訂單配班未完全成功 — {lr_a.get('message', '未知')}，請至後台確認排班狀況。")
            with st.expander("🔗 原訂單A後台連結", expanded=False):
                st.markdown(f"[開啟原訂單A後台]({conv_stage1.get('base_url', '')}/purchase?orderNo={conv_stage1['order_no_a']})")

        st.markdown("<hr>", unsafe_allow_html=True)
        step("5", "第二段：建立新訂單（優惠券折抵）")

        if not conv_stage1:
            st.info("請先完成第一段，才能建立新訂單。")
        else:
            conv_order_count = st.number_input("新訂單筆數", min_value=1, max_value=6, value=2, step=1, key="conv_order_count")
            st.markdown('<div class="hint-box">💡 每筆新訂單各自選日期、時段、人數。時數由時段自動帶出。折價券會依序折抵原訂單A服務金額；新單超過原單時，超出部分會留在新單應付。</div>', unsafe_allow_html=True)

            new_orders_input = []
            for i in range(int(conv_order_count)):
                st.markdown(f"**新訂單 B{i+1}**")
                b1, b2, b3, b4 = st.columns(4)
                with b1:
                    b_date = st.date_input(f"B{i+1} 日期", value=date.today() + timedelta(days=1), key=f"conv_date_{i}")
                with b2:
                    b_period = st.selectbox(f"B{i+1} 時段", PERIOD_OPTIONS, key=f"conv_period_{i}")
                with b3:
                    b_person = st.number_input(f"B{i+1} 人數", min_value=1, max_value=8, value=2, key=f"conv_person_{i}")
                with b4:
                    b_hour = PERIOD_HOUR_MAP.get(b_period, 4)
                    st.markdown(f"<br><b>{b_hour} 小時</b>（依時段帶出）", unsafe_allow_html=True)
                b_allow_lemon = st.checkbox(
                    f"B{i+1} 若無人力，自動補檸檬人（不動其他客人已配班專員）",
                    value=False, key=f"conv_allow_lemon_{i}",
                )
                new_orders_input.append({
                    "date_s": b_date.strftime("%Y-%m-%d"),
                    "period_s": b_period,
                    "hour": b_hour,
                    "person": int(b_person),
                    "allow_lemon": bool(b_allow_lemon),
                })

            _conv_stage1_result = conv_stage1.get("lemon_result_a", {}) or {}
            _conv_stage1_ready = bool(
                _conv_stage1_result.get("success")
                and _conv_stage1_result.get("date_change_ok", True)
            )
            if not _conv_stage1_ready:
                st.error("原訂單A還沒有用既有班表完成配班，已鎖定第二段；請先由人工處理班表。")

            if st.button("② 建立新訂單（優惠券折抵）", use_container_width=True, key="conv_stage2_btn", disabled=not _conv_stage1_ready):
                st.session_state.conv_stage2 = {}
                try:
                    with st.spinner("第二段執行中：建折價券 → 建新訂單 → 標記已付款 → 標註發票…"):
                        stage2 = convert_order_stage2_create_new_orders(conv_stage1, new_orders_input)
                    st.session_state.conv_stage2 = stage2
                except Exception as e:
                    st.session_state.conv_stage2 = {}
                    st.error(f"第二段執行失敗：{e}")

        conv_stage2 = st.session_state.get("conv_stage2")
        if conv_stage2:
            new_orders_ok = [r for r in conv_stage2.get("new_order_results", []) if r.get("order_no")]

            for r in new_orders_ok:
                ph_str = f"{r['person']}人{r['hour']}小時"
                _r_order_result = r.get("order_result") or {}
                _coupon_discount = int(r.get("coupon_discount", r.get("price_with_tax", 0)) or 0)
                _customer_due = int(r.get("customer_due", max(int(r.get("price_with_tax", 0) or 0) - _coupon_discount, 0)) or 0)
                _coupon_text = f"折價券 {r['coupon_code']}（折{_coupon_discount}元）" if r.get("coupon_code") else "未建立折價券"
                st.success(
                    f"✅ 第二段：新訂單 {r['order_no']}，{r['date_s']} {r['period_s']} {ph_str}，"
                    f"{_coupon_text}，應付{_customer_due}元　"
                    f"👤 專員：{_r_order_result.get('staff') or '（無班表資料）'}"
                )
                if r.get("mark_paid_ok") is True:
                    st.caption(f"✅ {r['order_no']} 已標記為已付款")
                elif r.get("mark_paid_ok") is None:
                    st.caption(f"ℹ️ {r['order_no']} {r.get('mark_paid_msg', '未自動標記已付款')}")
                else:
                    st.warning(f"⚠️ {r['order_no']} 標記已付款失敗：{r.get('mark_paid_msg', '')}")
                if r.get("invoice_note_ok"):
                    st.caption(f"✅ {r['order_no']} 發票號碼欄位已標註「不開立發票」")
                else:
                    st.warning(f"⚠️ {r['order_no']} 發票欄位標註失敗，請至後台手動填寫「不開立發票」：{r.get('invoice_note_msg', '')}")
                if _r_order_result.get("order_no_duplicated"):
                    show_duplicate_order_warning(
                        r.get("order_no"), _r_order_result.get("order_no_duplicate_count", 2),
                        dedup_key=f"conv_{r.get('order_no')}",
                    )
            for r in [r for r in conv_stage2.get("new_order_results", []) if r.get("error")]:
                st.error(f"❌ 第二段 B{r['index']}（{r['date_s']} {r['period_s']}）失敗：{r['error']}")

            with st.expander("🔍 細項", expanded=False):
                st.markdown(f"[🔗 開啟原訂單A後台]({conv_stage2['purchase_url_a']})")

                st.markdown("**備註文字**")
                note_a_status = "✅ 已自動寫入" if conv_stage2.get("note_a_ok") else f"⚠️ 需手動貼上（{conv_stage2.get('note_a_msg', '')}）"
                st.markdown(f"原訂單A備註 {note_a_status}")
                st.text_area("原訂單A備註", conv_stage2.get("note_a", ""), height=70, label_visibility="collapsed", key="conv_note_a_out")
                copy_button("複製原訂單A備註", conv_stage2.get("note_a", ""), "copy_note_a")
                st.caption(f"全單備註：{conv_stage2.get('note', '')}")

            st.markdown("<hr>", unsafe_allow_html=True)
            step("6", "第三階段：比對原訂單與新訂單金額差額")
            _orig_amount = conv_stage2.get("service_amount_a_display", 0)
            _new_amount = conv_stage2.get("new_amount_total", 0)
            _new_amt_detail = "＋".join(f"{r['price_with_tax']}元" for r in new_orders_ok) if new_orders_ok else "0元"
            if conv_stage2.get("ph_warning"):
                st.warning(conv_stage2["ph_warning"])
            elif _orig_amount:
                st.success(f"✅ 金額比對：原訂單A {_orig_amount}元 ＝ 新訂單合計 {_new_amt_detail} = {_new_amount}元")
            else:
                st.warning(f"⚠️ 金額比對：原訂單A金額解析失敗，無法自動比較，新訂單合計 {_new_amt_detail} = {_new_amount}元，請手動核對。")

            # 2026-07-08：先顯示第三階段金額比對，再顯示 LINE 訊息。
            combined_msg = conv_stage2.get("combined_line_message", "")
            if combined_msg:
                st.markdown("#### 💬 合併 LINE 訊息（全部新訂單）")
                st.text_area("合併 LINE 訊息", combined_msg, height=380, label_visibility="collapsed")
                copy_button("複製合併 LINE 訊息", combined_msg, "copy_conv_combined_line")
            else:
                st.markdown("#### 💬 新訂單 LINE 訊息")
                for r in new_orders_ok:
                    if r.get("line_message"):
                        st.text_area(f"B{r['index']} LINE（{r['order_no']}）", r["line_message"], height=320, label_visibility="collapsed")
                        copy_button(f"複製 B{r['index']} LINE 訊息", r["line_message"], f"copy_conv_line_{r['index']}")
    # --------------------------------------------------
    # 儲值金補價差
    # --------------------------------------------------
    elif single_feature == "儲值金補價差":
        info_panel("流程說明", [
            "此功能拆成兩段：先成立儲值金折抵單，再成立客付補價差訂單。",
            "兩段都可勾選安全自動補檸檬人；已有任何班別的專員一律跳過，不動其他客人已配班專員。",
            "日期類型由服務日期自動判斷：週一到週五為平日，週六日為週末。",
            "儲值金清零單走 /booking/stored_value_routine，優惠券A = 服務總額 - 儲值金餘額；剩餘額用儲值金扣掉後歸零。",
            "補差價訂單走 /booking/single，優惠券B = 原儲值金餘額，付款方式限 ATM / 信用卡。",
        ])
        step("4", "客人與服務資料")
        sv1, sv2, sv3 = st.columns(3)
        with sv1:
            sv_phone = st.text_input("客人手機號碼", key="sv_auto_phone")
        with sv2:
            sv_ctype = st.selectbox("服務類別", list(CLEAN_TYPE_ID_MAP.keys()), key="sv_auto_ctype")
        with sv3:
            sv_svc_date = st.date_input("服務日期", value=date.today() + timedelta(days=7), key="sv_auto_date")
            sv_day_type_auto = "週末" if sv_svc_date.weekday() >= 5 else "平日"
            st.caption(f"日期類型：{sv_day_type_auto}（自動判斷）")
        sd1, sd2, sd3, sd4 = st.columns(4)
        with sd1:
            sv_svc_period = st.selectbox("服務時段", PERIOD_OPTIONS, key="sv_auto_period")
        with sd2:
            sv_svc_person = st.number_input("人數", min_value=1, max_value=8, value=2, key="sv_auto_person")
        with sd3:
            sv_svc_hour = PERIOD_HOUR_MAP.get(sv_svc_period, 4)
            sv_person_hours = int(sv_svc_person) * int(sv_svc_hour)
            st.markdown(f"<br><b>{sv_svc_hour} 小時</b><br><span style='color:#8E8E93;font-size:13px;'>人時：{sv_person_hours}</span>", unsafe_allow_html=True)
        with sd4:
            sv_unit_price = 700 if sv_day_type_auto == "週末" else 600
            st.markdown(f"<br><b>{sv_unit_price} 元 / 人時</b><br><span style='color:#8E8E93;font-size:13px;'>儲值金單目標金額：{sv_unit_price * sv_person_hours}</span>", unsafe_allow_html=True)
        st.markdown("<hr>", unsafe_allow_html=True)
        step("4", "客付訂單付款與發票")
        pay1, pay2 = st.columns(2)
        with pay1:
            sv_customer_payway = st.selectbox("付款方式", ["ATM", "信用卡"], key="sv_auto_customer_payway")
        with pay2:
            sv_invoice_mode = st.selectbox("發票", ["會員載具", "手機載具", "三聯式"], key="sv_auto_invoice_mode")
        sv_mobile_carrier = ""
        sv_company_title = ""
        sv_company_no = ""
        if sv_invoice_mode == "手機載具":
            sv_mobile_carrier = st.text_input("手機條碼", placeholder="例：/ABC1234", key="sv_auto_mobile_carrier")
        elif sv_invoice_mode == "三聯式":
            inv_a, inv_b = st.columns(2)
            with inv_a:
                sv_company_title = st.text_input("發票抬頭", key="sv_auto_company_title")
            with inv_b:
                sv_company_no = st.text_input("統一編號", key="sv_auto_company_no")
        else:
            st.caption("二聯會員載具會使用會員 email。")
        st.markdown("<hr>", unsafe_allow_html=True)
        step("4", "選填設定")
        opt1, opt2 = st.columns(2)
        with opt1:
            sv_address = st.text_input("指定服務地址（留空則用會員第一個地址）", key="sv_auto_address")
        with opt2:
            sv_region = st.selectbox("適用地區", [""] + list(COUPON_COMPANY_ID_MAP.keys()), format_func=lambda x: x or "依地址自動判斷", key="sv_auto_region")
        sv_allow_auto_lemon = st.checkbox("查無檸檬人時自動補檸檬人（不動其他客人已配班專員）", value=False, key="sv_allow_auto_lemon")
        st.markdown("<hr>", unsafe_allow_html=True)
        step("5", "第一段：建立儲值金清零訂單")
        sv_stored_total_preview = sv_unit_price * sv_person_hours
        st.markdown(f'<div class="hint-box">儲值金清零訂單會送到 <b>/booking/stored_value_routine</b>。服務總額為 <b>{sv_unit_price} × {sv_person_hours} = {sv_stored_total_preview}</b>；優惠券A會用「服務總額 - 儲值金餘額」計算，剩餘金額由儲值金扣抵後歸零。</div>', unsafe_allow_html=True)
        if st.button("① 建立儲值金清零訂單（stored_value_routine）", use_container_width=True, key="sv_create_stored_btn"):
            # v8.15：開始新的一次嘗試前，先清空上一次殘留的舊結果（含第二段）。
            st.session_state.sv_stored_stage = {}
            st.session_state.sv_paid_stage = {}
            if not backend_email.strip() or not backend_password.strip():
                st.error("請先輸入後台帳號密碼")
            elif not sv_phone.strip():
                st.error("請輸入客人手機號碼")
            else:
                try:
                    with st.spinner("第一段執行中：查儲值金 → 建優惠券A → 建儲值金清零訂單 → 用既有班表換檸檬人…"):
                        stored_stage = stored_value_makeup_create_stored_order(
                            env_name=env, backend_email=backend_email.strip(), backend_password=backend_password.strip(),
                            phone=sv_phone.strip(), clean_type_id=CLEAN_TYPE_ID_MAP[sv_ctype],
                            service_date=sv_svc_date.strftime("%Y-%m-%d"), period_s=sv_svc_period,
                            hour=str(sv_svc_hour), person=str(int(sv_svc_person)),
                            address=sv_address.strip(), region=sv_region, coupon_prefix_base=sv_phone.strip(),
                            allow_auto_lemon_shift=sv_allow_auto_lemon,
                        )
                    st.session_state.sv_stored_stage = stored_stage
                    st.session_state.sv_paid_stage = {}
                except Exception as e:
                    st.error(f"第一段建立失敗：{e}")
        stored_stage = st.session_state.get("sv_stored_stage")
        if stored_stage:
            plan = stored_stage["plan"]
            so = stored_stage["stored_order"]
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("儲值金餘額", f"{stored_stage['balance']} 元")
            c2.metric("日期類型", stored_stage.get("day_type", sv_day_type_auto))
            c3.metric("優惠券A", f"{plan['coupon_a']} 元")
            st.caption(f"計算式：{plan['dummy_price']} - {stored_stage['balance']} = {plan['coupon_a']}；剩餘 {plan.get('stored_value_applied', stored_stage['balance'])} 扣儲值金。")
            c4.metric("儲值金單", so.get("order_no", "—"))
            ca = stored_stage.get("coupon_a", {})
            st.success(
                f"✅ 第一段完成：儲值金清零訂單 {so.get('order_no', '—')}；"
                f"優惠券A {ca.get('coupon_code') or ca.get('coupon_prefix')}，面額 {plan['coupon_a']} 元。　"
                f"👤 專員：{so.get('staff') or '（無班表資料）'}"
            )
            if so.get("order_no_duplicated"):
                show_duplicate_order_warning(so.get("order_no"), so.get("order_no_duplicate_count", 2), dedup_key=f"sv_stored_{so.get('order_no')}")
            lemon_r = stored_stage.get("lemon_result", {})
            if lemon_r.get("success"):
                st.success(lemon_r.get("message", "已改為檸檬人"))
            else:
                st.error(lemon_r.get("message", "現有班表無足夠檸檬人，已停止第二段，請手動處理"))
            step("6", "第二段：建立客付補價差訂單")
            st.markdown(f'<div class="hint-box">客付補價差單會建立優惠券B，面額為原儲值金餘額 <b>{stored_stage["balance"]}</b> 元，付款方式為 <b>{sv_customer_payway}</b>。</div>', unsafe_allow_html=True)
            _sv_stage_ready = bool(lemon_r.get("success"))
            if st.button("② 建立客付補價差訂單（single）", use_container_width=True, key="sv_create_paid_btn", disabled=not _sv_stage_ready):
                # v8.15：開始新的一次嘗試前，先清空上一次殘留的舊結果。
                st.session_state.sv_paid_stage = {}
                try:
                    with st.spinner("第二段執行中：建優惠券B → 建客付補價差訂單…"):
                        paid_stage = stored_value_makeup_create_paid_order(
                            env_name=env, backend_email=backend_email.strip(), backend_password=backend_password.strip(),
                            phone=stored_stage.get("phone") or sv_phone.strip(),
                            clean_type_id=stored_stage.get("clean_type_id") or CLEAN_TYPE_ID_MAP[sv_ctype],
                            service_date=stored_stage.get("service_date") or sv_svc_date.strftime("%Y-%m-%d"),
                            period_s=stored_stage.get("period_s") or sv_svc_period,
                            hour=stored_stage.get("hour") or str(sv_svc_hour),
                            person=stored_stage.get("person") or str(int(sv_svc_person)),
                            customer_payway=sv_customer_payway, invoice_mode=sv_invoice_mode,
                            mobile_carrier=sv_mobile_carrier, company_title=sv_company_title, company_no=sv_company_no,
                            address=stored_stage.get("address") or sv_address.strip(),
                            region=stored_stage.get("region") or sv_region,
                            coupon_prefix_base=stored_stage.get("coupon_prefix_base") or sv_phone.strip(),
                            stored_order_no=stored_stage.get("stored_order", {}).get("order_no", ""),
                            balance_override=stored_stage.get("balance"),
                            allow_auto_lemon_shift=sv_allow_auto_lemon,
                        )
                    st.session_state.sv_paid_stage = paid_stage
                except Exception as e:
                    st.error(f"第二段建立失敗：{e}")
        paid_stage = st.session_state.get("sv_paid_stage")
        if paid_stage:
            po = paid_stage["paid_order"]
            cb = paid_stage.get("coupon_b", {})
            st.success(
                f"✅ 第二段完成：客付補價差訂單 {po.get('order_no', '—')}；"
                f"優惠券B {cb.get('coupon_code') or cb.get('coupon_prefix')}。　"
                f"👤 專員：{po.get('staff') or '（無班表資料）'}"
            )
            if paid_stage.get("mark_paid_ok") is True:
                st.caption("✅ 已標記為已付款")
            elif paid_stage.get("mark_paid_ok") is None:
                st.caption(f"ℹ️ {paid_stage.get('mark_paid_msg', '未自動標記已付款')}")
            else:
                st.warning(f"⚠️ 標記已付款失敗：{paid_stage.get('mark_paid_msg', '')}")
            if paid_stage.get("invoice_note_ok"):
                st.caption("✅ 發票號碼欄位已標註「不開立發票」")
            else:
                st.warning(f"⚠️ 發票欄位標註失敗，請至後台手動填寫「不開立發票」：{paid_stage.get('invoice_note_msg', '')}")
            if po.get("order_no_duplicated"):
                show_duplicate_order_warning(po.get("order_no"), po.get("order_no_duplicate_count", 2), dedup_key=f"sv_paid_{po.get('order_no')}")
            st.markdown("#### 📋 備註文字")
            combined_note = ""
            if stored_stage:
                combined_note += stored_stage.get("note", "")
            combined_note += "\n" + paid_stage.get("note", "")
            st.text_area("備註", combined_note.strip(), height=110, label_visibility="collapsed")
            copy_button("複製備註", combined_note.strip(), "copy_sv_stage_note")
            if paid_stage.get("line_message"):
                st.markdown("#### 💬 客付訂單 LINE 訊息")
                st.text_area("LINE 訊息", paid_stage["line_message"], height=320, label_visibility="collapsed")
                copy_button("複製 LINE 訊息", paid_stage["line_message"], "copy_sv_paid_line")

    # --------------------------------------------------
    # 建立儲值金訂單（v8.21 新增）
    # 客人自己買/儲值一筆金額，付款方式/發票不用手動選，自動沿用會員最近一次
    # VIP 或儲值金購買訂單的設定；都找不到才退回最近一次一般服務訂單。
    # --------------------------------------------------
    elif single_feature == "建立儲值金訂單":
        info_panel("流程說明", [
            "地區＝登入帳號本身所屬地區（例如用台北帳號登入，就會建在台北）。",
            "付款方式與發票不用手動選：自動抓這支電話最近一次 VIP 或儲值金購買訂單的設定，"
            "都找不到才退回抓最近一次一般服務訂單的設定，兩者都沒有則不會自動送出，"
            "改請你人工確認後至後台手動建立。",
        ])
        sv2_col1, sv2_col2 = st.columns(2)
        with sv2_col1:
            sv2_phone = st.text_input("客人手機號碼", key="sv2_phone")
        with sv2_col2:
            sv2_region = st.selectbox("地區（登入帳號所屬地區）", ["台北", "桃園", "新竹", "台中"], key="sv2_region")

        sv2_amount_labels = {
            "儲值金20,000（贈購物金800）": 20000,
            "儲值金50,000（贈購物金2,500）": 50000,
            "儲值金9,900（無贈送）": 9900,
            "儲值金17,000（無贈送）": 17000,
            "儲值金18,900（無贈送）": 18900,
            "儲值金19,400（無贈送）": 19400,
            "儲值金36,000（無贈送）": 36000,
        }
        sv2_amount_label = st.selectbox("儲值金金額", list(sv2_amount_labels.keys()), key="sv2_amount_label")
        sv2_amount = sv2_amount_labels[sv2_amount_label]
        sv2_notice = st.text_area("備註（選填）", height=80, key="sv2_notice")

        if st.button("🚀 建立儲值金購買訂單", use_container_width=True, key="sv2_create_btn", type="primary"):
            # v8.21：開始新的一次嘗試前，先清空上一次殘留的舊結果。
            st.session_state.sv2_result = {}
            if not backend_email.strip() or not backend_password.strip():
                st.error("請先輸入後台帳號密碼")
            elif not sv2_phone.strip():
                st.error("請輸入客人手機號碼")
            else:
                try:
                    with st.spinner("查詢會員 → 判斷付款方式/發票 → 建立儲值金訂單…"):
                        sv2_result = qo.create_stored_value_purchase_order(
                            env_name=env,
                            backend_email=backend_email.strip(),
                            backend_password=backend_password.strip(),
                            phone=sv2_phone.strip(),
                            stored_value_amount=sv2_amount,
                            region=sv2_region,
                            notice=sv2_notice.strip(),
                        )
                    st.session_state.sv2_result = sv2_result
                except Exception as e:
                    st.error(f"建立失敗：{e}")

        sv2_result = st.session_state.get("sv2_result") or {}
        if sv2_result:
            if sv2_result.get("need_manual_confirm"):
                st.warning(f"⚠️ {sv2_result.get('message', '')}")
                _dbg = sv2_result.get("search_debug") or {}
                with st.expander("🔍 查詢明細（點開看實際查到什麼，不用再用猜的）", expanded=True):
                    if _dbg.get("error"):
                        st.error(f"查詢時發生例外：{_dbg['error']}")
                    _queries_dbg = _dbg.get("queries") or []
                    if _queries_dbg:
                        st.table([
                            {
                                "查詢類別": q.get("label", ""),
                                "HTTP狀態碼": q.get("http_status", q.get("error", "")),
                                "查到筆數（已付款）": q.get("count", 0),
                                "訂單編號": "、".join(q.get("order_nos", [])) or "（無）",
                            }
                            for q in _queries_dbg
                        ])
                        _skipped_dbg = _dbg.get("skipped_stored_value_payway") or []
                        if _skipped_dbg:
                            st.caption("以下訂單因為付款方式是「儲值金」（既有餘額折抵消費，非真正付款）已跳過：")
                            st.table([{"類別": s.get("label", ""), "訂單編號": s.get("order_no", "")} for s in _skipped_dbg])
                        st.caption(
                            "依序查詢「儲值金」→「VIP券」→「專業清潔」三個類別（都只查已付款的訂單），"
                            "查到就直接用該類別裡最新一筆「付款方式是信用卡/ATM」的訂單，不會混在一起比日期，"
                            "也不會用付款方式是儲值金的訂單當範本。如果上表看起來明明有查到訂單、"
                            "卻還是被判定查無資料，麻煩把這個表格截圖給開發人員確認。"
                        )
                    else:
                        st.info("查詢過程沒有回傳任何結果，請檢查上方是否有例外訊息。")
            elif sv2_result.get("success"):
                st.success(
                    f"✅ 訂單：{sv2_result.get('order_no') or '（已送出，但查不到訂單編號，請至後台確認）'}　"
                    f"儲值金額：{sv2_result.get('stored_value_amount')}元　"
                    f"贈購物金：{sv2_result.get('bonus')}元　"
                    f"付款方式：{sv2_result.get('payway')}"
                )
                _invoice_type_label = {"1": "捐贈發票", "2": "二聯式", "3": "三聯式"}.get(sv2_result.get("invoice_type", ""), "")
                if _invoice_type_label:
                    st.caption(
                        f"發票設定沿用自會員歷史訂單：{_invoice_type_label}"
                        + (f"（{sv2_result.get('company_title')} / {sv2_result.get('company_no')}）" if sv2_result.get("invoice_type") == "3" else "")
                        + (f"（{sv2_result.get('carrier_info')}）" if sv2_result.get("invoice_type") == "2" and sv2_result.get("carrier_info") else "")
                    )
                # v8.23：跟其他成單流程一致，訂單建立後不自動發確認信，
                # 由客服確認資料無誤後手動按下「發送確認信」再送出。
                if sv2_result.get("order_no"):
                    if not sv2_result.get("mail_sent"):
                        if st.button("📧 發送確認信", key="sv2_send_mail_btn", type="primary"):
                            try:
                                ok_m, msg_m = send_confirmation(sv2_result)
                                if ok_m:
                                    sv2_result["mail_sent"] = True
                                    st.session_state.sv2_result = sv2_result
                                    st.success("✅ 確認信已發送")
                                    st.rerun()
                                else:
                                    st.error(f"確認信發送失敗：{msg_m}")
                            except Exception as e:
                                st.error(f"確認信發送失敗：{e}")
                    else:
                        st.success("✅ 確認信已發送")
                else:
                    st.info("查不到訂單編號，無法自動發送確認信，請至後台確認訂單後手動發送。")
                if sv2_result.get("line_message"):
                    st.markdown("#### 💬 LINE 訊息")
                    st.text_area("LINE 訊息", sv2_result["line_message"], height=380, label_visibility="collapsed")
                    copy_button("複製 LINE 訊息", sv2_result["line_message"], "copy_sv2_line")
                else:
                    st.info("此地區/付款方式組合目前沒有現成 LINE 通知文案，請至「LINE 通知產生器」用訂單編號查詢並人工確認內容。")
            else:
                st.error(f"❌ 建立失敗：{sv2_result.get('message', '未知錯誤')}")

    elif single_feature == "整理預約下次服務":
        info_panel("使用說明", [
            "搜尋「評價日期」區間內、有勾選預約下次服務的評價紀錄。",
            "每一筆會回頭查詢被評價的訂單本身，抓出電話/地址/服務日期時數/人數。",
            "查詢筆數多時（例如整月）會需要一點時間，請耐心等候。",
        ])
        rn_col1, rn_col2 = st.columns(2)
        with rn_col1:
            rn_date_s = st.date_input("評價日期-起", value=None, key="rn_date_s")
        with rn_col2:
            rn_date_e = st.date_input("評價日期-迄", value=None, key="rn_date_e")
        if st.button("🔍 開始搜尋", key="rn_search_btn", use_container_width=True):
            if not backend_email.strip() or not backend_password.strip():
                st.error("請先在上方輸入後台帳號密碼")
            else:
                try:
                    with st.spinner("查詢評價與訂單中，可能需要一點時間…"):
                        rn_results = qo.fetch_rating_next_appointments(
                            env_name=env, backend_email=backend_email.strip(),
                            backend_password=backend_password.strip(),
                            date_s=rn_date_s.strftime("%Y-%m-%d") if rn_date_s else "",
                            date_e=rn_date_e.strftime("%Y-%m-%d") if rn_date_e else "",
                        )
                    st.session_state.rn_results = rn_results
                except Exception as e:
                    st.error(f"搜尋失敗：{e}")

        rn_results = st.session_state.get("rn_results")
        if rn_results is not None:
            if not rn_results:
                st.info("這個區間內沒有預約下次服務的評價紀錄。")
            else:
                st.success(f"✅ 找到 {len(rn_results)} 筆預約下次服務的紀錄：")
                # v2026.07.07 新增：姓名可以直接點擊連到客人的 LINE 聊天視窗。
                # st.dataframe 的 LinkColumn 沒辦法讓儲存格顯示「姓名文字」但連到
                # 「另一個網址」（display_text 只能重新格式化網址本身的文字），
                # 所以改用 markdown 表格，姓名欄直接用 [姓名](LINE網址) 的超連結。
                _rn_headers = ["評價日期", "姓名", "電話", "地址", "預約下次日期", "預約下次時間", "服務日期及時間", "服務人數", "訂單編號"]
                _rn_md_lines = [
                    "| " + " | ".join(_rn_headers) + " |",
                    "|" + "|".join(["---"] * len(_rn_headers)) + "|",
                ]
                for r in rn_results:
                    name_cell = f"[{r['姓名']}]({r['LINE']})" if r.get("LINE") else r["姓名"]
                    _rn_md_lines.append(
                        "| " + " | ".join([
                            r["評價日期"], name_cell, r["電話"], r["地址"],
                            r["預約下次日期"], r["預約下次時間"], r["服務日期及時間"], r["服務人數"],
                            r["訂單編號"],
                        ]) + " |"
                    )
                st.markdown("\n".join(_rn_md_lines))
                rn_text = "\n".join(
                    f"{r['評價日期']}/ {r['姓名']}/ {r['電話']} /{r['地址']}/{r['預約下次日期']} "
                    f"/{r['預約下次時間']}/{r['服務日期及時間']} {r['服務人數']}/{r['訂單編號']}"
                    for r in rn_results
                )
                # v2026.07.07 新增：Google Sheets 貼上時要能自動分欄，必須是用
                # Tab 字元分隔（貼上純文字時瀏覽器複製到剪貼簿只會是斜線分隔的
                # 一整行文字，Sheets 不會自動拆欄）。這裡另外組一份 Tab 分隔版本，
                # 供貼到 Google Sheets 專用。
                rn_tsv = "\n".join(
                    ["\t".join(_rn_headers + ["LINE"])] +
                    [
                        "\t".join([
                            r["評價日期"], r["姓名"], r["電話"], r["地址"],
                            r["預約下次日期"], r["預約下次時間"], r["服務日期及時間"], r["服務人數"],
                            r["訂單編號"], r.get("LINE") or "",
                        ])
                        for r in rn_results
                    ]
                )
                copy_button("複製整理結果（文字訊息用）", rn_text, "copy_rn_results")
                copy_button("複製整理結果（貼到 Google Sheets 用，會自動分欄，含 LINE 網址）", rn_tsv, "copy_rn_results_tsv")

    elif single_feature == "更新建議下次服務時間":
        info_panel("功能說明", [
            "依「地址(B欄) + 電話(E欄)」查後台該電話底下所有訂單，比對地址後取最近3次"
            "服務日期，寫入 L/M/N 欄（L=最近一次，N=最遠一次）。",
            "登入帳密沿用 Step 1 上方輸入的後台帳號密碼，不用另外輸入。",
            "會自動跳過純儲值金訂單與已取消/已退款訂單。",
        ])

        import next_service_dates as nsd

        _nsd_sheet_options = {
            f"{i+1}. {region}｜gid={gid}": (region, spreadsheet_id, gid)
            for i, (region, spreadsheet_id, gid) in enumerate(nsd.SHEETS)
        }
        nsd_sheet_choice = st.selectbox(
            "目標工作表", ["全部四份"] + list(_nsd_sheet_options.keys()), key="nsd_sheet_choice",
        )

        if st.button("🚀 開始查詢並更新", use_container_width=True, key="nsd_run_btn", type="primary"):
            nsd_logs = []
            nsd_log_box = st.empty()

            def _nsd_ui_log(msg):
                nsd_logs.append(str(msg))
                nsd_log_box.text("\n".join(nsd_logs[-200:]))

            if not backend_email.strip() or not backend_password.strip():
                st.error("請先在上方 Step 1 輸入後台帳號密碼")
            else:
                try:
                    targets = nsd.SHEETS if nsd_sheet_choice == "全部四份" else [_nsd_sheet_options[nsd_sheet_choice]]
                    total_updated = 0
                    with st.spinner("查詢中，依資料量可能需要幾分鐘…"):
                        _session = nsd.login_backend(env, backend_email.strip(), backend_password.strip())
                        for _region, _spreadsheet_id, _gid in targets:
                            _nsd_ui_log(f"▶ 開始處理：{_region}｜gid={_gid}")
                            total_updated += nsd.update_next_service_dates_sheet(
                                _session, _spreadsheet_id, _gid, logger=_nsd_ui_log,
                            )
                    st.success(f"✅ 完成，共更新 {total_updated} 列。")
                except Exception as e:
                    st.error(f"執行失敗：{e}")

    elif single_feature == "會員喜好設定":
        info_panel("使用說明", [
            "輸入電話查詢會員，會列出目前設定的喜愛專員性別。",
            "下方會列出近 N 次「有排班」的服務紀錄（日期＋專員姓名），可針對每位出現過的專員勾選「喜愛」或「不喜愛」。",
            "按下「更新會員喜好設定」才會真的送出，其餘會員資料（姓名/電話/備註等）不會被更動。",
        ])
        mp_phone = st.text_input("客人電話", key="mp_phone")
        mp_n = st.number_input("列出近幾次服務紀錄", min_value=1, max_value=20, value=5, key="mp_n")
        if st.button("🔍 查詢會員", key="mp_lookup_btn"):
            if not mp_phone.strip():
                st.error("請輸入電話")
            elif not backend_email.strip() or not backend_password.strip():
                st.error("請先在上方輸入後台帳號密碼")
            else:
                try:
                    with st.spinner("查詢會員中…"):
                        lookup = qo.quick_lookup_member(
                            env_name=env, backend_email=backend_email.strip(),
                            backend_password=backend_password.strip(),
                            phone=mp_phone.strip(),
                        )
                        if not lookup.get("member_payload"):
                            st.error("查無此會員")
                            st.session_state.mp_data = None
                        else:
                            member = lookup["member_payload"]["member"]
                            member_id = member["member_id"]
                            edit_page = fetch_member_edit_page(lookup["session"], member_id)
                            records = fetch_recent_service_records(
                                lookup["session"], mp_phone.strip(), member.get("name", ""), n=int(mp_n),
                            )
                            st.session_state.mp_data = {
                                "session": lookup["session"], "member_id": member_id,
                                "member_name": member.get("name", ""), "edit_page": edit_page,
                                "records": records,
                            }
                except Exception as e:
                    st.error(f"查詢失敗：{e}")
                    st.session_state.mp_data = None

        mp_data = st.session_state.get("mp_data")
        if mp_data:
            st.success(f"✅ 會員：{mp_data['member_name']}")
            gender_labels = ["不限", "限女", "1女", "限男", "1男", "1男1女"]
            current_gender = int(mp_data["edit_page"]["fields"].get("preferredGender") or "0")
            mp_gender_choice = st.radio(
                "喜愛專員性別", gender_labels, index=current_gender, key="mp_gender", horizontal=True,
            )

            roster = mp_data["edit_page"]["roster"]
            # 依姓名建立 name -> cleaner_id 對照（同名時取第一個符合的，並在畫面上提醒可能有同名狀況）
            name_to_ids = {}
            for cid, info in roster.items():
                name_to_ids.setdefault(info["name"], []).append(cid)

            if not mp_data["records"]:
                st.info("查無近期有排班的服務紀錄。")
            else:
                st.markdown("**近期服務紀錄：**")
                unique_names = []
                for rec in mp_data["records"]:
                    date_part = f"{rec['date_clean']}（{rec['order_no']}）" if rec["order_no"] else rec["date_clean"]
                    st.caption(f"{date_part}：{' X '.join(rec['cleaner_names']) or '（無資料）'}")
                    for cn in rec["cleaner_names"]:
                        if cn not in unique_names:
                            unique_names.append(cn)

                st.markdown("**設定喜愛/不喜愛專員：**（同一位不能同時勾選兩個，若都勾了送出前會被擋下並提示）")
                pref_choices = {}
                has_conflict = False
                for cn in unique_names:
                    ids = name_to_ids.get(cn, [])
                    if not ids:
                        st.warning(f"⚠️「{cn}」在會員編輯頁的專員名單裡找不到對應資料，無法設定（可能是離職或名字打法不同）。")
                        continue
                    if len(ids) > 1:
                        st.caption(f"（注意：「{cn}」有 {len(ids)} 位同名專員，將套用到第一位，麻煩人工確認是否正確）")
                    cid = ids[0]

                    # v2026.07.07 修正：改成兩個獨立的勾選框放在姓名前面
                    # （喜愛專員／不喜愛專員），取代原本的單選按鈕。
                    col_like, col_dislike, col_name = st.columns([1, 1.3, 3])
                    with col_like:
                        is_liked = st.checkbox("喜愛專員", value=roster[cid]["liked"], key=f"mp_like_{cid}")
                    with col_dislike:
                        is_disliked = st.checkbox("不喜愛專員", value=roster[cid]["disliked"], key=f"mp_dislike_{cid}")
                    with col_name:
                        st.markdown(f"　{cn}")

                    if is_liked and is_disliked:
                        st.error(f"「{cn}」不能同時勾選喜愛和不喜愛，請取消其中一個。")
                        has_conflict = True

                    pref_choices[cid] = "喜愛" if is_liked else ("不喜愛" if is_disliked else "不變")

                if st.button("✅ 更新會員喜好設定", key="mp_submit_btn", type="primary", disabled=has_conflict):
                    try:
                        liked_ids = {cid for cid, info in roster.items() if info["liked"]}
                        disliked_ids = {cid for cid, info in roster.items() if info["disliked"]}
                        for cid, choice in pref_choices.items():
                            liked_ids.discard(cid)
                            disliked_ids.discard(cid)
                            if choice == "喜愛":
                                liked_ids.add(cid)
                            elif choice == "不喜愛":
                                disliked_ids.add(cid)
                        with st.spinner("更新中…"):
                            submit_member_preferences(
                                mp_data["session"], mp_data["member_id"], mp_data["edit_page"],
                                preferred_gender=gender_labels.index(mp_gender_choice),
                                liked_ids=liked_ids, disliked_ids=disliked_ids,
                            )
                        st.success("✅ 已更新會員喜好設定。")
                        st.session_state.mp_data = None
                    except Exception as e:
                        st.error(f"更新失敗：{e}")

    # --------------------------------------------------
    # 建立舊客訂單：多筆訂單結果顯示（建立筆數 > 1，或有任何一筆失敗時）
    # --------------------------------------------------
    old_results_multi = st.session_state.get("old_results_multi") if single_feature == "建立舊客訂單" else None
    if old_results_multi and not (len(old_results_multi) == 1 and old_results_multi[0]["ok"]):
        st.markdown("<hr>", unsafe_allow_html=True)
        step("5", "執行結果（多筆）")
        _ok_count = sum(1 for r in old_results_multi if r["ok"])
        st.info(f"共 {len(old_results_multi)} 筆，成功 {_ok_count} 筆，失敗 {len(old_results_multi) - _ok_count} 筆。")
        for _i, r in enumerate(old_results_multi, start=1):
            if r["ok"]:
                res = r["result"]
                st.success(f"✅ 第{_i}筆：{res['order_no']}　{res.get('date')} {res.get('period')}　專員：{res.get('staff') or '（無班表資料）'}")
                if res.get("address_mismatch_warning"):
                    st.warning(res["address_mismatch_warning"])
                if res.get("line_message"):
                    copy_button(f"複製第{_i}筆 LINE 訊息", res["line_message"], f"copy_old_multi_line_{_i}")
            else:
                st.error(f"❌ 第{_i}筆（{r.get('date')} {r.get('period')}）失敗：{r.get('error')}")

    # --------------------------------------------------
    # 建立舊客訂單：建單後結果顯示
    # v8.8：限定只在「建立舊客訂單」分頁顯示，避免切到其他分頁後，
    # session_state 裡殘留的舊訂單結果（q_order_result）還黏在畫面下方，
    # 跟當前分頁剛建立的訂單（例如「建立新客訂單」的 nc_result）混在一起顯示。
    # --------------------------------------------------
    order_result = st.session_state.get("q_order_result") if single_feature == "建立舊客訂單" else None
    if order_result:
        st.markdown("<hr>", unsafe_allow_html=True)
        step("5", "執行結果")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("訂單編號", order_result["order_no"])
        c2.metric("金額（含稅）", order_result.get("service_amount") or order_result.get("price_with_tax") or "—")
        c3.metric("車馬費", order_result.get("fare") or "0")
        c4.metric("確認信", "已發送" if order_result.get("mail_sent") else "未發送")
        _order_lemon_failed = order_result.get("lemon_assignment_ok") is False
        if _order_lemon_failed:
            st.error(order_result.get("lemon_assignment_warning") or "訂單已建立，但樸檬人置換失敗。")
        else:
            st.success(f"✅ 訂單建立成功：{order_result['order_no']}　👤 專員：{order_result.get('staff') or '（無班表資料）'}")
        if order_result.get("price_mismatch_warning"):
            st.warning(order_result["price_mismatch_warning"])
        if order_result.get("address_mismatch_warning"):
            st.warning(order_result["address_mismatch_warning"])
        if order_result.get("order_no_duplicated"):
            show_duplicate_order_warning(order_result.get("order_no"), order_result.get("order_no_duplicate_count", 2), dedup_key=f"old_{order_result.get('order_no')}")
        if _order_lemon_failed:
            st.warning("樸檬人置換完成前，不可發送確認信。")
        elif not order_result.get("mail_sent"):
            if st.button("📧 發送確認信", key="send_mail_btn", type="primary"):
                try:
                    ok_m, msg_m = send_confirmation(order_result)
                    if ok_m:
                        order_result["mail_sent"] = True
                        st.session_state.q_order_result = order_result
                        st.success("✅ 確認信已發送")
                        st.rerun()
                    else:
                        st.error(f"確認信發送失敗：{msg_m}")
                except Exception as e:
                    st.error(f"確認信發送失敗：{e}")
        else:
            st.success("✅ 確認信已發送")
        line_message = build_line_message(order_result)
        col_msg, col_memo = st.columns([3, 1])
        with col_msg:
            st.text_area("LINE 訊息內容", line_message, height=420, label_visibility="collapsed")
            copy_button("複製 LINE 訊息", line_message, "copy-line-message")
        with col_memo:
            st.text_area("N-J Memo", NJ_MEMO, height=200, label_visibility="collapsed", key="nj_memo_order_result")
            copy_button("複製 N-J Memo", NJ_MEMO, "copy-nj-memo-order-result")