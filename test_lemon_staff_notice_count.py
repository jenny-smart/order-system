from unittest.mock import patch

from quick_order import _count_staff_from_lines, _format_period_display


def test_lemon_staff_is_included_in_notice_headcount():
    with patch("shared.text_parsing.orders._extract_staff_line", return_value="王小明 X 檸檬人1"):
        assert _count_staff_from_lines(["專員：王小明 X 檸檬人1"]) == "2"
    with patch("shared.text_parsing.orders._extract_staff_line", return_value="檸檬人2"):
        assert _count_staff_from_lines(["專員：檸檬人2"]) == "1"


def test_missing_headcount_is_formatted_as_one_person_hours():
    assert _format_period_display("08:30-12:30", "1") == "08:30-12:30（1人4小時），共4人時"
    assert _format_period_display("09:00-12:00", "1") == "09:00-12:00（1人3小時），共3人時"
