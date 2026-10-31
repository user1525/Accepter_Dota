import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import copy
import tempfile
import threading
import unittest
import wave
from pathlib import Path
from PyQt5.QtCore import QObject, pyqtSignal, QThread
from PyQt5.QtWidgets import QApplication
from PyQt5.QtMultimedia import QSoundEffect
from unittest.mock import patch, Mock
import array
import miniaudio
from core.sound_manager import SoundManager, SoundImportError, validate_source, prepare_import
from ui.sound_settings import SoundSettings


class ConfigStub:
    def __init__(self):
        self.config = {'notifications_enabled': True,
                       'notification_sounds': {'start': 'program_activated', 'stop': 'target_deactivated', 'detection': 'target_detected'},
                       'notification_volumes': {'start': 15, 'stop': 40, 'detection': 85}}
    def are_notifications_enabled(self): return self.config['notifications_enabled']
    def get_notification_sounds(self): return copy.deepcopy(self.config['notification_sounds'])
    def get_notification_volume_for_event(self, event): return self.config['notification_volumes'].get(event, 100)
    def save_config(self): return True


class FakePlayer(QObject):
    statusChanged = pyqtSignal()
    def __init__(self, parent=None):
        super().__init__(parent)
        self.play_count = 0
        self.current_volume = 0
        self.thread_played = None
    def setVolume(self, volume): self.current_volume = volume
    def setSource(self, source): self.source = source
    def stop(self): pass
    def play(self):
        self.play_count += 1
        self.thread_played = QThread.currentThread()
    def status(self): return QSoundEffect.Ready


class AudioTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.app = QApplication.instance() or QApplication([])
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.config = ConfigStub()
        self.manager = SoundManager(self.config, sounds_dir=Path(self.temp.name)/'library', player_factory=FakePlayer)
        self.events = []
        self.manager.import_finished.connect(lambda *args: self.events.append(args))
    def tearDown(self):
        if self.manager._import_worker:
            self.manager._import_worker.wait(5000)
            self.app.processEvents()
        self.manager.shutdown()
        self.manager.deleteLater()
        self.app.processEvents()
        self.temp.cleanup()
    def wav(self, name='test.wav', seconds=1):
        path = Path(self.temp.name)/name
        with wave.open(str(path), 'wb') as sound:
            sound.setparams((1, 2, 8000, 0, 'NONE', 'not compressed'))
            sound.writeframes(b'\0\0' * int(8000 * seconds))
        return path
    def test_independent_event_volumes(self):
        for event, expected in [('start', 15), ('stop', 40), ('detection', 85)]:
            self.manager.play_sound(event)
            self.app.processEvents()
            self.assertEqual(self.manager._player.current_volume, expected / 100.0)
    def test_worker_requests_are_played_on_gui_thread(self):
        worker = threading.Thread(target=lambda: self.manager.play_sound('detection'))
        worker.start(); worker.join()
        self.assertIsNone(self.manager._player)
        self.app.processEvents()
        self.assertIs(self.manager._player.thread_played, self.app.thread())
    def test_zero_volume_does_not_play(self):
        self.config.config['notification_volumes']['start'] = 0
        self.manager.play_sound('start'); self.app.processEvents()
        self.assertIsNone(self.manager._player)
    def test_disabled_notifications_but_explicit_preview_works(self):
        self.config.config['notifications_enabled'] = False
        self.manager.play_sound('start'); self.app.processEvents()
        self.assertIsNone(self.manager._player)
        self.manager.test_sound('program_activated', 'start'); self.app.processEvents()
        self.assertEqual(self.manager._player.current_volume, 0.15)
    def test_import_copies_and_preserves_original_with_unique_names(self):
        source = self.wav('свой звук.WAV')
        self.manager.import_sound(source, 'start')
        self.manager._import_worker.wait(5000); self.app.processEvents()
        self.manager.import_sound(source, 'stop')
        self.manager._import_worker.wait(5000); self.app.processEvents()
        self.assertEqual(len(self.events), 2)
        self.assertNotEqual(self.events[0][1], self.events[1][1])
        self.assertTrue(source.exists())
        source.unlink()
        for _, key, error in self.events:
            self.assertFalse(error)
            self.assertTrue(Path(self.manager.custom_sounds[key]).exists())
    def test_rejects_long_and_corrupt_wav(self):
        with self.assertRaises(SoundImportError): validate_source(self.wav(seconds=31))
        path = self.wav()
        path.write_bytes(path.read_bytes()[:-10])
        with self.assertRaises(SoundImportError): validate_source(path)
    def test_decode_rejects_metadata_over_30_seconds(self):
        source = Path(self.temp.name)/'sound.mp3'; source.write_bytes(b'fake')
        with patch('core.sound_manager.miniaudio.get_file_info', return_value=Mock(duration=31)):
            with self.assertRaises(SoundImportError): prepare_import(source, self.manager.user_sounds_dir)
        self.assertEqual(list(self.manager.user_sounds_dir.iterdir()), [])
    def test_actual_decoded_duration_is_bounded_even_if_metadata_is_wrong(self):
        source = Path(self.temp.name)/'sound.mp3'; source.write_bytes(b'fake')
        def stream(*args, **kwargs):
            for _ in range(31): yield array.array('h', [0] * 88200)
        with patch('core.sound_manager.miniaudio.get_file_info', return_value=Mock(duration=1)), \
             patch('core.sound_manager.miniaudio.stream_file', side_effect=stream):
            with self.assertRaises(SoundImportError): prepare_import(source, self.manager.user_sounds_dir)
        self.assertEqual(list(self.manager.user_sounds_dir.iterdir()), [])
    def test_corrupt_mp3_not_added(self):
        source = Path(self.temp.name)/'sound.mp3'; source.write_bytes(b'not mp3')
        with self.assertRaises(SoundImportError): prepare_import(source, self.manager.user_sounds_dir)
        self.assertEqual(list(self.manager.user_sounds_dir.iterdir()), [])
    def test_each_row_changes_its_own_setting(self):
        panel = SoundSettings(self.config, self.manager)
        row = panel.rows['start']
        row['combo'].setCurrentIndex(row['combo'].findData('target_detected'))
        row['slider'].setValue(22)
        panel.flush_volumes()  # Persistence happens on release/debounce, not every tick.
        self.assertEqual(self.config.get_notification_sounds()['start'], 'target_detected')
        self.assertEqual(self.config.get_notification_sounds()['stop'], 'target_deactivated')
        self.assertEqual(self.config.get_notification_volume_for_event('start'), 22)
        self.assertEqual(self.config.get_notification_volume_for_event('stop'), 40)
        panel.deleteLater()
    def test_obsolete_selection_uses_new_default(self):
        self.config.config['notification_sounds']['start'] = 'warning_notification'
        self.assertEqual(self.manager.selected_sound('start'), 'program_activated')
