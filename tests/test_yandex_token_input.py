import io
import pytest
from unittest.mock import patch
from core.yandex_smart_home import YandexSmartHome

@pytest.mark.parametrize('entered',[
 'y0__synthetic', ' access_token=y0__synthetic ',
 'access_token=y0__synthetic&expires_in=3600',
 'https://oauth.yandex.ru/verification_code#access_token=y0__synthetic&expires_in=3600',
 'Bearer y0__synthetic', 'OAuth y0__synthetic', '"y0__synthetic"'])
def test_header_contains_only_access_token(entered):
 with patch('core.yandex_smart_home.urlopen',return_value=io.BytesIO(b'{"status":"ok","scenarios":[]}')) as request:
  assert YandexSmartHome(entered).list_scenarios()==[]
  assert request.call_args.args[0].get_header('Authorization')=='Bearer y0__synthetic'
