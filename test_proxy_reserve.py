import unittest

import pandas as pd

import shared.proxy_reserve as pr


class ProxyReserveTest(unittest.TestCase):
    def test_checked_rows_use_reserve_phone_and_keep_customer_name(self):
        df = pd.DataFrame([
            {"姓名": "王小明", "電話": "0912345678", "代客保留": "TRUE"},
            {"姓名": "李小華", "電話": "0922333444", "代客保留": "FALSE"},
            {"姓名": "陳大文", "電話": "0933444555", "代客保留": ""},
        ])
        pr.apply(df)
        self.assertEqual(list(df["電話"]), [pr.RESERVE_PHONE, "0922333444", "0933444555"])
        self.assertEqual(pr.proxy_name(df.iloc[0]), "王小明")
        self.assertEqual(df.iloc[0][pr.CUSTOMER_PHONE_KEY], "0912345678")
        self.assertEqual(pr.proxy_name(df.iloc[1]), "")
        self.assertEqual(pr.memo_for(" 王小明 "), "代客保留：王小明")

    def test_sheet_without_column_is_unchanged(self):
        df = pd.DataFrame([{"姓名": "王小明", "電話": "0912345678"}])
        pr.apply(df)
        self.assertEqual(list(df.columns), ["姓名", "電話"])
        self.assertEqual(pr.proxy_name(df.iloc[0]), "")

    def test_checkbox_values(self):
        for value in ("TRUE", "true", "V", "✓", "是", "1"):
            self.assertTrue(pr.is_checked(value), value)
        for value in ("", "FALSE", "否", "0", None):
            self.assertFalse(pr.is_checked(value), value)

    def test_proxy_rows_group_separately_from_customer_rows(self):
        import orders
        df = pd.DataFrame([
            {"姓名": "王小明", "電話": "0912345678", "地址": "台北市大安區", "服務人時": "2人",
             "開始時間": "9:00", "結束時間": "12:00", "代客保留": "TRUE"},
            {"姓名": "王小明", "電話": "0912345678", "地址": "台北市大安區", "服務人時": "2人",
             "開始時間": "9:00", "結束時間": "12:00", "代客保留": ""},
        ])
        pr.apply(df)
        self.assertNotEqual(orders.build_group_key(df.iloc[0]), orders.build_group_key(df.iloc[1]))

    def test_checked_row_without_name_is_rejected(self):
        df = pd.DataFrame([{"姓名": " ", "電話": "0912345678", "代客保留": "TRUE"},
                           {"姓名": "", "電話": "0922333444", "代客保留": ""}])
        pr.apply(df)
        with self.assertRaises(ValueError):
            pr.proxy_name(df.iloc[0])
        self.assertEqual(pr.proxy_name(df.iloc[1]), "")


if __name__ == "__main__":
    unittest.main()


def test_needs_native_address_only_for_proxy_rows():
    df = pd.DataFrame([{"姓名": "王亭雅", "電話": "0912269511", "代客保留": "TRUE"},
                       {"姓名": "王孟如", "電話": "0989125030", "代客保留": "FALSE"}])
    pr.apply(df)
    assert pr.needs_native_address(df.iloc[0]) is True
    assert pr.needs_native_address(df.iloc[1]) is False
    assert pr.needs_native_address({}) is False


def test_proxy_rows_of_same_address_group_together_in_optimized_mode():
    """批次優化／雲端：同客人同地址多日期同組（一次勾多時段）；不同地址分開。"""
    import shared.hybrid_batch_runner as hb
    base = {"電話": "0912269511", "代客保留": "TRUE", "開始時間": "09:00", "結束時間": "12:00", "服務人時": "6"}
    df = pd.DataFrame([dict(base, 姓名="王亭雅", 地址="新北市中和區測試路1號", 日期=d)
                       for d in ("2026/12/14", "2027/01/11", "2027/02/15")]
                      + [dict(base, 姓名="林小明", 電話="0922000000", 地址="台北市大安區測試路2號", 日期="2026/12/14")])
    pr.apply(df)
    keys = [hb._phone_address_group_key(r) for _, r in df.iterrows()]
    assert keys[0] == keys[1] == keys[2] and keys[3] != keys[0]
    assert keys[0][0] == pr.RESERVE_PHONE
