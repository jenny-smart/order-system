# order-system 第五批：驗證以明確呼叫取代 orders-system monkeypatch 後的批次防呆行為。
import unittest
from unittest.mock import MagicMock, patch

import pandas as pd

import orders
import shared.batch_booking_safety as safety
import shared.hybrid_batch_runner as hybrid
import shared.selected_row_status_guard as guard
from shared import gsheet


def _row(row_no, **fields):
    row = {'__sheet_row__': row_no, '服務人時': '2人3小時', '備註': '', '姓名': '王小明',
           '電話': '0912-345-678', '地址': '台北市大安區測試路1號', '日期': '2026/10/20',
           '開始時間': '09:00', '結束時間': '12:00', '狀態': '未安排', '購買項目': '居家清潔',
           '訂單編號': ''}
    row.update(fields)
    return row


class StatusGuardTest(unittest.TestCase):
    def test_status_normalized_and_existing_orders_still_processed(self):
        self.assertTrue(orders.should_create_order(pd.Series(_row(2, 狀態=' 未​安排 '))))
        self.assertFalse(orders.should_create_order(pd.Series(_row(2, 狀態='已安排'))))
        self.assertTrue(orders.should_process_row(pd.Series(_row(2, 狀態='已安排', 訂單編號='LC1'))))
        self.assertFalse(orders.should_process_row(pd.Series(_row(2, 狀態='已安排'))))

    def test_duplicate_columns_keep_first(self):
        df = pd.DataFrame([[1, 'a', 'b']], columns=['__sheet_row__', '狀態', '狀態'])
        with patch.object(orders, 'load_worksheet', return_value=(None, df)):
            _, out = guard._load_worksheet_unique('s')
        self.assertEqual(out.columns.tolist(), ['__sheet_row__', '狀態'])
        self.assertEqual(out['狀態'].iloc[0], 'a')


class SheetWritebackTest(unittest.TestCase):
    def test_first_header_and_pending_status_allowed(self):
        ws = MagicMock()
        headers = ['狀態', '結果', '結果']
        with patch.object(gsheet, 'ensure_columns_in_sheet', return_value=headers), \
             patch.object(gsheet, 'set_customer_notice_clip_style'):
            gsheet.update_sheet_rows(ws, {5: {'狀態': '待確認', '結果': '成功'}, 6: {'狀態': '未安排'}})
        ranges = {u['range']: u['values'][0][0] for u in ws.batch_update.call_args.args[0]}
        self.assertEqual(ranges.get('A5'), '待確認')
        self.assertEqual(ranges.get('B5'), '成功')
        self.assertNotIn('C5', ranges)
        self.assertNotIn('A6', ranges)


class MonthlyConfirmGuardTest(unittest.TestCase):
    def test_monthly_confirm_keeps_calendar_and_marks_pending(self):
        event = {'summary': '王小明 每月確認/自行預約', 'colorId': '5'}
        with patch.dict(orders.GOOGLE_CALENDAR_MAP, {'台北': 'cal'}), \
             patch.object(orders, 'find_matching_calendar_event', return_value=event), \
             patch.object(orders, 'sync_calendar_color_for_row') as sync:
            info = orders.stage_calendar_color(_row(2), object(), '台北')
        sync.assert_not_called()
        self.assertEqual(info['狀態'], '待確認')
        self.assertEqual(info['日曆改色結果'], '未改')

    def test_normal_event_goes_through_color_sync(self):
        with patch.dict(orders.GOOGLE_CALENDAR_MAP, {'台北': 'cal'}), \
             patch.object(orders, 'find_matching_calendar_event', return_value={'summary': '一般'}), \
             patch.object(orders, 'sync_calendar_color_for_row', return_value={'日曆改色結果': '成功'}) as sync:
            info = orders.stage_calendar_color(_row(2), object(), '台北')
        sync.assert_called_once()
        self.assertEqual(info, {'日曆改色結果': '成功'})


class ExactRecoveryMetaTest(unittest.TestCase):
    def test_exact_order_query_used_before_list_fallback(self):
        session = MagicMock()
        session.get.return_value = MagicMock(status_code=200, text='html')
        block = {'order_no': 'LC123', 'lines': ['王小明', '服務人員：陳一', '車馬費：200']}
        with patch.object(orders, 'extract_order_cards_from_purchase_html', return_value=[block]), \
             patch.object(orders, '_extract_service_date_time', return_value=('2026-10-20', '09:00-12:00')), \
             patch.object(orders, '_extract_staff_line', return_value='陳一'), \
             patch.object(orders, '_extract_status_line', return_value='已處理'), \
             patch.object(orders, '_fetch_order_meta_from_purchase_list') as fallback:
            meta = orders.fetch_order_meta_by_order_no(session, 'LC123')
        fallback.assert_not_called()
        self.assertEqual(session.get.call_args.kwargs['params']['orderNo'], 'LC123')
        self.assertEqual(meta['服務人員'], '陳一')
        self.assertEqual(meta['車馬費'], '200')

    def test_falls_back_when_exact_query_misses(self):
        session = MagicMock()
        session.get.return_value = MagicMock(status_code=500)
        with patch.object(orders, '_fetch_order_meta_from_purchase_list', return_value={'x': 1}) as fallback:
            self.assertEqual(orders.fetch_order_meta_by_order_no(session, 'LC9'), {'x': 1})
        fallback.assert_called_once_with(session, 'LC9')


class RecoverOnlyUnarrangedTest(unittest.TestCase):
    def test_non_unarranged_blank_rows_never_reach_backend(self):
        df = pd.DataFrame([_row(2, 狀態='已安排'), _row(3, 狀態='取消')])
        with patch.object(safety, '_load_worksheet_unique', return_value=('ws', df)), \
             patch.object(orders, 'login') as login:
            result = safety._recover_before_create('dev', '台北', 'e', 'p', 's', 2, 3, [2, 3], ['建單'], print)
        login.assert_not_called()
        self.assertEqual(result, ('ws', [], [], [], 0))


class LemonRetryTest(unittest.TestCase):
    def test_lemon_added_only_for_no_schedule_rows_then_retried(self):
        row = pd.Series(_row(2))
        first = {2: {'結果': '失敗', '原因': '無班表'}}
        second = {2: {'結果': '成功', '訂單編號': 'LC1'}}
        with patch.object(orders, 'process_one_group', side_effect=[first, second]) as core, \
             patch.object(orders, 'ensure_lemon_cleaner_shifts', return_value={'success': True, 'assigned': [1]}) as lemon, \
             patch.object(orders, 'get_csrf_token', return_value='t2'):
            out = guard.process_one_group_with_lemon_retry(object(), [(2, row)], 't', None, '台北', allow_auto_lemon_shift=True, logger=lambda m: None)
        self.assertEqual(out, second)
        self.assertEqual(core.call_count, 2)
        self.assertTrue(all(c.kwargs['allow_auto_lemon_shift'] is False for c in core.call_args_list))
        lemon.assert_called_once()

    def test_no_lemon_when_disabled_or_schedule_exists(self):
        row = pd.Series(_row(2))
        with patch.object(orders, 'process_one_group', return_value={2: {'結果': '失敗', '原因': '無班表'}}) as core, \
             patch.object(orders, 'ensure_lemon_cleaner_shifts') as lemon:
            guard.process_one_group_with_lemon_retry(object(), [(2, row)], 't', None, '台北', allow_auto_lemon_shift=False)
        lemon.assert_not_called()
        self.assertEqual(core.call_count, 1)


class HybridRunnerTest(unittest.TestCase):
    def test_multi_groups_first_then_singles_with_per_group_writeback(self):
        df = pd.DataFrame([
            _row(2), _row(3, 電話='0912345678', 日期='2026/10/21'), _row(4, 電話='0988000000'),
        ])
        calls = []

        def core(session, rows_with_idx, *args, **kwargs):
            calls.append([r for r, _ in rows_with_idx])
            return {r: {'結果': '成功', '訂單編號': f'LC{r}'} for r, _ in rows_with_idx}

        with patch.object(safety, '_recover_before_create', return_value=('ws', [2, 3, 4], [], [], 3)), \
             patch.object(safety, '_checkpoint'), \
             patch.object(hybrid, '_load_worksheet_unique', return_value=('ws', df)), \
             patch.object(hybrid, '_login_once', return_value=object()), \
             patch.object(orders, 'get_csrf_token', return_value='t'), \
             patch.object(orders, 'update_sheet_rows') as writeback, \
             patch.object(hybrid, 'process_one_group_with_lemon_retry', side_effect=core):
            progress = []
            result = hybrid.run_process_web_hybrid(
                env_name='dev', region='台北', backend_email='e', backend_password='p', sheet_name='s',
                start_row=2, end_row=4, selected_actions=['建單'], logger=lambda m: None,
                selected_rows=[2, 3, 4], progress_callback=lambda *a: progress.append(a),
            )
        self.assertEqual(calls, [[2, 3], [4]])
        self.assertEqual(result['success_count'], 3)
        self.assertEqual(writeback.call_args_list[0].args[1].keys(), {2, 3})
        self.assertEqual(progress[-1][:3], (3, 3, 0))


if __name__ == '__main__':
    unittest.main()
