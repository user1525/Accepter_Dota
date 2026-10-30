"""Guided connection panels. All network calls run outside the GUI thread."""
from PyQt5.QtCore import QThread, QTimer, pyqtSignal, QUrl, Qt
from PyQt5.QtGui import QDesktopServices
from PyQt5.QtWidgets import (QGroupBox, QVBoxLayout, QLabel,
    QPushButton, QLineEdit, QCheckBox, QComboBox, QWidget, QMessageBox)
from core.telegram_pairing import TelegramPairing, PairingError
from core.yandex_smart_home import YandexSmartHome, YandexError


class NetworkJob(QThread):
    result = pyqtSignal(object, object)

    def __init__(self, operation, parent):
        super().__init__(parent)
        self.operation = operation

    def run(self):
        try:
            self.result.emit(self.operation(), None)
        except (PairingError, YandexError) as error:
            self.result.emit(None, str(error))
        except Exception:
            self.result.emit(None, 'Не удалось выполнить запрос. Проверьте интернет, токен и доступ к сервису.')


class WrappedLabel(QLabel):
    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.setMinimumHeight(self.heightForWidth(event.size().width()))


class ConnectionPanel(QGroupBox):
    def __init__(self, title, config):
        super().__init__(title)
        self.config = config
        self.jobs = set()
        self.generation = 0
        self.last_operation_error = ''
        self.body = QVBoxLayout(self)
        self.body.setSpacing(12)

    def note(self, text):
        label = WrappedLabel(text)
        label.setWordWrap(True)
        label.setTextFormat(Qt.PlainText)
        self.body.addWidget(label)
        return label

    def button(self, text, action):
        button = QPushButton(text)
        button.clicked.connect(action)
        self.body.addWidget(button)
        return button

    def run_job(self, operation, callback):
        generation = self.generation
        job = NetworkJob(operation, self)
        self.jobs.add(job)
        def deliver(value, error):
            if generation == self.generation:
                self.last_operation_error = error or ''
                callback(value, error)
        job.result.connect(deliver)
        job.finished.connect(lambda: self.jobs.discard(job))
        job.finished.connect(job.deleteLater)
        job.finished.connect(lambda: self.refresh_buttons() if hasattr(self, 'refresh_buttons') else None)
        job.start()

    def busy(self):
        return any(job.isRunning() for job in self.jobs)

    def open_url(self, url):
        if not QDesktopServices.openUrl(QUrl(url)):
            self.status.setText('Не удалось открыть ссылку. Скопируйте её и откройте в браузере: ' + url)

    def save_values(self, **values):
        previous = self.config.config.copy()
        self.config.config.update(values)
        if not self.config.save_config():
            self.config.config = previous
            self.status.setText('Не удалось сохранить настройки. Проверьте доступ к папке программы и повторите.')
            return False
        return True

    def bind_checkbox(self, checkbox, key):
        def changed(checked):
            if not self.save_values(**{key: checked}):
                checkbox.blockSignals(True)
                checkbox.setChecked(bool(self.config.config.get(key)))
                checkbox.blockSignals(False)
            if hasattr(self, "refresh_buttons"):
                self.refresh_buttons()
        checkbox.toggled.connect(changed)


class TelegramPanel(ConnectionPanel):
    def __init__(self, config):
        super().__init__('Подключение личного чата', config)
        self.pairing = None
        self.step1_note = self.note('1. Создайте бота через /newbot в BotFather. Если бот уже есть, вставьте его токен.')
        self.botfather_button = self.button('Открыть BotFather', lambda: self.open_url('https://t.me/BotFather'))
        self.token = QLineEdit(config.get_telegram_bot_token())
        self.token.setEchoMode(QLineEdit.Password)
        self.token.setPlaceholderText('Токен из BotFather')
        self.body.addWidget(self.token)
        self.connect_button = self.button('Проверить бота', self.connect_bot)
        self.connect_button.setProperty('role', 'primary')
        self.step2_note = self.note('2. Откройте личный чат по кнопке ниже и нажмите «Запустить». Оставьте Accepter открытым до привязки.')
        self.open_button = self.button('Открыть бота в Telegram', self.open_bot)
        self.open_button.setEnabled(False)
        self.cancel_button = self.button('Отменить привязку', self.cancel)
        self.cancel_button.setEnabled(False)
        self.recipient = self.note(self.recipient_text())
        self.step3_note = self.note('3. Отправьте пробное сообщение, затем включите оповещения.')
        self.test_button = self.button('Отправить пробное сообщение', self.send_test)
        self.enabled = QCheckBox('Отправлять результат ожидания')
        self.enabled.setChecked(config.is_telegram_enabled())
        self.bind_checkbox(self.enabled, 'telegram_enabled')
        self.body.addWidget(self.enabled)
        screenshot = QCheckBox('Прикладывать снимок всего экрана')
        screenshot.setChecked(config.is_telegram_send_screenshot())
        self.bind_checkbox(screenshot, 'telegram_send_screenshot')
        self.screenshot = screenshot
        self.body.addWidget(screenshot)
        self.screenshot_note = self.note("Снимок может включать другие окна и личные данные. По умолчанию выключен.")
        self.status = self.note('Пробное уведомление ранее отправлено.' if config.is_telegram_verified() else
                                'Чат сохранён. Проверьте отправку.' if config.get_telegram_chat_id() else 'Начните с шага 1.')
        self.status.setProperty('role', 'notice')
        self.body.insertWidget(0, self.status)
        self.timer = QTimer(self)
        self.timer.setInterval(1200)
        self.timer.timeout.connect(self.poll)
        self.token.textChanged.connect(self.token_changed)
        self.edit_button = self.button('Изменить бота', self.edit_connection)
        self.editing = False
        self.remove_button = self.button('Удалить подключение', self.remove_connection)
        self.delivery_status = self.note('Последних доставок в этом сеансе нет.')
        self.refresh_buttons()

    def edit_connection(self):
        self.editing = True
        self.refresh_buttons()
        self.token.setFocus()

    def token_changed(self):
        self.refresh_buttons()
        if self.token.text().strip() != self.config.get_telegram_bot_token():
            self.status.setText('Токен изменён, но не сохранён. Проверьте бота и привяжите чат заново. Старое подключение пока сохранено; если оповещения включены, они продолжат работать до выключения.')
        else:
            self.status.setText('Используется сохранённое подключение.')

    def remove_connection(self):
        if self.busy():
            self.status.setText('Дождитесь завершения текущего запроса.'); return
        if QMessageBox.question(self, 'Удалить подключение?', 'Удалить сохранённые токен и чат на этом компьютере? Бот в Telegram останется.', QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        self.cancel()
        if self.config.clear_connection('telegram'):
            self.token.blockSignals(True); self.token.clear(); self.token.blockSignals(False)
            self.enabled.blockSignals(True); self.enabled.setChecked(False); self.enabled.blockSignals(False)
            self.screenshot.blockSignals(True); self.screenshot.setChecked(False); self.screenshot.blockSignals(False)
            self.recipient.setText(self.recipient_text()); self.last_operation_error = ''
            self.status.setText('Подключение удалено. Для нового бота начните с шага 1.')
            self.delivery_status.setText('Последних доставок для этого подключения нет.')
        else:
            self.status.setText(self.config.last_error)
        self.refresh_buttons()

    def recipient_text(self):
        chat = self.config.get_telegram_chat_id()
        name = self.config.config.get('telegram_chat_name')
        return 'Получатель: ' + (name or ('сохранённый чат ' + chat) if chat else 'ещё не привязан')

    def refresh_buttons(self):
        active = self.pairing is not None
        self.token.setEnabled(not active and not self.busy())
        self.connect_button.setEnabled(not active and not self.busy())
        self.open_button.setEnabled(active and bool(self.pairing.username))
        self.cancel_button.setEnabled(active)
        linked = bool(self.config.get_telegram_bot_token() and self.config.get_telegram_chat_id())
        unchanged = self.token.text().strip() == self.config.get_telegram_bot_token()
        self.test_button.setEnabled(linked and not active and unchanged and not self.busy())
        self.enabled.setEnabled(linked and not active and not self.busy() and (self.enabled.isChecked() or (unchanged and self.config.is_telegram_verified())))
        editing = getattr(self, 'editing', False)
        for control in (self.step1_note, self.botfather_button, self.token, self.connect_button):
            control.setVisible((not linked or editing or active) and not (active and bool(self.pairing.username)))
        for control in (self.step2_note, self.open_button, self.cancel_button):
            control.setVisible(active)
        for control in (self.step3_note, self.test_button, self.enabled, self.screenshot, self.screenshot_note):
            control.setVisible(linked and not active)
        self.recipient.setVisible(linked)
        if hasattr(self, 'edit_button'):
            self.edit_button.setVisible(linked and not active and not editing)
            self.remove_button.setVisible(linked and not active)
            self.remove_button.setEnabled(not self.busy())
            self.edit_button.setEnabled(not self.busy())

    def connect_bot(self):
        if self.busy():
            self.status.setText('Предыдущий запрос ещё завершается. Повторите через несколько секунд.')
            return
        token = self.token.text().strip()
        if not token:
            self.status.setText('Сначала вставьте токен, полученный в BotFather.')
            return
        self.generation += 1
        self.pairing = TelegramPairing(token)
        self.refresh_buttons()
        self.status.setText('Проверяем бота…')
        self.run_job(self.pairing.prepare, self.prepared)

    def prepared(self, pairing, error):
        if error:
            self.cancel()
            self.status.setText(error)
            return
        self.refresh_buttons()
        self.status.setText('Бот @' + pairing.username + ' найден. Нажмите «Открыть моего бота», затем «Запустить» в Telegram. Ждём до 5 минут.')
        self.timer.start()

    def open_bot(self):
        if self.pairing:
            self.open_url(self.pairing.url)

    def poll(self):
        if self.pairing and not self.busy():
            self.run_job(self.pairing.poll, self.received)

    def received(self, recipient, error):
        if error:
            self.cancel()
            self.status.setText(error)
        elif recipient:
            token = self.pairing.token
            username = self.pairing.username
            self.cancel()
            if self.save_values(telegram_bot_token=token, telegram_chat_id=recipient['id'],
                                telegram_chat_name=recipient['name'], telegram_bot_username=username,
                                telegram_verified=False, telegram_enabled=False):
                self.editing = False
                self.token.blockSignals(True); self.token.setText(token); self.token.blockSignals(False)
                self.recipient.setText(self.recipient_text())
                self.enabled.blockSignals(True); self.enabled.setChecked(False); self.enabled.blockSignals(False)
                self.status.setText('Чат привязан. Теперь отправьте пробное уведомление — оно будет без скриншота.')
                self.refresh_buttons()

    def cancel(self):
        self.generation += 1
        self.timer.stop()
        self.pairing = None
        self.refresh_buttons()
        self.status.setText('Привязка отменена. Ранее сохранённый чат не изменён.')

    def send_test(self):
        if self.busy() or self.pairing or self.token.text().strip() != self.config.get_telegram_bot_token():
            return
        client = TelegramPairing(self.config.get_telegram_bot_token())
        chat = self.config.get_telegram_chat_id()
        self.test_button.setEnabled(False)
        self.connect_button.setEnabled(False)
        self.status.setText('Отправляем пробное уведомление в сохранённый чат…')
        self.run_job(lambda: client.request('sendMessage', chat_id=chat,
                     text='Dota 2 Accepter: Telegram подключён. Здесь будут уведомления об игре.'), self.tested)

    def tested(self, result, error):
        if self.save_values(telegram_verified=not bool(error)):
            self.status.setText(('Проверялось сохранённое подключение. Новый токен ещё не применён. ' if self.token.text().strip() != self.config.get_telegram_bot_token() else '') + (error or 'Пробное сообщение отправлено. Теперь можно включить оповещения.'))
        self.refresh_buttons()


class YandexPanel(ConnectionPanel):
    def __init__(self, config):
        super().__init__('Подключение сценария', config)
        self.connected_token = config.get_yandex_token()
        self.editing = False
        self.step1_note = self.note('1. Получите токен Яндекса и вставьте его ниже. Данные сохранятся после успешной загрузки сценариев.')
        help_toggle = self.button('Где получить токен?', lambda: None)
        self.help_toggle = help_toggle
        help_toggle.setCheckable(True)
        help_content = QWidget()
        self.help_content = help_content
        help_layout = QVBoxLayout(help_content)
        help_layout.setContentsMargins(0, 0, 0, 0)
        instructions = WrappedLabel('В Яндекс OAuth зарегистрируйте приложение с правами iot:view и iot:control. Укажите Redirect URI https://oauth.yandex.ru/verification_code. Затем выполните шаги официальной инструкции «Получение токена вручную»: используйте Client ID своего приложения, разрешите доступ и скопируйте выданный токен. Accepter не запрашивает пароль Яндекса. При отзыве или истечении токена получите новый.')
        instructions.setWordWrap(True)
        help_layout.addWidget(instructions)
        oauth = QPushButton('Открыть Яндекс OAuth')
        oauth.clicked.connect(lambda: self.open_url('https://oauth.yandex.ru/'))
        help_layout.addWidget(oauth)
        manual = QPushButton('Инструкция Яндекса по получению токена')
        manual.clicked.connect(lambda: self.open_url('https://yandex.ru/dev/id/doc/ru/tokens/debug-token'))
        help_layout.addWidget(manual)
        help_content.hide()
        help_toggle.toggled.connect(help_content.setVisible)
        self.body.addWidget(help_content)
        self.token = QLineEdit(self.connected_token)
        self.token.setEchoMode(QLineEdit.Password)
        self.token.setPlaceholderText('OAuth-токен Яндекса')
        self.body.addWidget(self.token)
        self.load_button = self.button('Получить сценарии', self.load)
        self.load_button.setProperty('role', 'primary')
        self.cancel_button = self.button('Отменить запрос', self.cancel)
        self.cancel_button.setEnabled(False)
        self.step2_note = self.note('2. Выберите сценарий из «Дома с Алисой».')
        self.scenarios = QComboBox()
        self.scenarios.setMinimumContentsLength(18)
        self.scenarios.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        if config.get_yandex_scenario_id():
            self.scenarios.addItem(config.get_yandex_scenario_name(), config.get_yandex_scenario_id())
        self.body.addWidget(self.scenarios)
        self.scenarios.currentIndexChanged.connect(self.select)
        self.step3_note = self.note('3. Проверьте сценарий, затем включите его. Проверка выполнит реальные действия устройств. Во время ожидания сценарий запускается после Enter или обнаружения экрана выбора героя — в зависимости от режима.')
        self.test_button = self.button('Проверить запуск сценария', self.test)
        self.enabled = QCheckBox('Запускать сценарий по результату ожидания')
        self.enabled.setChecked(config.is_yandex_enabled())
        self.bind_checkbox(self.enabled, 'yandex_enabled')
        self.body.addWidget(self.enabled)
        self.status = self.note('Запуск сценария ранее подтверждён.' if config.is_yandex_verified() else 'Выберите сценарий и проверьте его запуск.' if config.get_yandex_scenario_id() else 'Начните с подключения аккаунта.')
        self.status.setProperty('role', 'notice')
        self.body.insertWidget(0, self.status)
        self.token.textChanged.connect(self.token_changed)
        self.edit_button = self.button('Изменить токен', self.edit_connection)
        self.remove_button = self.button('Удалить подключение', self.remove_connection)
        self.delivery_status = self.note('Последних запусков в этом сеансе нет.')
        self.refresh_buttons()

    def refresh_buttons(self):
        pending = self.busy() or getattr(self, '_operation_busy', False)
        valid = bool(self.connected_token and self.token.text().strip() == self.connected_token and self.scenarios.currentData())
        for control in (self.token, self.load_button, self.scenarios):
            control.setEnabled(not pending)
        self.test_button.setEnabled(valid and not pending)
        self.enabled.setEnabled(not pending and (self.enabled.isChecked() or (valid and self.config.is_yandex_verified())))
        connected = bool(self.connected_token)
        editing = self.editing or not connected
        for control in (self.step1_note, self.help_toggle, self.token):
            control.setVisible(editing)
        self.help_content.setVisible(editing and self.help_toggle.isChecked())
        self.load_button.setText('Получить сценарии' if editing else 'Обновить сценарии')
        if hasattr(self, 'edit_button'):
            self.edit_button.setVisible(connected and not self.editing)
            self.edit_button.setEnabled(not pending)
        for control in (self.step2_note, self.scenarios):
            control.setVisible(connected)
        for control in (self.step3_note, self.test_button, self.enabled):
            control.setVisible(bool(self.scenarios.currentData()))
        self.cancel_button.setVisible(pending)
        self.cancel_button.setEnabled(pending and not getattr(self, '_cancelled', False))
        if hasattr(self, 'remove_button'):
            self.remove_button.setVisible(connected)
            self.remove_button.setEnabled(not pending)

    def edit_connection(self):
        self.editing = True
        self.refresh_buttons()
        self.token.setFocus()

    def token_changed(self):
        self.refresh_buttons()
        self.status.setText('Токен изменён. Нажмите «Получить сценарии». Сохранённое подключение пока не изменено. Если сценарий включён, его можно выключить ниже.')

    def load(self):
        if self.busy():
            return
        token = self.token.text().strip()
        if not token:
            self.status.setText('Вставьте OAuth-токен Яндекса с доступами iot:view и iot:control.')
            return
        self.set_busy(True)
        self.status.setText('Получаем список сценариев…')
        self.generation += 1
        self.run_job(lambda: (token, YandexSmartHome(token).list_scenarios()), self.loaded)

    def set_busy(self, busy):
        self._operation_busy = busy
        if busy:
            self._cancelled = False
        self.refresh_buttons()

    def loaded(self, result, error):
        self.set_busy(False)
        if error:
            self.status.setText(error)
            return
        token, scenarios = result
        old_id = self.config.get_yandex_scenario_id() if token == self.connected_token else ''
        selected = next((item for item in scenarios if item[0] == old_id), ('', ''))
        verified = bool(selected[0] and self.config.is_yandex_verified())
        if not self.save_values(yandex_token=token, yandex_scenario_id=selected[0],
                                yandex_scenario_name=selected[1], yandex_verified=verified,
                                yandex_enabled=self.config.is_yandex_enabled() if verified else False):
            return
        self.connected_token = token
        self.editing = False
        self.enabled.blockSignals(True); self.enabled.setChecked(self.config.is_yandex_enabled()); self.enabled.blockSignals(False)
        self.scenarios.blockSignals(True)
        self.scenarios.clear()
        self.scenarios.addItem('Выберите сценарий…', '')
        for scenario_id, name in scenarios:
            self.scenarios.addItem(name, scenario_id)
        self.scenarios.setCurrentIndex(max(0, self.scenarios.findData(selected[0])))
        self.scenarios.blockSignals(False)
        self.refresh_buttons()
        self.status.setText('Аккаунт подключён. Выберите сценарий и проверьте запуск.' if scenarios else
                            'Аккаунт подключён, сценариев нет. Создайте сценарий в «Доме с Алисой», затем обновите список.')

    def select(self, index):
        scenario_id = self.scenarios.currentData() or ''
        if self.save_values(yandex_scenario_id=scenario_id,
                            yandex_scenario_name=self.scenarios.currentText() if scenario_id else '',
                            yandex_verified=False, yandex_enabled=False):
            self.enabled.blockSignals(True); self.enabled.setChecked(False); self.enabled.blockSignals(False)
            self.status.setText('Сценарий выбран. Запуск ещё не проверен.' if scenario_id else 'Выберите сценарий.')
        else:
            self.scenarios.blockSignals(True)
            self.scenarios.setCurrentIndex(self.scenarios.findData(self.config.get_yandex_scenario_id()))
            self.scenarios.blockSignals(False)
        self.refresh_buttons()

    def test(self):
        if self.busy() or not self.test_button.isEnabled():
            return
        if QMessageBox.question(self, 'Запустить сценарий?',
                'Сценарий «' + self.scenarios.currentText() + '» выполнит реальные действия устройств. Запустить сейчас?',
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        token, scenario = self.connected_token, self.scenarios.currentData()
        self.set_busy(True)
        self.status.setText('Запускаем выбранный сценарий…')
        self.run_job(lambda: YandexSmartHome(token).test_scenario(scenario), self.tested)

    def tested(self, result, error):
        self.set_busy(False)
        success = not error and bool(result[0])
        self.last_operation_error = error or ('' if success else result[1])
        if self.save_values(yandex_verified=bool(success)):
            self.status.setText(error or ('API подтвердил запуск. Включите сценарий для ожидания матча.' if success else result[1]))
        self.refresh_buttons()

    def cancel(self):
        self.generation += 1
        self._cancelled = True
        self.set_busy(False)
        self.status.setText('Ответ будет проигнорирован. Дождитесь завершения текущего запроса перед повтором. Сохранённые настройки не изменены; уже отправленный запуск отменить нельзя.')

    def remove_connection(self):
        if self.busy():
            self.status.setText('Дождитесь завершения текущего запроса.'); return
        if QMessageBox.question(self, 'Удалить подключение?', 'Удалить токен и выбранный сценарий из Accepter? Сам сценарий в Яндексе останется.', QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        self.generation += 1
        if self.config.clear_connection('yandex'):
            self.connected_token = ''
            self.token.blockSignals(True); self.token.clear(); self.token.blockSignals(False)
            self.scenarios.blockSignals(True); self.scenarios.clear(); self.scenarios.blockSignals(False)
            self.enabled.blockSignals(True); self.enabled.setChecked(False); self.enabled.blockSignals(False)
            self.last_operation_error = ''
            self.status.setText('Подключение удалено. Для нового аккаунта вставьте токен.')
            self.delivery_status.setText('Последних запусков для этого подключения нет.')
        else:
            self.status.setText(self.config.last_error)
        self.refresh_buttons()
