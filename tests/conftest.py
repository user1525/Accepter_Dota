"""Test-wide fail-closed guards: no live desktop or service effects."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from unittest.mock import patch
import pytest


@pytest.fixture(autouse=True)
def isolated_external_effects(tmp_path):
    attempts = []
    def blocked(name):
        def deny(*args, **kwargs):
            attempts.append(name)
            raise RuntimeError('Test attempted forbidden external effect: ' + name)
        return deny
    with patch('requests.sessions.Session.request', side_effect=blocked('HTTP')), \
         patch('core.yandex_smart_home.urlopen', side_effect=blocked('Yandex HTTP')), \
         patch('keyboard.add_hotkey', side_effect=blocked('global hotkey')), \
         patch('keyboard.hook', side_effect=blocked('global keyboard hook')), \
         patch('pyautogui.press', side_effect=blocked('global keyboard input')), \
         patch('pyautogui.screenshot', side_effect=blocked('desktop capture')), \
         patch('PIL.ImageGrab.grab', side_effect=blocked('window capture')), \
         patch('core.config.user_data_root', return_value=tmp_path / 'isolated-default-config'):
        yield
    assert not attempts, 'Forbidden effect attempts: ' + ', '.join(attempts)
