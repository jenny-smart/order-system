# 移植自 orders-system test_sheets_quota.py（fbf485d）。
# 雲端批次（cloud_batch_booking／cloud_booking_progress）尚未移植到 order-system，
# 對應的兩個測試（部分中止保留結果、進度寫入節流）待雲端批次移植時一併加入。
from unittest.mock import MagicMock, patch
import pytest
from gspread.exceptions import APIError
from gspread.http_client import HTTPClient
import shared.sheets_quota as quota


def api_error(code):
    response = MagicMock(status_code=code)
    response.json.return_value = {'error': {'code': code, 'message': 'quota' if code == 429 else 'forbidden'}}
    return APIError(response)


def test_quota_retry_waits_and_repeats_only_sheets_request():
    client = object.__new__(quota.QuotaHTTPClient)
    with patch.object(HTTPClient, 'request', side_effect=[api_error(429), 'ok']) as request, \
         patch.object(quota, 'pace'), patch.object(quota.time, 'sleep') as sleep:
        assert client.request('post', 'sheets/update') == 'ok'
    assert request.call_count == 2
    sleep.assert_called_once_with(2)


def test_nonquota_error_is_not_retried():
    client = object.__new__(quota.QuotaHTTPClient)
    with patch.object(HTTPClient, 'request', side_effect=api_error(403)) as request, patch.object(quota, 'pace'):
        with pytest.raises(APIError):
            client.request('post', 'sheets/update')
    assert request.call_count == 1


def test_quota_retry_is_bounded():
    client = object.__new__(quota.QuotaHTTPClient)
    with patch.object(HTTPClient, 'request', side_effect=api_error(429)) as request, \
         patch.object(quota, 'pace'), patch.object(quota.time, 'sleep') as sleep:
        with pytest.raises(APIError):
            client.request('get', 'sheets/read')
    assert request.call_count == 7
    assert [call.args[0] for call in sleep.call_args_list] == [2, 4, 8, 16, 32, 32]


def test_pacing_is_shared_between_client_instances():
    with patch.dict(quota._last, {}, clear=True), \
         patch.object(quota.time, 'monotonic', side_effect=[0, 0, 0, 2]), \
         patch.object(quota.time, 'sleep') as sleep:
        quota.pace('post')
        quota.pace('post')
    sleep.assert_called_once_with(2)


def test_gsheet_client_uses_quota_http_client():
    import orders  # noqa: F401  shared.gsheet 與 orders 互相引用，先載入 orders
    import shared.gsheet as gsheet
    with patch.object(gsheet, 'get_service_account_info', return_value={}), \
         patch.object(gsheet.Credentials, 'from_service_account_info', return_value='creds'), \
         patch.object(gsheet.gspread, 'authorize') as authorize:
        gsheet.build_gsheet_client()
    assert authorize.call_args.kwargs['http_client'] is quota.QuotaHTTPClient
