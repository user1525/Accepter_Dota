"""Safety contracts using synthetic frames and mocks; never touch a live game."""
from pathlib import Path
from unittest.mock import Mock, patch
import ctypes
import cv2
import numpy as np
import pytest
from PIL import Image
from core.accepter import DotaAccepter
from core.image_detector import ImageDetector
from core.templates import validate_templates
from core.telegram_sender import TelegramSender
from core import game_window

REGION = (100, 50, 640, 480)
FOUND = {'found': True, 'position': (200, 100), 'confidence': 1., 'region': REGION}
MISSING = {'found': False, 'position': None, 'confidence': 0.}

@pytest.fixture(autouse=True)
def no_real_effects():
    with patch('pyautogui.press', side_effect=AssertionError('Real input forbidden')), \
         patch('pyautogui.screenshot', side_effect=AssertionError('Desktop capture forbidden')), \
         patch('PIL.ImageGrab.grab', side_effect=AssertionError('Desktop capture forbidden')), \
         patch('requests.sessions.Session.request', side_effect=AssertionError('Network forbidden')), \
         patch('core.yandex_smart_home.urlopen', side_effect=AssertionError('Network forbidden')):
        yield

@pytest.fixture
def accepter():
    cfg = Mock()
    cfg.get_image_threshold.return_value = .8
    cfg.get_pre_accept_delay.return_value = 0
    cfg.get_check_interval.return_value = .001
    cfg.get_click_pause.return_value = 0
    cfg.is_telegram_enabled.return_value = False
    cfg.is_yandex_enabled.return_value = False
    obj = DotaAccepter(template_path=Path(__file__).resolve().parents[1] / 'resources/templates', config=cfg)
    obj.window_provider = Mock(return_value=REGION)
    obj.running = True
    return obj


def test_requires_fresh_match_after_delay(accepter):
    accepter.find_accept_button = Mock(side_effect=[dict(FOUND), dict(MISSING)])
    with patch('pyautogui.press') as press:
        assert not accepter.find_and_click_accept_button()
    press.assert_not_called()


def test_one_enter_until_two_real_missing_frames(accepter):
    accepter.find_accept_button = Mock(side_effect=[dict(FOUND), dict(FOUND), dict(FOUND),
        dict(MISSING), dict(FOUND), dict(MISSING), dict(MISSING), dict(FOUND), dict(FOUND)])
    with patch('pyautogui.press') as press:
        assert accepter.find_and_click_accept_button()
        assert not accepter.find_and_click_accept_button()
        assert not accepter.find_and_click_accept_button()
        assert not accepter.find_and_click_accept_button()
        assert not accepter.find_and_click_accept_button()
        assert not accepter.find_and_click_accept_button()
        assert accepter.find_and_click_accept_button()
    assert press.call_count == 2


def test_focus_or_capture_failure_does_not_rearm(accepter):
    accepter._pressed_visible = True
    accepter.find_accept_button = Mock(side_effect=[dict(MISSING, inactive=True), dict(MISSING, error=True), dict(FOUND)])
    with patch('pyautogui.press') as press:
        for _ in range(3): assert not accepter.find_and_click_accept_button()
    press.assert_not_called()
    assert accepter._pressed_visible


def test_stop_during_fresh_capture_never_enters(accepter):
    def fresh():
        accepter.stop()
        return dict(FOUND)
    accepter.find_accept_button = Mock(side_effect=[dict(FOUND), fresh])
    # Use a callable side effect because Mock list elements are returned verbatim.
    calls = iter([False, True])
    def find():
        if next(calls): accepter.stop()
        return dict(FOUND)
    accepter.find_accept_button = find
    with patch('pyautogui.press') as press:
        assert not accepter.find_and_click_accept_button()
    press.assert_not_called()


def test_final_focus_check_must_match_capture_region(accepter):
    accepter.find_accept_button = Mock(return_value=dict(FOUND))
    accepter.window_provider.return_value = (0, 0, 640, 480)
    with patch('pyautogui.press') as press:
        assert not accepter.find_and_click_accept_button()
    press.assert_not_called()


def test_no_foreground_dota_means_no_capture(accepter):
    accepter.window_provider.return_value = None
    accepter.image_detector.find_template = Mock()
    assert not accepter.find_and_click_accept_button()
    accepter.image_detector.find_template.assert_not_called()


def test_focus_change_during_capture_discards_match(accepter):
    accepter.window_provider.side_effect = [REGION, None]
    accepter.image_detector.find_template = Mock(return_value=dict(FOUND))
    result = accepter.find_accept_button()
    assert not result['found'] and result['inactive']


def test_cancelled_post_accept_wait_never_notifies(accepter):
    def accept():
        accepter.stop()
        return True
    accepter.find_and_click_accept_button = accept
    accepter.send_telegram_notification = Mock()
    accepter.send_yandex_notification = Mock()
    assert not accepter.run_simple_mode()
    accepter.send_telegram_notification.assert_not_called()
    accepter.send_yandex_notification.assert_not_called()


def test_simple_outcome_is_enter_not_confirmed_acceptance(accepter):
    accepter.find_and_click_accept_button = Mock(return_value=True)
    accepter.send_telegram_notification = Mock()
    accepter.send_yandex_notification = Mock()
    assert accepter.run_simple_mode()
    assert accepter.outcome == 'Enter отправлен'
    accepter.send_telegram_notification.assert_not_called()
    accepter.send_yandex_notification.assert_not_called()


def test_stop_in_status_callback_cancels_yandex_before_request(accepter):
    accepter.config.is_yandex_enabled.return_value = True
    accepter.channel_callback = lambda *args: accepter.stop()
    with patch('core.accepter.YandexSmartHome') as client:
        accepter.send_yandex_notification()
    client.assert_not_called()


def test_stop_in_status_callback_cancels_telegram_before_capture(accepter):
    accepter.config.is_telegram_enabled.return_value = True
    accepter.channel_callback = lambda *args: accepter.stop()
    with patch('core.accepter.TelegramSender') as client:
        accepter.send_telegram_notification()
    client.assert_not_called()


def test_synthetic_region_coordinates_and_capture_bounds(tmp_path):
    pattern=np.random.default_rng(2).integers(0,256,(10,12,3),dtype=np.uint8)
    canvas=np.zeros((50,80,3),dtype=np.uint8); canvas[20:30,30:42]=pattern
    path=tmp_path/'шаблон.png'; path.write_bytes(cv2.imencode('.png',pattern)[1].tobytes())
    image=Image.fromarray(cv2.cvtColor(canvas,cv2.COLOR_BGR2RGB))
    with patch('PIL.ImageGrab.grab',return_value=image) as grab:
        result=ImageDetector().find_template(path,region=(-100,50,80,50))
    grab.assert_called_once_with(bbox=(-100,50,-20,100),all_screens=True)
    assert result['found'] and result['position']==(-64,75)


def test_too_small_capture_is_error_not_button_disappearance(tmp_path):
    pattern=np.random.default_rng(2).integers(0,256,(20,20,3),dtype=np.uint8)
    path=tmp_path/'large.png'; path.write_bytes(cv2.imencode('.png',pattern)[1].tobytes())
    result=ImageDetector().find_template(path,screenshot=np.zeros((10,10,3),dtype=np.uint8))
    assert not result['found'] and result['error']


def test_template_validation_checks_mode_specific_files(tmp_path):
    assert not validate_templates(tmp_path)[0]
    pattern=np.random.default_rng(2).integers(0,256,(10,12,3),dtype=np.uint8)
    (tmp_path/'accept_button.png').write_bytes(cv2.imencode('.png',pattern)[1].tobytes())
    assert validate_templates(tmp_path,'simple')[0]
    assert not validate_templates(tmp_path,'check')[0]
    (tmp_path/'hero_select.png').write_bytes(b'broken')
    assert not validate_templates(tmp_path,'check')[0]


def test_telegram_does_not_echo_remote_credentials():
    sender=TelegramSender('synthetic-secret','1')
    with patch('core.telegram_sender.requests.post',return_value=Mock(json=lambda:{'ok':False,'error_code':401,'description':'synthetic-secret'})):
        success,detail=sender.send_message('test')
    assert not success and 'synthetic-secret' not in detail


def test_telegram_screenshot_stays_in_memory():
    sender=TelegramSender('synthetic-secret','1')
    picture=Image.new('RGB',(2,2))
    def response(*args,**kwargs):
        assert kwargs['files']['photo'][1].read().startswith(b'\x89PNG')
        return Mock(json=lambda:{'ok':True})
    with patch('core.telegram_sender.requests.post',side_effect=response):
        assert sender.send_screenshot('test',picture)[0]


def test_telegram_reports_actual_outcome_and_escapes_html():
    sender=TelegramSender('synthetic-secret','1'); sender.send_message=Mock(return_value=(True,'ok'))
    sender.send_game_accepted_notification(message='Enter <отправлен>. Принятие не подтверждено.')
    body=sender.send_message.call_args.args[0]
    assert '&lt;отправлен&gt;' in body and 'Игра принята!' not in body


class WinFunction:
    def __init__(self,call): self.call=call
    def __call__(self,*args): return self.call(*args)


def fake_windows(executable='C:\\games\\dota2.exe',changed=False):
    user, kernel=Mock(),Mock()
    calls=iter([10,11 if changed else 10])
    user.GetForegroundWindow=WinFunction(lambda:next(calls))
    def pid(hwnd,out): out._obj.value=123; return 1
    def rect(hwnd,out): out._obj.right=640; out._obj.bottom=480; return 1
    def origin(hwnd,out): out._obj.x=100; out._obj.y=50; return 1
    user.GetWindowThreadProcessId=WinFunction(pid); user.GetClientRect=WinFunction(rect); user.ClientToScreen=WinFunction(origin)
    kernel.OpenProcess=WinFunction(lambda *args:1234)
    def path(handle,flags,buffer,size): buffer.value=executable; return 1
    kernel.QueryFullProcessImageNameW=WinFunction(path)
    kernel.CloseHandle=WinFunction(Mock(return_value=1))
    return user,kernel


@pytest.mark.parametrize('executable,changed,expected',[(r'C:\games\dota2.exe',False,REGION),(r'C:\apps\other.exe',False,None),(r'C:\games\dota2.exe',True,None)])
def test_foreground_identity_geometry_and_focus_race(executable,changed,expected):
    user,kernel=fake_windows(executable,changed)
    with patch('core.game_window.ctypes.WinDLL',side_effect=[user,kernel]):
        assert game_window.foreground_dota_region()==expected
    kernel.CloseHandle.call.assert_called_once_with(1234)


def test_detection_dispatches_before_delay_and_deduplicates(accepter):
    accepter.start_detection_notifications=Mock()
    accepter.find_accept_button=Mock(side_effect=[dict(FOUND),dict(FOUND),dict(FOUND),dict(MISSING),dict(FOUND),dict(MISSING),dict(MISSING),dict(FOUND),dict(FOUND)])
    order=[]
    accepter.start_detection_notifications.side_effect=lambda:order.append('notify')
    with patch('pyautogui.press',side_effect=lambda *a,**k:order.append('enter')):
        for _ in range(7): accepter.find_and_click_accept_button()
    assert order==['notify','enter','notify','enter']


def test_detection_channels_do_not_block_enter(accepter):
    import threading
    release=threading.Event()
    started=[threading.Event(),threading.Event()]
    accepter.config.is_telegram_enabled.return_value=True
    accepter.config.is_yandex_enabled.return_value=True
    def send(index):
        started[index].set()
        assert release.wait(3)
    accepter.send_telegram_notification=lambda message:send(0)
    accepter.send_yandex_notification=lambda:send(1)
    accepter.find_accept_button=Mock(return_value=dict(FOUND))
    try:
        with patch('pyautogui.press') as press:
            assert accepter.find_and_click_accept_button()
            press.assert_called_once()
        assert all(event.wait(1) for event in started)
    finally:
        release.set()
        for thread in accepter._notification_threads: thread.join()


def test_yandex_delivery_keeps_safe_api_error(accepter):
    from core.yandex_smart_home import YandexError
    accepter.config.is_yandex_enabled.return_value=True
    accepter.config.get_yandex_token.return_value='synthetic'
    accepter.config.get_yandex_scenario_id.return_value='scenario'
    accepter.channel_callback=Mock()
    with patch('core.accepter.YandexSmartHome') as client:
        client.return_value.launch_scenario.side_effect=YandexError('Нет доступа. Для токена нужны права iot:view и iot:control.')
        accepter.send_yandex_notification()
    assert 'iot:control' in accepter.channel_callback.call_args.args[2]


def test_detection_threads_preserve_credentials_and_scenario(accepter):
    accepter.config.is_telegram_enabled.return_value=True
    accepter.config.is_yandex_enabled.return_value=True
    accepter.config.is_telegram_send_screenshot.return_value=False
    accepter.config.get_telegram_bot_token.return_value='synthetic-bot-token'
    accepter.config.get_telegram_chat_id.return_value='1234'
    accepter.config.get_yandex_token.return_value='synthetic-yandex-token'
    accepter.config.get_yandex_scenario_id.return_value='scenario-123'
    with patch('core.accepter.TelegramSender') as telegram, patch('core.accepter.YandexSmartHome') as yandex:
        telegram.return_value.send_game_accepted_notification.return_value=(True,'ok')
        yandex.return_value.launch_scenario.return_value=True
        accepter.start_detection_notifications()
        for thread in accepter._notification_threads: thread.join(2)
        assert all(not thread.is_alive() for thread in accepter._notification_threads)
        telegram.assert_called_once_with('synthetic-bot-token','1234')
        yandex.assert_called_once_with('synthetic-yandex-token')
        yandex.return_value.launch_scenario.assert_called_once_with('scenario-123')
