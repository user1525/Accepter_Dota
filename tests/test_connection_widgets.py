import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QThread
from core.config import Config
from core.telegram_pairing import TelegramPairing
from ui.connection_widgets import TelegramPanel, YandexPanel


class PanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.config = Config(Path(self.temp.name) / 'config.json')
        self.panels = []

    def tearDown(self):
        for panel in self.panels:
            if isinstance(panel, TelegramPanel):
                panel.timer.stop()
            for job in list(panel.jobs):
                job.wait(2000)
            self.app.processEvents()
            panel.deleteLater()
        self.app.processEvents()
        self.temp.cleanup()

    def panel(self, kind):
        panel = kind(self.config)
        self.panels.append(panel)
        return panel

    def test_empty_telegram_disables_test(self):
        p = self.panel(TelegramPanel)
        self.assertFalse(p.test_button.isEnabled())
        self.assertFalse(p.open_button.isEnabled())
        p.connect_bot()
        self.assertIn('вставьте токен', p.status.text())

    def test_cancel_preserves_existing_connection(self):
        self.config.config.update(telegram_bot_token='old', telegram_chat_id='99')
        p = self.panel(TelegramPanel)
        p.pairing = TelegramPairing('new')
        p.cancel()
        self.assertEqual(self.config.get_telegram_bot_token(), 'old')
        self.assertEqual(self.config.get_telegram_chat_id(), '99')

    def test_failed_checkbox_save_restores_display(self):
        self.config.config.update(telegram_bot_token='test', telegram_chat_id='99')
        p = self.panel(TelegramPanel)
        with patch.object(self.config, 'save_config', return_value=False):
            p.enabled.setChecked(True)
        self.assertFalse(p.enabled.isChecked())
        self.assertFalse(self.config.is_telegram_enabled())

    def test_yandex_has_no_client_id_field(self):
        p = self.panel(YandexPanel)
        self.assertFalse(hasattr(p, 'client_id'))

    def test_pairing_commits_both_fields_only_on_match(self):
        p = self.panel(TelegramPanel)
        p.pairing = TelegramPairing('new')
        p.received({'id': '101', 'name': 'Test'}, None)
        reloaded = Config(self.config.config_file)
        self.assertEqual(reloaded.get_telegram_chat_id(), '101')
        self.assertEqual(reloaded.get_telegram_bot_token(), 'new')
        self.assertFalse(reloaded.is_telegram_verified())
        self.assertTrue(p.test_button.isEnabled())
        self.assertIsNone(p.pairing)

    def test_failed_save_preserves_old_connection(self):
        p = self.panel(TelegramPanel)
        p.pairing = TelegramPairing('new')
        with patch.object(self.config, 'save_config', return_value=False):
            p.received({'id': '101', 'name': 'Test'}, None)
        self.assertEqual(self.config.get_telegram_chat_id(), '')
        self.assertIn('сохранить', p.status.text())

    def test_cancel_discards_inflight_result(self):
        p = self.panel(TelegramPanel)
        called = []
        p.run_job(lambda: 'result', lambda *args: called.append(args))
        p.cancel()
        for job in list(p.jobs):
            job.wait(1000)
        self.app.processEvents()
        self.assertEqual(called, [])

    def test_network_result_runs_on_gui_thread(self):
        p = self.panel(TelegramPanel)
        threads = []
        p.run_job(lambda: QThread.currentThread(),
                  lambda value, error: threads.extend([value, QThread.currentThread()]))
        for job in list(p.jobs):
            job.wait(1000)
        self.app.processEvents()
        self.assertEqual(len(threads), 2)
        self.assertIs(threads[1], self.app.thread())
        self.assertIsNot(threads[0], threads[1])

    def test_yandex_refresh_preserves_selected_scenario(self):
        self.config.config.update(yandex_token='token', yandex_scenario_id='b',
                                  yandex_scenario_name='B', yandex_verified=True)
        p = self.panel(YandexPanel)
        p.loaded(('token', [('a', 'A'), ('b', 'B')]), None)
        self.assertEqual(p.scenarios.currentData(), 'b')
        self.assertTrue(self.config.is_yandex_verified())
        p.scenarios.setCurrentIndex(1)
        self.assertEqual(self.config.get_yandex_scenario_id(), 'a')
        self.assertFalse(self.config.is_yandex_verified())

    def test_yandex_new_account_does_not_select_first_scenario(self):
        p = self.panel(YandexPanel)
        p.token.setText('token')
        p.loaded(('token', [('a', 'A')]), None)
        self.assertFalse(p.test_button.isEnabled())
        self.assertFalse(self.config.is_yandex_verified())
        self.assertEqual(self.config.get_yandex_scenario_id(), '')

    def test_yandex_save_failure_restores_displayed_selection(self):
        self.config.config.update(yandex_token='token', yandex_scenario_id='b', yandex_scenario_name='B')
        p = self.panel(YandexPanel)
        p.loaded(('token', [('a', 'A'), ('b', 'B')]), None)
        with patch.object(self.config, 'save_config', return_value=False):
            p.scenarios.setCurrentIndex(1)
        self.assertEqual(p.scenarios.currentData(), 'b')
        self.assertEqual(self.config.get_yandex_scenario_id(), 'b')

    def test_yandex_changed_token_cannot_test_old_account(self):
        self.config.config.update(yandex_token='old', yandex_scenario_id='a')
        p = self.panel(YandexPanel)
        p.token.setText('new')
        self.assertFalse(p.test_button.isEnabled())
        self.assertEqual(self.config.get_yandex_token(), 'old')

    def test_yandex_test_failure_resets_verification(self):
        p = self.panel(YandexPanel)
        self.config.config['yandex_verified'] = True
        p.tested(None, 'Ошибка сети')
        self.assertFalse(self.config.is_yandex_verified())

    def test_main_window_initializes_with_empty_config(self):
        from ui.main_window_optimized import MainWindow
        with patch('ui.main_window_optimized.Config', return_value=self.config), \
             patch.object(MainWindow, 'setup_keyboard_shortcut'), \
             patch('ui.main_window_optimized.keyboard.unhook_all'):
            window = MainWindow()
            window.show()
            self.app.processEvents()
            self.assertIsInstance(window.telegram_panel, TelegramPanel)
            self.assertIsInstance(window.yandex_panel, YandexPanel)
            window.close()
            window.deleteLater()
