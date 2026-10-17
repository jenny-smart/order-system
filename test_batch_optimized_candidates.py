import unittest
from unittest.mock import patch

import pandas as pd

import function.batch_booking_optimized as batch


def _row(**fields):
    row = {'服務人時': '2人4小時', '備註': '', '姓名': '王小明', '電話': '0912-345-678',
           '地址': '台北市大安區測試路1號', '日期': '2026/09/26', '開始時間': '09:00',
           '結束時間': '12:00', '狀態': '未安排', '購買項目': '居家清潔', '訂單編號': ''}
    row.update(fields)
    return row


class OptimizedBatchCandidatesTest(unittest.TestCase):
    def load(self, rows):
        df = pd.DataFrame(rows)
        df['__sheet_row__'] = range(2, len(rows) + 2)
        with patch.object(batch, 'load_worksheet', return_value=(None, df)):
            return batch._load_candidates('台北202609')

    def test_only_unarranged_rows_without_order_number(self):
        work = self.load([
            _row(),
            _row(狀態='已安排'),
            _row(狀態=''),
            _row(訂單編號='LC123'),
        ])
        self.assertEqual(work['__sheet_row__'].tolist(), [2])

    def test_groups_by_normalized_phone_and_address(self):
        work = self.load([
            _row(),
            _row(姓名='王 小明', 電話='0912345678', 日期='2026/09/27', 服務人時='1人3小時'),
            _row(電話='0988000000'),
        ])
        groups = batch._build_groups(work)
        self.assertEqual(sorted(g['count'] for g in groups), [1, 2])
        multi = next(g for g in groups if g['count'] == 2)
        self.assertEqual(multi['name'], '王小明')
        self.assertEqual(multi['date_count'], 2)


if __name__ == '__main__':
    unittest.main()
