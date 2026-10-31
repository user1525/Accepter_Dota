"""Three independent notification sounds with portable imports and previews."""
import copy
from PyQt5.QtCore import Qt, pyqtSignal, QTimer
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel,
    QCheckBox, QComboBox, QPushButton, QSlider, QFileDialog)


class SoundSettings(QWidget):
    changed = pyqtSignal()

    def __init__(self, config, sound_manager, parent=None):
        super().__init__(parent)
        self.config = config
        self.sound_manager = sound_manager
        self.rows = {}
        self.pending_volumes = {}
        self.volume_timer = QTimer(self)
        self.volume_timer.setSingleShot(True)
        self.volume_timer.setInterval(350)
        self.volume_timer.timeout.connect(self.flush_volumes)
        layout = QVBoxLayout(self)
        self.enabled = QCheckBox('Включить звуковые оповещения')
        self.enabled.setChecked(config.are_notifications_enabled())
        self.enabled.toggled.connect(self.toggle_enabled)
        layout.addWidget(self.enabled)
        hint = QLabel('Каждое событие имеет свой звук и громкость. «Прослушать» работает даже при выключенных оповещениях. Добавляйте MP3 или WAV до 30 секунд и 10 МБ.')
        hint.setWordWrap(True)
        layout.addWidget(hint)
        for event, title in (('start', 'Активация ожидания'), ('stop', 'Ручная деактивация'), ('detection', 'Кнопка принятия обнаружена')):
            box = QGroupBox(title)
            body = QVBoxLayout(box)
            choice = QHBoxLayout()
            combo = QComboBox()
            combo.setMinimumContentsLength(15)
            combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
            body.addWidget(combo)
            preview = QPushButton('Прослушать')
            preview.clicked.connect(lambda checked=False, e=event: self.preview(e))
            choice.addWidget(preview, 1)
            add = QPushButton('Добавить звук…')
            add.clicked.connect(lambda checked=False, e=event: self.choose_file(e))
            choice.addWidget(add, 1)
            body.addLayout(choice)
            volume_row = QHBoxLayout()
            volume_row.addWidget(QLabel('Громкость'))
            slider = QSlider(Qt.Horizontal)
            slider.setRange(0, 100)
            slider.setValue(max(0, min(100, config.get_notification_volume_for_event(event))))
            slider.setAccessibleName('Громкость: ' + title)
            value = QLabel(str(slider.value()) + '%')
            value.setMinimumWidth(36)
            volume_row.addWidget(slider, 1)
            volume_row.addWidget(value)
            body.addLayout(volume_row)
            layout.addWidget(box)
            self.rows[event] = {'combo': combo, 'slider': slider, 'value': value, 'add': add}
            combo.currentIndexChanged.connect(lambda index, e=event: self.save_selection(e))
            slider.valueChanged.connect(lambda amount, e=event: self.queue_volume(e, amount))
            slider.sliderReleased.connect(self.flush_volumes)
        self.status = QLabel('Изменения сохраняются автоматически.')
        self.status.setWordWrap(True)
        self.status.setTextFormat(Qt.PlainText)
        layout.addWidget(self.status)
        layout.addStretch()
        sound_manager.import_finished.connect(self.imported)
        sound_manager.error.connect(self.status.setText)
        sound_manager.library_changed.connect(self.refresh)
        self.refresh()
        missing = [event for event, key in self.config.get_notification_sounds().items() if key != 'none' and key not in self.sound_manager.get_available_sounds()]
        if missing:
            self.status.setText('Сохранённый файл не найден. Используется стандартная запись. Добавьте свой звук заново.')

    def queue_volume(self, event, amount):
        self.pending_volumes[event] = amount
        self.rows[event]['value'].setText(str(amount) + '%')
        self.volume_timer.start()

    def flush_volumes(self):
        self.volume_timer.stop()
        if not self.pending_volumes:
            return True
        volumes = dict(self.config.config.get('notification_volumes', {}))
        volumes.update(self.pending_volumes)
        self.pending_volumes.clear()
        success = self.save({'notification_volumes': volumes})
        if not success:
            for event, row in self.rows.items():
                amount = self.config.get_notification_volume_for_event(event)
                row['slider'].blockSignals(True); row['slider'].setValue(amount); row['slider'].blockSignals(False)
                row['value'].setText(str(amount) + '%')
        return success

    def save(self, values):
        old = copy.deepcopy(self.config.config)
        self.config.config.update(values)
        if not self.config.save_config():
            self.config.config = old
            self.status.setText('Не удалось сохранить настройки. Проверьте доступ к папке программы.')
            return False
        self.status.setText('Настройки звука сохранены.')
        self.changed.emit()
        return True

    def toggle_enabled(self, checked):
        if not self.save({'notifications_enabled': checked}):
            self.enabled.blockSignals(True)
            self.enabled.setChecked(self.config.are_notifications_enabled())
            self.enabled.blockSignals(False)

    def refresh(self):
        available = self.sound_manager.get_available_sounds()
        for event, row in self.rows.items():
            combo = row['combo']
            combo.blockSignals(True)
            combo.clear()
            combo.addItem('Без звука', 'none')
            for key in available:
                combo.addItem(self.sound_manager.get_sound_display_name(key), key)
            combo.setCurrentIndex(max(0, combo.findData(self.sound_manager.selected_sound(event))))
            combo.blockSignals(False)

    def save_selection(self, event):
        selected = self.rows[event]['combo'].currentData()
        if selected is None:
            return
        sounds = self.config.get_notification_sounds()
        sounds[event] = selected
        if not self.save({'notification_sounds': sounds}):
            self.refresh()
        missing = [event for event, key in self.config.get_notification_sounds().items() if key != 'none' and key not in self.sound_manager.get_available_sounds()]
        if missing:
            self.status.setText('Сохранённый файл не найден. Используется стандартная запись. Добавьте свой звук заново.')



    def save_volume(self, event, amount):
        volumes = dict(self.config.config.get('notification_volumes', {}))
        volumes[event] = amount
        row = self.rows[event]
        if self.save({'notification_volumes': volumes}):
            row['value'].setText(str(amount) + '%')
        else:
            row['slider'].blockSignals(True)
            row['slider'].setValue(self.config.get_notification_volume_for_event(event))
            row['slider'].blockSignals(False)

    def preview(self, event):
        if not self.flush_volumes():
            return
        key = self.rows[event]['combo'].currentData()
        if self.config.get_notification_volume_for_event(event) == 0:
            self.status.setText('Громкость 0% — звук выключен для этого события.')
            return
        if key == 'none':
            self.status.setText('Для этого события выбран режим «Без звука».')
        elif self.sound_manager.test_sound(key, event):
            self.status.setText('Воспроизведение: ' + self.sound_manager.get_sound_display_name(key))

    def choose_file(self, event):
        path, _ = QFileDialog.getOpenFileName(self, 'Добавить короткое оповещение', '', 'Звуки (*.wav *.mp3);;Все файлы (*)')
        if not path:
            return
        for row in self.rows.values():
            row['add'].setEnabled(False)
        self.status.setText('Проверяем звук и сохраняем копию рядом с программой…')
        self.sound_manager.import_sound(path, event)

    def imported(self, event, key, error):
        for row in self.rows.values():
            row['add'].setEnabled(True)
        if error:
            self.status.setText(error)
            return
        sounds = self.config.get_notification_sounds()
        sounds[event] = key
        if self.save({'notification_sounds': sounds}):
            self.refresh()
            self.status.setText('Звук добавлен и выбран. Исходный файл можно переместить: программа хранит свою копию.')
