import pandas as pd

from shared.line_notice_sheet import groups_from_dataframe, parse_row_spec, results_tsv


def test_groups_existing_orders_by_customer_address_and_service():
    df = pd.DataFrame([
        {"__sheet_row__": 2, "姓名": "陳宜慧", "地址": "新北市永和區A號", "購買項目": "居家清潔", "訂單編號": "LC1", "結果": "成功"},
        {"__sheet_row__": 3, "姓名": "陳宜慧", "地址": "新北市永和區A號", "購買項目": "居家清潔", "訂單編號": "LC2", "結果": "成功"},
        {"__sheet_row__": 4, "姓名": "陳宜慧", "地址": "台北市辦公路B號", "購買項目": "辦公室清潔", "訂單編號": "LC3", "結果": "成功"},
        {"__sheet_row__": 5, "姓名": "失敗客", "地址": "地址", "購買項目": "居家清潔", "訂單編號": "LC4", "結果": "失敗"},
    ])
    groups = groups_from_dataframe(df, "2-5")
    assert [group["order_nos"] for group in groups] == [["LC1", "LC2"], ["LC3"]]


def test_tsv_keeps_multiline_notice_in_one_cell():
    output = results_tsv([{
        "order_no": "LC1、LC2", "group": {"name": "陳宜慧", "address": "地址"},
        "text": "第一行\n第二行", "error": None,
    }])
    assert output.startswith("姓名\t地址\t訂單編號\tLINE預約完成通知\t日曆檢查\n")
    assert '"第一行\n第二行"' in output


def test_row_spec_accepts_commas_and_ranges():
    assert parse_row_spec("2,4-5") == {2, 4, 5}
