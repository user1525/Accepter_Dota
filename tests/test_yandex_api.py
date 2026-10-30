import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError
from core.yandex_smart_home import YandexSmartHome, YandexError


class YandexTests(unittest.TestCase):
    def test_expired_token_is_actionable(self):
        with patch('core.yandex_smart_home.urlopen', side_effect=HTTPError('https://api.iot.yandex.net', 401, 'unauthorized', {}, None)):
            with self.assertRaisesRegex(YandexError, 'новый'):
                YandexSmartHome('secret').list_scenarios()

    def test_api_error_is_not_an_empty_scenario_list(self):
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.read.return_value = b'{"status":"error"}'
        with patch('core.yandex_smart_home.urlopen', return_value=response):
            with self.assertRaises(YandexError):
                YandexSmartHome('secret').list_scenarios()

    def test_scenario_id_is_encoded(self):
        api = YandexSmartHome('secret')
        api._request = Mock(return_value={'status': 'ok'})
        self.assertTrue(api.launch_scenario('x/y'))
        api._request.assert_called_once_with('POST', '/scenarios/x%2Fy/actions')
