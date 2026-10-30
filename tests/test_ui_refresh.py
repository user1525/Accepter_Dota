"""User-visible regression cases; all data and effects are synthetic."""
from pathlib import Path
from unittest.mock import patch, Mock
import threading
import pytest
from PyQt5.QtWidgets import QApplication, QMessageBox
from PyQt5.QtTest import QTest
from core.config import Config
from core.single_instance import acquire_instance
from core.sound_manager import SoundManager
from ui.main_window_optimized import MainWindow
from ui.connection_widgets import TelegramPanel, YandexPanel
from ui.sound_settings import SoundSettings


@pytest.fixture(scope='session')
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def config(tmp_path):
    return Config(tmp_path / 'synthetic.json')


@pytest.fixture
def window(app, config):
    window = MainWindow(enable_hotkeys=False, config=config)
    yield window
    window.close()
    window.deleteLater()
    app.processEvents()


def test_pause_direct_edit_persists_and_failed_atomic_write_restores_ui(window, config):
    window.pause_edit.setValue(3.5)
    assert Config(config.config_file).get_click_pause() == 3.5
    before = config.config_file.read_bytes()
    with patch('core.config.os.replace', side_effect=PermissionError('test')):
        window.pause_edit.setValue(8)
    assert window.pause_edit.value() == 3.5
    assert config.get_click_pause() == 3.5
    assert config.config_file.read_bytes() == before
    assert not window.config_warning.isHidden()


def test_navigation_does_not_resize_window(window, app):
    window.resize(820, 700)
    window.show()
    app.processEvents()
    initial = window.size()
    for index in range(5):
        window.navigation.setCurrentRow(index)
        app.processEvents()
        assert window.size() == initial


def test_log_hidden_by_default_bounded_and_expandable(window):
    assert window.log_text.isHidden()
    for i in range(420):
        window.log('Synthetic entry ' + str(i))
    assert window.log_text.document().blockCount() <= 300
    assert 'Synthetic entry 419' in window.log_text.toPlainText()
    assert 'Synthetic entry 0\n' not in window.log_text.toPlainText()
    window.log_toggle.setChecked(True)
    assert not window.log_text.isHidden()


def test_edited_telegram_token_cannot_test_saved_bot(app, config):
    config.config.update(telegram_bot_token='synthetic-old', telegram_chat_id='123', telegram_verified=True)
    panel = TelegramPanel(config)
    assert panel.test_button.isEnabled()
    panel.token.setText('synthetic-new')
    assert not panel.test_button.isEnabled()
    assert 'не сохранён' in panel.status.text()
    with patch.object(panel, 'run_job') as run:
        panel.send_test()
    run.assert_not_called()
    assert config.get_telegram_bot_token() == 'synthetic-old'
    panel.deleteLater()


@pytest.mark.parametrize('kind,prefix', [(TelegramPanel,'telegram'), (YandexPanel,'yandex')])
def test_remove_connection_clears_only_selected_synthetic_service(app, config, kind, prefix):
    config.config.update(telegram_bot_token='synthetic-tg',telegram_chat_id='123',telegram_verified=True,
                         telegram_enabled=True,telegram_send_screenshot=True,yandex_token='synthetic-ya',
                         yandex_scenario_id='scenario',yandex_scenario_name='Test',yandex_verified=True,yandex_enabled=True)
    assert config.save_config()
    panel = kind(config)
    with patch('ui.connection_widgets.QMessageBox.question', return_value=QMessageBox.Yes):
        panel.remove_connection()
    restored = Config(config.config_file)
    assert not restored.config[prefix+'_enabled']
    assert not restored.config[prefix+'_verified']
    if prefix == 'telegram':
        assert restored.get_telegram_bot_token() == ''
        assert restored.get_telegram_chat_id() == ''
        assert restored.get_yandex_token() == 'synthetic-ya'
        assert not restored.is_telegram_send_screenshot()
    else:
        assert restored.get_yandex_token() == ''
        assert restored.get_yandex_scenario_id() == ''
        assert restored.get_telegram_bot_token() == 'synthetic-tg'
    assert not panel.enabled.isChecked()
    assert not panel.test_button.isEnabled()
    panel.deleteLater()


def test_yandex_test_requires_confirmation_and_cancel_has_no_request(app, config):
    config.config.update(yandex_token='synthetic',yandex_scenario_id='scenario',yandex_scenario_name='Test')
    panel = YandexPanel(config)
    assert panel.test_button.isEnabled()
    with patch('ui.connection_widgets.QMessageBox.question', return_value=QMessageBox.No) as question, \
         patch.object(panel, 'run_job') as run:
        panel.test()
    question.assert_called_once()
    run.assert_not_called()
    assert not config.is_yandex_verified()
    panel.deleteLater()


def test_cancelled_yandex_job_does_not_commit_late_account(app, config):
    config.config.update(yandex_token='synthetic-old',yandex_scenario_id='old',yandex_scenario_name='Old')
    panel = YandexPanel(config)
    gate = threading.Event()
    def response():
        gate.wait(2)
        return 'synthetic-new', [('new','New')]
    panel.run_job(response, panel.loaded)
    panel.cancel()
    gate.set()
    for job in list(panel.jobs):
        assert job.wait(3000)
    app.processEvents()
    assert config.get_yandex_token() == 'synthetic-old'
    assert config.get_yandex_scenario_id() == 'old'
    assert panel.connected_token == 'synthetic-old'
    panel.deleteLater()


def test_volume_changes_debounce_one_save_and_release_flush(window, config):
    panel = window.sound_settings
    with patch.object(config, 'save_config', wraps=config.save_config) as save:
        for value in [25, 26, 27]:
            panel.rows['start']['slider'].setValue(value)
        assert save.call_count == 0
        assert panel.rows['start']['value'].text() == '27%'
        assert config.get_notification_volume_for_event('start') == 100
        QTest.qWait(450)
        assert save.call_count == 1
        assert config.get_notification_volume_for_event('start') == 27
        panel.rows['start']['slider'].setValue(31)
        panel.rows['start']['slider'].sliderReleased.emit()
        assert save.call_count == 2
        assert config.get_notification_volume_for_event('start') == 31


def test_failed_volume_save_restores_slider_label_and_config(window, config):
    panel = window.sound_settings
    with patch('core.config.os.replace', side_effect=PermissionError('test')):
        panel.rows['start']['slider'].setValue(20)
        assert not panel.flush_volumes()
    assert panel.rows['start']['slider'].value() == 100
    assert panel.rows['start']['value'].text() == '100%'
    assert config.get_notification_volume_for_event('start') == 100


def test_preview_at_zero_explains_silence_without_playing(window):
    panel = window.sound_settings
    panel.rows['start']['slider'].setValue(0)
    with patch.object(window.sound_manager, 'test_sound') as playback:
        panel.preview('start')
    playback.assert_not_called()
    assert '0%' in panel.status.text()


def test_missing_saved_audio_is_explained(app, config, tmp_path):
    config.config['notification_sounds']['start'] = 'missing-custom-sound'
    manager = SoundManager(config, sounds_dir=tmp_path/'library')
    panel = SoundSettings(config, manager)
    assert 'не найден' in panel.status.text()
    assert 'стандартн' in panel.status.text()
    assert panel.rows['start']['combo'].currentData() == 'program_activated'
    manager.shutdown()
    panel.deleteLater()
    manager.deleteLater()


def test_second_instance_lock_fails_until_first_releases(tmp_path):
    path = tmp_path / 'test-instance.lock'
    first = acquire_instance(path)
    assert first is not None
    try:
        assert acquire_instance(path) is None
    finally:
        first.unlock()
    replacement = acquire_instance(path)
    assert replacement is not None
    replacement.unlock()


def test_delivery_results_visible_separately_from_search(window):
    window.set_search_state('Enter отправлен','Принятие не подтверждено')
    window.record_delivery('Telegram',False,'Сеть недоступна')
    assert window.status_label.text() == 'Enter отправлен'
    assert 'Сеть недоступна' in window.delivery_label.text()
    assert 'Сеть недоступна' in window.telegram_panel.delivery_status.text()


def test_running_state_freezes_settings_and_mode(window):
    window.set_running_ui(True)
    assert not window.settings_tab.isEnabled()
    assert not window.mode_group.isEnabled()
    assert not window.start_btn.isEnabled()
    assert window.stop_btn.isEnabled()
    window.set_running_ui(False)
    assert window.settings_tab.isEnabled()
    assert window.mode_group.isEnabled()

@pytest.mark.parametrize('kind,prefix', [(TelegramPanel,'telegram'), (YandexPanel,'yandex')])
def test_declined_connection_removal_preserves_synthetic_data(app, config, kind, prefix):
    config.config.update(telegram_bot_token='synthetic-tg',telegram_chat_id='123',
                         yandex_token='synthetic-ya',yandex_scenario_id='scenario')
    assert config.save_config()
    before = config.config_file.read_bytes()
    panel = kind(config)
    with patch('ui.connection_widgets.QMessageBox.question', return_value=QMessageBox.No):
        panel.remove_connection()
    assert config.config_file.read_bytes() == before
    assert config.get_telegram_bot_token() == 'synthetic-tg'
    assert config.get_yandex_token() == 'synthetic-ya'
    panel.deleteLater()


def test_invalid_templates_block_start_before_worker_creation(window, config, tmp_path):
    config.set_template_path(str(tmp_path / 'missing-templates'))
    with patch('ui.main_window_optimized.WorkerThread') as worker:
        window.start_accepter()
    worker.assert_not_called()
    assert window.worker_thread is None
    assert 'шаблон' in window.status_label.text().lower()
    assert window.start_btn.isEnabled()


def test_failed_connection_delete_retains_token_and_ui(app, config):
    config.config.update(telegram_bot_token='synthetic-tg',telegram_chat_id='123',telegram_enabled=True,telegram_verified=True)
    assert config.save_config()
    before = config.config_file.read_bytes()
    panel = TelegramPanel(config)
    with patch('ui.connection_widgets.QMessageBox.question', return_value=QMessageBox.Yes), \
         patch('core.config.os.replace', side_effect=PermissionError('test')):
        panel.remove_connection()
    assert config.config_file.read_bytes() == before
    assert config.get_telegram_bot_token() == 'synthetic-tg'
    assert config.get_telegram_chat_id() == '123'
    assert panel.token.text() == 'synthetic-tg'
    assert panel.enabled.isChecked()
    assert 'сохранить' in panel.status.text()
    panel.deleteLater()


def test_failed_yandex_refresh_save_preserves_selection_and_restores_controls(app, config):
    config.config.update(yandex_token='synthetic-old',yandex_scenario_id='old',yandex_scenario_name='Old',yandex_verified=True)
    assert config.save_config()
    panel = YandexPanel(config)
    panel.set_busy(True)
    with patch('core.config.os.replace', side_effect=PermissionError('test')):
        panel.loaded(('synthetic-old',[('old','Old'),('new','New')]),None)
    assert panel.connected_token == 'synthetic-old'
    assert panel.scenarios.currentData() == 'old'
    assert panel.token.isEnabled()
    assert panel.load_button.isEnabled()
    assert panel.scenarios.isEnabled()
    assert panel.test_button.isEnabled()
    assert not panel.cancel_button.isEnabled()
    assert 'сохранить' in panel.status.text()
    panel.deleteLater()


def test_yandex_cancel_waits_for_inflight_request_before_enabling_retry(app, config):
    config.config.update(yandex_token='synthetic',yandex_scenario_id='scenario',yandex_scenario_name='Test')
    panel = YandexPanel(config)
    gate = threading.Event()
    def response():
        gate.wait(2)
        return 'synthetic',[('scenario','Test')]
    panel.set_busy(True)
    panel.run_job(response,panel.loaded)
    try:
        panel.cancel()
        assert panel.busy()
        assert not panel.load_button.isEnabled()
        assert not panel.test_button.isEnabled()
    finally:
        gate.set()
        for job in list(panel.jobs):
            assert job.wait(3000)
        app.processEvents()
    assert panel.load_button.isEnabled()
    assert panel.test_button.isEnabled()
    panel.deleteLater()


def test_telegram_old_test_result_does_not_hide_unsaved_token_warning(app, config):
    config.config.update(telegram_bot_token='synthetic-old',telegram_chat_id='123')
    panel = TelegramPanel(config)
    gate = threading.Event()
    def response(*args,**kwargs):
        gate.wait(2)
        return {'message_id':1}
    with patch('ui.connection_widgets.TelegramPairing.request',side_effect=response):
        panel.send_test()
        panel.token.setText('synthetic-new')
        gate.set()
        for job in list(panel.jobs):
            assert job.wait(3000)
        app.processEvents()
    assert config.get_telegram_bot_token() == 'synthetic-old'
    assert panel.token.text() == 'synthetic-new'
    assert not panel.test_button.isEnabled()
    assert 'не сохран' in panel.status.text().lower() or 'не примен' in panel.status.text().lower()
    panel.deleteLater()


@pytest.mark.parametrize('kind,prefix', [(TelegramPanel,'telegram'), (YandexPanel,'yandex')])
def test_enabled_connection_can_be_switched_off_after_token_edit(app, config, kind, prefix):
    config.config.update(telegram_bot_token='synthetic-tg-old',telegram_chat_id='123',telegram_enabled=True,
                         telegram_verified=True,yandex_token='synthetic-ya-old',yandex_scenario_id='scenario',
                         yandex_scenario_name='Test',yandex_enabled=True,yandex_verified=True)
    assert config.save_config()
    panel = kind(config)
    panel.edit_connection()
    panel.token.setText('synthetic-new-unapplied')
    assert panel.enabled.isChecked()
    assert panel.enabled.isEnabled(), 'An active saved connection must remain possible to turn off'
    assert not panel.test_button.isEnabled(), 'Do not silently test the saved token after edits'
    panel.enabled.click()
    assert not panel.enabled.isChecked()
    assert not config.config[prefix+'_enabled']
    restored = Config(config.config_file)
    assert not restored.config[prefix+'_enabled']
    expected = 'synthetic-tg-old' if prefix == 'telegram' else 'synthetic-ya-old'
    token_field = 'telegram_bot_token' if prefix == 'telegram' else 'yandex_token'
    assert restored.config[token_field] == expected
    assert panel.token.text() == 'synthetic-new-unapplied'
    assert not panel.enabled.isEnabled(), 'Unsaved token must not allow re-enabling until setup completes'
    panel.deleteLater()


def test_start_uses_isolated_in_memory_configuration_snapshot(window, config):
    config.config.update(telegram_bot_token='synthetic-tg',telegram_chat_id='123',telegram_enabled=True,
                         yandex_token='synthetic-ya',yandex_scenario_id='scenario',yandex_enabled=True,
                         click_pause=3.5,pre_accept_delay=1.7)
    config.config['notification_volumes']['start'] = 42
    config.config['notification_sounds']['start'] = 'program_activated'
    before = config.config_file.read_bytes()
    with patch('ui.main_window_optimized.WorkerThread.start') as start, \
         patch.object(window.sound_manager, 'play_sound'):
        window.start_accepter()
    start.assert_called_once()
    assert not window.worker_thread.isRunning()
    session = window.accepter.config
    assert session is not config
    assert session.config is not config.config
    assert session.config['notification_volumes'] is not config.config['notification_volumes']
    assert session.config['notification_sounds'] is not config.config['notification_sounds']
    config.config.update(telegram_bot_token='later-tg',telegram_chat_id='456',telegram_enabled=False,
                         yandex_token='later-ya',yandex_scenario_id='other',yandex_enabled=False,
                         click_pause=9,pre_accept_delay=5)
    config.config['notification_volumes']['start'] = 3
    config.config['notification_sounds']['start'] = 'none'
    assert session.get_telegram_bot_token() == 'synthetic-tg'
    assert session.get_telegram_chat_id() == '123'
    assert session.is_telegram_enabled()
    assert session.get_yandex_token() == 'synthetic-ya'
    assert session.get_yandex_scenario_id() == 'scenario'
    assert session.is_yandex_enabled()
    assert session.get_click_pause() == 3.5
    assert session.get_pre_accept_delay() == 1.7
    assert session.get_notification_volume_for_event('start') == 42
    assert session.get_notification_sounds()['start'] == 'program_activated'
    assert config.config_file.read_bytes() == before, 'Session snapshot must not write a new configuration'
