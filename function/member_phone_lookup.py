# 移植自 orders-system member_phone_lookup_ui.py：會員手機查詢頁面。
"""Streamlit entry point for member phone lookup."""
import streamlit as st

from function.ui_common import step
from shared.member_phone_lookup import (
    DEFAULT_TAB_TITLE, MemberClient, default_sheet_url, load_sheet_columns, load_sheet_entries,
    lookup_entries, parse_pasted, to_tsv,
)


def render(backend_email, backend_password, env):
    step("3", "會員手機查詢")
    render_member_phone_lookup(env, backend_email, backend_password)


def render_member_phone_lookup(env, email, password):
    st.caption('依姓名查會員手機；有 LINE 連結時再核對。同名多筆全部列出，供人工確認。')
    basis_label = st.radio('查詢依據', ['後台會員連結', 'LINE 連結', '純姓名文字'], horizontal=True, key='mpl_basis')
    basis = {'後台會員連結': 'backend', 'LINE 連結': 'line', '純姓名文字': 'name'}[basis_label]
    st.caption('後台會員連結：使用 keyword 查詢（沿用上方選定環境）；LINE：姓名搜尋後核對連結。沒有連結的列改用姓名並標示。')
    source = st.radio('名單來源', ['Google Sheet 指定列', '貼上名單'], horizontal=True, key='mpl_source')
    text, url, start, end, column, line_column = '', '', 1, 1, 'C', None
    ready = True
    if source == '貼上名單':
        text = st.text_area('每行一筆：姓名，或姓名＋所選類型的連結', height=160,
                            placeholder='王小明\n陳小美 https://chat.line.biz/官方帳號/chat/客戶識別碼', key='mpl_text')
        st.caption('只貼 LINE 無法直接反查手機，請同時提供姓名。每次最多 100 筆。')
    else:
        if 'mpl_url' not in st.session_state:
            st.session_state['mpl_url'] = default_sheet_url()
        url = st.text_input(f'Google Sheet 網址（沒帶 gid 時用「{DEFAULT_TAB_TITLE}」分頁）', key='mpl_url')
        header = int(st.number_input('欄位標題在第幾列', min_value=1, value=1, key='mpl_header'))
        schema_key = (url.strip(), header)
        if st.session_state.get('mpl_schema_key') != schema_key:
            st.session_state.pop('mpl_schema', None)
            st.session_state.pop('mpl_results', None)
        if st.button('讀取欄位', key='mpl_load_columns'):
            st.session_state.pop('mpl_schema', None)
            st.session_state.pop('mpl_results', None)
            try:
                with st.spinner('讀取試算表欄位…'):
                    st.session_state['mpl_schema'] = load_sheet_columns(url, header)
                    st.session_state['mpl_schema_key'] = schema_key
                    st.session_state.pop('mpl_name_column', None)
                    st.session_state.pop('mpl_line_column', None)
            except ValueError as exc:
                st.error(str(exc))
            except Exception:
                st.error('無法讀取欄位，請確認連結與 Google 服務帳號讀取權限。')
        schema = st.session_state.get('mpl_schema')
        ready = bool(schema)
        if schema:
            st.caption(f"目前分頁：{schema['title']}；若需其他分頁，請貼上該分頁連結。")
            columns = list(schema['columns'])
            preferred = next((i for i, c in enumerate(columns) if schema['columns'][c] in ('姓名', '客戶姓名', '會員姓名')), 0)
            label = lambda c: f"{c} — {schema['columns'][c] or '無標題'}"
            a, b = st.columns(2)
            column = a.selectbox('依據欄位（姓名）', columns, index=preferred, format_func=label, key='mpl_name_column')
            if basis != 'name':
                line_column = b.selectbox('連結來源欄位', [None] + columns,
                                          format_func=lambda c: '使用姓名格內的超連結' if c is None else label(c), key='mpl_line_column')
            a, b = st.columns(2)
            start = int(a.number_input('起始列', min_value=1, value=188, step=1, key='mpl_start'))
            end = int(b.number_input('結束列', min_value=1, value=206, step=1, key='mpl_end'))
            st.caption('請排除標題列，每次最多 100 列。只有 LINE 時須補姓名；比對結果不會自動回填。')
        else:
            st.info('貼上連結後按「讀取欄位」，再選擇姓名欄與查詢列數。')

    context = (env, email.strip(), source, text, url, start, end, column, line_column, basis)
    if st.session_state.get('mpl_context') != context:
        st.session_state.pop('mpl_results', None)
        st.session_state['mpl_context'] = context
    if st.button('查詢會員手機', type='primary', key='mpl_search', disabled=not ready):
        st.session_state.pop('mpl_results', None)
        if not email.strip() or not password.strip():
            st.error('請先填寫上方後台帳號與密碼。')
            return
        client = None
        try:
            with st.spinner('讀取名單並查詢會員…'):
                entries = parse_pasted(text) if source == '貼上名單' else load_sheet_entries(url, start, end, column, line_column)
                from env import BASE_URL_DEV, BASE_URL_PROD
                client = MemberClient(BASE_URL_DEV if env == 'dev' else BASE_URL_PROD, email.strip(), password.strip())
                results = lookup_entries(client, entries, basis=basis)
                st.session_state['mpl_results'] = results
        except ValueError as exc:
            st.error(str(exc))
        except Exception:
            st.error('查詢失敗：請檢查後台登入、網路及 Google Sheet 讀取權限，再重新查詢。')
        finally:
            if client:
                client.close()
    rows = st.session_state.get('mpl_results')
    if rows:
        st.dataframe(rows, width="stretch", hide_index=True,
                     column_config={'手機號碼': st.column_config.TextColumn('手機號碼')})
        st.caption('僅依姓名相符仍需核對身分；查無資料、LINE 不符、同名多筆不會自動選取。貼回試算表前請將電話欄設為純文字，保留開頭 0。')
        value = to_tsv(rows)
        st.code(value, language=None)
        st.download_button('下載查詢結果 TSV', value.encode('utf-8-sig'),
                           '會員手機查詢.tsv', 'text/tab-separated-values', key='mpl_download')
