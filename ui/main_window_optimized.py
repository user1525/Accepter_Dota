"""Main desktop shell. Search, delivery and settings have separate visible states."""
import copy
from datetime import datetime
from PyQt5.QtWidgets import (QApplication,QMainWindow,QWidget,QVBoxLayout,QHBoxLayout,
    QPushButton,QLabel,QGroupBox,QRadioButton,QTextEdit,QFileDialog,QMessageBox,
    QProgressBar,QCheckBox,QTabWidget,QListWidget,QScrollArea,QDoubleSpinBox)
from PyQt5.QtCore import Qt,QTimer,QThread,pyqtSignal,QUrl
from PyQt5.QtGui import QIcon,QDesktopServices
import keyboard
from core.accepter import DotaAccepter
from core.config import Config
from core.app_paths import resource_root
from core.sound_manager import SoundManager
from core.hotkeys import HotkeyBinding,display_hotkey
from core.templates import validate_templates
from ui.styles import get_stylesheet
from ui.brand_header import BrandHeader
from ui.about_dialog import AboutDialog
from ui.connection_widgets import TelegramPanel,YandexPanel
from ui.sound_settings import SoundSettings
from ui.hotkey_dialog import HotkeyDialog


def label(text,role=None):
    item=QLabel(text); item.setWordWrap(True); item.setTextFormat(Qt.PlainText)
    if role: item.setProperty('role',role)
    return item


class WorkerThread(QThread):
    update_signal=pyqtSignal(str)
    finished_signal=pyqtSignal(bool)
    state_signal=pyqtSignal(str,str)
    channel_signal=pyqtSignal(str,object,str)
    def __init__(self,accepter,mode,parent=None):
        super().__init__(parent); self.accepter=accepter; self.mode=mode
    def run(self):
        try:
            success=self.accepter.run_simple_mode() if self.mode=='simple' else self.accepter.run_check_mode()
            self.finished_signal.emit(bool(success))
        except Exception:
            self.update_signal.emit('Не удалось продолжить ожидание. Проверьте окно игры и шаблоны.')
            self.finished_signal.emit(False)


class MainWindow(QMainWindow):
    activation_requested=pyqtSignal()
    def __init__(self,enable_hotkeys=True,config=None):
        super().__init__()
        self.config=config if config is not None else Config()
        self.sound_manager=SoundManager(self.config,sounds_dir=self.config.config_file.parent / "user_sounds")
        self.accepter=None; self.worker_thread=None
        self.key_capture_mode=False; self.stop_requested=False; self._closing=False
        self.delivery={}; self.hotkeys_allowed=enable_hotkeys
        self.activation_requested.connect(self.on_keyboard_activation,Qt.QueuedConnection)
        self.hotkey_binding=HotkeyBinding(self.activation_requested.emit)
        self.init_ui()
        self.sound_manager.error.connect(self.log)
        if enable_hotkeys: self.setup_keyboard_shortcut()
        self.summary_timer=QTimer(self); self.summary_timer.timeout.connect(self.refresh_notification_status); self.summary_timer.start(500)
        self.refresh_notification_status()
        QTimer.singleShot(0,self.show_config_warnings)

    def init_ui(self):
        self.setWindowTitle('Dota Accepter')
        self.setWindowIcon(QIcon(str(resource_root()/'resources/icons/accepter_icon.ico')))
        self.setStyleSheet(get_stylesheet())
        screen=QApplication.primaryScreen().availableGeometry()
        self.setMinimumSize(640,440); self.resize(min(860,screen.width()-40),min(780,screen.height()-60))
        central=QWidget(); self.setCentralWidget(central)
        shell=QVBoxLayout(central); shell.setContentsMargins(24,20,24,16); shell.setSpacing(20)
        header=QHBoxLayout(); header.addWidget(BrandHeader(),1)
        self.discussions_button = QPushButton('Обсуждения')
        self.discussions_button.setProperty('role', 'link')
        self.discussions_button.setToolTip('Вопросы, ошибки и идеи на GitHub')
        self.discussions_button.clicked.connect(self.open_discussion)
        header.addWidget(self.discussions_button)
        about=QPushButton('О программе'); about.setProperty('role','link'); about.clicked.connect(self.show_about); header.addWidget(about)
        shell.addLayout(header)
        body=QHBoxLayout(); body.setSpacing(20)
        self.navigation=QListWidget(); self.navigation.setObjectName('navigation'); self.navigation.setFixedWidth(142)
        self.navigation.addItems(['Ожидание','Управление','Звуки','Telegram','Алиса'])
        self.navigation.setAccessibleName('Разделы программы'); body.addWidget(self.navigation)
        self.tab_widget=QTabWidget(); self.tab_widget.tabBar().hide(); self.tab_widget.setObjectName('content')
        self.main_tab=QWidget(); self.main_tab.setObjectName('page'); self.init_main_tab()
        main_scroll=QScrollArea(); main_scroll.setWidgetResizable(True); main_scroll.setWidget(self.main_tab)
        main_frame=QWidget(); main_frame.setObjectName('content'); main_frame_layout=QVBoxLayout(main_frame); main_frame_layout.setContentsMargins(0,0,0,0); main_frame_layout.setSpacing(0)
        main_frame_layout.addWidget(main_scroll,1); main_frame_layout.addWidget(self.action_panel)
        self.tab_widget.addTab(main_frame,'Ожидание')
        self.settings_tab=QWidget(); self.init_settings_tab(); self.tab_widget.addTab(self.settings_tab,'Настройки')
        body.addWidget(self.tab_widget,1); shell.addLayout(body,1)
        self.config_warning=label('','error'); self.config_warning.hide(); shell.addWidget(self.config_warning)
        footer=label('Настройки сохраняются автоматически. Telegram и Алиса необязательны.','muted'); shell.addWidget(footer)
        self.navigation.currentRowChanged.connect(self.navigate); self.navigation.setCurrentRow(0)

    def navigate(self,index):
        if index==0: self.tab_widget.setCurrentIndex(0)
        else: self.tab_widget.setCurrentIndex(1); self.settings_sections.setCurrentIndex(index-1)

    def open_settings_section(self,index):
        self.navigation.setCurrentRow(index+1)

    def init_main_tab(self):
        layout=QVBoxLayout(self.main_tab); layout.setContentsMargins(24,24,24,24); layout.setSpacing(12)
        self.status_label=label('Готов к ожиданию','state'); layout.addWidget(self.status_label)
        layout.addWidget(label('Начните поиск в Dota 2. Включите ожидание здесь и вернитесь в игру.','muted'))
        self.state_detail=label('Программа нажмёт Enter только в активном окне Dota 2.','muted'); layout.addWidget(self.state_detail)
        self.progress_bar=QProgressBar(); self.progress_bar.setRange(0,0); self.progress_bar.setTextVisible(False); self.progress_bar.hide(); layout.addWidget(self.progress_bar)
        self.mode_group=QGroupBox('Когда завершить ожидание'); modes=QVBoxLayout(self.mode_group); modes.setSpacing(8)
        self.simple_radio=QRadioButton('После отправки Enter'); self.check_radio=QRadioButton('Когда появится выбор героя')
        self.simple_radio.setChecked(self.config.get_default_mode()=='simple'); self.check_radio.setChecked(self.config.get_default_mode()=='check')
        modes.addWidget(self.simple_radio); modes.addWidget(label('Один Enter. Результат принятия не проверяется.','muted'))
        modes.addWidget(self.check_radio); modes.addWidget(label('Продолжать при новом предложении матча.','muted')); layout.addWidget(self.mode_group)
        self.simple_radio.toggled.connect(self.mode_changed)
        self.action_panel=QWidget(); self.action_panel.setObjectName('content')
        action_layout=QVBoxLayout(self.action_panel); action_layout.setContentsMargins(24,12,24,16); action_layout.setSpacing(8)
        actions=QHBoxLayout(); self.start_btn=QPushButton('Включить ожидание'); self.start_btn.setProperty('role','primary')
        self.stop_btn=QPushButton('Остановить'); self.stop_btn.setEnabled(False)
        self.start_btn.clicked.connect(self.start_accepter); self.stop_btn.clicked.connect(self.stop_accepter)
        actions.addWidget(self.start_btn,1); actions.addWidget(self.stop_btn); action_layout.addLayout(actions)
        self.hotkey_hint=label('','muted'); action_layout.addWidget(self.hotkey_hint)
        layout.addWidget(label('Оповещения','section'))
        self.notification_status_buttons={}
        self.notification_toggles={}
        notification_row=QHBoxLayout(); notification_row.setSpacing(8)
        for name,section in [('Звук',1),('Telegram',2),('Алиса',3)]:
            button=QPushButton(); button.setStyleSheet('text-align: left;'); button.clicked.connect(lambda checked=False,i=section:self.open_settings_section(i))
            self.notification_status_buttons[name]=button
            card=QWidget(); card_layout=QVBoxLayout(card); card_layout.setContentsMargins(0,0,0,0); card_layout.setSpacing(4)
            card_layout.addWidget(button)
            toggle=QCheckBox('Включено'); toggle.setAccessibleName(name+': включить оповещения')
            toggle.toggled.connect(lambda checked,n=name:self.toggle_notification(n,checked))
            self.notification_toggles[name]=toggle; card_layout.addWidget(toggle)
            notification_row.addWidget(card,1)
        layout.addLayout(notification_row)
        self.delivery_label=label('Последних доставок в этом сеансе нет.','muted'); layout.addWidget(self.delivery_label)
        self.log_toggle=QPushButton('Показать журнал'); self.log_toggle.setCheckable(True); self.log_toggle.setProperty('role','link')
        self.log_text=QTextEdit(); self.log_text.setReadOnly(True); self.log_text.document().setMaximumBlockCount(300); self.log_text.setMinimumHeight(130); self.log_text.setMaximumHeight(200); self.log_text.hide()
        self.log_toggle.toggled.connect(lambda visible:(self.log_text.setVisible(visible),self.log_toggle.setText('Скрыть журнал' if visible else 'Показать журнал')))
        layout.addWidget(self.log_toggle); layout.addWidget(self.log_text); layout.addStretch()

    def init_settings_tab(self):
        outer=QVBoxLayout(self.settings_tab); outer.setContentsMargins(0,0,0,0)
        self.settings_sections=QTabWidget(); self.settings_sections.tabBar().hide(); outer.addWidget(self.settings_sections)
        management=QWidget(); form=QVBoxLayout(management); form.setSpacing(14)
        form.addWidget(label('Изменения применяются при следующем включении ожидания. Во время ожидания настройки заблокированы.','muted'))
        form.addWidget(label('Пауза после Enter','section'))
        form.addWidget(label('Задержка перед следующим шагом. Не является таймаутом поиска.','muted'))
        self.pause_edit=QDoubleSpinBox(); self.pause_edit.setRange(0,60); self.pause_edit.setDecimals(1); self.pause_edit.setSingleStep(.5); self.pause_edit.setSuffix(' с'); self.pause_edit.setValue(self.config.get_click_pause()); self.pause_edit.setKeyboardTracking(False); self.pause_edit.setAccessibleName('Пауза после Enter')
        self.pause_edit.valueChanged.connect(self.change_pause); form.addWidget(self.pause_edit)
        form.addWidget(label('Горячая клавиша','section'))
        self.keyboard_checkbox=QCheckBox('Запускать и останавливать одной клавишей'); self.keyboard_checkbox.setChecked(self.config.is_keyboard_activation_enabled()); self.keyboard_checkbox.toggled.connect(self.toggle_keyboard_activation); form.addWidget(self.keyboard_checkbox)
        row=QHBoxLayout(); self.key_display=label(self.config.get_activation_key()); self.key_button=QPushButton('Изменить сочетание'); self.key_button.clicked.connect(self.set_activation_key); row.addWidget(self.key_display,1); row.addWidget(self.key_button); form.addLayout(row)
        self.minimize_checkbox=QCheckBox('Сворачивать окно при включении ожидания'); self.minimize_checkbox.setChecked(self.config.is_minimize_on_start_enabled()); self.minimize_checkbox.toggled.connect(self.toggle_minimize_on_start); form.addWidget(self.minimize_checkbox)
        form.addWidget(label('Шаблоны распознавания','section'))
        self.path_status_indicator=label(''); self.path_label=label('','muted'); self.path_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        form.addWidget(self.path_status_indicator); form.addWidget(self.path_label)
        row=QHBoxLayout(); self.browse_btn=QPushButton('Выбрать папку'); self.browse_btn.clicked.connect(self.browse_templates); reset=QPushButton('Встроенные'); reset.clicked.connect(self.restore_templates); row.addWidget(self.browse_btn); row.addWidget(reset); form.addLayout(row)
        form.addWidget(label('Используйте встроенные шаблоны. Своя папка нужна только для другого изображения кнопки или экрана выбора героя.','muted'))
        self.management=management
        self.sound_settings=SoundSettings(self.config,self.sound_manager)
        self.telegram_panel=TelegramPanel(self.config); self.yandex_panel=YandexPanel(self.config)
        for title,subtitle,widget in [('Управление','Ожидание, клавиша и распознавание',management),('Звуки','Три события. Своя запись и громкость для каждого.',self.sound_settings),('Telegram','Сообщение в ваш личный чат',self.telegram_panel),('Алиса','Запуск сценария из «Дома с Алисой»',self.yandex_panel)]:
            page=QWidget(); page.setObjectName('page'); layout=QVBoxLayout(page); layout.setContentsMargins(24,24,24,24); layout.setSpacing(16)
            layout.addWidget(label(title,'title')); layout.addWidget(label(subtitle,'muted')); layout.addWidget(widget); layout.addStretch()
            scroll=QScrollArea(); scroll.setWidgetResizable(True); scroll.setWidget(page); self.settings_sections.addTab(scroll,title)
        self.update_compact_template_status()

    def mode_changed(self):
        mode='simple' if self.simple_radio.isChecked() else 'check'
        if not self.config.set_default_mode(mode):
            self.simple_radio.blockSignals(True)
            self.simple_radio.setChecked(self.config.get_default_mode()=='simple'); self.check_radio.setChecked(self.config.get_default_mode()=='check'); self.simple_radio.blockSignals(False)
        self.update_compact_template_status()

    def show_config_warnings(self):
        messages=list(getattr(self.config,'load_warnings',[]))
        if messages: self.config_warning.setText('\n'.join(messages)); self.config_warning.show()

    def toggle_notification(self,name,checked):
        control={'Звук':self.sound_settings.enabled,'Telegram':self.telegram_panel.enabled,'Алиса':self.yandex_panel.enabled}[name]
        if self.settings_tab.isEnabled() and control.isEnabled():
            control.setChecked(checked)
        self.refresh_notification_status()

    def refresh_notification_status(self):
        cfg=self.config
        self.notification_status_buttons['Звук'].setText('Звук\n'+('Включён' if cfg.are_notifications_enabled() else 'Выключен'))
        for name,prefix,panel in [('Telegram','telegram',self.telegram_panel),('Алиса','yandex',self.yandex_panel)]:
            ready=bool(cfg.config.get(prefix+'_token' if prefix=='yandex' else 'telegram_bot_token') and cfg.config.get(prefix+'_scenario_id' if prefix=='yandex' else 'telegram_chat_id'))
            enabled=cfg.config.get(prefix+'_enabled',False); verified=cfg.config.get(prefix+'_verified',False)
            state='Не настроено' if not ready else ('Включено' if enabled else 'Выключено')
            detail='Проверено ранее' if verified else 'Не проверено'
            if panel.last_operation_error: detail='Ошибка проверки'
            self.notification_status_buttons[name].setText(name+'\n'+state+('\n'+detail if ready else ''))
            self.notification_status_buttons[name].setToolTip(panel.last_operation_error or detail + '. Текущая доступность сети не проверяется автоматически.')
        for name,control in [('Звук',self.sound_settings.enabled),('Telegram',self.telegram_panel.enabled),('Алиса',self.yandex_panel.enabled)]:
            toggle=self.notification_toggles[name]
            toggle.blockSignals(True); toggle.setChecked(control.isChecked()); toggle.blockSignals(False)
            toggle.setText('Включено' if control.isChecked() else 'Выключено')
            toggle.setEnabled(self.settings_tab.isEnabled() and control.isEnabled())
            toggle.setToolTip('Остановите ожидание, чтобы изменить оповещения.' if not self.settings_tab.isEnabled() else
                              'Включить или выключить оповещения.' if control.isEnabled() else
                              'Откройте настройки подключения и успешно выполните проверку.')
        error=self.config.last_error or '\n'.join(getattr(cfg,'load_warnings',[]))
        self.config_warning.setText(error); self.config_warning.setVisible(bool(error))
        try: key=display_hotkey(cfg.get_activation_key())
        except ValueError: key='Не задана'
        active=bool(self.hotkey_binding.handle is not None)
        self.hotkey_hint.setText(('Запуск / остановка: '+key) if active else ('Горячая клавиша выключена' if not cfg.is_keyboard_activation_enabled() else 'Горячая клавиша недоступна. Используйте кнопки.'))
        self.key_display.setText(key)

    def change_pause(self,value=None):
        if not self.config.set_click_pause(self.pause_edit.value()):
            self.pause_edit.blockSignals(True); self.pause_edit.setValue(self.config.get_click_pause()); self.pause_edit.blockSignals(False)
        self.refresh_notification_status()

    def update_compact_template_status(self):
        path=self.config.get_template_path(); mode='simple' if self.simple_radio.isChecked() else 'check'
        ready,detail=validate_templates(path,mode)
        self.path_status_indicator.setText(detail); self.path_label.setText(path)
        self.path_status_indicator.setProperty('role','muted' if ready else 'error')
        self.path_status_indicator.style().unpolish(self.path_status_indicator); self.path_status_indicator.style().polish(self.path_status_indicator)

    def browse_templates(self):
        folder=QFileDialog.getExistingDirectory(self,'Папка с шаблонами',self.config.get_template_path())
        if folder: self.config.set_template_path(folder); self.update_compact_template_status(); self.refresh_notification_status()

    def restore_templates(self):
        self.config.set_template_path('resources/templates'); self.update_compact_template_status(); self.refresh_notification_status()

    def start_accepter(self):
        if self.worker_thread and self.worker_thread.isRunning(): return
        if self.telegram_panel.jobs or self.yandex_panel.jobs or self.telegram_panel.pairing or self.sound_manager._import_worker is not None:
            self.set_search_state('Завершите настройку','Дождитесь запроса или отмените привязку перед включением ожидания.'); return
        mode='simple' if self.simple_radio.isChecked() else 'check'
        ready,detail=validate_templates(self.config.get_template_path(),mode)
        if not ready: self.set_search_state('Нужны шаблоны',detail); return
        if self.config.last_error:
            self.set_search_state('Настройки не сохранены','Исправьте ошибку записи перед включением ожидания.'); return
        if not self.sound_settings.flush_volumes():
            self.set_search_state("Настройки не сохранены", "Проверьте доступ к папке программы."); return
        session_config=copy.copy(self.config); session_config.config=copy.deepcopy(self.config.config)
        self.accepter=DotaAccepter(template_path=self.config.get_template_path(),config=session_config)
        self.accepter.sound_manager=self.sound_manager
        worker=WorkerThread(self.accepter,mode,self); self.worker_thread=worker; self.stop_requested=False
        self.accepter.set_log_callback(worker.update_signal.emit); self.accepter.state_callback=worker.state_signal.emit; self.accepter.channel_callback=worker.channel_signal.emit
        worker.update_signal.connect(self.update_log); worker.state_signal.connect(self.set_search_state); worker.channel_signal.connect(self.record_delivery)
        self._worker_result=False
        worker.finished_signal.connect(self.remember_result); worker.finished.connect(self.worker_done)
        self.set_running_ui(True); self.set_search_state('Ожидание включено','Вернитесь в Dota 2. Проверяем только активное окно игры.')
        self.sound_manager.play_sound('start'); worker.start()
        if self.config.is_minimize_on_start_enabled(): self.showMinimized()

    def remember_result(self,success): self._worker_result=success
    def worker_done(self): self.on_task_finished(self._worker_result)

    def set_running_ui(self,running):
        self.start_btn.setEnabled(not running); self.stop_btn.setEnabled(running); self.progress_bar.setVisible(running)
        self.mode_group.setEnabled(not running); self.settings_tab.setEnabled(not running)
        self.refresh_notification_status()

    def set_search_state(self,title,detail):
        if self.stop_requested and self.worker_thread and self.worker_thread.isRunning(): return
        self.status_label.setText(title); self.state_detail.setText(detail)

    def stop_accepter(self):
        if self.worker_thread and self.worker_thread.isRunning():
            if not self.stop_requested: self.sound_manager.play_sound('stop')
            self.stop_requested=True; self.accepter.stop(); self.stop_btn.setEnabled(False)
            self.status_label.setText('Останавливаем ожидание'); self.state_detail.setText('Новых нажатий не будет. Уже начатый сетевой запрос должен завершиться.')

    def on_task_finished(self,success):
        self.set_running_ui(False)
        if self.stop_requested:
            self.status_label.setText('Ожидание остановлено'); self.state_detail.setText('Новые нажатия и уведомления отменены. Уже отправленные действия отменить нельзя.')
        elif success:
            self.status_label.setText(self.accepter.outcome)
            self.state_detail.setText('Нажатие выполнено. Принятие матча не подтверждено.' if self.accepter.outcome=='Enter отправлен' else 'Обнаружено изображение экрана выбора героя. Ожидание завершено.')
        else:
            self.status_label.setText('Ожидание завершено'); self.state_detail.setText('Результат не подтверждён. Проверьте окно игры и журнал.')
        if self.config.is_minimize_on_start_enabled(): self.showNormal()

    def record_delivery(self,channel,success,detail):
        self.delivery[channel]=datetime.now().strftime('%H:%M:%S')+'  '+detail
        self.delivery_label.setText('\n'.join(name+': '+text for name,text in self.delivery.items()))
        panel=self.telegram_panel if channel=='Telegram' else self.yandex_panel
        panel.delivery_status.setText('Последняя доставка: '+self.delivery[channel])

    def update_log(self,message): self.log_text.append(message)
    def log(self,message): self.update_log(datetime.now().strftime('%H:%M:%S')+'  '+message)
    def open_discussion(self):
        url = 'https://github.com/user1525/Accepter_Dota/discussions/1'
        if not QDesktopServices.openUrl(QUrl(url)):
            QMessageBox.warning(self, 'Обсуждения',
                                'Не удалось открыть браузер. Откройте ссылку вручную:\n' + url)

    def show_about(self): AboutDialog(self).exec_()
    def open_settings(self): self.open_settings_section(0)
    def load_settings(self): self.update_compact_template_status()

    def setup_keyboard_shortcut(self):
        if not self.config.is_keyboard_activation_enabled(): self.hotkey_binding.close(); return
        try: self.hotkey_binding.replace(self.config.get_activation_key())
        except Exception: self.log('Не удалось зарегистрировать горячую клавишу. Выберите другое сочетание.')

    def toggle_keyboard_activation(self,enabled):
        try:
            if enabled and self.hotkeys_allowed:
                self.hotkey_binding.replace(self.config.get_activation_key(),persist=lambda key:self.config.set_keyboard_activation_enabled(True))
            else:
                if not self.config.set_keyboard_activation_enabled(enabled): raise RuntimeError()
                self.hotkey_binding.close()
        except Exception:
            self.keyboard_checkbox.blockSignals(True); self.keyboard_checkbox.setChecked(self.config.is_keyboard_activation_enabled()); self.keyboard_checkbox.blockSignals(False)
            QMessageBox.warning(self,'Горячая клавиша','Не удалось применить настройку. Прежнее сочетание сохранено.')
        self.refresh_notification_status()

    def toggle_minimize_on_start(self,enabled):
        if not self.config.set_minimize_on_start_enabled(enabled):
            self.minimize_checkbox.blockSignals(True); self.minimize_checkbox.setChecked(self.config.is_minimize_on_start_enabled()); self.minimize_checkbox.blockSignals(False)

    def set_activation_key(self):
        self.key_capture_mode=True; self.hotkey_binding.paused=True
        try:
            dialog=HotkeyDialog(self.config.get_activation_key(),self)
            if dialog.exec_()!=dialog.Accepted: return
            if self.config.is_keyboard_activation_enabled() and self.hotkeys_allowed:
                self.hotkey_binding.replace(dialog.selected_key,persist=self.config.set_activation_key)
            elif not self.config.set_activation_key(dialog.selected_key): raise RuntimeError()
        except Exception: QMessageBox.warning(self,'Горячая клавиша','Не удалось сохранить сочетание. Прежняя настройка сохранена.')
        finally: self.key_capture_mode=False; self.hotkey_binding.paused=False; self.refresh_notification_status()

    def on_keyboard_activation(self):
        if self.key_capture_mode or self._closing or QApplication.activeModalWidget(): return
        if self.worker_thread and self.worker_thread.isRunning(): self.stop_accepter()
        else: self.start_accepter()

    def closeEvent(self,event):
        if not getattr(self,'_closing',False):
            if self.worker_thread and self.worker_thread.isRunning():
                if QMessageBox.question(self,'Закрыть программу?','Ожидание ещё включено. Остановить и закрыть?',QMessageBox.Yes|QMessageBox.No,QMessageBox.No)!=QMessageBox.Yes:
                    event.ignore(); return
            self._closing=True; self.telegram_panel.cancel(); self.yandex_panel.generation+=1
            self.sound_manager.shutdown()
            if self.accepter: self.accepter.stop()
            self.setEnabled(False)
        if self.telegram_panel.busy() or self.yandex_panel.busy() or self.sound_manager.busy() or (self.worker_thread and self.worker_thread.isRunning()):
            self.status_label.setText('Завершаем текущие запросы…'); QTimer.singleShot(200,self.close); event.ignore(); return
        self.sound_settings.flush_volumes(); self.hotkey_binding.close(); self.sound_manager.shutdown(); event.accept()
