# ============================================================
# 檔名：orders.py
# 版本：v2026.08.14-2
# 模組：批次建單核心引擎（Google Sheet → 後台訂單，供 ordersapp.py 呼叫）
# 最後更新：2026-08-14
#
# Change Log
# v2026.08.14-2
# - 修正「後台／Google 日曆雙向比對」的兩個誤判漏洞（真實訂單 LC00213191、
#   LC00212665 驗證過）：
#   1. 原本用 _extract_order_dates_from_block_lines 抓服務日期，要求先出現
#      「訂購日期（建立時間，YYYY-MM-DD HH:MM:SS）」這一行才承認服務日期；
#      代客預訂類訂單卡片沒有這一行，導致服務日期永遠抓不到、整筆訂單被跳過
#      比對，誤判成「日曆有、後台沒有」。改成新的 _calchk_service_date_time_
#      from_lines：不依賴訂購日期是否出現，直接定位「HH:MM-HH:MM」服務時段
#      這一行，往回找最近的純日期行當服務日期。
#   2. 非標準時段（例如客人約 10:00-12:00，系統送 09:00-11:00 佔位）的訂單，
#      日期旁顯示的是系統時段，真正跟客人約定、也是 Google 日曆實際顯示的
#      時間記在「簡訊實際服務時間」標籤後面。原本只看系統時段，永遠跟日曆
#      對不上；現在偵測到這個標籤時改用標籤後面的時段比對。
# v2026.08.14-1
# - 新增 run_backend_calendar_consistency_check：獨立的「後台訂單／Google 日曆
#   雙向比對」工具，比照 run_standalone_consistency_check 的雙向比對精神，把
#   比對對象從 Google Sheet 成單工作表換成 Google 日曆。以日曆事件的時間與
#   顏色為基準（沿用既有慣例：黃色＝已安排／應該已成單），只有黃色事件才拿來
#   跟後台已付款訂單互相比對，找出「後台有、日曆沒有」或「日曆有、後台沒有」
#   的訂單。供 ordersapp.py 新增的「後台／Google 日曆雙向比對」功能使用。
# v2026.07.20-1
# - 批次建單恢復「自動補檸檬人」可選開關。底層安全保護維持：
#   專員當日已有任何班別時一律跳過，不動到其他客人已配班人員。
# v2026.07.19-1
# - 批次建單禁止自動新增或改寫專員班表；只能使用後台當下已有的
#   可用人力，查無班表或人數不足時直接停止。
# - 補班底層保護：專員當日已有任何班別時拒絕寫入，避免動到其他
#   本來已配班的人員。
# v2026.07.08-1
# - 儲值獎金備註效能優化：find_pending_stored_value_orders 搜尋時一併回傳
#   edit_id，apply_bonus_notes / add_bonus_note_to_order 可直接使用這個 edit_id
#   開啟訂單編輯頁，套用備註時不再每筆都重新用訂單編號搜尋 /purchase。
#   這樣同一頁流程可做到「搜尋一次 → 確認名單 → 直接套用」，減少等待時間。
# v2026.07.07-5
# - 修正 fetch_recent_service_records 抓專員姓名時，把連結內附帶的「(評分
#   數字)」也一起抓進來的 bug（例如「嚴慶隆(3)」而不是「嚴慶隆」），改成
#   抓完後把結尾的 (數字) 去掉，只留姓名本身。
# v2026.07.07-4
# - 新功能：會員喜好設定。新增 fetch_member_edit_page（讀取/解析會員編輯頁，
#   含完整喜愛/不喜愛專員名單與目前勾選狀態）、submit_member_preferences
#   （送出更新，沿用其他既有欄位避免被清空）、fetch_recent_service_records
#   （查詢近N筆有排班的服務紀錄，含日期與專員姓名），供 ordersapp.py 新增的
#   「會員喜好設定」分頁使用。
# v2026.07.07-3
# - 修正批次建單「查詢地址/地區失敗」誤擋單的重大邏輯錯誤：手動在後台操作
#   證實，選擇會員「已存在的下拉地址」時，畫面本來就是直接沿用會員資料裡
#   存好的 areaId/lat/lng，check_contain 失敗也照樣送得出訂單（check_contain
#   只是順便再確認，不是必要條件）。之前的程式碼把 check_contain 當成每次
#   都要成功的硬性條件，導致已知、能正常服務的地址也被誤擋下來。現在改成
#   只有在 best_addr 本身完全沒有 area_id 時才需要 check_contain 成功。
# v2026.07.07-2
# - 批次建單「查詢地址/地區失敗」加上除錯資訊（HTTP狀態碼、lat/lng、回應
#   內容前300字）。check_contain 只有 HTTP 層級失敗（非200或非合法JSON）
#   才會走到這個錯誤，不是地址真的判斷不出區域（那種情況會直接沿用既有
#   area_id/company_id 不會擋單），所以需要實際狀態碼才能判斷根因
#   （常見原因：token過期、或這筆地址沒有已存的經緯度、又剛好 Google Maps
#   金鑰沒設定，導致 lat/lng 送空值給後台）。
# v2026.07.07-1
# - 修正 add_bonus_note_to_order 找不到編輯ID的 bug：原本只靠線上搜尋拿
#   編輯ID，找不到就直接失敗；現在加上跟其他函式一致的 fallback，改用
#   訂單編號直接算編輯ID（_purchase_edit_id_from_order_no）。
# - find_orders_without_line_link / find_pending_stored_value_orders 新增
#   return_debug 參數，回傳候選訂單數/是否撞到頁數上限等除錯資訊。
# - 修正 LOGIN_URL 沒有跟著 env_name 切換環境的 bug（3處：
#   find_orders_without_line_link、find_pending_stored_value_orders、
#   apply_bonus_notes）：原本只切換 BASE_URL/PURCHASE_URL，LOGIN_URL 卻
#   永遠停在模組載入當下 env.py 的 ENV 對應網域，導致選 prod 時其實是
#   登入 dev、卻拿 dev 的 session cookie 去查 prod，永遠查不到資料。
# 舊版：v2026.07.13-2（此日期為先前誤植，今天實際日期為 2026-07-07）
# - find_pending_stored_value_orders 的 purchase_status 參數新增支援傳入
#   list/tuple（例如 ["0","1"] 代表「待付款＋已付款」的組合篩選）。因為
#   後台的付款狀態欄位只吃單一值，傳清單時不會送給後台篩選，改成抓回來
#   的訂單全部掃過一輪，自己比對「付款狀態」這行文字是不是屬於清單裡任一
#   種，在 Python 這邊做篩選。已用假資料測試過，確認「待付款＋已付款」
#   組合能正確排除「取消訂單」等其他狀態。
# v2026.07.13
# - 儲值獎金備註功能依客服需求調整：
#   1. 搜尋條件改成訂購日期／付款日期／付款狀態（可選：不拘/待付款/已付款/
#      取消訂單/已退款），移除原本寫死的「處理狀態：未處理」。
#   2. 新增「客服備註為空白」的篩選條件——只列出客服備註目前還沒有內容的
#      訂單，避免重複回填。新增 _extract_notice_map_from_raw_html，因為
#      客服備註的實際內容只出現在 <label alt="...">客服備註</label> 這個
#      標籤的屬性裡，extract_order_cards_from_purchase_html 是用 get_text()
#      把整頁攤平成純文字，屬性值會被整個遺失，所以另外寫一個函式回頭用
#      原始 HTML 判斷：某張訂單卡片的原始 HTML 裡有沒有出現這個標籤，
#      沒出現代表客服備註是空白（後台不會渲染空白備註的這個標籤）。
#   3. 結果新增「付款狀態」欄位。
#   4. add_bonus_note_to_order 寫入獎金備註時，一併把 progress 改成 "1"
#      （已處理）。
#   已用真實訂單卡片文字驗證過「客服備註空白判斷」跟「付款狀態解析」都
#   正確。
# v2026.07.12-2
# - 修正重大 bug：add_bonus_note_to_order 之前天真地把訂單編輯頁靜態 HTML
#   解析出來的 input/textarea 值整包送回去，但這個編輯頁很多欄位（加收
#   狀態/待退狀態的 radio、加收備註/待退備註的 textarea 等）是 Vue.js
#   動態渲染的，靜態 HTML 裡看到的是還沒被渲染的樣板語法（例如 textarea
#   內容是字面上的 "{{ purchase.chargeNote }}"），radio 的勾選狀態也不會
#   反映在靜態 HTML 的 checked 屬性上。實際案例：本來「加收狀態：無」
#   「待退狀態：無」，套用完變成「已加收」「已全額退款」，「加收備註」被
#   寫入字面上的樣板字串。
#   修法：改成從頁面內嵌在 <script> 裡的 `purchase: {...}` JSON 資料
#   （Vue 的 data()）讀出這些欄位的真實值，蓋掉靜態 HTML 解析可能抓錯的
#   部分，只有「notice」這個欄位是我們自己要更新的。已用模擬真實 Vue
#   樣板情境的假頁面測試過，確認 isCharge/isRefund 正確送出原本的 0（無），
#   chargeNote/refundNote 正確送出空字串，不再是樣板亂碼。
# v2026.07.12
# - 新增「儲值獎金備註」獨立工具：
#   find_pending_stored_value_orders：搜尋購買項目儲值金、付款狀態已付款、
#   處理狀態未處理的訂單，列出客戶姓名/電話/訂單編號（沿用 v2026.07.11-4
#   同一套「後台粗篩＋Python 自己解析日期精確比對」的日期篩選作法）。
#   add_bonus_note_to_order：依訂單編號，把「獎金：名字1X名字2...」加進
#   訂單編輯頁的客服備註（notice 欄位），保留原本備註內容、不覆蓋，其餘
#   欄位（含服務狀態）原封不動送回去。
#   apply_bonus_notes：批次套用用的包裝函式，統一登入一次後逐筆呼叫
#   add_bonus_note_to_order。
#   另外新增 _fetch_order_edit_id 的 orders.py 本地版本（跟 quick_order.py
#   同名函式邏輯一致，這裡另外放一份是因為 orders.py 不匯入 quick_order，
#   避免循環匯入）。
#   已用假 session 測試過搜尋跟寫入備註兩個函式，確認搜尋能正確解析姓名/
#   電話，寫入備註時能正確保留既有備註內容並附加新的獎金行。
# v2026.07.11-4
# - find_orders_without_line_link 第四次修正漏單問題：v2026.07.11-3 遇到
#   區間只填一邊時，選擇整個放棄該區間、改成完全不篩選、直接掃描前 80 頁。
#   但實測發現這樣還是抓不到 LC00212069 這種很新的訂單——研判是後台在
#   完全沒有篩選條件時的預設排序並不是「新到舊」（很可能是依 ID 由舊到
#   新），導致掃描前 80 頁只掃得到很久以前的舊訂單，新訂單永遠輪不到。
#   改成：不管只填了起或迄的哪一邊，都自動幫忙補上另一邊寬鬆的日期
#   （很早的 2000-01-01 或很晚的 2099-12-31），確保送給後台的一定是
#   「起訖都有值」的完整區間，不會再整個放棄篩選條件。用假 session 驗證過
#   實際送出的查詢參數確實是完整區間，也確認能正確抓到 LC00212069。
# v2026.07.11-3
# - find_orders_without_line_link 再次修正漏單問題：實測發現不管是「三種
#   區間同時送」還是「每種區間分開各送一次」，只要區間裡有任何一邊留空
#   （例如只填起始日、沒填結束日——這剛好是最常見的用法），後台的日期
#   篩選就整個不準，導致明明符合條件的訂單被漏掉（用真實訂單 LC00212069、
#   LC00212115、LC00138514 等大量驗證過）。
#   改成完全不依賴後台日期篩選的準確性：只用「起訖都有填」的其中一種區間
#   （優先順序：服務日期 > 訂購日期 > 付款日期）當後台粗篩，抓到候選訂單
#   後，新增 _extract_order_dates_from_block_lines 自己解析每張卡片實際的
#   訂購日期／服務日期／付款日期，三種區間都在 Python 這邊自己比對篩選。
#   已用真實訂單卡片文字驗證過解析結果完全正確，並用「只填起始日」這種
#   使用者實際會用的輸入模式模擬過完整流程，確認能正確抓到 LC00212069。
# v2026.07.11-2
# - 修正 find_orders_without_line_link 重大漏單問題：實測發現把訂購日期／
#   付款日期／服務日期三種區間「同時」塞進同一次查詢請求，後台會漏掉一大堆
#   明明符合條件的訂單（用真實訂單編號 LC00212069、LC00212115 等驗證過）。
#   改成「每一種有填的日期區間分別各自查一次」，結果依訂單編號合併去重，
#   不管後台能不能正確同時處理多重日期篩選都不會漏單。新增輔助函式
#   _fetch_all_purchase_blocks_with_filters，並用假 session 驗證過分開查詢
#   各自能正確撈到不同訂單。
# v2026.07.11
# - 新增 find_orders_without_line_link：獨立工具，搜尋「訂購資訊」欄位裡
#   沒有 LINE 連結的訂單，列出訂單編號/姓名/電話，可用訂購日期/付款日期/
#   服務日期三種區間分別篩選（都可留空）。用實際頁面結構驗證過：判斷方式
#   是看訂單卡片解析出來的 lines 裡有沒有出現純文字「LINE」這一行（對應
#   <a href="https://chat.line.biz/...">LINE</a> 這個連結的顯示文字），
#   沒有這一行代表這張訂單沒有綁 LINE。
# v2026.07.10
# - 修正批次建單同樣的規則漏洞：run_process_web 之前只檢查「時段存不存在」
#   （slot_ok），沒有檢查「人數夠不夠」，導致時段有排班、但排的人數不夠這張
#   單需要的人數時，還是照樣送出建單。現在時段存在但人數不足時，一併視同
#   「無班表」處理（併入 no_slot_dates，reason 顯示「無班表」/staff 顯示
#   「無人力」），不會再送出人力不足的訂單。跟 quick_order.py v8.31 的
#   舊客/新客建單修正保持一致的規則：不論服務日期遠近，人數不夠一律不能
#   成單，若客服有勾選「查無班表時自動補檸檬人」，會先嘗試補到足夠人數，
#   補不到才擋單。
# v2026.07.09
# - 修正 run_standalone_consistency_check 方向二的邏輯漏洞：舊版是拿工作表
#   裡已出現的電話去查後台，如果某張後台訂單的客人電話整筆漏登記進工作表，
#   從一開始就不會被拿去查，等於查不出「後台有、工作表完全沒有」的情況。
#   新增 _fetch_all_purchase_blocks_by_date_range（處理分頁），改成直接掃過
#   date_range_start ~ date_range_end 這段期間後台「全部」已付款訂單，逐筆
#   核對訂單編號有沒有出現在工作表任何一列，才是真正回答得了「後台這段
#   期間的訂單是否都在 Google Sheet 裡」這個問題。有給日期區間才會執行這段
#   加強版方向二；沒給的話退回舊版（以電話為主）的方向二。
# v2026.07.08
# - 新增 run_standalone_consistency_check：獨立版的雙向訂單一致性檢查，
#   不用依附在批次建單流程裡，可以直接針對任一份已經有「訂單編號」欄位的
#   工作表重新跑一次雙向比對（不限定是不是這次批次剛跑過的列）。內部沿用
#   既有的 verify_batch_order_consistency 核心比對邏輯，只是改成讀取整份
#   工作表目前的狀態，而不是只看某次批次執行過的 target_rows。
# v2026.07.07
# - 修正 ORDER_NO_REGEX 只認得 LC/TT 開頭的訂單編號，導致這次發現的「儲值金
#   購買」訂單（KK 開頭，例如 KK00212122）完全沒被辨識成一張訂單卡片的起點，
#   在 extract_order_cards_from_purchase_html 解析訂單列表時整張漏掉或跟
#   前後訂單卡片的內容混在一起。這個函式是整個系統解析後台訂單列表的共用
#   基礎（批次、LINE 訊息、發票/付款方式查詢、一致性檢查全部都靠它），影響
#   範圍很廣。修法：改成明確列舉前綴 (LC|TT|KK)。
#   　※有考慮過改成更寬鬆的「任兩個大寫字母＋數字」規則，但發票號碼（例如
#   　　TF27826169、FG82592263）剛好也符合這個格式，會被誤判成訂單編號，
#   　　反而把訂單卡片切錯位置，所以還是採用明確列舉前綴的做法，比較安全。
#   　　之後如果後台又出現新的訂單編號前綴，記得要加進這個清單。
# v2026.07.06
# - 新增 PURCHASE_FILTER_PARAMS_TEMPLATE，並修正 verify_batch_order_consistency
#   查詢 /purchase 時原本只送 {"orderNo": ...} 或 {"phone": ...} 單一參數，
#   跟後台搜尋表單瀏覽器實際送出的參數（所有欄位都會帶上，只是空字串）不同，
#   可能觸發後台不同的預設篩選邏輯，導致查到的結果比預期少。現在統一以完整
#   樣板為底，只覆蓋真正要篩選的欄位（配合 quick_order.py v8.23 同步修正）。
# v2026.07.05
# - 新增 run_batch_consistency_check：把一致性檢查從 run_process_web 內部抽出來，
#   改成獨立函式，只在「整批列都執行完」之後由 ordersapp.py 呼叫一次，而不是
#   原本每呼叫一次 run_process_web（每一列）就各自比對一次——原寫法會讓同一支
#   電話在多列批次裡被重複查詢很多次，也不是真正「全部成單到一個段落後」的
#   整批核對。run_process_web 不再自動觸發一致性檢查。
# - verify_batch_order_consistency 擴充為雙向比對：
#   方向一（從 Google Sheet 比對系統）：原本只比對電話/日期/時段，這次加入
#   地址比對（依電話/地址/日期/時間四項），更嚴謹地確認訂單編號沒有誤配對。
#   方向二（新增，從系統的日期區間比對 Google Sheet）：以這批次涉及的每支
#   電話，查詢系統該電話底下落在這批次日期範圍內的實際訂單，確認每一筆都能
#   對應回 Google Sheet 某一列寫下的訂單編號，抓出「系統其實已經成單，但
#   Google Sheet 沒有正確記錄（M欄空白或寫錯）」這種方向一照不到的死角。
# v2026.07.04
# - 新增檸檬人排班工具函式（VALUE_TO_SHIFT_CODE / ensure_lemon_cleaner_shifts 等，
#   邏輯與 quick_order.py 一致），process_one_group 新增 allow_auto_lemon_shift
#   參數（預設 False）：查無班表時，只有客服明確勾選才會自動補檸檬人排班，
#   不再查不到班表就自動嘗試。run_process_web / run_process 皆已貫穿此參數，
#   讓「批次」跟「舊客/新客/訂單轉換/儲值金補價差」五個成單功能共用同一套邏輯。
# - 修正 fetch_order_no_by_date_and_period / match_order_from_purchase_page：
#   原本只比對「日期＋時段」，未比對電話，導致同一天同時段有多筆不同客人訂單時，
#   可能誤配對到別人的訂單編號，造成 Google Sheet 訂單編號欄（M欄）重複、
#   實際上這一列並沒有真的成單。現在改為同時比對電話，並排除本次批次已用過的
#   訂單編號。
# - 新增 verify_batch_order_consistency：批次執行完畢、回填 Google Sheet 後，
#   自動逐列比對「電話、日期、時段」是否跟寫回的訂單編號實際對應的後台訂單一致，
#   抓出訂單編號誤配對、重複寫入、或該列其實沒有真的成單的情況，結果會透過
#   run_process_web 回傳的 consistency_problems 提供給 ordersapp.py 顯示。
# 開發歷史（此版本之前無版本標示紀錄，檔案主體邏輯延續既有「儲值金系統設定」）：
# - 原始檔案標示：儲值金系統設定.py 版本：2026-05-03-final-staff-notice-aa
# ============================================================
# -*- coding: utf-8 -*-
import os
import re
import json
import time
import html
from datetime import datetime, timedelta, timezone
from collections import defaultdict

import requests
import pandas as pd
from bs4 import BeautifulSoup

import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from accounts import ACCOUNTS
from env import (
    ENV,
    BASE_URL_DEV,
    BASE_URL_PROD,
    GOOGLE_SHEET_ID,
    ENABLE_GCAL_COLOR_SYNC,
    GOOGLE_CALENDAR_MAP,
    GOOGLE_SERVICE_ACCOUNT_FILE,
    COLOR_PURPLE,
    COLOR_YELLOW,
    REQUEST_DELAY,
    ORDER_PREFIX_DEV,
    ORDER_PREFIX_PROD,
)

try:
    import streamlit as st
except Exception:
    st = None

try:
    from env import GOOGLE_MAPS_API_KEY
except Exception:
    GOOGLE_MAPS_API_KEY = ""


# =========================
# 環境
# =========================
if ENV == "dev":
    BASE_URL = BASE_URL_DEV
    ORDER_PREFIX = ORDER_PREFIX_DEV
else:
    BASE_URL = BASE_URL_PROD
    ORDER_PREFIX = ORDER_PREFIX_PROD

LOGIN_URL = f"{BASE_URL}/login"
BOOKING_URL = f"{BASE_URL}/booking/stored_value_routine"
PURCHASE_URL = f"{BASE_URL}/purchase"
GET_MEMBER_URL = f"{BASE_URL}/ajax/get_member"
CHECK_CONTAIN_URL = f"{BASE_URL}/ajax/check_contain"
CALCULATE_HOUR_URL = f"{BASE_URL}/ajax/calculate_hour"
GET_SECTION_URL = f"{BASE_URL}/ajax/get_section"
MAIL_SUCCESS_URL = f"{BASE_URL}/purchase/mail_success/{{order_no}}"

HEADERS = {"User-Agent": "Mozilla/5.0"}

# v2026.07.05：後台 /purchase 訂單列表頁的搜尋表單，瀏覽器送出時會帶上全部
# 欄位（沒填的欄位是空字串，不是完全不送）。如果我們用 requests 查詢時只帶
# 想篩選的那一兩個參數（例如只送 phone），後台某些邏輯是用「這個參數有沒有
# 出現在請求裡」而不是「值是不是空字串」來判斷，可能會觸發跟瀏覽器不一樣的
# 預設篩選（例如自動加上當月日期區間），導致查到的結果變少甚至查無資料。
# 所以查詢時一律以這份樣板為底，只覆蓋真正要篩選的欄位，其餘保持空字串。
PURCHASE_FILTER_PARAMS_TEMPLATE = {
    "keyword": "", "name": "", "phone": "", "orderNo": "",
    "date_s": "", "date_e": "", "clean_date_s": "", "clean_date_e": "",
    "paid_at_s": "", "paid_at_e": "", "refundDateS": "", "refundDateE": "",
    "buy": "", "area_id": "", "isCharge": "", "isRefund": "",
    "payway": "", "purchase_status": "", "progress_status": "",
    "invoiceStatus": "", "otherFee": "", "orderBy": "",
}
MAIL_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "User-Agent": "Mozilla/5.0",
    "Referer": PURCHASE_URL,
}

CLEAN_TYPE_MAP = {
    "居家清潔": "1",
    "辦公室清潔": "2",
    "裝修細清": "3",
}

# v2026.07.06：訂單編號目前已知前綴有 LC（一般訂單）、TT（測試站/儲值金折抵
# 消費訂單）、KK（儲值金購買訂單，這次才發現）。之前只認 LC/TT，導致 KK 開頭
# 的訂單完全沒被辨識成一張訂單卡片的起點，解析會出錯或漏掉整張訂單。
# 沒有改成更寬鬆的「任兩個大寫字母＋數字」，是因為發票號碼（例如
# TF27826169、FG82592263）剛好也符合這個格式，會被誤判成訂單編號，反而把
# 訂單卡片切錯位置。如果之後後台又出現新的訂單編號前綴，要記得加在這裡。
ORDER_NO_REGEX = r"(LC|TT|KK)\d+"

# 保留舊版可穩定比對班表的系統時段
STANDARD_SLOTS = [
    "08:30-12:30",
    "09:00-11:00",
    "09:00-12:00",
    "14:00-16:00",
    "14:00-17:00",
    "14:00-18:00",
    "09:00-16:00",
    "09:00-18:00",
]

KNOWN_SERVICE_STATUS = [
    "已處理",
    "未處理",
    "處理中",
    "已完成",
    "已取消",
    "待處理",
]

print("=== 儲值金系統設定.py 版本：2026-05-03-final-staff-notice-aa ===")


# =========================
# 基本工具
# =========================
def is_blank(value):
    return str(value).strip() in ("", "nan", "None")


def normalize_phone(phone_value):
    phone = str(phone_value).strip().replace(".0", "")
    phone = re.sub(r"\D", "", phone)
    if len(phone) == 9:
        phone = "0" + phone
    return phone


def normalize_text_for_parse(text):
    return re.sub(r"\s+", "", str(text or ""))


def normalize_addr_for_match(addr):
    return re.sub(r"\s+", "", str(addr or "")).strip()


def same_address(a, b):
    return normalize_addr_for_match(a) == normalize_addr_for_match(b)


def first_nonzero(*values, default="0"):
    for value in values:
        text = str(value if value is not None else "").strip()
        if text not in ("", "0", "0.0", "nan", "None"):
            return text
    return str(default)


def find_nested_value(obj, keys):
    key_set = {str(k) for k in keys}

    if isinstance(obj, dict):
        for key, value in obj.items():
            if str(key) in key_set and value not in (None, ""):
                return value

        for value in obj.values():
            found = find_nested_value(value, key_set)
            if found not in (None, ""):
                return found

    elif isinstance(obj, list):
        for item in obj:
            found = find_nested_value(item, key_set)
            if found not in (None, ""):
                return found

    return ""


def parse_date_value(date_value):
    if isinstance(date_value, pd.Timestamp):
        return date_value.to_pydatetime()

    text = str(date_value).strip()
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            pass

    raise Exception(f"無法解析日期: {date_value}")


def get_date_str(date_value):
    return parse_date_value(date_value).strftime("%Y-%m-%d")


def normalize_sheet_date(date_value):
    return get_date_str(date_value)


def is_weekend(date_value):
    return parse_date_value(date_value).weekday() >= 5


def get_unit_price_by_date(date_value):
    return 700 if is_weekend(date_value) else 600


def parse_time_slot(start_time_str, end_time_str):
    if not str(start_time_str).strip() or not str(end_time_str).strip():
        raise Exception(f"開始時間或結束時間為空：{start_time_str} / {end_time_str}")

    def to_hm(t):
        text = str(t).strip()
        parts = text.split(":")
        if not parts or not parts[0].strip():
            raise Exception(f"時間格式錯誤：{t}")
        h = int(parts[0])
        m = int(parts[1]) if len(parts) > 1 and parts[1].strip() else 0
        return h, m

    sh, sm = to_hm(start_time_str)
    eh, em = to_hm(end_time_str)
    return sh, sm, eh, em


def calc_hours_from_time(start_time_str, end_time_str):
    sh, sm, eh, em = parse_time_slot(start_time_str, end_time_str)
    hours = (eh - sh) + (em - sm) / 60.0
    return hours if hours > 0 else None


def calc_effective_hours_from_time(start_time_str, end_time_str):
    hours = calc_hours_from_time(start_time_str, end_time_str)
    if hours is None:
        return None
    if hours >= 7:
        hours -= 1
    return hours


def normalize_period_text(start_time_str, end_time_str):
    sh, sm, eh, em = parse_time_slot(start_time_str, end_time_str)
    return f"{sh:02d}:{sm:02d}-{eh:02d}:{em:02d}"


def display_period_text(start_time_str, end_time_str):
    sh, sm, eh, em = parse_time_slot(start_time_str, end_time_str)
    return f"{sh:02d}:{sm:02d} - {eh:02d}:{em:02d}"


def normalize_sheet_period(start_time_str, end_time_str):
    return normalize_period_text(start_time_str, end_time_str)


def build_target_slot_from_row(row):
    date_part = normalize_sheet_date(row["日期"])
    period_part = normalize_sheet_period(row["開始時間"], row["結束時間"])
    return f"{date_part}_{period_part}"


def slot_duration_hours(slot_text):
    start_text, end_text = slot_text.split("-")
    return calc_effective_hours_from_time(start_text, end_text)


def slot_start_hour(slot_text):
    return int(slot_text.split("-")[0].split(":")[0])


def is_morning_slot(slot_text):
    return slot_start_hour(slot_text) < 12


def map_to_system_slot(start_time_str, end_time_str, service_text=None):
    """
    重要規則：
    1. Google Sheet 的開始/結束時間 = 客戶實際要約的服務時段，也用來查班表。
       例如 Sheet 是 09:00-12:00，就一定查 09:00-12:00。
    2. calculate_hour 回傳的 hour 只用來算價格，不用來反推班表時段。
    3. 只有特殊時段 10:00-12:00，要送系統 09:00-11:00，並在簡訊/客備註記原始時間。
    """
    original_slot = normalize_period_text(start_time_str, end_time_str)

    if original_slot == "10:00-12:00":
        return {
            "original_slot": original_slot,
            "system_slot": "09:00-11:00",
            "need_note": True,
            "sms_time": original_slot,
            "customer_time_note": f"服務時間：{original_slot}",
        }

    # 標準時段直接用 Sheet 原始時段，不用 hour 反推
    if original_slot in STANDARD_SLOTS:
        return {
            "original_slot": original_slot,
            "system_slot": original_slot,
            "need_note": False,
            "sms_time": "",
            "customer_time_note": "",
        }

    # 非標準時段才用服務時數對應系統可送時段
    actual_hours = None

    if service_text and str(service_text).strip():
        match = re.search(r"(\d+)\s*人\s*(\d+(?:\.\d+)?)\s*小時", str(service_text))
        if match:
            actual_hours = float(match.group(2))
        else:
            match = re.search(r"(\d+(?:\.\d+)?)\s*小時", str(service_text))
            if match:
                actual_hours = float(match.group(1))

    if actual_hours is None:
        actual_hours = calc_effective_hours_from_time(start_time_str, end_time_str)

    if actual_hours is None:
        raise Exception(f"無法解析服務時段: {start_time_str}-{end_time_str}")

    sh, sm, eh, em = parse_time_slot(start_time_str, end_time_str)
    original_is_morning = sh < 12

    matched_slot = None
    for slot in STANDARD_SLOTS:
        if is_morning_slot(slot) == original_is_morning and abs(slot_duration_hours(slot) - actual_hours) < 1e-9:
            matched_slot = slot
            break

    if not matched_slot:
        raise Exception(f"找不到可對應的系統時段：原始時段 {original_slot}，時數 {actual_hours}")

    return {
        "original_slot": original_slot,
        "system_slot": matched_slot,
        "need_note": True,
        "sms_time": original_slot,
        "customer_time_note": f"服務時間：{original_slot}",
    }


def parse_service_human_hour(service_text, start_time, end_time):
    """
    最終規則：
    1. 預設 2 人。
    2. 預設時數 = Google Sheet 開始/結束時間換算。
    3. 若 A欄/服務人時 有明確寫「3人4小時」，則人數與時數都以 A欄為準。
    """
    people = 2
    hours = calc_effective_hours_from_time(start_time, end_time)

    if service_text and str(service_text).strip():
        text = str(service_text).strip()

        people_match = re.search(r"(\d+)\s*人", text)
        if people_match:
            people = int(people_match.group(1))

        hour_match = re.search(r"(\d+(?:\.\d+)?)\s*小時", text)
        if hour_match:
            hours = float(hour_match.group(1))

    if hours is None:
        return people, None

    return people, int(hours) if float(hours).is_integer() else hours


def normalize_hours_text(cell_value, start_time_str=None, end_time_str=None):
    people, hours = parse_service_human_hour(cell_value, start_time_str, end_time_str)
    if hours is None:
        return f"{people}人"
    htxt = f"{int(hours)}小時" if float(hours).is_integer() else f"{hours}小時"
    return f"{people}人{htxt}"


def build_group_key(row):
    normalized_human_hour = normalize_hours_text(
        row["服務人時"],
        row["開始時間"],
        row["結束時間"],
    )
    return (
        str(row["姓名"]).strip(),
        normalize_phone(row["電話"]),
        str(row["地址"]).strip(),
        str(row["購買項目"]).strip(),
        normalize_period_text(row["開始時間"], row["結束時間"]),
        normalized_human_hour,
        str(row["備註"]).strip(),
    )


def get_region_by_address(address, accounts_config):
    for region, config in accounts_config.items():
        keywords = config.get("address_keywords", [])
        if keywords:
            for kw in keywords:
                if kw in address:
                    return region
        else:
            if region == "台北" and ("台北市" in address or "新北市" in address):
                return region
            if region == "台中" and "台中市" in address:
                return region
            if region == "桃園" and "桃園" in address:
                return region
            if region == "新竹" and ("新竹市" in address or "新竹縣" in address):
                return region
            if region == "高雄" and ("高雄市" in address or "台南市" in address):
                return region
    return None


def should_process_row(row):
    return str(row.get("狀態", "")).strip() == "未安排" and is_blank(row.get("訂單編號", ""))


def should_create_order(row):
    return str(row.get("狀態", "")).strip() == "未安排" and is_blank(row.get("訂單編號", ""))


# =========================
# XYZ / 回填模板
# =========================
def finalize_xyz(meta=None, fallback_fare="0"):
    meta = meta or {}

    staff_raw = str(meta.get("服務人員", "") or "").strip()
    staff = normalize_staff_display(staff_raw) if staff_raw else ""
    status = str(meta.get("服務狀態", "") or "").strip()
    fare = str(meta.get("車馬費", "") or "").strip()

    if not staff:
        staff = "無人力"
    if not status:
        status = "未處理"
    if not fare:
        fare = str(fallback_fare or "0").strip() or "0"

    return {
        "服務人員": staff,
        "服務狀態": status,
        "車馬費": fare,
    }


def build_row_result(
    order_no="",
    result="失敗",
    reason="",
    no_slot_date="",
    insufficient_date="",
    sms_time="",
    customer_note="",
    service_notice="",
    confirm_mail="",
    calendar_result="",
    calendar_reason="",
    calendar_old="",
    calendar_new="",
    status_value="",
    staff="無人力",
    service_status="未處理",
    fare="0",
):
    xyz = finalize_xyz(
        {
            "服務人員": staff,
            "服務狀態": service_status,
            "車馬費": fare,
        },
        fallback_fare=fare or "0",
    )

    return {
        "訂單編號": order_no,
        "結果": result,
        "原因": reason,
        "沒班表日期": no_slot_date,
        "餘額不足未送": insufficient_date,
        "簡訊實際服務時間": sms_time,
        "客人備註": customer_note,
        "客服備註": service_notice,
        "確認信": confirm_mail,
        "日曆改色結果": calendar_result,
        "日曆改色原因": calendar_reason,
        "日曆原色": calendar_old,
        "日曆新色": calendar_new,
        "狀態": status_value,
        "服務人員": xyz["服務人員"],
        "服務狀態": xyz["服務狀態"],
        "車馬費": xyz["車馬費"],
    }


# =========================
# Google 憑證 / Sheet
# =========================
def get_service_account_info():
    if st is not None:
        try:
            if "gcp_service_account" in st.secrets:
                return dict(st.secrets["gcp_service_account"])
            if "GOOGLE_SERVICE_ACCOUNT" in st.secrets:
                return dict(st.secrets["GOOGLE_SERVICE_ACCOUNT"])
        except Exception:
            pass

    raw_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
    if raw_json:
        try:
            return json.loads(raw_json)
        except Exception as e:
            raise Exception(f"GOOGLE_SERVICE_ACCOUNT_JSON 不是合法 JSON：{e}")

    candidate_files = []
    if GOOGLE_SERVICE_ACCOUNT_FILE:
        candidate_files.append(GOOGLE_SERVICE_ACCOUNT_FILE)
    candidate_files.append("google_service_account.json")

    for fp in candidate_files:
        if fp and os.path.exists(fp):
            with open(fp, "r", encoding="utf-8") as f:
                return json.load(f)

    raise FileNotFoundError(
        "找不到 Google 憑證。請在 Streamlit secrets 設定 gcp_service_account 或 GOOGLE_SERVICE_ACCOUNT，"
        "或提供 GOOGLE_SERVICE_ACCOUNT_JSON，或放置 google_service_account.json。"
    )


def build_gsheet_client():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    service_account_info = get_service_account_info()
    creds = Credentials.from_service_account_info(service_account_info, scopes=scopes)
    return gspread.authorize(creds)


def load_worksheet(sheet_name):
    client = build_gsheet_client()
    sh = client.open_by_key(GOOGLE_SHEET_ID)
    ws = sh.worksheet(sheet_name)

    values = ws.get_all_values()
    if not values:
        raise Exception(f"工作表 {sheet_name} 沒有資料")

    headers = values[0]
    rows = values[1:]
    df = pd.DataFrame(rows, columns=headers)
    df["__sheet_row__"] = range(2, len(df) + 2)
    return ws, df


def ensure_columns_in_sheet(ws):
    headers = ws.row_values(1)
    required = [
        "簡訊實際服務時間",
        "客人備註",
        "客服備註",
        "訂單編號",
        "結果",
        "原因",
        "沒班表日期",
        "餘額不足未送",
        "確認信",
        "日曆改色結果",
        "日曆改色原因",
        "日曆原色",
        "日曆新色",
        "狀態",
        "服務人員",
        "服務狀態",
        "車馬費",
    ]

    changed = False
    for col in required:
        if col not in headers:
            headers.append(col)
            changed = True

    if changed:
        ws.resize(rows=max(ws.row_count, 1), cols=len(headers))
        ws.update("A1", [headers])

    return headers


def set_customer_notice_clip_style(ws, headers=None, row_numbers=None):
    """
    Google Sheet 顯示規則：
    客服備註內容完整保留，但儲存格視覺上使用「自動裁剪 / CLIP」，
    避免長備註自動換行把列高撐高。
    """
    try:
        headers = headers or ws.row_values(1)
        if "客服備註" not in headers:
            return

        col_index = headers.index("客服備註")  # 0-based
        sheet_id = ws.id

        service_account_info = get_service_account_info()
        creds = Credentials.from_service_account_info(
            service_account_info,
            scopes=["https://www.googleapis.com/auth/spreadsheets"],
        )
        service = build("sheets", "v4", credentials=creds)

        requests_body = [
            {
                "repeatCell": {
                    "range": {
                        "sheetId": sheet_id,
                        "startRowIndex": 1,
                        "startColumnIndex": col_index,
                        "endColumnIndex": col_index + 1,
                    },
                    "cell": {
                        "userEnteredFormat": {
                            "wrapStrategy": "CLIP"
                        }
                    },
                    "fields": "userEnteredFormat.wrapStrategy",
                }
            }
        ]

        # 只固定本次有寫入的資料列，避免長備註撐高列高。
        # row_numbers 是 Google Sheet 的 1-based row number；API 是 0-based index。
        if row_numbers:
            for row_num in sorted(set(int(x) for x in row_numbers if int(x) > 1)):
                requests_body.append(
                    {
                        "updateDimensionProperties": {
                            "range": {
                                "sheetId": sheet_id,
                                "dimension": "ROWS",
                                "startIndex": row_num - 1,
                                "endIndex": row_num,
                            },
                            "properties": {
                                "pixelSize": 21
                            },
                            "fields": "pixelSize",
                        }
                    }
                )

        service.spreadsheets().batchUpdate(
            spreadsheetId=GOOGLE_SHEET_ID,
            body={"requests": requests_body},
        ).execute()

    except Exception as e:
        print(f"設定客服備註欄位自動裁剪失敗: {e}")


def update_sheet_rows(ws, row_results):
    headers = ensure_columns_in_sheet(ws)
    header_index = {h: i + 1 for i, h in enumerate(headers)}
    updates = []

    for row_num, info in row_results.items():
        xyz = finalize_xyz(
            {
                "服務人員": info.get("服務人員", ""),
                "服務狀態": info.get("服務狀態", ""),
                "車馬費": info.get("車馬費", ""),
            },
            fallback_fare=info.get("車馬費", "0"),
        )
        info["服務人員"] = xyz["服務人員"]
        info["服務狀態"] = xyz["服務狀態"]
        info["車馬費"] = xyz["車馬費"]

        for key, value in info.items():
            if key not in header_index:
                continue

            # I欄「狀態」只允許在成功完成流程時寫入「已安排」。
            # 其他空白或非已安排值都不覆蓋原本的「未安排」。
            if key == "狀態" and str(value).strip() != "已安排":
                continue

            updates.append({
                "range": gspread.utils.rowcol_to_a1(row_num, header_index[key]),
                "values": [[("" if value is None else str(value))]],
            })

    if updates:
        ws.batch_update(updates)
        set_customer_notice_clip_style(ws, headers=headers, row_numbers=row_results.keys())


# =========================
# 後台 API
# =========================
def login(session, email, password):
    resp = session.get(LOGIN_URL, headers=HEADERS, allow_redirects=True)
    if resp.status_code != 200:
        return False

    soup = BeautifulSoup(resp.text, "html.parser")
    token_input = soup.find("input", {"name": "_token"})
    if not token_input:
        return False

    token = token_input.get("value", "").strip()
    if not token:
        return False

    resp = session.post(
        LOGIN_URL,
        data={"_token": token, "email": email, "password": password},
        headers=HEADERS,
        allow_redirects=True,
    )
    return resp.status_code == 200 and "login" not in resp.url.lower()


def get_csrf_token(session):
    resp = session.get(BOOKING_URL, headers=HEADERS, allow_redirects=True)
    if resp.status_code != 200:
        raise Exception(f"取得儲值金訂單頁失敗: {resp.status_code}")

    soup = BeautifulSoup(resp.text, "html.parser")
    token_input = soup.find("input", {"name": "_token"})
    if not token_input:
        raise Exception("無法從儲值金訂單頁提取 _token")

    token = token_input.get("value", "").strip()
    if not token:
        raise Exception("_token 為空")

    return token


def get_member(session, phone, token, clean_type_id):
    resp = session.post(
        GET_MEMBER_URL,
        data={"phone": phone, "_token": token, "clean_type_id": clean_type_id},
        headers=HEADERS,
        allow_redirects=True,
    )
    if resp.status_code != 200:
        return None

    try:
        result = resp.json()
    except Exception:
        return None

    return result if isinstance(result, dict) and result.get("return_code") == "0000" and result.get("member") else None


def _extract_cleaner_roster_from_member_edit_html(soup):
    """
    v2026.07.07 新功能：從會員編輯頁（/member/edit/{id}）解析「喜愛專員」
    /「不喜愛專員」兩區塊的完整專員名單，回傳 {cleaner_id: {"name":..., "liked":bool, "disliked":bool}}。
    這兩區塊列的是同一份完整專員名單，一份用 name="cleaner[]"（喜愛，checked=目前已設為喜愛），
    一份用 name="no_cleaner[]"（不喜愛）。用這份名單可以把「近期服務專員姓名」對應回專員 id，
    才能在送出表單時正確勾選/取消勾選對應的 checkbox。
    """
    roster = {}
    for input_tag in soup.find_all("input", attrs={"name": "cleaner[]"}):
        cid = str(input_tag.get("value", "")).strip()
        if not cid:
            continue
        label = soup.find("label", attrs={"for": input_tag.get("id", "")})
        name = re.sub(r"\[\d+\]\s*$", "", label.get_text(strip=True)) if label else ""
        roster.setdefault(cid, {"name": name, "liked": False, "disliked": False})
        roster[cid]["name"] = name or roster[cid]["name"]
        roster[cid]["liked"] = bool(input_tag.has_attr("checked"))
    for input_tag in soup.find_all("input", attrs={"name": "no_cleaner[]"}):
        cid = str(input_tag.get("value", "")).strip()
        if not cid:
            continue
        label = soup.find("label", attrs={"for": input_tag.get("id", "")})
        name = re.sub(r"\[\d+\]\s*$", "", label.get_text(strip=True)) if label else ""
        roster.setdefault(cid, {"name": name, "liked": False, "disliked": False})
        roster[cid]["name"] = name or roster[cid]["name"]
        roster[cid]["disliked"] = bool(input_tag.has_attr("checked"))
    return roster


def fetch_member_edit_page(session, member_id):
    """
    v2026.07.07 新功能：讀取會員編輯頁（/member/edit/{member_id}），解析出：
    - token：這頁的 _token（跟登入 session 共用的 _token 不同，每頁可能不一樣）
    - fields：其他要一起送出、不能遺漏的既有欄位值（姓名/電話/Email/備註等），
      避免更新喜好時把這些欄位意外清空
    - roster：完整專員名單，含目前的喜愛/不喜愛勾選狀態
    """
    resp = session.get(f"{BASE_URL}/member/edit/{member_id}", headers=HEADERS, allow_redirects=True)
    if resp.status_code != 200:
        raise Exception(f"讀取會員編輯頁失敗（HTTP {resp.status_code}），member_id={member_id}")
    soup = BeautifulSoup(resp.text, "html.parser")

    def _val(name):
        tag = soup.find(attrs={"name": name})
        return str(tag.get("value", "")).strip() if tag else ""

    def _textarea(name):
        tag = soup.find("textarea", attrs={"name": name})
        return tag.get_text() if tag else ""

    def _selected(name):
        sel = soup.find("select", attrs={"name": name})
        if not sel:
            return ""
        opt = sel.find("option", attrs={"selected": True})
        return str(opt.get("value", "")).strip() if opt else ""

    def _checked_radio(name):
        tag = soup.find("input", attrs={"name": name, "checked": True})
        return str(tag.get("value", "")).strip() if tag else ""

    token_tag = soup.find("input", attrs={"name": "_token"})
    fields = {
        "member_level_id": _selected("member_level_id"),
        "price_vvip": _val("price_vvip"),
        "name": _val("name"),
        "phone": _val("phone"),
        "tel": _val("tel"),
        "email": _val("email"),
        "fbName": _val("fbName"),
        "fb": _val("fb"),
        "line": _val("line"),
        "memoProcess": _textarea("memoProcess"),
        "memoFinance": _textarea("memoFinance"),
        "flag": _checked_radio("flag") or "1",
        "id": _selected("id"),
        "frequency_id": _selected("frequency_id"),
        "notice": _textarea("notice"),
        "preferredGender": _checked_radio("preferredGender") or "0",
    }
    return {
        "token": str(token_tag.get("value", "")).strip() if token_tag else "",
        "fields": fields,
        "roster": _extract_cleaner_roster_from_member_edit_html(soup),
    }


def submit_member_preferences(session, member_id, edit_page, preferred_gender, liked_ids, disliked_ids):
    """
    v2026.07.07 新功能：把更新後的「喜愛/不喜愛專員」跟「喜愛專員性別」送回
    /member/edit/{member_id}。liked_ids／disliked_ids 是完整的最終勾選清單
    （呼叫端已經處理好「互斥」——同一個專員不能同時喜愛又不喜愛），這裡只負責
    組表單送出，並沿用 fetch_member_edit_page 抓到的其他欄位，避免把姓名/
    電話/備註等既有資料意外清空。
    """
    fields = edit_page["fields"]
    data = {
        "member_level_id": fields["member_level_id"],
        "price_vvip": fields["price_vvip"],
        "pass": "",
        "name": fields["name"],
        "phone": fields["phone"],
        "tel": fields["tel"],
        "email": fields["email"],
        "fbName": fields["fbName"],
        "fb": fields["fb"],
        "line": fields["line"],
        "memoProcess": fields["memoProcess"],
        "memoFinance": fields["memoFinance"],
        "flag": fields["flag"],
        "id": fields["id"],
        "frequency_id": fields["frequency_id"],
        "notice": fields["notice"],
        "preferredGender": str(preferred_gender),
        "_token": edit_page["token"],
    }
    form_data = list(data.items())
    for cid in liked_ids:
        form_data.append(("cleaner[]", str(cid)))
    for cid in disliked_ids:
        form_data.append(("no_cleaner[]", str(cid)))

    resp = session.post(
        f"{BASE_URL}/member/edit/{member_id}",
        data=form_data,
        headers=HEADERS,
        allow_redirects=True,
    )
    if resp.status_code != 200:
        raise Exception(f"更新會員喜好失敗（HTTP {resp.status_code}）")
    return True


def fetch_recent_service_records(session, phone, name, n=5):
    """
    v2026.07.07 新功能：查詢某會員近 N 筆「有實際排班」的服務紀錄
    （服務日期＋專員姓名），用於畫面上讓客服勾選要設定喜愛/不喜愛的專員。
    只抓有 shift（schedule/edit 連結）的訂單，儲值金購買/尚未排班的訂單
    沒有專員資訊，直接跳過。
    """
    resp = session.get(
        f"{BASE_URL}/purchase",
        params={"phone": phone, "name": name},
        headers=HEADERS,
        allow_redirects=True,
    )
    if resp.status_code != 200:
        raise Exception(f"查詢服務紀錄失敗（HTTP {resp.status_code}）")
    soup = BeautifulSoup(resp.text, "html.parser")

    records = []
    for row in soup.find_all("tr"):
        cells = row.find_all("td")
        if len(cells) < 3:
            continue
        date_cell = cells[2]
        shift_links = date_cell.find_all("a", href=re.compile(r"/schedule/edit\?"))
        if not shift_links:
            continue
        # v2026.07.07 修正：<a> 連結內除了專員姓名（包在 <span> 裡）之外，
        # 後面還接著純文字的「(n)」評分數字，get_text() 會把整個 <a> 裡的文字
        # 全部串在一起，導致抓到「嚴慶隆(3)」而不是單純的「嚴慶隆」。這裡改成
        # 抓到文字後，把結尾的 (數字) 去掉，只保留姓名本身。
        cleaner_names = []
        for a in shift_links:
            raw_name = a.get_text(strip=True)
            clean_name = re.sub(r"\(\d+\)\s*$", "", raw_name).strip()
            if clean_name:
                cleaner_names.append(clean_name)
        date_text = date_cell.get_text(" ", strip=True)
        m = re.search(r"(\d{4}-\d{2}-\d{2})", date_text)
        date_clean = m.group(1) if m else ""
        order_no_tag = row.find("td")
        order_no_m = re.search(r"(LC|TT)\d+", order_no_tag.get_text() if order_no_tag else "")
        records.append({
            "date_clean": date_clean,
            "cleaner_names": cleaner_names,
            "order_no": order_no_m.group(0) if order_no_m else "",
        })
    records.sort(key=lambda r: r["date_clean"], reverse=True)
    return records[:n]


def pick_best_address_info(member_payload, target_address):
    """
    強制以真正下拉地址為主；沒有 addressId 視為沒選到下拉地址
    """
    member = member_payload.get("member", {}) if isinstance(member_payload, dict) else {}
    member_address_list = member.get("memberAddressList", []) if isinstance(member, dict) else []

    target_norm = normalize_addr_for_match(target_address)

    for item in member_address_list:
        item_addr = str(item.get("address", "")).strip()
        if normalize_addr_for_match(item_addr) == target_norm:
            return {
                "addressId": str(item.get("id", "")).strip(),
                "country_id": item.get("countryId", ""),
                "area_id": item.get("areaId", ""),
                "address": item_addr,
                "lat": item.get("lat", ""),
                "lng": item.get("lng", ""),
                "company_id": item.get("companyId", 1),
                "purchase": item.get("purchase", {}) if isinstance(item.get("purchase"), dict) else {},
            }

    return {}


def geocode_address(address):
    if not GOOGLE_MAPS_API_KEY:
        return None, None

    try:
        url = "https://maps.googleapis.com/maps/api/geocode/json"
        params = {
            "address": address,
            "language": "zh-TW",
            "key": GOOGLE_MAPS_API_KEY,
        }
        resp = requests.get(url, params=params, timeout=15)
        if resp.status_code != 200:
            return None, None

        data = resp.json()
        results = data.get("results", [])
        if not results:
            return None, None

        location = results[0].get("geometry", {}).get("location", {})
        lat = location.get("lat")
        lng = location.get("lng")
        if lat is None or lng is None:
            return None, None

        return str(lat), str(lng)
    except Exception:
        return None, None


def check_contain(session, member_id, address, lat, lng, token, clean_type_id):
    resp = session.post(
        CHECK_CONTAIN_URL,
        data={
            "memberId": member_id,
            "cleanTypeId": clean_type_id,
            "address": address,
            "lat": lat or "",
            "lng": lng or "",
            "_token": token,
        },
        headers=HEADERS,
        allow_redirects=True,
    )
    if resp.status_code != 200:
        return None

    try:
        return resp.json()
    except Exception:
        return None


def calculate_hour(session, order_data, token):
    data = order_data.copy()
    data["_token"] = token

    resp = session.post(CALCULATE_HOUR_URL, data=data, headers=HEADERS, allow_redirects=True)
    if resp.status_code != 200:
        return None

    try:
        return resp.json()
    except Exception:
        return None


def extract_calc_fields(calc_result, fallback_hours="", fallback_fare="0"):
    """
    calculate_hour 的回傳格式可能是 dict/list/html/string。
    手動流程是先送 hour/price/fare 空值，後台回傳後再填入：
    hour=4, price=4771, fare=200。
    這裡用遞迴 + 字串 regex 雙重解析。
    """
    def regex_find(text, names):
        text = str(text or "")
        for name in names:
            patterns = [
                rf'"{re.escape(name)}"\s*:\s*"?([0-9]+(?:\.[0-9]+)?)"?',
                rf"'{re.escape(name)}'\s*:\s*'?([0-9]+(?:\.[0-9]+)?)'?",
                rf'name=["\\\']{re.escape(name)}["\\\'][^>]*value=["\\\']?([0-9]+(?:\.[0-9]+)?)',
                rf'id=["\\\']{re.escape(name)}["\\\'][^>]*value=["\\\']?([0-9]+(?:\.[0-9]+)?)',
                rf'{re.escape(name)}=([0-9]+(?:\.[0-9]+)?)',
            ]
            for pat in patterns:
                m = re.search(pat, text)
                if m:
                    return m.group(1)
        return ""

    if isinstance(calc_result, (dict, list)):
        hour = find_nested_value(calc_result, [
            "hour", "clean_hour", "hours", "total_hour", "service_hour"
        ])
        price = find_nested_value(calc_result, [
            "price", "total_price", "service_price", "amount", "total", "money"
        ])
        price_vvip = find_nested_value(calc_result, [
            "price_vvip", "vvip_price", "vip_price"
        ])
        fare = find_nested_value(calc_result, [
            "fare", "car_fare", "traffic_fee", "trafficFee", "carFare", "車馬費"
        ])
    else:
        hour = price = price_vvip = fare = ""

    raw_text = json.dumps(calc_result, ensure_ascii=False) if isinstance(calc_result, (dict, list)) else str(calc_result or "")

    if not hour:
        hour = regex_find(raw_text, ["hour", "clean_hour", "hours", "total_hour", "service_hour"])
    if not price:
        price = regex_find(raw_text, ["price", "total_price", "service_price", "amount", "total", "money"])
    if not price_vvip:
        price_vvip = regex_find(raw_text, ["price_vvip", "vvip_price", "vip_price"])
    if not fare:
        fare = regex_find(raw_text, ["fare", "car_fare", "traffic_fee", "trafficFee", "carFare"])

    return {
        "hour": str(hour or fallback_hours or ""),
        "price": first_nonzero(price, default="0"),
        "price_vvip": str(price_vvip or "0"),
        "fare": first_nonzero(fare, fallback_fare, default="0"),
    }


def get_section_raw(session, order_data, token, date_slot):
    data = order_data.copy()
    data["_token"] = token
    data["date_list[]"] = date_slot

    resp = session.post(GET_SECTION_URL, data=data, headers=HEADERS, allow_redirects=True)
    return resp.text if resp.status_code == 200 else ""


def extract_cleaners_from_section_response(raw_text, date_slot):
    """
    從 get_section 回傳抓指定日期/時段的人員。
    支援 JSON list：
    [{"date":"2026-05-14","section":"14:00-18:00","cleaner":["胡偉勝"]}]
    """
    if not raw_text:
        return []

    date_part, period_part = date_slot.split("_", 1)
    raw = str(raw_text)

    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            data = data.get("data") or data.get("result") or data.get("sections") or []
        if isinstance(data, list):
            for item in data:
                if not isinstance(item, dict):
                    continue
                item_date = str(item.get("date", "")).strip()
                item_section = str(item.get("section", "")).strip().replace(" ", "")
                if item_date == date_part and item_section == period_part.replace(" ", ""):
                    cleaners = (
                        item.get("cleaner")
                        or item.get("cleaners")
                        or item.get("staff")
                        or item.get("staffs")
                        or item.get("cleaner_name")
                        or item.get("cleanerName")
                        or item.get("name")
                        or item.get("text")
                        or item.get("title")
                        or ""
                    )
                    if isinstance(cleaners, list):
                        return [str(x).strip().lstrip("＊*") for x in cleaners if str(x).strip()]
                    if isinstance(cleaners, str) and cleaners.strip():
                        m = re.search(r"[（(]([^）)]+)[）)]", cleaners)
                        text = m.group(1) if m else cleaners
                        return [x.strip().lstrip("＊*") for x in re.split(r"[,，、/]+", text) if x.strip()]
    except Exception:
        pass

    text = html.unescape(raw)
    try:
        text = BeautifulSoup(text, "html.parser").get_text(" ", strip=True)
    except Exception:
        pass

    compact = re.sub(r"\s+", "", text)
    d = date_part
    p = period_part.replace(" ", "")
    idx = compact.find(d)
    if idx >= 0:
        nearby = compact[idx:idx + 600]
        pidx = nearby.find(p)
        if pidx >= 0:
            nearby = nearby[pidx:pidx + 500]
            m = re.search(r"[（(]([^）)]+)[）)]", nearby)
            if m:
                return [x.strip().lstrip("＊*") for x in re.split(r"[,，、/]+", m.group(1)) if x.strip()]

    return []


def clean_staff_name(name):
    """
    將班表/訂單頁的人名清成純姓名。
    例：
    - 00洪暐智(4) -> 洪暐智
    - X蔡佩玲(1) -> 蔡佩玲
    - ＊黃惟芊 -> 黃惟芊
    - 吳豐閔 X X蔡佩玲 -> 會在 normalize_staff_display 再統一成 吳豐閔 X 蔡佩玲
    """
    text = html.unescape(str(name or "")).strip()
    if not text:
        return ""

    text = text.strip().lstrip("＊*").strip()
    text = re.sub(r"^[Xx×＊*\s]+", "", text).strip()
    text = re.sub(r"^\d+", "", text).strip()
    text = re.sub(r"[（(]\d+[）)]", "", text).strip()
    text = re.sub(r"^[Xx×\s]+", "", text).strip()
    text = re.sub(r"[Xx×\s]+$", "", text).strip()
    return text


def normalize_staff_display(value, limit=None):
    """
    X欄顯示規則：名字和名字中間只保留一個「 X 」。
    不管來源是 list、已經串好的字串、或含有 X姓名，都先拆開、清洗、再重組。
    """
    if value in (None, ""):
        return ""

    if isinstance(value, (list, tuple)):
        raw_parts = []
        for item in value:
            raw_parts.extend(re.split(r"\s*[Xx×]\s*|[,，、/]+", str(item or "")))
    else:
        raw_parts = re.split(r"\s*[Xx×]\s*|[,，、/]+", str(value or ""))

    cleaned = []
    seen = set()
    for part in raw_parts:
        name = clean_staff_name(part)
        if not name or name in seen:
            continue
        cleaned.append(name)
        seen.add(name)
        if limit and len(cleaned) >= int(limit):
            break

    return " X ".join(cleaned)


def format_staff_from_cleaners(cleaners, people=None):
    try:
        limit = int(people) if people not in (None, "") else None
    except Exception:
        limit = None

    staff = normalize_staff_display(cleaners or [], limit=limit)
    return staff if staff else "無人力"


def slot_exists_in_section_response(raw_text, date_slot):
    """
    get_section 回傳可能是 HTML、JSON 包 HTML、escaped HTML。
    這裡不要只做單一 regex，改成多種格式都可比對。
    """
    if not raw_text:
        return False

    date_part, period_part = date_slot.split("_", 1)
    start_part, end_part = period_part.split("-", 1)

    raw = str(raw_text)
    unescaped = html.unescape(raw)

    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            data = data.get("data") or data.get("result") or data.get("sections") or []
        if isinstance(data, list):
            for item in data:
                if not isinstance(item, dict):
                    continue
                item_date = str(item.get("date", "")).strip()
                item_section = str(item.get("section", "")).strip().replace(" ", "")
                if item_date == date_part and item_section == period_part.replace(" ", ""):
                    return True
    except Exception:
        pass

    try:
        soup_text = BeautifulSoup(unescaped, "html.parser").get_text(" ", strip=True)
    except Exception:
        soup_text = unescaped

    candidates = [raw, unescaped, soup_text]

    date_variants = list(dict.fromkeys([
        date_part,
        date_part.replace("-", "/"),
        date_part.replace("-", ""),
    ]))

    period_variants = list(dict.fromkeys([
        period_part,
        period_part.replace(" ", ""),
        f"{start_part} - {end_part}",
        f"{start_part}~{end_part}",
        f"{start_part}～{end_part}",
    ]))

    for text in candidates:
        compact = re.sub(r"\s+", "", text)

        for d in date_variants:
            for p in period_variants:
                dp = re.sub(r"\s+", "", d)
                pp = re.sub(r"\s+", "", p)
                if dp in compact and pp in compact:
                    date_idx = compact.find(dp)
                    period_idx = compact.find(pp)
                    if date_idx >= 0 and period_idx >= 0 and abs(period_idx - date_idx) < 500:
                        return True

        for d in date_variants:
            d_re = re.escape(d)
            s_re = re.escape(start_part)
            e_re = re.escape(end_part)
            patterns = [
                rf"{d_re}.{{0,500}}{s_re}\s*[-~～]\s*{e_re}",
                rf"{d_re}.{{0,500}}{re.escape(period_part)}",
            ]
            for pat in patterns:
                if re.search(pat, text, flags=re.S):
                    return True

    return False


# =========================
# 檸檬人勾班工具函式（v2026-07：與 quick_order.py 保持一致邏輯，供批次流程共用）
# =========================
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


def _period_to_shift_code(period_s):
    compact = str(period_s or "").replace(" ", "")
    return PERIOD_TO_SHIFT_CODE.get(compact, "")


def _shift_value_to_code(value):
    value = str(value or "").strip()
    return VALUE_TO_SHIFT_CODE.get(value, value)


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


def _parse_cleaner_shift_page(html_text, date_str=None):
    token_m = re.search(r'name=["\']_token["\'][^>]*value=["\']([^"\']+)["\']', html_text or "")
    csrf = token_m.group(1) if token_m else ""
    if not csrf:
        meta_m = re.search(r'<meta name="csrf-token" content="([^"]+)"', html_text or "")
        csrf = meta_m.group(1) if meta_m else ""
    checked_fields = []
    checked_codes_on_date = set()
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
            checked_codes_on_date.add(_shift_value_to_code(value))
    return csrf, checked_fields, checked_codes_on_date


def _get_cleaner_shift_form_info(session, base_url, cleaner_id, date_str):
    ym = str(date_str)[:7]
    resp = session.get(f"{base_url}/cleaner1/{cleaner_id}/shift", params={"month": ym}, headers=HEADERS, allow_redirects=True)
    if resp.status_code != 200:
        return "", [], set(), f"HTTP {resp.status_code}"
    csrf, checked_fields, checked_codes = _parse_cleaner_shift_page(resp.text, date_str)
    return csrf, checked_fields, checked_codes, ""


def _search_lemon_cleaners(session, base_url, target_month=None, min_needed=0):
    entries = []
    seen_ids = set()
    seen_names = set()
    target_month = str(target_month or datetime.today().strftime("%Y-%m"))[:7]
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
        page_html = resp.text or ""
        row_blocks = re.split(r"<tr\b", page_html, flags=re.I)
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
        for m in re.finditer(r"/cleaner1/(\d+)(?=[/'\"?#])", page_html, re.I):
            cid = m.group(1)
            ctx = page_html[max(0, m.start() - 1000): m.end() + 1000]
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
    return {
        "success": ok, "name": cleaner_name, "id": cleaner_id,
        "message": f"{cleaner_name} 已補勾 {date_str} {target_shift_code}" if ok else f"POST 失敗：HTTP {resp.status_code}",
        "checked": sorted(checked_codes), "target": target_shift_code,
    }


def ensure_lemon_cleaner_shifts(session, base_url, service_date, period_s, person_count):
    """
    v2026-07：查無班表時補勾檸檬人排班。與 quick_order.py 的同名函式邏輯一致，
    供批次（Google Sheet）流程共用，確保五個成單功能行為一致。
    呼叫端必須自行決定是否要在「查無班表」時呼叫本函式（由
    allow_auto_lemon_shift 參數控制），本函式本身不做開關判斷。
    """
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


# =========================
# Purchase 頁解析
# =========================
def extract_order_cards_from_purchase_html(html):
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text("\n", strip=True)
    lines = [line.strip() for line in text.splitlines() if line.strip()]

    blocks = []
    current = None

    for line in lines:
        if re.fullmatch(ORDER_NO_REGEX, line):
            if current:
                blocks.append(current)
            current = {"order_no": line, "lines": [line]}
        elif current:
            current["lines"].append(line)

    if current:
        blocks.append(current)

    return blocks


def match_order_from_purchase_page(html, target_date, target_period, phone="", exclude_order_nos=None):
    """
    v2026-07：比對日期＋時段，且若有提供 phone 則同時比對電話，避免只用
    日期+時段配對到別人的訂單（這是造成同一個訂單編號被誤寫進兩列
    Google Sheet「M欄重複」的根因——原本完全沒有比對電話）。
    exclude_order_nos 可排除本次批次已經用掉的訂單編號，進一步降低誤配對機率。
    """
    exclude_order_nos = exclude_order_nos or set()
    target_phone_norm = normalize_phone(phone) if phone else ""
    fallback_candidate = None
    for block in extract_order_cards_from_purchase_html(html):
        order_no_candidate = block.get("order_no")
        if not order_no_candidate or order_no_candidate in exclude_order_nos:
            continue
        joined = "\n".join(block["lines"])
        if target_date not in joined or target_period not in joined:
            continue
        if not target_phone_norm:
            return order_no_candidate
        joined_compact = re.sub(r"[-\s]", "", joined)
        if target_phone_norm in joined_compact:
            return order_no_candidate
        if fallback_candidate is None:
            fallback_candidate = order_no_candidate
    # 找不到電話完全相符的訂單時，退回原本「只比對日期+時段」的第一筆結果，
    # 並由呼叫端的一致性檢查（verify_batch_order_consistency）事後抓出異常。
    return fallback_candidate


def fetch_order_no_by_date_and_period(session, target_date, target_period, phone="", exclude_order_nos=None):
    resp = session.get(PURCHASE_URL, headers=HEADERS, allow_redirects=True)
    if resp.status_code != 200:
        return None
    return match_order_from_purchase_page(resp.text, target_date, target_period, phone=phone, exclude_order_nos=exclude_order_nos)


def _extract_staff_line(lines):
    joined = "\n".join(lines)
    normalized = normalize_text_for_parse(joined)

    # 支援任意人數的服務人員，例如：
    # 陳靜怡(3)X蔡宗原(5)X鄭蓓婷(1)
    # 余世煒(3)X黃惟芊(2)X檸檬人1(0)
    #
    # 舊寫法只抓到前兩個 group，因此 3 人以上會少顯示。
    # 這裡改成先找「連續 X 串接的人員群組」，並取人數最多的那一組。
    staff_token = r"[\u4e00-\u9fffA-Za-z0-9]+[（(]\d+[）)]"
    staff_group_pattern = rf"{staff_token}(?:[Xx×]{staff_token})+"

    groups = re.findall(staff_group_pattern, normalized)
    if groups:
        best_group = max(
            groups,
            key=lambda value: len(re.findall(staff_token, value)),
        )
        return normalize_staff_display(best_group)

    # 支援只有 1 位服務人員的訂單，例如：檸檬人1(0)
    singles = re.findall(staff_token, normalized)
    if singles:
        return normalize_staff_display(singles[0])

    return "無人力"


def _extract_status_line(lines):
    joined = "\n".join(lines)
    normalized = normalize_text_for_parse(joined)

    for status in KNOWN_SERVICE_STATUS:
        if status in normalized:
            return status

    if "未處理" in normalized:
        return "未處理"
    if "已處理" in normalized:
        return "已處理"

    return "未處理"


def _extract_fare_line(lines):
    joined = "\n".join(lines)
    normalized = normalize_text_for_parse(joined)

    m = re.search(r'車馬費[：:]?(\d+)', normalized)
    if m:
        return m.group(1)

    return "0"


def _extract_service_date_time(lines):
    service_date = ""
    service_time = ""

    for idx, line in enumerate(lines):
        text = line.strip()
        if re.match(r"\d{4}-\d{2}-\d{2}", text):
            service_date = text[:10]

            for j in range(idx + 1, min(idx + 5, len(lines))):
                nxt = lines[j].strip().replace(" ", "")
                if re.match(r"\d{2}:\d{2}-\d{2}:\d{2}", nxt):
                    service_time = nxt
                    break
            break

    return service_date, service_time


def fetch_order_meta_by_order_no(session, order_no):
    resp = session.get(PURCHASE_URL, headers=HEADERS, allow_redirects=True)
    if resp.status_code != 200:
        return {
            "服務人員": "無人力",
            "服務狀態": "未處理",
            "車馬費": "0",
            "服務日期": "",
            "服務時間": "",
        }

    blocks = extract_order_cards_from_purchase_html(resp.text)
    for block in blocks:
        if block["order_no"] == order_no:
            lines = block.get("lines", [])
            service_date, service_time = _extract_service_date_time(lines)
            staff = _extract_staff_line(lines)
            status = _extract_status_line(lines)
            fare = _extract_fare_line(lines)

            return {
                "服務人員": staff if staff else "無人力",
                "服務狀態": status if status else "未處理",
                "車馬費": fare if fare else "0",
                "服務日期": service_date,
                "服務時間": service_time,
            }

    return {
        "服務人員": "無人力",
        "服務狀態": "未處理",
        "車馬費": "0",
        "服務日期": "",
        "服務時間": "",
    }


def verify_batch_order_consistency(session, df, all_row_results):
    """
    v2026.07.04：雙向比對 Google Sheet 與後台系統訂單是否一致。

    方向一（從 Google Sheet 比對系統）：
        逐列拿寫回的訂單編號回查系統，比對「電話、地址、日期、時段」是否跟
        Google Sheet 這一列的資料相符，抓出：
        1. 同一個訂單編號被寫進超過一列（M欄重複）。
        2. 訂單編號在後台查無資料。
        3. 訂單編號查得到，但電話/地址/日期/時段跟這一列對不上（代表訂單編號
           很可能誤配對到別人的訂單，這一列實際上沒有真的成單）。

    方向二（從系統的日期區間比對 Google Sheet）：
        以這批次涉及的每支電話，查詢系統該電話底下的實際訂單，只看落在這批次
        涉及日期範圍內的訂單，確認每一筆系統訂單都能對應回 Google Sheet 某一列
        寫下的訂單編號，抓出「系統其實已經成單，但 Google Sheet 沒有正確記錄
        （M欄空白、或寫的是別的訂單編號）」的情況——這是方向一（只看 Sheet 已
        填寫的編號）照不到的死角。

    回傳 list of dict：[{row_num, order_no, issue}, ...]（方向二查到的問題
    row_num 為 None，因為它不是從特定一列出發）。沒有問題則回傳空 list。
    查詢過程中任何單筆錯誤都不中斷整體檢查，只會跳過該筆。
    """
    problems = []
    row_lookup = {}
    for _, row in df.iterrows():
        try:
            row_lookup[int(row["__sheet_row__"])] = row
        except Exception:
            continue

    seen_order_nos = {}
    # 方向二用：記錄每支電話在 Google Sheet 上「認定」的 (日期, 訂單編號) 組合，
    # 以及這批次涉及的日期範圍，供之後反查系統訂單時比對。
    phone_sheet_records = defaultdict(list)

    # ---------- 方向一：從 Google Sheet 出發，回查系統 ----------
    for row_num, result in all_row_results.items():
        row_num_int = int(row_num)
        row = row_lookup.get(row_num_int)
        order_no = str(result.get("訂單編號", "") or "").strip()

        # 不管這一列有沒有訂單編號，只要抓得到電話/日期，都先記錄下來供方向二比對
        if row is not None:
            try:
                _phone_for_dir2 = normalize_phone(row.get("電話", ""))
                _date_for_dir2 = get_date_str(row["日期"])
                if _phone_for_dir2:
                    phone_sheet_records[_phone_for_dir2].append({
                        "row_num": row_num_int, "date": _date_for_dir2, "order_no": order_no,
                    })
            except Exception:
                pass

        if not order_no:
            continue

        # 同一個訂單編號被寫進超過一列 → 直接標記重複（這是「M欄重複」最直接的證據）
        if order_no in seen_order_nos:
            problems.append({
                "row_num": row_num_int,
                "order_no": order_no,
                "issue": f"訂單編號 {order_no} 與第 {seen_order_nos[order_no]} 列重複，這兩列很可能只有一列真的成單，另一列請重新確認。",
            })
        else:
            seen_order_nos[order_no] = row_num_int

        if row is None:
            continue

        try:
            phone = normalize_phone(row.get("電話", ""))
            date_s = get_date_str(row["日期"])
            period_s = normalize_sheet_period(row["開始時間"], row["結束時間"])
            display_period = display_period_text(period_s.split("-")[0], period_s.split("-")[1])
            address = str(row.get("地址", "")).strip()
        except Exception:
            continue

        try:
            _params = dict(PURCHASE_FILTER_PARAMS_TEMPLATE)
            _params["orderNo"] = order_no
            resp = session.get(PURCHASE_URL, params=_params, headers=HEADERS, allow_redirects=True)
        except Exception:
            continue
        if resp.status_code != 200:
            continue

        actual_block = None
        for block in extract_order_cards_from_purchase_html(resp.text):
            if block.get("order_no") == order_no:
                actual_block = block
                break

        if not actual_block:
            problems.append({
                "row_num": row_num_int,
                "order_no": order_no,
                "issue": f"訂單編號 {order_no} 在後台查無資料，第 {row_num_int} 列很可能其實沒有真的成單。",
            })
            continue

        joined = "\n".join(actual_block.get("lines", []))
        joined_compact = re.sub(r"[-\s]", "", joined)
        phone_match = (not phone) or (phone in joined_compact)
        date_match = date_s in joined
        period_match = (
            display_period.replace(" ", "") in joined.replace(" ", "")
            or period_s.replace(" ", "") in joined.replace(" ", "")
        )
        address_match = True
        if address:
            addr_norm = normalize_addr_for_match(address)
            joined_addr_norm = normalize_addr_for_match(joined)
            # 地址核心片段（去掉樓層等細節差異的風險）只要有出現在訂單內容即可算相符，
            # 避免因為門牌格式些微差異（例如全形/半形號樓字）誤判成不相符。
            core = addr_norm[:10] if len(addr_norm) >= 10 else addr_norm
            address_match = bool(core) and core in joined_addr_norm

        if not (phone_match and date_match and period_match and address_match):
            problems.append({
                "row_num": row_num_int,
                "order_no": order_no,
                "issue": (
                    f"訂單 {order_no} 實際內容跟 Google Sheet 第 {row_num_int} 列不符"
                    f"（電話符合：{phone_match}，地址符合：{address_match}，"
                    f"日期符合：{date_match}，時段符合：{period_match}），"
                    f"很可能是訂單編號誤配對到別人的訂單，此列可能其實沒有真的成單，請人工確認。"
                ),
            })

    # ---------- 方向二：從系統的日期區間出發，反查 Google Sheet ----------
    for phone, sheet_records in phone_sheet_records.items():
        relevant_dates = {r["date"] for r in sheet_records if r.get("date")}
        sheet_order_nos_for_phone = {r["order_no"] for r in sheet_records if r.get("order_no")}
        if not relevant_dates:
            continue
        try:
            _params = dict(PURCHASE_FILTER_PARAMS_TEMPLATE)
            _params["phone"] = phone
            resp = session.get(PURCHASE_URL, params=_params, headers=HEADERS, allow_redirects=True)
        except Exception:
            continue
        if resp.status_code != 200:
            continue

        for block in extract_order_cards_from_purchase_html(resp.text):
            sys_order_no = block.get("order_no")
            if not sys_order_no:
                continue
            joined = "\n".join(block.get("lines", []))
            matched_date = ""
            for _d in relevant_dates:
                if _d in joined:
                    matched_date = _d
                    break
            if not matched_date:
                continue  # 這筆系統訂單不在這批次涉及的日期範圍內，略過

            if sys_order_no not in sheet_order_nos_for_phone:
                problems.append({
                    "row_num": None,
                    "order_no": sys_order_no,
                    "issue": (
                        f"系統查到電話 {phone} 在 {matched_date} 有一筆訂單 {sys_order_no}，"
                        f"但 Google Sheet 這批次處理的列裡找不到寫著這個訂單編號的紀錄"
                        f"（可能是某一列的訂單編號欄位空白或寫錯），請確認是否有列遺漏記錄。"
                    ),
                })

    return problems


def send_confirmation_mail(session, order_no):
    url = MAIL_SUCCESS_URL.format(order_no=order_no)
    resp = session.get(url, headers=MAIL_HEADERS, allow_redirects=True)

    if resp.status_code != 200:
        return False, f"HTTP {resp.status_code}"

    try:
        return True, str(resp.json())
    except Exception:
        return True, resp.text[:200]


# =========================
# Google Calendar
# =========================
def build_gcal_service():
    if not ENABLE_GCAL_COLOR_SYNC:
        return None

    scopes = ["https://www.googleapis.com/auth/calendar"]
    service_account_info = get_service_account_info()
    credentials = Credentials.from_service_account_info(service_account_info, scopes=scopes)
    return build("calendar", "v3", credentials=credentials)


def parse_event_time(dt_str):
    if not dt_str:
        return None
    try:
        return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
    except Exception:
        try:
            return datetime.strptime(dt_str, "%Y-%m-%d")
        except Exception:
            return None


def color_name_from_id(color_id):
    mapping = {
        "1": "薰衣草紫",
        "2": "鼠尾草綠",
        "3": "葡萄紫",
        "4": "火鶴紅",
        "5": "香蕉黃",
        "6": "橘子橙",
        "7": "孔雀藍",
        "8": "石墨灰",
        "9": "藍莓藍",
        "10": "羅勒綠",
        "11": "番茄紅",
    }
    return mapping.get(str(color_id), f"未知({color_id})")


def find_matching_calendar_event(service, calendar_id, address, target_date, start_time_str, end_time_str):
    target_date_obj = parse_date_value(target_date)
    sh, sm, eh, em = parse_time_slot(start_time_str, end_time_str)

    tz = timezone(timedelta(hours=8))
    day_start = datetime(target_date_obj.year, target_date_obj.month, target_date_obj.day, 0, 0, 0, tzinfo=tz)
    day_end = day_start + timedelta(days=1)

    events = service.events().list(
        calendarId=calendar_id,
        timeMin=day_start.isoformat(),
        timeMax=day_end.isoformat(),
        singleEvents=True,
        orderBy="startTime",
    ).execute().get("items", [])

    target_addr = normalize_addr_for_match(address)

    for event in events:
        start_raw = event.get("start", {}).get("dateTime") or event.get("start", {}).get("date")
        end_raw = event.get("end", {}).get("dateTime") or event.get("end", {}).get("date")
        start_dt = parse_event_time(start_raw)
        end_dt = parse_event_time(end_raw)
        if not start_dt or not end_dt:
            continue

        location = event.get("location", "") or ""
        description = event.get("description", "") or ""
        summary = event.get("summary", "") or ""
        text_blob = normalize_addr_for_match(location + " " + description + " " + summary)

        if (
            start_dt.date() == target_date_obj.date()
            and (start_dt.hour, start_dt.minute) == (sh, sm)
            and (end_dt.hour, end_dt.minute) == (eh, em)
            and target_addr
            and target_addr in text_blob
        ):
            return event

    return None


def sync_calendar_color_for_row(service, calendar_id, address, date_value, start_time_str, end_time_str):
    if not ENABLE_GCAL_COLOR_SYNC or service is None:
        return {
            "日曆改色結果": "未執行",
            "日曆改色原因": "未啟用日曆改色",
            "日曆原色": "",
            "日曆新色": "",
        }

    try:
        event = find_matching_calendar_event(service, calendar_id, address, date_value, start_time_str, end_time_str)
    except HttpError as e:
        return {
            "日曆改色結果": "失敗",
            "日曆改色原因": f"Calendar API 錯誤: {e}",
            "日曆原色": "",
            "日曆新色": "",
        }
    except Exception as e:
        return {
            "日曆改色結果": "失敗",
            "日曆改色原因": f"Calendar 例外: {e}",
            "日曆原色": "",
            "日曆新色": "",
        }

    if not event:
        return {
            "日曆改色結果": "失敗",
            "日曆改色原因": "找不到對應日曆事件",
            "日曆原色": "",
            "日曆新色": "",
        }

    event_id = event.get("id")
    old_color = str(event.get("colorId", ""))
    old_color_name = color_name_from_id(old_color)

    if old_color != COLOR_PURPLE:
        return {
            "日曆改色結果": "未改",
            "日曆改色原因": f"需求有異動（原色：{old_color_name}）",
            "日曆原色": old_color_name,
            "日曆新色": old_color_name,
        }

    try:
        service.events().patch(
            calendarId=calendar_id,
            eventId=event_id,
            body={"colorId": COLOR_YELLOW},
        ).execute()
    except HttpError as e:
        return {
            "日曆改色結果": "失敗",
            "日曆改色原因": f"改色 API 錯誤: {e}",
            "日曆原色": old_color_name,
            "日曆新色": old_color_name,
        }
    except Exception as e:
        return {
            "日曆改色結果": "失敗",
            "日曆改色原因": f"改色例外: {e}",
            "日曆原色": old_color_name,
            "日曆新色": old_color_name,
        }

    return {
        "日曆改色結果": "成功",
        "日曆改色原因": "葡萄紫 → 香蕉黃",
        "日曆原色": old_color_name,
        "日曆新色": color_name_from_id(COLOR_YELLOW),
    }


# =========================
# 各階段
# =========================
def prepare_base_order_data(row, member_payload, address_info, clean_type_id, people, hours, system_period, note_info):
    member = member_payload.get("member", {}) if isinstance(member_payload, dict) else {}
    last_purchase = member_payload.get("lastPurchase", {}) if isinstance(member_payload, dict) else {}
    old_purchase = address_info.get("purchase", {}) if isinstance(address_info, dict) else {}

    def pick(key, default=""):
        if old_purchase.get(key) not in (None, ""):
            return old_purchase.get(key)
        if last_purchase.get(key) not in (None, ""):
            return last_purchase.get(key)
        return default

    def pick_address_notice(default=""):
        # 客服備註必須以「下拉地址對應的前次訂單客服備註」為準。
        # 不使用 lastPurchase.notice，避免抓到會員其他地址或最後一筆訂單的備註。
        if address_info.get("notice") not in (None, ""):
            return address_info.get("notice")
        if old_purchase.get("notice") not in (None, ""):
            return old_purchase.get("notice")
        if old_purchase.get("service_notice") not in (None, ""):
            return old_purchase.get("service_notice")
        return default

    base_memo = ""
    if note_info["need_note"]:
        base_memo = note_info["customer_time_note"] if not base_memo else f"{base_memo}；{note_info['customer_time_note']}"

    return {
        "clean_type_id": clean_type_id,
        "phone": normalize_phone(row["電話"]),
        "name": str(member.get("name") or row["姓名"]).strip(),
        "email": str(member.get("email") or "").strip(),
        "tel": str(member.get("tel") or normalize_phone(row["電話"])),
        "line": str(member.get("line") or ""),
        "fbName": str(member.get("fb_name") or ""),
        "fb": str(member.get("fb") or ""),
        "memoProcess": str(member.get("memo_process") or ""),
        "memoFinance": str(member.get("memo_finance") or ""),
        "addressId": str(address_info.get("addressId") or ""),
        "country_id": str(address_info.get("country_id") or pick("country_id", "12")),
        "address": str(row["地址"]).strip(),
        "ping": str(pick("ping", "4")),
        "room": str(pick("room", "0")),
        "bathroom": str(pick("bathroom", "0")),
        "balcony": str(pick("balcony", "0")),
        "livingroom": str(pick("livingroom", "0")),
        "kitchen": str(pick("kitchen", "0")),
        "window": str(pick("window", "")),
        "shutter": str(pick("shutter", "")),
        "clothes": str(pick("clothes", "0")),
        "dyson": str(pick("dyson", "0")),
        "refrigerator": str(pick("refrigerator", "0")),
        "disinfection": str(pick("disinfection", "0")),
        "go_abord": str(pick("go_abord", "0")),
        "home_move": str(pick("home_move", "0")),
        "storage": str(pick("storage", "0")),
        "cabinet": str(pick("cabinet", "0")),
        "quintuple": str(pick("quintuple", "0")),
        "hour": str(int(float(hours))),
        "price": "0",
        "price_vvip": "0",
        "person": str(int(people)),
        "date_s": "",
        "period_s": system_period,
        "period": note_info["sms_time"] if note_info["need_note"] else "",
        "cycle": "1",
        "fare": str(address_info.get("fare") or pick("fare", "0") or "0"),
        "memo": base_memo,
        "notice": str(pick_address_notice("")),
        "discount_code": "",
        "payway": "4",
        "is_backend": "477",
        "member_id": str(member.get("member_id") or ""),
        "company_id": str(address_info.get("company_id") or pick("company_id", "1")),
        "area_id": str(address_info.get("area_id") or pick("area_id", "25")),
        "lat": str(address_info.get("lat") or pick("lat", "")),
        "lng": str(address_info.get("lng") or pick("lng", "")),
    }


def filter_dates_by_balance(date_slots, date_prices, stored_value):
    # 只用服務費 price 判斷，車馬費不算在儲值金
    selected_slots, selected_prices, total = [], [], 0
    for slot, price in zip(date_slots, date_prices):
        if total + price <= stored_value:
            selected_slots.append(slot)
            selected_prices.append(price)
            total += price
    return selected_slots, selected_prices, total


def stage_send_confirmation(order_no, session):
    if not order_no:
        return {"確認信": ""}
    try:
        ok, mail_msg = send_confirmation_mail(session, order_no)
        return {"確認信": "已發送" if ok else f"發送失敗: {mail_msg}"}
    except Exception as e:
        return {"確認信": f"發送失敗: {e}"}


def stage_calendar_color(row, gcal_service, region):
    calendar_id = GOOGLE_CALENDAR_MAP.get(region)
    if not calendar_id:
        return {
            "日曆改色結果": "未執行",
            "日曆改色原因": f"找不到區域 {region} 的日曆設定",
            "日曆原色": "",
            "日曆新色": "",
        }

    try:
        return sync_calendar_color_for_row(
            gcal_service,
            calendar_id,
            str(row["地址"]).strip(),
            row["日期"],
            str(row["開始時間"]).strip(),
            str(row["結束時間"]).strip(),
        )
    except Exception as e:
        return {
            "日曆改色結果": "失敗",
            "日曆改色原因": str(e),
            "日曆原色": "",
            "日曆新色": "",
        }


def stage_update_status(order_no, confirm_info, calendar_info, row_result=None):
    confirm_ok = str(confirm_info.get("確認信", "")).strip() == "已發送"
    calendar_ok = str(calendar_info.get("日曆改色結果", "")).strip() == "成功"

    row_result = row_result or {}
    staff_ok = str(row_result.get("服務人員", "")).strip() not in ("", "無人力")
    service_status_ok = str(row_result.get("服務狀態", "")).strip() != ""
    fare_ok = str(row_result.get("車馬費", "")).strip() != ""

    if order_no and confirm_ok and calendar_ok and staff_ok and service_status_ok and fare_ok:
        return {"狀態": "已安排"}

    return {}


def has_action(selected_actions, action_name):
    return True if not selected_actions else action_name in selected_actions


def process_existing_order_only(row, gcal_service, region, session, selected_actions=None):
    order_no = str(row.get("訂單編號", "")).strip()

    if not order_no:
        return build_row_result(
            result="失敗",
            reason="無訂單編號",
            status_value="",
            staff="無人力",
            service_status="未處理",
            fare="0",
        )

    meta = fetch_order_meta_by_order_no(session, order_no)

    result = build_row_result(
        order_no=order_no,
        result="跳過",
        reason="",
        status_value="",
        staff=meta.get("服務人員", "無人力"),
        service_status=meta.get("服務狀態", "未處理"),
        fare=meta.get("車馬費", "0"),
    )

    did_anything = False
    confirm_info = {}
    calendar_info = {}

    if has_action(selected_actions, "寄確認信"):
        confirm_info = stage_send_confirmation(order_no, session)
        result.update(confirm_info)
        did_anything = True

    if has_action(selected_actions, "改 Google 日曆"):
        calendar_info = stage_calendar_color(row, gcal_service, region)
        result.update(calendar_info)
        did_anything = True

    result.update(stage_update_status(order_no, confirm_info, calendar_info, result))

    if did_anything:
        result["結果"] = "成功"

    return result


def process_one_group(session, rows_with_idx, token, gcal_service, region, backend_user_id=None, selected_actions=None, allow_auto_lemon_shift=False, used_order_nos=None):
    _, row0 = rows_with_idx[0]

    purchase_item = str(row0["購買項目"]).strip()
    clean_type_id = CLEAN_TYPE_MAP.get(purchase_item)
    if not clean_type_id:
        raise Exception(f"未知購買項目: {purchase_item}")

    mapped = map_to_system_slot(row0["開始時間"], row0["結束時間"], row0["服務人時"])
    system_period = mapped["system_slot"]
    system_display_period = display_period_text(system_period.split("-")[0], system_period.split("-")[1])

    people, hours = parse_service_human_hour(row0["服務人時"], row0["開始時間"], row0["結束時間"])
    if hours is None:
        raise Exception("無法判斷服務時數")

    print("[DEBUG] parsed person/hour =", {
        "服務人時": str(row0["服務人時"]),
        "sheet_time": normalize_period_text(row0["開始時間"], row0["結束時間"]),
        "person": people,
        "hour": hours,
    })
    try:
        if st is not None:
            st.write("👥 parsed person/hour =", {
                "服務人時": str(row0["服務人時"]),
                "sheet_time": normalize_period_text(row0["開始時間"], row0["結束時間"]),
                "person": people,
                "hour": hours,
            })
    except Exception:
        pass

    phone = normalize_phone(row0["電話"])
    member_payload = get_member(session, phone, token, clean_type_id)
    if not member_payload:
        raise Exception(f"會員不存在: {phone}")

    member = member_payload.get("member", {})
    stored_value = int(float(member_payload.get("storedValue", 0) or 0))

    target_address = str(row0["地址"]).strip().split(",")[0]
    best_addr = pick_best_address_info(member_payload, target_address)
    if not best_addr:
        raise Exception("找不到對應地址資料")
    if not str(best_addr.get("addressId", "")).strip():
        raise Exception(f"地址存在但未選到下拉地址，缺少 addressId：{target_address}")

    selected_address = str(best_addr.get("address") or target_address).strip()

    geo_lat, geo_lng = geocode_address(selected_address)
    if geo_lat and geo_lng:
        best_addr["lat"] = geo_lat
        best_addr["lng"] = geo_lng

    addr_check = check_contain(
        session,
        member.get("member_id", ""),
        selected_address,
        best_addr.get("lat", ""),
        best_addr.get("lng", ""),
        token,
        clean_type_id,
    )
    if not addr_check and not str(best_addr.get("area_id", "")).strip():
        # v2026.07.07 修正重大邏輯錯誤：這裡原本只要 check_contain 失敗就直接
        # 擋單，但手動在後台操作證實——選「已存在的下拉地址」時，畫面本來就
        # 是直接沿用會員資料裡存好的 areaId/lat/lng（changeMemberAddress），
        # 就算後續 check_contain 沒成功也照樣送得出訂單，因為 area_id 早就從
        # 下拉選單帶進來了，check_contain 只是順便再確認一次、不是必要條件。
        # 之前的程式碼把 check_contain 當成每次都要成功的硬性條件，導致明明
        # 是已知、能正常服務的地址，也會被誤擋下來。現在改成：只有在
        # best_addr 本身完全沒有 area_id（代表這筆地址真的資料不全，不是已知
        # 下拉地址）時，才需要 check_contain 成功；已知地址則不因
        # check_contain 失敗而擋單，直接沿用 best_addr 原本的資料繼續。
        _debug_resp = session.post(
            CHECK_CONTAIN_URL,
            data={
                "memberId": member.get("member_id", ""),
                "cleanTypeId": clean_type_id,
                "address": selected_address,
                "lat": best_addr.get("lat", "") or "",
                "lng": best_addr.get("lng", "") or "",
                "_token": token,
            },
            headers=HEADERS,
            allow_redirects=True,
        )
        raise Exception(
            f"查詢地址/地區失敗：{selected_address}"
            f"\n🔧 除錯：HTTP狀態碼={_debug_resp.status_code}　"
            f"lat={best_addr.get('lat', '')}　lng={best_addr.get('lng', '')}"
            f"\n回應內容前300字：{_debug_resp.text[:300]}"
        )

    # 確認是否真的有模擬按下「查詢地址」
    print("[DEBUG] check_contain raw =", addr_check)
    try:
        if st is not None:
            st.write("check_contain raw =", addr_check)
    except Exception:
        pass

    area_info = addr_check.get("area") if isinstance(addr_check, dict) and isinstance(addr_check.get("area"), dict) else {}
    purchase_info = addr_check.get("purchase") if isinstance(addr_check, dict) and isinstance(addr_check.get("purchase"), dict) else {}

    if area_info:
        best_addr["area_id"] = area_info.get("area_id", best_addr.get("area_id"))
        best_addr["company_id"] = area_info.get("company_id", best_addr.get("company_id"))
        best_addr["country_id"] = area_info.get("country_id", best_addr.get("country_id"))

    # 注意：check_contain 回傳的 purchase 通常是付款/發票資訊，
    # 不是「下拉地址前一次訂單」的客服備註來源。
    # 所以不能覆蓋 best_addr["purchase"]，否則會把下拉地址 purchase.notice 洗掉。

    # 模擬後台「查詢地址」後的資料補齊：
    # 車馬費可能在 purchase、area 或巢狀欄位中，需全部掃描。
    fare_from_check = first_nonzero(
        purchase_info.get("fare") if purchase_info else "",
        purchase_info.get("car_fare") if purchase_info else "",
        purchase_info.get("traffic_fee") if purchase_info else "",
        area_info.get("fare") if area_info else "",
        area_info.get("car_fare") if area_info else "",
        area_info.get("traffic_fee") if area_info else "",
        find_nested_value(addr_check, ["fare", "car_fare", "traffic_fee", "trafficFee", "車馬費"]),
        best_addr.get("fare", ""),
        default="0",
    )
    best_addr["fare"] = fare_from_check

    # 客服備註來源修正：
    # 後台在選定會員地址 / 查詢地區後，應帶出「該地址前一次訂單」的預設備註。
    # 這裡只接受 check_contain 的 purchase / 該地址 address_info 回傳值，
    # 不使用 area_info.notice，也不使用 member_payload.lastPurchase.notice，
    # 避免抓到區域備註、會員其他地址或最後一筆訂單的備註。
    dropdown_purchase = best_addr.get("purchase", {}) if isinstance(best_addr.get("purchase"), dict) else {}
    notice_from_dropdown_purchase = (
        dropdown_purchase.get("notice")
        or dropdown_purchase.get("service_notice")
        or find_nested_value(dropdown_purchase, ["notice", "service_notice", "memo_notice", "customer_service_notice"])
        or ""
    )
    notice_from_check = (
        notice_from_dropdown_purchase
        or best_addr.get("notice", "")
        or (purchase_info.get("notice") if purchase_info else "")
        or (purchase_info.get("service_notice") if purchase_info else "")
        or find_nested_value(purchase_info, ["notice", "service_notice", "memo_notice", "customer_service_notice"])
        or ""
    )
    best_addr["notice"] = notice_from_check

    base_data = prepare_base_order_data(
        row0,
        member_payload,
        best_addr,
        clean_type_id,
        people,
        hours,
        system_period,
        mapped,
    )

    # 強制套用查詢地址後取得的區域/車馬費資料
    base_data["fare"] = first_nonzero(best_addr.get("fare"), base_data.get("fare"), default="0")
    base_data["notice"] = str(best_addr.get("notice") or base_data.get("notice") or "")
    base_data["area_id"] = str(best_addr.get("area_id") or base_data.get("area_id") or "")
    base_data["company_id"] = str(best_addr.get("company_id") or base_data.get("company_id") or "")
    base_data["country_id"] = str(best_addr.get("country_id") or base_data.get("country_id") or "")
    base_data["addressId"] = str(best_addr.get("addressId") or base_data.get("addressId") or "")
    base_data["lat"] = str(best_addr.get("lat") or base_data.get("lat") or "")
    base_data["lng"] = str(best_addr.get("lng") or base_data.get("lng") or "")

    print("[DEBUG] address check result =", {
        "addressId": base_data.get("addressId"),
        "area_id": base_data.get("area_id"),
        "company_id": base_data.get("company_id"),
        "fare": base_data.get("fare"),
        "lat": base_data.get("lat"),
        "lng": base_data.get("lng"),
    })

    def build_time_fields():
        sms_time = base_data.get("period", "")
        customer_note = base_data.get("memo", "")
        if mapped["need_note"]:
            sms_time = mapped["original_slot"]
            customer_note = f"服務時間：{mapped['original_slot']}"
        return sms_time, customer_note

    def build_priced_payload_for_date(date_s):
        calc_data = base_data.copy()

        # 重要：完全模擬手動「計算時數」流程。
        # 手動 request 會送 date_s/hour/price/price_vvip/fare 空值，
        # 讓後台自行計算 hour/price/fare；若先帶 0，後台可能不會重算。
        # 查詢班表/計算時數前，先把人數與時數改成 Google Sheet/A欄規則後的值。
        # 不採用後台自動推回來的 hour 來決定班表。
        calc_data["date_s"] = date_s
        calc_data["hour"] = str(base_data.get("hour") or "")
        calc_data["person"] = str(base_data.get("person") or "")
        calc_data["price"] = ""
        calc_data["price_vvip"] = ""
        calc_data["fare"] = ""

        calc_result = calculate_hour(session, calc_data, token)
        if not calc_result:
            raise Exception(f"計算時數失敗：{date_s}")

        print("[DEBUG] calculate_hour raw =", calc_result)
        try:
            if st is not None:
                st.write("🟠 calculate_hour raw =", calc_result)
        except Exception:
            pass

        calc_fields = extract_calc_fields(
            calc_result,
            fallback_hours=base_data.get("hour", ""),
            fallback_fare=best_addr.get("fare", "0"),
        )

        payload = base_data.copy()
        payload["date_s"] = date_s
        payload["hour"] = str(base_data.get("hour") or calc_fields.get("hour") or "")
        payload["person"] = str(base_data.get("person") or payload.get("person") or "")
        payload["price"] = str(calc_fields.get("price") or "0")
        payload["price_vvip"] = str(calc_fields.get("price_vvip") or "0")

        print("[DEBUG] calc_fields =", calc_fields)
        try:
            if st is not None:
                st.write("🟣 calc_fields =", calc_fields)
        except Exception:
            pass
        payload["fare"] = first_nonzero(calc_fields.get("fare"), best_addr.get("fare"), base_data.get("fare"), default="0")

        if str(payload.get("price", "")).strip() in ("", "0", "0.0"):
            raise Exception(f"計算時數後 price 仍為 0，請貼 🟠 calculate_hour raw 與 🟣 calc_fields：{date_s}")

        payload["notice"] = str(base_data.get("notice") or best_addr.get("notice") or "")
        payload["area_id"] = str(base_data.get("area_id") or best_addr.get("area_id") or "")
        payload["company_id"] = str(base_data.get("company_id") or best_addr.get("company_id") or "")
        payload["addressId"] = str(base_data.get("addressId") or best_addr.get("addressId") or "")
        return payload

    row_details = []
    for row_num, row in rows_with_idx:
        date_s = get_date_str(row["日期"])
        priced_payload = build_priced_payload_for_date(date_s)

        row_details.append({
            "row_num": row_num,
            "date": date_s,
            "slot": f"{date_s}_{system_period}",
            "price": int(float(priced_payload.get("price") or 0)),  # 只拿服務費比對儲值金
            "display_period": system_display_period,
            "row": row,
            "payload": priced_payload,
        })

        print("[DEBUG] row slot =", {
            "row_num": row_num,
            "sheet_time": normalize_period_text(row["開始時間"], row["結束時間"]),
            "system_period": system_period,
            "slot": f"{date_s}_{system_period}",
            "price": priced_payload.get("price"),
            "fare": priced_payload.get("fare"),
        })
        try:
            if st is not None:
                st.write("🧭 row slot =", {
                    "row_num": row_num,
                    "sheet_time": normalize_period_text(row["開始時間"], row["結束時間"]),
                    "system_period": system_period,
                    "slot": f"{date_s}_{system_period}",
                    "price": priced_payload.get("price"),
                    "fare": priced_payload.get("fare"),
                })
        except Exception:
            pass

    need_create_order = has_action(selected_actions, "建單")
    row_results = {}

    if not need_create_order:
        for detail in row_details:
            existing_order_no = str(detail["row"].get("訂單編號", "")).strip()
            sms_time, customer_note = build_time_fields()
            service_notice = str(detail["payload"].get("notice") or "")

            meta = fetch_order_meta_by_order_no(session, existing_order_no) if existing_order_no else {
                "服務人員": "無人力",
                "服務狀態": "未處理",
                "車馬費": "0",
            }

            result = build_row_result(
                order_no=existing_order_no,
                result="成功" if existing_order_no else "失敗",
                reason="" if existing_order_no else "無訂單編號，無法寄信或改日曆",
                sms_time=sms_time,
                customer_note=customer_note,
                service_notice=service_notice,
                status_value="",
                staff=meta.get("服務人員", "無人力"),
                service_status=meta.get("服務狀態", "未處理"),
                fare=meta.get("車馬費", "0"),
            )

            if existing_order_no and has_action(selected_actions, "寄確認信"):
                result.update(stage_send_confirmation(existing_order_no, session))

            if has_action(selected_actions, "改 Google 日曆"):
                calendar_info = stage_calendar_color(detail["row"], gcal_service, region)
                result.update(calendar_info)
                if existing_order_no:
                    result.update(stage_update_status(existing_order_no, result, calendar_info, result))

            row_results[detail["row_num"]] = result

        return row_results

    no_slot_dates = []
    valid_details = []

    for detail in row_details:
        raw = get_section_raw(session, detail["payload"], token, detail["slot"])
        slot_ok = slot_exists_in_section_response(raw, detail["slot"])
        cleaners = extract_cleaners_from_section_response(raw, detail["slot"])

        # 若有勾選安全補檸檬人，才在無班表時嘗試補班。補班底層會跳過
        # 當日已有任何班別的專員，不會動到其他客人已配班人員。
        if not slot_ok and allow_auto_lemon_shift:
            try:
                ensure_lemon_cleaner_shifts(
                    session=session, base_url=BASE_URL,
                    service_date=detail["date"], period_s=system_period,
                    person_count=str(people),
                )
                time.sleep(2)
                raw = get_section_raw(session, detail["payload"], token, detail["slot"])
                slot_ok = slot_exists_in_section_response(raw, detail["slot"])
                cleaners = extract_cleaners_from_section_response(raw, detail["slot"])
            except Exception as _e_lemon:
                print(f"[DEBUG] 安全自動補檸檬人失敗：{_e_lemon}")

        detail["section_cleaners"] = cleaners
        detail["section_staff"] = format_staff_from_cleaners(cleaners, people=people)

        # v2026.07.09：光是「時段存在」還不夠，人數要真的足夠才能送出建單。
        # 之前只檢查 slot_ok（時段存不存在），沒檢查人數，導致時段有排班、
        # 但排的人數不夠這張單需要的人數時，還是照樣送出建單，等於人力不足
        # 的訂單也會成單，不符合「人數不夠一律不能成單」的規則。
        try:
            _people_needed = int(people)
        except Exception:
            _people_needed = 0
        if slot_ok and _people_needed and len(cleaners) < _people_needed:
            slot_ok = False

        print("[DEBUG] section match =", {
            "slot": detail["slot"],
            "matched": slot_ok,
            "staff": detail.get("section_staff"),
            "raw_preview": str(raw)[:500],
        })
        try:
            if st is not None:
                st.write("🧩 section match =", {
                    "slot": detail["slot"],
                    "matched": slot_ok,
                    "staff": detail.get("section_staff"),
                    "raw_preview": str(raw)[:500],
                })
        except Exception:
            pass

        if slot_ok:
            valid_details.append(detail)
        else:
            no_slot_dates.append(detail["date"])

    if not valid_details:
        for detail in row_details:
            sms_time, customer_note = build_time_fields()
            service_notice = str(detail["payload"].get("notice") or "")
            row_results[detail["row_num"]] = build_row_result(
                result="失敗",
                reason="無班表",
                no_slot_date=detail["date"],
                sms_time=sms_time,
                customer_note=customer_note,
                service_notice=service_notice,
                status_value="",
                staff="無人力",
                service_status="未處理",
                fare="0",
            )
        return row_results

    # 不再預設檢查「儲值金餘額是否足夠訂單金額」。
    # 後台系統本身已有檢查，這裡只要有班表就送出。
    insufficient_dates = []
    send_details = valid_details

    for detail in row_details:
        sms_time, customer_note = build_time_fields()
        service_notice = str(detail["payload"].get("notice") or "")

        if detail["date"] in no_slot_dates:
            row_results[detail["row_num"]] = build_row_result(
                result="失敗",
                reason="無班表",
                no_slot_date=detail["date"],
                sms_time=sms_time,
                customer_note=customer_note,
                service_notice=service_notice,
                status_value="",
                staff="無人力",
                service_status="未處理",
                fare="0",
            )
        elif detail["date"] in insufficient_dates:
            row_results[detail["row_num"]] = build_row_result(
                result="未送",
                reason="餘額不足",
                insufficient_date=detail["date"],
                sms_time=sms_time,
                customer_note=customer_note,
                service_notice=service_notice,
                status_value="",
                staff=detail.get("section_staff") or "無人力",
                service_status="未處理",
                fare=str(detail["payload"].get("fare") or "0"),
            )

    if not send_details:
        return row_results

    # v2026-07：追蹤「本次呼叫」已配對過的訂單編號，避免比對日期+時段+電話時
    # 誤配對到本次批次自己前面幾筆剛建立、但實際上不同列的訂單。
    if used_order_nos is None:
        used_order_nos = set()

    # 每筆單獨送出，避免日期互相污染
    for detail in send_details:
        payload = detail["payload"].copy()
        slots = [detail["slot"]]

        print("[DEBUG] booking payload =",
              {
                  "date": detail["date"],
                  "slot": detail["slot"],
                  "price": payload.get("price"),
                  "fare": payload.get("fare"),
                  "addressId": payload.get("addressId"),
                  "area_id": payload.get("area_id"),
                  "company_id": payload.get("company_id"),
                  "notice_len": len(str(payload.get("notice") or "")),
              })

        session.post(
            BOOKING_URL,
            data={**payload, "_token": token, "date_list[]": slots},
            headers=HEADERS,
            allow_redirects=True,
        )

        time.sleep(1)

        # v2026-07：比對時同時帶入電話 + 已排除本次用過的訂單編號，避免
        # 只用日期+時段配對到別人的訂單，造成同一個訂單編號被誤寫進兩列
        # Google Sheet（M欄重複、實際上只有一列真的成單）。
        order_no = fetch_order_no_by_date_and_period(
            session, detail["date"], detail["display_period"],
            phone=phone, exclude_order_nos=used_order_nos,
        )
        if order_no:
            used_order_nos.add(order_no)
        sms_time, customer_note = build_time_fields()
        service_notice = str(payload.get("notice") or "")

        if not order_no:
            row_results[detail["row_num"]] = build_row_result(
                result="已送出",
                reason="抓不到訂單編號",
                sms_time=sms_time,
                customer_note=customer_note,
                service_notice=service_notice,
                status_value="",
                staff=detail.get("section_staff") or "無人力",
                service_status="未處理",
                fare=str(detail["payload"].get("fare") or "0"),
            )
            continue

        meta = fetch_order_meta_by_order_no(session, order_no)

        staff_value = meta.get("服務人員", "")
        if not staff_value or staff_value == "無人力":
            staff_value = detail.get("section_staff") or "無人力"

        stage_result = build_row_result(
            order_no=order_no,
            result="成功",
            reason="",
            sms_time=sms_time,
            customer_note=customer_note,
            service_notice=service_notice,
            status_value="",
            staff=staff_value,
            service_status=meta.get("服務狀態", "未處理"),
            fare=meta.get("車馬費", "0") or str(detail["payload"].get("fare") or "0"),
        )

        confirm_info = {}
        calendar_info = {}

        if has_action(selected_actions, "寄確認信"):
            confirm_info = stage_send_confirmation(order_no, session)
            stage_result.update(confirm_info)

        if has_action(selected_actions, "改 Google 日曆"):
            calendar_info = stage_calendar_color(detail["row"], gcal_service, region)
            stage_result.update(calendar_info)

        stage_result.update(stage_update_status(order_no, confirm_info, calendar_info, stage_result))

        row_results[detail["row_num"]] = stage_result

    return row_results


# =========================
# 主執行
# =========================
def run_process(sheet_name, start_row, end_row, env_name_from_ui=None, allow_auto_lemon_shift=False):
    print(f"目前環境：{ENV}")
    print(f"BASE_URL：{BASE_URL}")
    print(f"執行工作表：{sheet_name}")
    print(f"執行列範圍：{start_row} ~ {end_row}")

    ws, df = load_worksheet(sheet_name)

    required_cols = [
        "服務人時",
        "備註",
        "姓名",
        "電話",
        "地址",
        "日期",
        "開始時間",
        "結束時間",
        "狀態",
        "購買項目",
        "訂單編號",
    ]
    for col in required_cols:
        if col not in df.columns:
            raise Exception(f"工作表缺少必要欄位: {col}")

    df = df[(df["__sheet_row__"] >= start_row) & (df["__sheet_row__"] <= end_row)]
    df = df[df.apply(should_process_row, axis=1)]

    if df.empty:
        print("沒有符合條件的資料可執行。")
        return

    gcal_service = None
    if ENABLE_GCAL_COLOR_SYNC:
        try:
            gcal_service = build_gcal_service()
            print("Google Calendar 已啟用")
        except Exception as e:
            print(f"Google Calendar 初始化失敗：{e}")
            gcal_service = None

    grouped_orders = defaultdict(list)

    for _, row in df.iterrows():
        region = get_region_by_address(str(row["地址"]), ACCOUNTS)
        if not region:
            continue
        if not should_create_order(row):
            continue

        key = (region, build_group_key(row))
        grouped_orders[key].append((int(row["__sheet_row__"]), row))

    all_row_results = {}

    region_groups = defaultdict(list)
    for (region, group_key), items in grouped_orders.items():
        region_groups[region].append((group_key, items))

    for region, group_items in region_groups.items():
        config = ACCOUNTS.get(region)
        if not config:
            continue

        email = config["email"]
        password = config["password"]

        print(f"\n===== 開始處理區域：{region} ({email}) =====")

        session = requests.Session()
        if not login(session, email, password):
            print("登入失敗，略過該區域")
            continue

        used_order_nos_this_region = set()

        for group_no, (_, rows_with_idx) in enumerate(group_items, start=1):
            _, first_row = rows_with_idx[0]
            print(f"\n--- 處理第 {group_no} 組：{first_row['姓名']}，共 {len(rows_with_idx)} 筆 ---")

            try:
                token = get_csrf_token(session)
                row_results = process_one_group(
                    session,
                    rows_with_idx,
                    token,
                    gcal_service,
                    region,
                    None,
                    ["建單", "寄確認信", "改 Google 日曆"],
                    allow_auto_lemon_shift=allow_auto_lemon_shift,
                    used_order_nos=used_order_nos_this_region,
                )
                all_row_results.update(row_results)
            except Exception as e:
                print(f"❌ 整組失敗：{e}")
                for row_num, _ in rows_with_idx:
                    all_row_results[row_num] = build_row_result(
                        result="失敗",
                        reason=str(e),
                        status_value="",
                        staff="無人力",
                        service_status="未處理",
                        fare="0",
                    )

            time.sleep(REQUEST_DELAY)

    update_sheet_rows(ws, all_row_results)
    print("已回填 Google Sheet。")

    try:
        consistency_problems = verify_batch_order_consistency(session, df, all_row_results)
        if consistency_problems:
            print(f"⚠️ 訂單一致性檢查發現 {len(consistency_problems)} 筆異常")
            for p in consistency_problems:
                _row_label = f"第 {p['row_num']} 列" if p.get("row_num") is not None else "（系統反查）"
                print(f"  {_row_label}：{p['issue']}")
    except Exception as e:
        print(f"訂單一致性檢查失敗：{e}")


def get_runtime_config(env_name: str):
    if env_name == "dev":
        return {
            "BASE_URL": BASE_URL_DEV,
            "ORDER_PREFIX": ORDER_PREFIX_DEV,
        }
    return {
        "BASE_URL": BASE_URL_PROD,
        "ORDER_PREFIX": ORDER_PREFIX_PROD,
    }


def run_process_web(env_name, region, backend_email, backend_password, sheet_name, start_row, end_row, selected_actions=None, logger=print, allow_auto_lemon_shift=False):
    global BASE_URL, ORDER_PREFIX
    if env_name == "dev":
        BASE_URL = BASE_URL_DEV
        ORDER_PREFIX = ORDER_PREFIX_DEV
    else:
        BASE_URL = BASE_URL_PROD
        ORDER_PREFIX = ORDER_PREFIX_PROD

    global LOGIN_URL, BOOKING_URL, PURCHASE_URL, GET_MEMBER_URL
    global CHECK_CONTAIN_URL, CALCULATE_HOUR_URL, GET_SECTION_URL, MAIL_SUCCESS_URL

    LOGIN_URL = f"{BASE_URL}/login"
    BOOKING_URL = f"{BASE_URL}/booking/stored_value_routine"
    PURCHASE_URL = f"{BASE_URL}/purchase"
    GET_MEMBER_URL = f"{BASE_URL}/ajax/get_member"
    CHECK_CONTAIN_URL = f"{BASE_URL}/ajax/check_contain"
    CALCULATE_HOUR_URL = f"{BASE_URL}/ajax/calculate_hour"
    GET_SECTION_URL = f"{BASE_URL}/ajax/get_section"
    MAIL_SUCCESS_URL = f"{BASE_URL}/purchase/mail_success/{{order_no}}"

    logger(f"目前環境：{env_name}")
    logger(f"BASE_URL：{BASE_URL}")
    logger(f"執行區域：{region}")
    logger(f"執行工作表：{sheet_name}")
    logger(f"執行列範圍：{start_row} ~ {end_row}")

    if selected_actions is None:
        selected_actions = ["建單", "寄確認信", "改 Google 日曆"]

    ws, df = load_worksheet(sheet_name)

    required_cols = [
        "服務人時",
        "備註",
        "姓名",
        "電話",
        "地址",
        "日期",
        "開始時間",
        "結束時間",
        "狀態",
        "購買項目",
        "訂單編號",
    ]
    for col in required_cols:
        if col not in df.columns:
            raise Exception(f"工作表缺少必要欄位: {col}")

    df = df[(df["__sheet_row__"] >= start_row) & (df["__sheet_row__"] <= end_row)]
    df = df[df.apply(should_process_row, axis=1)]

    if df.empty:
        logger("沒有符合條件的資料可執行。")
        return {
            "success": True,
            "message": "沒有符合條件的資料",
            "failed_records": [],
        }

    filtered_rows = [row for _, row in df.iterrows() if get_region_by_address(str(row["地址"]), ACCOUNTS) == region]
    if not filtered_rows:
        logger(f"沒有 {region} 區域的資料可執行。")
        return {
            "success": True,
            "message": f"沒有 {region} 區域資料",
            "failed_records": [],
        }

    df = pd.DataFrame(filtered_rows)
    if "__sheet_row__" not in df.columns:
        raise Exception("資料缺少 __sheet_row__")

    gcal_service = None
    if ENABLE_GCAL_COLOR_SYNC:
        try:
            gcal_service = build_gcal_service()
            logger("Google Calendar 已啟用")
        except Exception as e:
            logger(f"Google Calendar 初始化失敗：{e}")
            gcal_service = None

    session = requests.Session()
    if not login(session, backend_email, backend_password):
        raise Exception("後台登入失敗，請確認帳號密碼")

    grouped_orders = defaultdict(list)
    existing_order_rows = []

    for _, row in df.iterrows():
        row_num = int(row["__sheet_row__"])

        if not has_action(selected_actions, "建單") or not should_create_order(row):
            existing_order_rows.append((row_num, row))
            continue

        grouped_orders[build_group_key(row)].append((row_num, row))

    all_row_results = {}
    failed_records = []

    for row_num, row in existing_order_rows:
        try:
            result = process_existing_order_only(row, gcal_service, region, session, selected_actions)
            all_row_results[row_num] = result
            if result.get("結果") == "失敗":
                failed_records.append({
                    "row": row_num,
                    "name": str(row.get("姓名", "未知")).strip(),
                    "error": str(result.get("原因", "")),
                })
        except Exception as e:
            all_row_results[row_num] = build_row_result(
                result="失敗",
                reason=f"補處理失敗: {e}",
                status_value="",
                staff="無人力",
                service_status="未處理",
                fare="0",
            )
            failed_records.append({
                "row": row_num,
                "name": str(row.get("姓名", "未知")).strip(),
                "error": f"補處理失敗: {e}",
            })

    # v2026-07：本次呼叫累計已配對過的訂單編號，避免跨組別誤配對到同一張訂單
    used_order_nos_this_run = set()

    for group_no, (_, rows_with_idx) in enumerate(grouped_orders.items(), start=1):
        _, first_row = rows_with_idx[0]
        logger(f"處理第 {group_no} 組：{first_row['姓名']}，共 {len(rows_with_idx)} 筆")

        try:
            token = get_csrf_token(session)
            row_results = process_one_group(
                session, rows_with_idx, token, gcal_service, region, None, selected_actions,
                allow_auto_lemon_shift=allow_auto_lemon_shift,
                used_order_nos=used_order_nos_this_run,
            )
            all_row_results.update(row_results)

            for row_num, row in rows_with_idx:
                result = row_results.get(row_num, {})
                if result.get("結果") == "失敗":
                    failed_records.append({
                        "row": row_num,
                        "name": str(row.get("姓名", "未知")).strip(),
                        "error": str(result.get("原因", "")),
                    })
        except Exception as e:
            logger(f"整組失敗：{e}")
            for row_num, row in rows_with_idx:
                failed_records.append({
                    "row": row_num,
                    "name": str(row.get("姓名", "未知")).strip(),
                    "error": str(e),
                })
                all_row_results[row_num] = build_row_result(
                    result="失敗",
                    reason=str(e),
                    status_value="",
                    staff="無人力",
                    service_status="未處理",
                    fare="0",
                )

        time.sleep(REQUEST_DELAY)

    update_sheet_rows(ws, all_row_results)
    logger("已回填 Google Sheet。")

    # v2026.07.05：一致性檢查改由呼叫端（ordersapp.py）在「整批列都執行完」後，
    # 用 run_batch_consistency_check 統一做一次，而不是每呼叫一次 run_process_web
    # 就各自比對一次（原本的寫法會讓同一支電話被重複查詢很多次，也不是真正
    # 「全部成單到一個段落後」的整批核對）。這裡不再自動觸發。
    success_count = sum(1 for v in all_row_results.values() if v.get("結果") == "成功")
    fail_count = sum(1 for v in all_row_results.values() if v.get("結果") == "失敗")

    return {
        "success": True,
        "sheet_name": sheet_name,
        "region": region,
        "env": env_name,
        "success_count": success_count,
        "fail_count": fail_count,
        "total_processed": len(all_row_results),
        "failed_records": failed_records,
    }


def _fetch_all_purchase_blocks_by_date_range(session, date_s, date_e, purchase_status="1", max_pages=80):
    """
    v2026.07.09：依服務日期區間（clean_date_s ~ clean_date_e）查詢後台「全部」
    訂單，處理分頁（後台一頁固定 20 筆，用回傳筆數 < 20 判斷已經是最後一頁）。
    purchase_status="1" 代表只抓已付款訂單；傳 None 或空字串則不篩付款狀態。
    回傳所有訂單卡片 list（跟 extract_order_cards_from_purchase_html 格式相同）。
    """
    all_blocks = []
    for page in range(1, max_pages + 1):
        params = dict(PURCHASE_FILTER_PARAMS_TEMPLATE)
        params["clean_date_s"] = date_s
        params["clean_date_e"] = date_e
        if purchase_status:
            params["purchase_status"] = purchase_status
        params["page"] = str(page)
        try:
            resp = session.get(PURCHASE_URL, params=params, headers=HEADERS, allow_redirects=True)
        except Exception:
            break
        if resp.status_code != 200:
            break
        blocks = extract_order_cards_from_purchase_html(resp.text)
        if not blocks:
            break
        all_blocks.extend(blocks)
        if len(blocks) < 20:
            break
    return all_blocks


def _extract_order_dates_from_block_lines(lines):
    """
    v2026.07.11-3：從一張訂單卡片的 lines 裡，解析出三種日期（都只取日期，
    不含時間）：
    - 訂購日期（建立時間）：格式「YYYY-MM-DD HH:MM:SS」單獨一行。
    - 服務日期：緊接在訂購日期之後、開頭是「YYYY-MM-DD」的那一行（後面可能
      黏著星期幾，例如「2026-07-26                    (日)」，中間有很多
      空白是 get_text() 解析時殘留的，不影響開頭的日期字串）。
    - 付款日期：格式「付款日期：YYYY-MM-DD HH:MM:SS」。
    用實際訂單卡片文字驗證過這個解析方式完全正確。
    """
    created_at = None
    service_date = None
    paid_date = None
    for ln in lines:
        m_paid = re.search(r"付款日期[：:]\s*(\d{4}-\d{2}-\d{2})", ln)
        if m_paid:
            paid_date = m_paid.group(1)
            continue
        m_full = re.fullmatch(r"(\d{4}-\d{2}-\d{2}) \d{2}:\d{2}:\d{2}", ln)
        if m_full and created_at is None:
            created_at = m_full.group(1)
            continue
        m_start = re.match(r"^(\d{4}-\d{2}-\d{2})", ln)
        if m_start and created_at is not None and service_date is None:
            service_date = m_start.group(1)
    return created_at, service_date, paid_date


def _fetch_all_purchase_blocks_with_filters(session, extra_params, max_pages=80):
    """依給定的篩選參數（會疊加在 PURCHASE_FILTER_PARAMS_TEMPLATE 上）撈出全部
    分頁的訂單卡片。"""
    all_blocks = []
    for page in range(1, max_pages + 1):
        params = dict(PURCHASE_FILTER_PARAMS_TEMPLATE)
        params.update(extra_params)
        params["page"] = str(page)
        resp = session.get(PURCHASE_URL, params=params, headers=HEADERS, allow_redirects=True)
        if resp.status_code != 200:
            break
        blocks = extract_order_cards_from_purchase_html(resp.text)
        if not blocks:
            break
        all_blocks.extend(blocks)
        if len(blocks) < 20:
            break
    return all_blocks


def find_orders_without_line_link(
    env_name, backend_email, backend_password,
    date_s=None, date_e=None,
    paid_at_s=None, paid_at_e=None,
    clean_date_s=None, clean_date_e=None,
    max_pages=80,
    return_debug=False,
):
    """
    v2026.07.11-3：獨立工具——搜尋「訂購資訊」欄位裡沒有 LINE 連結的訂單，
    列出訂單編號/姓名/電話。可用訂購日期/付款日期/服務日期三種區間分別
    篩選（每種都可留空不篩）。

    v2026.07.11-3 修正重大漏單問題：實測發現不管是「三種區間同時送」還是
    「每種區間分開各送一次」，只要區間裡有任何一邊留空（例如只填起始日、
    沒填結束日），後台的日期篩選就會整個不準，導致明明符合條件的訂單被
    漏掉（用真實訂單 LC00212069、LC00212115、LC00138514 等大量驗證過）。

    改成完全不依賴後台的日期篩選是否準確：先用「服務日期」（如果起訖都有
    填）當唯一的後台篩選條件抓一批候選訂單（沒填就依序改用訂購日期、付款
    日期，都沒填或只填一邊就直接抓最近的訂單，用 max_pages 限制掃描範圍），
    接著針對每一張抓到的訂單卡片，自己解析出訂購日期／服務日期／付款日期
    三個實際日期（_extract_order_dates_from_block_lines），三種區間都在
    我們自己這邊用 Python 比對篩選，不管後台的日期篩選本身準不準都不影響
    最終結果的正確性。

    判斷有沒有 LINE 連結的方式：後台訂單卡片裡，有綁 LINE 的客人會多一行
    純文字「LINE」（連結文字，來自 <a href="https://chat.line.biz/...">LINE
    </a>，這裡用 extract_order_cards_from_purchase_html 解析後只留得下
    "LINE" 這個文字），沒有 LINE 的客人這一行整個不會出現。
    """
    global BASE_URL, ORDER_PREFIX, PURCHASE_URL, LOGIN_URL
    if env_name == "dev":
        BASE_URL = BASE_URL_DEV
        ORDER_PREFIX = ORDER_PREFIX_DEV
    else:
        BASE_URL = BASE_URL_PROD
        ORDER_PREFIX = ORDER_PREFIX_PROD
    PURCHASE_URL = f"{BASE_URL}/purchase"
    LOGIN_URL = f"{BASE_URL}/login"  # v2026.07.06 修正：原本這裡漏了同步更新 LOGIN_URL，
    # 導致不管選哪個環境，login() 永遠登入模組載入當下 env.py 的 ENV 對應網域
    # （目前是 dev），session cookie 只在該網域有效，選 prod 時後續查詢就會
    # 因為帶著錯網域的 cookie 被當成未登入，掃到 0 筆候選訂單。

    session = requests.Session()
    if not login(session, backend_email, backend_password):
        raise Exception("後台登入失敗，請確認帳號密碼")

    # 只用「其中一種」區間當後台端的粗篩，優先順序：服務日期 > 訂購日期 > 付款日期。
    # v2026.07.11-4：不管使用者只填了起或迄的哪一邊，都自動補上一個寬鬆的
    # 另一邊（很早的日期 / 很晚的日期），確保送給後台的一定是「起訖都有值」
    # 的完整區間。這是因為實測發現只要區間有一邊是空的，後台就會整個放棄
    # 這個篩選條件，退回某種不可控的預設排序（很可能是依 ID 由舊到新），
    # 導致像 LC00212069 這種很新的訂單，掃描 80 頁都排不到、永遠掃不到。
    _far_past, _far_future = "2000-01-01", "2099-12-31"
    pre_filter = {}
    if clean_date_s or clean_date_e:
        pre_filter = {"clean_date_s": clean_date_s or _far_past, "clean_date_e": clean_date_e or _far_future}
    elif date_s or date_e:
        pre_filter = {"date_s": date_s or _far_past, "date_e": date_e or _far_future}
    elif paid_at_s or paid_at_e:
        pre_filter = {"paid_at_s": paid_at_s or _far_past, "paid_at_e": paid_at_e or _far_future}

    all_blocks = []
    edit_id_map = {}
    hit_page_limit = True
    for page in range(1, max_pages + 1):
        params = dict(PURCHASE_FILTER_PARAMS_TEMPLATE)
        params.update(pre_filter)
        params["page"] = str(page)
        resp = session.get(PURCHASE_URL, params=params, headers=HEADERS, allow_redirects=True)
        if resp.status_code != 200:
            hit_page_limit = False
            break
        blocks = extract_order_cards_from_purchase_html(resp.text)
        if not blocks:
            hit_page_limit = False
            break
        all_blocks.extend(blocks)
        edit_id_map.update(_extract_edit_id_map_from_raw_html(resp.text))
        if len(blocks) < 20:
            hit_page_limit = False
            break

    results = []
    for block in all_blocks:
        lines = block.get("lines", [])
        order_no = block.get("order_no", "")

        created_at, service_date, paid_date = _extract_order_dates_from_block_lines(lines)

        # Python 端自己比對三種日期區間（只要有填就一定要符合，留空的維度不篩）
        if date_s and (not created_at or created_at < date_s):
            continue
        if date_e and (not created_at or created_at > date_e):
            continue
        if clean_date_s and (not service_date or service_date < clean_date_s):
            continue
        if clean_date_e and (not service_date or service_date > clean_date_e):
            continue
        if paid_at_s and (not paid_date or paid_date < paid_at_s):
            continue
        if paid_at_e and (not paid_date or paid_date > paid_at_e):
            continue

        line_blank = _order_edit_line_url_is_blank(session, order_no, edit_id_map.get(order_no))
        if line_blank is False:
            continue
        if line_blank is None and "LINE" in lines:
            continue

        phone = ""
        name = ""
        for idx, ln in enumerate(lines):
            if re.fullmatch(r"09\d{8}", ln):
                phone = ln
                if idx > 0:
                    name = lines[idx - 1]
                break
        if "檸檬" in name or "保留" in name:
            continue
        results.append({"order_no": order_no, "name": name, "phone": phone})

    if return_debug:
        # v2026.07.06：診斷用資訊，方便分辨「prod 找不到資料」到底是卡在
        # 哪一關——是後台列表頁根本抓不到候選訂單（scanned_candidates 是
        # 0，代表登入/篩選參數/分頁在該環境有問題），還是候選訂單有抓到、
        # 只是逐筆判斷後真的都有 LINE 連結。
        debug = {
            "env": env_name,
            "base_url": BASE_URL,
            "scanned_candidates": len(all_blocks),
            "matched_without_line": len(results),
            "hit_page_limit": hit_page_limit,
        }
        return results, debug
    return results


def _extract_notice_map_from_raw_html(html):
    """
    v2026.07.13：判斷每張訂單卡片的「客服備註」是不是空白。

    extract_order_cards_from_purchase_html 是用 get_text() 把整頁攤平成
    純文字再切段，但客服備註的實際內容只出現在 <label alt="..." title="...">
    客服備註</label> 這個標籤的 alt/title「屬性」裡，不是文字內容本身
    （文字內容永遠只有「客服備註」四個字），get_text() 會把屬性值整個
    遺失掉。所以要判斷「客服備註是否為空白」，必須回頭用原始 HTML 判斷：
    如果某張訂單卡片的原始 HTML 裡完全沒有出現這個 <label ...>客服備註
    </label> 標籤，代表客服備註是空白（後台不會渲染空白備註的這個標籤）；
    有出現就代表客服備註有內容。

    回傳 dict：{order_no: True/False}，True 表示客服備註「有內容」。
    """
    order_no_positions = [(m.start(), m.group(0)) for m in re.finditer(ORDER_NO_REGEX, html)]
    notice_map = {}
    for i, (pos, order_no) in enumerate(order_no_positions):
        end = order_no_positions[i + 1][0] if i + 1 < len(order_no_positions) else len(html)
        segment = html[pos:end]
        has_notice = bool(re.search(r'<label\s+alt="[^"]*"[^>]*>\s*客服備註\s*</label>', segment))
        # 同一個訂單編號可能因為表格其他欄位重複出現，用 or 累加，只要任一段有找到就算有
        notice_map[order_no] = notice_map.get(order_no, False) or has_notice
    return notice_map


def _extract_edit_id_map_from_raw_html(html):
    order_no_positions = [(m.start(), m.group(0)) for m in re.finditer(ORDER_NO_REGEX, html)]
    edit_id_map = {}
    for i, (pos, order_no) in enumerate(order_no_positions):
        end = order_no_positions[i + 1][0] if i + 1 < len(order_no_positions) else len(html)
        segment = html[pos:end]
        m = re.search(r"/purchase/edit/(\d+)", segment)
        if m:
            edit_id_map[order_no] = m.group(1)
    return edit_id_map


def find_pending_stored_value_orders(
    env_name, backend_email, backend_password,
    date_s=None, date_e=None,
    paid_at_s=None, paid_at_e=None,
    purchase_status=None,
    notice_status="blank",
    max_pages=80,
    return_debug=False,
):
    """
    v2026.07.13-2：獨立工具——搜尋「購買項目：儲值金」且「客服備註是空白」的
    訂單，列出客戶姓名/電話/訂單編號/付款狀態，用來配合客服在 LINE 群組裡
    回報的介紹獎金名單，之後用 add_bonus_note_to_order 依姓名把「獎金：
    名字1X名字2X名字3...」寫進客服備註（同時會把服務狀態改為已處理）。

    可用訂購日期/付款日期兩種區間、以及付款狀態分別篩選（都可留空/不拘）。
    purchase_status 可以是單一值字串（"0"/"1"/"2"/"3"），也可以是
    list/tuple（例如 ["0", "1"] 代表「待付款＋已付款」的組合篩選）。
    傳清單的情況因為後台的付款狀態欄位只吃單一值，這裡不會送給後台篩選，
    改成抓回來的訂單全部掃過一輪，自己比對「付款狀態」這行文字是不是屬於
    清單裡任一種，在 Python 這邊做篩選。

    日期篩選沿用 find_orders_without_line_link 同一套「後台粗篩 + Python
    自己解析日期精確比對」的作法，避免後台日期篩選本身不準確的問題。
    「客服備註是否為空白」用 _extract_notice_map_from_raw_html 從原始
    HTML 判斷（get_text() 純文字解析看不到這個資訊）。
    """
    global BASE_URL, ORDER_PREFIX, PURCHASE_URL, LOGIN_URL
    if env_name == "dev":
        BASE_URL = BASE_URL_DEV
        ORDER_PREFIX = ORDER_PREFIX_DEV
    else:
        BASE_URL = BASE_URL_PROD
        ORDER_PREFIX = ORDER_PREFIX_PROD
    PURCHASE_URL = f"{BASE_URL}/purchase"
    LOGIN_URL = f"{BASE_URL}/login"  # v2026.07.06 修正：原本這裡漏了同步更新 LOGIN_URL，
    # 導致不管選哪個環境，login() 永遠登入模組載入當下 env.py 的 ENV 對應網域
    # （目前是 dev），session cookie 只在該網域有效，選 prod 時後續查詢就會
    # 因為帶著錯網域的 cookie 被當成未登入，掃到 0 筆候選訂單。

    session = requests.Session()
    if not login(session, backend_email, backend_password):
        raise Exception("後台登入失敗，請確認帳號密碼")

    _PURCHASE_STATUS_TEXT = {"0": "待付款", "1": "已付款", "2": "取消訂單", "3": "已退款"}

    is_multi_status = isinstance(purchase_status, (list, tuple, set))
    allowed_status_texts = None
    if purchase_status:
        status_values = purchase_status if is_multi_status else [purchase_status]
        allowed_status_texts = {_PURCHASE_STATUS_TEXT.get(str(s), "") for s in status_values}
        allowed_status_texts.discard("")

    _far_past, _far_future = "2000-01-01", "2099-12-31"
    pre_filter = {"buy": "5"}
    if purchase_status and not is_multi_status:
        pre_filter["purchase_status"] = purchase_status
    if date_s or date_e:
        pre_filter["date_s"] = date_s or _far_past
        pre_filter["date_e"] = date_e or _far_future
    elif paid_at_s or paid_at_e:
        pre_filter["paid_at_s"] = paid_at_s or _far_past
        pre_filter["paid_at_e"] = paid_at_e or _far_future

    # 分頁抓取時，順便把每一頁的原始 HTML 留著，才能判斷客服備註是否為空白
    all_blocks = []
    notice_map = {}
    edit_id_map = {}
    hit_page_limit = True
    for page in range(1, max_pages + 1):
        params = dict(PURCHASE_FILTER_PARAMS_TEMPLATE)
        params.update(pre_filter)
        params["page"] = str(page)
        resp = session.get(PURCHASE_URL, params=params, headers=HEADERS, allow_redirects=True)
        if resp.status_code != 200:
            hit_page_limit = False
            break
        blocks = extract_order_cards_from_purchase_html(resp.text)
        if not blocks:
            hit_page_limit = False
            break
        all_blocks.extend(blocks)
        notice_map.update(_extract_notice_map_from_raw_html(resp.text))
        edit_id_map.update(_extract_edit_id_map_from_raw_html(resp.text))
        if len(blocks) < 20:
            hit_page_limit = False
            break

    results = []
    for block in all_blocks:
        lines = block.get("lines", [])
        order_no = block.get("order_no", "")

        created_at, service_date, paid_date = _extract_order_dates_from_block_lines(lines)

        if date_s and (not created_at or created_at < date_s):
            continue
        if date_e and (not created_at or created_at > date_e):
            continue
        if paid_at_s and (not paid_date or paid_date < paid_at_s):
            continue
        if paid_at_e and (not paid_date or paid_date > paid_at_e):
            continue

        joined = "\n".join(lines)
        status_text = ""
        status_m = re.search(r"付款狀態[：:]\s*([^\n]+)", joined)
        if status_m:
            status_text = status_m.group(1).strip()

        if allowed_status_texts and status_text not in allowed_status_texts:
            continue
        notice_text = _fetch_order_edit_notice(session, order_no, edit_id_map.get(order_no))
        if notice_text is None:
            notice_text = "（列表顯示有客服備註）" if notice_map.get(order_no) else ""
        has_notice = bool(str(notice_text).strip())
        if notice_status == "blank" and has_notice:
            continue
        if notice_status == "nonblank" and not has_notice:
            continue

        phone = ""
        name = ""
        for idx, ln in enumerate(lines):
            if re.fullmatch(r"09\d{8}", ln):
                phone = ln
                if idx > 0:
                    name = lines[idx - 1]
                break
        results.append({
            "order_no": order_no,
            "edit_id": edit_id_map.get(order_no, ""),
            "name": name,
            "phone": phone,
            "purchase_status": status_text,
            "paid_date": paid_date or "",
            "notice": notice_text,
        })

    if return_debug:
        debug = {
            "env": env_name,
            "base_url": BASE_URL,
            "scanned_candidates": len(all_blocks),
            "matched": len(results),
            "hit_page_limit": hit_page_limit,
        }
        return results, debug
    return results


def _purchase_edit_id_from_order_no(order_no):
    digits = re.sub(r"\D", "", str(order_no or ""))
    return str(int(digits)) if digits else ""


def _order_edit_line_url_is_blank(session, order_no, edit_id=None):
    edit_id = edit_id or _fetch_order_edit_id(session, order_no) or _purchase_edit_id_from_order_no(order_no)
    if not edit_id:
        return None
    resp = session.get(f"{BASE_URL}/purchase/edit/{edit_id}", headers=HEADERS, allow_redirects=True)
    if resp.status_code != 200:
        return None
    soup = BeautifulSoup(resp.text, "html.parser")
    line_input = soup.find("input", attrs={"name": "line"})
    if line_input is None:
        return None
    return not str(line_input.get("value") or "").strip()


def _fetch_order_edit_notice(session, order_no, edit_id=None):
    edit_id = edit_id or _fetch_order_edit_id(session, order_no) or _purchase_edit_id_from_order_no(order_no)
    if not edit_id:
        return None
    resp = session.get(f"{BASE_URL}/purchase/edit/{edit_id}", headers=HEADERS, allow_redirects=True)
    if resp.status_code != 200:
        return None
    soup = BeautifulSoup(resp.text, "html.parser")
    notice = soup.find("textarea", attrs={"name": "notice"}) or soup.find("input", attrs={"name": "notice"})
    if notice is None:
        return None
    value = notice.get("value") if notice.name == "input" else notice.get_text()
    return str(value or "").strip()


def _fetch_order_edit_id(session, order_no):
    """跟 quick_order.py 裡同名函式邏輯一致，這裡另外放一份是因為 orders.py
    不匯入 quick_order（避免循環匯入：quick_order 本身會匯入 orders）。"""
    params = dict(PURCHASE_FILTER_PARAMS_TEMPLATE)
    params["orderNo"] = str(order_no).strip()
    resp = session.get(PURCHASE_URL, params=params, headers=HEADERS, allow_redirects=True)
    if resp.status_code != 200:
        return None
    m = re.search(r"/purchase/edit/(\d+)", resp.text)
    return m.group(1) if m else None


def add_bonus_note_to_order(session, base_url, order_no, bonus_names, edit_id=None):
    """
    v2026.07.12（v2：修正欄位覆蓋 bug）：把「獎金：名字1X名字2X名字3...」這行
    文字加進訂單編輯頁的「客服備註」（notice 欄位），保留原本客服備註內容
    （換行接在後面，不覆蓋），其餘欄位原封不動送回去。

    重要修正：訂單編輯頁很多欄位（加收狀態/待退狀態的 radio、加收備註/
    待退備註的 textarea 等）是用 Vue.js 動態渲染的，靜態 HTML 裡看到的是
    還沒被渲染的樣板語法（例如 textarea 內容是字面上的
    "{{ purchase.chargeNote }}"），radio 的勾選狀態也不會反映在靜態 HTML
    的 checked 屬性上。如果只是天真地把靜態 HTML 解析出來的 input/textarea
    值整包送回去，會把這些欄位覆蓋成錯誤的樣板字串或錯誤的預設值（實際
    案例：本來「加收狀態：無」「待退狀態：無」，套用完變成「已加收」
    「已全額退款」，「加收備註」被寫入字面上的 "{{ purchase.chargeNote }}"）。

    修法：這些欄位的真實值其實是內嵌在頁面 <script> 裡的
    `purchase: {...}` JSON 資料（Vue 的 data()），不是從靜態 HTML 屬性
    解析。改成優先從這包 JSON 讀出這些欄位的真實值，蓋掉靜態 HTML 解析
    可能抓錯的部分，只有「notice」這個欄位是我們自己要更新的。
    """
    # v2026.07.06 修正：跟 _order_edit_line_url_is_blank / _fetch_order_edit_notice
    # 用同一套「先試線上搜尋，找不到再退而求其次用訂單編號直接算」的邏輯。
    # 原本這裡只呼叫 _fetch_order_edit_id（用 orderNo 參數送一次 PURCHASE_URL
    # 查詢），如果那次查詢因為任何原因沒抓到（分頁、篩選參數、prod 資料量
    # 較大等），就直接判定「找不到編輯 ID」而失敗，即使訂單編號本身其實
    # 就能算出正確的編輯 ID（LC00212093 → 212093，跟後台編輯頁網址
    # /purchase/edit/212093 一致）。加上這個 fallback 之後，就算線上搜尋
    # 失敗，也能用訂單編號直接算出編輯 ID 繼續執行。
    edit_id = edit_id or _fetch_order_edit_id(session, order_no) or _purchase_edit_id_from_order_no(order_no)
    if not edit_id:
        return False, f"找不到訂單 {order_no} 的編輯 ID"
    edit_url = f"{base_url}/purchase/edit/{edit_id}"
    try:
        get_resp = session.get(edit_url, headers=HEADERS, allow_redirects=True)
        if get_resp.status_code != 200:
            return False, f"無法開啟編輯頁面：HTTP {get_resp.status_code}"
        token_m = re.search(r'<meta name="csrf-token" content="([^"]+)"', get_resp.text)
        csrf = token_m.group(1) if token_m else ""
        if not csrf:
            return False, "無法取得 CSRF token"

        existing = {}
        for m2 in re.finditer(r'<input[^>]+name="([^"]+)"[^>]+value="([^"]*)"[^>]*>', get_resp.text):
            existing[m2.group(1)] = m2.group(2)
        for m2 in re.finditer(r'<textarea[^>]+name="([^"]+)"[^>]*>([^<]*)</textarea>', get_resp.text):
            existing[m2.group(1)] = m2.group(2).strip()

        # 用頁面內嵌的 purchase JSON 蓋掉容易被靜態 HTML 解析錯的欄位
        json_m = re.search(r'purchase:\s*(\{.*?\})\s*\n?\s*\}\s*\n?\s*\}', get_resp.text, re.S)
        if json_m:
            try:
                purchase_json = json.loads(json_m.group(1))
            except Exception:
                purchase_json = {}
        else:
            purchase_json = {}

        _json_backed_fields = [
            "isCharge", "chargeDate", "chargePayment", "chargeInvoiceDate",
            "chargeAmount", "chargeInvoice", "chargeNote",
            "isRefund", "refundDate", "refundPayment", "refundAmount",
            "refundNumber", "refundInvoiceDate", "refundInvoiceAmount",
            "refundInvoice", "refundNote", "progress",
        ]
        for key in _json_backed_fields:
            if key in purchase_json:
                val = purchase_json.get(key)
                existing[key] = "" if val is None else str(val)

        bonus_line = "獎金：" + "X".join(bonus_names)
        old_notice = str(purchase_json.get("notice") or existing.get("notice", "") or "").strip()
        new_notice = f"{old_notice}\n{bonus_line}" if old_notice else bonus_line

        existing["_token"] = csrf
        existing.pop("_method", None)
        existing["notice"] = new_notice
        existing["progress"] = "1"  # v2026.07.13：回填獎金備註時，服務狀態一併改為已處理

        post_resp = session.post(
            edit_url, data=existing,
            headers={**HEADERS, "Content-Type": "application/x-www-form-urlencoded"},
            allow_redirects=True,
        )
        if post_resp.status_code in (200, 302):
            return True, new_notice
        return False, f"HTTP {post_resp.status_code}"
    except Exception as e:
        return False, str(e)


def apply_bonus_notes(env_name, backend_email, backend_password, mapping):
    """
    v2026.07.12：批次套用獎金備註。mapping 是 list of dict：
    [{"order_no": ..., "cust_name": ..., "bonus_names": [...]}]
    這裡統一登入一次後，逐筆呼叫 add_bonus_note_to_order。
    """
    global BASE_URL, ORDER_PREFIX, PURCHASE_URL, LOGIN_URL
    if env_name == "dev":
        BASE_URL = BASE_URL_DEV
        ORDER_PREFIX = ORDER_PREFIX_DEV
    else:
        BASE_URL = BASE_URL_PROD
        ORDER_PREFIX = ORDER_PREFIX_PROD
    PURCHASE_URL = f"{BASE_URL}/purchase"
    LOGIN_URL = f"{BASE_URL}/login"  # v2026.07.06 修正：原本這裡漏了同步更新 LOGIN_URL，
    # 導致不管選哪個環境，login() 永遠登入模組載入當下 env.py 的 ENV 對應網域
    # （目前是 dev），session cookie 只在該網域有效，選 prod 時後續查詢就會
    # 因為帶著錯網域的 cookie 被當成未登入，掃到 0 筆候選訂單。

    session = requests.Session()
    if not login(session, backend_email, backend_password):
        raise Exception("後台登入失敗，請確認帳號密碼")

    results = []
    for item in mapping:
        ok, msg = add_bonus_note_to_order(
            session,
            BASE_URL,
            item["order_no"],
            item["bonus_names"],
            edit_id=item.get("edit_id"),
        )
        results.append({**item, "ok": ok, "msg": msg})
    return results


def run_standalone_consistency_check(env_name, backend_email, backend_password, sheet_name, region=None,
                                       date_range_start=None, date_range_end=None):
    """
    v2026.07.09：獨立的「雙向訂單一致性檢查」工具，不依附在批次建單流程裡
    （批次建單裡的一致性檢查只能核對「這次批次剛執行過的列」，沒辦法單獨
    針對一個既有的成單工作表重新查一次）。

    這裡直接讀取指定工作表目前的全部內容（不限定是不是這次批次跑過的列），
    只要工作表裡已經有「訂單編號」欄位（不管是這次還是很久以前寫入的），
    就能重新對這整份工作表跑一次雙向比對：

    方向一：工作表寫的訂單編號，回查後台是否真的存在，電話/地址/日期/時段
            是否跟這一列相符。

    方向二（v2026.07.09 修正邏輯漏洞）：
        舊版方向二是「拿工作表裡已經出現的電話」去後台查該電話的訂單，這樣
        如果某張後台訂單的客人電話「根本沒被登記進工作表」（例如整筆漏登記），
        從一開始就不會被查到，等於查不出「後台有、工作表完全沒有」這種情況。
        修正後改成：直接用 date_range_start ~ date_range_end 這段日期區間，
        查後台在這段期間「全部」的已付款訂單（不透過電話清單、會處理分頁），
        逐筆核對每一筆訂單編號有沒有出現在工作表任何一列的「訂單編號」欄位裡，
        沒出現就代表工作表完全沒有記錄到這筆訂單。
        有給 date_range_start/date_range_end 才會執行這段加強版方向二；不給的話
        只會執行方向一 + 舊版（以電話為主）的方向二。

    region：可選，若有指定則只檢查該區域的列（用地址判斷區域）；不指定則
    檢查整份工作表所有列。

    回傳 list of dict：[{row_num, order_no, issue}, ...]，沒有問題則回傳空 list。
    """
    global BASE_URL, ORDER_PREFIX
    if env_name == "dev":
        BASE_URL = BASE_URL_DEV
        ORDER_PREFIX = ORDER_PREFIX_DEV
    else:
        BASE_URL = BASE_URL_PROD
        ORDER_PREFIX = ORDER_PREFIX_PROD

    global LOGIN_URL, BOOKING_URL, PURCHASE_URL, GET_MEMBER_URL
    global CHECK_CONTAIN_URL, CALCULATE_HOUR_URL, GET_SECTION_URL, MAIL_SUCCESS_URL

    LOGIN_URL = f"{BASE_URL}/login"
    BOOKING_URL = f"{BASE_URL}/booking/stored_value_routine"
    PURCHASE_URL = f"{BASE_URL}/purchase"
    GET_MEMBER_URL = f"{BASE_URL}/ajax/get_member"
    CHECK_CONTAIN_URL = f"{BASE_URL}/ajax/check_contain"
    CALCULATE_HOUR_URL = f"{BASE_URL}/ajax/calculate_hour"
    GET_SECTION_URL = f"{BASE_URL}/ajax/get_section"
    MAIL_SUCCESS_URL = f"{BASE_URL}/purchase/mail_success/{{order_no}}"

    ws, df = load_worksheet(sheet_name)
    required_cols = ["電話", "地址", "日期", "開始時間", "結束時間", "訂單編號"]
    for col in required_cols:
        if col not in df.columns:
            raise Exception(f"工作表缺少必要欄位: {col}")

    # 只檢查有填日期/電話的列，避免整份工作表裡的空白列造成一堆無意義的解析錯誤
    df_for_check = df[(df["電話"].astype(str).str.strip() != "") & (df["日期"].astype(str).str.strip() != "")]

    if region and not df_for_check.empty:
        df_for_check = df_for_check[df_for_check.apply(lambda row: get_region_by_address(str(row["地址"]), ACCOUNTS) == region, axis=1)]

    session = requests.Session()
    if not login(session, backend_email, backend_password):
        raise Exception("後台登入失敗，請確認帳號密碼")

    problems = []

    if not df_for_check.empty:
        all_row_results = {}
        for _, row in df_for_check.iterrows():
            row_num = int(row["__sheet_row__"])
            all_row_results[row_num] = {"訂單編號": str(row.get("訂單編號", "") or "").strip()}
        problems.extend(verify_batch_order_consistency(session, df_for_check, all_row_results))

    # ---------- 方向二（加強版）：直接掃過整段日期範圍的後台訂單 ----------
    if date_range_start and date_range_end:
        # 用「整份工作表」（不限 region 篩選過的 df_for_check）裡出現過的訂單編號
        # 當作已知清單，只要工作表任何一列有寫到這個訂單編號就算有記錄。
        known_order_nos = {
            str(x).strip() for x in df["訂單編號"].tolist() if str(x).strip()
        }
        backend_blocks = _fetch_all_purchase_blocks_by_date_range(session, date_range_start, date_range_end)
        for block in backend_blocks:
            order_no = str(block.get("order_no", "") or "").strip()
            if not order_no or order_no in known_order_nos:
                continue
            joined = "\n".join(block.get("lines", []))
            phone_m = re.search(r"(09\d{8})", joined)
            phone_disp = phone_m.group(1) if phone_m else "（電話不明）"
            problems.append({
                "row_num": None,
                "order_no": order_no,
                "issue": (
                    f"後台訂單 {order_no}（電話 {phone_disp}，服務日期落在 "
                    f"{date_range_start}~{date_range_end} 範圍內）在工作表「{sheet_name}」"
                    f"裡完全查不到這個訂單編號，請確認是否漏登記。"
                ),
            })

    return problems


def _calchk_address_from_lines(lines):
    """從訂單卡片文字行裡取出地址（比照 weekend_reminders._address 的判斷方式：
    找第一行含有『市/縣』+『區/鄉/鎮/市』且不是電話/LINE 這種雜項的行）。"""
    for line in lines:
        text = str(line or "").strip()
        if not text or "@" in text or text.upper() == "LINE":
            continue
        if re.search(
            r"(台|臺|新北|桃園|台中|臺中|台南|臺南|高雄|基隆|新竹|嘉義|苗栗|彰化|"
            r"南投|雲林|屏東|宜蘭|花蓮|台東|臺東|澎湖|金門|連江).*(市|縣).*(區|鄉|鎮|市)",
            text,
        ):
            return text
    return ""


def _calchk_phone_from_lines(lines):
    for line in lines:
        if re.fullmatch(r"09\d{8}", str(line).strip()):
            return str(line).strip()
    return ""


def _calchk_name_from_lines(lines):
    """訂購人姓名固定緊接在電話號碼那一行之前（比照 weekend_reminders._name_
    phone 的判斷方式）。"""
    for idx, line in enumerate(lines):
        if re.fullmatch(r"09\d{8}", str(line).strip()):
            return str(lines[idx - 1]).strip() if idx else ""
    return ""


def _calchk_service_date_time_from_lines(lines):
    """
    抓服務日期／實際要跟日曆比對用的服務時段。

    v2026.08.14 修正：原本用 _extract_order_dates_from_block_lines 抓服務日期，
    但那個函式要求先找到「訂購日期（建立時間，格式 YYYY-MM-DD HH:MM:SS）」這
    一行，才承認後面的日期行是服務日期。代客預訂類訂單卡片沒有這一行建立時間
    戳記，導致服務日期永遠抓不到、整筆訂單被跳過比對，誤判成「日曆有、後台
    沒有」。改成不依賴訂購日期是否出現：直接找「HH:MM-HH:MM」服務時段這一行
    （格式獨特，訂單卡片裡只會出現一次系統時段），往回找最接近、且不是完整
    建立時間戳記（帶秒數）的純日期行，當作服務日期。

    另外，非標準時段（例如客人約 10:00-12:00，後台系統送 09:00-11:00 佔位）
    的訂單卡片，日期旁邊顯示的是系統時段，真正跟客人約定、也是 Google 日曆
    實際會顯示的時間，記在「簡訊實際服務時間」這個標籤後面。若卡片上有這個
    標籤，比對時要改用它後面的時段，不能只看系統時段，否則永遠跟日曆對不上。

    回傳 (service_date, service_time)，都抓不到時回傳 ("", "")。
    """
    time_idx = None
    system_time = ""
    for idx, line in enumerate(lines):
        compact = str(line).strip().replace(" ", "")
        m = re.match(r"^(\d{2}:\d{2})[-~～](\d{2}:\d{2})$", compact)
        if m:
            time_idx = idx
            system_time = f"{m.group(1)}-{m.group(2)}"
            break
    if time_idx is None:
        return "", ""

    service_date = ""
    for j in range(time_idx - 1, max(-1, time_idx - 5), -1):
        text = str(lines[j]).strip()
        if re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", text):
            continue  # 這是訂購日期（建立時間），不是服務日期
        m2 = re.match(r"^(\d{4}-\d{2}-\d{2})", text)
        if m2:
            service_date = m2.group(1)
            break
    if not service_date:
        return "", ""

    service_time = system_time
    for idx, line in enumerate(lines):
        if "簡訊實際服務時間" in str(line):
            for nxt in lines[idx + 1: idx + 3]:
                m3 = re.match(r"^(\d{2}:\d{2})[-~～](\d{2}:\d{2})$", str(nxt).strip().replace(" ", ""))
                if m3:
                    service_time = f"{m3.group(1)}-{m3.group(2)}"
                    break
            break

    return service_date, service_time


def run_backend_calendar_consistency_check(env_name, backend_email, backend_password,
                                            date_range_start, date_range_end, region=None,
                                            purchase_status="1"):
    """
    v2026.08.14：後台訂單／Google 日曆雙向比對，比照 run_standalone_consistency_check
    （後台 vs. Google Sheet 成單工作表）的雙向比對精神，只是把比對對象換成
    Google 日曆事件。

    比對基準是日曆事件的「時間」與「顏色」：沿用 VIP 訂單／日曆同步既有的顏色
    慣例（紫色＝未安排、黃色＝已安排、綠色＝暫停），只有黃色事件代表「已安排／
    應該已經成單」，才拿來跟後台已付款訂單互相比對；紫色（尚未成單）、綠色
    （已暫停）等其他顏色的事件不列入比對範圍，避免把本來就還沒成單或已暫停的
    日曆事件誤判成異常。

    方向一（後台有、日曆沒有）：後台在 date_range_start~date_range_end 這段
    服務日期區間內的已付款訂單，逐筆用區域＋服務日期＋時段去該區域日曆找
    對應的黃色事件（時間需完全一致），找不到就列為異常。

    方向二（日曆有、後台沒有）：日曆在同一段期間內的黃色事件，逐筆核對是否
    有後台已付款訂單的服務日期＋時段能對應上，對不上就列為異常。

    region：可選，限定只比對 GOOGLE_CALENDAR_MAP 裡的其中一個區域；不指定則
    比對 GOOGLE_CALENDAR_MAP 裡已設定日曆 ID 的全部區域。

    回傳 dict：
        {
            "backend_missing_in_calendar": [{"order_no", "phone", "address",
                "region", "service_date", "service_time", "issue"}, ...],
            "calendar_missing_in_backend": [{"event_summary", "address",
                "region", "service_date", "service_time", "event_link",
                "issue"}, ...],
        }
    """
    global BASE_URL, ORDER_PREFIX
    if env_name == "dev":
        BASE_URL = BASE_URL_DEV
        ORDER_PREFIX = ORDER_PREFIX_DEV
    else:
        BASE_URL = BASE_URL_PROD
        ORDER_PREFIX = ORDER_PREFIX_PROD

    global LOGIN_URL, BOOKING_URL, PURCHASE_URL, GET_MEMBER_URL
    global CHECK_CONTAIN_URL, CALCULATE_HOUR_URL, GET_SECTION_URL, MAIL_SUCCESS_URL

    LOGIN_URL = f"{BASE_URL}/login"
    BOOKING_URL = f"{BASE_URL}/booking/stored_value_routine"
    PURCHASE_URL = f"{BASE_URL}/purchase"
    GET_MEMBER_URL = f"{BASE_URL}/ajax/get_member"
    CHECK_CONTAIN_URL = f"{BASE_URL}/ajax/check_contain"
    CALCULATE_HOUR_URL = f"{BASE_URL}/ajax/calculate_hour"
    GET_SECTION_URL = f"{BASE_URL}/ajax/get_section"
    MAIL_SUCCESS_URL = f"{BASE_URL}/purchase/mail_success/{{order_no}}"

    if region and region not in GOOGLE_CALENDAR_MAP:
        raise Exception(f"{region} 尚未設定 Google Calendar ID，無法比對")
    regions_to_check = [region] if region else list(GOOGLE_CALENDAR_MAP.keys())
    if not regions_to_check:
        raise Exception("尚未設定任何 Google Calendar ID（GOOGLE_CALENDAR_MAP 是空的）")

    service = build_gcal_service()
    if service is None:
        raise Exception("Google 日曆同步目前未啟用")

    session = requests.Session()
    if not login(session, backend_email, backend_password):
        raise Exception("後台登入失敗，請確認帳號密碼")

    # ---------- 後台：抓這段服務日期區間內的全部已付款訂單，解析區域/地址/服務日期時段 ----------
    blocks = _fetch_all_purchase_blocks_by_date_range(
        session, date_range_start, date_range_end, purchase_status=purchase_status
    )
    backend_orders = []
    for block in blocks:
        order_no = str(block.get("order_no", "") or "").strip()
        lines = block.get("lines", [])
        if not order_no:
            continue
        address = _calchk_address_from_lines(lines)
        if not address:
            continue
        order_region = get_region_by_address(address, ACCOUNTS)
        if order_region not in regions_to_check:
            continue
        service_date, service_time = _calchk_service_date_time_from_lines(lines)
        if not service_date or not service_time:
            continue
        backend_orders.append({
            "order_no": order_no,
            "name": _calchk_name_from_lines(lines),
            "phone": _calchk_phone_from_lines(lines),
            "address": address,
            "region": order_region,
            "service_date": service_date,
            "service_time": service_time,
        })

    # ---------- 日曆：抓這段期間內每個區域的黃色事件 ----------
    tz = timezone(timedelta(hours=8))
    day_start = datetime.strptime(date_range_start, "%Y-%m-%d").replace(tzinfo=tz)
    day_end = datetime.strptime(date_range_end, "%Y-%m-%d").replace(tzinfo=tz) + timedelta(days=1)

    calendar_events_by_region = {}
    all_events_by_region = {}
    for r in regions_to_check:
        calendar_id = GOOGLE_CALENDAR_MAP[r]
        events = service.events().list(
            calendarId=calendar_id,
            timeMin=day_start.isoformat(),
            timeMax=day_end.isoformat(),
            singleEvents=True,
            orderBy="startTime",
            maxResults=2500,
        ).execute().get("items", [])
        all_events_by_region[r] = events
        calendar_events_by_region[r] = [e for e in events if str(e.get("colorId", "")) == COLOR_YELLOW]

    def _event_local_range(event):
        start_raw = event.get("start", {}).get("dateTime") or event.get("start", {}).get("date")
        end_raw = event.get("end", {}).get("dateTime") or event.get("end", {}).get("date")
        start_dt = parse_event_time(start_raw)
        end_dt = parse_event_time(end_raw)
        if not start_dt or not end_dt:
            return None, None
        return start_dt.astimezone(tz), end_dt.astimezone(tz)

    def _event_time_match(order, event):
        start_local, end_local = _event_local_range(event)
        if not start_local or not end_local:
            return False
        try:
            start_s, end_s = order["service_time"].split("-")
            sh, sm, eh, em = parse_time_slot(start_s, end_s)
        except Exception:
            return False
        return (
            start_local.strftime("%Y-%m-%d") == order["service_date"]
            and (start_local.hour, start_local.minute) == (sh, sm)
            and (end_local.hour, end_local.minute) == (eh, em)
        )

    def _event_blob(event):
        return re.sub(r"\s+", "", " ".join([
            event.get("summary", "") or "",
            event.get("description", "") or "",
            event.get("location", "") or "",
        ]))

    def _event_phone_match(order_phone, event):
        phone_norm = normalize_phone(order_phone) if order_phone else ""
        return bool(phone_norm) and phone_norm in _event_blob(event)

    def _event_addr_core_match(order_address, event):
        blob = normalize_addr_for_match(" ".join([
            event.get("summary", "") or "",
            event.get("description", "") or "",
            event.get("location", "") or "",
        ]))
        addr_norm = normalize_addr_for_match(order_address)
        core = addr_norm[:10] if len(addr_norm) >= 10 else addr_norm
        return bool(core) and core in blob

    def _phone_in_any_event(phone, events):
        phone_norm = normalize_phone(phone) if phone else ""
        if not phone_norm:
            return False
        return any(phone_norm in _event_blob(e) for e in events)

    def _color_breakdown(events):
        counts = {}
        for e in events:
            name = color_name_from_id(e.get("colorId")) if e.get("colorId") else "（未設定顏色，使用日曆預設色）"
            counts[name] = counts.get(name, 0) + 1
        return "、".join(f"{name}x{n}" for name, n in counts.items())

    matched_event_ids = set()
    result = {"backend_missing_in_calendar": [], "calendar_missing_in_backend": []}

    # ---------- 方向一：後台有、日曆沒有 ----------
    # v2026.08.14：改成兩階段配對。這個系統很多訂單共用同一組標準時段
    # （例如 09:00-11:00），同一天、同一區域常常會有好幾筆不同地址的訂單／
    # 事件落在同一個時段。如果只用「單一輪、對不上就退回第一筆可用事件」的
    # 貪婪配對，會讓對不上的訂單搶先把明明對得上的另一筆訂單該用的事件用掉，
    # 導致那一筆反而被誤判成「日曆沒有」（真實案例 LC00212341、LC00214313：
    # 同時段其實有好幾筆顏色、時段都正確的候選事件，只是被同時段其他訂單
    # 先搶走）。
    #
    # 第一輪：優先用「電話」鎖定配對——實測日曆事件內容通常是
    # 「<已確認>姓名,電話」，並不包含完整地址，用地址核對反而常常對不上；
    # 電話是精確、不會誤判的識別碼，找到就直接鎖定，絕不會被之後任何訂單
    # 搶走。地址核心片段吻合也一併當作可信配對（保留給日曆內容真的有寫
    # 地址的情況）。
    for order in backend_orders:
        for event in calendar_events_by_region.get(order["region"], []):
            event_id = event.get("id")
            if event_id in matched_event_ids:
                continue
            if _event_time_match(order, event) and (
                _event_phone_match(order["phone"], event)
                or _event_addr_core_match(order["address"], event)
            ):
                matched_event_ids.add(event_id)
                order["_matched"] = True
                break

    # 第二輪：電話／地址都核對不上（或事件內容完全沒有可辨識資訊）的訂單，
    # 才用「同時段還沒被配走的事件」補配——此時才可能發生名不符實的配對，
    # 但至少不會搶走第一輪已經確認電話／地址相符的配對。
    for order in backend_orders:
        if order.get("_matched"):
            continue
        candidates = [
            e for e in calendar_events_by_region.get(order["region"], [])
            if e.get("id") not in matched_event_ids and _event_time_match(order, e)
        ]
        if candidates:
            matched_event_ids.add(candidates[0].get("id"))
            continue

        # v2026.08.14：後台有這筆訂單，但這支電話整段期間內完全沒出現在該區域
        # 日曆的任何一筆事件裡（不限時段、不限顏色）——代表這位客人根本不是走
        # 日曆管理流程（例如電話沒登記進日曆、或這類客人本來就不會排進這個
        # 日曆），不列入比對範圍，避免誤報成「日曆沒有」。
        if not _phone_in_any_event(order["phone"], all_events_by_region.get(order["region"], [])):
            continue

        # v2026.08.14：找不到黃色事件時，額外查同時段／同區域是否有「其他顏色
        # （或根本沒設色）」的事件——這樣才分得出「日曆真的完全沒排」跟
        # 「其實有排、只是顏色沒被標成黃色」這兩種不同狀況。顏色只彙總計數
        # （例如「香蕉黃x6、葡萄紫x1」），不逐筆列出，避免同時段候選一多，
        # 訊息裡出現同一個顏色名稱重複好幾次、反而不好讀。
        same_time_any_color = [
            e for e in all_events_by_region.get(order["region"], [])
            if _event_time_match(order, e)
        ]
        if same_time_any_color:
            yellow_events = [e for e in same_time_any_color if str(e.get("colorId", "")) == COLOR_YELLOW]
            other_events = [e for e in same_time_any_color if str(e.get("colorId", "")) != COLOR_YELLOW]
            parts = []
            if yellow_events:
                parts.append(f"{len(yellow_events)} 筆是黃色，但同時段訂單數比黃色事件數多，已被其他訂單配走")
            if other_events:
                parts.append(f"{len(other_events)} 筆顏色不是黃色（{_color_breakdown(other_events)}）")
            extra = f"同時段在日曆上共找到 {len(same_time_any_color)} 筆事件：" + "；".join(parts) + "。"
        else:
            extra = "同時段在日曆上完全找不到任何事件。"
        result["backend_missing_in_calendar"].append({
            "order_no": order["order_no"],
            "name": order["name"],
            "phone": order["phone"],
            "address": order["address"],
            "region": order["region"],
            "service_date": order["service_date"],
            "service_time": order["service_time"],
            "issue": (
                f"後台訂單 {order['order_no']}（{order['name'] or '姓名不明'}，"
                f"{order['phone'] or '電話不明'}，{order['region']}，服務日期 "
                f"{order['service_date']} {order['service_time']}）在 Google 日曆找不到"
                f"對應的黃色事件。{extra}請確認日曆是否漏排或顏色不對。"
            ),
        })

    def _event_name_phone(event):
        """從日曆事件的 summary／description 解析出姓名／電話。實測事件內容
        常見格式是「<已確認>姓名,電話」，姓名緊接在電話前面。"""
        blob = " ".join([event.get("summary", "") or "", event.get("description", "") or ""])
        phone_m = re.search(r"(09\d{8})", blob)
        phone = phone_m.group(1) if phone_m else ""
        name = ""
        if phone_m:
            before = blob[:phone_m.start()]
            name_m = re.search(r"([\u4e00-\u9fffA-Za-z]+)[,，]?\s*$", before)
            name = name_m.group(1) if name_m else ""
        return name, phone

    # ---------- 方向二：日曆有、後台沒有 ----------
    for r, events in calendar_events_by_region.items():
        for event in events:
            if event.get("id") in matched_event_ids:
                continue
            start_local, end_local = _event_local_range(event)
            service_date = start_local.strftime("%Y-%m-%d") if start_local else ""
            service_time = (
                f"{start_local.strftime('%H:%M')}-{end_local.strftime('%H:%M')}"
                if start_local and end_local else ""
            )
            summary = event.get("summary", "") or "（無標題）"
            event_name, event_phone = _event_name_phone(event)
            result["calendar_missing_in_backend"].append({
                "event_summary": summary,
                "name": event_name,
                "phone": event_phone,
                "address": event.get("location", "") or "",
                "region": r,
                "service_date": service_date,
                "service_time": service_time,
                "event_link": event.get("htmlLink", ""),
                "issue": (
                    f"{r}日曆有一筆黃色事件「{summary}」"
                    f"（{event_name or '姓名不明'}，{event_phone or '電話不明'}，"
                    f"{service_date} {service_time}），"
                    f"但後台這段期間的已付款訂單裡找不到服務日期／時段相符的訂單，"
                    f"請確認是否漏成單或日期時段對不上。"
                ),
            })

    return result


def run_batch_consistency_check(env_name, region, backend_email, backend_password, sheet_name, target_rows, logger=print):
    """
    v2026.07.05：批次「整批列都執行完」之後，統一做一次雙向一致性比對，
    取代原本掛在 run_process_web 裡、每呼叫一次就各自比對一次的寫法
    （那樣同一支電話在多列批次裡會被重複查詢很多次，也不是真正「全部成單到
    一個段落後」的整批核對）。

    做法：重新讀一次 Google Sheet 目前的狀態（此時 M 欄等欄位應該都已經是
    這批次執行完、回填後的最終結果），只取 target_rows 這些列、且屬於
    region 這個區域的資料，組成 verify_batch_order_consistency 需要的
    all_row_results（每一列目前 Sheet 上寫的訂單編號），再呼叫既有的雙向
    比對邏輯。

    target_rows: 這次批次實際跑過的列號，可以是不連續的 list，例如 [2, 5, 9]。
    回傳 list of dict：[{row_num, order_no, issue}, ...]，沒有問題則回傳空 list。
    """
    global BASE_URL, ORDER_PREFIX
    if env_name == "dev":
        BASE_URL = BASE_URL_DEV
        ORDER_PREFIX = ORDER_PREFIX_DEV
    else:
        BASE_URL = BASE_URL_PROD
        ORDER_PREFIX = ORDER_PREFIX_PROD

    global LOGIN_URL, BOOKING_URL, PURCHASE_URL, GET_MEMBER_URL
    global CHECK_CONTAIN_URL, CALCULATE_HOUR_URL, GET_SECTION_URL, MAIL_SUCCESS_URL

    LOGIN_URL = f"{BASE_URL}/login"
    BOOKING_URL = f"{BASE_URL}/booking/stored_value_routine"
    PURCHASE_URL = f"{BASE_URL}/purchase"
    GET_MEMBER_URL = f"{BASE_URL}/ajax/get_member"
    CHECK_CONTAIN_URL = f"{BASE_URL}/ajax/check_contain"
    CALCULATE_HOUR_URL = f"{BASE_URL}/ajax/calculate_hour"
    GET_SECTION_URL = f"{BASE_URL}/ajax/get_section"
    MAIL_SUCCESS_URL = f"{BASE_URL}/purchase/mail_success/{{order_no}}"

    target_row_set = {int(r) for r in (target_rows or [])}
    if not target_row_set:
        return []

    ws, df = load_worksheet(sheet_name)
    required_cols = ["電話", "地址", "日期", "開始時間", "結束時間", "訂單編號"]
    for col in required_cols:
        if col not in df.columns:
            raise Exception(f"工作表缺少必要欄位: {col}")

    df = df[df["__sheet_row__"].isin(target_row_set)]
    if df.empty:
        logger("一致性檢查：指定的列號在工作表裡查無資料，略過。")
        return []

    df = df[df.apply(lambda row: get_region_by_address(str(row["地址"]), ACCOUNTS) == region, axis=1)]
    if df.empty:
        logger(f"一致性檢查：指定的列號裡沒有屬於 {region} 區域的資料，略過。")
        return []

    session = requests.Session()
    if not login(session, backend_email, backend_password):
        raise Exception("後台登入失敗，請確認帳號密碼（一致性檢查階段）")

    all_row_results = {}
    for _, row in df.iterrows():
        row_num = int(row["__sheet_row__"])
        all_row_results[row_num] = {"訂單編號": str(row.get("訂單編號", "") or "").strip()}

    logger(f"開始整批一致性檢查（共 {len(all_row_results)} 列）…")
    problems = verify_batch_order_consistency(session, df, all_row_results)

    if problems:
        logger(f"⚠️ 訂單一致性檢查發現 {len(problems)} 筆異常，請人工確認：")
        for p in problems:
            _row_label = f"第 {p['row_num']} 列" if p.get("row_num") is not None else "（系統反查）"
            logger(f"  {_row_label}（訂單 {p['order_no']}）：{p['issue']}")
    else:
        logger("✅ 訂單一致性檢查通過，本次寫回的訂單編號皆與 Google Sheet 電話/地址/日期/時段相符。")

    return problems
