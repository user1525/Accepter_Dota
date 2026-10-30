import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import cv2
import numpy as np
from PyQt5.QtWidgets import QApplication
from core.config import Config
from core.image_detector import ImageDetector
from ui.main_window_optimized import MainWindow


class PortableUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_template_in_unicode_folder(self):
        with tempfile.TemporaryDirectory(prefix='шаблоны-') as folder:
            pattern = np.random.default_rng(42).integers(0, 256, (15, 20, 3), dtype=np.uint8)
            path = Path(folder) / 'кнопка.png'
            path.write_bytes(cv2.imencode('.png', pattern)[1].tobytes())
            screen = np.zeros((100, 100, 3), dtype=np.uint8)
            screen[20:35, 30:50] = pattern
            result = ImageDetector().find_template(path, screenshot=screen)
            self.assertTrue(result['found'])
            self.assertEqual(result['position'], (40, 27))

    def test_status_tracks_settings_and_recovers_from_save_error(self):
        with tempfile.TemporaryDirectory() as folder:
            config = Config(Path(folder) / 'config.json')
            with patch('ui.main_window_optimized.Config', return_value=config):
                window = MainWindow(enable_hotkeys=False)
                config.config.update(telegram_enabled=True, telegram_bot_token='dummy', telegram_chat_id='1')
                window.refresh_notification_status()
                self.assertIn('Включено', window.notification_status_buttons['Telegram'].text())
                config.config['telegram_enabled'] = False
                config.last_error = 'Ошибка сохранения'
                window.refresh_notification_status()
                self.assertIn('Выключено', window.notification_status_buttons['Telegram'].text())
                self.assertFalse(window.config_warning.isHidden())
                config.last_error = ''
                window.refresh_notification_status()
                self.assertTrue(window.config_warning.isHidden())
                window.close()
                window.deleteLater()
