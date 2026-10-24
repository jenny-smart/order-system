# -*- coding: utf-8 -*-
"""檸檬保留刪除地址：代客保留會替檸檬保留帳號加很多客人地址，用完要刪掉。

- 固定保留兩個地址（KEEP_ADDRESSES），永遠不刪。
- 地址還有未取消、服務日期在今天以後的訂單就跳過；讀不完未來訂單時全部跳過。
- 刪除是用瀏覽器開會員管理頁，點該地址旁的垃圾桶（fa-trash-o），刪完重新讀頁面確認。
"""
from __future__ import annotations

import re
import shutil
import unicodedata
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Dict, Iterable, List, Tuple
from urllib.parse import quote, urlparse

from bs4 import BeautifulSoup, NavigableString, Tag

from function import cancel_order as co
import orders
from shared.proxy_reserve import RESERVE_PHONE

KEEP_ADDRESSES = ("台北市大安區信義路四段210號4樓", "台中市北區館前路19號4樓")
INACTIVE_PAYMENT_STATUS = {"取消訂單", "已退款"}
DELETE = "刪除"
MAX_ORDER_PAGES = 60

# 頁面上的地址行：「地址[備註] 🗑」，以 <br> 分行；Python 與瀏覽器用同一套規則取地址文字。
_MARK_JS = """
({phone, target}) => {
  const norm = t => String(t || '').normalize('NFKC').replace(/\\[備註\\]/g, '').replace(/\\s+/g, '').replace(/臺/g, '台');
  document.querySelectorAll('[data-reserve-delete]').forEach(el => el.removeAttribute('data-reserve-delete'));
  const rows = Array.from(document.querySelectorAll('tr')).filter(tr => (tr.textContent || '').includes(phone));
  for (const row of rows) {
    for (const icon of row.querySelectorAll('i.fa-trash-o')) {
      const node = icon.closest('a, button') || icon;
      let text = '';
      for (let prev = node.previousSibling; prev && prev.nodeName !== 'BR'; prev = prev.previousSibling) {
        text = (prev.textContent || '') + text;
      }
      if (norm(text) && norm(text) === norm(target)) {
        node.setAttribute('data-reserve-delete', '1');
        return true;
      }
    }
  }
  return false;
}
"""


def address_key(address) -> str:
    text = unicodedata.normalize("NFKC", str(address or "")).replace("[備註]", "")
    return re.sub(r"\s+", "", text).replace("臺", "台")


def is_kept(address) -> bool:
    return address_key(address) in {address_key(a) for a in KEEP_ADDRESSES}


def _text_before(node: Tag) -> str:
    parts = []
    for prev in node.previous_siblings:
        if isinstance(prev, Tag) and prev.name == "br":
            break
        parts.append(str(prev) if isinstance(prev, NavigableString) else prev.get_text())
    text = "".join(reversed(parts)).replace("[備註]", "")
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", text))


def parse_member_addresses(html: str, phone: str = RESERVE_PHONE) -> List[str]:
    """會員管理頁中，該手機會員有垃圾桶可刪的地址（依頁面順序、不重複）。"""
    soup = BeautifulSoup(html or "", "html.parser")
    found = []
    for row in soup.find_all("tr"):
        if phone not in row.get_text():
            continue
        for icon in row.select("i.fa-trash-o"):
            node = icon.find_parent(["a", "button"]) or icon
            address = _text_before(node)
            if address and address not in found:
                found.append(address)
    return found


def _today() -> str:
    return datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d")


def _launch_browser(runtime):
    executable = shutil.which("chromium") or shutil.which("chromium-browser")
    return runtime.chromium.launch(headless=True, **({"executable_path": executable} if executable else {}))


def _open_member_page(page, member_url):
    """開會員管理頁，等地址清單（垃圾桶圖示）出現；清單由頁面程式產生，不能一載入就讀。"""
    page.goto(member_url, wait_until="domcontentloaded")
    if "/login" in page.url:
        raise RuntimeError("後台登入已失效")
    try:
        page.wait_for_selector("i.fa-trash-o", state="attached", timeout=15000)
    except Exception:
        pass  # 真的沒有可刪地址時不會出現垃圾桶


def list_member_addresses(env_name, backend_email, backend_password, phone=RESERVE_PHONE) -> List[str]:
    session, base_url = co._new_logged_in_session(env_name, backend_email, backend_password)
    resp = session.get(f"{base_url}/member", params={"keyword": phone}, headers=orders.HEADERS, allow_redirects=True)
    if resp.status_code != 200:
        raise RuntimeError(f"讀取會員管理頁失敗：HTTP {resp.status_code}")
    found = parse_member_addresses(resp.text, phone)
    if found:
        return found
    # 地址清單由頁面程式產生時，直接讀 HTML 讀不到；改用瀏覽器開頁面再讀。
    from playwright.sync_api import sync_playwright
    origin = base_url.rstrip("/")
    with sync_playwright() as runtime:
        browser = _launch_browser(runtime)
        try:
            context = browser.new_context()
            context.add_cookies(_browser_cookies(session, origin))
            page = context.new_page()
            _open_member_page(page, f"{origin}/member?keyword={quote(phone)}")
            return parse_member_addresses(page.content(), phone)
        finally:
            browser.close()


def active_order_counts(env_name, backend_email, backend_password, phone=RESERVE_PHONE) -> Tuple[Dict[str, int], bool]:
    """今天以後、未取消的訂單數（依地址）；第二個值＝是否確定讀完。

    後台 /purchase 同時送電話與日期篩選可能整個失效、回傳空結果（見 cancel_order.find_orders），
    所以只用電話篩選、依服務日期新到舊排序，日期與付款狀態在這裡自己比對。
    一張訂單都讀不到時不當作「已讀完」，避免把還在使用的地址刪掉。
    """
    session, base_url = co._new_logged_in_session(env_name, backend_email, backend_password)
    today = _today()
    counts: Counter = Counter()
    seen = 0
    for page in range(1, MAX_ORDER_PAGES + 1):
        params = dict(co.PURCHASE_FILTER_PARAMS_TEMPLATE)
        params.update({"phone": phone, "orderBy": "date_clean:desc", "page": str(page)})
        resp = session.get(f"{base_url}/purchase", params=params, headers=orders.HEADERS, allow_redirects=True)
        if resp.status_code != 200:
            return dict(counts), False
        blocks = orders.extract_order_cards_from_purchase_html(resp.text)
        seen += len(blocks)
        page_dates = []
        for block in blocks:
            item = co._order_from_block(block) or {}
            if item.get("phone") and item["phone"] != phone:
                continue
            service_date = str(item.get("service_date") or "")
            if service_date:
                page_dates.append(service_date)
            if service_date < today or item.get("payment_status") in INACTIVE_PAYMENT_STATUS:
                continue
            address = item.get("address") or orders._calchk_address_from_lines(block.get("lines", []))
            if address:
                counts[address_key(address)] += 1
        # 依服務日期新到舊：最後一頁，或整頁都已早於今天，就不會再有今天以後的訂單。
        if len(blocks) < 20 or (page_dates and max(page_dates) < today):
            return dict(counts), seen > 0
    return dict(counts), False


def plan_cleanup(addresses: Iterable[str], counts: Dict[str, int], complete: bool) -> List[dict]:
    plan = []
    for address in addresses:
        active = counts.get(address_key(address), 0)
        if is_kept(address):
            action, reason = "保留", "固定保留地址"
        elif not complete:
            action, reason = "跳過", "未能讀完今天以後的訂單，無法確認是否還在使用"
        elif active:
            action, reason = "跳過", f"仍有 {active} 張今天以後未取消的訂單"
        else:
            action, reason = DELETE, ""
        plan.append({"地址": address, "處理": action, "原因": reason})
    return plan


def _browser_cookies(session, origin):
    hostname = urlparse(origin).hostname
    cookies = []
    for cookie in session.cookies:
        domain = cookie.domain.lstrip(".")
        if domain and not (hostname == domain or hostname.endswith("." + domain)):
            continue
        cookies.append({"name": cookie.name, "value": cookie.value, "domain": cookie.domain or hostname,
                        "path": cookie.path or "/", "secure": cookie.secure})
    return cookies


def delete_member_addresses(env_name, backend_email, backend_password, addresses: Iterable[str],
                            phone=RESERVE_PHONE) -> List[dict]:
    """逐一點垃圾桶刪除；固定地址一律不刪。每刪一個就重新讀頁面確認已消失。"""
    targets = [a for a in addresses if not is_kept(a)]
    results = [{"地址": a, "結果": "未刪除", "說明": "固定保留地址"} for a in addresses if is_kept(a)]
    if not targets:
        return results
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError("刪除地址所需瀏覽器尚未安裝，請更新部署套件") from exc
    session, base_url = co._new_logged_in_session(env_name, backend_email, backend_password)
    origin = base_url.rstrip("/")
    member_url = f"{origin}/member?keyword={quote(phone)}"
    with sync_playwright() as runtime:
        browser = _launch_browser(runtime)
        try:
            context = browser.new_context()
            context.add_cookies(_browser_cookies(session, origin))
            page = context.new_page()
            page.on("dialog", lambda dialog: dialog.accept())
            for address in targets:
                try:
                    _open_member_page(page, member_url)
                    if not page.evaluate(_MARK_JS, {"phone": phone, "target": address}):
                        results.append({"地址": address, "結果": "未刪除", "說明": "頁面上找不到這個地址的垃圾桶（可能已刪除）"})
                        continue
                    button = page.locator('[data-reserve-delete="1"]').first
                    try:
                        button.click(timeout=5000)
                    except Exception:
                        # 圖示字型沒載入時圖示大小為 0，改直接送出點擊事件。
                        button.dispatch_event("click")
                    # 後台若用 SweetAlert 確認視窗，按確認；原生確認視窗已由 dialog 事件自動接受。
                    try:
                        page.locator(".sweet-alert.visible button.confirm, .swal2-confirm").first.click(timeout=3000)
                    except Exception:
                        pass
                    try:
                        page.wait_for_load_state("networkidle", timeout=15000)
                    except Exception:
                        pass
                    _open_member_page(page, member_url)
                    still_there = page.evaluate(_MARK_JS, {"phone": phone, "target": address})
                    results.append({"地址": address, "結果": "失敗" if still_there else "已刪除",
                                    "說明": "按下垃圾桶後地址仍在，請到後台確認" if still_there else ""})
                except Exception as exc:
                    results.append({"地址": address, "結果": "失敗", "說明": str(exc)})
        finally:
            browser.close()
    return results


def cleanup_after_cancel(env_name, backend_email, backend_password, cancelled_rows: Iterable[dict],
                         phone=RESERVE_PHONE) -> List[dict]:
    """取消檸檬保留帳號的訂單後（代客保留單取消頁或一般取消訂單頁）：
    這些訂單的地址若已沒有今天以後未取消的訂單，就從檸檬保留刪除；固定地址一律不刪。"""
    keys = {address_key(r.get("address")) for r in cancelled_rows
            if r.get("ok") and r.get("address")
            and (r.get("memo_keyword") or re.sub(r"\D", "", str(r.get("phone") or "")) == phone)}
    if not keys:
        return []
    addresses = [a for a in list_member_addresses(env_name, backend_email, backend_password, phone)
                 if address_key(a) in keys]
    if not addresses:
        return []
    counts, complete = active_order_counts(env_name, backend_email, backend_password, phone)
    plan = plan_cleanup(addresses, counts, complete)
    to_delete = [item["地址"] for item in plan if item["處理"] == DELETE]
    deleted = {r["地址"]: r for r in delete_member_addresses(env_name, backend_email, backend_password, to_delete, phone)}
    return [{**item, **({"結果": deleted[item["地址"]]["結果"], "說明": deleted[item["地址"]]["說明"]}
                        if item["地址"] in deleted else {"結果": "未刪除", "說明": item["原因"]})}
            for item in plan]
