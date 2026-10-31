import unittest
from unittest.mock import Mock, patch

from core.telegram_sender import TelegramSender
from core.image_detector import ImageDetector
from core.accepter import DotaAccepter
from ui.main_window_optimized import MainWindow, WorkerThread


class RegressionTests(unittest.TestCase):
    def test_stop_during_detection_does_not_press_enter(self):
        accepter = DotaAccepter(config=Mock())
        accepter.running = True
        accepter.window_provider = Mock(return_value=(0, 0, 1280, 720))
        def found(_, **kwargs):
            accepter.stop()
            return dict(found=True, position=(1, 1), confidence=1)
        accepter.image_detector.find_template = found
        with patch('core.accepter.Path.is_file', return_value=True), patch('core.accepter.pyautogui.press') as press:
            self.assertFalse(accepter.find_and_click_accept_button())
        press.assert_not_called()

    def test_stop_before_worker_starts(self):
        accepter = DotaAccepter(config=Mock())
        accepter.stop()
        accepter.find_and_click_accept_button = Mock()
        self.assertFalse(accepter.run_simple_mode())
        accepter.find_and_click_accept_button.assert_not_called()

    def test_yandex_enabled_uses_selected_scenario(self):
        config = Mock()
        config.get_yandex_token.return_value = 'test'
        config.get_yandex_scenario_id.return_value = 'scenario'
        accepter = DotaAccepter(config=config)
        with patch('core.accepter.YandexSmartHome') as client:
            accepter.send_yandex_notification()
        client.return_value.launch_scenario.assert_called_once_with('scenario')

    def test_yandex_disabled_does_not_call_network(self):
        config = Mock()
        config.is_yandex_enabled.return_value = False
        accepter = DotaAccepter(config=config)
        with patch('core.accepter.YandexSmartHome') as client:
            accepter.send_yandex_notification()
        client.assert_not_called()

    def test_notification_without_image_is_text_only(self):
        sender = TelegramSender('test', 'test')
        sender.send_message = Mock(return_value=(True, 'ok'))
        sender.send_screenshot = Mock(return_value=(True, 'ok'))
        sender.send_game_accepted_notification()
        sender.send_message.assert_called_once()
        sender.send_screenshot.assert_not_called()

    def test_explicit_image_is_sent(self):
        sender = TelegramSender('test', 'test')
        sender.send_screenshot = Mock(return_value=(True, 'ok'))
        picture = object()
        sender.send_game_accepted_notification(picture)
        self.assertIs(sender.send_screenshot.call_args.args[1], picture)

    def test_wait_timeout(self):
        self.assertFalse(ImageDetector().wait_for_template('missing', timeout=0)['found'])

    def test_worker_preserves_failed_result(self):
        accepter = Mock()
        accepter.run_check_mode.return_value = False
        worker = WorkerThread(accepter, 'check')
        results = []
        worker.finished_signal.connect(results.append)
        worker.run()
        self.assertEqual(results, [False])

    def test_cancel_close_keeps_hotkey(self):
        window, event = Mock(), Mock()
        window._closing = False
        window.telegram_panel.busy.return_value = False
        window.yandex_panel.busy.return_value = False
        with patch('ui.main_window_optimized.QMessageBox.question', return_value=65536), patch('ui.main_window_optimized.keyboard.unhook_all') as unhook:
            MainWindow.closeEvent(window, event)
        event.ignore.assert_called_once()
        unhook.assert_not_called()
        window.telegram_panel.cancel.assert_not_called()

    def test_close_stops_polling_before_waiting(self):
        window, event = Mock(), Mock()
        window._closing = False
        window.worker_thread = None
        window.yandex_panel.generation = 0
        window.telegram_panel.busy.return_value = True
        with patch('ui.main_window_optimized.QTimer.singleShot') as retry:
            MainWindow.closeEvent(window, event)
        window.telegram_panel.cancel.assert_called_once()
        retry.assert_called_once()
        event.ignore.assert_called_once()


if __name__ == '__main__':
    unittest.main()
