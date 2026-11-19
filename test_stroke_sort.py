from shared.stroke_sort import name_stroke_key, stroke_count


def test_taiwan_stroke_counts():
    # 教育部國語辭典總筆畫：阝算 3 劃、艹算 4 劃
    assert [stroke_count(c) for c in "王林陳黃蔡邱蘇葉鄭劉"] == [4, 8, 11, 12, 15, 8, 20, 13, 15, 15]


def test_surname_then_given_name_then_non_chinese():
    names = ["陳曉倫", "Connie Hsu", "王大明", "陳怡晴", "林佩君", ""]
    assert sorted(names, key=name_stroke_key) == ["王大明", "林佩君", "陳怡晴", "陳曉倫", "Connie Hsu", ""]
