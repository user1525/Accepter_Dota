"""Explicit capture/save dialog; modifiers alone never finish capture."""
from PyQt5.QtCore import Qt, QEvent
from PyQt5.QtWidgets import QDialog, QVBoxLayout, QLabel, QLineEdit, QDialogButtonBox
from core.hotkeys import normalize_hotkey, display_hotkey


_SPECIAL_KEYS = {
    Qt.Key_Insert: 'insert', Qt.Key_Delete: 'delete', Qt.Key_Return: 'enter',
    Qt.Key_Enter: 'enter', Qt.Key_Space: 'space', Qt.Key_Tab: 'tab',
    Qt.Key_Backspace: 'backspace', Qt.Key_Home: 'home', Qt.Key_End: 'end',
    Qt.Key_PageUp: 'page up', Qt.Key_PageDown: 'page down', Qt.Key_Left: 'left',
    Qt.Key_Right: 'right', Qt.Key_Up: 'up', Qt.Key_Down: 'down', Qt.Key_Pause: 'pause',
}


def key_event_hotkey(event):
    """Map Windows physical letter keys consistently across RU/EN layouts."""
    if event.isAutoRepeat() or event.key() in (Qt.Key_Control, Qt.Key_Alt, Qt.Key_Shift, Qt.Key_Meta, Qt.Key_AltGr):
        return None
    modifiers = event.modifiers()
    if modifiers & (Qt.MetaModifier | Qt.GroupSwitchModifier):
        raise ValueError('Используйте Ctrl, Alt или Shift; сочетания с Win и AltGr не поддерживаются.')
    if modifiers & Qt.KeypadModifier:
        raise ValueError('Используйте основную клавиатуру: NumPad отдельно пока не поддерживается.')
    key = _SPECIAL_KEYS.get(event.key())
    if key is None and Qt.Key_F1 <= event.key() <= Qt.Key_F24:
        key = 'f' + str(event.key() - Qt.Key_F1 + 1)
    if key is None:
        vk = event.nativeVirtualKey()
        if 0x30 <= vk <= 0x39 or 0x41 <= vk <= 0x5A:
            key = chr(vk).lower()
        elif Qt.Key_A <= event.key() <= Qt.Key_Z or Qt.Key_0 <= event.key() <= Qt.Key_9:
            key = chr(event.key()).lower()
    if key is None:
        raise ValueError('Выберите букву, цифру, F1–F24 или служебную клавишу, например Insert.')
    parts = []
    for flag, name in ((Qt.ControlModifier, 'ctrl'), (Qt.AltModifier, 'alt'), (Qt.ShiftModifier, 'shift')):
        if modifiers & flag:
            parts.append(name)
    return normalize_hotkey('+'.join(parts + [key]))


class HotkeyDialog(QDialog):
    def __init__(self, current_key, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Клавиша запуска и остановки')
        self.setMinimumWidth(400)
        try:
            self.selected_key = normalize_hotkey(current_key)
        except ValueError:
            self.selected_key = None
        layout = QVBoxLayout(self)
        hint = QLabel('Нажмите клавишу или сочетание, например Ctrl+Alt+F8.\nЗатем нажмите «Сохранить». Esc — отмена.')
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.capture = QLineEdit()
        self.capture.setReadOnly(True)
        self.capture.setAccessibleName('Новое сочетание клавиш')
        self.capture.setText(display_hotkey(self.selected_key) if self.selected_key else '')
        self.capture.setPlaceholderText('Нажмите сочетание…')
        self.capture.installEventFilter(self)
        layout.addWidget(self.capture)
        self.status = QLabel('Нажатия в этом поле используются для выбора сочетания.')
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        self.save_button = buttons.button(QDialogButtonBox.Save)
        self.save_button.setText('Сохранить')
        self.save_button.setAutoDefault(False)
        self.save_button.setEnabled(self.selected_key is not None)
        buttons.button(QDialogButtonBox.Cancel).setText('Отмена')
        buttons.button(QDialogButtonBox.Cancel).setAutoDefault(False)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.capture.setFocus()

    def eventFilter(self, watched, event):
        if watched is self.capture and event.type() == QEvent.KeyPress:
            if event.key() == Qt.Key_Escape:
                self.reject()
                return True
            try:
                key = key_event_hotkey(event)
            except ValueError as error:
                self.status.setText(str(error))
                self.save_button.setEnabled(False)
                self.selected_key = None
                return True
            if key is not None:
                self.selected_key = key
                self.capture.setText(display_hotkey(key))
                self.status.setText('Сочетание выбрано. Нажмите «Сохранить».')
                self.save_button.setEnabled(True)
            return True
        return super().eventFilter(watched, event)

    def accept(self):
        if self.selected_key is not None:
            super().accept()
