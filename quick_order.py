# ============================================================
# 檔名：quick_order.py
# 版本：v8.62
# 最後更新：2026-08-12
#
# Change Log
# v8.62
# - 修正合併多個不同服務日期的儲值金／VIP 訂單 LINE 通知：combined_period
#   已包含每筆完整日期，訊息範本不再額外加上第一筆日期，避免第一行日期重複。
# v8.61
# - 新客建單的日期／時段查班表流程改為與舊客一致：使用
#   /booking/single 的 token，先送完整服務表單到 calculate_hour，再將
#   hour/price/price_vvip/fare 回填後查 get_section，避免同資料舊客
#   查得到專員、新客卻因 payload 不完整而被判定無班表。
# v8.59
# - 所有建單的人力判斷必須來自後台回覆的「同日期＋完整同時段」名單；
#   人數不足即停止，不得用短時段或自行推算放行。
# v8.58
# - 修正新客建單班表誤判：get_section 改送完整服務資料，避免已選
#   09:00-12:00 卻回傳 09:00-11:00，導致有人力被判成 0 人。
# - 自動補檸檬人後必須重查到正確時段且人數足夠才可送單，不再因
#   「補班動作成功」就繞過班表驗證。
# - 新客勾選自動補檸檬人時，建單後必須實際把本單換成檸檬人；
#   置換失敗會明確警示，不再顯示為檸檬人成功。
# v8.57
# - 批次／舊客／新客／訂單轉換／儲值金補價差恢復「自動補檸檬人」
#   可選開關。安全保護保留：專員當日只要已有任何班別，補班程式就跳過，
#   不會去動其他客人已配班的專員。
# v8.56
# - 排班安全規則擴大到批次建單、舊客建單、新客建單、訂單轉換與
#   儲值金補價差：這些流程一律禁止自動新增或改寫專員班表，
#   只能使用後台當下已有的可用人力；人力不足就停止。
# - 補班底層增加保護：檸檬人當日只要已有任何班別，就不得寫入新班別，
#   避免動到本來已配班的人員。
# v8.55
# - 訂單轉換安全修正：舊單A與新單B都不得呼叫自動補檸檬人班表，
#   只能使用後台當下已有的可用班表。若人力不足就停止並提示手動處理，
#   避免轉換流程改動「未配班」名單或已配班人員的班別。
# v8.54
# - 修正新客建單／舊客新地址：客人地址已明確寫縣市＋行政區時，只採用地址
#   本身拆出的行政區下拉值；check_contain 僅用來補服務區域必要欄位，不再拿
#   回傳區域名稱覆蓋或否定客人填的行政區。只有客人沒寫行政區時，才用
#   check_contain 回傳值補行政區，補不到就停下。
# v8.53
# - 修正舊客建單價格仍沿用後台 calculate_hour 回傳金額，造成 3人4小時平日
#   12人時被算成 10800。舊客與新客統一用固定公式：平日每人時600、週末
#   每人時700；送後台時反推未稅 price 欄位，避免後台再乘稅後金額跑掉。
# v8.52
# - 修正 _build_purchase_edit_payload_from_page 誤塞 _method=PUT，導致
#   _update_order_invoice_no_text／_update_order_note 呼叫 /purchase/edit/{id}
#   一律回 HTTP 405（訂單修改頁的表單本來就是純 POST，沒有 _method 欄位，
#   後台也沒註冊 PUT 路由）。移除這個誤塞的欄位，改回純 POST。
# v8.51
# - 訂單轉換第二段／儲值金補價差第二段：總金額扣車馬費為 0 時，改回呼叫
#   _mark_order_as_paid 自動標記已付款（v8.47 一度改成只註記發票不改付款
#   狀態，現依客服確認改回兩個動作都要做：標記已付款＋發票號碼欄註記
#   「不開立發票」）。
# - build_line_message：折抵後金額（price／customer_due）為 0 時，信用卡
#   分支不再顯示刷卡連結，ATM 分支不再顯示匯款帳號資訊，兩者都改顯示
#   「本次費用已由優惠券全額折抵，無需另行付款/匯款」，避免客人誤會還要
#   再付一次錢。
# v8.50
# - 修正 build_line_message：ATM「轉帳金額」跟信用卡「服務金額」這兩行，
#   原本不管優惠券折抵多少，一律顯示折抵前的原始訂單金額（訂單轉換／
#   儲值金補價差用優惠券折掉大半後，LINE 訊息卻還是要客人匯全額）。
#   改成只要呼叫端有算出 customer_due（折抵後客人實際待付金額），就一律
#   顯示 customer_due。
# - convert_order_stage2_create_new_orders：order_result 補上 customer_due
#   欄位，讓 build_line_message 實際拿得到折抵後金額（原本只算出來卻沒有
#   塞進 order_result，等於白算）。
# - stored_value_makeup_create_paid_order：custom_amount_line 改用
#   service_due（總金額扣車馬費後、已反映優惠券折抵的真正待付金額）取代
#   原本錯用的訂單原始金額，同時補上 customer_due 欄位。
# v8.49
# - 訂單轉換第二段（convert_order_stage2_create_new_orders）：新單配班的
#   allow_auto_lemon_shift 原本寫死 True，客服無法個別關閉；改成讀每筆
#   new_orders[i].get("allow_lemon", True)，預設維持原行為（True），但可
#   針對個別新單關閉「無人力時自動補檸檬人」。
# v8.48
# - 移除新單成單時可能把地址誤判成大安區的區域查詢/預設 fallback：
#   不再用 geocode 猜行政區、不再用 area_id=25/company_id=1 當預設值；
#   舊客既有地址優先使用會員地址已存的 area_id/company_id，新地址若後台
#   check_contain 查不到明確區域就直接擋下，不靜默套用大安區。
# v8.47
# - 訂單轉換與儲值金補價差建立新單後，若「總金額扣除車馬費」等於 0，
#   僅在訂單修改頁的發票號碼欄註記「不開立發票」，不再呼叫 set_success
#   改付款狀態，也不動加收/待退等其他欄位。若仍大於 0，付款與發票皆不動。
# v8.46
# - 訂單轉換與儲值金補價差建立新單後，會先回查後台訂單卡片，以「總金額
#   扣除車馬費」判斷實際服務待收金額；只有等於 0 時才自動標記已付款並在
#   發票號碼欄標註「不開立發票」。若不為 0，保留待付款與正常發票狀態，
#   避免仍有客付差額時被誤標成已付款/不開發票。
# v8.45
# - fetch_rating_next_appointments 改成用完整評價時間戳記（含時分秒）由舊到
#   新排序，符合畫面「評價日期愈新在愈下方」的要求（原本沿用後台頁面本身
#   「愈新在愈上面」的排序，且只用日期排序，同一天多筆時順序不精準）。
# v8.44
# - 新增 _fetch_line_url_for_order_no：直接在原始 HTML 裡找對應訂單編號的
#   <tr>，抓出裡面 chat.line.biz 的連結網址（extract_order_cards_from_purchase_html
#   把 HTML 轉純文字時會把 href 弄丟，只剩下顯示文字「LINE」，所以需要另外
#   抓）。fetch_rating_next_appointments 現在每筆都會多帶一個 LINE 網址欄位。
# v8.43
# - 修正 fetch_rating_next_appointments 漏抓迄日當天資料的 bug：後台
#   /rating 的 date_e 篩選似乎是用「當天00:00:00」比對評價的完整時間戳記，
#   導致迄日當天稍晚時間的評價被排除。改成送給後台的 date_e 多加一天當
#   緩衝，抓回資料後再用本地解析出的實際評價日期重新過濾回正確區間。
# v8.42
# - 新功能：整理預約下次服務。新增 fetch_rating_next_appointments，搜尋
#   /rating 評價日期區間內有勾選預約下次服務的評價，回頭查每筆訂單抓出
#   電話/地址/服務日期時數/人數，組成「評價日期／姓名／電話／地址／
#   預約下次日期／預約下次時間／服務日期及時間／服務人數」的整理名單。
# v8.41
# - 「查無班表或人數不足」的擋單訊息加上除錯資訊（area_id/company_id/
#   get_section 原始回應前300字），方便比對排班頁畫面看到的人力跟系統
#   查詢班表時用的區域是否一致。
# v8.40
# - 新客建單時查到電話其實已是舊客會員，新增 existing_member_warning 提醒
#   （不再默默沿用舊會員資料，完全不告知客服）。
# - 舊客可以約新地址：quick_create_order／quick_check_available_slots
#   原本地址不在會員既有清單裡就直接擋單，現在改成當新地址處理（跟新客
#   建單新地址邏輯一致，用 geocode + check_contain 動態算區域）。
# - quick_create_order 補上跟新客流程一致的 address_mismatch_warning
#   （比對後台實際存的地址跟送出地址是否一致）。
# - 修正 check_contain 參數名稱打錯的 bug：新客新地址那段原本送
#   member_id/clean_type_id（snake_case），後台實際要的是
#   memberId/cleanTypeId（camelCase，比對後台原始頁面 JS 確認），打錯導致
#   後台永遠收不到正確參數、查無區域。
# - LINE通知服務名稱不再寫死「居家清潔」，改成依 clean_type_id／訂單卡片
#   文字動態代入正確服務名稱（build_line_message 新增 CLEAN_TYPE_NAME_MAP；
#   用訂單編號查詢時新增 _extract_service_type_label 直接從卡片文字判斷）。
# - 儲值金購買 LINE 訊息（信用卡/ATM）原本 6 段文字全部黏在一起，補上段落
#   空行。
# 舊版：v8.39（最後更新誤植為 2026-07-10，今天實際日期為 2026-07-07）
# - 修正合併訂單 LINE 訊息重複顯示人時的 bug：_format_period_display 本身
#   就會組好「（Ｎ人Ｍ小時），共X人時」的完整格式，之前又手動在後面重複
#   加了一次同樣的文字，導致實際服務時間那行出現兩次一樣的人時說明。
#   訂單轉換跟儲值金補價差都有這個問題，已一併修正。
# v8.38
# - build_line_message 新增 merged_service_time_line／hide_amount_line／
#   custom_amount_line 三個可選欄位，讓呼叫端可以客製化「服務時間」那行
#   跟「服務金額」那行，不用整段複製一份範本改。
# - 訂單轉換（convert_order_stage2_create_new_orders）：每筆新訂單 LINE
#   訊息改成「原訂單A＋新訂單B 合併訂單」格式，另起一行顯示新訂單真正的
#   服務時間，並且不顯示服務金額（新訂單是優惠券折抵成0，顯示金額容易讓
#   客人誤會）。
# - 儲值金補價差（stored_value_makeup_create_paid_order）：LINE 訊息同樣
#   改成「儲值金歸零訂單＋補價差訂單 合併訂單」格式，但服務金額這行要
#   顯示，並註明「已扣除儲值金餘額$XXXX」。
# v8.37
# - convert_order_stage2_create_new_orders 補上跟儲值金補價差第二段一致的
#   動作：每筆新訂單建立後標記為已付款（_mark_order_as_paid）、發票號碼
#   欄位標註「不開立發票」（_update_order_invoice_no_text）。之前這兩個
#   動作只有儲值金補價差有做，訂單轉換漏掉了。
# v8.36
# - 發票欄位標註文字改成「不開立發票」（原本寫「不用開發票」），跟後台實際
#   顯示格式一致，已用真實訂單驗證過（訂單列表會直接顯示「發票：不開立
#   發票」）。
# - 訂單轉換改成跟儲值金補價差一樣的分階段介面，新增
#   convert_order_stage1_reassign_original（第一段：把原訂單A的服務日期
#   改到指定新日期，並一律自動補檸檬人排班，不用客服勾選，此單必須全是
#   檸檬人）跟 convert_order_stage2_create_new_orders（第二段：用第一段
#   結果建折價券＋建新訂單，並比對原訂單A金額跟新訂單合計是否一致，有差額
#   會在 ph_warning 明確標示）。原本一次到位的 convert_order_multi 保留
#   （內部改成呼叫 stage1+stage2），維持向下相容。
# v8.35
# - 找到「儲值金訂單付款方式空白、卡在待付款」的真正根因：實際查看
#   /booking/stored_value_routine 頁面原始 HTML 後發現，這個頁面本身「有」
#   payway 欄位，只是選項只有一個「儲值金」（<option value="4">儲值金
#   </option>），而且是 required 必填 select。_build_booking_submit_data
#   之前誤以為這個頁面完全不需要 payway 而把它整個拿掉，導致送給後台的
#   表單缺少必填欄位——這才是真正原因，不是 v8.35 之前懷疑的 token 來源
#   問題（token 那個修正本身沒有錯，只是不是這次的根因，予以保留）。
#   修法：儲值金訂單改成固定送 payway=4，其餘發票相關欄位（這個頁面本來
#   就沒有）維持移除。已用單元測試確認送出的資料正確包含 payway=4。
# v8.34
# - 依客服重新確認的儲值金補價差完整流程，補齊三個缺漏：
#   1. 第一段（儲值金清零單）換人為檸檬人時，原本沒開 allow_auto_lemon_shift，
#      排班頁若當下沒有現成檸檬人可換就會直接失敗，不符合「此單必須全是
#      檸檬人」的規定。改成強制開啟，補不到才會顯示失敗訊息。
#   2. 新增 _mark_order_as_paid：第二段（客付補價差單）建立後呼叫後台
#      /purchase/set_success/{id} 標記為已付款，不能讓它卡在待付款狀態
#      （這張單全額用優惠券折抵，客人本來就不需要再實際付款）。
#   3. 新增 _update_order_invoice_no_text：第二段建立後把訂單編輯頁的
#      「發票號碼」欄位標註成「不用開發票」，避免財務誤以為漏開發票。
# v8.33
# - 修正重大 bug：儲值金訂單（payway=儲值金）建單時，如果地址檢查
#   （check_contain）用 stored_value_routine 頁面的 token 失敗，v8.5 加的
#   備援邏輯會向 /booking/single 借一個 token 重試，成功後把 token 變數
#   永久換成借來的那個——但後面正式送出建單時也繼續沿用這個借來的 token，
#   導致送到 /booking/stored_value_routine 的請求帶著 /booking/single 頁面
#   發出的 token，後台可能因此誤判、出現付款方式空白、訂單卡在待付款、
#   儲值金沒有真的被扣除的情況（實際案例：TT00212129）。
#   修法：不管前面 check_contain 階段借用過哪個網址的 token，正式送出建單
#   前一律重新跟「這筆訂單實際要用的建單網址」（依 payway 對應，儲值金訂單
#   就是 /booking/stored_value_routine）要一個乾淨的 token。
# v8.32
# - 儲值金補價差（stored_value_makeup_create_stored_order/create_paid_order）
#   人數不夠時，改成自動補檸檬人排班（allow_auto_lemon_shift=True 寫死），
#   不用客服另外勾選，補不到才會被 quick_create_order 擋單。之前這兩個函式
#   完全沒有自動補檸檬人的參數，人數不夠一定會直接被 v8.31 的擋單邏輯擋下。
# v8.31
# - 修正重大規則漏洞：查無班表或人數不足時，quick_create_order（舊客快速
#   建單）跟 quick_create_new_customer_order（新客資料拆解）之前都會「仍
#   嘗試建單」，只在畫面標記「（待配班）」或直接靜默略過（except: pass），
#   等於人力不足的訂單照樣成單，不符合「不論服務日期遠近，人數不夠一律
#   不能成單」的業務規則。現在改成：查完班表（含允許時的自動補檸檬人重查）
#   後，只要人數還是不夠，直接 raise Exception 擋單，不會送出訂單。
#   訂單轉換（convert_order/convert_order_multi）跟儲值金補價差都是呼叫
#   quick_create_order 建單，自動一併套用這個修正，不用另外改。
# - quick_create_new_customer_order 補上建單成功後的實際專員名字（"staff"
#   欄位），原本完全沒有回傳這個資訊。
# v8.30
# - 修正 _parse_invoice_details_from_block 解析手機載具/自然人憑證時，把
#   開頭的「/」去掉了（例如「/HWHMPF6」解析成「HWHMPF6」）。台灣手機條碼
#   載具本來就是「/」開頭的格式，送出去的 carrier_info 要保留這個「/」，
#   不然送到後台的載具號碼會是錯的。已修正為保留開頭的「/」。
# v8.29
# - 修正「儲值金購買」建出來的訂單完全沒有姓名/Email 的問題：後台
#   /booking/stored_value 表單裡「會員姓名/會員帳號/市內電話」雖然是唯讀
#   （readonly）欄位，但仍然是 name="name"/"email"/"tel" 的 input，送出
#   表單時一樣會帶上這三個值。create_stored_value_purchase_order 雖然有
#   呼叫查詢會員 API 拿到姓名/Email，卻忘記把這三個欄位放進最後送出的
#   post_data，導致建出來的訂單姓名/Email 都是空的。已補上。
# v8.28
# - 修正查詢優先順序：改成嚴格依序查（儲值金 → 查不到才查VIP → 查不到才查
#   專業清潔），不是把儲值金跟VIP兩類合併起來比日期取最新一筆（v8.27 誤解
#   了客服要的優先順序，這次改正）。
# - 新增 _pick_block_with_real_payway：每個類別裡都只採用付款方式真的是
#   「信用卡」或「ATM」的訂單，跳過付款方式是「儲值金」的訂單——那種是用
#   既有餘額折抵消費，不是真正付款，也不會有發票，不能拿來當範本。如果
#   該類別最新一筆剛好是儲值金折抵，會繼續往下找同類別裡次新、且付款方式
#   是信用卡/ATM 的那一筆，不會直接放棄整個類別。
#   已用「儲值金類別直接命中」「儲值金類別最新一筆是折抵、跳過選次新」
#   「儲值金類別查無、改查VIP」三種情境測試過，結果都正確。
# - search_debug 補上 skipped_stored_value_payway，記錄哪些訂單因為付款
#   方式是儲值金被跳過，畫面會另外用表格顯示。
# v8.26
# - 重新設計「儲值金購買」查詢會員歷史付款方式/發票的邏輯：改用後台「購買
#   項目」(buy=vip/5/1) + 「付款狀態」(purchase_status=已付款) 伺服器端篩選
#   直接查，不再用「只篩電話、查全部訂單、自己在前端分類」的做法。
#   　根因：後台訂單列表預設一頁只有 20 筆，只用電話篩選（沒指定購買項目）
#   　時，訂單量大的客戶很容易一頁就被一般清潔訂單佔滿，真正要找的 VIP／
#   　儲值金購買訂單被擠到第二頁以後，程式只抓第一頁，就會誤判成「查無
#   　資料」——這正是「康健診所」這種常態下單客戶一直查不到的真正原因。
#   VIP／儲值金兩類會一起比對「建立時間」找真正最新的一筆，不是固定優先
#   哪一類；都找不到才查專業清潔。用康健診所真實訂單資料（三筆已付款儲值金
#   購買訂單）驗證過，能正確選到最新一筆並取出正確的付款方式/發票設定。
# - search_debug 改成記錄「依序查了哪些類別、各查到幾筆、有哪些訂單編號」，
#   查無資料時可以直接看出是哪個環節查不到，不用再靠反覆截圖排查。
# v8.25
# - 「儲值金購買」查不到會員過去訂單設定時，不再只顯示一句「查無資料」，
#   改成把實際查詢過程回傳出來（HTTP 狀態碼、這支電話查到幾張訂單卡片、
#   每張卡片的訂單編號/分類結果/是否算已付款），交由畫面用表格顯示。
#   這樣往後如果又查不到，可以直接從畫面上的表格判斷是「後台真的查不到
#   任何訂單」還是「查得到訂單但分類/已付款判斷有誤判」，不用再靠反覆
#   猜測跟來回截圖排查。
# v8.24
# - 修正「儲值金購買」一直查不到會員過去訂單設定的真正根因：
#   _find_payway_invoice_source_for_stored_value 跟 _fetch_latest_stored_
#   value_order_no 裡查詢 /purchase 用的是裸的 `PURCHASE_URL`，但這個名稱在
#   quick_order.py 裡從沒被 import 過（全部其他地方都是用 `orders.PURCHASE_URL`，
#   因為它是依環境 dev/prod 動態設定的）。這會直接丟出 NameError，但剛好被
#   函式自己的 `except Exception:` 整個吞掉，才會靜默顯示「查無資料」而不是
#   報錯，很難察覺。已全部改成 `orders.PURCHASE_URL`。
# - 依客服提供的精確規則調整搜尋範圍：
#   1. 只採用「付款狀態：已付款」的訂單當範本，未付款的訂單一律不採用。
#   2. 找不到 VIP/儲值金購買訂單時，退回的「一般服務訂單」精準限定為
#      「專業清潔」類別（居家清潔/辦公室清潔/裝修細清/大掃除/搬出清潔/
#      搬入清潔），不是任何非 VIP/儲值金的訂單都算數。
#   已用實際訂單資料（VIP券兩筆已付款訂單、信用卡、二聯式會員載具）驗證過，
#   結果正確。
# v8.23
# - 修正「儲值金購買」查不到會員過去 VIP/儲值金/一般服務訂單設定的問題：
#   _find_payway_invoice_source_for_stored_value 跟 _fetch_latest_stored_
#   value_order_no 查詢 /purchase 時，原本只送 {"phone": ...} 單一參數，
#   跟後台搜尋表單瀏覽器實際送出的參數（所有欄位都會帶上，只是空字串）不同，
#   可能觸發後台不同的預設篩選邏輯（例如自動套用當月日期區間），導致查到的
#   結果比預期少甚至查無資料。現在統一改用既有的
#   PURCHASE_FILTER_PARAMS_TEMPLATE 當底，只覆蓋真正要篩選的欄位。
# v8.22
# - 修正 create_stored_value_purchase_order 執行時報錯
#   「name 'BeautifulSoup' is not defined」：quick_order.py 過去都是透過
#   orders 模組的函式間接處理 HTML，從沒有直接用過 BeautifulSoup，這次新增的
#   儲值金購買建單功能是第一個直接呼叫 BeautifulSoup 解析 /booking/stored_value
#   頁面 token 的地方，但漏加 import。已補上 `from bs4 import BeautifulSoup`。
# v8.21
# - 新增「儲值金購買」自動建單功能（create_stored_value_purchase_order），
#   對應後台 /booking/stored_value（代客預訂-VIP儲值金）頁面，客人自己買/
#   儲值一筆金額，用信用卡或ATM付款。
#   付款方式/發票資訊依客服指定的優先順序自動判斷，不用手動選：
#   1. 這支電話最近一次 VIP 購買或儲值金購買訂單的付款方式/發票設定
#      （新增 _classify_order_block_type，鎖定「建立時間」那一行的下一行
#      判斷購買項目類型，避免誤抓客服/財務備註裡出現的「VIP」字樣）。
#   2. 都找不到才退回最近一次一般服務訂單的設定。
#   3. 都找不到就不會自動送出，回傳 need_manual_confirm，交由客服人工確認。
#   新增 _parse_invoice_details_from_block 解析二聯式/三聯式/捐贈發票的明細
#   （會員載具/手機載具/自然人憑證/紙本、公司抬頭統編、捐贈碼）。
#   建立成功後會嘗試用 build_stored_value_purchase_message 產生對應的 LINE
#   通知訊息。地區＝登入帳號本身所屬地區，對應 companyId（台北=1/桃園=2/
#   新竹=3/台中=4）。
# v8.20
# - 修正台中 ATM 儲值金購買範本：v8.19 我誤植成一份自己猜測的「方案說明」條列
#   式文案，跟客服提供的正確版本完全不同。現在改成台北／台中共用同一個骨架
#   （跟一般 ATM 訂單一樣，先講儲值金額/贈購物金，再附匯款帳戶資訊），只換
#   銀行戶名/代碼/帳號（台中為：泳檬有限公司／台北富邦銀行(012)-營業部／
#   00200102520512），轉帳金額一律依訂單實際金額帶入，不寫死。
# v8.19
# - 新增「儲值金購買」訂單的 LINE 通知專用範本（信用卡／ATM-台北／ATM-台中
#   三種），跟一般清潔服務訂單完全分開處理：客人買/儲值金額本身用信用卡或
#   ATM 付款，訂單沒有服務日期/地址，原本套用一般範本會出錯或格式不對。
#   新增 _extract_stored_value_purchase_info 直接從訂單內容裡「儲值金-台北
#   (儲值金50,000贈購物金2,500)」這段文字解析出區域/金額/贈購物金，不使用
#   寫死的金額對照表，任何金額組合都能正確解析、不用之後再改 code。
#   build_line_message_from_order_no 會優先判斷是否為儲值金購買訂單，是的話
#   直接用專用範本；build_combined_line_message_from_order_nos 若合併清單中
#   出現儲值金購買訂單則直接擋下，提示改用單筆查詢（合併多筆沒有意義）。
# v8.14
# - 拿掉 _lookup_district_via_geocode 裡的 Nominatim（OpenStreetMap）免費備援：
#   實測發現它在台灣的行政區判斷常常不準（例如把「羅斯福路二段」誤判成大安區，
#   實際上是中正區）。猜錯比不猜更糟——猜錯的區域會被我們送出去，之後後台存的
#   地址剛好跟猜的一樣，address_mismatch_warning 反而抓不到這個錯誤。現在只用
#   準確度高很多的 Google 地理編碼 API；沒有金鑰或查詢失敗就不猜，維持原地址，
#   交由既有的地址比對警示去抓後續落差。
# v8.13
# - 新增訂單編號重複偵測（_check_order_no_duplicate）：quick_create_order 與
#   quick_create_new_customer_order 建單成功後，會用「訂單編號」篩選查詢後台
#   訂單列表，若同一個訂單編號查到一張以上的訂單卡片，代表後台產生了重複的
#   訂單編號，回傳值加上 order_no_duplicated / order_no_duplicate_count /
#   duplicate_order_warning，供畫面用提醒視窗警示客服。
# - 查無班表時是否自動勾檸檬人排班，改為必須明確開啟才會執行（新增
#   allow_auto_lemon_shift 參數，預設 False）：
#   quick_create_order、quick_create_new_customer_order、
#   assign_lemon_cleaners_to_order、_assign_mixed_cleaners_to_order、
#   convert_order、convert_order_multi 皆新增此參數並貫穿內部呼叫。
#   預設不再「查不到班表就自動勾檸檬人」，必須客服在畫面上勾選才會執行；
#   未開啟時查無可換班檸檬人會直接回傳明確訊息，不會靜默嘗試自動勾班。
# v8.12
# - 重寫 parse_new_customer_text：
#   1. 不管客人貼上的文字有沒有「訂購人姓名：」等標籤，都能辨識姓名/電話/Email/
#      地址/坪數/付款方式（無標籤格式支援一行一個欄位，依序姓名/電話/Email/地址/
#      坪數/付款方式/備註）。
#   2. 標籤與冒號之間允許有空白（例如「室內坪數 :45」），修正原本因為多一個空白
#      就抓不到值的問題。
#   3. 付款方式支援「信用卡 / 轉帳匯款 擇一　轉帳」這種列出選項＋客人實際填寫
#      答案的格式，取「擇一」之後的內容判斷，不會誤判成說明文字列出的所有選項。
#   4. 付款方式完全判斷不出來時，payway 回傳空字串並將 need_ask_payway 設為
#      True，不再默默預設成信用卡，交由畫面請客服手動選擇。
#   5. 發票載具/統編偵測不到明確填寫值時（例如只有說明文字）carrier/company_no
#      皆為空字串，維持「未填則走會員載具」的既有預設行為。
# v8.11
# - 修正新客建單（quick_create_new_customer_order）地址被誤標成錯誤區域（例如
#   一律變成「大安區」）的根因：新地址查詢區域時（check_contain）原本 lat/lng
#   永遠送空字串，未先呼叫 geocode_address 取得經緯度，導致 check_contain 查無
#   正確結果，area_id 掉進寫死的 fallback "25"（該編號在後台對應到錯誤區域）。
#   現在改為先 geocode 取得經緯度再查詢，且查無正確 area_id 時直接丟出明確錯誤，
#   不再默默套用可能錯誤的固定值。此問題只影響全新地址（會員從未購買過的地址），
#   後台手動建單或既有地址不受影響，符合實際觀察到的現象。
# v8.9
# - quick_create_new_customer_order 建單後回查同時比對地址：若後台實際地址與我們
#   送出的地址不同（例如後台自動判斷區域時加了不正確的市/區前綴，如「台北市大安區」
#   被疊加在正確地址前面），回傳值加上 address_mismatch_warning 與
#   backend_actual_address，供畫面顯示警示。此類地址被後台改動的情況經確認並非
#   本系統送出資料有誤，而是後台端自身的地址正規化行為，此警示用於即時發現、
#   方便回報或至後台手動修正。
# v8.7
# - quick_create_new_customer_order 新增建單後回查後台實際金額並與人時公式
#   （600平日/700週末 × 人時，不含車馬費）比對；若後台實際金額不同，回傳值加上
#   price_mismatch_warning 與 backend_actual_amount，供畫面顯示警示，方便立即發現
#   金額被後台依坪數/房間數等另行計價覆蓋的情況。
# v8.6
# - 修正 _build_combined_period_display：單筆訂單合併時不再重複附加「，共X人時」
#   （原本每筆訂單自帶一次人時小計，加總後又整體附加一次，單筆時造成完全重複顯示）。
# - quick_create_new_customer_order 回傳值補齊 date/period/region/fare/service_amount/
#   actual_period 等 build_line_message 需要的欄位，避免呼叫端組 LINE 訊息時 KeyError
#   或缺少地址所屬區域資訊。
# - 新增 _fix_address_district_order 與 _lookup_district_via_geocode：新客地址若完全缺少
#   行政區（區/鄉/鎮），會嘗試查詢並補在「市/縣」之後；若地址本身區域順序錯誤
#   （例如「大安區台北市...」），會自動對調為「台北市大安區...」。查詢失敗不會擋住建單。
# v8.5
# - 新增 _fetch_csrf_from_url：儲值金訂單地址檢查（check_contain）失敗時，
#   改向 /booking/single 借一個可靠的 CSRF token 重試，不影響 orders.BOOKING_URL。
# - _build_booking_submit_data：儲值金訂單不再帶 payway/invoice_type/carrier_type_id/
#   carrier_info/company_title/company_no/donate_code 等付款與發票欄位。
# - quick_create_order：新增 _booking_balance_error，偵測後台回傳的儲值金餘額不足
#   JSON（stored_value_balance 存在且 count=0），直接明確告知餘額不足與目前餘額，
#   不再顯示模糊的「count>0 但查無新單」錯誤。
# v8.4
# - 新增 _assign_mixed_cleaners_to_order：配班優先用排班頁現有一般專員，不足再補檸檬人。
# - 新增 convert_order_multi：一張原單A → 多筆新單B1/B2/B3，每筆各建一張折價券。
#   原單A配班走混合邏輯。備註格式：A+B1+B2+B3 合併服務。
# v8.3 - 排班換人必須勾選足夠不同的檸檬人
# v8.2 - 檸檬人補勾依序檸檬人1/2/3
# v8.1 - 儲值金補價差第二段沿用第一段餘額
# v8.0 - 檸檬人清單解析新增 shift 頁掃描備援
# v7.9 - 檸檬人勾班衝突自動跳過
# v7.8 - 儲值金清零邏輯修正
# v7.7 - 儲值金補價差拆兩段
# v7.3 - PERIOD_DISPLAY_INFO / _format_period_display
# ============================================================
# -*- coding: utf-8 -*-
__version__ = "8.39"

import time
import re
import json
from datetime import date, datetime, timedelta

import requests
from bs4 import BeautifulSoup

import orders
from orders import (
    login, get_csrf_token, get_member, pick_best_address_info,
    geocode_address, check_contain, calculate_hour, extract_calc_fields,
    get_section_raw, slot_exists_in_section_response,
    extract_cleaners_from_section_response, format_staff_from_cleaners,
    fetch_order_meta_by_order_no, extract_order_cards_from_purchase_html,
    _extract_staff_line, send_confirmation_mail, normalize_phone,
    normalize_addr_for_match, display_period_text, first_nonzero,
    find_nested_value, get_region_by_address, HEADERS,
)
from accounts import ACCOUNTS
from env import BASE_URL_DEV, BASE_URL_PROD, ORDER_PREFIX_DEV, ORDER_PREFIX_PROD

PAYWAY_MAP = {"信用卡": "1", "ATM": "2", "儲值金": "4"}
BOOKING_ENDPOINT_MAP = {"信用卡": "/booking/single", "ATM": "/booking/single", "儲值金": "/booking/stored_value_routine"}


def normalize_booking_payway(payway):
    text = str(payway or "").strip()
    if text in PAYWAY_MAP:
        return text
    if "儲值金" in text:
        return "儲值金"
    if "信用卡" in text or "刷卡" in text:
        return "信用卡"
    if "ATM" in text.upper() or "匯款" in text or "轉帳" in text or "藍新" in text:
        return "ATM"
    return text
TAX_RATE = 1.05

PERIOD_DISPLAY_INFO = {
    "08:30-12:30": ("4小時", False), "09:00-11:00": ("2小時", False),
    "09:00-12:00": ("3小時", False), "14:00-16:00": ("2小時", False),
    "14:00-17:00": ("3小時", False), "14:00-18:00": ("4小時", False),
    "09:00-16:00": ("6小時", True), "09:00-18:00": ("8小時", True),
}

COUPON_COMPANY_ID_MAP = {"台北": "1", "桃園": "2", "新竹": "3", "台中": "4"}
COUNTRY_ID_BY_CITY_AREA = {
    ("台北市", "中正區"): "8", ("台北市", "大同區"): "9", ("台北市", "中山區"): "10",
    ("台北市", "松山區"): "11", ("台北市", "大安區"): "12", ("台北市", "萬華區"): "13",
    ("台北市", "信義區"): "14", ("台北市", "士林區"): "15", ("台北市", "北投區"): "16",
    ("台北市", "內湖區"): "17", ("台北市", "南港區"): "18", ("台北市", "文山區"): "19",
    ("新北市", "板橋區"): "22", ("新北市", "汐止區"): "23", ("新北市", "新店區"): "30",
    ("新北市", "永和區"): "33", ("新北市", "中和區"): "34", ("新北市", "土城區"): "35",
    ("新北市", "三峽區"): "36", ("新北市", "樹林區"): "37", ("新北市", "鶯歌區"): "38",
    ("新北市", "三重區"): "39", ("新北市", "新莊區"): "40", ("新北市", "泰山區"): "41",
    ("新北市", "林口區"): "42", ("新北市", "蘆洲區"): "43", ("新北市", "五股區"): "44",
    ("桃園市", "中壢區"): "49", ("桃園市", "平鎮區"): "50", ("桃園市", "桃園區"): "55",
    ("桃園市", "龜山區"): "56", ("桃園市", "八德區"): "57", ("桃園市", "蘆竹區"): "61",
    ("新竹市", "東區"): "62", ("新竹市", "北區"): "63", ("新竹市", "香山區"): "64",
    ("新竹縣", "竹北市"): "65", ("新竹縣", "新豐鄉"): "67", ("新竹縣", "寶山鄉"): "71",
    ("新竹縣", "竹東鎮"): "72",
    ("苗栗縣", "竹南鎮"): "78", ("苗栗縣", "頭份市"): "79",
    ("台中市", "中區"): "96", ("台中市", "東區"): "97", ("台中市", "南區"): "98",
    ("台中市", "西區"): "99", ("台中市", "北區"): "100", ("台中市", "北屯區"): "101",
    ("台中市", "西屯區"): "102", ("台中市", "南屯區"): "103", ("台中市", "太平區"): "104",
    ("台中市", "大里區"): "105", ("台中市", "烏日區"): "107", ("台中市", "潭子區"): "114",
    ("台中市", "大雅區"): "115",
    ("台南市", "中西區"): "204", ("台南市", "東區"): "205", ("台南市", "南區"): "206",
    ("台南市", "北區"): "207", ("台南市", "安平區"): "208", ("台南市", "安南區"): "209",
    ("台南市", "永康區"): "210",
    ("高雄市", "新興區"): "241", ("高雄市", "前金區"): "242", ("高雄市", "苓雅區"): "243",
    ("高雄市", "鹽埕區"): "244", ("高雄市", "鼓山區"): "245", ("高雄市", "前鎮區"): "247",
    ("高雄市", "三民區"): "248", ("高雄市", "楠梓區"): "249", ("高雄市", "小港區"): "250",
    ("高雄市", "左營區"): "251", ("高雄市", "岡山區"): "254", ("高雄市", "橋頭區"): "259",
    ("高雄市", "梓官區"): "260", ("高雄市", "彌陀區"): "261", ("高雄市", "鳳山區"): "264",
}
COUNTRY_ID_BY_CITY_AREA.update({
    (city.replace("台", "臺"), area): country_id
    for (city, area), country_id in list(COUNTRY_ID_BY_CITY_AREA.items())
    if "台" in city
})
COUPON_SERVICE_ITEM_MAP = {
    "居家清潔": "1", "辦公室清潔": "2", "裝修細清": "3", "年節大掃除": "4",
    "冷氣機清潔": "5", "洗衣機清潔": "6", "沙發/床墊清潔": "7", "整理收納": "8",
}
COUPON_TYPE_MAP = {
    "不得與其他優惠券重複": "1",
    "可重複使用，每個帳號限用一次": "2",
    "可重複使用，不限使用次數": "3",
}
COUPON_ADD_URL_PATH = "/coupon/add"

VALUE_TO_SHIFT_CODE = {
    "6": "全6", "8": "全8",
    "0830-1230": "上4", "0900-1200": "上3", "0900-1100": "上2",
    "1400-1600": "下2", "1400-1700": "下3", "1400-1800": "下4",
    "1900-2100": "晚2",
}
SHIFT_CONFLICT_TABLE = {
    "全6": {"上3", "上4", "上2", "全6", "全8"},
    "全8": {"上3", "上4", "上2", "下2", "下3", "下4", "全6", "全8"},
    "上3": {"上3", "上4", "上2", "全6", "全8"},
    "上4": {"上3", "上4", "上2", "全6", "全8"},
    "上2": {"上3", "上4", "上2", "全6", "全8"},
    "下3": {"下2", "下3", "下4", "全6", "全8"},
    "下4": {"下2", "下3", "下4", "全6", "全8"},
    "下2": {"下2", "下3", "下4", "全6", "全8"},
}
PERIOD_TO_SHIFT_CODE = {
    "09:00-12:00": "上3", "08:30-12:30": "上4", "09:00-11:00": "上2",
    "14:00-16:00": "下2", "14:00-17:00": "下3", "14:00-18:00": "下4",
    "09:00-16:00": "全6", "09:00-18:00": "全8",
}

PURCHASE_FILTER_PARAMS_TEMPLATE = {
    "keyword": "", "name": "", "phone": "", "orderNo": "",
    "date_s": "", "date_e": "", "clean_date_s": "", "clean_date_e": "",
    "paid_at_s": "", "paid_at_e": "", "refundDateS": "", "refundDateE": "",
    "buy": "", "area_id": "", "isCharge": "", "isRefund": "",
    "payway": "", "purchase_status": "", "progress_status": "",
    "invoiceStatus": "", "otherFee": "", "orderBy": "",
}
_LAST_PURCHASE_FETCH_DEBUG = {}
PURCHASE_STATUS_PAID = "1"


# =========================================================
# 基礎工具函式
# =========================================================

def _format_period_display(period_raw, person="", display_override=""):
    compact = str(period_raw or "").replace(" ", "")
    display = str(display_override or "").replace(" ", "") or compact
    info = PERIOD_DISPLAY_INFO.get(compact)
    person_str = str(person or "").strip()
    if info:
        hour_str, has_break = info
        break_note = "，中間休息1小時" if has_break else ""
        if person_str and person_str != "0":
            inner = f"{person_str}人{hour_str}{break_note}"
            # 計算並加上「共X人時」
            try:
                h = int(float(hour_str.replace("小時", "")))
                p = int(person_str)
                ph = h * p
                ph_note = f"，共{ph}人時"
            except Exception:
                ph_note = ""
        else:
            inner = f"{hour_str}{break_note}"
            ph_note = ""
        return f"{display}（{inner}）{ph_note}"
    if person_str and person_str != "0":
        return f"{display}（{person_str}人）"
    return display


def _extract_actual_service_time(joined_text):
    m = re.search(r"簡訊實際服務時間\s*[：:]?\s*(\d{1,2}:\d{2})\s*[-~～]\s*(\d{1,2}:\d{2})", joined_text)
    if m:
        start, end = m.groups()
        return f"{start} - {end}"
    return ""


def _extract_phone_from_block_lines(lines):
    joined = "\n".join(lines)
    m = re.search(r"(?:\+?886[-\s]?)?0?9[\d\-\s]{8,10}", joined)
    if m:
        return normalize_phone(m.group(0))
    return ""


def _build_combined_period_display(orders_data):
    parts = []
    total_ph = 0
    orders_list = list(orders_data)
    for o in sorted(orders_list, key=lambda x: str(x.get("period_s") or "").replace(" ", "")):
        period_raw = str(o.get("period_s") or "").replace(" ", "")
        actual = str(o.get("actual_period") or "").replace(" ", "")
        person_str = str(o.get("person") or "").strip()
        p_str = _format_period_display(period_raw, person_str, display_override=actual)
        parts.append(p_str)
        info = PERIOD_DISPLAY_INFO.get(period_raw)
        if info:
            try:
                h = int(float(info[0].replace("小時", "")))
                p = int(person_str) if person_str else 0
                total_ph += h * p
            except Exception:
                pass
    combined = "＋".join(parts)
    # v8.6：每筆訂單經 _format_period_display 已自帶一次「，共X人時」小計，
    # 只有在合併「多筆」訂單時才需要再附加一次整體加總，否則單筆訂單會重複顯示兩次。
    if total_ph and len(parts) > 1:
        combined += f"，共{total_ph}人時"
    return combined


def _configure_environment(env_name):
    base_url = BASE_URL_DEV if env_name == "dev" else BASE_URL_PROD
    order_prefix = ORDER_PREFIX_DEV if env_name == "dev" else ORDER_PREFIX_PROD
    orders.BASE_URL = base_url
    orders.ORDER_PREFIX = order_prefix
    orders.LOGIN_URL = f"{base_url}/login"
    orders.BOOKING_URL = f"{base_url}/booking/stored_value_routine"
    orders.PURCHASE_URL = f"{base_url}/purchase"
    orders.GET_MEMBER_URL = f"{base_url}/ajax/get_member"
    orders.CHECK_CONTAIN_URL = f"{base_url}/ajax/check_contain"
    orders.CALCULATE_HOUR_URL = f"{base_url}/ajax/calculate_hour"
    orders.GET_SECTION_URL = f"{base_url}/ajax/get_section"
    orders.MAIL_SUCCESS_URL = f"{base_url}/purchase/mail_success/{{order_no}}"
    return base_url


def _booking_url_for_payway(base_url, payway):
    return f"{base_url}{BOOKING_ENDPOINT_MAP.get(payway, '/booking/single')}"


def _get_booking_token_for_payway(session, base_url, payway):
    orders.BOOKING_URL = _booking_url_for_payway(base_url, payway)
    return get_csrf_token(session)


def _fetch_csrf_from_url(session, url):
    """從指定頁面抓 CSRF token，不影響 orders.BOOKING_URL 等全域設定。
    v8.5：用於儲值金訂單 check_contain 失敗時，向 /booking/single 借一個可靠的 token。"""
    resp = session.get(url, headers=HEADERS, allow_redirects=True)
    if resp.status_code != 200:
        return ""
    m = re.search(r'<meta name="csrf-token" content="([^"]+)"', resp.text)
    return m.group(1) if m else ""


def _build_booking_submit_data(base_data, token, payway, slot):
    data = {**base_data, "_token": token}
    if payway in ("信用卡", "ATM"):
        data["date_s"] = ""
        data["datePeriod"] = slot
    else:
        # 儲值金訂單：v2026.07.10 修正——實際查看 /booking/stored_value_routine
        # 頁面原始 HTML 後發現，這個頁面本身「有」payway 欄位，只是選項只有
        # 一個「儲值金」（<option value="4">儲值金</option>），而且是 required
        # 的必填 select。之前誤以為這個頁面不需要 payway 而整個拿掉，導致
        # 後台收到的表單缺少必填欄位，這才是付款方式空白、訂單卡在待付款、
        # 儲值金沒有真的被扣除的真正原因（不是先前懷疑的 token 來源問題）。
        # 這個頁面也沒有發票相關欄位（invoice_type/carrier_type_id 等），
        # 那幾個繼續拿掉是對的。
        data["date_list[]"] = [slot]
        data["payway"] = "4"
        for _k in ("invoice_type", "carrier_type_id", "carrier_info",
                   "company_title", "company_no", "donate_code"):
            data.pop(_k, None)
    return data


def get_last_purchase_fetch_debug():
    return dict(_LAST_PURCHASE_FETCH_DEBUG)


def _block_matches_phone_filter(block, phone_norm):
    if not phone_norm:
        return True
    joined = "\n".join(block.get("lines", []))
    compact = joined.replace("-", "").replace(" ", "")
    if phone_norm in compact:
        return True
    visible_phones = {
        normalize_phone(m.group(0))
        for m in re.finditer(r"(?:\+?886[-\s]?)?0?9[\d\-\s]{8,12}", joined)
    }
    visible_phones.discard("")
    if visible_phones:
        return phone_norm in visible_phones
    return True


def _fetch_purchase_blocks_for_phone(session, phone, name="", purchase_status=""):
    global _LAST_PURCHASE_FETCH_DEBUG
    params = dict(PURCHASE_FILTER_PARAMS_TEMPLATE)
    params["phone"] = normalize_phone(phone)
    if purchase_status:
        params["purchase_status"] = purchase_status
    if name and not params["phone"]:
        params["name"] = name
    resp = session.get(orders.PURCHASE_URL, params=params, headers=HEADERS, allow_redirects=True)
    raw_blocks = []
    if resp.status_code == 200:
        raw_blocks = extract_order_cards_from_purchase_html(resp.text)
    looks_like_login_page = "login" in resp.url.lower() or (len(raw_blocks) == 0 and "password" in resp.text.lower())
    effective_purchase_status = purchase_status
    fallback_info = {}
    if purchase_status and resp.status_code == 200 and not raw_blocks and not looks_like_login_page:
        fallback_params = dict(PURCHASE_FILTER_PARAMS_TEMPLATE)
        fallback_params["phone"] = normalize_phone(phone)
        if name and not fallback_params["phone"]:
            fallback_params["name"] = name
        fallback_resp = session.get(orders.PURCHASE_URL, params=fallback_params, headers=HEADERS, allow_redirects=True)
        fallback_blocks = []
        if fallback_resp.status_code == 200:
            fallback_blocks = extract_order_cards_from_purchase_html(fallback_resp.text)
        fallback_info = {
            "fallback_request_url": getattr(fallback_resp.request, "url", ""),
            "fallback_status_code": fallback_resp.status_code,
            "fallback_raw_block_count": len(fallback_blocks),
        }
        if fallback_blocks:
            resp = fallback_resp
            raw_blocks = fallback_blocks
            effective_purchase_status = ""
            looks_like_login_page = "login" in resp.url.lower()
    _LAST_PURCHASE_FETCH_DEBUG = {
        "request_url": getattr(resp.request, "url", ""), "final_url": resp.url,
        "status_code": resp.status_code, "purchase_status_filter": purchase_status,
        "effective_purchase_status_filter": effective_purchase_status,
        "raw_block_count": len(raw_blocks), "looks_like_login_page": looks_like_login_page,
        "snippet": resp.text[:300].replace("\n", " ").strip() if resp.status_code == 200 else "",
        **fallback_info,
    }
    if resp.status_code != 200:
        return []
    phone_norm = normalize_phone(phone)
    if not phone_norm:
        _LAST_PURCHASE_FETCH_DEBUG["filtered_block_count"] = len(raw_blocks)
        return raw_blocks
    filtered = [block for block in raw_blocks if _block_matches_phone_filter(block, phone_norm)]
    _LAST_PURCHASE_FETCH_DEBUG["filtered_block_count"] = len(filtered)
    return filtered


def list_order_numbers_for_phone(session, phone, name=""):
    blocks = _fetch_purchase_blocks_for_phone(session, phone, name=name)
    return {block["order_no"] for block in blocks if block.get("order_no")}


def _fetch_line_url_for_order_no(session, order_no):
    """
    v2026.07.07 新功能：抓某張訂單卡片裡的 LINE 聊天連結網址。
    extract_order_cards_from_purchase_html 把 HTML 轉成純文字，LINE 連結的
    網址（href）會被丟掉，只留下顯示文字「LINE」，所以這裡改成直接在原始
    HTML 裡找到對應訂單編號所在的那個 <tr>，再從裡面找 chat.line.biz 的連結。
    """
    params = dict(PURCHASE_FILTER_PARAMS_TEMPLATE)
    params["orderNo"] = str(order_no or "").strip()
    resp = session.get(orders.PURCHASE_URL, params=params, headers=HEADERS, allow_redirects=True)
    if resp.status_code != 200:
        return ""
    soup = BeautifulSoup(resp.text, "html.parser")
    target = str(order_no or "").strip()
    for tr in soup.find_all("tr"):
        if target in tr.get_text():
            line_a = tr.find("a", href=re.compile(r"chat\.line\.biz"))
            if line_a:
                return str(line_a.get("href", "")).strip()
    return ""


def _fetch_purchase_block_for_order_no(session, order_no):
    params = dict(PURCHASE_FILTER_PARAMS_TEMPLATE)
    params["orderNo"] = str(order_no or "").strip()
    resp = session.get(orders.PURCHASE_URL, params=params, headers=HEADERS, allow_redirects=True)
    if resp.status_code != 200:
        raise Exception(f"查詢訂單失敗：HTTP {resp.status_code}")
    target = str(order_no or "").strip()
    for block in extract_order_cards_from_purchase_html(resp.text):
        if block.get("order_no") == target:
            return block
    raise Exception(f"查無訂單：{target}")


def _check_order_no_duplicate(session, order_no):
    """
    v8.13：檢查這個訂單編號在後台訂單列表用「訂單編號」篩選查詢時，
    是否對應到一張以上的訂單卡片——這是後台偶發「產生重複訂單編號」問題的偵測方式。
    正常情況下同一個訂單編號應該只會對應到一張訂單卡片。
    回傳 (is_duplicate: bool, count: int)；查詢失敗時回傳 (False, 1)，不擋建單流程。
    """
    try:
        params = dict(PURCHASE_FILTER_PARAMS_TEMPLATE)
        params["orderNo"] = str(order_no or "").strip()
        resp = session.get(orders.PURCHASE_URL, params=params, headers=HEADERS, allow_redirects=True)
        if resp.status_code != 200:
            return False, 1
        target = str(order_no or "").strip()
        matched_blocks = [b for b in extract_order_cards_from_purchase_html(resp.text) if b.get("order_no") == target]
        count = len(matched_blocks)
        return count > 1, max(count, 1)
    except Exception:
        return False, 1


def _parse_service_date_time_loose(joined_text):
    date_match = re.search(r"(\d{4}-\d{2}-\d{2})\s*[（(][一二三四五六日][）)]", joined_text)
    if not date_match:
        for m in re.finditer(r"(\d{4}-\d{2}-\d{2})", joined_text):
            tail = joined_text[m.end():m.end() + 12]
            if not re.match(r"\s*\d{1,2}:\d{2}:\d{2}", tail):
                date_match = m
                break
    if not date_match:
        return "", ""
    service_date = date_match.group(1)
    tail = joined_text[date_match.end():date_match.end() + 600]
    time_match = re.search(r"(\d{1,2}:\d{2})\s*[-~～]\s*(\d{1,2}:\d{2})(?!:\d)", tail)
    if not time_match:
        time_match = re.search(r"(\d{1,2}:\d{2})\s*[-~～]\s*(\d{1,2}:\d{2})(?!:\d)", joined_text)
    if not time_match:
        return service_date, ""
    start, end = time_match.groups()
    return service_date, f"{start} - {end}"


def _extract_money_line(joined_text, labels):
    text = str(joined_text or "").replace(",", "")
    for label in labels:
        m = re.search(rf"{re.escape(label)}\s*[：:]?\s*\$?\s*(-?\d+(?:\.\d+)?)", text)
        if m:
            value = m.group(1)
            try:
                number = float(value)
                return str(int(number)) if number.is_integer() else str(number)
            except Exception:
                return value
    return ""


def _extract_total_amount_line(joined_text):
    return _extract_money_line(joined_text, ["訂單總金額", "總金額", "合計", "總計"])


def _extract_fare_line(joined_text):
    return _extract_money_line(joined_text, ["車馬費"])


def _extract_person_hour_line(joined_text):
    text = str(joined_text or "")
    compact_match = re.search(r"(\d+)\s*人\s*(\d+(?:\.\d+)?)\s*(?:小時|時)", text)
    if compact_match:
        return compact_match.group(1), compact_match.group(2)
    person = ""
    hour = ""
    person_match = re.search(r"(?:服務人數|人數|專員人數)\s*[：:]?\s*(\d+)", text)
    hour_match = re.search(r"(?:服務時數|時數)\s*[：:]?\s*(\d+(?:\.\d+)?)", text)
    if person_match:
        person = person_match.group(1)
    if hour_match:
        hour = hour_match.group(1)
    return person, hour


def _count_staff_from_lines(lines):
    staff_str = _extract_staff_line(lines)
    if not staff_str:
        return ""
    parts = [p.strip() for p in re.split(r"\s*X\s*", staff_str) if p.strip()]
    count = sum(1 for p in parts if "檸檬人" not in p)
    return str(count) if count > 0 else ""


def _fix_address_district_order(address, fallback_district=""):
    """
    v8.6：確保地址格式為「市/縣 → 區/鄉/鎮 → 其餘地址」。
    - 情況一：區/鄉/鎮 出現在 市/縣 之前（例如「大安區台北市羅斯福路...」，順序錯誤），
      自動對調為「台北市大安區羅斯福路...」。
    - 情況二：市/縣 後方已經有區/鄉/鎮，順序正確，不需處理。
    - 情況三：地址完全沒有區/鄉/鎮，若有提供 fallback_district（例如查詢取得），
      補在「市/縣」之後。
    任何情況解析失敗都直接回傳原始地址，不擋住建單流程。
    """
    address = str(address or "").strip()
    if not address:
        return address
    try:
        city_m = re.search(r"(?P<city>[^市縣區鄉鎮]{1,6}[市縣])", address)
        if not city_m:
            return address
        city = city_m.group("city")
        before_city = address[:city_m.start()]
        after_city = address[city_m.end():]
        district_m = re.match(r"^(?P<district>[^區鄉鎮市]{1,6}[區鄉鎮])", before_city)
        if district_m:
            district = district_m.group("district")
            rest_before = before_city[district_m.end():]
            if re.match(r"^[^區鄉鎮]{0,6}[區鄉鎮]", after_city):
                return f"{rest_before}{city}{after_city}".strip()
            return f"{rest_before}{city}{district}{after_city}".strip()
        if re.match(r"^[^區鄉鎮]{0,6}[區鄉鎮]", after_city):
            return address
        if fallback_district:
            return f"{before_city}{city}{fallback_district}{after_city}".strip()
        return address
    except Exception:
        return address


def _lookup_district_via_geocode(address):
    """
    v8.6：查詢地址對應的行政區（區/鄉/鎮），用於補齊新客地址缺少區域的情況。
    v8.18：拿掉原本的 Nominatim（OpenStreetMap）免費備援——實測發現它在台灣的
    行政區判斷常常不準（例如把「羅斯福路二段」誤判成大安區，實際上是中正區），
    猜錯比不猜更糟：猜錯的區域會被我們自己送出去，之後後台存的地址剛好跟我們
    猜的一樣，address_mismatch_warning 反而抓不到這個錯誤。
    現在只用準確度高很多的 Google 地理編碼 API；沒有設定金鑰或查詢失敗時，
    一律回傳空字串、不猜測，讓地址維持原樣，交給建單後的地址比對警示
    （address_mismatch_warning）去抓後續後台端可能出現的落差。
    """
    address = str(address or "").strip()
    if not address:
        return ""
    _google_key = None
    for _attr in ("GOOGLE_API_KEY", "GOOGLE_MAPS_API_KEY", "GOOGLE_GEOCODE_API_KEY", "MAPS_API_KEY"):
        _google_key = getattr(orders, _attr, None)
        if _google_key:
            break
    if not _google_key:
        return ""
    try:
        resp = requests.get(
            "https://maps.googleapis.com/maps/api/geocode/json",
            params={"address": address, "key": _google_key, "region": "tw", "language": "zh-TW"},
            timeout=5,
        )
        if resp.status_code == 200:
            data = resp.json()
            for result in data.get("results", []):
                for comp in result.get("address_components", []):
                    types = comp.get("types", [])
                    if "administrative_area_level_3" in types or "administrative_area_level_2" in types:
                        name = comp.get("long_name", "")
                        if re.search(r"(區|鄉|鎮)$", name):
                            return name
    except Exception:
        pass
    return ""


def _extract_district_from_address(address):
    address = str(address or "").strip()
    city_m = re.search(r"[^市縣區鄉鎮]{1,6}[市縣]", address)
    if not city_m:
        return ""
    after_city = address[city_m.end():]
    district_m = re.match(r"(?P<district>[^區鄉鎮市]{1,6}[區鄉鎮])", after_city)
    return district_m.group("district") if district_m else ""


def _normalize_city_for_country_id(city):
    return str(city or "").strip().replace("臺", "台")


def _split_booking_address(address):
    address = _fix_address_district_order(str(address or "").strip(), fallback_district="")
    result = {"city": "", "district": "", "country_id": "", "detail": address, "full": address}
    city_m = re.search(r"(?P<city>[^市縣區鄉鎮]{1,6}[市縣])", address)
    if not city_m:
        return result
    city = city_m.group("city")
    after_city = address[city_m.end():]
    city_for_country = _normalize_city_for_country_id(city)
    district_m = re.match(r"(?P<district>[^區鄉鎮市]{1,6}[區鄉鎮])", after_city)
    if not district_m:
        return {
            "city": city_for_country,
            "district": "",
            "country_id": "",
            "detail": after_city.strip() or address,
            "full": f"{city_for_country}{after_city}".strip(),
        }
    district = district_m.group("district")
    detail = after_city[district_m.end():].strip()
    country_id = COUNTRY_ID_BY_CITY_AREA.get((city, district), "") or COUNTRY_ID_BY_CITY_AREA.get((city_for_country, district), "")
    return {
        "city": city_for_country,
        "district": district,
        "country_id": country_id,
        "detail": detail or address,
        "full": f"{city_for_country}{district}{detail}".strip(),
    }


def _assert_address_region_resolved(address_parts, original_address, context="地址"):
    if address_parts.get("city") and address_parts.get("district") and not address_parts.get("country_id"):
        raise Exception(
            f"{context}無法對應後台縣市/區域下拉選單：{original_address}。"
            "已停止成單，不會自動改成大安區；請確認此區域是否在服務範圍或補上區域對照。"
        )


def _area_district_from_info(area_info):
    text = str(
        (area_info or {}).get("area_name")
        or (area_info or {}).get("name")
        or (area_info or {}).get("area")
        or (area_info or {}).get("district")
        or ""
    ).strip()
    m = re.search(r"([^區鄉鎮市]{1,6}[區鄉鎮])", text)
    return m.group(1) if m else ""


def _complete_missing_district(address_parts, area_info, original_address, context="地址"):
    if address_parts.get("district"):
        return address_parts
    city = address_parts.get("city", "")
    district = _area_district_from_info(area_info)
    if not city or not district:
        raise Exception(f"{context}「{original_address}」無法判斷區域，已停止成單，請確認地址是否正確。")
    country_id = COUNTRY_ID_BY_CITY_AREA.get((city, district), "")
    if not country_id:
        raise Exception(f"{context}「{original_address}」找到區域「{district}」，但無法對應後台下拉選單，已停止成單。")
    detail = address_parts.get("detail", "")
    return {"city": city, "district": district, "country_id": country_id, "detail": detail, "full": f"{city}{district}{detail}".strip()}


def _validate_area_not_known_bad(address, area_info, context=""):
    area_id = str((area_info or {}).get("area_id") or (area_info or {}).get("areaId") or "").strip()
    if area_id != "25":
        return
    district = _extract_district_from_address(address)
    if district and district != "大安區":
        prefix = f"{context}：" if context else ""
        raise Exception(
            f"{prefix}查詢地址區域疑似錯誤：地址寫的是「{district}」，"
            "但後台回傳 area_id=25（大安區）。已停止成單，避免地址被加成台北市大安區。"
        )


def _validate_address_before_submit(address, area_id, context=""):
    if re.search(r"[^市縣區鄉鎮]{1,6}[市縣].+[^市縣區鄉鎮]{1,6}[市縣]", str(address or "")):
        prefix = f"{context}：" if context else ""
        raise Exception(
            f"{prefix}送出前地址格式異常：地址內出現兩個縣市「{address}」。"
            "已停止成單，避免沿用後台錯誤加上的市/區前綴。"
        )
    if str(area_id or "").strip() == "25":
        _validate_area_not_known_bad(address, {"area_id": "25"}, context=context)
    fixed = _fix_address_district_order(address, fallback_district="")
    if normalize_addr_for_match(fixed) != normalize_addr_for_match(address):
        prefix = f"{context}：" if context else ""
        raise Exception(
            f"{prefix}送出前地址格式異常：目前地址是「{address}」，"
            f"整理後會變成「{fixed}」。已停止成單，請確認不要沿用後台錯誤地址。"
        )


def _extract_address_line(lines):
    for line in lines:
        text = str(line or "").strip()
        if not text or "@" in text or text.upper() == "LINE":
            continue
        if re.search(r"(台|臺|新北|桃園|台中|臺中|台南|臺南|高雄|基隆|新竹|嘉義|苗栗|彰化|南投|雲林|屏東|宜蘭|花蓮|台東|臺東|澎湖|金門|連江).*(市|縣).*(區|鄉|鎮|市)", text):
            return _fix_address_district_order(text)
    return ""


def _date_not_after_today(date_text):
    try:
        return datetime.strptime(str(date_text), "%Y-%m-%d").date() <= date.today()
    except Exception:
        return False


def _extract_service_type_label(lines):
    """
    v2026.07.06：從訂單卡片的文字行裡抓實際服務類型（居家清潔／辦公室清潔／
    裝修細清／大掃除／搬出清潔／搬入清潔），用於「用訂單編號查詢/重新產生
    LINE通知」這個路徑——之前這裡完全沒有抓服務類型，導致 build_line_message
    永遠拿不到 clean_type_id，訊息一律顯示「居家清潔」，不管實際訂的是什麼
    服務。訂單列表卡片上服務類型是獨立一行文字（例如圖片裡的橘字「辦公室
    清潔」），直接逐行比對已知類別名稱即可。
    """
    known_labels = ["居家清潔", "辦公室清潔", "裝修細清", "大掃除", "搬出清潔", "搬入清潔"]
    for line in lines:
        text = str(line).strip()
        if text in known_labels:
            return text
    return ""


def _extract_payway_line(joined_text):
    text = str(joined_text or "")
    for line in text.splitlines():
        if "付款方式" not in line:
            continue
        m_line = re.search(r"付款方式[：:]\s*(.+)", line)
        if m_line:
            value = normalize_booking_payway(m_line.group(1).strip())
            if value in ("信用卡", "ATM", "儲值金"):
                return value
    m = re.search(r"付款方式[：:]\s*([^\s\n]+)", text)
    if m:
        value = normalize_booking_payway(m.group(1).strip())
        if value in ("信用卡", "ATM", "儲值金"):
            return value
    if "藍新ATM" in text or "ATM" in text:
        return "ATM"
    if "儲值金" in text:
        return "儲值金"
    if _extract_total_amount_line(text) == "0" and not _extract_invoice_line(text):
        return "儲值金"
    return ""


def _service_amount_from_block(joined_text, fare):
    total = _extract_total_amount_line(joined_text)
    if not total:
        return ""
    try:
        total_num = int(round(float(str(total).replace(",", ""))))
        fare_num = int(round(float(str(fare or "0").replace(",", ""))))
        amount = total_num - fare_num if fare_num and total_num > fare_num else total_num
        return str(amount)
    except Exception:
        return total


def _is_paid_order_text(joined_text, trusted_paid_filter=False):
    if "已取消" in joined_text or "已退款" in joined_text:
        return False
    if trusted_paid_filter:
        return True
    compact = re.sub(r"\s+", "", str(joined_text or ""))
    if "待付款" in compact or "未付款" in compact:
        return False
    if "已付款" in compact:
        return True
    if "儲值金" in compact and (
        _extract_total_amount_line(joined_text) == "0"
        or "扣儲值金" in compact or "儲值金扣款" in compact
    ):
        return True
    if re.search(r"付款.{0,12}(完成|成功)", compact):
        return True
    return False


def _extract_invoice_line(joined_text):
    m = re.search(r"((?:二聯式|三聯式|捐贈發票)[：:][^\n]*)", joined_text)
    return m.group(1).strip() if m else ""


CLEAN_TYPE_LABELS = ["居家清潔", "辦公室清潔", "裝修細清", "大掃除"]


def _extract_clean_type_line(joined_text):
    for label in CLEAN_TYPE_LABELS:
        if label in joined_text:
            return label
    return ""


def _extract_label_value(lines, label, stop_labels):
    try:
        idx = lines.index(label)
    except ValueError:
        return ""
    value_lines = []
    for line in lines[idx + 1:]:
        if line in stop_labels or line in CLEAN_TYPE_LABELS:
            break
        value_lines.append(line)
    return " ".join(value_lines).strip()


def _period_to_shift_code(period_s):
    compact = str(period_s or "").replace(" ", "")
    return PERIOD_TO_SHIFT_CODE.get(compact, "")


def _shift_value_to_code(value):
    value = str(value or "").strip()
    return VALUE_TO_SHIFT_CODE.get(value, value)


def _shift_value_to_code_by_name(name, value):
    name = str(name or "")
    value = str(value or "").strip()
    group = name.rsplit("_", 1)[-1] if "_" in name else ""
    if group == "1" and value in {"2", "3", "4"}:
        return {"2": "上2", "3": "上3", "4": "上4"}[value]
    if group == "2" and value in {"2", "3", "4"}:
        return {"2": "下2", "3": "下3", "4": "下4"}[value]
    if group == "3" and value == "2":
        return "晚2"
    return _shift_value_to_code(value)


def _shift_code_to_value(code):
    code = str(code or "").strip()
    for value, mapped in VALUE_TO_SHIFT_CODE.items():
        if mapped == code:
            return value
    return code


def _shift_code_to_group(code):
    code = str(code or "").strip()
    if code in {"全6", "全8"}:
        return "all"
    if code in {"上2", "上3", "上4"}:
        return "1"
    if code in {"下2", "下3", "下4"}:
        return "2"
    if code in {"晚2"}:
        return "3"
    return "1"


def _shift_codes_conflict(existing_code, target_code):
    existing_code = _shift_value_to_code(existing_code)
    target_code = _shift_value_to_code(target_code)
    if not existing_code or not target_code:
        return False
    if existing_code == target_code:
        return False
    if existing_code in {"全6", "全8"} or target_code in {"全6", "全8"}:
        return True
    return target_code in SHIFT_CONFLICT_TABLE.get(existing_code, set())


# =========================================================
# 會員查詢 & 訂單建立
# =========================================================

def quick_lookup_member(env_name, backend_email, backend_password, phone, clean_type_id="1"):
    base_url = _configure_environment(env_name)
    session = requests.Session()
    if not login(session, backend_email, backend_password):
        raise Exception("後台登入失敗，請確認帳號密碼")
    token = get_csrf_token(session)
    phone = normalize_phone(phone)
    member_payload = get_member(session, phone, token, clean_type_id)
    return {"session": session, "token": token, "phone": phone, "member_payload": member_payload, "base_url": base_url, "env_name": env_name}


def get_customer_paid_orders(session, phone, known_addresses=None, name=""):
    known_addresses = known_addresses or []
    blocks = _fetch_purchase_blocks_for_phone(session, phone, name=name, purchase_status=PURCHASE_STATUS_PAID)
    trusted_paid_filter = (
        get_last_purchase_fetch_debug().get("effective_purchase_status_filter") == PURCHASE_STATUS_PAID
    )
    results = []
    for block in blocks:
        lines = block.get("lines", [])
        joined = "\n".join(lines)
        if not _is_paid_order_text(joined, trusted_paid_filter=trusted_paid_filter):
            continue
        service_date, service_time = _parse_service_date_time_loose(joined)
        if not service_date:
            continue
        joined_norm = normalize_addr_for_match(joined)
        matched_addr = ""
        for addr in known_addresses:
            if addr and normalize_addr_for_match(addr) in joined_norm:
                matched_addr = addr
                break
        person, hour = _extract_person_hour_line(joined)
        payway = _extract_payway_line(joined)
        invoice_text = "" if payway == "儲值金" else _extract_invoice_line(joined)
        results.append({
            "order_no": block["order_no"], "date": service_date, "time": service_time,
            "address": matched_addr, "clean_type": _extract_clean_type_line(joined),
            "staff": _extract_staff_line(lines), "payway": payway, "invoice_text": invoice_text,
            "service_notice": _extract_label_value(lines, "客服備註", ["財務備註", "客人備註"]),
            "person": person, "hour": hour,
            "total_amount": _extract_total_amount_line(joined),
            "fare": _extract_fare_line(joined),
        })
    results.sort(key=lambda x: (x["date"], x.get("time", "")), reverse=True)
    return results


def _match_person_hour(member_payload, order_no, address):
    if not isinstance(member_payload, dict):
        return "", ""
    last_purchase = member_payload.get("lastPurchase", {}) or {}
    member = member_payload.get("member", {}) or {}
    addr_list = member.get("memberAddressList", []) or []
    candidates = []
    if last_purchase:
        candidates.append(last_purchase)
    target_norm = normalize_addr_for_match(address) if address else ""
    for item in addr_list:
        if target_norm and normalize_addr_for_match(item.get("address", "")) == target_norm:
            item_purchase = item.get("purchase", {})
            if isinstance(item_purchase, dict) and item_purchase:
                candidates.append(item_purchase)
    for c in candidates:
        if str(c.get("order_no", "")).strip() == str(order_no).strip():
            return c.get("person", ""), c.get("hour", "")
    return "", ""


def _order_person_hour(member_payload, order):
    person, hour = _match_person_hour(member_payload, order.get("order_no", ""), order.get("address", ""))
    return person or order.get("person", ""), hour or order.get("hour", "")


def get_last_paid_per_address(session, phone, member_payload, known_addresses, within_days=365):
    cutoff = date.today() - timedelta(days=within_days)
    name = (member_payload.get("member", {}) or {}).get("name", "") if isinstance(member_payload, dict) else ""
    paid_orders = get_customer_paid_orders(session, phone, known_addresses, name=name)
    by_address = {}
    for o in paid_orders:
        addr = o.get("address", "")
        if not addr or addr in by_address:
            continue
        try:
            d = datetime.strptime(o["date"], "%Y-%m-%d").date()
        except Exception:
            continue
        if d > date.today() or d < cutoff:
            continue
        by_address[addr] = o
    result = {}
    for addr in known_addresses:
        order = by_address.get(addr)
        if not order:
            result[addr] = None
            continue
        person, hour = _order_person_hour(member_payload, order)
        result[addr] = {
            "order_no": order["order_no"], "date": order["date"], "time": order["time"],
            "clean_type": order["clean_type"], "staff": order["staff"], "payway": order["payway"],
            "invoice_text": order["invoice_text"], "service_notice": order["service_notice"],
            "person": person, "hour": hour, "fare": order.get("fare", ""),
        }
    return result


def get_last_paid_summary(session, phone, member_payload, known_addresses):
    name = (member_payload.get("member", {}) or {}).get("name", "") if isinstance(member_payload, dict) else ""
    paid_orders = get_customer_paid_orders(session, phone, known_addresses, name=name)
    paid_orders = [o for o in paid_orders if _date_not_after_today(o.get("date", ""))]
    if not paid_orders:
        return None
    latest = paid_orders[0]
    same_date_orders = []
    for order in paid_orders:
        if order["date"] != latest["date"]:
            continue
        person, hour = _order_person_hour(member_payload, order)
        enriched = dict(order)
        enriched["person"] = person
        enriched["hour"] = hour
        same_date_orders.append(enriched)
    person, hour = _order_person_hour(member_payload, latest)
    return {
        "order_no": latest["order_no"], "date": latest["date"], "time": latest["time"],
        "address": latest["address"], "clean_type": latest["clean_type"], "staff": latest["staff"],
        "payway": latest["payway"], "invoice_text": latest["invoice_text"],
        "service_notice": latest["service_notice"], "person": person, "hour": hour,
        "fare": latest.get("fare", ""), "same_date_orders": same_date_orders,
    }


def get_unserved_paid_orders(session, phone, member_payload, known_addresses, today_value=None):
    today_value = today_value or date.today()
    name = (member_payload.get("member", {}) or {}).get("name", "") if isinstance(member_payload, dict) else ""
    blocks = _fetch_purchase_blocks_for_phone(session, phone, name=name, purchase_status=PURCHASE_STATUS_PAID)
    trusted_paid_filter = (
        get_last_purchase_fetch_debug().get("effective_purchase_status_filter") == PURCHASE_STATUS_PAID
    )
    upcoming = []
    for block in blocks:
        lines = block.get("lines", [])
        joined = "\n".join(lines)
        if not _is_paid_order_text(joined, trusted_paid_filter=trusted_paid_filter):
            continue
        service_date, service_time = _parse_service_date_time_loose(joined)
        if not service_date:
            continue
        try:
            d = datetime.strptime(service_date, "%Y-%m-%d").date()
        except Exception:
            continue
        if d < today_value:
            continue
        joined_norm = normalize_addr_for_match(joined)
        matched_addr = ""
        for addr in known_addresses or []:
            if addr and normalize_addr_for_match(addr) in joined_norm:
                matched_addr = addr
                break
        payway = _extract_payway_line(joined)
        parsed_person, parsed_hour = _extract_person_hour_line(joined)
        person, hour = _match_person_hour(member_payload, block["order_no"], matched_addr)
        person = person or parsed_person
        hour = hour or parsed_hour
        upcoming.append({
            "order_no": block["order_no"], "date": service_date, "time": service_time,
            "address": matched_addr, "clean_type": _extract_clean_type_line(joined),
            "staff": _extract_staff_line(lines), "payway": payway,
            "invoice_text": "" if payway == "儲值金" else _extract_invoice_line(joined),
            "person": person, "hour": hour, "fare": _extract_fare_line(joined),
        })
    upcoming.sort(key=lambda x: x["date"])
    return upcoming


def quick_check_available_slots(env_name, payway, lookup_result, address, clean_type_id, date_s, hour, person="2", periods=None, period_hours=None):
    base_url = _configure_environment(env_name)
    session = lookup_result["session"]
    token = _get_booking_token_for_payway(session, base_url, payway)
    member_payload = lookup_result["member_payload"]
    if not member_payload:
        raise Exception("此電話查無會員資料，請先查詢會員")
    member = member_payload.get("member", {})
    best_addr = pick_best_address_info(member_payload, address)
    if not best_addr:
        # v2026.07.06 修正：查可預約時段時，舊客地址不在既有清單裡不再直接擋掉，
        # 當作新地址處理（跟 quick_create_order 的新地址邏輯一致）。
        best_addr = {}
    selected_address = str(best_addr.get("address") or address).strip()
    address_parts = _split_booking_address(selected_address)
    _assert_address_region_resolved(address_parts, selected_address, context="查詢可預約地址")
    selected_address_for_lookup = address_parts["full"]
    selected_address_for_submit = address_parts["detail"]
    geo_lat, geo_lng = geocode_address(selected_address_for_lookup)
    if geo_lat and geo_lng:
        best_addr["lat"] = geo_lat
        best_addr["lng"] = geo_lng
    addr_check = check_contain(session, member.get("member_id", ""), selected_address_for_lookup, best_addr.get("lat", ""), best_addr.get("lng", ""), token, clean_type_id)
    if not addr_check and lookup_result.get("token") and lookup_result.get("token") != token:
        addr_check = check_contain(session, member.get("member_id", ""), selected_address_for_lookup, best_addr.get("lat", ""), best_addr.get("lng", ""), lookup_result["token"], clean_type_id)
    if not addr_check and payway == "儲值金":
        # v8.5：stored_value_routine 頁面的 token 有時無法用於 check_contain，
        # 改向 /booking/single 借一個可靠的 token 重試
        _fallback_token = _fetch_csrf_from_url(session, f"{base_url}/booking/single")
        if _fallback_token and _fallback_token != token and _fallback_token != lookup_result.get("token"):
            addr_check = check_contain(session, member.get("member_id", ""), selected_address_for_lookup, best_addr.get("lat", ""), best_addr.get("lng", ""), _fallback_token, clean_type_id)
            if addr_check:
                token = _fallback_token
    if not addr_check:
        raise Exception(f"查詢地址/地區失敗：{selected_address_for_lookup}")
    area_info = addr_check.get("area") if isinstance(addr_check.get("area"), dict) else {}
    if area_info:
        address_parts = _complete_missing_district(address_parts, area_info, selected_address_for_lookup, context="查詢可預約地址")
        selected_address_for_lookup = address_parts["full"]
        selected_address_for_submit = address_parts["detail"]
        best_addr["area_id"] = area_info.get("area_id", best_addr.get("area_id"))
        best_addr["company_id"] = area_info.get("company_id", best_addr.get("company_id"))
        best_addr["country_id"] = address_parts.get("country_id") or area_info.get("country_id", best_addr.get("country_id"))
    old_purchase = best_addr.get("purchase", {}) if isinstance(best_addr.get("purchase"), dict) else {}

    def pick(key, default=""):
        value = old_purchase.get(key)
        return value if value not in (None, "") else default

    base_data = {
        "clean_type_id": clean_type_id, "phone": lookup_result.get("phone", ""),
        "name": str(member.get("name") or "").strip(), "email": str(member.get("email") or "").strip(),
        "tel": str(member.get("tel") or lookup_result.get("phone", "")),
        "line": str(member.get("line") or ""), "fbName": str(member.get("fb_name") or ""),
        "fb": str(member.get("fb") or ""), "memoProcess": str(member.get("memo_process") or ""),
        "memoFinance": str(member.get("memo_finance") or ""),
        "addressId": str(best_addr.get("addressId") or ""),
        "country_id": str(address_parts.get("country_id") or best_addr.get("country_id") or pick("country_id", "")),
        "address": selected_address_for_submit, "ping": str(pick("ping", "4")),
        "room": str(pick("room", "0")), "bathroom": str(pick("bathroom", "0")),
        "balcony": str(pick("balcony", "0")), "livingroom": str(pick("livingroom", "0")),
        "kitchen": str(pick("kitchen", "0")), "window": str(pick("window", "")),
        "shutter": str(pick("shutter", "")), "clothes": str(pick("clothes", "0")),
        "dyson": str(pick("dyson", "0")), "refrigerator": str(pick("refrigerator", "0")),
        "disinfection": str(pick("disinfection", "0")), "go_abord": str(pick("go_abord", "0")),
        "home_move": str(pick("home_move", "0")), "storage": str(pick("storage", "0")),
        "cabinet": str(pick("cabinet", "0")), "quintuple": str(pick("quintuple", "0")),
        "hour": str(int(float(hour))), "price": "", "price_vvip": "",
        "person": str(person), "date_s": date_s, "period_s": "", "period": "",
        "cycle": "1", "fare": "", "memo": "",
        "notice": str(best_addr.get("notice") or old_purchase.get("notice") or ""),
        "discount_code": "", "payway": PAYWAY_MAP.get(payway, "2"),
        "invoice_type": "2", "carrier_type_id": "1",
        "carrier_info": str(member.get("email") or ""),
        "company_title": "", "company_no": "", "donate_code": "8585", "is_backend": "477",
        "member_id": str(member.get("member_id") or ""),
        "company_id": str(best_addr.get("company_id") or best_addr.get("companyId") or pick("company_id", "")),
        "area_id": str(best_addr.get("area_id") or best_addr.get("areaId") or pick("area_id", "")),
        "lat": str(best_addr.get("lat") or pick("lat", "")),
        "lng": str(best_addr.get("lng") or pick("lng", "")),
    }
    rows = []
    if not str(base_data.get("country_id") or "").strip():
        raise Exception(f"地址「{selected_address_for_lookup}」無法判斷縣市/區域下拉選單，已停止查詢，不會自動改成大安區。")
    for period in periods or []:
        slot = f"{date_s}_{period}"
        data = base_data.copy()
        data["period_s"] = period
        data["hour"] = str(int(float((period_hours or {}).get(period, hour))))
        calc_result = calculate_hour(session, data, token)
        if not calc_result:
            rows.append({"date": date_s, "period": period, "available": False, "staff": "", "error": "計算時數失敗"})
            continue
        calc_fields = extract_calc_fields(calc_result, fallback_hours=data["hour"], fallback_fare="0")
        data["price"] = str(calc_fields.get("price") or "0")
        data["price_vvip"] = str(calc_fields.get("price_vvip") or "0")
        data["fare"] = str(calc_fields.get("fare") or "0")
        raw_section = get_section_raw(session, data, token, slot)
        available = slot_exists_in_section_response(raw_section, slot)
        cleaners = extract_cleaners_from_section_response(raw_section, slot) if available else []
        rows.append({"date": date_s, "period": period, "available": available, "staff": format_staff_from_cleaners(cleaners, people=person) if available else ""})
    return rows


def quick_create_order(
    env_name, payway, region, lookup_result, address, clean_type_id,
    date_s, period_s, hour, person="2", fallback_fare="0", discount_code="",
    payment_type="", carrier_info="", company_no="", company_title="",
    invoice_type_override="", carrier_type_id_override="",
    extra_fields=None, allow_auto_lemon_shift=False,
):
    payway = normalize_booking_payway(payway)
    base_url = _configure_environment(env_name)
    session = lookup_result["session"]
    token = _get_booking_token_for_payway(session, base_url, payway)
    member_payload = lookup_result["member_payload"]
    phone = lookup_result["phone"]
    member_name = (member_payload.get("member", {}) or {}).get("name", "") if member_payload else ""
    if not member_payload:
        raise Exception("此電話查無會員資料，請先走新客人資訊收集流程建立會員後再建單")
    member = member_payload.get("member", {})
    best_addr = pick_best_address_info(member_payload, address)
    is_new_address = not bool(best_addr)
    if not best_addr:
        # v2026.07.06 修正：舊客地址不在既有清單裡不再直接擋掉查詢，
        # 當作新地址處理（跟 quick_create_order 的新地址邏輯一致）。
        best_addr = {}
    selected_address = str(best_addr.get("address") or address).strip()
    address_parts = _split_booking_address(selected_address)
    _assert_address_region_resolved(address_parts, selected_address, context="舊客地址")
    address_for_lookup = address_parts["full"]
    address_for_submit = address_parts["detail"]
    geo_lat, geo_lng = geocode_address(address_for_lookup)
    if is_new_address and (not geo_lat or not geo_lng):
        raise Exception(
            f"新地址「{address_for_lookup}」無法取得經緯度，已停止成單，"
            "避免後台用空座標誤判成大安區。請確認地址是否完整到路段/門牌，或改用後台手動建單。"
        )
    if geo_lat and geo_lng:
        best_addr["lat"] = geo_lat
        best_addr["lng"] = geo_lng
    # 2026-07-08：避免新單成單時被 check_contain 誤判成大安區。
    # 若會員既有地址已經有 area_id/company_id，就直接用既有資料，不再重新查詢區域覆蓋。
    # 只有在既有地址完全沒有 area_id 時，才呼叫後台 check_contain；查不到就擋下，不套預設大安區。
    addr_check = {}
    if not str(best_addr.get("area_id") or best_addr.get("areaId") or "").strip():
        addr_check = check_contain(session, member.get("member_id", ""), address_for_lookup, best_addr.get("lat", ""), best_addr.get("lng", ""), token, clean_type_id)
        if not addr_check and lookup_result.get("token") and lookup_result.get("token") != token:
            addr_check = check_contain(session, member.get("member_id", ""), address_for_lookup, best_addr.get("lat", ""), best_addr.get("lng", ""), lookup_result["token"], clean_type_id)
        if not addr_check and payway == "儲值金":
            _fallback_token = _fetch_csrf_from_url(session, f"{base_url}/booking/single")
            if _fallback_token and _fallback_token != token and _fallback_token != lookup_result.get("token"):
                addr_check = check_contain(session, member.get("member_id", ""), address_for_lookup, best_addr.get("lat", ""), best_addr.get("lng", ""), _fallback_token, clean_type_id)
                if addr_check:
                    token = _fallback_token
        area_info = addr_check.get("area") if isinstance(addr_check.get("area"), dict) else {}
        if not area_info.get("area_id"):
            route = BOOKING_ENDPOINT_MAP.get(payway, "/booking/single")
            raise Exception(f"地址缺少已存區域，且查詢地址/地區失敗（{payway}：{route}）：{address_for_lookup}，請先到會員地址或後台手動確認區域")
        address_parts = _complete_missing_district(address_parts, area_info, address_for_lookup, context="舊客新地址")
        address_for_lookup = address_parts["full"]
        address_for_submit = address_parts["detail"]
        _validate_area_not_known_bad(address_for_lookup, area_info, context="舊客新地址")
        best_addr["area_id"] = area_info.get("area_id")
        best_addr["company_id"] = area_info.get("company_id", best_addr.get("company_id"))
        best_addr["country_id"] = address_parts.get("country_id") or area_info.get("country_id", best_addr.get("country_id"))
        if not str(best_addr.get("country_id") or "").strip():
            raise Exception(f"地址「{address_for_lookup}」無法判斷縣市/區域下拉選單，已停止成單，不會自動改成大安區。")
    else:
        if best_addr.get("areaId") and not best_addr.get("area_id"):
            best_addr["area_id"] = best_addr.get("areaId")
        if best_addr.get("companyId") and not best_addr.get("company_id"):
            best_addr["company_id"] = best_addr.get("companyId")
        if best_addr.get("countryId") and not best_addr.get("country_id"):
            best_addr["country_id"] = best_addr.get("countryId")

    area_info = addr_check.get("area") if isinstance(addr_check.get("area"), dict) else {}
    purchase_info = addr_check.get("purchase") if isinstance(addr_check.get("purchase"), dict) else {}
    fare_from_check = first_nonzero(
        purchase_info.get("fare") if purchase_info else "",
        purchase_info.get("car_fare") if purchase_info else "",
        purchase_info.get("traffic_fee") if purchase_info else "",
        area_info.get("fare") if area_info else "",
        area_info.get("car_fare") if area_info else "",
        area_info.get("traffic_fee") if area_info else "",
        find_nested_value(addr_check, ["fare", "car_fare", "traffic_fee", "trafficFee", "車馬費"]),
        best_addr.get("fare", ""),
        default=str(fallback_fare or "0"),
    )
    best_addr["fare"] = fare_from_check
    invoice_type = str(first_nonzero(invoice_type_override, purchase_info.get("invoiceType") if purchase_info else "", find_nested_value(addr_check, ["invoiceType", "invoice_type"]), default="2"))
    carrier_type_id = str(first_nonzero(carrier_type_id_override, purchase_info.get("carrierTypeId") if purchase_info else "", default="1"))
    carrier_info = str(first_nonzero(carrier_info, purchase_info.get("carrierInfo") if purchase_info else "", member.get("email") or "", default=""))
    company_title = str(first_nonzero(company_title, purchase_info.get("companyTitle", "") if purchase_info else "", default=""))
    company_no = str(first_nonzero(company_no, purchase_info.get("companyNo", "") if purchase_info else "", default=""))
    donate_code = str(purchase_info.get("donateCode", "8585") if purchase_info else "8585")
    old_purchase = best_addr.get("purchase", {}) if isinstance(best_addr.get("purchase"), dict) else {}

    def pick(key, default=""):
        value = old_purchase.get(key)
        return value if value not in (None, "") else default

    base_data = {
        "clean_type_id": clean_type_id, "phone": phone,
        "name": str(member.get("name") or "").strip(), "email": str(member.get("email") or "").strip(),
        "tel": str(member.get("tel") or phone), "line": str(member.get("line") or ""),
        "fbName": str(member.get("fb_name") or ""), "fb": str(member.get("fb") or ""),
        "memoProcess": str(member.get("memo_process") or ""), "memoFinance": str(member.get("memo_finance") or ""),
        "addressId": str(best_addr.get("addressId") or ""),
        "country_id": str(address_parts.get("country_id") or best_addr.get("country_id") or pick("country_id", "")),
        "address": address_for_submit, "ping": str(pick("ping", "4")),
        "room": str(pick("room", "0")), "bathroom": str(pick("bathroom", "0")),
        "balcony": str(pick("balcony", "0")), "livingroom": str(pick("livingroom", "0")),
        "kitchen": str(pick("kitchen", "0")), "window": str(pick("window", "")),
        "shutter": str(pick("shutter", "")), "clothes": str(pick("clothes", "0")),
        "dyson": str(pick("dyson", "0")), "refrigerator": str(pick("refrigerator", "0")),
        "disinfection": str(pick("disinfection", "0")), "go_abord": str(pick("go_abord", "0")),
        "home_move": str(pick("home_move", "0")), "storage": str(pick("storage", "0")),
        "cabinet": str(pick("cabinet", "0")), "quintuple": str(pick("quintuple", "0")),
        "hour": str(int(float(hour))), "price": "", "price_vvip": "",
        "person": str(person), "date_s": date_s, "period_s": period_s,
        "period": "", "cycle": "1", "fare": "", "memo": "",
        "notice": str(best_addr.get("notice") or old_purchase.get("notice") or ""),
        "discount_code": str(discount_code or ""), "payment": str(payment_type or ""),
        "carrierInfo": str(carrier_info or ""), "companyNo": str(company_no or ""),
        "companyTitle": str(company_title or ""), "payway": PAYWAY_MAP.get(payway, "2"),
        "invoice_type": invoice_type, "carrier_type_id": carrier_type_id,
        "carrier_info": carrier_info, "company_title": company_title,
        "company_no": company_no, "donate_code": donate_code, "is_backend": "477",
        "member_id": str(member.get("member_id") or ""),
        "company_id": str(best_addr.get("company_id") or best_addr.get("companyId") or pick("company_id", "")),
        "area_id": str(best_addr.get("area_id") or best_addr.get("areaId") or pick("area_id", "")),
        "lat": str(best_addr.get("lat") or pick("lat", "")),
        "lng": str(best_addr.get("lng") or pick("lng", "")),
    }
    if extra_fields:
        base_data.update(extra_fields)

    # 不再用 area_id=25/company_id=1 當預設值；缺少區域就擋下，避免誤成大安區。
    if not str(base_data.get("country_id") or "").strip():
        raise Exception(
            f"地址「{address_for_lookup}」缺少明確縣市/區域下拉選單，已停止成單，"
            "不會自動改成大安區。"
        )
    if not str(base_data.get("area_id") or "").strip() or not str(base_data.get("company_id") or "").strip():
        raise Exception(
            f"地址「{address_for_lookup}」缺少明確 area_id/company_id，已停止成單，"
            "請先在會員地址或後台手動確認區域，避免系統誤判成大安區。"
        )
    _validate_address_before_submit(address_for_lookup, base_data.get("area_id"), context="舊客建單")

    calc_result = calculate_hour(session, base_data, token)
    if not calc_result:
        raise Exception("計算時數失敗")
    calc_fields = extract_calc_fields(calc_result, fallback_hours=base_data["hour"], fallback_fare=best_addr.get("fare", "0"))
    day_type = _day_type_from_date(date_s)
    unit_price = 700 if day_type == "週末" else 600
    person_hours = int(person) * int(float(hour))
    formula_price_with_tax = unit_price * person_hours
    formula_price_no_tax = int(round(formula_price_with_tax / TAX_RATE))
    base_data["price"] = str(formula_price_no_tax)
    base_data["price_vvip"] = str(calc_fields.get("price_vvip") or "0")
    base_data["fare"] = first_nonzero(calc_fields.get("fare"), best_addr.get("fare"), default="0")
    if base_data["price"] in ("", "0", "0.0") and payway != "儲值金":
        raise Exception("計算時數後金額為 0，請確認坪數/時數設定是否正確")
    slot = f"{date_s}_{period_s}"
    raw_section = get_section_raw(session, base_data, token, slot)
    _slot_found = slot_exists_in_section_response(raw_section, slot)
    _auto_shift_ok = False
    if (not _slot_found or not extract_cleaners_from_section_response(raw_section, slot)) and allow_auto_lemon_shift:
        # v8.13：該時段查無班表 → 去勾檸檬人班表，再重查。
        # 只有在客服明確勾選「查無班表時自動補檸檬人」時才會執行，
        # 預設不自動執行，避免查不到班表就自動幫忙勾人。
        _pre = ensure_lemon_cleaner_shifts(
            session=session,
            base_url=base_url,
            service_date=date_s, period_s=period_s, person_count=str(person),
        )
        _auto_shift_ok = bool(_pre.get("success"))
        time.sleep(2)
        raw_section = get_section_raw(session, base_data, token, slot)
        _slot_found = slot_exists_in_section_response(raw_section, slot)
    # v8.30：依規定，查無班表或人數不足時一律擋單，不能成單（不論服務日期
    # 遠近，不再是「查無班表就標記待配班、照樣送出訂單」）。
    cleaners = extract_cleaners_from_section_response(raw_section, slot) if _slot_found else []
    _need = int(person) if str(person).isdigit() else 2
    _has_explicit_cleaners = bool(cleaners)
    if _slot_found and _has_explicit_cleaners and len(cleaners) < _need and allow_auto_lemon_shift:
        _pre2 = ensure_lemon_cleaner_shifts(
            session=session,
            base_url=base_url,
            service_date=date_s, period_s=period_s, person_count=str(_need - len(cleaners)),
        )
        _auto_shift_ok = bool(_pre2.get("success"))
        time.sleep(2)
        raw_section = get_section_raw(session, base_data, token, slot)
        _slot_found = slot_exists_in_section_response(raw_section, slot)
        cleaners = extract_cleaners_from_section_response(raw_section, slot) if _slot_found else []
        _has_explicit_cleaners = bool(cleaners)
    if not _slot_found or not _has_explicit_cleaners or len(cleaners) < _need:
        raise Exception(
            f"查無班表或人數不足（需要 {_need} 人，目前排班頁只有 {len(cleaners)} 人可指派），"
            f"依規定人數不足不能成單，請先確認/補足班表後再建單。"
            f"\n🔧 除錯：area_id={best_addr.get('area_id')}　company_id={best_addr.get('company_id')}"
            f"\nget_section 原始回應前300字：{str(raw_section)[:300]}"
        )
    # v2026.07.10：修正重大 bug——前面 check_contain 若失敗，可能借用過
    # /booking/single 頁面的 token（見上面 v8.5 的備援邏輯），並把 token
    # 變數永久換成借來的那個。如果送出建單時仍沿用這個借來的 token，會導致
    # 送到 /booking/stored_value_routine 的請求帶著 /booking/single 頁面
    # 發出的 token，後台可能因此誤判成一般訂單處理，出現付款方式空白、
    # 訂單卡在待付款、儲值金沒有真的被扣除的情況。這裡在正式送出建單前，
    # 一律重新跟「這筆訂單實際要用的建單網址」要一個乾淨的 token，不管前面
    # check_contain 階段借用過哪個網址的 token。
    booking_url = _booking_url_for_payway(base_url, payway)
    _fresh_token = _fetch_csrf_from_url(session, booking_url)
    if _fresh_token:
        token = _fresh_token
    staff_display = format_staff_from_cleaners(cleaners, people=person)
    before_order_nos = list_order_numbers_for_phone(session, phone, name=member_name)
    booking_resp = session.post(booking_url, data=_build_booking_submit_data(base_data, token, payway, slot), headers=HEADERS, allow_redirects=True)
    display_period = display_period_text(period_s.split("-")[0], period_s.split("-")[1])
    after_order_nos = set()
    new_order_nos = set()
    for wait_seconds in (1, 2, 3, 5):
        time.sleep(wait_seconds)
        after_order_nos = list_order_numbers_for_phone(session, phone, name=member_name)
        new_order_nos = after_order_nos - before_order_nos
        if new_order_nos:
            break

    def _booking_count_success(resp):
        try:
            payload = resp.json()
        except Exception:
            return False
        try:
            return int(payload.get("count", 0)) > 0
        except Exception:
            return False

    def _booking_balance_error(resp):
        """v8.5：儲值金訂單若餘額不足，後台會回 JSON 帶 stored_value_balance 且 count=0。
        找到就回傳餘額數字，否則回傳 None（代表不是餘額不足的情況）。"""
        try:
            payload = resp.json()
        except Exception:
            return None
        if isinstance(payload, dict) and payload.get("stored_value_balance") is not None and int(payload.get("count", 1)) == 0:
            return payload.get("stored_value_balance", 0)
        return None

    def _find_matching_order_after_submit():
        blocks = _fetch_purchase_blocks_for_phone(session, phone, name=member_name)
        target_addr_norm = normalize_addr_for_match(selected_address)
        target_period_compact = str(period_s or "").replace(" ", "")
        target_display_compact = str(display_period or "").replace(" ", "")
        matched = []
        for block in blocks:
            order_no_candidate = block.get("order_no")
            if not order_no_candidate:
                continue
            lines = block.get("lines", [])
            joined = "\n".join(lines)
            service_date_found, service_time_found = _parse_service_date_time_loose(joined)
            if service_date_found != date_s:
                continue
            joined_addr_norm = normalize_addr_for_match(joined)
            if target_addr_norm and target_addr_norm not in joined_addr_norm:
                continue
            payway_found = _extract_payway_line(joined)
            if payway_found and payway_found != payway:
                continue
            time_compact = str(service_time_found or "").replace(" ", "")
            if target_period_compact and target_period_compact not in time_compact and target_display_compact not in time_compact:
                continue
            matched.append(order_no_candidate)
        for candidate in matched:
            if candidate not in before_order_nos:
                return candidate
        return matched[0] if matched else None

    if not new_order_nos:
        _balance_err = _booking_balance_error(booking_resp) if payway == "儲值金" else None
        if _balance_err is not None:
            raise Exception(f"儲值金餘額不足（目前餘額：{_balance_err} 元），無法建立此訂單，請改用信用卡或ATM付款方式。")
        order_no = _find_matching_order_after_submit() if _booking_count_success(booking_resp) else None
        if not order_no:
            debug_snippet = booking_resp.text[:300].replace("\n", " ").strip()
            extra_hint = "後台回傳 count > 0，但訂單列表回查不到符合條件的新訂單；請檢查訂單管理是否已建立。" if _booking_count_success(booking_resp) else ""
            raise Exception(f"建單失敗：系統未產生新訂單編號。\n{extra_hint}\n回應狀態：{booking_resp.status_code}，網址：{booking_resp.url}\n片段：{debug_snippet}")
    elif len(new_order_nos) == 1:
        order_no = next(iter(new_order_nos))
    else:
        order_no = None
        for candidate in new_order_nos:
            meta = fetch_order_meta_by_order_no(session, candidate)
            if meta.get("服務日期") == date_s and display_period.replace(" ", "") in str(meta.get("服務時間", "")).replace(" ", ""):
                order_no = candidate
                break
        if not order_no:
            order_no = sorted(new_order_nos)[-1]
    meta = fetch_order_meta_by_order_no(session, order_no)
    price_no_tax = base_data["price"]
    price_with_tax = formula_price_with_tax
    # v8.13：建單成功後檢查此訂單編號是否重複對應到多張訂單卡片
    _is_dup, _dup_count = _check_order_no_duplicate(session, order_no)
    _dup_warning = (
        f"⚠️ 訂單編號重複警示：訂單編號 {order_no} 目前查詢到 {_dup_count} 張不同的訂單卡片，"
        f"這是後台偶發的訂單編號重複問題，請務必至後台人工確認，避免訂單資料互相搞混或覆蓋！"
        if _is_dup else ""
    )
    # v2026.07.06：跟「新客資料拆解」流程（quick_create_new_customer_order）
    # 補齊同一個「地址比對警示」——後台在存地址時有時會自動加上不正確的市/區
    # 前綴（例如把地址誤判成大安區），這是後台端自己的地址正規化行為，不是本
    # 系統送出的地址資料有誤。之前這個檢查只有新客流程有，舊客快速建單完全
    # 沒有，導致舊客訂單出現同樣的地址跑掉狀況時，畫面上完全看不出來。
    address_mismatch_warning = ""
    backend_actual_address = ""
    try:
        _verify_block = _fetch_purchase_block_for_order_no(session, order_no)
        _verify_addr = _extract_address_line(_verify_block.get("lines", []))
        if _verify_addr:
            backend_actual_address = _verify_addr
            _norm_submitted = normalize_addr_for_match(selected_address)
            _norm_backend = normalize_addr_for_match(_verify_addr)
            if _norm_submitted and _norm_backend and _norm_submitted != _norm_backend:
                address_mismatch_warning = (
                    f"⚠️ 後台實際地址為「{_verify_addr}」，與送出的「{selected_address}」不同"
                    f"（很可能是後台自動判斷區域時加了不正確的市/區前綴，屬於後台端行為，"
                    f"非本系統送出的資料有誤），請至後台手動確認/修正訂單 {order_no} 的地址。"
                )
    except Exception:
        pass
    return {
        "order_no": order_no, "address": selected_address, "date": date_s,
        "period": display_period, "period_s": period_s, "person": str(person),
        "price": price_no_tax, "price_with_tax": price_with_tax, "service_amount": price_with_tax,
        "fare": base_data["fare"], "payway": payway, "region": region,
        "clean_type_id": str(clean_type_id),
        "staff": meta.get("服務人員") or staff_display, "service_status": meta.get("服務狀態", "未處理"),
        "order_no_duplicated": _is_dup, "order_no_duplicate_count": _dup_count,
        "duplicate_order_warning": _dup_warning,
        "backend_actual_address": backend_actual_address,
        "address_mismatch_warning": address_mismatch_warning,
        "env_name": env_name, "session": session,
    }


# =========================================================
# 優惠券 & 訂單備註工具
# =========================================================

def _get_newest_coupon_code(session, base_url, prefix):
    try:
        list_resp = session.get(f"{base_url}/coupon", headers=HEADERS, allow_redirects=True)
        if list_resp.status_code != 200:
            return ""
        ids = re.findall(r"/coupon/detail/(\d+)", list_resp.text)
        if not ids:
            return ""
        prefix_esc = re.escape(prefix)
        for coupon_id in ids[:10]:
            detail_resp = session.get(f"{base_url}/coupon/detail/{coupon_id}", headers=HEADERS)
            if detail_resp.status_code != 200:
                continue
            codes = re.findall(rf"\b{prefix_esc}[A-Za-z0-9]*\b", detail_resp.text)
            if codes:
                return codes[0]
        return ""
    except Exception:
        return ""


def _build_coupon_via_session(session, base_url, title, discount, date_s, date_e, prefix, piece, regions, service_items):
    """用既有 session 建優惠券，不重新登入。回傳實際優惠碼字串。"""
    coupon_add_url = f"{base_url}{COUPON_ADD_URL_PATH}"
    get_resp = session.get(coupon_add_url, headers=HEADERS, allow_redirects=True)
    if get_resp.status_code != 200:
        raise Exception("無法開啟優惠券新增頁面")
    token_m = re.search(r'<meta name="csrf-token" content="([^"]+)"', get_resp.text)
    csrf = token_m.group(1) if token_m else ""
    if not csrf:
        raise Exception("無法取得 CSRF token")
    coupon_fields = [
        ("coupon_type_id", "1"), ("title", str(title)),
        ("date_s", str(date_s)), ("date_e", str(date_e)),
        ("prefix", str(prefix)), ("discount", str(int(float(discount)))),
        ("piece", str(int(piece))), ("_token", csrf),
    ]
    for rn in (regions or ["台北", "台中"]):
        coupon_fields.append(("company_id[]", COUPON_COMPANY_ID_MAP.get(rn, "1")))
    for svc in (service_items or ["居家清潔", "裝修細清"]):
        coupon_fields.append(("service_item[]", COUPON_SERVICE_ITEM_MAP.get(svc, "1")))
    coupon_files = [(k, (None, v)) for k, v in coupon_fields]
    post_headers = {k: v for k, v in HEADERS.items() if k.lower() != "content-type"}
    post_resp = session.post(coupon_add_url, files=coupon_files, headers=post_headers, allow_redirects=True)
    if post_resp.status_code not in (200, 302):
        snippet = post_resp.text[:200].replace("\n", " ")
        raise Exception(f"優惠券建立失敗：HTTP {post_resp.status_code}｜{snippet}")
    if post_resp.url and "add" in post_resp.url:
        raise Exception("優惠券建立失敗：後台驗證未通過，請確認區域/服務項目欄位")
    time.sleep(1)
    return _get_newest_coupon_code(session, base_url, str(prefix))


def create_coupon(
    env_name, backend_email, backend_password, title, discount,
    date_s, date_e, prefix, piece="1", regions=None, service_items=None,
    coupon_type="不得與其他優惠券重複",
):
    """獨立登入版本的優惠券建立，供 UI 直接呼叫。"""
    base_url = _configure_environment(env_name)
    session = requests.Session()
    if not login(session, backend_email, backend_password):
        raise Exception("後台登入失敗，請確認帳號密碼")
    regions = regions or ["台北"]
    service_items = service_items or ["居家清潔"]
    coupon_add_url = f"{base_url}{COUPON_ADD_URL_PATH}"
    get_resp = session.get(coupon_add_url, headers=HEADERS, allow_redirects=True)
    if get_resp.status_code != 200:
        raise Exception(f"無法開啟優惠券新增頁面：HTTP {get_resp.status_code}")
    token = ""
    token_match = re.search(r'<meta name="csrf-token" content="([^"]+)"', get_resp.text)
    if token_match:
        token = token_match.group(1)
    if not token:
        token_match2 = re.search(r'name=\"_token\"\s+value=\"([^\"]+)\"', get_resp.text)
        if token_match2:
            token = token_match2.group(1)
    if not token:
        raise Exception("無法取得 CSRF token，請確認已登入後台")
    fields = [
        ("coupon_type_id", COUPON_TYPE_MAP.get(coupon_type, "1")),
        ("title", str(title).strip()), ("date_s", str(date_s).strip()),
        ("date_e", str(date_e).strip()), ("prefix", str(prefix).strip()),
        ("discount", str(int(float(discount)))), ("piece", str(int(piece))), ("_token", token),
    ]
    for r in (regions or ["台北"]):
        fields.append(("company_id[]", COUPON_COMPANY_ID_MAP.get(r, "1")))
    for s in (service_items or ["居家清潔"]):
        fields.append(("service_item[]", COUPON_SERVICE_ITEM_MAP.get(s, "1")))
    coupon_files3 = [(k, (None, v)) for k, v in fields]
    post_headers3 = {k: v for k, v in HEADERS.items() if k.lower() != "content-type"}
    post_resp = session.post(coupon_add_url, files=coupon_files3, headers=post_headers3, allow_redirects=True)
    if post_resp.status_code not in (200, 302):
        snippet = post_resp.text[:200].replace("\n", " ")
        raise Exception(f"優惠券建立失敗：HTTP {post_resp.status_code}｜{snippet}")
    if post_resp.url and "add" in post_resp.url:
        raise Exception("優惠券建立失敗：後台驗證未通過，請確認區域/服務項目欄位")
    coupon_code = _get_newest_coupon_code(session, base_url, str(prefix).strip())
    return {"success": True, "coupon_prefix": prefix, "coupon_code": coupon_code, "discount": int(float(discount)), "piece": int(piece), "message": f"優惠券建立成功，優惠碼：{coupon_code}"}


def _mark_order_as_paid(session, base_url, order_no):
    """
    v2026.07.10：呼叫後台 /purchase/set_success/{purchase_id}，把訂單標記為
    已付款。用於儲值金補價差第二段（客付補價差單）：這張單本質上是用優惠券
    折抵掉原儲值金餘額金額，客人不需要再實際刷卡/匯款，所以要主動標記為
    已付款，不能讓它卡在待付款狀態。
    """
    edit_id = _fetch_order_edit_id(session, order_no)
    if not edit_id:
        return False, f"無法取得訂單 {order_no} 的後台 ID，無法標記已付款"
    try:
        resp = session.get(f"{base_url}/purchase/set_success/{edit_id}", headers=HEADERS, allow_redirects=True)
        if resp.status_code == 200:
            return True, "已標記為已付款"
        return False, f"標記已付款失敗，HTTP {resp.status_code}"
    except Exception as e:
        return False, f"標記已付款失敗：{e}"


def _service_due_after_fare(session, order_no):
    block = _fetch_purchase_block_for_order_no(session, order_no)
    joined = "\n".join(block.get("lines", []))
    fare = _extract_fare_line(joined) or "0"
    service_amount = _service_amount_from_block(joined, fare)
    try:
        return int(float(str(service_amount or "0").replace(",", "")))
    except Exception:
        return None


def _fetch_order_edit_id(session, order_no):
    params = dict(PURCHASE_FILTER_PARAMS_TEMPLATE)
    params["orderNo"] = str(order_no).strip()
    resp = session.get(orders.PURCHASE_URL, params=params, headers=HEADERS, allow_redirects=True)
    if resp.status_code != 200:
        return None
    m = re.search(r"/purchase/edit/(\d+)", resp.text)
    return m.group(1) if m else None


def _extract_purchase_json_from_edit_html(html_text):
    """
    從訂單修改頁 Vue data() 裡的 purchase JSON 取出真實目前值。
    訂單修改頁有些欄位是 Vue 動態渲染，靜態 HTML 會看到樣板字串或未 checked
    的 radio；更新發票號碼時必須優先用這份 purchase JSON，避免誤改其他欄位。
    """
    marker = "purchase:"
    idx = str(html_text or "").find(marker)
    if idx < 0:
        return {}
    start = idx + len(marker)
    while start < len(html_text) and html_text[start].isspace():
        start += 1
    if start >= len(html_text) or html_text[start] != "{":
        return {}
    decoder = json.JSONDecoder()
    try:
        obj, _end = decoder.raw_decode(html_text[start:])
        return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}


def _build_purchase_edit_payload_from_page(html_text, csrf, overrides=None):
    """
    組訂單修改頁 POST payload。
    只覆蓋 overrides 指定欄位，其餘欄位用頁面內 Vue purchase JSON 的真實值保留。
    """
    overrides = overrides or {}
    soup = BeautifulSoup(html_text or "", "html.parser")
    existing = {}

    # 先用靜態表單建立基本 payload
    for tag in soup.find_all(["input", "textarea", "select"]):
        name = tag.get("name")
        if not name:
            continue
        if name == "_method":
            continue

        if tag.name == "textarea":
            value = tag.text or ""
        elif tag.name == "select":
            selected = tag.find("option", selected=True)
            value = selected.get("value", "") if selected else ""
        elif tag.get("type") in ("radio", "checkbox"):
            if tag.has_attr("checked"):
                value = tag.get("value", "")
            else:
                continue
        else:
            value = tag.get("value", "")

        existing[name] = value

    purchase = _extract_purchase_json_from_edit_html(html_text)

    # Vue purchase JSON key -> 後台表單 name
    vue_to_form = {
        "line": "line",
        "fbName": "fbName",
        "fb": "fb",
        "memoProcess": "memoProcess",
        "memoFinance": "memoFinance",
        "address": "address",
        "areaId": "area_id",
        "lat": "lat",
        "lng": "lng",
        "progress": "progress",
        "email": "email",
        "phone": "phone",
        "period": "period",
        "invoiceNo": "invoice_no",
        "isTransfer": "is_transfer",
        "memo": "memo",
        "notice": "notice",
        "isCharge": "isCharge",
        "chargeDate": "chargeDate",
        "chargePayment": "chargePayment",
        "chargeInvoiceDate": "chargeInvoiceDate",
        "chargeAmount": "chargeAmount",
        "chargeInvoice": "chargeInvoice",
        "chargeNote": "chargeNote",
        "isRefund": "isRefund",
        "refundDate": "refundDate",
        "refundPayment": "refundPayment",
        "refundAmount": "refundAmount",
        "refundNumber": "refundNumber",
        "refundInvoiceDate": "refundInvoiceDate",
        "refundInvoiceAmount": "refundInvoiceAmount",
        "refundInvoice": "refundInvoice",
        "refundNote": "refundNote",
    }
    for vue_key, form_key in vue_to_form.items():
        if vue_key in purchase:
            val = purchase.get(vue_key)
            existing[form_key] = "" if val is None else str(val)

    existing["_token"] = csrf

    for k, v in overrides.items():
        existing[k] = "" if v is None else str(v)

    return existing


def _update_order_invoice_no_text(session, base_url, order_no, invoice_no_text):
    """
    只更新訂單修改頁的 invoice_no 欄位。
    其他欄位以 Vue purchase JSON 的真實值保留，避免靜態 HTML 的 radio/textarea
    樣板值造成加收、待退、服務狀態等欄位被誤改。
    """
    try:
        edit_id = _fetch_order_edit_id(session, order_no)
        if not edit_id:
            return False, f"找不到訂單 {order_no} 的編輯 ID"
        edit_url = f"{base_url}/purchase/edit/{edit_id}"
        get_resp = session.get(edit_url, headers=HEADERS, allow_redirects=True)
        if get_resp.status_code != 200:
            return False, f"無法開啟編輯頁面：HTTP {get_resp.status_code}"
        token_m = re.search(r'<meta name="csrf-token" content="([^"]+)"', get_resp.text)
        csrf = token_m.group(1) if token_m else ""
        if not csrf:
            token_m2 = re.search(r'name="_token"[^>]*value="([^"]+)"', get_resp.text)
            csrf = token_m2.group(1) if token_m2 else ""
        if not csrf:
            return False, "無法取得 CSRF token"

        payload = _build_purchase_edit_payload_from_page(
            get_resp.text,
            csrf,
            overrides={"invoice_no": invoice_no_text},
        )
        post_resp = session.post(
            edit_url,
            data=payload,
            headers={**HEADERS, "Content-Type": "application/x-www-form-urlencoded"},
            allow_redirects=True,
        )
        success = post_resp.status_code in (200, 302)
        return success, f"HTTP {post_resp.status_code}"
    except Exception as e:
        return False, str(e)


def _update_order_note(session, base_url, order_no, note):
    """
    更新處理備註 memoProcess。
    其餘欄位同樣用 Vue purchase JSON 的真實值保留，避免訂單修改頁靜態 HTML
    裡的 radio/textarea 樣板值誤改加收、待退、服務狀態等欄位。
    """
    try:
        edit_id = _fetch_order_edit_id(session, order_no)
        if not edit_id:
            return False, f"找不到訂單 {order_no} 的編輯 ID"
        edit_url = f"{base_url}/purchase/edit/{edit_id}"
        get_resp = session.get(edit_url, headers=HEADERS, allow_redirects=True)
        if get_resp.status_code != 200:
            return False, f"無法開啟編輯頁面：HTTP {get_resp.status_code}"
        token_m = re.search(r'<meta name="csrf-token" content="([^"]+)"', get_resp.text)
        csrf = token_m.group(1) if token_m else ""
        if not csrf:
            token_m2 = re.search(r'name="_token"[^>]*value="([^"]+)"', get_resp.text)
            csrf = token_m2.group(1) if token_m2 else ""
        if not csrf:
            return False, "無法取得 CSRF token"

        payload = _build_purchase_edit_payload_from_page(
            get_resp.text,
            csrf,
            overrides={"memoProcess": note},
        )
        post_resp = session.post(
            edit_url,
            data=payload,
            headers={**HEADERS, "Content-Type": "application/x-www-form-urlencoded"},
            allow_redirects=True,
        )
        success = post_resp.status_code in (200, 302)
        return success, f"HTTP {post_resp.status_code}"
    except Exception as e:
        return False, str(e)


def _update_order_service_date(session, base_url, order_no, new_date_s, new_period_s="", phone=""):
    """
    把原訂單服務日期/時段改成新的。
    endpoint: GET /purchase/change_date/{edit_id}?phone={phone}
              POST /purchase/change_date/{edit_id}?phone={phone}
    表單欄位：
        name="date"    → value = "2026-07-02"
        name="section" → value = "09:00-16:00"（動態載入，直接 POST 正確值）
        name="_token"  → CSRF token
        name="area_id" → 從頁面抓
        name="clean_type_id" → 從頁面抓
    回傳 (成功bool, 訊息str)。
    """
    try:
        edit_id = _fetch_order_edit_id(session, order_no)
        if not edit_id:
            return False, f"找不到訂單 {order_no} 的編輯 ID"

        params = {}
        if phone:
            params["phone"] = str(phone)

        change_date_url = f"{base_url}/purchase/change_date/{edit_id}"
        get_resp = session.get(change_date_url, params=params, headers=HEADERS, allow_redirects=True)
        if get_resp.status_code != 200:
            return False, f"無法開啟修改日期頁面：HTTP {get_resp.status_code}"

        # 取 CSRF token
        token_m = re.search(r'<meta name="csrf-token" content="([^"]+)"', get_resp.text)
        csrf = token_m.group(1) if token_m else ""
        if not csrf:
            # 備用：從 hidden input 取
            token_m2 = re.search(r'name="_token"[^>]*value="([^"]+)"', get_resp.text)
            csrf = token_m2.group(1) if token_m2 else ""
        if not csrf:
            return False, "無法取得 CSRF token"

        # 取 area_id / clean_type_id
        area_m = re.search(r'name="area_id"[^>]*value="([^"]*)"', get_resp.text)
        clean_type_m = re.search(r'name="clean_type_id"[^>]*value="([^"]*)"', get_resp.text)
        area_id = area_m.group(1) if area_m else ""
        clean_type_id = clean_type_m.group(1) if clean_type_m else ""

        # 直接 POST：date 和 section 填入目標值
        # section 值格式為 "09:00-16:00"，與 period_s 相同
        data = {
            "_token": csrf,
            "date": str(new_date_s),
            "section": str(new_period_s) if new_period_s else "",
        }
        if area_id:
            data["area_id"] = area_id
        if clean_type_id:
            data["clean_type_id"] = clean_type_id

        post_resp = session.post(
            change_date_url, params=params, data=data,
            headers={**HEADERS, "Content-Type": "application/x-www-form-urlencoded"},
            allow_redirects=True,
        )
        success = post_resp.status_code in (200, 302)
        return success, f"HTTP {post_resp.status_code}"
    except Exception as e:
        return False, str(e)



# =========================================================
# 檸檬人勾班工具函式
# =========================================================

def _parse_cleaner_shift_page(html_text, date_str=None):
    token_m = re.search(r'name=["\']_token["\'][^>]*value=["\']([^"\']+)["\']', html_text or "")
    csrf = token_m.group(1) if token_m else ""
    if not csrf:
        meta_m = re.search(r'<meta name="csrf-token" content="([^"]+)"', html_text or "")
        csrf = meta_m.group(1) if meta_m else ""
    checked_fields = []
    checked_codes_on_date = set()
    for m in re.finditer(r'<input\b[^>]*\btype=["\']hidden["\'][^>]*>', html_text or "", re.I):
        tag = m.group(0)
        name_m = re.search(r'\bname=["\']([^"\']+)["\']', tag, re.I)
        value_m = re.search(r'\bvalue=["\']([^"\']*)["\']', tag, re.I)
        if name_m:
            checked_fields.append((name_m.group(1), value_m.group(1) if value_m else ""))
    for m in re.finditer(r'<input\b[^>]*\bchecked\b[^>]*>', html_text or "", re.I):
        tag = m.group(0)
        name_m = re.search(r'\bname=["\']([^"\']+)["\']', tag, re.I)
        value_m = re.search(r'\bvalue=["\']?([^"\'\s>]+)', tag, re.I)
        date_m = re.search(r'\bdate=["\']([^"\']+)["\']', tag, re.I)
        if not name_m or not value_m:
            continue
        name = name_m.group(1)
        value = value_m.group(1)
        checked_fields.append((name, value))
        d = date_m.group(1) if date_m else ""
        if date_str and d == date_str:
            checked_codes_on_date.add(_shift_value_to_code_by_name(name, value))
    return csrf, checked_fields, checked_codes_on_date


def _get_cleaner_shift_form_info(session, base_url, cleaner_id, date_str):
    ym = str(date_str)[:7]
    resp = session.get(f"{base_url}/cleaner1/{cleaner_id}/shift", params={"month": ym}, headers=HEADERS, allow_redirects=True)
    if resp.status_code != 200:
        return "", [], set(), f"HTTP {resp.status_code}"
    csrf, checked_fields, checked_codes = _parse_cleaner_shift_page(resp.text, date_str)
    return csrf, checked_fields, checked_codes, ""


def _get_cleaner_shifts_on_date(session, base_url, cleaner_id, date_str):
    _csrf, _fields, checked_codes, _msg = _get_cleaner_shift_form_info(session, base_url, cleaner_id, date_str)
    return checked_codes


def _search_lemon_cleaners(session, base_url, target_month=None, min_needed=0):
    entries = []
    seen_ids = set()
    seen_names = set()
    target_month = str(target_month or date.today().strftime("%Y-%m"))[:7]
    min_needed = int(min_needed or 0)

    def lemon_sort_key(item):
        m = re.search(r"檸檬人\s*(\d+)", item[1])
        return int(m.group(1)) if m else 9999

    def add_entry(cid, name):
        cid = str(cid or "").strip()
        name = re.sub(r"\s+", "", str(name or "").strip())
        m = re.search(r"檸檬人\d+", name)
        if m:
            name = m.group(0)
        if not cid or cid in seen_ids or "檸檬人" not in name:
            return
        if name in seen_names:
            return
        seen_ids.add(cid)
        seen_names.add(name)
        entries.append((cid, name))

    candidate_ids = []

    def add_candidate(cid):
        cid = str(cid or "").strip()
        if cid.isdigit() and cid not in candidate_ids:
            candidate_ids.append(cid)

    try:
        resp = session.get(f"{base_url}/cleaner1", params={"area_id": "", "keyword": "檸檬"}, headers=HEADERS, allow_redirects=True)
    except Exception:
        resp = None

    if resp is not None and resp.status_code == 200:
        html = resp.text or ""
        row_blocks = re.split(r"<tr\b", html, flags=re.I)
        for row in row_blocks:
            if "檸檬人" not in row:
                continue
            name_m = re.search(r"檸檬人\d+", row)
            ids = re.findall(r"/cleaner1/(\d+)(?=[/'\"?#])", row, re.I)
            ids += re.findall(r"cleaner[_-]?id[=:'\" ]+(\d+)", row, re.I)
            for cid in ids:
                add_candidate(cid)
                if name_m:
                    add_entry(cid, name_m.group(0))
        for m in re.finditer(r"/cleaner1/(\d+)(?=[/'\"?#])", html, re.I):
            cid = m.group(1)
            ctx = html[max(0, m.start() - 1000): m.end() + 1000]
            name_m = re.search(r"檸檬人\d+", ctx)
            add_candidate(cid)
            if name_m:
                add_entry(cid, name_m.group(0))

    entries.sort(key=lemon_sort_key)
    if min_needed and len(entries) >= min_needed:
        return entries

    for cid in list(range(1, 501)):
        add_candidate(cid)

    for cid in candidate_ids:
        if str(cid) in seen_ids:
            continue
        try:
            r = session.get(f"{base_url}/cleaner1/{cid}/shift", params={"month": target_month}, headers=HEADERS, allow_redirects=True)
        except Exception:
            continue
        if r.status_code != 200:
            continue
        txt = r.text or ""
        name_m = re.search(r"專員\s*[：:]\s*(?:<[^>]+>\s*)*(檸檬人\d+)", txt)
        if not name_m:
            name_m = re.search(r"<label>\s*(檸檬人\d+)\s*</label>", txt)
        if name_m:
            add_entry(cid, name_m.group(1))
            entries.sort(key=lemon_sort_key)
            if min_needed and len(entries) >= min_needed:
                break

    entries.sort(key=lemon_sort_key)
    return entries


def _set_cleaner_shift_if_available(session, base_url, cleaner_id, cleaner_name, date_str, target_shift_code):
    csrf, checked_fields, checked_codes, err = _get_cleaner_shift_form_info(session, base_url, cleaner_id, date_str)
    if err:
        return {"success": False, "name": cleaner_name, "id": cleaner_id, "reason": err, "checked": sorted(checked_codes)}
    target_shift_code = _shift_value_to_code(target_shift_code)
    if checked_codes:
        return {
            "success": False, "name": cleaner_name, "id": cleaner_id,
            "reason": f"{date_str} 已有班別 {'、'.join(sorted(checked_codes))}，為保護已配班人員不寫入新班別",
            "checked": sorted(checked_codes), "protected_existing_shift": True,
        }
    conflicts = sorted(c for c in checked_codes if _shift_codes_conflict(c, target_shift_code))
    if conflicts:
        return {"success": False, "name": cleaner_name, "id": cleaner_id, "reason": f"{date_str} 已勾 {'、'.join(conflicts)}，與 {target_shift_code} 衝突", "checked": sorted(checked_codes)}
    if target_shift_code in checked_codes:
        # 該時段已勾班，可能已被其他訂單佔用，跳過換下一位檸檬人
        return {"success": False, "name": cleaner_name, "id": cleaner_id, "reason": f"{date_str} {target_shift_code} 已勾班（可能已有其他訂單使用），換下一位", "checked": sorted(checked_codes), "already_checked": True}
    target_name = f"shift_{date_str}_{_shift_code_to_group(target_shift_code)}"
    target_value = _shift_code_to_value(target_shift_code)
    fields = []
    if csrf:
        fields.append(("_token", csrf))
    seen = set()
    for name, value in checked_fields:
        key = (name, value)
        if key in seen:
            continue
        seen.add(key)
        fields.append((name, value))
    if (target_name, target_value) not in seen:
        fields.append((target_name, target_value))
    resp = session.post(f"{base_url}/cleaner1/{cleaner_id}/shift", params={"month": str(date_str)[:7]}, data=fields, headers=HEADERS, allow_redirects=True)
    ok = resp.status_code in (200, 302)
    if ok:
        _csrf2, _fields2, checked_after, _err2 = _get_cleaner_shift_form_info(session, base_url, cleaner_id, date_str)
        ok = target_shift_code in checked_after
    return {
        "success": ok, "name": cleaner_name, "id": cleaner_id,
        "message": f"{cleaner_name} 已補勾 {date_str} {target_shift_code}" if ok else f"POST 後未確認到班別 {date_str} {target_shift_code}（HTTP {resp.status_code}）",
        "checked": sorted(checked_codes), "target": target_shift_code,
    }


def ensure_lemon_cleaner_shifts(session, base_url, service_date, period_s, person_count):
    target_shift_code = _period_to_shift_code(period_s)
    if not target_shift_code:
        return {"success": False, "message": f"無法判斷服務時段 {period_s} 對應班別", "assigned": [], "skipped": []}
    cleaners = _search_lemon_cleaners(session, base_url, target_month=str(service_date)[:7], min_needed=int(person_count))
    if not cleaners:
        return {"success": False, "message": "找不到檸檬人清單", "assigned": [], "skipped": []}
    need = int(person_count)
    assigned = []
    assigned_ids = []
    skipped = []
    seen_candidate_names = set()
    seen_candidate_ids = set()
    for cleaner_id, cleaner_name in cleaners:
        if str(cleaner_id) in seen_candidate_ids or str(cleaner_name) in seen_candidate_names:
            continue
        seen_candidate_ids.add(str(cleaner_id))
        seen_candidate_names.add(str(cleaner_name))
        if len(assigned) >= need:
            break
        result = _set_cleaner_shift_if_available(session, base_url, cleaner_id, cleaner_name, service_date, target_shift_code)
        if result.get("success"):
            assigned.append(cleaner_name)
            assigned_ids.append(str(cleaner_id))
        else:
            skipped.append(result)
    ok = len(assigned) >= need
    return {
        "success": ok,
        "message": f"已預先補勾檸檬人：{'、'.join(assigned)}" if ok else f"可用檸檬人不足：需要 {need} 位，找到 {len(assigned)} 位",
        "assigned": assigned, "assigned_ids": assigned_ids, "skipped": skipped, "target_shift_code": target_shift_code,
    }


def _get_schedule_edit_info(session, base_url, date_str, purchase_id):
    resp = session.get(f"{base_url}/schedule/edit", params={"date": date_str, "purchase_id": purchase_id}, headers=HEADERS, allow_redirects=True)
    if resp.status_code != 200:
        return None, [], []
    token_m = re.search(r'<meta name="csrf-token" content="([^"]+)"', resp.text)
    csrf = token_m.group(1) if token_m else ""
    origin_ids = re.findall(r'name=["\']originShiftId\[\]["\'][^>]*value=["\']?(\d+)["\']?', resp.text)
    if not origin_ids:
        origin_ids = re.findall(r'value=["\']?(\d+)["\'][^>]*name=["\']originShiftId\[\]', resp.text)
    slots = []
    slot_blocks = re.split(r'name=["\']originShiftId\[\]', resp.text)[1:]
    for block in slot_blocks:
        slot_map = {}
        for m in re.finditer(r'<label[^>]+for=["\']shift_\d+_(\d+)["\'][^>]*>([^<]+)</label>', block):
            shift_id = m.group(1)
            name = m.group(2).strip()
            slot_map[name] = shift_id
        slots.append(slot_map)
    return csrf, origin_ids, slots


def assign_lemon_cleaners_to_order(session, base_url, order_no_a, service_date, period_s, person_count, allow_auto_lemon_shift=False):
    """
    原訂單A換人：
    1. GET 排班修改頁，若各槽位已有可換班人員則直接換
    2. 若排班頁沒有人（無可換班候選），且 allow_auto_lemon_shift=True 才會先去勾檸檬人
       班表，再重取頁面換人；預設不會自動勾班，避免查無班表就自動幫忙勾人。
    不預先全量勾班，避免把其他訂單的檸檬人班別干擾掉。
    """
    purchase_id = _fetch_order_edit_id(session, order_no_a)
    if not purchase_id:
        return {"success": False, "message": f"無法取得訂單 {order_no_a} 的後台 ID"}

    def _lemon_name_no(name):
        m = re.search(r"檸檬人\s*(\d+)", str(name or ""))
        return int(m.group(1)) if m else 9999

    def _pick_lemon(slot_map, used):
        candidates = [
            (k.strip(), v) for k, v in slot_map.items()
            if "檸檬人" in k and k.strip() not in used
        ]
        candidates.sort(key=lambda x: _lemon_name_no(x[0]))
        return candidates[0] if candidates else None

    csrf, origin_ids, slots = _get_schedule_edit_info(session, base_url, service_date, purchase_id)
    if not slots:
        return {"success": False, "message": "無法取得排班修改頁，請手動操作"}

    n = int(person_count)
    used_names = set()
    shift_choices = []
    assigned_names = []
    need_lemon_count = 0

    # 第一輪：看排班頁有沒有檸檬人可選
    # shift_choices 和 assigned_names 必須同步增長（用 None 佔位），避免索引錯位
    for i, slot_map in enumerate(slots):
        if i >= n:
            break
        entry = _pick_lemon(slot_map, used_names)
        if entry:
            shift_choices.append(entry[1])
            assigned_names.append(entry[0])
            used_names.add(entry[0])
        else:
            # 這個槽位排班頁沒有檸檬人，需要先去勾班
            shift_choices.append(None)
            assigned_names.append(None)
            need_lemon_count += 1

    # 若有槽位沒有檸檬人可選，且客服有勾選自動補檸檬人，先勾班再重取頁面
    pre_shift_result = {"success": True, "assigned": [], "message": "排班頁已有檸檬人，無需額外勾班"}
    if need_lemon_count > 0:
        if not allow_auto_lemon_shift:
            return {
                "success": False,
                "message": (
                    f"排班頁有 {need_lemon_count} 個槽位查無可換班的檸檬人，"
                    f"若需要系統自動補檸檬人班表，請勾選「查無班表時自動補檸檬人」後再試一次；"
                    f"否則請至後台手動勾班。"
                ),
                "assigned": [],
            }
        pre_shift_result = ensure_lemon_cleaner_shifts(
            session=session, base_url=base_url,
            service_date=service_date, period_s=period_s,
            person_count=str(need_lemon_count),
        )
        # 重取排班修改頁
        csrf, origin_ids, slots = _get_schedule_edit_info(session, base_url, service_date, purchase_id)
        if not slots:
            return {"success": False, "message": "勾班後無法重取排班修改頁，請手動操作"}
        # 重新填入 None 的槽位
        for i, slot_map in enumerate(slots):
            if i >= n:
                break
            if shift_choices[i] is None:
                entry = _pick_lemon(slot_map, used_names)
                if entry:
                    shift_choices[i] = entry[1]
                    assigned_names[i] = entry[0]
                    used_names.add(entry[0])
                else:
                    return {
                        "success": False,
                        "message": f"槽位 {i+1} 勾班後仍找不到可用的檸檬人，請手動操作",
                        "pre_shift_result": pre_shift_result,
                    }

    # 過濾掉 None（避免 None 混入名單；同時不覆蓋 n=person_count）
    assigned_names = [name for name in assigned_names if name]

    fields = [("_token", csrf), ("_method", "PUT")]
    for oid in origin_ids[:n]:
        fields.append(("originShiftId[]", oid))
    for j, sid in enumerate(shift_choices[:n]):
        fields.append((f"shiftId[{j}]", sid))
    post_resp = session.post(
        f"{base_url}/schedule/edit",
        params={"date": service_date, "purchase_id": purchase_id},
        data=fields, headers=HEADERS, allow_redirects=True,
    )
    success = post_resp.status_code in (200, 302)
    # actual_person_count：從 originShiftId 數量取得訂單實際人數（最準確）
    actual_person_count = len(origin_ids) if origin_ids else n
    return {
        "success": success,
        "assigned": assigned_names,
        "actual_person_count": actual_person_count,
        "pre_shift_result": pre_shift_result,
        "message": f"已換為檸檬人：{'、'.join(assigned_names)}" if success else f"POST 失敗：HTTP {post_resp.status_code}",
    }


def _assign_mixed_cleaners_to_order(session, base_url, order_no, service_date, period_s, person_count, allow_auto_lemon_shift=False):
    """
    v8.4 混合配班：優先用排班頁現有一般專員，不足再補檸檬人。
    v8.13：是否預先勾檸檬人班表改由 allow_auto_lemon_shift 控制。
    回傳 dict: success / assigned / assigned_types / message
    """
    purchase_id = _fetch_order_edit_id(session, order_no)
    if not purchase_id:
        return {"success": False, "message": f"無法取得訂單 {order_no} 的後台 ID"}
    n = int(person_count)
    if allow_auto_lemon_shift:
        pre_shift_result = ensure_lemon_cleaner_shifts(session=session, base_url=base_url, service_date=service_date, period_s=period_s, person_count=person_count)
    else:
        pre_shift_result = {"success": True, "assigned": [], "message": "未勾選自動補檸檬人，跳過預先勾班"}
    preferred_lemon_names = list(pre_shift_result.get("assigned") or [])
    csrf, origin_ids, slots = _get_schedule_edit_info(session, base_url, service_date, purchase_id)
    if not slots:
        return {"success": False, "message": "無法取得排班修改頁，請手動操作"}
    shift_choices = []
    assigned_names = []
    assigned_types = []
    used_names = set()

    def _lemon_no(name):
        m = re.search(r"檸檬人\s*(\d+)", str(name or ""))
        return int(m.group(1)) if m else 9999

    for i, slot_map in enumerate(slots):
        if i >= n:
            break
        chosen = None
        chosen_type = None
        # 優先：一般專員
        normal_candidates = [(name_key.strip(), sid) for name_key, sid in slot_map.items() if "檸檬人" not in name_key and name_key.strip() not in used_names]
        if normal_candidates:
            chosen = normal_candidates[0]
            chosen_type = "一般"
        # 備用：檸檬人
        if not chosen:
            lemon_candidates = [(name_key.strip(), sid) for name_key, sid in slot_map.items() if "檸檬人" in name_key and name_key.strip() not in used_names]
            preferred = [c for c in lemon_candidates if c[0] in preferred_lemon_names]
            others = [c for c in lemon_candidates if c[0] not in preferred_lemon_names]
            preferred.sort(key=lambda x: _lemon_no(x[0]))
            others.sort(key=lambda x: _lemon_no(x[0]))
            all_lemon = preferred + others
            if all_lemon:
                chosen = all_lemon[0]
                chosen_type = "檸檬人"
        if chosen:
            shift_choices.append(chosen[1])
            assigned_names.append(chosen[0])
            assigned_types.append(chosen_type)
            used_names.add(chosen[0])
        else:
            return {"success": False, "message": f"槽位 {i+1} 找不到可用人員（一般專員或檸檬人），請手動操作", "assigned": assigned_names, "assigned_types": assigned_types}
    fields = [("_token", csrf), ("_method", "PUT")]
    for oid in origin_ids:
        fields.append(("originShiftId[]", oid))
    for j, sid in enumerate(shift_choices):
        fields.append((f"shiftId[{j}]", sid))
    post_resp = session.post(f"{base_url}/schedule/edit", params={"date": service_date, "purchase_id": purchase_id}, data=fields, headers=HEADERS, allow_redirects=True)
    success = post_resp.status_code in (200, 302)
    normal_count = assigned_types.count("一般")
    lemon_count = assigned_types.count("檸檬人")
    detail = []
    if normal_count:
        detail.append(f"一般專員 {normal_count} 位")
    if lemon_count:
        detail.append(f"檸檬人 {lemon_count} 位")
    return {
        "success": success, "assigned": assigned_names, "assigned_types": assigned_types,
        "pre_shift_result": pre_shift_result,
        "message": f"配班已設為：{'、'.join(assigned_names)}（{'＋'.join(detail)}）" if success else f"POST 失敗：HTTP {post_resp.status_code}",
    }


# =========================================================
# 訂單轉換（一對一，原有邏輯）& 一對多（v8.4 新增）
# =========================================================

def convert_order(
    env_name, backend_email, backend_password, order_no_a,
    new_person, new_hour, new_date_s, new_period_s, clean_type_id="1",
    allow_auto_lemon_shift=False,
):
    """一對一訂單轉換：原單A全換檸檬人，建折價券，建新單B。"""
    base_url = _configure_environment(env_name)
    session = requests.Session()
    if not login(session, backend_email, backend_password):
        raise Exception("後台登入失敗，請確認帳號密碼")
    block_a = _fetch_purchase_block_for_order_no(session, order_no_a)
    lines_a = block_a.get("lines", [])
    joined_a = "\n".join(lines_a)
    service_date_a, period_a_raw = _parse_service_date_time_loose(joined_a)
    address_a = _extract_address_line(lines_a)
    payway_a = normalize_booking_payway(_extract_payway_line(joined_a))
    fare_a = _extract_fare_line(joined_a) or "0"
    service_amount_a = _service_amount_from_block(joined_a, fare_a)
    phone_a = _extract_phone_from_block_lines(lines_a)
    region_a = get_region_by_address(address_a, ACCOUNTS) or "台北"
    if not phone_a:
        raise Exception(f"無法從訂單 {order_no_a} 取得客人電話，請手動確認")
    if not service_amount_a or service_amount_a == "0":
        raise Exception(f"訂單 {order_no_a} 金額為 0 或無法取得，請確認訂單付款狀態")
    if not service_date_a:
        raise Exception(f"訂單 {order_no_a} 無法取得服務日期")
    if not address_a:
        raise Exception(f"訂單 {order_no_a} 無法取得服務地址")
    today_str = date.today().strftime("%Y-%m-%d")
    coupon_prefix = order_no_a[-4:]
    coupon_discount = int(float(str(service_amount_a).replace(",", "")))
    coupon_code = _build_coupon_via_session(
        session, base_url, title=f"訂單轉換-{order_no_a}",
        discount=coupon_discount, date_s=today_str, date_e=service_date_a,
        prefix=coupon_prefix, piece=2, regions=["台北", "台中"], service_items=["居家清潔", "裝修細清"],
    )
    if not coupon_code or coupon_code == coupon_prefix:
        raise Exception(f"折價券建立失敗，請至後台確認")
    token_booking = get_csrf_token(session)
    member_payload = get_member(session, phone_a, token_booking, clean_type_id)
    if not member_payload:
        raise Exception(f"電話 {phone_a} 查無會員資料")
    lookup_result = {"session": session, "token": token_booking, "phone": phone_a, "member_payload": member_payload, "base_url": base_url, "env_name": env_name}
    order_b_result = quick_create_order(
        env_name=env_name, payway=payway_a, region=region_a, lookup_result=lookup_result,
        address=address_a, clean_type_id=clean_type_id, date_s=new_date_s,
        period_s=new_period_s, hour=new_hour, person=new_person, discount_code=coupon_code,
        allow_auto_lemon_shift=allow_auto_lemon_shift,
    )
    order_no_b = order_b_result["order_no"]
    combo_desc = f"{new_person}人{new_hour}小時"
    note_b = f"{order_no_a}+{order_no_b} 合併{combo_desc}服務"
    note_a = f"{order_no_a}+{order_no_b} 合併{combo_desc}服務，檸檬人勿動"
    note_a_ok, note_a_msg = _update_order_note(session, base_url, order_no_a, note_a)
    note_b_ok, note_b_msg = _update_order_note(session, base_url, order_no_b, note_b)
    line_msg = build_line_message(order_b_result)
    lemon_result = assign_lemon_cleaners_to_order(
        session=session, base_url=base_url, order_no_a=order_no_a,
        service_date=service_date_a, period_s=new_period_s, person_count=new_person,
        allow_auto_lemon_shift=True,
    )
    return {
        "order_no_a": order_no_a, "order_no_b": order_no_b, "coupon_code": coupon_code,
        "lemon_result": lemon_result, "coupon_discount": coupon_discount,
        "service_date_a": service_date_a, "combo_desc": combo_desc,
        "note_a": note_a, "note_b": note_b,
        "note_a_ok": note_a_ok, "note_a_msg": note_a_msg,
        "note_b_ok": note_b_ok, "note_b_msg": note_b_msg,
        "edit_url_a": f"{base_url}/purchase/edit/{order_no_a.replace('LC00', '')}",
        "purchase_url_a": f"{base_url}/purchase?orderNo={order_no_a}",
        "line_message": line_msg, "order_b_result": order_b_result, "region": region_a,
    }


def convert_order_stage1_reassign_original(
    env_name, backend_email, backend_password, order_no_a, target_date_s=None, clean_type_id="1",
    allow_auto_lemon_shift=True,
):
    """
    訂單轉換第一階段：只處理原訂單A。把服務日期改到指定的新日期，
    再從後台當下已有的可用班表中換成檸檬人。若開啟自動補檸檬人，
    只能補當日沒有任何班別的人；已有班別的專員一律跳過。

    target_date_s 沒給的話就不改日期，只做換人為檸檬人。

    回傳的 dict 帶著第二階段（建新訂單）需要的所有資訊，第二階段直接把這個
    dict 傳進 convert_order_stage2_create_new_orders 即可，不用再重新查一次
    原訂單A。
    """
    base_url = _configure_environment(env_name)
    session = requests.Session()
    if not login(session, backend_email, backend_password):
        raise Exception("後台登入失敗，請確認帳號密碼")

    # ── Step 1: 查原訂單A ─────────────────────────────────────────
    block_a = _fetch_purchase_block_for_order_no(session, order_no_a)
    lines_a = block_a.get("lines", [])
    joined_a = "\n".join(lines_a)
    service_date_a, period_a_raw = _parse_service_date_time_loose(joined_a)
    address_a = _extract_address_line(lines_a)
    payway_a = _extract_payway_line(joined_a)
    phone_a = _extract_phone_from_block_lines(lines_a)
    region_a = get_region_by_address(address_a, ACCOUNTS) or "台北"
    fare_a = _extract_fare_line(joined_a) or "0"
    service_amount_a = _service_amount_from_block(joined_a, fare_a)
    try:
        service_amount_a_int = int(float(str(service_amount_a or "0").replace(",", "")))
    except Exception:
        service_amount_a_int = 0

    person_a = 0
    try:
        _edit_id_a = _fetch_order_edit_id(session, order_no_a)
        if _edit_id_a:
            _edit_resp_a = session.get(f"{base_url}/purchase/edit/{_edit_id_a}", headers=HEADERS, allow_redirects=True)
            if _edit_resp_a.status_code == 200:
                _pm = re.search(r'name=["\'"]person["\'"][^>]*value=["\'"]?(\d+)["\'"]?', _edit_resp_a.text, re.I)
                if not _pm:
                    _pm = re.search(r'value=["\'"]?(\d+)["\'"]?[^>]*name=["\'"]person["\'"]?', _edit_resp_a.text, re.I)
                if _pm:
                    person_a = int(_pm.group(1))
                _price_m = re.search(r'name=["\'"]price["\'"][^>]*value=["\'"]?([\d.]+)["\'"]?', _edit_resp_a.text, re.I)
                if _price_m and not service_amount_a_int:
                    try:
                        _price_no_tax = float(_price_m.group(1))
                        service_amount_a_int = int(round(_price_no_tax * 1.05))
                    except Exception:
                        pass
    except Exception:
        pass

    if not person_a:
        _person_str, _ = _extract_person_hour_line(joined_a)
        if _person_str and _person_str.isdigit():
            person_a = int(_person_str)
    if not person_a:
        person_a = 2  # 最後 fallback

    if not phone_a:
        raise Exception(f"無法從訂單 {order_no_a} 取得客人電話")
    if not address_a:
        raise Exception(f"訂單 {order_no_a} 無法取得服務地址")
    if not service_date_a:
        raise Exception(f"訂單 {order_no_a} 無法取得服務日期")

    # ── Step 2: 查會員 ────────────────────────────────────────────
    token_booking = get_csrf_token(session)
    member_payload = get_member(session, phone_a, token_booking, clean_type_id)
    if not member_payload:
        raise Exception(f"電話 {phone_a} 查無會員資料")
    lookup_result = {
        "session": session, "token": token_booking, "phone": phone_a,
        "member_payload": member_payload, "base_url": base_url, "env_name": env_name,
    }

    # ── Step 3: 原訂單A 改日期 → 用既有班表／安全補檸檬人換人 ───
    target_date_a = target_date_s or service_date_a
    period_a_for_assign = period_a_raw.replace(" ", "") if period_a_raw else ""
    pre_shift_a = {
        "success": True, "assigned": [],
        "message": "已開啟安全補檸檬人" if allow_auto_lemon_shift else "未勾選自動補檸檬人",
        "protect_other_orders": True,
    }

    date_change_ok = False
    date_change_msg = ""
    if target_date_a and target_date_a != service_date_a:
        date_change_ok, date_change_msg = _update_order_service_date(
            session, base_url, order_no_a, target_date_a, period_a_for_assign, phone=phone_a
        )
    else:
        date_change_ok = True
        date_change_msg = "日期相同，無須修改"
        target_date_a = service_date_a

    lemon_result_a = assign_lemon_cleaners_to_order(
        session=session, base_url=base_url, order_no_a=order_no_a,
        service_date=target_date_a, period_s=period_a_for_assign, person_count=str(person_a),
        allow_auto_lemon_shift=True,
    )
    lemon_result_a["date_change_ok"] = date_change_ok
    lemon_result_a["date_change_msg"] = date_change_msg
    lemon_result_a["new_service_date"] = target_date_a
    lemon_result_a["pre_shift_a"] = pre_shift_a
    if lemon_result_a.get("actual_person_count"):
        person_a = lemon_result_a["actual_person_count"]

    return {
        "order_no_a": order_no_a, "session": session, "base_url": base_url, "env_name": env_name,
        "phone_a": phone_a, "address_a": address_a, "payway_a": payway_a, "region_a": region_a,
        "person_a": person_a, "service_amount_a_int": service_amount_a_int,
        "period_a_raw": period_a_raw, "service_date_a": service_date_a,
        "target_date_a": target_date_a, "clean_type_id": clean_type_id,
        "lookup_result": lookup_result, "member_payload": member_payload,
        "lemon_result_a": lemon_result_a,
    }


def convert_order_stage2_create_new_orders(stage1_result, new_orders):
    """
    v2026.07.10：訂單轉換第二階段（跟儲值金補價差的分階段介面一致）——用
    第一階段的結果，建折價券（所有新單券額加總最多等於原訂單A服務金額，
    新單超出時保留應付差額）並建立新訂單B1/B2/B3...，最後比對「原訂單A
    的服務金額」跟「新訂單合計金額」是否有差額，有差額會在結果的 ph_warning
    裡明確標示出來，不會默默忽略。
    """
    lemon_result_a = stage1_result.get("lemon_result_a") or {}
    if not lemon_result_a.get("date_change_ok", True):
        raise Exception("原訂單A日期修改失敗，已停止建立新訂單B，請先完成第一段。")
    if not lemon_result_a.get("success"):
        raise Exception(
            "原訂單A無法用後台當下已有班表完成配班，已停止建立新訂單B。"
            "系統不會改寫已有班別或動到其他客人的專員，請先由人工處理班表。"
        )

    session = stage1_result["session"]
    base_url = stage1_result["base_url"]
    env_name = stage1_result["env_name"]
    order_no_a = stage1_result["order_no_a"]
    address_a = stage1_result["address_a"]
    payway_a = normalize_booking_payway(stage1_result["payway_a"])
    if not payway_a:
        raise Exception(
            f"原訂單付款方式解析失敗：讀到「{stage1_result.get('payway_a', '')}」。"
            "付款方式必須是信用卡、ATM、儲值金或藍新ATM。"
        )
    region_a = stage1_result["region_a"]
    clean_type_id = stage1_result["clean_type_id"]
    lookup_result = stage1_result["lookup_result"]
    member_payload = stage1_result["member_payload"]
    service_amount_a_int = stage1_result["service_amount_a_int"]
    person_a = stage1_result["person_a"]

    member = member_payload.get("member", {})
    best_addr = pick_best_address_info(member_payload, address_a)
    if not best_addr:
        raise Exception(f"找不到地址資料：{address_a}")
    selected_address = str(best_addr.get("address") or address_a).strip()
    geo_lat, geo_lng = geocode_address(selected_address)
    if geo_lat and geo_lng:
        best_addr["lat"] = geo_lat
        best_addr["lng"] = geo_lng
    token_for_calc = _get_booking_token_for_payway(session, base_url, payway_a)
    addr_check = check_contain(
        session, member.get("member_id", ""), selected_address,
        best_addr.get("lat", ""), best_addr.get("lng", ""), token_for_calc, clean_type_id,
    )
    if addr_check:
        area_info = addr_check.get("area") if isinstance(addr_check.get("area"), dict) else {}
        if area_info:
            best_addr["area_id"] = area_info.get("area_id", best_addr.get("area_id"))
            best_addr["company_id"] = area_info.get("company_id", best_addr.get("company_id"))

    today_str = date.today().strftime("%Y-%m-%d")
    new_order_results = []
    new_order_nos = []
    remaining_coupon_budget = max(int(service_amount_a_int or 0), 0)

    for idx, new_order in enumerate(new_orders):
        new_date_s = new_order["date_s"]
        new_period_s = new_order["period_s"]
        new_hour = str(new_order["hour"])
        new_person = str(new_order["person"])

        try:
            _day_type_new = _day_type_from_date(new_date_s)
            _unit_price_new = 700 if _day_type_new == "週末" else 600
            _person_hours_new = int(new_person) * int(float(new_hour))
            price_with_tax = _unit_price_new * _person_hours_new
            if price_with_tax <= 0 and payway_a != "儲值金":
                raise Exception(f"金額計算為 0（{new_person}人{new_hour}小時），請確認設定")

            coupon_prefix = f"c{order_no_a[-3:]}{idx+1}{datetime.now().strftime('%H%M%S')}"
            coupon_discount = min(price_with_tax, remaining_coupon_budget)
            coupon_code = ""
            if coupon_discount > 0:
                coupon_code = _build_coupon_via_session(
                    session, base_url,
                    title=f"訂單轉換-{order_no_a}-B{idx+1}",
                    discount=coupon_discount,
                    date_s=today_str, date_e=new_date_s,
                    prefix=coupon_prefix, piece=1,
                    regions=[region_a] if region_a else ["台北", "台中"],
                    service_items=["居家清潔", "裝修細清"],
                )
                if not coupon_code:
                    raise Exception(
                        f"折價券建立失敗：prefix={coupon_prefix}，折抵金額={coupon_discount}。"
                        "已停止建立新訂單，避免後台 /booking/single 因無效優惠碼回 500。"
                    )
                remaining_coupon_budget -= coupon_discount
            order_result = quick_create_order(
                env_name=env_name, payway=payway_a, region=region_a,
                lookup_result=lookup_result, address=address_a,
                clean_type_id=clean_type_id, date_s=new_date_s, period_s=new_period_s,
                hour=new_hour, person=new_person, discount_code=coupon_code,
                allow_auto_lemon_shift=bool(new_order.get("allow_lemon", False)),
            )
            new_order_nos.append(order_result["order_no"])

            service_due = _service_due_after_fare(session, order_result["order_no"])
            if service_due == 0:
                # v8.51：依客服確認改回來——總金額扣車馬費為 0 時，要自動標記
                # 已付款（客人已用優惠券折抵完畢，不需要再刷卡/匯款），並在
                # 發票號碼欄註記「不開立發票」，兩個動作都要做。
                mark_paid_ok, mark_paid_msg = _mark_order_as_paid(session, base_url, order_result["order_no"])
                invoice_note_ok, invoice_note_msg = _update_order_invoice_no_text(session, base_url, order_result["order_no"], "不開立發票")
            else:
                mark_paid_ok, mark_paid_msg = None, f"服務金額未歸零（總金額扣車馬費={service_due}），不自動標記已付款"
                invoice_note_ok, invoice_note_msg = False, "服務金額未歸零，不自動標註不開立發票"

            # v2026.07.10：訂單轉換的 LINE 訊息改成「原訂單A＋新訂單B 合併
            # 訂單」的格式，另起一行顯示新訂單真正的服務時間，且不顯示
            # 服務金額（僅全額折抵時隱藏；若有補差額則要保留金額）。
            _new_period_disp = _format_period_display(new_period_s.replace(" ", ""), new_person)
            order_result["merged_service_time_line"] = (
                f"服務時間 : {order_no_a}＋{order_result['order_no']}  合併訂單\n"
                f"                      實際服務時間：{new_date_s.replace('-', '/')} {_new_period_disp}"
            )
            customer_due = max(price_with_tax - coupon_discount, 0)
            order_result["hide_amount_line"] = (customer_due == 0)
            order_result["customer_due"] = customer_due

            new_order_results.append({
                "index": idx + 1, "order_no": order_result["order_no"],
                "date_s": new_date_s, "period_s": new_period_s,
                "hour": new_hour, "person": new_person,
                "price_with_tax": price_with_tax, "coupon_code": coupon_code,
                "coupon_discount": coupon_discount, "customer_due": customer_due,
                "coupon_budget_remaining": remaining_coupon_budget,
                "coupon_prefix": coupon_prefix, "assign_result": {"success": True, "message": "由後台建單時自動配班"},
                "order_result": order_result,
                "line_message": build_line_message(order_result),
                "mark_paid_ok": mark_paid_ok, "mark_paid_msg": mark_paid_msg,
                "invoice_note_ok": invoice_note_ok, "invoice_note_msg": invoice_note_msg,
                "error": None,
            })
        except Exception as e:
            new_order_results.append({
                "index": idx + 1, "date_s": new_date_s, "period_s": new_period_s,
                "hour": new_hour, "person": new_person, "order_no": None,
                "error": (
                    f"{e}\n"
                    f"🔧 第二段B{idx+1}：payway={payway_a}，coupon_prefix={locals().get('coupon_prefix', '')}，"
                    f"coupon_code={locals().get('coupon_code', '')}，coupon_discount={locals().get('coupon_discount', '')}，"
                    f"price_with_tax={locals().get('price_with_tax', '')}，remaining_coupon_budget={remaining_coupon_budget}"
                ),
            })

    # 合併 LINE 訊息（所有新訂單 B1+B2...）
    combined_line_message = ""
    try:
        b_nos_for_line = [r["order_no"] for r in new_order_results if r.get("order_no")]
        if len(b_nos_for_line) > 1:
            orders_info = []
            for ono in b_nos_for_line:
                block = _fetch_purchase_block_for_order_no(session, ono)
                lines_b = block.get("lines", [])
                joined_b = "\n".join(lines_b)
                sdate, stime = _parse_service_date_time_loose(joined_b)
                actual_t = _extract_actual_service_time(joined_b)
                p_str, _ = _extract_person_hour_line(joined_b)
                addr_b = _extract_address_line(lines_b)
                fare_b = _extract_fare_line(joined_b) or "0"
                svc_amt = _service_amount_from_block(joined_b, fare_b)
                orders_info.append({
                    "order_no": ono, "service_date": sdate, "period_s": stime,
                    "actual_period": actual_t, "person": p_str,
                    "address": addr_b or address_a,
                    "fare": fare_b, "payway": payway_a,
                    "service_amount": svc_amt, "region": region_a,
                })
            unique_dates = sorted({o["service_date"] for o in orders_info})
            all_same_date = len(unique_dates) == 1
            if all_same_date:
                period_parts = []
                _total_ph_same_date = 0
                for o in orders_info:
                    p_compact = str(o["period_s"] or "").replace(" ", "")
                    p_disp = _format_period_display(p_compact, str(o["person"] or ""))
                    period_parts.append(p_disp)
                    _info_sd = PERIOD_DISPLAY_INFO.get(p_compact)
                    if _info_sd:
                        try:
                            _h_sd = int(float(_info_sd[0].replace("小時", "")))
                            _p_sd = int(str(o["person"] or "0"))
                            _total_ph_same_date += _h_sd * _p_sd
                        except Exception:
                            pass
                combined_period = "＋".join(period_parts)
                if _total_ph_same_date and len(period_parts) > 1:
                    combined_period += f"，共{_total_ph_same_date}人時"
                multi_date = False
            else:
                period_lines = []
                for o in orders_info:
                    d = o["service_date"].replace("-", "/")
                    p_compact = str(o["period_s"] or "").replace(" ", "")
                    p_disp = _format_period_display(p_compact, str(o["person"] or ""))
                    period_lines.append(f"{d} {p_disp}")
                combined_period = "\n".join(period_lines)
                multi_date = True
            total_fare = sum(int(float(o["fare"] or "0")) for o in orders_info)
            amt_parts = [str(o["service_amount"] or "0") for o in orders_info]
            total_amt = sum(int(float(a.replace(",", ""))) for a in amt_parts if a)
            amount_display = "＋".join(amt_parts) + "＝" + str(total_amt) if len(amt_parts) > 1 else str(total_amt)
            first = orders_info[0]
            line_result = {
                "order_no": first["order_no"], "all_order_nos": b_nos_for_line,
                "address": address_a, "date": first["service_date"],
                "period": first["period_s"], "period_s": first["period_s"],
                "actual_period": first["actual_period"], "combined_period": combined_period,
                "multi_date": multi_date, "person": first["person"],
                "service_amount": amount_display, "price_with_tax": str(total_amt),
                "fare": str(total_fare) if total_fare else "0",
                "payway": payway_a, "region": region_a,
                "env_name": env_name, "session": session,
            }
            combined_line_message = build_line_message(line_result)
        elif b_nos_for_line and new_order_results:
            combined_line_message = new_order_results[0].get("line_message", "")
    except Exception as _e_line:
        combined_line_message = f"（合併 LINE 訊息產生失敗：{_e_line}）"

    # 備註文字並自動寫入
    b_nos = [r["order_no"] for r in new_order_results if r.get("order_no")]
    all_nos_str = "+".join([order_no_a] + b_nos)
    combo_desc = "、".join([f"{r['person']}人{r['hour']}小時" for r in new_order_results if r.get("order_no")])
    note_text = f"{all_nos_str} 合併服務（{combo_desc}）"
    note_a = f"{note_text}，原單配班請勿改動"
    note_a_ok, note_a_msg = _update_order_note(session, base_url, order_no_a, note_a)
    for r in new_order_results:
        if r.get("order_no"):
            _update_order_note(session, base_url, r["order_no"], note_text)

    # v2026.07.10：比對原訂單A跟新訂單合計是否有差額（客服要求的驗證步驟）
    new_amount_total = sum(int(r.get("price_with_tax", 0)) for r in new_order_results if r.get("order_no"))
    coupon_discount_total = sum(int(r.get("coupon_discount", 0)) for r in new_order_results if r.get("order_no"))
    new_ph = sum(int(r.get("person", 0)) * int(r.get("hour", 0)) for r in new_order_results if r.get("order_no"))
    ph_warning = None
    if service_amount_a_int > 0 and new_amount_total != service_amount_a_int:
        diff_amount = service_amount_a_int - new_amount_total
        ph_warning = (
            f"⚠️ 金額不符：原訂單服務金額 {service_amount_a_int} 元，"
            f"新訂單合計 {new_amount_total} 元（{' + '.join(str(r.get('price_with_tax', 0)) for r in new_order_results if r.get('order_no'))}），"
            f"折價券合計 {coupon_discount_total} 元，"
            f"差額 {abs(diff_amount)} 元（{'缺少' if diff_amount > 0 else '超出'}）。"
            f"請確認是否需要補建新訂單。"
        )

    return {
        "order_no_a": order_no_a,
        "new_order_results": new_order_results,
        "lemon_result_a": lemon_result_a,
        "note": note_text, "note_a": note_a,
        "note_a_ok": note_a_ok, "note_a_msg": note_a_msg,
        "purchase_url_a": f"{base_url}/purchase?orderNo={order_no_a}",
        "all_nos_str": all_nos_str,
        "success_count": len([r for r in new_order_results if r.get("order_no")]),
        "fail_count": len([r for r in new_order_results if not r.get("order_no")]),
        "ph_warning": ph_warning,
        "service_amount_a_display": service_amount_a_int,
        "new_amount_total": new_amount_total,
        "coupon_discount_total": coupon_discount_total,
        "coupon_budget_remaining": remaining_coupon_budget,
        "new_ph": new_ph,
        "person_a_count": person_a,
        "combined_line_message": combined_line_message,
    }


def convert_order_multi(
    env_name, backend_email, backend_password, order_no_a, new_orders, clean_type_id="1",
    allow_auto_lemon_shift=False,
):
    """
    v2026.07.10：保留原本「一次到位」的介面給舊呼叫端相容用，內部直接組合
    stage1 + stage2（畫面已改用分階段版本，見 convert_order_stage1_
    reassign_original / convert_order_stage2_create_new_orders）。
    """
    new_dates = sorted([o.get("date_s", "") for o in new_orders if o.get("date_s")])
    target_date_a = new_dates[0] if new_dates else None
    stage1 = convert_order_stage1_reassign_original(
        env_name, backend_email, backend_password, order_no_a, target_date_a, clean_type_id,
    )
    return convert_order_stage2_create_new_orders(stage1, new_orders)


# =========================================================
# LINE 訊息 & 確認信
# =========================================================

def send_confirmation(order_result):
    session = order_result["session"]
    order_no = order_result["order_no"]
    return send_confirmation_mail(session, order_no)


def build_line_message(order_result):
    # v2026.07.06 修正：原本這裡不管實際訂什麼服務，LINE 訊息一律寫死
    # 「【居家清潔】」。現在改成依 clean_type_id 動態代入正確的服務名稱。
    # 目前確定的對應（跟畫面 CLEAN_TYPE_ID_MAP / orders.py CLEAN_TYPE_MAP 一致）：
    # 1=居家清潔，2=辦公室清潔，3=裝修細清。搬出清潔／搬入清潔目前的 clean_type_id
    # 還沒跟 Jenny 確認過實際數值，先保留在對照表裡用文字 key 備用；如果之後
    # 這兩種服務也會走到這個 LINE 訊息組裝流程，麻煩告訴我對應的 id，我再補上。
    CLEAN_TYPE_NAME_MAP = {
        "1": "居家清潔", "2": "辦公室清潔", "3": "裝修細清",
    }
    service_label = (
        order_result.get("service_label")
        or CLEAN_TYPE_NAME_MAP.get(str(order_result.get("clean_type_id") or ""), "居家清潔")
    )
    payway = order_result["payway"]
    region = order_result["region"]
    date_disp = order_result["date"].replace("-", "/")
    combined_period = str(order_result.get("combined_period", "") or "")
    if combined_period:
        period = combined_period
    else:
        period_raw = str(order_result.get("period_s") or order_result.get("period", "")).replace(" ", "")
        actual_period = str(order_result.get("actual_period", "") or "")
        person_cnt = str(order_result.get("person", "") or "")
        period = _format_period_display(period_raw, person_cnt, display_override=actual_period)
    price = order_result.get("service_amount") or order_result.get("price_with_tax", order_result.get("price"))
    # v8.49：訂單轉換／儲值金補價差用優惠券折抵後，LINE 訊息裡「服務金額」
    # （信用卡）跟「轉帳金額」（ATM）這兩行原本都還是顯示折抵前的原始訂單
    # 金額（例如客付單已用優惠券折掉大半，畫面卻還是要客人匯全額），改成
    # 只要呼叫端有算出 customer_due（折抵後客人實際要付的金額），這兩行都
    # 一律改顯示 customer_due，不再顯示折抵前的原始金額。
    if order_result.get("customer_due") is not None:
        price = order_result.get("customer_due")
    # v8.51：折抵後金額為 0 時（已用優惠券全額折抵完畢），LINE 訊息不該再
    # 顯示信用卡刷卡連結或 ATM 匯款帳號資訊，避免客人誤會還要再付一次錢。
    try:
        fully_covered = float(str(price or "0").replace(",", "")) == 0
    except Exception:
        fully_covered = False
    fare = order_result["fare"]
    address = order_result["address"]
    order_no = order_result["order_no"]
    multi_date = order_result.get("multi_date", False)
    if multi_date and combined_period:
        service_time_line = f"服務時間 :\n{period}"
    else:
        service_time_line = f"服務時間 : {date_disp}  {period}"
    # v2026.07.10：訂單轉換／儲值金補價差用的「合併訂單」專用格式，蓋掉上面
    # 一般單筆訂單算出的 service_time_line（訂單編號合併＋另起一行實際服務
    # 時間），由呼叫端組好整段文字傳進來。
    if order_result.get("merged_service_time_line"):
        service_time_line = order_result["merged_service_time_line"]
    # v2026.07.10：訂單轉換的合併訂單 LINE 訊息不需要「服務金額」這行
    # （新訂單本身是用優惠券折抵成 0，顯示金額反而容易讓客人誤會），
    # 只有信用卡分支才有獨立的「服務金額」行，ATM 分支本來就是用
    # 「轉帳金額」表示要匯款的金額，跟這裡的服務金額行是兩回事，不受影響。
    show_amount_line = not order_result.get("hide_amount_line", False)
    if show_amount_line:
        amount_line_text = (order_result.get("custom_amount_line") or f"服務金額：{price}（含稅）") + "\n"
    else:
        amount_line_text = ""
    order_last6 = order_no[-6:] if len(order_no) >= 6 else order_no
    try:
        has_fare = float(str(fare or "0").replace(",", "")) != 0
    except Exception:
        has_fare = bool(str(fare or "").strip())
    vip_fare_line = f"車馬費：{fare}\n" if has_fare else ""
    card_fare_line = f"車馬費：{fare}（請現場支付給專員）\n" if has_fare else ""
    taipei_atm_fare_line = f"車馬費：{fare}（請現場支付給專員）\n" if has_fare else ""
    taichung_atm_fare_line = f"\n車馬費:{fare}（請現場支付給專員）" if has_fare else ""
    common_footer = """**當您完成付款後即表示服務已完成預約，
預約完成後，即代表您同意接受檸檬專業清潔公司 服務條款 及 隱私權政策。
請詳閱服務條款及隱私權相關說明 https://www.lemonclean.com.tw/terms
＊若現場溝通時確認無法於服務時間內完成服務需求，會請您排優先順序，以時間內可以完成的區域為主。
＊窗戶獨立於各區域單獨計算，拆紗窗不拆玻璃，含窗溝及窗框及內側，若外側無法安全站立則以手能擦拭範圍為主。
＊夏季天氣炎熱，若情況充許請提供電扇或冷氣供專員使用，謝謝。
＊若超過服務時間，則會以加時費用計算。
若訂購後有上述情事請主動連繫檸檬家事官方LINE@，謝謝。"""
    cancel_policy = """**異動/取消服務注意事項
凡訂單成立付款後，若異動日期或取消服務異動手續費如下
 **工作日不含例假日且以上班時間計之，超過 17:30 算下個工作日。
◎服務日3個工作天前，取消酌收訂單5%手續費。
◎服務日2-3個工作天內，取消或更改酌收訂單30%手續費。
◎服務日1個工作天內，取消或更改酌收訂單50%手續費。"""
    if payway == "儲值金":
        # v8.62：跨日期合併時 period（combined_period）已經是
        # 「日期＋時段」逐行排列，不能再於前方加 date_disp，否則第一筆日期
        # 會重複成「2026/09/15 2026/09/15 ...」。同日合併與單筆維持原格式。
        if multi_date and combined_period:
            stored_value_service_time_line = f"服務時間：{period}"
        else:
            stored_value_service_time_line = f"服務時間：{date_disp} {period}"
        return f"""感謝您預約檸檬家事【{service_label}】服務
{stored_value_service_time_line}
服務地址：{address}

{vip_fare_line}檸檬家事專員會於現場再溝通服務需求，
以於系統估算時間內可以完的服務項目為主。
預約完成後，即代表您同意接受檸檬專業清潔公司 服務條款 及 隱私權政策。
請詳閱服務條款及隱私權相關說明 https://www.lemonclean.com.tw/terms

建議您可以至會員中心》訂單查詢 確認喔
https://www.lemonclean.com.tw/login
帳號：email；密碼：手機號碼
＊即日起本站暫停做防疫調查，為保障客戶及專員安全，若確診請於服務前日主動告知，否則需付異動費喔
若訂購後有上述情事請主動連繫檸檬家事官方LINE@，謝謝。

VIP客戶
◎異動費
VIP若取消/異動服務日期，需於服務日前4個工作天上班時間(不含例假日，17:30後算下個工作日)告知。
若於服務前2-3個工作日告知，則收取每2人1小時異動費200元；
若於服務前1個工日(含服務當天)告知，則收取每2人1小時異動費300元。"""
    if payway == "信用卡":
        all_order_nos = order_result.get("all_order_nos") or [order_no]
        if len(all_order_nos) > 1:
            link_lines = []
            for i, ono in enumerate(all_order_nos, start=1):
                last6 = ono[-6:] if len(ono) >= 6 else ono
                link_lines.append(f"訂單{i}：https://www.lemonclean.com.tw/order/{last6}")
            payment_links = "\n".join(link_lines)
        else:
            payment_links = f"https://www.lemonclean.com.tw/order/{order_last6}"
        if fully_covered:
            deadline_line = "本次費用已由優惠券全額折抵，無需另行付款。"
            payment_block = ""
        else:
            deadline_line = "※麻煩您於『明天 24:00前』完成付款，為保留他人訂購權利，逾期付款訂單將自動取消"
            payment_block = f"""線上刷卡流程:
{payment_links}
登入會員
帳號：email；密碼：手機號碼
在訂單點選付款狀態點選『重新付款』即可

"""
        return f"""感謝您於 檸檬家事 預約【{service_label}】服務！
{service_time_line}
{amount_line_text}{card_fare_line}服務地址：{address}
{deadline_line}

{common_footer}

{payment_block}{cancel_policy}"""
    if payway == "ATM":
        if region == "台北":
            bank_block = """銀行戶名：檸檬專業清潔有限公司
銀行代碼 台北富邦銀行(012)-松高分行
銀行帳號 7091-2000-3320"""
            extra_note = """*發票於付款完成後24小時之內會開立並寄至Email，屆時麻煩查收或是檢查垃圾郵件。
*匯款完成後再請您提供您的匯款帳號後5碼，以供檸檬家事為您核對帳款。
"""
        else:
            bank_block = """銀行戶名：泳檬有限公司
銀行代碼 台北富邦銀行(012)-營業部
銀行帳號 00200102520512"""
            extra_note = ""
        atm_pay_title = "▲請您依下列匯款帳戶資訊繳費，謝謝！" if region == "台北" else "請您依下列匯款帳戶資訊繳費，謝謝！"
        extra_note_block = f"\n{extra_note}" if extra_note else ""
        service_lines = (
            f"{service_time_line}\n{taipei_atm_fare_line}服務地址：{address}"
            if region == "台北"
            else f"{service_time_line}\n服務地址：{address}{taichung_atm_fare_line}"
        )
        if fully_covered:
            atm_deadline_line = "本次費用已由優惠券全額折抵，無需另行匯款。"
            pay_section = ""
            extra_note_block_final = ""
        else:
            atm_deadline_line = "※麻煩您於『明天 24:00前』完成付款，為保留他人訂購權利，逾期付款訂單將自動取消"
            pay_section = f"""{atm_pay_title}
{bank_block}
轉帳金額  {price}元（含營業稅）

"""
            extra_note_block_final = extra_note_block
        return f"""感謝您於 檸檬家事 預約【{service_label}】服務！
{service_lines}
{atm_deadline_line}

{common_footer}

{pay_section}訂單可以登入『會員中心』查詢確認
https://www.lemonclean.com.tw/login
帳號：email；密碼：手機號碼
{extra_note_block_final}
{cancel_policy}"""
    raise Exception(f"未知付款方式: {payway}")


def _extract_stored_value_purchase_info(joined_text):
    """
    v8.19：偵測這張訂單是不是「儲值金購買/儲值」訂單——客人自己買/儲值一筆
    金額本身（用信用卡或ATM付款），跟「使用既有儲值金折抵一般清潔服務」是
    完全不同的兩件事，後者才是 payway == "儲值金" 的情況。
    直接從訂單內容裡「儲值金-台北(儲值金50,000贈購物金2,500)」這段文字解析出
    區域、金額、贈送購物金，不使用寫死的金額對照表，任何金額組合都能正確解析。
    不是儲值金購買訂單時回傳 (None, None, None)。
    """
    m = re.search(r"儲值金[-－]?\s*([\u4e00-\u9fff]+)\s*[（(]\s*儲值金\s*([\d,]+)\s*贈購物金\s*([\d,]+)", joined_text)
    if not m:
        return None, None, None
    region_raw = m.group(1).strip()
    try:
        amount = int(m.group(2).replace(",", ""))
        bonus = int(m.group(3).replace(",", ""))
    except Exception:
        return None, None, None
    return region_raw, amount, bonus


def build_stored_value_purchase_message(order_no, payway, region, amount, bonus):
    """
    v8.19：儲值金「購買/儲值」訂單專用 LINE 訊息範本（信用卡／ATM-台北／
    ATM-台中三種），跟一般清潔服務訂單的 build_line_message 是分開的，因為
    這種訂單沒有服務日期/地址，內容也完全不同。
    amount / bonus 直接來自訂單本身解析出的實際金額，非寫死對照表。
    """
    order_last6 = order_no[-6:] if len(order_no) >= 6 else order_no
    order_link = f"https://www.lemonclean.com.tw/order/{order_last6}"

    if payway == "信用卡":
        return f"""已為您成立儲值金訂單
儲值金額：{amount}元
贈購物金：{bonus}元(自付款日起2年內有效，逾期失效)

＊即日起本站暫停做防疫調查，為保障客戶及專員安全，若確診請於服務前日主動告知，否則需付異動費喔
若訂購後有上述情事請主動連繫檸檬家事官方LINE@，謝謝。

線上刷卡流程:
{order_link}
登入會員
帳號：email；密碼：手機號碼
在訂單點選付款狀態點選『重新付款』即可

付款完成後，即代表您同意接受檸檬專業清潔公司 服務條款 及 隱私權政策 及 VIP政策。
請詳閱服務條款及隱私權相關說明 https://www.lemonclean.com.tw/terms

檸檬家事專員會於現場再溝通服務需求，
以於系統估算時間內可以完的服務項目為主。

VIP客戶
◎異動費
VIP若取消/異動服務日期，需於服務日前4個工作日(不含例假日，17:30算下個工作日)告知。
若於服務前2-3個工作日告知，則收取每2人1小時異動費200元；
若於服務前1個工作日(含服務當天)告知，則收取每2人1小時異動費300元。"""

    if payway == "ATM":
        # v8.20：台北／台中的儲值金購買 ATM 範本結構完全一樣，只有匯款帳戶
        # 資訊不同，改成共用同一個骨架、只換銀行區塊，避免兩份文案各自維護
        # 容易漏改或打錯字。轉帳金額那行的空格數量依各區客服提供的原文保留，
        # 不強制統一。
        if region == "台北":
            bank_block = (
                "銀行戶名：檸檬專業清潔有限公司\n"
                "銀行代碼 台北富邦銀行(012)-松高分行\n"
                "銀行帳號 7091-2000-3320"
            )
            amount_line = f"轉帳金額  {amount}元（含營業稅）"
        elif region == "台中":
            bank_block = (
                "銀行戶名：泳檬有限公司\n"
                "銀行代碼 台北富邦銀行(012)-營業部\n"
                "銀行帳號 00200102520512"
            )
            amount_line = f"轉帳金額  {amount} 元（含營業稅）"
        else:
            bank_block = None
            amount_line = None

        if bank_block:
            return f"""已為您成立儲值金訂單
儲值金額：{amount}元
贈購物金：{bonus}元(自付款日起2年內有效，逾期失效)

＊即日起本站暫停做防疫調查，為保障客戶及專員安全，若確診請於服務前日主動告知，否則需付異動費喔
若訂購後有上述情事請主動連繫檸檬家事官方LINE@，謝謝。

請您依下列匯款帳戶資訊繳費，謝謝！
{bank_block}
{amount_line}

付款完成後，即代表您同意接受檸檬專業清潔公司 服務條款 及 隱私權政策 及 VIP政策。
請詳閱服務條款及隱私權相關說明 https://www.lemonclean.com.tw/terms

檸檬家事專員會於現場再溝通服務需求，
以於系統估算時間內可以完的服務項目為主。

VIP客戶
◎異動費
VIP若取消/異動服務日期，需於服務日前4個工作天上班時間(不含例假日)告知。
若於服務前2-3個工作天告知，則收取每2人1小時異動費200元；
若於服務前1個工作天內(含服務當天)告知，則收取每2人1小時異動費300元。"""

    # 其他區域或付款方式組合，目前沒有現成文案，回傳提示字串並附上解析到的金額，
    # 提醒客服人工確認/補上正確文案，而不是送出格式錯誤的訊息。
    return (
        f"⚠️ 尚未提供「{payway}／{region}」的儲值金訂單專用文案，請人工確認/補上正確文案。\n\n"
        f"訂單編號：{order_no}\n儲值金額：{amount}元\n贈購物金：{bonus}元"
    )


# =========================
# v8.21：儲值金購買自動建單（對應後台 /booking/stored_value「代客預訂-VIP儲值金」頁面）
# =========================
STORED_VALUE_COMPANY_MAP = {"台北": "1", "桃園": "2", "新竹": "3", "台中": "4"}

# 對照後台 /booking/stored_value 頁面「儲值金」下拉選單，金額與贈送購物金
# 一一對應，用於自動判斷贈購物金金額，不用等訂單建立後再回頭解析。
STORED_VALUE_OPTIONS = {
    20000: 800,
    50000: 2500,
    9900: 0,
    17000: 0,
    18900: 0,
    19400: 0,
    36000: 0,
}


def _empty_invoice_info():
    return {
        "invoice_type": "", "carrier_type_id": "", "carrier_info": "",
        "company_title": "", "company_no": "", "donate_code": "",
    }


PROFESSIONAL_CLEANING_LABELS = ["居家清潔", "辦公室清潔", "裝修細清", "大掃除", "搬出清潔", "搬入清潔"]


def _classify_order_block_type(lines):
    """
    v8.23：判斷一張訂單卡片是「VIP購買」「儲值金購買」「專業清潔」還是其他
    （家電清潔/傢俱清潔/整理收納等，不在儲值金購買發票來源的搜尋範圍內）。
    直接鎖定「建立時間」那一行的下一行（也就是購買項目那一行），避免誤抓到
    客服備註/財務備註裡出現的「VIP若取消...」等文字（那些是備註內容，不是
    購買項目）。
    """
    joined = "\n".join(lines)
    m = re.search(r"\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\s*\n\s*([^\n]+)", joined)
    item_line = m.group(1).strip() if m else ""
    if re.search(r"儲值金[-－]", item_line):
        return "stored_value_purchase"
    if "VIP" in item_line:
        return "vip_purchase"
    if any(label in item_line for label in PROFESSIONAL_CLEANING_LABELS):
        return "professional_cleaning"
    return "other"


def _is_paid_block(joined_text):
    """v8.23：只有「付款狀態：已付款」的訂單，才能拿來當付款方式/發票設定的範本。"""
    return bool(re.search(r"付款狀態[：:]\s*已付款", joined_text))


def _parse_invoice_details_from_block(lines):
    """
    v8.21：從訂單卡片文字列表解析發票設定明細，用於「儲值金購買」自動建單時
    沿用會員過去訂單的發票設定。
    """
    for i, line in enumerate(lines):
        if line.startswith("三聯式"):
            company_title = lines[i + 1].strip() if i + 1 < len(lines) else ""
            company_no = lines[i + 2].strip() if i + 2 < len(lines) else ""
            info = _empty_invoice_info()
            info.update({"invoice_type": "3", "company_title": company_title, "company_no": company_no})
            return info
        if line.startswith("二聯式"):
            rest = re.split(r"[：:]", line, maxsplit=1)[-1].strip()
            info = _empty_invoice_info()
            info["invoice_type"] = "2"
            if "會員載具" in rest:
                info["carrier_type_id"] = "1"
            elif "手機載具" in rest:
                info["carrier_type_id"] = "2"
                # v8.30：手機條碼載具本來就是「/」開頭的格式（例如 /HWHMPF6），
                # 送出去的 carrier_info 要保留這個「/」，不能只取後面的字元。
                m = re.search(r"(/\s*[A-Za-z0-9.\-]+)", rest)
                info["carrier_info"] = re.sub(r"\s+", "", m.group(1)) if m else ""
            elif "自然人憑證" in rest:
                info["carrier_type_id"] = "3"
                m = re.search(r"(/\s*[A-Za-z0-9]+)", rest)
                info["carrier_info"] = re.sub(r"\s+", "", m.group(1)) if m else ""
            elif "紙本" in rest:
                info["carrier_type_id"] = "4"
            return info
        if line.startswith("捐贈"):
            m = re.search(r"(\d{4,})", line)
            info = _empty_invoice_info()
            info.update({"invoice_type": "1", "donate_code": m.group(1) if m else "8585"})
            return info
    return _empty_invoice_info()


def _extract_block_created_at(lines):
    """從訂單卡片文字裡取出「建立時間」（YYYY-MM-DD HH:MM:SS），用於比較新舊。"""
    joined = "\n".join(lines)
    m = re.search(r"\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}", joined)
    return m.group(0) if m else ""


def _query_purchase_blocks_by_phone_buy_paid(session, phone_norm, buy_value, label, debug):
    """
    v8.26：直接用後台「購買項目」(buy) + 「付款狀態」(purchase_status=已付款)
    伺服器端篩選查詢，取代原本「只篩電話、查全部訂單再自己分類」的做法。
    原本的做法在訂單量大的客戶身上會踩雷：後台訂單列表預設一頁只有 20 筆，
    如果只用電話篩選（沒有指定購買項目），常下單的客戶很容易一頁就被一般
    清潔訂單佔滿，真正要找的 VIP／儲值金購買訂單被擠到第二頁以後，
    程式只抓第一頁，就會誤判成「查無資料」。
    改用 buy 篩選之後，查詢結果只會有這個類別的訂單，不會被分頁排擠掉。
    buy_value: "vip"=VIP券、"5"=儲值金、"1"=專業清潔（對應後台搜尋表單選項）。
    """
    try:
        params = dict(PURCHASE_FILTER_PARAMS_TEMPLATE)
        params["phone"] = phone_norm
        params["buy"] = buy_value
        params["purchase_status"] = "1"  # 已付款，直接讓後台篩掉未付款/取消/退款的訂單
        resp = session.get(orders.PURCHASE_URL, params=params, headers=HEADERS, allow_redirects=True)
    except Exception as e:
        debug["queries"].append({"label": label, "error": str(e), "count": 0})
        return []
    if resp.status_code != 200:
        debug["queries"].append({"label": label, "http_status": resp.status_code, "count": 0})
        return []
    blocks = extract_order_cards_from_purchase_html(resp.text)
    debug["queries"].append({
        "label": label, "http_status": resp.status_code, "count": len(blocks),
        "order_nos": [b.get("order_no", "") for b in blocks],
    })
    return blocks


def _pick_block_with_real_payway(blocks_sorted_by_recency, debug=None, label=""):
    """
    v8.27：從依時間排序（新到舊）的候選訂單卡片裡，挑出「第一筆付款方式是
    真正 ATM/信用卡」的訂單，跳過付款方式是「儲值金」的訂單。
    「專業清潔」這類一般服務訂單，很可能是用既有儲值金餘額折抵消費（付款
    方式＝儲值金），這種訂單不是真的刷卡/匯款付款，也不會有發票（發票在
    當初儲值購買時就已經開立過了），不能拿來當儲值金購買訂單的付款方式/
    發票範本。如果只挑「最新一筆」，剛好抓到這種儲值金折抵的訂單就會誤判。
    """
    skipped = []
    for block in blocks_sorted_by_recency:
        joined = "\n".join(block.get("lines", []))
        payway = _extract_payway_line(joined)
        if payway in ("信用卡", "ATM"):
            if debug is not None and skipped:
                debug.setdefault("skipped_stored_value_payway", []).extend(
                    [{"label": label, "order_no": o} for o in skipped]
                )
            return block
        skipped.append(block.get("order_no", ""))
    if debug is not None and skipped:
        debug.setdefault("skipped_stored_value_payway", []).extend(
            [{"label": label, "order_no": o} for o in skipped]
        )
    return None


def _find_payway_invoice_source_for_stored_value(session, phone_norm):
    """
    v8.28：依客服指定的優先順序，嚴格依序查詢這支電話用來建立「儲值金購買」
    訂單時應該沿用的付款方式與發票設定（不是把類別混在一起比日期，是一個
    類別完全查不到才換下一個類別）：
    1. 購買項目是「儲值金」、且付款狀態是「已付款」的訂單裡最近一次的那一筆。
    2. 查不到，才查購買項目是「VIP」、且付款狀態是「已付款」的訂單裡最近
       一次的那一筆。
    3. 還是查不到，才查購買項目是「專業清潔」、且付款狀態是「已付款」的
       訂單裡最近一次的那一筆。
    4. 都找不到則回傳空白，交由客服手動確認，不會默默送出錯誤的付款/發票設定。

    每個類別裡都只採用付款方式真的是「信用卡」或「ATM」的訂單（用
    _pick_block_with_real_payway 依時間新到舊挑選，跳過付款方式是「儲值金」
    的訂單——那種是用既有餘額折抵消費，沒有真正付款方式也沒有發票，不能
    拿來當範本；如果該類別裡最新一筆剛好是儲值金折抵，會繼續往下找同類別
    裡次新、且付款方式是信用卡/ATM 的那一筆，而不是直接放棄整個類別）。

    改用後台「購買項目」+「付款狀態」伺服器端篩選直接查（不再自己抓全部
    訂單分類），避免訂單量大的客戶被分頁排擠掉查不到；同時回傳 debug
    資訊（每個類別查了幾筆、有哪些訂單編號、跳過了哪些儲值金折抵的訂單），
    查無資料時可以直接顯示，不用再靠反覆截圖排查。
    """
    debug = {"queries": [], "error": ""}

    def _query_and_pick(buy_value, label):
        blocks = _query_purchase_blocks_by_phone_buy_paid(session, phone_norm, buy_value, f"{label}（已付款）", debug)
        blocks.sort(key=lambda b: _extract_block_created_at(b.get("lines", [])), reverse=True)
        return _pick_block_with_real_payway(blocks, debug=debug, label=label)

    chosen_block = _query_and_pick("5", "儲值金")
    if not chosen_block:
        chosen_block = _query_and_pick("vip", "VIP券")
    if not chosen_block:
        chosen_block = _query_and_pick("1", "專業清潔")

    if not chosen_block:
        return {"payway": ""}, _empty_invoice_info(), debug

    joined = "\n".join(chosen_block.get("lines", []))
    payway = _extract_payway_line(joined)
    invoice_info = _parse_invoice_details_from_block(chosen_block.get("lines", []))
    debug["chosen_order_no"] = chosen_block.get("order_no", "")
    return {"payway": payway}, invoice_info, debug


def _fetch_latest_stored_value_order_no(session, phone_norm, amount):
    """
    v8.21：建立儲值金購買訂單後，回查這支電話最新一筆對應金額的訂單編號。
    """
    try:
        params = dict(PURCHASE_FILTER_PARAMS_TEMPLATE)
        params["phone"] = phone_norm
        resp = session.get(orders.PURCHASE_URL, params=params, headers=HEADERS, allow_redirects=True)
    except Exception:
        return None
    if resp.status_code != 200:
        return None
    for block in extract_order_cards_from_purchase_html(resp.text):
        joined = "\n".join(block.get("lines", []))
        _region, _amount, _bonus = _extract_stored_value_purchase_info(joined)
        if _amount == int(amount):
            return block.get("order_no")
    return None


def create_stored_value_purchase_order(
    env_name, backend_email, backend_password, phone, stored_value_amount,
    region, frequency="1", notice="",
):
    """
    v8.21：新增「儲值金購買」自動建單功能，對應後台 /booking/stored_value
    （代客預訂-VIP儲值金）頁面。

    region: "台北"/"桃園"/"新竹"/"台中"——對應登入帳號所屬地區（登入哪個地區
    的後台帳號，就用哪個地區，不用另外選）。

    付款方式/發票資訊依客服指定的優先順序自動判斷：
    1. 這支電話最近一次 VIP 購買或儲值金購買訂單的設定。
    2. 都找不到才用最近一次一般服務訂單的設定。
    3. 都找不到就不會自動送出（need_manual_confirm=True），交由客服人工確認
       付款方式與發票後，至後台手動建立這筆訂單。

    成功建立後會嘗試用 build_stored_value_purchase_message 產生對應的 LINE
    通知訊息（信用卡／ATM-台北／ATM-台中，其餘地區目前沒有現成文案）。
    """
    base_url = _configure_environment(env_name)
    session = requests.Session()
    if not login(session, backend_email, backend_password):
        raise Exception("後台登入失敗，請確認帳號密碼")

    company_id = STORED_VALUE_COMPANY_MAP.get(region, "")
    if not company_id:
        raise Exception(f"未知地區：{region}")

    resp = session.get(f"{base_url}/booking/stored_value", headers=HEADERS, allow_redirects=True)
    if resp.status_code != 200:
        raise Exception(f"無法開啟儲值金購買頁面：HTTP {resp.status_code}")
    soup = BeautifulSoup(resp.text, "html.parser")
    token_input = soup.find("input", {"name": "_token"})
    token = token_input.get("value", "").strip() if token_input else ""
    if not token:
        raise Exception("無法取得 _token")

    phone_norm = normalize_phone(phone)
    member_payload = get_member(session, phone_norm, token, "0")
    if not member_payload:
        raise Exception(f"會員不存在：{phone_norm}，請確認手機號碼")
    member = member_payload.get("member", {})
    member_id = member.get("member_id", "")
    if not member_id:
        raise Exception("查詢會員成功但缺少 member_id")

    payway_source, invoice_source, search_debug = _find_payway_invoice_source_for_stored_value(session, phone_norm)
    payway_map = {"信用卡": "1", "ATM": "2"}
    payway_code = payway_map.get(payway_source.get("payway", ""), "")

    if not payway_code or not invoice_source.get("invoice_type"):
        return {
            "success": False,
            "need_manual_confirm": True,
            "phone": phone_norm, "member_id": member_id,
            "stored_value_amount": stored_value_amount,
            "region": region,
            "message": (
                "查無此會員過去 VIP／儲值金／一般服務訂單可用的付款方式或發票設定，"
                "請人工確認付款方式與發票後，至後台手動建立這筆儲值金訂單。"
            ),
            "search_debug": search_debug,
            "session": session, "env_name": env_name,
        }

    post_data = {
        "_token": token,
        "storedValue": str(stored_value_amount),
        "phone": phone_norm,
        "memberId": str(member_id),
        # v8.29：後台表單裡「會員姓名/會員帳號/市內電話」雖然是唯讀欄位，
        # 但仍然是 name="name"/"email"/"tel" 的 input，送出表單時一樣會帶上；
        # 之前漏加這幾個欄位，導致建出來的儲值金購買訂單完全沒有姓名/Email。
        "name": member.get("name", "") or "",
        "email": member.get("email", "") or "",
        "tel": member.get("tel", "") or "",
        "companyId": company_id,
        "frequency": str(frequency),
        "notice": notice or "",
        "memoFinance": member.get("memo_finance", "") or "",
        "payway": payway_code,
        "invoice_type": invoice_source["invoice_type"],
    }
    if invoice_source["invoice_type"] == "1":
        post_data["donate_code"] = invoice_source.get("donate_code") or "8585"
    elif invoice_source["invoice_type"] == "2":
        carrier_type_id = invoice_source.get("carrier_type_id", "")
        carrier_info = invoice_source.get("carrier_info", "")
        if carrier_type_id == "1" and not carrier_info:
            carrier_info = member.get("email", "") or ""
        post_data["carrier_type_id"] = carrier_type_id
        post_data["carrier_info"] = carrier_info
    elif invoice_source["invoice_type"] == "3":
        post_data["company_title"] = invoice_source.get("company_title", "")
        post_data["company_no"] = invoice_source.get("company_no", "")

    resp2 = session.post(f"{base_url}/booking/stored_value", data=post_data, headers=HEADERS, allow_redirects=True)
    if resp2.status_code not in (200, 302):
        raise Exception(f"建立儲值金訂單失敗：HTTP {resp2.status_code}")

    time.sleep(1.5)
    order_no = _fetch_latest_stored_value_order_no(session, phone_norm, stored_value_amount)
    bonus = STORED_VALUE_OPTIONS.get(int(stored_value_amount), 0)

    line_message = ""
    if order_no:
        line_message = build_stored_value_purchase_message(
            order_no, payway_source.get("payway", ""), region, int(stored_value_amount), bonus,
        )

    return {
        "success": True,
        "order_no": order_no, "phone": phone_norm, "member_id": member_id,
        "stored_value_amount": int(stored_value_amount), "bonus": bonus,
        "payway": payway_source.get("payway", ""),
        "invoice_type": invoice_source.get("invoice_type", ""),
        "carrier_type_id": invoice_source.get("carrier_type_id", ""),
        "carrier_info": invoice_source.get("carrier_info", ""),
        "company_title": invoice_source.get("company_title", ""),
        "company_no": invoice_source.get("company_no", ""),
        "region": region, "company_id": company_id,
        "line_message": line_message,
        "search_debug": search_debug,
        "env_name": env_name, "session": session,
    }


_WEEKDAY_ZH = ["一", "二", "三", "四", "五", "六", "日"]


def fetch_rating_next_appointments(env_name, backend_email, backend_password, date_s, date_e, max_pages=30):
    """
    v2026.07.07 新功能：整理「預約下次服務」名單。
    查詢 /rating（評價管理）在指定評價日期區間內、有勾選「預約下次服務」的評價，
    針對每一筆有填「預約下一次服務時間」的評價，再回頭查詢被評價的那筆訂單本身
    （訂單編號），抓出電話/地址/服務日期時間/服務人數，組出：
    評價日期／姓名／電話／地址／預約下次日期／預約下次時間／服務日期及時間／服務人數
    這一整排資訊，供客服彙整「下次要主動聯繫/確認」的名單。
    """
    base_url = _configure_environment(env_name)
    session = requests.Session()
    if not login(session, backend_email, backend_password):
        raise Exception("後台登入失敗，請確認帳號密碼")

    # v2026.07.07 修正：後台 /rating 的 date_e 篩選似乎是用「當天 00:00:00」
    # 去比對評價的完整時間戳記，導致迄日當天稍晚時間評價的紀錄（例如
    # 2026-07-06 09:44:14）被排除在外，等於實際上少抓了迄日當天的資料。
    # 這裡改成送給後台的 date_e 多加一天當緩衝，抓到的資料再用本地端解析
    # 出來的實際評價日期，重新過濾回使用者真正要的日期區間，避免因為這個
    # 緩衝多抓到超出範圍的資料。
    _query_date_e = date_e
    if date_e:
        try:
            _y, _m, _d = [int(x) for x in date_e.split("-")]
            _query_date_e = (date(_y, _m, _d) + timedelta(days=1)).strftime("%Y-%m-%d")
        except Exception:
            _query_date_e = date_e

    rows = []
    for page in range(1, max_pages + 1):
        resp = session.get(
            f"{base_url}/rating",
            params={"date_s": date_s or "", "date_e": _query_date_e or "", "next_time": "on", "page": page},
            headers=HEADERS, allow_redirects=True,
        )
        if resp.status_code != 200:
            break
        soup = BeautifulSoup(resp.text, "html.parser")
        table = soup.find("table")
        if not table:
            break
        trs = table.find("tbody").find_all("tr") if table.find("tbody") else []
        if not trs:
            break
        for tr in trs:
            cells = tr.find_all("td")
            if len(cells) < 3:
                continue
            name_cell, content_cell, date_cell = cells[0], cells[1], cells[2]
            name_link = name_cell.find("a", href=re.compile(r"/member\?keyword="))
            order_link = name_cell.find("a", href=re.compile(r"/purchase\?keyword="))
            name = name_link.get_text(strip=True) if name_link else ""
            order_no = order_link.get_text(strip=True) if order_link else ""
            rating_date_text = date_cell.get_text(strip=True)
            rating_date = rating_date_text.split(" ")[0] if rating_date_text else ""

            # 因為送給後台的 date_e 多加了一天緩衝，這裡要用實際評價日期
            # 把超出使用者原本要求範圍的紀錄擋掉，避免多抓到隔天的資料。
            if date_s and rating_date and rating_date < date_s:
                continue
            if date_e and rating_date and rating_date > date_e:
                continue

            content_text = content_cell.get_text(" ", strip=True)
            m = re.search(r"預約下一次服務時間[：:]\s*(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2}-\d{2}:\d{2})", content_text)
            if not m or not order_no:
                continue
            next_date, next_time = m.group(1), m.group(2)
            rows.append({
                "rating_date": rating_date, "rating_datetime_full": rating_date_text,
                "name": name, "order_no": order_no,
                "next_date": next_date, "next_time": next_time,
            })
        if len(trs) < 15:
            break

    # v2026.07.07：畫面要求「依評價日期排序，愈新在愈下方」，改成用完整的
    # 評價時間戳記（含時分秒）由舊到新排序，而不是只用日期（同一天會有
    # 多筆，只比日期排不出正確順序）。
    rows.sort(key=lambda r: r["rating_datetime_full"])

    results = []
    for row in rows:
        try:
            block = _fetch_purchase_block_for_order_no(session, row["order_no"])
            lines = block.get("lines", [])
            joined = "\n".join(lines)
            address = _extract_address_line(lines)
            phone = _extract_phone_from_block_lines(lines)
            service_date, service_time = _parse_service_date_time_loose(joined)
            person, _ = _extract_person_hour_line(joined)
            if not person:
                person = _count_staff_from_lines(lines)
            weekday = ""
            if service_date:
                try:
                    y, mo, d = [int(x) for x in service_date.split("-")]
                    weekday = _WEEKDAY_ZH[date(y, mo, d).weekday()]
                except Exception:
                    weekday = ""
            service_dt_display = (
                f"{service_date} ({weekday}) {service_time}" if service_date else "（查無服務日期）"
            )
            try:
                line_url = _fetch_line_url_for_order_no(session, row["order_no"])
            except Exception:
                line_url = ""
            results.append({
                "評價日期": row["rating_date"], "姓名": row["name"], "電話": phone,
                "地址": address, "預約下次日期": row["next_date"], "預約下次時間": row["next_time"],
                "服務日期及時間": service_dt_display, "服務人數": f"{person}人" if person else "",
                "訂單編號": row["order_no"], "LINE": line_url,
            })
        except Exception as e:
            results.append({
                "評價日期": row["rating_date"], "姓名": row["name"], "電話": "",
                "地址": "", "預約下次日期": row["next_date"], "預約下次時間": row["next_time"],
                "服務日期及時間": f"⚠️ 查詢訂單失敗：{e}", "服務人數": "",
                "訂單編號": row["order_no"], "LINE": "",
            })
    return results


def build_line_message_from_order_no(env_name, backend_email, backend_password, order_no, fallback_region="台北"):
    base_url = _configure_environment(env_name)
    session = requests.Session()
    if not login(session, backend_email, backend_password):
        raise Exception("後台登入失敗，請確認帳號密碼")
    block = _fetch_purchase_block_for_order_no(session, order_no)
    lines = block.get("lines", [])
    joined = "\n".join(lines)

    # v8.19：先判斷是不是「儲值金購買」訂單——這種訂單沒有服務日期/地址，
    # 走專用範本，不套用一般清潔服務訂單需要服務日期/地址/金額的檢查。
    _sv_region, _sv_amount, _sv_bonus = _extract_stored_value_purchase_info(joined)
    if _sv_amount is not None:
        sv_payway = _extract_payway_line(joined)
        if not sv_payway:
            raise Exception(f"訂單 {order_no} 無法判斷付款方式（信用卡/ATM），請至後台確認。")
        sv_message = build_stored_value_purchase_message(order_no, sv_payway, _sv_region, _sv_amount, _sv_bonus)
        sv_result = {
            "order_no": block["order_no"], "all_order_nos": [block["order_no"]],
            "payway": sv_payway, "region": _sv_region or fallback_region,
            "is_stored_value_purchase": True,
            "stored_value_amount": _sv_amount, "stored_value_bonus": _sv_bonus,
            "env_name": env_name, "session": session,
            "source_url": f"{base_url}/purchase?orderNo={block['order_no']}",
        }
        return sv_result, sv_message

    service_date, service_time = _parse_service_date_time_loose(joined)
    actual_time = _extract_actual_service_time(joined)
    person_extracted, _ = _extract_person_hour_line(joined)
    if not person_extracted:
        person_extracted = _count_staff_from_lines(lines)
    address = _extract_address_line(lines)
    fare = _extract_fare_line(joined) or "0"
    payway = _extract_payway_line(joined)
    region = get_region_by_address(address, ACCOUNTS) or fallback_region
    service_amount = _service_amount_from_block(joined, fare)
    if not service_date or not service_time:
        raise Exception(f"訂單 {order_no} 缺少服務日期或時段，無法產生通知")
    if not address:
        raise Exception(f"訂單 {order_no} 缺少服務地址，無法產生通知")
    if not payway:
        raise Exception(f"訂單 {order_no} 無法判斷付款方式（信用卡/ATM/儲值金），請至後台確認。")
    if payway != "儲值金" and not service_amount:
        raise Exception(f"訂單 {order_no} 缺少服務金額，無法產生通知")
    result = {
        "order_no": block["order_no"], "all_order_nos": [block["order_no"]],
        "address": address, "date": service_date, "period": service_time,
        "period_s": service_time, "actual_period": actual_time, "combined_period": "",
        "person": person_extracted, "service_amount": service_amount,
        "price_with_tax": service_amount, "fare": fare, "payway": payway,
        "region": region, "service_label": _extract_service_type_label(lines),
        "env_name": env_name, "session": session,
        "source_url": f"{base_url}/purchase?orderNo={block['order_no']}",
    }
    return result, build_line_message(result)


def build_combined_line_message_from_order_nos(env_name, backend_email, backend_password, order_nos, fallback_region="台北"):
    base_url = _configure_environment(env_name)
    session = requests.Session()
    if not login(session, backend_email, backend_password):
        raise Exception("後台登入失敗，請確認帳號密碼")
    orders_info = []
    for ono in order_nos:
        block = _fetch_purchase_block_for_order_no(session, ono)
        lines = block.get("lines", [])
        joined = "\n".join(lines)
        # v8.19：儲值金購買訂單沒有服務日期/地址，性質跟一般清潔服務訂單完全
        # 不同，不適合合併在一起產生訊息，直接擋下並提示改用單筆查詢。
        _sv_region_chk, _sv_amount_chk, _sv_bonus_chk = _extract_stored_value_purchase_info(joined)
        if _sv_amount_chk is not None:
            raise Exception(f"訂單 {ono} 是儲值金購買訂單，沒有服務日期/地址，不適合合併，請改用單筆訂單編號查詢。")
        service_date, service_time = _parse_service_date_time_loose(joined)
        actual_time = _extract_actual_service_time(joined)
        person_extracted, _ = _extract_person_hour_line(joined)
        if not person_extracted:
            person_extracted = _count_staff_from_lines(lines)
        address = _extract_address_line(lines)
        fare = _extract_fare_line(joined) or "0"
        payway = _extract_payway_line(joined)
        service_amount = _service_amount_from_block(joined, fare)
        region = get_region_by_address(address, ACCOUNTS) or fallback_region
        if not service_date or not service_time:
            raise Exception(f"訂單 {ono} 缺少服務日期或時段，無法合併")
        if not address:
            raise Exception(f"訂單 {ono} 缺少服務地址，無法合併")
        if not payway:
            raise Exception(f"訂單 {ono} 無法判斷付款方式，請至後台確認")
        orders_info.append({"order_no": ono, "service_date": service_date, "period_s": service_time, "actual_period": actual_time, "person": person_extracted, "address": address, "fare": fare, "payway": payway, "service_amount": service_amount, "region": region, "service_label": _extract_service_type_label(lines)})
    payways = {o["payway"] for o in orders_info if o["payway"]}
    if len(payways) > 1:
        raise Exception(f"合併的訂單付款方式不同（{', '.join(payways)}），請分開輸入分別產生通知。")
    # v2026.07.06：跟付款方式一樣，合併多筆訂單時服務類型也可能不同
    # （例如一筆居家清潔一筆辦公室清潔），不能只沿用第一筆的服務類型，
    # 否則訊息裡的服務名稱可能跟其中一筆訂單實際的服務不符。
    service_labels = {o["service_label"] for o in orders_info if o["service_label"]}
    if len(service_labels) > 1:
        raise Exception(f"合併的訂單服務類型不同（{', '.join(service_labels)}），請分開輸入分別產生通知。")
    unique_dates = sorted({o["service_date"] for o in orders_info})
    all_same_date = len(unique_dates) == 1
    if all_same_date:
        combined_period = _build_combined_period_display([{"period_s": o["period_s"], "actual_period": o["actual_period"], "person": o["person"]} for o in orders_info])
        multi_date = False
    else:
        period_lines = []
        for o in orders_info:
            d = o["service_date"].replace("-", "/")
            p_str = _format_period_display(str(o["period_s"] or "").replace(" ", ""), str(o["person"] or ""), display_override=str(o["actual_period"] or "").replace(" ", ""))
            period_lines.append(f"{d} {p_str}")
        combined_period = "\n".join(period_lines)
        multi_date = True
    amount_parts = []
    total_amount = 0
    for o in orders_info:
        try:
            v = int(str(o["service_amount"] or "0").replace(",", ""))
            amount_parts.append(str(v))
            total_amount += v
        except Exception:
            pass
    amount_display = "＋".join(amount_parts) + "＝" + str(total_amount) if len(amount_parts) > 1 else (str(total_amount) if total_amount else "")
    total_fare = 0
    for o in orders_info:
        try:
            total_fare += int(str(o["fare"] or "0").replace(",", ""))
        except Exception:
            pass
    first = orders_info[0]
    result = {
        "order_no": first["order_no"], "all_order_nos": order_nos,
        "address": first["address"], "date": first["service_date"],
        "period": first["period_s"], "period_s": first["period_s"],
        "actual_period": first["actual_period"], "combined_period": combined_period,
        "multi_date": multi_date, "person": first["person"],
        "service_amount": amount_display, "price_with_tax": str(total_amount),
        "fare": str(total_fare) if total_fare else "0", "payway": first["payway"],
        "region": first["region"], "service_label": first["service_label"],
        "env_name": env_name, "session": session,
        "source_url": f"{base_url}/purchase?orderNo={first['order_no']}",
    }
    return result, build_line_message(result)


# =========================================================
# 需求搜尋 / 其他工具
# =========================================================

def _is_target_day(d, day_type="不限"):
    weekday = d.weekday()
    if day_type == "平日":
        return weekday < 5
    if day_type == "週末":
        return weekday >= 5
    return True


def _filter_periods_by_preference(periods, time_preference="不限"):
    selected = []
    for period in periods or []:
        try:
            start_hour = int(str(period).split("-", 1)[0].split(":", 1)[0])
        except Exception:
            start_hour = 0
        if time_preference == "上午" and start_hour >= 12:
            continue
        if time_preference == "下午" and start_hour < 12:
            continue
        selected.append(period)
    return selected


def build_equivalent_plans(person, hour):
    try:
        base_person = int(person)
        base_hour = int(float(hour))
    except Exception:
        base_person, base_hour = 2, 4
    total_person_hours = base_person * base_hour
    candidates = [(base_person, base_hour)]
    for p in range(1, 5):
        if p == base_person:
            continue
        if total_person_hours % p != 0:
            continue
        h = total_person_hours // p
        if 2 <= h <= 8:
            candidates.append((p, h))
    seen = set()
    plans = []
    for p, h in candidates:
        key = (p, h)
        if key in seen:
            continue
        seen.add(key)
        plans.append({"person": p, "hour": h, "total_person_hours": total_person_hours})
    return plans


def search_available_service_dates(
    env_name, payway, lookup_result, address, clean_type_id, start_date,
    days=30, day_type="不限", time_preference="不限", plans=None,
    periods=None, period_hours=None, max_results=30,
):
    if isinstance(start_date, datetime):
        cursor = start_date.date()
    elif isinstance(start_date, date):
        cursor = start_date
    else:
        cursor = datetime.strptime(str(start_date), "%Y-%m-%d").date()
    periods = periods or ["08:30-12:30", "09:00-11:00", "09:00-12:00", "14:00-16:00", "14:00-17:00", "14:00-18:00", "09:00-16:00", "09:00-18:00"]
    period_hours = period_hours or {"08:30-12:30": 4, "09:00-11:00": 2, "09:00-12:00": 3, "14:00-16:00": 2, "14:00-17:00": 3, "14:00-18:00": 4, "09:00-16:00": 6, "09:00-18:00": 8}
    periods = _filter_periods_by_preference(periods, time_preference)
    plans = plans or build_equivalent_plans(2, 4)
    results = []
    for offset in range(int(days)):
        d = cursor + timedelta(days=offset)
        if not _is_target_day(d, day_type):
            continue
        date_s = d.strftime("%Y-%m-%d")
        for plan in plans:
            target_hour = int(plan.get("hour") or 0)
            target_periods = [p for p in periods if int(period_hours.get(p, 0)) == target_hour]
            if not target_periods:
                continue
            rows = quick_check_available_slots(
                env_name=env_name, payway=payway, lookup_result=lookup_result,
                address=address, clean_type_id=clean_type_id, date_s=date_s,
                hour=target_hour, person=plan.get("person"),
                periods=target_periods, period_hours=period_hours,
            )
            for row in rows:
                if not row.get("available"):
                    continue
                results.append({"date": date_s, "period": row.get("period"), "person": plan.get("person"), "hour": target_hour, "total_person_hours": plan.get("total_person_hours"), "staff": row.get("staff", "")})
                if len(results) >= int(max_results):
                    return results
    return results


def get_stored_value(env_name, backend_email, backend_password, phone, clean_type_id="1"):
    base_url = _configure_environment(env_name)
    session = requests.Session()
    if not login(session, backend_email, backend_password):
        raise Exception("後台登入失敗")
    page = session.get(f"{base_url}/booking/stored_value_routine", headers=HEADERS, allow_redirects=True)
    token_m = re.search(r'<meta name="csrf-token" content="([^"]+)"', page.text)
    csrf = token_m.group(1) if token_m else ""
    ajax = session.post(f"{base_url}/ajax/get_member", data={"phone": str(phone).strip(), "_token": csrf, "clean_type_id": str(clean_type_id)}, headers={**HEADERS, "X-Requested-With": "XMLHttpRequest"}, allow_redirects=True)
    try:
        data = ajax.json()
    except Exception:
        return 0, None
    if data.get("return_code") == "0000":
        sv = int(data.get("storedValue") or 0)
        member = data.get("member", {})
        return sv, member
    return 0, None



def lookup_company_name_by_tax_id(tax_id):
    """
    用統編查公司名稱，透過經濟部商工開放資料平台。
    回傳公司名稱字串，查無則回傳空字串。
    """
    try:
        import urllib.parse
        tax_id = str(tax_id).strip()
        # 商業登記（行號）
        url_biz = (
            f"https://data.gcis.nat.gov.tw/od/data/api/5F64D864-61CB-4D0D-8AD9-492047CC1EA6"
            f"?%24format=json&%24filter=Business_Accounting_NO%20eq%20{tax_id}&%24top=1"
        )
        resp = requests.get(url_biz, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            if data and data[0].get("Company_Name"):
                return data[0]["Company_Name"]
        # 公司登記（有限公司/股份有限公司）
        url_co = (
            f"https://data.gcis.nat.gov.tw/od/data/api/236EE382-4942-41A9-BD03-CA0709025E7C"
            f"?%24format=json&%24filter=Business_Accounting_NO%20eq%20{tax_id}&%24top=1"
        )
        resp2 = requests.get(url_co, timeout=5)
        if resp2.status_code == 200:
            data2 = resp2.json()
            if data2 and data2[0].get("Company_Name"):
                return data2[0]["Company_Name"]
    except Exception:
        pass
    return ""

def _day_type_from_date(date_text):
    try:
        d = datetime.strptime(str(date_text), "%Y-%m-%d").date()
    except Exception:
        return "平日"
    return "週末" if d.weekday() >= 5 else "平日"


def calc_stored_value_plan(sv, new_service_price=None, day_type="平日", total_person_hours=None, zero_total_stored_order=True):
    import math
    sv = int(float(sv or 0))
    unit_price = 700 if str(day_type or "").strip() == "週末" else 600
    try:
        ph = int(float(total_person_hours or 0))
    except Exception:
        ph = 0
    if ph > 0:
        n = ph
        dummy_price = unit_price * ph
    else:
        n = math.ceil(sv / unit_price) if sv > 0 else 1
        dummy_price = n * unit_price
    coupon_a = max(dummy_price - sv, 0)
    coupon_b = sv
    customer_pays = (new_service_price - sv) if new_service_price else None
    return {"unit_price": unit_price, "dummy_price": dummy_price, "coupon_a": coupon_a, "coupon_b": coupon_b, "customer_pays": customer_pays, "n": n, "total_person_hours": ph or n, "stored_value_applied": min(sv, dummy_price), "stored_order_total_after_coupon": max(dummy_price - coupon_a - sv, 0), "zero_total_stored_order": bool(zero_total_stored_order)}


def _invoice_payload(invoice_mode, member_email="", mobile_carrier="", company_title="", company_no=""):
    mode = str(invoice_mode or "會員載具").strip()
    if mode == "手機載具":
        if not str(mobile_carrier or "").strip().startswith("/"):
            raise Exception("手機載具需以 / 開頭")
        return {"invoice_type_override": "2", "carrier_type_id_override": "2", "carrier_info": str(mobile_carrier).strip(), "company_title": "", "company_no": "", "payment_type": "B2C"}
    if mode == "三聯式":
        if not str(company_title or "").strip() or not str(company_no or "").strip():
            raise Exception("三聯式發票需填寫抬頭與統編")
        return {"invoice_type_override": "3", "carrier_type_id_override": "1", "carrier_info": "", "company_title": str(company_title).strip(), "company_no": str(company_no).strip(), "payment_type": "B2B"}
    return {"invoice_type_override": "2", "carrier_type_id_override": "1", "carrier_info": str(member_email or "").strip(), "company_title": "", "company_no": "", "payment_type": "B2C"}


def _stored_value_makeup_context(
    env_name, backend_email, backend_password, phone, clean_type_id, service_date,
    period_s, hour, person, address="", region="", coupon_prefix_base="",
    coupon_valid_days=60, balance_override=None, allow_zero_balance=False,
):
    day_type = _day_type_from_date(service_date)
    if balance_override not in (None, ""):
        sv = int(float(balance_override))
    else:
        sv, _ = get_stored_value(env_name, backend_email, backend_password, phone, clean_type_id)
    if sv <= 0 and not allow_zero_balance:
        raise Exception("查無儲值金或儲值金餘額為 0")
    try:
        total_ph = int(float(person)) * int(float(hour))
    except Exception:
        total_ph = 0
    plan = calc_stored_value_plan(sv, None, day_type=day_type, total_person_hours=total_ph, zero_total_stored_order=True)
    lookup = quick_lookup_member(env_name, backend_email, backend_password, phone, clean_type_id)
    member_payload = lookup.get("member_payload")
    if not member_payload:
        raise Exception(f"電話 {phone} 查無會員資料")
    member = member_payload.get("member", {}) or {}
    addr_list = member.get("memberAddressList", []) or []
    selected_address = address or (addr_list[0].get("address", "") if addr_list else "")
    if not selected_address:
        raise Exception("會員沒有可用服務地址，請先至後台補地址")
    selected_region = region or get_region_by_address(selected_address, ACCOUNTS) or "台北"
    today_str = date.today().strftime("%Y-%m-%d")
    date_e = (date.today() + timedelta(days=int(coupon_valid_days))).strftime("%Y-%m-%d")
    suffix = str(coupon_prefix_base or phone)[-4:]
    return {"balance": sv, "plan": plan, "lookup": lookup, "member": member, "address": selected_address, "region": selected_region, "day_type": day_type, "today_str": today_str, "date_e": date_e, "prefix_a": f"svA{suffix}", "prefix_b": f"svB{suffix}"}


def stored_value_makeup_create_stored_order(
    env_name, backend_email, backend_password, phone, clean_type_id, service_date, period_s,
    hour, person, address="", region="", coupon_prefix_base="", coupon_valid_days=60,
    allow_auto_lemon_shift=False,
):
    ctx = _stored_value_makeup_context(env_name, backend_email, backend_password, phone, clean_type_id, service_date, period_s, hour, person, address, region, coupon_prefix_base, coupon_valid_days)
    regions = [ctx["region"]] if ctx.get("region") else list(COUPON_COMPANY_ID_MAP.keys())
    services = ["居家清潔", "裝修細清"]
    coupon_a = create_coupon(env_name, backend_email, backend_password, title=f"儲值金清零-{phone}", discount=ctx["plan"]["coupon_a"], date_s=ctx["today_str"], date_e=ctx["date_e"], prefix=ctx["prefix_a"], piece="1", regions=regions, service_items=services)
    code_a = coupon_a.get("coupon_code") or coupon_a.get("coupon_prefix") or ctx["prefix_a"]
    stored_order = quick_create_order(env_name=env_name, payway="儲值金", region=ctx["region"], lookup_result=ctx["lookup"], address=ctx["address"], clean_type_id=clean_type_id, date_s=service_date, period_s=period_s, hour=str(hour), person=str(person), discount_code=code_a, allow_auto_lemon_shift=bool(allow_auto_lemon_shift))
    lemon_result = assign_lemon_cleaners_to_order(session=stored_order["session"], base_url=_configure_environment(env_name), order_no_a=stored_order["order_no"], service_date=service_date, period_s=period_s, person_count=str(person), allow_auto_lemon_shift=bool(allow_auto_lemon_shift))
    note = (f"儲值金補價差第一段：儲值金折抵單 {stored_order['order_no']}，{ctx['day_type']}單價 {ctx['plan']['unit_price']} × {ctx['plan']['total_person_hours']}人時 = {ctx['plan']['dummy_price']}，優惠券A折抵 {ctx['plan']['coupon_a']} 元，剩餘 {ctx['plan']['stored_value_applied']} 元扣儲值金後總額應為 0，檸檬人勿動。")
    _update_order_note(stored_order["session"], _configure_environment(env_name), stored_order["order_no"], note)
    return {"stage": "stored_order", "balance": ctx["balance"], "plan": ctx["plan"], "day_type": ctx["day_type"], "coupon_a": coupon_a, "stored_order": stored_order, "lemon_result": lemon_result, "note": note, "address": ctx["address"], "region": ctx["region"], "phone": phone, "clean_type_id": clean_type_id, "service_date": service_date, "period_s": period_s, "hour": str(hour), "person": str(person), "coupon_prefix_base": coupon_prefix_base or phone, "coupon_valid_days": coupon_valid_days}


def stored_value_makeup_create_paid_order(
    env_name, backend_email, backend_password, phone, clean_type_id, service_date, period_s,
    hour, person, customer_payway="ATM", invoice_mode="會員載具", mobile_carrier="",
    company_title="", company_no="", address="", region="", coupon_prefix_base="",
    coupon_valid_days=60, stored_order_no="", balance_override=None,
    allow_auto_lemon_shift=False,
):
    ctx = _stored_value_makeup_context(env_name, backend_email, backend_password, phone, clean_type_id, service_date, period_s, hour, person, address, region, coupon_prefix_base, coupon_valid_days, balance_override=balance_override)
    if balance_override not in (None, ""):
        ctx["balance"] = int(float(balance_override))
        ctx["plan"]["coupon_b"] = ctx["balance"]
    regions = [ctx["region"]] if ctx.get("region") else list(COUPON_COMPANY_ID_MAP.keys())
    services = ["居家清潔", "裝修細清"]
    coupon_b = create_coupon(env_name, backend_email, backend_password, title=f"儲值金補價差客付-{phone}", discount=ctx["plan"]["coupon_b"], date_s=ctx["today_str"], date_e=ctx["date_e"], prefix=ctx["prefix_b"], piece="1", regions=regions, service_items=services)
    code_b = coupon_b.get("coupon_code") or coupon_b.get("coupon_prefix") or ctx["prefix_b"]
    invoice = _invoice_payload(invoice_mode, member_email=ctx["member"].get("email") or "", mobile_carrier=mobile_carrier, company_title=company_title, company_no=company_no)
    paid_order = quick_create_order(env_name=env_name, payway=customer_payway, region=ctx["region"], lookup_result=ctx["lookup"], address=ctx["address"], clean_type_id=clean_type_id, date_s=service_date, period_s=period_s, hour=str(hour), person=str(person), discount_code=code_b, allow_auto_lemon_shift=bool(allow_auto_lemon_shift), **invoice)
    pair = f"儲值折抵單 {stored_order_no} + 客付補價差單 {paid_order['order_no']}" if stored_order_no else f"客付補價差單 {paid_order['order_no']}"
    note = f"儲值金補價差第二段：{pair}，客付單使用優惠券B折抵原儲值金餘額 {ctx['balance']} 元。"
    _update_order_note(paid_order["session"], _configure_environment(env_name), paid_order["order_no"], note)
    service_due = _service_due_after_fare(paid_order["session"], paid_order["order_no"])
    if service_due == 0:
        # v8.51：跟訂單轉換一致，總金額扣車馬費為 0 時要自動標記已付款。
        mark_paid_ok, mark_paid_msg = _mark_order_as_paid(paid_order["session"], _configure_environment(env_name), paid_order["order_no"])
        invoice_note_ok, invoice_note_msg = _update_order_invoice_no_text(paid_order["session"], _configure_environment(env_name), paid_order["order_no"], "不開立發票")
    else:
        mark_paid_ok, mark_paid_msg = None, f"服務金額未歸零（總金額扣車馬費={service_due}），不自動標記已付款"
        invoice_note_ok, invoice_note_msg = False, "服務金額未歸零，不自動標註不開立發票"

    # v2026.07.10：LINE 訊息改成「儲值金歸零訂單＋補價差訂單 合併訂單」的
    # 格式，另起一行顯示補價差訂單真正的服務時間；服務金額這行要顯示（跟
    # 訂單轉換不同），並註明已扣除多少儲值金餘額。
    _new_period_disp = _format_period_display(str(period_s).replace(" ", ""), str(person))
    if stored_order_no:
        paid_order["merged_service_time_line"] = (
            f"服務時間 : {stored_order_no}＋{paid_order['order_no']}  合併訂單\n"
            f"                      實際服務時間：{str(service_date).replace('-', '/')} {_new_period_disp}"
        )
    _paid_amount = service_due
    paid_order["custom_amount_line"] = f"服務金額：{_paid_amount}（含稅，已扣除儲值金餘額${ctx['balance']}）"
    paid_order["hide_amount_line"] = False
    paid_order["customer_due"] = service_due

    return {
        "stage": "paid_order", "balance": ctx["balance"], "plan": ctx["plan"], "day_type": ctx["day_type"],
        "coupon_b": coupon_b, "paid_order": paid_order, "note": note,
        "line_message": build_line_message(paid_order), "address": ctx["address"], "region": ctx["region"],
        "stored_order_no": stored_order_no,
        "mark_paid_ok": mark_paid_ok, "mark_paid_msg": mark_paid_msg,
        "invoice_note_ok": invoice_note_ok, "invoice_note_msg": invoice_note_msg,
    }


def stored_value_makeup_convert(
    env_name, backend_email, backend_password, phone, clean_type_id, service_date, period_s,
    hour, person, day_type="", customer_payway="ATM", invoice_mode="會員載具",
    mobile_carrier="", company_title="", company_no="", address="", region="",
    coupon_prefix_base="", coupon_valid_days=60,
):
    first = stored_value_makeup_create_stored_order(env_name, backend_email, backend_password, phone, clean_type_id, service_date, period_s, hour, person, address, region, coupon_prefix_base, coupon_valid_days)
    second = stored_value_makeup_create_paid_order(env_name, backend_email, backend_password, phone, clean_type_id, service_date, period_s, hour, person, customer_payway, invoice_mode, mobile_carrier, company_title, company_no, first["address"], first["region"], coupon_prefix_base, coupon_valid_days, stored_order_no=first["stored_order"].get("order_no", ""), balance_override=first["balance"])
    note = first.get("note", "") + "\n" + second.get("note", "")
    return {"balance": first["balance"], "plan": first["plan"], "day_type": first["day_type"], "coupon_a": first.get("coupon_a"), "coupon_b": second.get("coupon_b"), "stored_order": first.get("stored_order"), "paid_order": second.get("paid_order"), "lemon_result": first.get("lemon_result"), "note": note, "line_message": second.get("line_message"), "address": first["address"], "region": first["region"]}


def parse_new_customer_order_text(raw_text):
    text = str(raw_text or "").strip()
    result = {"name": "", "phone": "", "email": "", "address": "", "ping": "", "payway": "", "invoice_type": "", "invoice_title": "", "tax_id": "", "carrier": "", "requirement": "", "note": ""}
    if not text:
        return result

    def clean_value(value):
        return str(value or "").strip().strip("：:").strip()

    normalized = text.replace("：", ":")
    lines = [line.strip() for line in normalized.splitlines() if line.strip()]
    label_map = [
        ("name", ["訂購人姓名", "姓名", "客人姓名"]),
        ("phone", ["訂購人電話", "電話", "手機", "客人電話"]),
        ("email", ["訂購人Email", "訂購人email", "Email", "email", "信箱"]),
        ("address", ["服務地址", "地址"]),
        ("ping", ["室內坪數", "坪數"]),
        ("payway", ["付款方式"]),
        ("invoice_type", ["發票載具", "發票方式", "載具類型", "發票"]),
        ("invoice_title", ["發票抬頭", "公司抬頭", "抬頭", "買受人"]),
        ("tax_id", ["統一編號", "統編", "公司統編", "買受人統編"]),
        ("carrier", ["載具號碼", "載碼", "載具", "統編資訊"]),
        ("requirement", ["服務需求", "需求", "服務條件"]),
    ]
    consumed = set()
    for idx, line in enumerate(lines):
        compact_line = line.replace(" ", "")
        for key, labels in label_map:
            for label in labels:
                compact_label = label.replace(" ", "")
                if compact_line.startswith(compact_label + ":"):
                    result[key] = clean_value(line.split(":", 1)[1])
                    consumed.add(idx)
                    break
                if compact_line == compact_label and idx + 1 < len(lines):
                    result[key] = clean_value(lines[idx + 1])
                    consumed.add(idx)
                    consumed.add(idx + 1)
                    break
            if idx in consumed:
                break
    if not result["carrier"]:
        for idx, line in enumerate(lines):
            value = line.strip()
            if re.match(r"^/[A-Za-z0-9.+-]{6,}$", value):
                result["carrier"] = value
                consumed.add(idx)
                break
    if not result["email"]:
        m = re.search(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}", text)
        if m:
            result["email"] = m.group(0)
    if not result["phone"]:
        m = re.search(r"(?:\+?886[-\s]?)?0?9[\d\-\s]{8,12}", text)
        if m:
            result["phone"] = normalize_phone(m.group(0))
    if result.get("phone"):
        result["phone"] = normalize_phone(result["phone"])
    requirement_patterns = [r"(平日|週末|假日|不限).*(\d+)\s*人\s*(\d+(?:\.\d+)?)\s*小時", r"(\d+)\s*人\s*(\d+(?:\.\d+)?)\s*小時"]
    if not result["requirement"]:
        for idx, line in enumerate(lines):
            if idx in consumed:
                continue
            if any(re.search(pattern, line) for pattern in requirement_patterns):
                result["requirement"] = line.strip()
                consumed.add(idx)
                break
    if not result["tax_id"]:
        tax_matches = re.findall(r"(?<!\d)\d{8}(?!\d)", text)
        if tax_matches:
            result["tax_id"] = tax_matches[0]
    notes = [line for idx, line in enumerate(lines) if idx not in consumed]
    result["note"] = "\n".join(notes).strip()
    return result


def parse_new_customer_text(text):
    """
    v8.12：從客人提供的文字拆解出建單所需欄位，支援兩種格式：
      1. 有標籤格式：「訂購人姓名：XXX」「電話：09...」「Email：...」等
         （標籤與冒號之間允許有空白，例如「室內坪數 :45」）。
      2. 無標籤格式：一行一個欄位，依序為姓名/電話/Email/地址/坪數/付款方式/備註，
         不論有沒有「訂購人姓名：」這類標籤，都要能辨識出對應欄位。
    付款方式：
      - 支援「付款方式：信用卡 / 轉帳匯款 擇一　轉帳」這種列出選項＋客人實際填寫
        答案的格式，取「擇一」之後客人實際填寫的答案，而非誤判成說明文字列出的
        所有選項。
      - 完全判斷不出來時，payway 回傳空字串，並將 need_ask_payway 設為 True，
        呼叫端（畫面）必須請客服手動選擇，不可默默預設成信用卡。
    發票載具/統編：
      - 偵測不到明確的手機載具或統編（例如只有說明文字，沒有實際填寫的值）時，
        carrier 與 company_no 皆回傳空字串；呼叫端（quick_create_new_customer_order）
        本來就會在兩者皆空時預設走「會員載具（email）」，符合「發票載具若未填
        則用會員載具」的需求，這裡不需要額外處理。
    回傳 dict：name, phone, email, address, ping, payway, carrier, company_title,
              company_no, need_lookup_title, need_ask_payway
    """
    import re as _re
    result = {}
    raw_text = str(text or "")
    lines_all = [l.strip() for l in raw_text.splitlines() if l.strip()]

    def _find(patterns, text):
        for p in patterns:
            m = _re.search(p, text, _re.IGNORECASE)
            if m:
                return m.group(1).strip()
        return ""

    # ---------- 姓名（有標籤） ----------
    result["name"] = _find([
        r"(?:訂購人)?姓名\s*[：:]\s*(.+)",
    ], raw_text)

    # ---------- 電話 ----------
    _raw_phone = _find([
        r"(?:訂購人)?電話\s*[：:]\s*([\d\-\s]+)",
        r"手機\s*[：:]\s*([\d\-\s]+)",
    ], raw_text)
    if not _raw_phone:
        _phone_m = _re.search(r"(?:\+?886[-\s]?)?0?9\d{2}[-\s]?\d{3}[-\s]?\d{3}", raw_text)
        if _phone_m:
            _raw_phone = _phone_m.group(0)
    result["phone"] = normalize_phone(_raw_phone) if _raw_phone else ""

    # ---------- Email ----------
    result["email"] = _find([
        r"(?:訂購人)?[Ee]mail\s*[：:]\s*(\S+)",
        r"[Ee]-mail\s*[：:]\s*(\S+)",
        r"信箱\s*[：:]\s*(\S+)",
    ], raw_text)
    if not result["email"]:
        _email_m = _re.search(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}", raw_text)
        if _email_m:
            result["email"] = _email_m.group(0)

    # ---------- 地址 ----------
    _addr_lines = []
    for _line in raw_text.splitlines():
        _line = _line.strip()
        if _re.match(r"服務地址\s*[：:]", _line) or _re.match(r"地址\s*[：:]", _line):
            _addr_val = _re.sub(r"^(服務)?地址\s*[：:]\s*", "", _line).strip()
            if _addr_val:
                _addr_lines.append(_addr_val)
    if _addr_lines:
        result["address"] = _addr_lines[0]
    else:
        # 無標籤格式：掃描各行，找出符合台灣地址型態的行
        _addr_pattern = r"(台|臺|新北|桃園|台中|臺中|台南|臺南|高雄|基隆|新竹|嘉義|苗栗|彰化|南投|雲林|屏東|宜蘭|花蓮|台東|臺東|澎湖|金門|連江).*(市|縣).*(區|鄉|鎮|市)"
        _addr_found = ""
        for _line in lines_all:
            if _re.search(_addr_pattern, _line):
                _addr_found = _line
                break
        result["address"] = _addr_found

    # ---------- 坪數 → ping 代號 ----------
    _ping_raw = _find([
        r"(?:室內)?坪數\s*[：:]\s*(.+)",
    ], raw_text)
    if not _ping_raw:
        # 無標籤格式：找一行是純數字（1~3位，代表坪數）或「約XX坪」格式
        for _line in lines_all:
            if _re.fullmatch(r"\d{1,3}", _line):
                _ping_raw = _line
                break
            _ping_m = _re.match(r"^(?:約)?(\d{1,3})\s*坪$", _line)
            if _ping_m:
                _ping_raw = _ping_m.group(1)
                break
    ping = "4"
    if _ping_raw:
        nums = _re.findall(r"\d+", _ping_raw)
        if nums:
            n = int(nums[0])
            if n <= 10: ping = "1"
            elif n <= 20: ping = "2"
            elif n <= 30: ping = "3"
            elif n <= 40: ping = "4"
            elif n <= 50: ping = "5"
            else: ping = "6"
    result["ping"] = ping

    # ---------- 付款方式 ----------
    _payway_raw = _find([r"付款方式\s*[：:]\s*(.+)"], raw_text) or ""
    if not _payway_raw:
        # 無標籤格式：找一行本身就是付款方式關鍵字（例如單獨一行「轉帳」）
        for _line in lines_all:
            if _re.fullmatch(r"(信用卡|ATM|atm|轉帳|匯款|轉帳匯款|現金|刷卡)", _line):
                _payway_raw = _line
                break

    def _resolve_payway(raw_value):
        raw_value = str(raw_value or "").strip()
        if not raw_value:
            return ""
        # 若文字中有「擇一」等提示字樣，優先取其後的內容（客人實際填寫的答案），
        # 避免把說明文字裡列出的所有選項都誤判成答案。
        _after_marker = raw_value
        for _marker in ("擇一", "請選擇", "請勾選", "->", "→"):
            if _marker in raw_value:
                _after_marker = raw_value.split(_marker)[-1]
                break
        _has_card = bool(_re.search(r"信用卡|刷卡", _after_marker))
        _has_atm = bool(_re.search(r"ATM|atm|轉帳|匯款|現金", _after_marker))
        if _has_card and not _has_atm:
            return "信用卡"
        if _has_atm and not _has_card:
            return "ATM"
        return ""  # 兩者都有或都沒有 → 無法判斷，視為未填

    result["payway"] = _resolve_payway(_payway_raw)
    # v8.12：付款方式判斷不出來時，標記旗標讓呼叫端請客服手動選擇，不可默默預設。
    result["need_ask_payway"] = not bool(result["payway"])

    # ---------- 發票（載具 / 統編） ----------
    _invoice_raw = _find([r"發票[^：:]*\s*[：:]\s*(.+)"], raw_text) or ""

    # 手機載具（格式：/開頭，5-8碼英數字，可能有空格或括號）
    _carrier_m = _re.search(r"(/[\.\-A-Z0-9]{5,8})", (_invoice_raw + " " + raw_text).upper())
    result["carrier"] = _carrier_m.group(1) if _carrier_m else ""

    # 統編（8位數字）
    _tax_m = _re.search(r"統一編號\s*[：:]*\s*(\d{8})", raw_text) or _re.search(r"(\d{8})", _invoice_raw)
    # 若發票載具欄位本身就是8位數字，也當作統編
    _carrier_str = _invoice_raw.strip()
    if not _tax_m and _re.fullmatch(r"\d{8}", _carrier_str):
        result["company_no"] = _carrier_str
        result["carrier"] = ""
    elif _tax_m:
        result["company_no"] = _tax_m.group(1)
    else:
        result["company_no"] = ""

    # 公司抬頭（先從文字找，若無則需呼叫統編查詢 API）
    _title_m = _re.search(r"(?:公司抬頭|抬頭)\s*[：:]*\s*(.+?)(?:及|與|統|$)", _invoice_raw + " " + raw_text)
    result["company_title"] = _title_m.group(1).strip() if _title_m else ""

    # 有統編但無抬頭 → 旗標，讓呼叫方去查抬頭
    result["need_lookup_title"] = bool(result.get("company_no") and not result.get("company_title"))

    # ---------- 姓名 fallback（無標籤格式）----------
    # 排除掉已辨識為電話/Email/地址/坪數/付款方式的行，以及看起來像「標籤：內容」的行，
    # 剩下第一個非空行視為姓名。
    if not result["name"]:
        _phone_digits = _re.sub(r"\D", "", result.get("phone", ""))
        for _line in lines_all:
            _line_digits = _re.sub(r"\D", "", _line)
            _is_phone_line = bool(_phone_digits) and len(_line_digits) >= 9 and _phone_digits in _line_digits
            _is_email_line = bool(result.get("email")) and result["email"] in _line
            _is_address_line = bool(result.get("address")) and result["address"] in _line
            _is_ping_line = bool(_re.fullmatch(r"\d{1,3}", _line)) or bool(_re.match(r"^(?:約)?\d{1,3}\s*坪$", _line))
            _is_payway_line = bool(_re.fullmatch(r"(信用卡|ATM|atm|轉帳|匯款|轉帳匯款|現金|刷卡)", _line))
            _is_label_line = bool(_re.match(r"^[\u4e00-\u9fffA-Za-z0-9（）()\s]{1,10}[：:]", _line))
            if _is_phone_line or _is_email_line or _is_address_line or _is_ping_line or _is_payway_line or _is_label_line:
                continue
            result["name"] = _line
            break

    return result


def quick_create_new_customer_order(env_name, backend_email, backend_password, customer, allow_auto_lemon_shift=False):
    """
    新客建單：完整模擬後台 /booking/single 表單送出流程。
    customer dict 必填：name, phone, email, address, payway, clean_type_id,
                        date_s, period_s, hour, person
    選填：ping, service_type, carrier, company_title, company_no, tel, line
    """
    required = ["name", "phone", "email", "address", "payway", "clean_type_id",
                "date_s", "period_s", "hour", "person"]
    missing = [k for k in required if not str((customer or {}).get(k, "")).strip()]
    if missing:
        raise Exception("新客資料不足，請補齊：" + "、".join(missing))

    base_url = _configure_environment(env_name)
    session = requests.Session()
    if not login(session, backend_email, backend_password):
        raise Exception("後台登入失敗")

    phone = normalize_phone(str(customer["phone"]).strip())
    name = str(customer["name"]).strip()
    email = str(customer["email"]).strip()
    tel = str(customer.get("tel", "")).strip()
    line = str(customer.get("line", "")).strip()
    address = str(customer["address"]).strip()
    # 2026-07-08：移除 geocode 猜行政區。
    # 之前地址缺少行政區時可能猜成大安區，導致新單區域錯誤；現在只修正既有行政區順序，不再補猜。
    address = _fix_address_district_order(address, fallback_district="")
    address_parts = _split_booking_address(address)
    _assert_address_region_resolved(address_parts, address, context="新客地址")
    address_for_lookup = address_parts["full"]
    address_for_submit = address_parts["detail"]
    payway = str(customer["payway"]).strip()
    clean_type_id = str(customer["clean_type_id"]).strip()
    date_s = str(customer["date_s"]).strip()
    period_s = str(customer["period_s"]).strip()
    hour = str(customer["hour"]).strip()
    person = str(customer["person"]).strip()
    ping = str(customer.get("ping", "4")).strip()
    service_type = str(customer.get("service_type", "")).strip()
    carrier = str(customer.get("carrier", "")).strip()
    company_no = str(customer.get("company_no", "")).strip()
    company_title = str(customer.get("company_title", "")).strip()

    # 有統編 → 一律查詢公司抬頭（確保正確），查不到就擋住建單
    if company_no:
        try:
            import requests as _req2
            _r2 = _req2.get(
                "https://data.gcis.nat.gov.tw/od/data/api/5F64D864-61CB-4D0D-8AD9-492047CC1EA6",
                params={"$format": "json", "$filter": f"Business_Accounting_NO eq {company_no}"},
                timeout=5,
                verify=False,
            )
            _d2 = _r2.json()
            if _d2 and isinstance(_d2, list) and _d2[0].get("Company_Name"):
                company_title = _d2[0]["Company_Name"]
            else:
                raise Exception(f"統編 {company_no} 查無公司抬頭，請確認統編是否正確，建單已停止")
        except Exception as _e2:
            if "查無公司抬頭" in str(_e2):
                raise
            raise Exception(f"統編查詢失敗（{_e2}），請確認網路或統編是否正確，建單已停止")

    # 其他選填欄位
    memo = str(customer.get("memo", "")).strip()        # 客人備註
    notice = str(customer.get("notice", "")).strip()    # 客服備註
    actual_time = str(customer.get("actual_time", "")).strip()  # 簡訊實際服務時間

    # payway: 信用卡=1, ATM=2（與 PAYWAY_MAP 一致）
    if "信用卡" in payway or payway == "1":
        payway_code = "1"
    elif "ATM" in payway or "匯款" in payway or "轉帳" in payway or payway == "2":
        payway_code = "2"
    else:
        payway_code = "1"  # 預設信用卡

    # 發票設定
    if company_no:
        # 有統編 → 三聯式發票
        invoice_type = "3"
        carrier_type_id = "1"
        carrier_info = email
    elif carrier and carrier.startswith("/"):
        # 手機載具
        invoice_type = "2"
        carrier_type_id = "2"
        carrier_info = carrier
    else:
        # 預設二聯式會員載具（email）
        invoice_type = "2"
        carrier_type_id = "1"
        carrier_info = email

    # Step 1: 取 CSRF token 和 is_backend（登入者ID）
    booking_page = session.get(f"{base_url}/booking/single", headers=HEADERS, allow_redirects=True)
    token_m = re.search(r'<meta name="csrf-token" content="([^"]+)"', booking_page.text)
    csrf = token_m.group(1) if token_m else ""
    if not csrf:
        raise Exception("無法取得 CSRF token")

    # 取 is_backend（後台員工ID，藏在頁面 JS 裡）
    backend_id_m = re.search(r"is_backend[^0-9]*([0-9]+)", booking_page.text)
    is_backend = backend_id_m.group(1) if backend_id_m else ""

    # Step 2: 查會員或建立會員
    # v2026.07.06：原本這裡如果查到會員就直接沿用，完全沒有告知客服「這支電話
    # 其實已經是舊客會員」，導致客服可能誤把舊客當新客處理（例如漏看舊客歷史
    # 訂單/地址、用新客話術溝通等）。現在查到既有會員時記錄下來，並把姓名/
    # Email 放進回傳結果的警示欄位，讓客服在畫面上能直接看到提醒。
    member_payload = get_member(session, phone, csrf, clean_type_id)
    existing_member_name = ""
    existing_member_email = ""
    is_existing_member = bool(member_payload)
    if is_existing_member:
        _existing_member_info = member_payload.get("member", {}) or {}
        existing_member_name = str(_existing_member_info.get("name") or "").strip()
        existing_member_email = str(_existing_member_info.get("email") or "").strip()
    if not member_payload:
        # 建立新會員
        create_resp = session.post(
            f"{base_url}/ajax/create_member",
            data={"name": name, "phone": phone, "tel": tel, "email": email, "_token": csrf},
            headers={**HEADERS, "X-Requested-With": "XMLHttpRequest"},
        )
        try:
            cdata = create_resp.json()
        except Exception:
            raise Exception(f"建立會員失敗：{create_resp.text[:200]}")
        if str(cdata.get("err_no", "")) != "0":
            raise Exception(f"建立會員失敗：{cdata.get('description', '未知')}")
        member_payload = get_member(session, phone, csrf, clean_type_id)
        if not member_payload:
            raise Exception("建立會員後仍查無會員")

    member = member_payload.get("member", {}) or {}
    member_id = str(member.get("member_id", ""))
    existing_member_warning = (
        f"⚠️ 這支電話（{phone}）其實已經是舊客會員（姓名：{existing_member_name or member.get('name', '')}"
        f"{'，Email：' + existing_member_email if existing_member_email else ''}），不是新客！"
        "建議改用「舊客快速建單」流程處理，避免漏看歷史訂單/地址。"
        if is_existing_member else ""
    )

    # 新會員建立完成後，直接使用舊客建單的唯一核心流程。
    # 不再於本函式另做一套 calculate_hour/get_section，避免相同日期時段
    # 在新客與舊客流程得到不同班表結果。
    _lookup_for_order = {
        "session": session,
        "token": csrf,
        "phone": phone,
        "member_payload": member_payload,
        "base_url": base_url,
        "env_name": env_name,
    }
    _shared_result = quick_create_order(
        env_name=env_name,
        payway=payway,
        region=get_region_by_address(address, ACCOUNTS) or "台北",
        lookup_result=_lookup_for_order,
        address=address,
        clean_type_id=clean_type_id,
        date_s=date_s,
        period_s=period_s,
        hour=hour,
        person=person,
        carrier_info=carrier_info,
        company_no=company_no,
        company_title=company_title,
        invoice_type_override=invoice_type,
        carrier_type_id_override=carrier_type_id,
        extra_fields={
            "ping": ping,
            "serviceType": service_type,
            "room": str(customer.get("room", "0")),
            "bathroom": str(customer.get("bathroom", "0")),
            "balcony": str(customer.get("balcony", "0")),
            "livingroom": str(customer.get("livingroom", "0")),
            "kitchen": str(customer.get("kitchen", "0")),
            "window": str(customer.get("window", "")),
            "shutter": str(customer.get("shutter", "")),
            "clothes": str(customer.get("clothes", "0")),
            "dyson": str(customer.get("dyson", "0")),
            "refrigerator": str(customer.get("refrigerator", "0")),
            "disinfection": str(customer.get("disinfection", "0")),
            "go_abord": str(customer.get("go_abord", "0")),
            "home_move": str(customer.get("home_move", "0")),
            "storage": str(customer.get("storage", "0")),
            "cabinet": str(customer.get("cabinet", "0")),
            "quintuple": str(customer.get("quintuple", "0")),
            "memo": memo,
            "notice": notice,
            "period": actual_time,
        },
        allow_auto_lemon_shift=allow_auto_lemon_shift,
    )
    _shared_result.update({
        "member_id": member_id,
        "date_s": date_s,
        "period_s": period_s,
        "period": period_s,
        "actual_period": actual_time,
        "hour": hour,
        "person": person,
        "existing_member_warning": existing_member_warning,
        "day_type": _day_type_from_date(date_s),
    })
    return _shared_result

    # Step 3: 查或建地址，取 addressId / area_id / company_id / lat / lng
    addr_list = member.get("memberAddressList", []) or []
    address_norm = normalize_addr_for_match(address_for_lookup)
    matched_addr = None
    for a in addr_list:
        if normalize_addr_for_match(a.get("address", "")) == address_norm:
            matched_addr = a
            break

    if matched_addr:
        # 確認後台存的地址和原始地址一致才帶 addressId
        stored_addr = matched_addr.get("address", "")
        if normalize_addr_for_match(stored_addr) == address_norm:
            address_id = str(matched_addr.get("addressId") or matched_addr.get("id", ""))
        else:
            address_id = ""  # 地址不一致，不帶舊 addressId 避免帶入錯誤地址
        area_id = str(matched_addr.get("areaId", ""))
        country_id = str(matched_addr.get("countryId", ""))
        lat = str(matched_addr.get("lat", ""))
        lng = str(matched_addr.get("lng", ""))
        purchase_info = matched_addr.get("purchase", {}) or {}
        company_id = str(purchase_info.get("company_id", "1"))
    else:
        # 2026-07-08：不再用 geocode 猜地址/行政區；交由後台 check_contain 判斷。
        # 若後台無法判斷 area_id，直接擋下，不使用任何大安區 fallback。
        # 2026-07-08 補強：check_contain 若拿不到 lat/lng，後台可能用錯誤預設區域
        # 回傳 area_id，造成成單後地址被加上「大安區」。所以這裡仍先 geocode 取座標，
        # 但只把座標交給後台判斷，不用 geocode 結果自行猜行政區或改地址字串。
        geo_lat, geo_lng = geocode_address(address_for_lookup)
        check_resp = session.post(
            f"{base_url}/ajax/check_contain",
            data={
                # v2026.07.06 修正：後台 /ajax/check_contain 實際要的參數名稱是
                # camelCase（memberId／cleanTypeId），跟畫面手動點「查詢地區」時
                # 送出的一致（後台原始頁面 JS：'memberId=' + ... + '&cleanTypeId=' + ...）。
                # 這裡原本誤用成 snake_case（member_id／clean_type_id），後台完全
                # 收不到正確的會員 ID 和服務類別，導致 check_contain 永遠查不到
                # 正確區域——不管地址寫得多正確都一樣會失敗，或（改這個修正前）
                # 靜默套用固定 fallback 值，導致每筆新地址都被誤標成同一個區域
                # （例如大安區）。這才是「常常是大安區」現象的真正原因，不是後台
                # 自己的地址正規化行為。
                "_token": csrf, "memberId": member_id,
                "address": address_for_lookup, "lat": str(geo_lat or ""), "lng": str(geo_lng or ""),
                "cleanTypeId": clean_type_id,
            },
            headers={**HEADERS, "X-Requested-With": "XMLHttpRequest"},
        )
        try:
            check_data = check_resp.json()
        except Exception:
            raise Exception(f"查詢地址區域失敗：{check_resp.text[:200]}")
        area_info = (check_data.get("area") or {})
        if not area_info.get("area_id"):
            # v8.11：查無正確區域時直接擋下，不再默默套用可能錯誤的固定值，
            # 避免地址被誤標成錯誤區域（例如一律變成大安區）。
            raise Exception(
                f"查詢地址區域失敗：地址「{address_for_lookup}」無法判斷所屬區域"
                f"（check_contain 回傳無 area_id，地址是否正確或是否為服務涵蓋範圍？）"
                f"，請確認地址格式或改用後台手動建單。"
            )
        address_parts = _complete_missing_district(address_parts, area_info, address_for_lookup, context="新客地址")
        address_for_lookup = address_parts["full"]
        address_for_submit = address_parts["detail"]
        area_id = str(area_info.get("area_id") or "")
        company_id = str(area_info.get("company_id") or "")
        country_id = str(address_parts.get("country_id") or area_info.get("country_id") or "")
        _validate_area_not_known_bad(address_for_lookup, area_info, context="新客地址")
        if not company_id:
            raise Exception(
                f"查詢地址區域失敗：地址「{address_for_lookup}」無法判斷 company_id，"
                "已停止成單，避免系統誤判區域。"
            )
        if not country_id:
            raise Exception(
                f"查詢地址區域失敗：地址「{address_for_lookup}」無法判斷縣市/區域下拉選單，"
                "已停止成單，不會自動改成大安區。"
            )
        lat = str(geo_lat or "")
        lng = str(geo_lng or "")
        address_id = ""

    # Step 4: 組 datePeriod（格式：2026-07-11_14:00-18:00）
    date_period = f"{date_s}_{period_s}"

    # 計算 price（已含稅，用固定公式：人時 × 600平日/700週末）
    day_type = _day_type_from_date(date_s)
    unit_price = 700 if day_type == "週末" else 600
    ph = int(person) * int(float(hour))
    price_with_tax = unit_price * ph

    # Step 4b: 查班表，若無人或人數不足，且客服有明確勾選「自動補檸檬人」才勾檸檬人班表；
    # v2026.07.09：查完（含補勾檸檬人重查）後，人數還是不夠就直接擋單，不再靜默放行
    # （之前 except 整段吞掉，就算查無班表/人數不足也照樣建單）。
    # 與舊客 quick_create_order 使用相同的 /booking/single token。
    # 這裡不能再呼叫 get_csrf_token：_configure_environment 的預設
    # BOOKING_URL 是 stored_value_routine，會讓新客查班表與一般舊客走不同表單。
    token_for_section = csrf
    _base_data_check = {
        "clean_type_id": clean_type_id,
        "phone": phone, "name": name, "email": email, "tel": tel or phone,
        "line": line, "fbName": "", "fb": "", "memoProcess": "", "memoFinance": "",
        "addressId": address_id, "country_id": country_id, "address": address_for_submit,
        "ping": ping, "serviceType": service_type,
        "room": str(customer.get("room", "0")),
        "bathroom": str(customer.get("bathroom", "0")),
        "balcony": str(customer.get("balcony", "0")),
        "livingroom": str(customer.get("livingroom", "0")),
        "kitchen": str(customer.get("kitchen", "0")),
        "window": str(customer.get("window", "")),
        "shutter": str(customer.get("shutter", "")),
        "clothes": str(customer.get("clothes", "0")),
        "dyson": str(customer.get("dyson", "0")),
        "refrigerator": str(customer.get("refrigerator", "0")),
        "disinfection": str(customer.get("disinfection", "0")),
        "go_abord": str(customer.get("go_abord", "0")),
        "home_move": str(customer.get("home_move", "0")),
        "storage": str(customer.get("storage", "0")),
        "cabinet": str(customer.get("cabinet", "0")),
        "quintuple": str(customer.get("quintuple", "0")),
        "hour": str(int(float(hour))), "price": "", "price_vvip": "",
        "person": person, "date_s": date_s, "period_s": period_s,
        "period": "", "cycle": "1", "fare": "", "memo": memo, "notice": notice,
        "discount_code": "", "payway": payway_code,
        "invoice_type": invoice_type, "carrier_type_id": carrier_type_id,
        "carrier_info": carrier_info, "company_title": company_title,
        "company_no": company_no, "donate_code": "", "is_backend": is_backend,
        "member_id": member_id,
        "company_id": company_id, "area_id": area_id,
        "lat": lat, "lng": lng,
    }
    if not str(country_id or "").strip():
        raise Exception(
            f"地址「{address_for_lookup}」缺少明確縣市/區域下拉選單，已停止成單，"
            "不會自動改成大安區。"
        )
    if not str(area_id or "").strip() or not str(company_id or "").strip():
        raise Exception(
            f"地址「{address_for_lookup}」缺少明確 area_id/company_id，已停止成單，"
            "請先到後台手動確認區域，避免系統誤判成大安區。"
        )
    _validate_address_before_submit(address_for_lookup, area_id, context="新客建單")

    # 後台手動建單與舊客流程都會先 calculate_hour；get_section
    # 會依賴這些回填欄位判斷完整時段。新客原本略過這步，
    # 會出現選 09:00-12:00 卻回到 09:00-11:00，進而誤判無人力。
    _calc_result = calculate_hour(session, _base_data_check, token_for_section)
    if not _calc_result:
        raise Exception("計算時數失敗")
    _calc_fields = extract_calc_fields(
        _calc_result,
        fallback_hours=_base_data_check["hour"],
        fallback_fare="0",
    )
    _base_data_check["price"] = str(int(round(price_with_tax / TAX_RATE)))
    _base_data_check["price_vvip"] = str(_calc_fields.get("price_vvip") or "0")
    _base_data_check["fare"] = str(_calc_fields.get("fare") or "0")

    _slot = f"{date_s}_{period_s}"
    _raw_section = get_section_raw(session, _base_data_check, token_for_section, _slot)
    _slot_found = slot_exists_in_section_response(_raw_section, _slot)
    _cleaners = extract_cleaners_from_section_response(_raw_section, _slot) if _slot_found else []
    _need = int(person)
    _has_explicit_cleaners = bool(_cleaners)
    _auto_shift_ok = False
    _pre_shift = {}
    # v8.13：查無班表/人數不足時，預設不自動勾檸檬人，必須客服明確勾選才會執行。
    if (not _slot_found or (_has_explicit_cleaners and len(_cleaners) < _need)) and allow_auto_lemon_shift:
        _short = _need - len(_cleaners) if _slot_found and _has_explicit_cleaners else _need
        _pre_shift = ensure_lemon_cleaner_shifts(
            session=session, base_url=base_url,
            service_date=date_s, period_s=period_s,
            person_count=str(_short),
        )
        _auto_shift_ok = bool(_pre_shift.get("success"))
        time.sleep(2)
        _raw_section = get_section_raw(session, _base_data_check, token_for_section, _slot)
        _slot_found = slot_exists_in_section_response(_raw_section, _slot)
        _cleaners = extract_cleaners_from_section_response(_raw_section, _slot) if _slot_found else []
        _has_explicit_cleaners = bool(_cleaners)

    if not _slot_found or not _has_explicit_cleaners or len(_cleaners) < _need:
        # v2026.07.07：加上診斷資訊——地址審核期間解析出的 area_id/company_id，
        # 以及 get_section 實際回傳內容的前 300 字。之前只顯示「0人可指派」，
        # 但排班頁明明看得到人，無法判斷是查詢班表時用錯了 area_id/company_id
        # （查到别的區域去了），還是 get_section 回傳格式跟解析邏輯對不上，
        # 這樣至少能比對排班頁畫面上顯示的區域是否跟這裡解析出來的一致。
        raise Exception(
            f"查無班表或人數不足（需要 {_need} 人，目前排班頁只有 {len(_cleaners)} 人可指派），"
            f"依規定人數不足不能成單，請先確認/補足班表後再建單。"
            f"\n🔧 除錯：area_id={area_id}　company_id={company_id}　country_id={country_id}"
            f"\nget_section 原始回應前300字：{str(_raw_section)[:300]}"
        )

    # Step 5: POST /booking/single
    post_data = {
        "_token": csrf,
        "clean_type_id": clean_type_id,
        "phone": phone,
        "name": name,
        "email": email,
        "tel": tel,
        "line": line,
        "fbName": "",
        "fb": "",
        "memoProcess": "",
        "memoFinance": "",
        "addressId": address_id,
        "last_area": "",
        "country_id": country_id,
        "address": address_for_submit,
        "ping": ping,
        "serviceType": service_type,
        "room": str(customer.get("room", "")),
        "bathroom": str(customer.get("bathroom", "")),
        "balcony": str(customer.get("balcony", "")),
        "livingroom": str(customer.get("livingroom", "")),
        "kitchen": str(customer.get("kitchen", "")),
        "window": str(customer.get("window", "")),
        "shutter": str(customer.get("shutter", "")),
        "clothes": str(customer.get("clothes", "0")),
        "dyson": str(customer.get("dyson", "0")),
        "refrigerator": str(customer.get("refrigerator", "0")),
        "disinfection": str(customer.get("disinfection", "0")),
        "go_abord": str(customer.get("go_abord", "0")),
        "home_move": str(customer.get("home_move", "0")),
        "storage": str(customer.get("storage", "0")),
        "cabinet": str(customer.get("cabinet", "0")),
        "quintuple": str(customer.get("quintuple", "0")),
        "hour": hour,
        "price": str(price_with_tax),
        "price_vvip": "0",
        "person": person,
        "date_s": "",
        "period_s": period_s,
        "cycle": "1",
        "fare": "0",
        "datePeriod": date_period,
        "period": "",
        "memo": memo,
        "notice": notice,
        "period": actual_time,   # 簡訊實際服務時間
        "discount_code": "",
        "payway": payway_code,
        "invoice_type": invoice_type,
        "donate_code": "",
        "carrier_type_id": carrier_type_id,
        "carrier_info": carrier_info,
        "company_title": company_title,
        "company_no": company_no,
        "is_backend": is_backend,
        "member_id": member_id,
        "company_id": company_id,
        "area_id": area_id,
        "lat": lat,
        "lng": lng,
    }

    # 後台表單的縣市/區域由 country_id 下拉承接，address 欄只送路街巷號樓。
    post_data["address"] = address_for_submit

    # 依付款方式選 endpoint 和欄位
    if payway_code == "4":  # 儲值金
        booking_endpoint = f"{base_url}/booking/stored_value_routine"
        # 儲值金不帶付款/發票欄位
        for _k in ["payway", "invoice_type", "donate_code", "carrier_type_id",
                   "carrier_info", "company_title", "company_no"]:
            post_data.pop(_k, None)
    else:  # 信用卡=1, ATM=2
        booking_endpoint = f"{base_url}/booking/single"

    resp = session.post(
        booking_endpoint,
        data=post_data,
        headers={**HEADERS, "Content-Type": "application/x-www-form-urlencoded",
                 "Referer": booking_endpoint},
        allow_redirects=True,
    )

    # 建單後統一從回應和 /purchase 列表取訂單號
    order_no = ""

    # 先試從回應內容取（HTML redirect 含訂單號）
    order_no_m = re.search(r"(TT\d{8}|LC\d{9})", resp.url + resp.text[:5000])
    if order_no_m:
        order_no = order_no_m.group(1)

    # 若回應是 JSON（儲值金流程：{"count":1} 或餘額不足）
    if not order_no:
        try:
            _resp_json = resp.json()
            if isinstance(_resp_json, dict):
                # 餘額不足
                if _resp_json.get("stored_value_balance") is not None and _resp_json.get("count", 1) == 0:
                    balance = _resp_json.get("stored_value_balance", 0)
                    raise Exception(f"儲值金餘額不足（目前餘額：{balance} 元），無法建單")
                # 建單成功（count > 0）
                if _resp_json.get("count", 0) > 0:
                    pass  # 繼續往下從 /purchase 撈
        except Exception as _je:
            if "儲值金餘額不足" in str(_je):
                raise

    # 等後台完成，再從訂單列表撈最新訂單
    if not order_no:
        time.sleep(3)
        blocks = _fetch_purchase_blocks_for_phone(session, phone, name=name)
        # 取最新一筆（blocks 已依時間倒序）
        if blocks:
            order_no = blocks[0].get("order_no", "")

    if not order_no:
        raise Exception(
            f"建單後無法取得訂單編號（HTTP {resp.status_code}）\n"
            f"請至後台訂單管理確認電話 {phone} 是否已有新訂單，若有請直接使用該訂單號碼。"
        )

    # 勾選「自動補檸檬人」不只是補出可成單的時段；成單後還必須
    # 實際把這張訂單的人員換成檸檬人。只修改本單，且補班底層會
    # 跳過當日已有班別的專員，不動其他客人的已配班專員。
    lemon_assignment = {}
    if allow_auto_lemon_shift:
        lemon_assignment = assign_lemon_cleaners_to_order(
            session=session, base_url=base_url, order_no_a=order_no,
            service_date=date_s, period_s=period_s, person_count=str(person),
            allow_auto_lemon_shift=True,
        )
        if lemon_assignment.get("success"):
            time.sleep(1)

    # v8.6：補齊 build_line_message 需要的欄位（date/period/region/fare/service_amount/
    # actual_period），避免呼叫端組 LINE 訊息時因缺少欄位而 KeyError 或漏掉地址所屬區域。
    _region_computed = get_region_by_address(address, ACCOUNTS) or "台北"

    # v8.7：建單後回查後台實際金額，與人時公式（600平日/700週末，不含車馬費）算出的
    # price_with_tax 比對；若後台實際金額不同（例如後台依坪數/房間數等另行計價，
    # 覆蓋掉我們送出的固定公式金額），加上警示訊息，方便客服在畫面上立即發現。
    # v8.9：同一次回查也順便比對地址——若後台實際地址跟我們送出的地址不同
    # （例如後台自動判斷區域時加了不正確的市/區前綴），一併加上警示。
    # 查詢失敗不影響建單結果，只是無法附上警示。
    price_mismatch_warning = ""
    backend_actual_amount = None
    address_mismatch_warning = ""
    backend_actual_address = ""
    try:
        _verify_block = _fetch_purchase_block_for_order_no(session, order_no)
        _verify_joined = "\n".join(_verify_block.get("lines", []))
        _verify_fare = _extract_fare_line(_verify_joined) or "0"
        _verify_amount = _service_amount_from_block(_verify_joined, _verify_fare)
        if _verify_amount:
            backend_actual_amount = int(round(float(str(_verify_amount).replace(",", ""))))
            if backend_actual_amount != price_with_tax:
                price_mismatch_warning = (
                    f"⚠️ 後台實際金額為 {backend_actual_amount} 元，"
                    f"與人時公式算出的 {price_with_tax} 元（{unit_price}元×{ph}人時，{day_type}）不同，"
                    f"請至後台確認訂單 {order_no} 的實際金額是否正確。"
                )
        _verify_addr = _extract_address_line(_verify_block.get("lines", []))
        if _verify_addr:
            backend_actual_address = _verify_addr
            _norm_submitted = normalize_addr_for_match(address)
            _norm_backend = normalize_addr_for_match(_verify_addr)
            if _norm_submitted and _norm_backend and _norm_submitted != _norm_backend:
                address_mismatch_warning = (
                    f"⚠️ 後台實際地址為「{_verify_addr}」，與送出的「{address}」不同"
                    f"（很可能是後台自動判斷區域時加了不正確的市/區前綴，屬於後台端行為，"
                    f"非本系統送出的資料有誤），請至後台手動確認/修正訂單 {order_no} 的地址。"
                )
    except Exception:
        pass

    # v2026.07.09：補上成單後的實際專員名字，跟舊客快速建單一致。
    # 優先用 fetch_order_meta_by_order_no 撈後台實際配班結果（後台可能依
    # 班表自動配到跟建單前查詢當下不同的人），查不到才退回用建單前查到的
    # 排班候選人（_cleaners）當備援顯示。
    try:
        _meta = fetch_order_meta_by_order_no(session, order_no)
    except Exception:
        _meta = {}
    _staff_fallback = format_staff_from_cleaners(_cleaners, people=person) if _cleaners else "（無班表資料）"
    staff_display = _meta.get("服務人員") or _staff_fallback
    lemon_assignment_ok = (not allow_auto_lemon_shift) or bool(lemon_assignment.get("success"))
    if allow_auto_lemon_shift and lemon_assignment.get("success") and lemon_assignment.get("assigned"):
        staff_display = " X ".join(lemon_assignment["assigned"])
    lemon_assignment_warning = ""
    if allow_auto_lemon_shift and not lemon_assignment_ok:
        lemon_assignment_warning = (
            f"⚠️ 訂單 {order_no} 已建立，但檸檬人置換失敗："
            f"{lemon_assignment.get('message', '無法取得足夠檸檬人')}。請先人工確認配班，不要發確認信。"
        )

    # v8.13：建單成功後檢查此訂單編號是否重複對應到多張訂單卡片
    _is_dup, _dup_count = _check_order_no_duplicate(session, order_no)
    _dup_warning = (
        f"⚠️ 訂單編號重複警示：訂單編號 {order_no} 目前查詢到 {_dup_count} 張不同的訂單卡片，"
        f"這是後台偶發的訂單編號重複問題，請務必至後台人工確認，避免訂單資料互相搞混或覆蓋！"
        if _is_dup else ""
    )

    return {
        "order_no": order_no,
        "member_id": member_id,
        "address": address,
        "date_s": date_s,
        "date": date_s,
        "period_s": period_s,
        "period": period_s,
        "actual_period": actual_time,
        "hour": hour,
        "person": person,
        "staff": staff_display,
        "lemon_assignment": lemon_assignment,
        "lemon_assignment_ok": lemon_assignment_ok,
        "lemon_assignment_warning": lemon_assignment_warning,
        "price_with_tax": price_with_tax,
        "service_amount": price_with_tax,
        "backend_actual_amount": backend_actual_amount,
        "price_mismatch_warning": price_mismatch_warning,
        "backend_actual_address": backend_actual_address,
        "address_mismatch_warning": address_mismatch_warning,
        "order_no_duplicated": _is_dup, "order_no_duplicate_count": _dup_count,
        "duplicate_order_warning": _dup_warning,
        "existing_member_warning": existing_member_warning,
        "fare": "0",
        "payway": payway,
        "clean_type_id": str(clean_type_id),
        "region": _region_computed,
        "day_type": day_type,
        "session": session,
    }
