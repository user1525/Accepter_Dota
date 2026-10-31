import unittest
from unittest.mock import Mock
from core.accepter import DotaAccepter


class DetectionTests(unittest.TestCase):
    def test_one_sound_per_button_appearance(self):
        accepter = DotaAccepter(config=Mock())
        accepter.running = True
        accepter.sound_manager = Mock()
        for visible in (False, True, True, True, False, True, True):
            accepter.notify_button_visibility(visible)
        self.assertEqual(accepter.sound_manager.play_sound.call_count, 2)
        accepter.sound_manager.play_sound.assert_called_with('detection')

    def test_stopped_detector_does_not_play(self):
        accepter = DotaAccepter(config=Mock())
        accepter.sound_manager = Mock()
        accepter.stop()
        accepter.notify_button_visibility(True)
        accepter.sound_manager.play_sound.assert_not_called()

    def test_stop_during_post_accept_pause_does_not_notify(self):
        config = Mock()
        config.get_check_interval.return_value = 0.1
        config.get_click_pause.return_value = 0
        accepter = DotaAccepter(config=config)
        accepter.window_provider = Mock(return_value=(0, 0, 1280, 720))
        def detect():
            accepter.stop()
            return True
        accepter.find_and_click_accept_button = detect
        accepter.send_telegram_notification = Mock()
        accepter.send_yandex_notification = Mock()
        self.assertFalse(accepter.run_simple_mode())
        accepter.send_telegram_notification.assert_not_called()
        accepter.send_yandex_notification.assert_not_called()
