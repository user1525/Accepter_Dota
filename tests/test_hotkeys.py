import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import unittest
from unittest.mock import Mock
from PyQt5.QtCore import Qt, QEvent
from PyQt5.QtGui import QKeyEvent
from PyQt5.QtWidgets import QApplication, QDialog
from core.hotkeys import normalize_hotkey, display_hotkey, HotkeyBinding
from ui.hotkey_dialog import HotkeyDialog, key_event_hotkey


class HotkeyTests(unittest.TestCase):
    def test_normalize(self):
        for raw, expected in [('INS', 'insert'), ('Ctrl+Alt+F8', 'ctrl+alt+f8'),
                              ('Shift+Insert', 'shift+insert'), ('ALT+CTRL+A', 'ctrl+alt+a')]:
            self.assertEqual(normalize_hotkey(raw), expected)
        self.assertEqual(display_hotkey('ctrl+alt+f8'), 'Ctrl+Alt+F8')

    def test_invalid_and_system_chords(self):
        for raw in ('Ctrl', 'Ctrl+Shift', '', 'Win+A', 'Ctrl+A,B', 'Alt+F4', 'Ctrl+Ctrl+A'):
            with self.assertRaises(ValueError):
                normalize_hotkey(raw)

    def test_register_failure_preserves_previous(self):
        backend, callback = Mock(), Mock()
        backend.add_hotkey.side_effect = ['old', ValueError('bad')]
        binding = HotkeyBinding(callback, backend)
        binding.replace('F8')
        with self.assertRaises(ValueError):
            binding.replace('Ctrl+A')
        self.assertEqual(binding.key, 'f8')
        backend.remove_hotkey.assert_not_called()

    def test_save_failure_rolls_back_new_registration(self):
        backend = Mock()
        backend.add_hotkey.side_effect = ['old', 'new']
        binding = HotkeyBinding(Mock(), backend)
        binding.replace('F8')
        with self.assertRaises(RuntimeError):
            binding.replace('F9', lambda key: False)
        backend.remove_hotkey.assert_called_once_with('new')
        self.assertEqual(binding.key, 'f8')

    def test_paused_old_and_closed_callbacks_are_inert(self):
        backend, callback = Mock(), Mock()
        backend.add_hotkey.side_effect = ['old', 'new']
        binding = HotkeyBinding(callback, backend)
        binding.replace('F8')
        old = backend.add_hotkey.call_args.args[1]
        self.assertTrue(backend.add_hotkey.call_args.kwargs['trigger_on_release'])
        binding.paused = True
        old()
        callback.assert_not_called()
        binding.paused = False
        old()
        callback.assert_called_once()
        binding.replace('F9')
        old()
        callback.assert_called_once()
        new = backend.add_hotkey.call_args.args[1]
        new()
        self.assertEqual(callback.call_count, 2)
        binding.close()
        new()
        self.assertEqual(callback.call_count, 2)


class CaptureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def event(self, key, mods=Qt.NoModifier, autorepeat=False):
        return QKeyEvent(QEvent.KeyPress, key, mods, '', autorepeat)

    def test_modifier_only_and_repeat_ignored(self):
        self.assertIsNone(key_event_hotkey(self.event(Qt.Key_Control, Qt.ControlModifier)))
        self.assertIsNone(key_event_hotkey(self.event(Qt.Key_F8, autorepeat=True)))

    def test_combo_requires_explicit_save(self):
        dialog = HotkeyDialog('Insert')
        dialog.eventFilter(dialog.capture, self.event(Qt.Key_Control, Qt.ControlModifier))
        self.assertEqual(dialog.selected_key, 'insert')
        dialog.eventFilter(dialog.capture, self.event(Qt.Key_F8, Qt.ControlModifier | Qt.AltModifier))
        self.assertEqual(dialog.selected_key, 'ctrl+alt+f8')
        self.assertEqual(dialog.result(), QDialog.Rejected)
        dialog.accept()
        self.assertEqual(dialog.result(), QDialog.Accepted)
        dialog.deleteLater()

    def test_escape_cancels(self):
        dialog = HotkeyDialog('F8')
        dialog.eventFilter(dialog.capture, self.event(Qt.Key_Escape))
        self.assertEqual(dialog.result(), QDialog.Rejected)
        dialog.deleteLater()

    def test_russian_layout_uses_windows_virtual_key(self):
        # Cyrillic А is the physical F key on the standard RU layout.
        event = QKeyEvent(QEvent.KeyPress, 0x410, Qt.ControlModifier, 0, 0x46, 0, 'а')
        self.assertEqual(key_event_hotkey(event), 'ctrl+f')

    def test_keypad_is_explicitly_rejected(self):
        with self.assertRaises(ValueError):
            key_event_hotkey(self.event(Qt.Key_1, Qt.KeypadModifier))
