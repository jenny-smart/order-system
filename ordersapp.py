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

import streamlit as st
from datetime import date, timedelta

from env import GOOGLE_CALENDAR_MAP
from function.ui_common import step, info_panel
from function import consistency_check as _consistency_check_page
from function import calendar_check as _calendar_check_page
from function import cleaner_next_day_reminder as _cleaner_next_day_page
from function import weekend_reminder_page as _weekend_reminder_page
from function import no_line_link_search as _no_line_link_page
from function import bonus_note as _bonus_note_page
from function import order_creation as _order_creation_page
from function import line_notice_generator as _line_notice_page
from function import next_appointment_list as _next_appointment_page
from function import next_service_time_updater as _next_service_time_page
from function import member_preferences as _member_preferences_page
from accounts import ACCOUNTS
from memo_system.ui import render_memo_system

try:
    import quick_order
except Exception as e:
    st.error(f"quick_order.py 載入失敗：{type(e).__name__}: {e}")
    st.stop()


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
    from function.cancel_order import render_cancel_order

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
    import function.vip_calendar_sync as _vcs
    import function.vip_calendar_patch as _vcp
    from function.vip_calendar_patch import apply_patch as _apply_patch1
    from function.vip_calendar_patch2 import apply_patch as _apply_patch2
    from function.vip_calendar_patch3 import apply_patch as _apply_patch3
    from function.vip_calendar_patch4 import apply_patch as _apply_patch4
    from function.vip_calendar_patch5 import apply_patch as _apply_patch5

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
    _order_creation_page.render_batch(backend_email, backend_password, env)

elif mode == "建立舊客訂單":
    _order_creation_page.render_old_customer(backend_email, backend_password, env)

elif mode == "建立新客訂單":
    _order_creation_page.render_new_customer(backend_email, backend_password, env)

elif mode == "建立儲值金訂單":
    _order_creation_page.render_stored_value_order(backend_email, backend_password, env)

elif mode == "訂單轉換":
    _order_creation_page.render_order_conversion(backend_email, backend_password, env)

elif mode == "儲值金補價差":
    _order_creation_page.render_topup_diff(backend_email, backend_password, env)

elif mode == "雙向訂單檢查":
    _consistency_check_page.render(backend_email, backend_password, env, ACCOUNTS)

elif mode == "後台／Google 日曆雙向比對":
    _calendar_check_page.render(backend_email, backend_password, env, GOOGLE_CALENDAR_MAP)

elif mode == "專員隔日上班提醒":
    _cleaner_next_day_page.render(backend_email, backend_password, env)

elif mode == "週末服務 LINE 提醒":
    _weekend_reminder_page.render(backend_email, backend_password, env)

elif mode == "查詢無LINE連結訂單":
    _no_line_link_page.render(backend_email, backend_password, env)

elif mode == "儲值獎金備註":
    _bonus_note_page.render(backend_email, backend_password, env)

elif mode == "LINE 通知產生器":
    _line_notice_page.render(backend_email, backend_password, env)

elif mode == "整理預約下次服務":
    _next_appointment_page.render(backend_email, backend_password, env)

elif mode == "更新建議下次服務時間":
    _next_service_time_page.render(backend_email, backend_password, env)

elif mode == "會員喜好設定":
    _member_preferences_page.render(backend_email, backend_password, env)
