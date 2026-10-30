"""Asynchronous local notifications and validated portable sound imports."""
from pathlib import Path
import re
import uuid
import wave
import miniaudio
from PyQt5.QtCore import QObject, QThread, QUrl, Qt, pyqtSignal, pyqtSlot
from PyQt5.QtMultimedia import QSoundEffect
from core.app_paths import resource_root, user_data_root

DEFAULT_SOUNDS = {'start': 'program_activated', 'stop': 'target_deactivated', 'detection': 'target_detected'}
MAX_SECONDS = 30
MAX_BYTES = 10 * 1024 * 1024


class SoundImportError(ValueError):
    pass


def validate_source(path):
    path = Path(path)
    if not path.is_file() or path.suffix.lower() not in ('.wav', '.mp3'):
        raise SoundImportError('Выберите файл WAV или MP3.')
    if not 0 < path.stat().st_size <= MAX_BYTES:
        raise SoundImportError('Файл должен быть непустым и не больше 10 МБ.')
    if path.suffix.lower() == '.wav':
        try:
            with wave.open(str(path), 'rb') as sound:
                duration = sound.getnframes() / sound.getframerate()
                expected = sound.getnframes() * sound.getnchannels() * sound.getsampwidth()
                if not 0 < duration <= MAX_SECONDS:
                    raise SoundImportError('Нужен короткий звук: не более 30 секунд.')
                if len(sound.readframes(sound.getnframes())) != expected:
                    raise SoundImportError('WAV-файл повреждён или обрезан.')
        except (wave.Error, EOFError, ZeroDivisionError):
            raise SoundImportError('Не удалось прочитать WAV. Используйте обычный PCM WAV или MP3.') from None
    return path


def prepare_import(source, directory):
    """Decode imports to PCM WAV independently of Windows multimedia codecs."""
    source = validate_source(source)
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    stem = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', source.stem).strip(' .')[:70] or 'sound'
    destination = directory / ('user_' + uuid.uuid4().hex + '__' + stem + '.wav')
    try:
        try:
            info = miniaudio.get_file_info(str(source.resolve()))
            if not 0 < info.duration <= MAX_SECONDS:
                raise SoundImportError('Нужен короткий звук: не более 30 секунд.')
            decoder = miniaudio.stream_file(str(source.resolve()),
                        output_format=miniaudio.SampleFormat.SIGNED16,
                        nchannels=2, sample_rate=44100, frames_to_read=4096)
            frames = 0
            try:
                with wave.open(str(destination), 'wb') as output:
                    output.setparams((2, 2, 44100, 0, 'NONE', 'not compressed'))
                    for samples in decoder:
                        frames += len(samples) // 2
                        if frames > 44100 * MAX_SECONDS:
                            raise SoundImportError('Нужен короткий звук: не более 30 секунд.')
                        output.writeframesraw(samples.tobytes())
            finally:
                decoder.close()
            if frames == 0:
                raise SoundImportError('В файле не найдено аудио.')
        except miniaudio.DecodeError:
            raise SoundImportError('Не удалось прочитать звук. Файл повреждён или содержит неподдерживаемое аудио.') from None
        validate_source(destination)
        return destination
    except Exception:
        destination.unlink(missing_ok=True)
        raise


class ImportWorker(QThread):
    result = pyqtSignal(str, str, str)

    def __init__(self, source, directory, event_type, parent):
        super().__init__(parent)
        self.source, self.directory, self.event_type = source, directory, event_type

    def run(self):
        try:
            destination = prepare_import(self.source, self.directory)
            self.result.emit(self.event_type, destination.stem, '')
        except SoundImportError as error:
            self.result.emit(self.event_type, '', str(error))
        except Exception:
            self.result.emit(self.event_type, '', 'Не удалось добавить звук. Проверьте файл и доступ к папке программы.')


class SoundManager(QObject):
    error = pyqtSignal(str)
    import_finished = pyqtSignal(str, str, str)
    library_changed = pyqtSignal()
    _play_requested = pyqtSignal(str, str)

    def __init__(self, config, parent=None, *, sounds_dir=None, player_factory=None):
        super().__init__(parent)
        self.config = config
        self.user_sounds_dir = Path(sounds_dir) if sounds_dir else user_data_root() / 'user_sounds'
        self.custom_sounds = {}
        self._factory = player_factory or QSoundEffect
        self._player = None
        self._pending_play = False
        self._import_worker = None
        self._play_requested.connect(self._play, Qt.QueuedConnection)
        self.refresh_library()

    def refresh_library(self):
        sounds = {}
        for folder in (resource_root() / 'resources' / 'sounds', self.user_sounds_dir):
            if folder.is_dir():
                for path in sorted(folder.iterdir()):
                    if path.is_file() and path.suffix.lower() == '.wav':
                        sounds[path.stem] = str(path)
        self.custom_sounds = sounds
        self.library_changed.emit()

    def get_available_sounds(self):
        return dict(self.custom_sounds)

    def selected_sound(self, event_type):
        saved = self.config.get_notification_sounds().get(event_type)
        if saved == 'none':
            return 'none'
        return saved if saved in self.custom_sounds else DEFAULT_SOUNDS.get(event_type, 'none')

    def play_sound(self, event_type):
        if self.config.are_notifications_enabled():
            self._play_requested.emit(self.selected_sound(event_type), event_type)

    def test_sound(self, sound_name, event_type='detection'):
        if sound_name == 'none':
            return True
        if sound_name not in self.custom_sounds:
            self.error.emit('Звуковой файл не найден. Выберите другой звук.')
            return False
        self._play_requested.emit(sound_name, event_type)
        return True

    @pyqtSlot(str, str)
    def _play(self, sound_name, event_type):
        if sound_name == 'none':
            return
        path = self.custom_sounds.get(sound_name)
        if not path or not Path(path).is_file():
            self.error.emit('Звуковой файл не найден. Добавьте его заново в настройках звуков.')
            return
        volume = max(0, min(100, int(self.config.get_notification_volume_for_event(event_type))))
        self._pending_play = False
        if self._player is not None:
            self._player.stop()
        if volume == 0:
            return
        if self._player is None:
            self._player = self._factory(self)
            self._player.statusChanged.connect(self._playback_status)
        self._player.setVolume(volume / 100.0)
        self._player.setSource(QUrl.fromLocalFile(path))
        self._pending_play = True
        self._playback_status()

    def _playback_status(self):
        if self._player.status() == QSoundEffect.Error:
            self._pending_play = False
            self.error.emit('Не удалось воспроизвести звук. Проверьте аудиоустройство и выберите другой WAV.')
        elif self._pending_play and self._player.status() == QSoundEffect.Ready:
            self._pending_play = False
            self._player.play()

    def import_sound(self, source, event_type):
        if self.busy():
            self.import_finished.emit(event_type, '', 'Дождитесь завершения предыдущего импорта.')
            return
        worker = ImportWorker(source, self.user_sounds_dir, event_type, self)
        self._import_worker = worker
        worker.result.connect(self._import_result)
        worker.finished.connect(worker.deleteLater)
        worker.finished.connect(lambda: self._clear_worker(worker))
        worker.start()

    def _clear_worker(self, worker):
        if self._import_worker is worker:
            self._import_worker = None

    def _import_result(self, event_type, key, error):
        if key and not error:
            self.refresh_library()
        self.import_finished.emit(event_type, key, error)

    def busy(self):
        return self._import_worker is not None and self._import_worker.isRunning()

    def shutdown(self):
        # MainWindow must defer closing while busy(); no GUI-blocking wait here.
        self._pending_play = False
        if self._player:
            self._player.stop()

    def get_sound_display_name(self, sound_name):
        names = {'none': 'Без звука', 'program_activated': 'Программа активирована',
                 'target_deactivated': 'Программа деактивирована', 'target_detected': 'Кнопка принятия обнаружена'}
        return names.get(sound_name, sound_name.split('__', 1)[-1] if sound_name.startswith('user_') else sound_name)
