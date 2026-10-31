#!/usr/bin/env python3
"""
Основной модуль для принятия игр Dota 2
"""

import time
import logging
import threading
from datetime import datetime
from pathlib import Path
import pyautogui
import cv2
import numpy as np
from core.image_detector import ImageDetector
from core.game_window import foreground_dota_region
from core.templates import ACCEPT_NAMES, validate_templates
from core.config import Config
from core.telegram_sender import TelegramSender
from core.yandex_smart_home import YandexSmartHome, YandexError


class DotaAccepter:
    """Класс для автоматического принятия игр Dota 2"""

    def __init__(self, template_path="resources/templates", timeout=60, config=None):
        self.template_path = Path(template_path)
        self.timeout = timeout
        self.config = config if config is not None else Config()
        # Используем настраиваемый порог чувствительности
        threshold = self.config.get_image_threshold() if self.config else 0.8
        self.image_detector = ImageDetector(template_path, threshold=threshold)
        self.running = False
        self._stop_event = threading.Event()
        self._accept_visible = False
        self._input_lock = threading.RLock()
        self._pressed_visible = False
        self._missing_frames = 0
        self._notified_visible = False
        self._notification_threads = []
        self._last_state = None
        self.outcome = ""
        self.window_provider = foreground_dota_region
        self.keyboard_mode = False  # Режим активации по клавише
        self.logger = self.setup_logger()

        # Настройки PyAutoGUI
        pyautogui.FAILSAFE = True
        pyautogui.PAUSE = 0.5

    def setup_logger(self):
        """Настройка логирования"""
        logger = logging.getLogger('DotaAccepter')
        logger.setLevel(logging.WARNING)  # Только предупреждения и выше

        # Создаем обработчик для вывода в консоль
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.WARNING)

        # Формат сообщений
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        console_handler.setFormatter(formatter)

        if not logger.handlers:
            logger.addHandler(console_handler)
        return logger

    def get_timestamp(self):
        """Получение текущего времени в формате строки"""
        return datetime.now().strftime("%H:%M:%S")

    def log(self, message, level="info"):
        """Логирование сообщения"""
        timestamp = self.get_timestamp()
        full_message = f"[{timestamp}] {message}"

        if level == "info":
            self.logger.info(message)
        elif level == "warning":
            self.logger.warning(message)
        elif level == "error":
            self.logger.error(message)
        elif level == "debug":
            self.logger.debug(message)

        # Также можно отправлять сообщение в UI через callback, если он установлен
        if hasattr(self, 'log_callback'):
            self.log_callback(full_message)

    def run_simple_mode(self):
        return self._run_mode('simple')

    def run_check_mode(self):
        return self._run_mode('check')

    def notify_button_visibility(self, found):
        """One detection sound per appearance, before the acceptance delay."""
        if found and not self._accept_visible and self.running and not self._stop_event.is_set():
            manager = getattr(self, 'sound_manager', None)
            if manager:
                manager.play_sound('detection')
        self._accept_visible = bool(found)

    def find_and_click_accept_button(self):
        if not self.running or self._stop_event.is_set():
            return False
        result = self.find_accept_button()
        if result.get('error') or result.get('inactive'):
            # Losing focus or failing to capture is not evidence that the button
            # disappeared. Preserve the latch, otherwise focus changes re-arm it.
            return False
        self.notify_button_visibility(result['found'])
        if not result['found']:
            self._missing_frames += 1
            if self._missing_frames >= 2:
                self._pressed_visible = False
                self._notified_visible = False
            return False
        self._missing_frames = 0
        if not self._notified_visible and self.running and not self._stop_event.is_set():
            self._notified_visible = True
            self.start_detection_notifications()
        if self._pressed_visible or not self.running or self._stop_event.is_set():
            return False
        self.set_state('Кнопка найдена', 'Проверяем окно и кнопку ещё раз перед Enter.')
        if self._stop_event.wait(self.config.get_pre_accept_delay()):
            return False
        # A fresh screenshot after the delay; never press using stale detection.
        fresh = self.find_accept_button()
        if not fresh['found']:
            return False
        with self._input_lock:
            current_region = self.window_provider()
            if (self._stop_event.is_set() or not self.running or not current_region
                    or current_region != fresh.get('region', current_region)):
                return False
            pyautogui.press('enter', _pause=False)
            self._pressed_visible = True
        self.set_state('Enter отправлен', 'Принятие матча ещё не подтверждено игрой.')
        return True

    def wait_for_accept_button(self):
        """Ожидание кнопки 'Принять игру' в цикле"""
        self.log("Ожидание кнопки 'Принять игру' в цикле...")
        check_interval = self.config.get_check_interval()

        while self.running:
            accept_button_found = self.find_and_click_accept_button()

            if accept_button_found:
                self.log("Enter отправлен. Принятие матча не подтверждено.")
                return not self._stop_event.wait(self.config.get_click_pause())

            # Ждем перед следующей проверкой
            self._stop_event.wait(check_interval)

        if not self.running:
            self.log("Процесс остановлен пользователем")

        return False

    def wait_for_patterns_parallel_loop(self):
        while self.running and not self._stop_event.is_set():
            if not self.window_provider():
                self.set_state('Вернитесь в Dota 2', 'Ожидание включено. Нажатия выполняются только в активном окне игры.')
                self._stop_event.wait(self.config.get_check_interval())
                continue
            pressed = self.find_and_click_accept_button()
            if self._stop_event.is_set():
                return False
            if not self._accept_visible and self.find_hero_select()['found']:
                return True
            if pressed:
                self._stop_event.wait(self.config.get_click_pause())
            else:
                self.set_state('Ожидаем матч', 'Ищем кнопку принятия и экран выбора героя в окне Dota 2.')
                self._stop_event.wait(self.config.get_check_interval())
        return False

    def find_accept_button(self):
        region = self.window_provider()
        failed = False
        if region:
            for name in ACCEPT_NAMES:
                path = self.template_path / name
                if path.is_file():
                    result = self.image_detector.find_template(str(path), region=region)
                    if self._stop_event.is_set() or self.window_provider() != region:
                        return {'found': False, 'inactive': True, 'position': None, 'confidence': 0.0}
                    failed = failed or bool(result.get('error'))
                    if result['found']:
                        result['region'] = region
                        return result
        return {'found': False, 'position': None, 'confidence': 0.0,
                'inactive': not bool(region), 'error': failed}

    def find_hero_select(self):
        region = self.window_provider()
        if region:
            result = self.image_detector.find_template(str(self.template_path / 'hero_select.png'), region=region)
            if not self._stop_event.is_set() and self.window_provider() == region:
                return result
        return {'found': False, 'position': None, 'confidence': 0.0}

    def stop(self):
        self._stop_event.set()
        with self._input_lock:
            self.running = False
            self.keyboard_mode = False
        self.log('Ожидание остановлено')

    def set_log_callback(self, callback):
        """Установка callback для логирования в UI"""
        self.log_callback = callback

    def toggle_keyboard_mode(self):
        """Переключение режима активации по клавише"""
        if self.config and self.config.is_keyboard_activation_enabled():
            self.keyboard_mode = not self.keyboard_mode
            if self.keyboard_mode:
                self.log("✅ Режим активации по клавише ВКЛЮЧЕН")
                self.log(f"Нажмите клавишу '{self.config.get_activation_key()}' для запуска/остановки")
            else:
                self.log("🛑 Режим активации по клавише ВЫКЛЮЧЕН")
        else:
            self.log("⚠️ Активация по клавише не включена в настройках")

    def is_keyboard_mode_active(self):
        """Проверка активен ли режим активации по клавише"""
        return self.keyboard_mode

    def start_detection_notifications(self):
        """Dispatch both channels immediately without delaying Enter or each other."""
        self._notification_threads = [t for t in self._notification_threads if t.is_alive()]
        message = 'В Dota 2 обнаружена кнопка «Принять игру»: игра найдена. Принятие матча ещё не подтверждено.'
        for enabled, target, args in (
                (self.config.is_telegram_enabled(), self.send_telegram_notification, (message,)),
                (self.config.is_yandex_enabled(), self.send_yandex_notification, ())):
            if enabled and not self._stop_event.is_set():
                thread = threading.Thread(target=target, args=args, daemon=True)
                self._notification_threads.append(thread)
                thread.start()

    def send_yandex_notification(self):
        if self._stop_event.is_set() or not self.config.is_yandex_enabled():
            return
        token, scenario = self.config.get_yandex_token(), self.config.get_yandex_scenario_id()
        if not token or not scenario:
            self.channel_result('Алиса', False, 'Подключение не настроено.')
            return
        self.channel_result('Алиса', None, 'Запускаем сценарий…')
        if self._stop_event.is_set():
            self.channel_result('Алиса', False, 'Запуск отменён до отправки запроса.')
            return
        try:
            success = YandexSmartHome(token).launch_scenario(scenario)
            self.channel_result('Алиса', success, 'API подтвердил запуск.' if success else 'API не подтвердил запуск.')
        except YandexError as error:
            self.channel_result('Алиса', False, str(error))
        except Exception:
            self.channel_result('Алиса', False, 'Не удалось запустить сценарий. Проверьте подключение.')

    def send_telegram_notification(self, message='Enter отправлен. Принятие матча не подтверждено.'):
        if self._stop_event.is_set() or not self.config.is_telegram_enabled():
            return
        token, chat = self.config.get_telegram_bot_token(), self.config.get_telegram_chat_id()
        if not token or not chat:
            self.channel_result('Telegram', False, 'Подключение не настроено.')
            return
        self.channel_result('Telegram', None, 'Отправляем уведомление…')
        try:
            if self._stop_event.is_set():
                self.channel_result('Telegram', False, 'Отправка отменена до запроса.')
                return
            screenshot = pyautogui.screenshot() if self.config.is_telegram_send_screenshot() else None
            if self._stop_event.is_set():
                self.channel_result('Telegram', False, 'Отправка отменена до запроса.')
                return
            success, detail = TelegramSender(token, chat).send_game_accepted_notification(screenshot, message=message)
            self.channel_result('Telegram', success, detail)
        except Exception:
            self.channel_result('Telegram', False, 'Не удалось отправить. Проверьте сеть и подключение бота.')

    def set_state(self, title, detail):
        state = (title, detail)
        if state != self._last_state and not self._stop_event.is_set():
            self._last_state = state
            callback = getattr(self, 'state_callback', None)
            if callback:
                callback(title, detail)
            self.log(title + '. ' + detail)

    def channel_result(self, channel, success, detail):
        callback = getattr(self, 'channel_callback', None)
        if callback:
            callback(channel, success, detail)
        self.log(channel + ': ' + detail)

    def _run_mode(self, mode):
        if self._stop_event.is_set():
            return False
        ready, reason = validate_templates(self.template_path, mode)
        if not ready:
            self.set_state('Нужны шаблоны', reason)
            return False
        self.running = True
        try:
            if mode == 'check':
                success = self.wait_for_patterns_parallel_loop()
                self.outcome = 'Обнаружен экран выбора героя' if success else ''
            else:
                success = False
                while self.running and not self._stop_event.is_set():
                    if not self.window_provider():
                        self.set_state('Вернитесь в Dota 2', 'Ожидание включено. Окно игры должно быть активно и видно.')
                    elif self.find_and_click_accept_button():
                        if self._stop_event.wait(self.config.get_click_pause()):
                            return False
                        success = True
                        self.outcome = 'Enter отправлен'
                        break
                    else:
                        self.set_state('Ожидаем матч', 'Ищем кнопку принятия в активном окне Dota 2.')
                    self._stop_event.wait(self.config.get_check_interval())
            if not success or self._stop_event.is_set():
                return False
            self.set_state(self.outcome, 'Ожидание завершено. Ждём завершения начатых уведомлений.')
            return not self._stop_event.is_set()
        finally:
            for thread in self._notification_threads:
                thread.join()
            self._notification_threads.clear()
            self.running = False
