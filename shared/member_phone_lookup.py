# 移植自 orders-system member_phone_lookup.py（5b71577／2c45f8b／c6f6a3c）：會員手機查詢核心邏輯。
"""Read-only, bounded member lookup; never follows customer LINE URLs."""
from __future__ import annotations

import csv
import io
import json
import re
import unicodedata
from urllib.parse import urlparse, unquote, parse_qs

from bs4 import BeautifulSoup


def clean_name(value):
    return re.sub(r'\s+', '', unicodedata.normalize('NFKC', str(value or ''))).strip()


def line_key(value):
    value = unquote(str(value or '').strip()).rstrip('/')
    parsed = urlparse(value)
    # Match the conversation path, never the official-account ID preceding /chat/.
    if parsed.hostname in {'chat.line.biz', 'manager.line.biz'}:
        match = re.search(r'/chat/([^/?#]+)', parsed.path)
        if match:
            return 'chat:' + match.group(1)
    if parsed.hostname in {'line.me', 'lin.ee'}:
        return parsed.hostname + parsed.path
    return value


def parse_pasted(text):
    entries = []
    for row, raw in enumerate(text.splitlines(), 1):
        if not raw.strip():
            continue
        urls = re.findall(r'https?://[^\s<>"\])]+', raw)
        name = raw
        for url in urls:
            name = name.replace(url, '')
        name = re.sub(r'[\[\]()\t]+', ' ', name).strip()
        if len(urls) > 1:
            raise ValueError(f'第 {row} 行請只放一個 LINE 連結。')
        entries.append({'source': str(row), 'name': name, 'line': urls[0] if urls else ''})
    if not entries or len(entries) > 100:
        raise ValueError('請提供 1～100 筆姓名或姓名＋LINE 連結。')
    return entries


def parse_member_page(html):
    soup = BeautifulSoup(html, 'html.parser')
    for script in soup.find_all('script'):
        match = re.search(r'\bmemberList\s*:\s*', script.get_text())
        if match:
            try:
                members, _ = json.JSONDecoder().raw_decode(script.get_text()[match.end():])
            except (ValueError, TypeError) as exc:
                raise ValueError('會員資料格式改變，無法安全解析。') from exc
            if not isinstance(members, list) or any(not isinstance(m, dict) for m in members):
                raise ValueError('會員資料格式改變。')
            # Keep only the fields needed for matching; discard auto-login tokens etc.
            records = [{k: m.get(k, '') for k in ('id', 'name', 'phone', 'line')} for m in members]
            pages = []
            for a in soup.select('.pagination a[href], a[rel="next"][href]'):
                number = parse_qs(urlparse(a['href']).query).get('page', [''])[0]
                if number.isdigit():
                    pages.append(int(number))
            return records, pages
    raise ValueError('找不到會員資料；請確認帳號權限或重新登入。')


class MemberClient:
    def __init__(self, base_url, email, password):
        import requests
        self.session = requests.Session()
        self.base = base_url.rstrip('/')
        self.cache = {}
        try:
            page = self.session.get(self.base + '/login', timeout=30)
            page.raise_for_status()
            token = BeautifulSoup(page.text, 'html.parser').select_one('input[name="_token"]')
            if not token:
                raise ValueError('無法取得登入頁。')
            response = self.session.post(self.base + '/login', data={
                '_token': token.get('value', ''), 'email': email, 'password': password,
            }, timeout=30)
            response.raise_for_status()
            if '/login' in urlparse(response.url).path:
                raise ValueError('後台登入失敗。')
        except Exception:
            self.session.close()
            raise

    def search(self, name, max_pages=10):
        name = name.strip()
        if not name:
            raise ValueError('請提供姓名；後台不支援只用 LINE 搜尋。')
        if name in self.cache:
            return self.cache[name]
        records, seen, pending = {}, set(), {1}
        while pending and len(seen) < max_pages:
            page = min(pending)
            pending.remove(page)
            seen.add(page)
            response = self.session.get(self.base + '/member', params={
                'keyword': name, 'page': page,
            }, timeout=30)
            response.raise_for_status()
            if '/login' in urlparse(response.url).path:
                raise ValueError('登入已失效，請重新查詢。')
            members, pages = parse_member_page(response.text)
            for m in members:
                if not m['id']:
                    raise ValueError('會員資料缺少識別碼。')
                records[str(m['id'])] = m
            pending.update(set(pages) - seen)
        result = (list(records.values()), not pending)
        self.cache[name] = result
        return result

    def close(self):
        self.session.close()


def match_entry(entry, members, complete=True):
    exact = [m for m in members if clean_name(m['name']) == clean_name(entry['name'])]
    if entry.get('line'):
        exact = [m for m in exact if m.get('line') and line_key(m['line']) == line_key(entry['line'])]
    status = ('姓名＋LINE 相符' if entry.get('line') else '姓名唯一相符（請核對）')
    if not complete:
        status = '查詢未完整，請縮小搜尋範圍'
    elif len(exact) > 1:
        status = f'有多筆（{len(exact)} 筆），請人工確認'
    elif not exact:
        status = '姓名有候選但 LINE 不符' if entry.get('line') and members else '查無完全相符會員'
    results = []
    for member in exact or [{}]:
        phone = str(member.get('phone') or '').strip()
        if phone and not re.fullmatch(r'09\d{8}', phone):
            phone_status = status + '；手機格式需確認'
        elif member and not phone:
            phone_status = status + '；會員未填手機'
        else:
            phone_status = status
        results.append({'來源列': entry.get('source', ''), '查詢姓名': entry['name'],
                        '會員姓名': member.get('name', ''), '手機號碼': phone,
                        '比對狀態': phone_status, '會員編號': str(member.get('id', '')),
                        'LINE': member.get('line', '')})
    return results


def backend_keyword(link):
    parsed = urlparse(str(link).strip())
    if (parsed.scheme != 'https' or parsed.hostname not in {
        'backend.lemonclean.com.tw', 'backend-dev.lemonclean.com.tw'
    } or parsed.path.rstrip('/') != '/member' or parsed.username or parsed.password):
        raise ValueError('不是支援的後台會員搜尋連結（/member?keyword=…）')
    keywords = parse_qs(parsed.query).get('keyword', [])
    if len(keywords) != 1 or not keywords[0].strip():
        raise ValueError('後台會員連結缺少唯一的搜尋關鍵字')
    return keywords[0].strip()


def lookup_entries(client, entries, basis='legacy'):
    results = []
    for original in entries:
        entry = dict(original)
        link = entry.get('line', '')
        note = ''
        keyword = entry['name'].strip()
        if basis == 'backend' and link:
            try:
                keyword = backend_keyword(link)
            except ValueError as exc:
                row = match_entry(entry, [])[0]
                row['比對狀態'] = str(exc) + '；請切換依據或修正連結'
                results.append(row)
                continue
            entry['line'] = ''
            entry['name'] = keyword
            note = '後台連結關鍵字：' + keyword + '；'
        elif basis == 'name':
            entry['line'] = ''
        elif basis == 'line' and link:
            parsed = urlparse(link)
            if parsed.hostname not in {'chat.line.biz', 'manager.line.biz', 'line.me', 'lin.ee'}:
                row = match_entry(entry, [])[0]
                row['比對狀態'] = '此連結不是 LINE；請選擇後台會員連結或修正連結'
                results.append(row)
                continue
        if basis in {'backend', 'line'} and not link:
            note = '無連結，改以姓名查詢；'
        if not keyword:
            row = match_entry(entry, [])[0]
            row['比對狀態'] = '僅有 LINE：請補姓名，後台不支援 LINE 搜尋'
            results.append(row)
            continue
        members, complete = client.search(keyword)
        if basis == 'backend' and link:
            # A member search URL is a keyword search, not proof of a unique account.
            matched = [m for m in members if clean_name(m['name']) == clean_name(keyword)
                       or str(m.get('phone', '')).strip() == keyword]
            normalized = [dict(m, name=keyword) for m in matched]
            rows = match_entry(entry, normalized, complete)
            for row, member in zip(rows, matched):
                row['會員姓名'] = member['name']
        else:
            rows = match_entry(entry, members, complete)
        for row in rows:
            row['查詢姓名'] = original['name'] or keyword
            row['比對狀態'] = note + row['比對狀態']
        results.extend(rows)
    return results


def cell_link(cell):
    links = [cell.get('hyperlink', '')]
    links += [run.get('format', {}).get('link', {}).get('uri', '') for run in cell.get('textFormatRuns', [])]
    formula = cell.get('userEnteredValue', {}).get('formulaValue', '')
    match = re.match(r'=HYPERLINK\(\s*"([^"]+)"', formula, re.I)
    if match:
        links.append(match.group(1))
    links = list(dict.fromkeys(x for x in links if x))
    if len(links) > 1:
        raise ValueError('姓名儲存格含多個連結，請改用貼上名單指定。')
    return links[0] if links else ''


def column_letter(number):
    value = ''
    while number:
        number, rem = divmod(number - 1, 26)
        value = chr(65 + rem) + value
    return value


DEFAULT_TAB_TITLE = '評價預約'


def open_sheet_target(url):
    from orders import build_gsheet_client
    parsed = urlparse(url.strip())
    match = re.fullmatch(r'/spreadsheets/d/([\w-]+)(?:/.*)?', parsed.path)
    if parsed.hostname != 'docs.google.com' or not match:
        raise ValueError('請提供完整 Google Sheets 網址。')
    book = build_gsheet_client().open_by_key(match.group(1))
    gid = parse_qs(parsed.fragment).get('gid', parse_qs(parsed.query).get('gid', ['']))[0]
    if gid and not gid.isdigit():
        raise ValueError('分頁 gid 格式錯誤。')
    if gid:
        ws = book.get_worksheet_by_id(int(gid))
    else:
        # 網址沒帶 gid 時依名稱找預設分頁（換年 GID 會變）；找不到就報錯，不改用第一個分頁
        titles = [w.title for w in book.worksheets()]
        if DEFAULT_TAB_TITLE not in titles:
            raise ValueError(f'試算表找不到「{DEFAULT_TAB_TITLE}」分頁，請在網址帶上 gid。')
        ws = book.worksheet(DEFAULT_TAB_TITLE)
    return book, ws


def default_sheet_url():
    """預設名單：今年台北內勤工作表單（依年度根目錄找）的「評價預約」分頁；找不到回傳空字串。"""
    try:
        from year_roots import root_file_id

        return f'https://docs.google.com/spreadsheets/d/{root_file_id("內勤工作表單", "台北")}/edit'
    except Exception:
        return ''


def load_sheet_columns(url, header_row=1):
    _, ws = open_sheet_target(url)
    if not 1 <= header_row <= ws.row_count:
        raise ValueError('標題列超出分頁大小。')
    count = min(ws.col_count, 256)
    values = ws.get(f'A{header_row}:{column_letter(count)}{header_row}')
    headers = values[0] if values else []
    columns = {column_letter(i + 1): str(headers[i]).strip() if i < len(headers) else ''
               for i in range(count)}
    return {'title': ws.title, 'row_count': ws.row_count, 'columns': columns}


def load_sheet_entries(url, start, end, name_column='C', line_column=None):
    if not 1 <= start <= end or end - start >= 100:
        raise ValueError('每次讀取 1～100 列。')
    book, ws = open_sheet_target(url)
    for column in [name_column] + ([line_column] if line_column else []):
        if not re.fullmatch(r'[A-Z]{1,3}', column):
            raise ValueError('欄位格式錯誤。')
        col = 0
        for char in column:
            col = col * 26 + ord(char) - 64
        if end > ws.row_count or col > ws.col_count:
            raise ValueError('讀取範圍超出分頁大小。')
    title = ws.title.replace("'", "''")

    def read_column(column):
        data = book.fetch_sheet_metadata(params={
            'includeGridData': True, 'ranges': f"'{title}'!{column}{start}:{column}{end}",
            'fields': 'sheets(data(startRow,rowData(values(formattedValue,hyperlink,textFormatRuns,userEnteredValue))))',
        })
        cells = {}
        for sheet in data.get('sheets', []):
            for grid in sheet.get('data', []):
                for i, row in enumerate(grid.get('rowData', [])):
                    cells[grid.get('startRow', start - 1) + i + 1] = (row.get('values') or [{}])[0]
        return cells

    names = read_column(name_column)
    links = read_column(line_column) if line_column and line_column != name_column else names
    entries = []
    for row_number, cell in names.items():
        name = cell.get('formattedValue', '').strip()
        if name:
            link_cell = links.get(row_number, {})
            link = cell_link(link_cell)
            if line_column and line_column != name_column and not link:
                link = link_cell.get('formattedValue', '').strip()
            entries.append({'source': str(row_number), 'name': name, 'line': link})
    if not entries:
        raise ValueError('指定範圍沒有姓名。')
    return entries


def to_tsv(rows):
    output = io.StringIO()
    writer = csv.writer(output, delimiter='\t', lineterminator='\n')
    fields = ['來源列', '查詢姓名', '會員姓名', '手機號碼', '比對狀態', '會員編號', 'LINE']
    writer.writerow(fields)
    for row in rows:
        # Avoid formulas when pasted into a spreadsheet.
        values = [str(row.get(k, '')) for k in fields]
        writer.writerow(["'" + v if v.startswith(('=', '+', '-', '@')) else v for v in values])
    return output.getvalue()
