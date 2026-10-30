#!/usr/bin/env python3
"""
Конфигурация приложения
"""

import json
import copy
import math
import os
import tempfile
from core.app_paths import resource_root, user_data_root
from core.secret_store import protect_secret, unprotect_secret, SecretStoreError
from pathlib import Path


class Config:
    """Класс для управления конфигурацией приложения"""
    
    def __init__(self, config_file=None):
        self.config_file = Path(config_file).resolve() if config_file else user_data_root() / "config.json"
        self.last_error = ''
        self.load_error = ''
        self.load_warnings = []
        self._clear_secrets = set()
        self.secret_errors = {}
        self._unavailable_secrets = {}
        self._write_blocked = False
        self._last_saved = None
        self.default_config = {
            "schema_version": 2,
            "template_path": "resources/templates",
            "timeout": 60,
            "check_interval": 2,
            "click_pause": 2,
            "pre_accept_delay": 1.5,
            "debug_mode": False,
            "auto_start": False,
            "image_threshold": 0.8,
            "keyboard_activation_enabled": True,  # Включаем активацию по клавише по умолчанию
            "activation_key": "INS",
            "default_mode": "simple",  # Добавляем режим по умолчанию
            "notifications_enabled": False,  # Включение оповещений
            "notification_sounds": {
                "start": "program_activated",  # Звук активации
                "stop": "target_deactivated",  # Звук выключения
                "detection": "target_detected"  # Звук обнаружения объекта
            },
            "notification_volume": 100,  # Громкость оповещений (0-100)
            "notification_volumes": {
                "start": 100,
                "stop": 100,
                "detection": 100,
            },
            "minimize_on_start": False,  # Сворачивать окно при запуске
            "telegram_enabled": False,  # Включить Telegram-уведомления
            "telegram_bot_token": "",  # Токен Telegram-бота
            "telegram_chat_id": "",  # ID чата/пользователя
            "telegram_verified": False,
            "telegram_send_screenshot": False  # Скриншоты отключены
            ,"yandex_enabled": False
            ,"yandex_token": ""
            ,"yandex_scenario_id": ""
            ,"yandex_scenario_name": ""
            ,"yandex_verified": False
        }
        self.config = self.load_config()
        self._last_saved = copy.deepcopy(self.config)
        self.load_warnings = list(self.secret_errors.values())
        if self.last_error:
            self.load_warnings.insert(0, self.last_error)

    SECRET_FIELDS = ('telegram_bot_token', 'yandex_token')

    def _normalize(self, incoming):
        """Keep extension keys, validate known fields and fill nested defaults."""
        def merge(defaults, values):
            result = copy.deepcopy(values) if isinstance(values, dict) else {}
            for key, default in defaults.items():
                value = result.get(key)
                if isinstance(default, dict):
                    result[key] = merge(default, value)
                elif isinstance(default, bool):
                    result[key] = value if isinstance(value, bool) else default
                elif isinstance(default, (int, float)):
                    result[key] = value if type(value) in (int, float) and math.isfinite(value) else default
                else:
                    result[key] = value if isinstance(value, str) else default
            return result
        result = merge(self.default_config, incoming)
        ranges = {'timeout': (1, 86400), 'check_interval': (0.1, 60),
                  'click_pause': (0, 60), 'pre_accept_delay': (0, 10),
                  'image_threshold': (0.01, 1), 'notification_volume': (0, 100)}
        for key, (low, high) in ranges.items():
            result[key] = max(low, min(high, result[key]))
        result['notification_volume'] = int(result['notification_volume'])
        for event in self.default_config['notification_volumes']:
            result['notification_volumes'][event] = int(max(0, min(100, result['notification_volumes'][event])))
        if result['default_mode'] not in ('simple', 'check'):
            result['default_mode'] = 'simple'
        if not result['activation_key'].strip():
            result['activation_key'] = self.default_config['activation_key']
        result['schema_version'] = 2
        return result

    def load_config(self):
        if not self.config_file.exists():
            defaults = copy.deepcopy(self.default_config)
            self.save_config(defaults)
            return defaults
        try:
            with self.config_file.open('r', encoding='utf-8-sig') as stream:
                raw = json.load(stream)
            if not isinstance(raw, dict):
                raise ValueError()
        except (OSError, ValueError, UnicodeError):
            self._write_blocked = True
            self.load_error = self.last_error = (
                'Не удалось прочитать config.json. Исходный файл сохранён без изменений. '
                'Исправьте его или переместите в другую папку, чтобы создать новые настройки.')
            return copy.deepcopy(self.default_config)
        version = raw.get('schema_version', 0)
        legacy_volume = type(version) not in (int, float) or version < 2
        if legacy_volume:
            master = raw.get('notification_volume', 100)
            if type(master) not in (int, float) or not math.isfinite(master):
                master = 100
            master = max(0, min(100, master))
            volumes = raw.get('notification_volumes', {})
            if not isinstance(volumes, dict):
                volumes = {}
            migrated = {}
            for event in self.default_config['notification_volumes']:
                amount = volumes.get(event, 100)
                if type(amount) not in (int, float) or not math.isfinite(amount):
                    amount = 100
                migrated[event] = int(max(0, min(100, amount * master / 100)))
            raw['notification_volumes'] = migrated
        plaintext_found = False
        for key in self.SECRET_FIELDS:
            value = raw.get(key, '')
            if isinstance(value, dict):
                try:
                    raw[key] = unprotect_secret(value)
                except SecretStoreError as error:
                    self._unavailable_secrets[key] = copy.deepcopy(value)
                    self.secret_errors[key] = str(error)
                    raw[key] = ''
                    prefix = 'telegram' if key.startswith('telegram') else 'yandex'
                    raw[prefix + '_verified'] = False
            elif isinstance(value, str) and value:
                plaintext_found = True
        config = self._normalize(raw)
        self._last_saved = copy.deepcopy(config)
        # Persist migration once, including sound levels even when no secrets exist.
        # Never make a plaintext backup of legacy tokens.
        if plaintext_found or legacy_volume:
            self.save_config(config)
        return config

    def save_config(self, config=None):
        if self._write_blocked:
            self.last_error = self.load_error
            if self._last_saved is not None and hasattr(self, 'config'):
                self.config = copy.deepcopy(self._last_saved)
            return False
        candidate = self._normalize(self.config if config is None else config)
        payload = copy.deepcopy(candidate)
        temporary = None
        try:
            for key in self.SECRET_FIELDS:
                if not candidate[key] and key in self._unavailable_secrets and key not in self._clear_secrets:
                    payload[key] = copy.deepcopy(self._unavailable_secrets[key])
                else:
                    payload[key] = protect_secret(candidate[key])
            self.config_file.parent.mkdir(parents=True, exist_ok=True)
            fd, temporary = tempfile.mkstemp(prefix='.config-', suffix='.tmp', dir=self.config_file.parent)
            with os.fdopen(fd, 'w', encoding='utf-8') as stream:
                json.dump(payload, stream, indent=2, ensure_ascii=False, allow_nan=False)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.config_file)
            temporary = None
            for key in self.SECRET_FIELDS:
                if candidate[key] or key in self._clear_secrets:
                    self._unavailable_secrets.pop(key, None)
                    self.secret_errors.pop(key, None)
            self._last_saved = copy.deepcopy(candidate)
            if hasattr(self, 'config'):
                self.config = candidate
            self.last_error = ''
            self.load_warnings = list(self.secret_errors.values())
            self._clear_secrets.clear()
            return True
        except SecretStoreError as error:
            self.last_error = str(error)
        except (OSError, ValueError, TypeError):
            self.last_error = ('Не удалось сохранить config.json рядом с программой. '
                               'Перенесите программу в папку с разрешением на запись и повторите.')
        finally:
            if temporary is not None:
                try:
                    os.unlink(temporary)
                except OSError:
                    pass
        self._clear_secrets.clear()
        if self._last_saved is not None and hasattr(self, 'config'):
            self.config = copy.deepcopy(self._last_saved)
        return False

    def get_template_path(self):
        """Получение пути к шаблонам"""
        path = Path(self.config.get("template_path", self.default_config["template_path"]))
        if not path.is_absolute():
            path = resource_root() / path
        return str(path.resolve())
        
    def set_template_path(self, path):
        """Установка пути к шаблонам"""
        self.config["template_path"] = path
        return self.save_config()
        
        
    def get_check_interval(self):
        """Получение интервала проверки"""
        return self.config.get("check_interval", self.default_config["check_interval"])

    def get_timeout(self):
        """Получение таймаута ожидания"""
        return self.config.get("timeout", self.default_config["timeout"])

    def set_timeout(self, timeout):
        """Установка таймаута ожидания"""
        self.config["timeout"] = timeout
        return self.save_config()
        
    def set_check_interval(self, interval):
        """Установка интервала проверки"""
        self.config["check_interval"] = interval
        return self.save_config()
        
    def is_debug_mode(self):
        """Проверка режима отладки"""
        return self.config.get("debug_mode", self.default_config["debug_mode"])
        
    def set_debug_mode(self, debug):
        """Установка режима отладки"""
        self.config["debug_mode"] = debug
        return self.save_config()
        
    def is_auto_start(self):
        """Проверка автозапуска"""
        return self.config.get("auto_start", self.default_config["auto_start"])

    def are_notifications_enabled(self):
        """Проверка включения оповещений"""
        return self.config.get("notifications_enabled", self.default_config["notifications_enabled"])

    def set_notifications_enabled(self, enabled):
        """Установка включения оповещений"""
        self.config["notifications_enabled"] = enabled
        return self.save_config()

    def get_notification_sounds(self):
        """Получение звуков оповещений"""
        return copy.deepcopy(self.config.get("notification_sounds", self.default_config["notification_sounds"]))

    def set_notification_sound(self, event_type, sound):
        """Установка звука оповещения для конкретного события"""
        if "notification_sounds" not in self.config:
            self.config["notification_sounds"] = self.default_config["notification_sounds"].copy()
        self.config["notification_sounds"][event_type] = sound
        return self.save_config()

    def get_notification_volume(self):
        """Получение громкости оповещений"""
        return self.config.get("notification_volume", self.default_config["notification_volume"])

    def set_notification_volume(self, volume):
        """Установка громкости оповещений"""
        self.config["notification_volume"] = volume
        return self.save_config()

    def get_notification_volume_for_event(self, event_type):
        """Получение индивидуальной громкости события (0-100%)."""
        volumes = self.config.get("notification_volumes", self.default_config["notification_volumes"])
        return int(volumes.get(event_type, 100))

    def set_notification_volume_for_event(self, event_type, volume):
        """Установка индивидуальной громкости события (0-100%)."""
        volumes = self.config.setdefault("notification_volumes", copy.deepcopy(self.default_config["notification_volumes"]))
        volumes[event_type] = max(0, min(100, int(volume)))
        return self.save_config()
        
    def set_auto_start(self, auto):
        """Установка автозапуска"""
        self.config["auto_start"] = auto
        return self.save_config()
        
    def get_click_pause(self):
        """Получение паузы после клика"""
        return self.config.get("click_pause", self.default_config["click_pause"])

    def get_pre_accept_delay(self):
        """Получение паузы перед нажатием Enter."""
        return float(self.config.get("pre_accept_delay", self.default_config["pre_accept_delay"]))

    def set_pre_accept_delay(self, delay):
        """Установка паузы перед нажатием Enter."""
        self.config["pre_accept_delay"] = max(0.0, min(10.0, float(delay)))
        return self.save_config()
        
    def set_click_pause(self, pause):
        """Установка паузы после клика"""
        self.config["click_pause"] = pause
        return self.save_config()
        
    def get_image_threshold(self):
        """Получение порога чувствительности для поиска изображений"""
        return self.config.get("image_threshold", self.default_config["image_threshold"])
        
    def set_image_threshold(self, threshold):
        """Установка порога чувствительности для поиска изображений"""
        self.config["image_threshold"] = threshold
        return self.save_config()
        
    def reset_to_defaults(self):
        """Сброс конфигурации к значениям по умолчанию"""
        self._write_blocked = False
        self._clear_secrets.update(self.SECRET_FIELDS)
        self.config = copy.deepcopy(self.default_config)
        return self.save_config()
        
    def get_all_settings(self):
        """Получение всех настроек"""
        return self.config.copy()
        
    def update_settings(self, settings):
        """Обновление настроек"""
        self.config.update(settings)
        return self.save_config()
        
    def is_keyboard_activation_enabled(self):
        """Проверка включена ли активация по клавише"""
        return self.config.get("keyboard_activation_enabled", self.default_config["keyboard_activation_enabled"])
        
    def set_keyboard_activation_enabled(self, enabled):
        """Установка активации по клавише"""
        self.config["keyboard_activation_enabled"] = enabled
        return self.save_config()
        
    def get_activation_key(self):
        """Получение клавиши активации"""
        return self.config.get("activation_key", self.default_config["activation_key"])
        
    def set_activation_key(self, key):
        """Установка клавиши активации"""
        self.config["activation_key"] = key
        return self.save_config()
        
    def get_default_mode(self):
        """Получение режима по умолчанию"""
        return self.config.get("default_mode", self.default_config["default_mode"])
        
    def set_default_mode(self, mode):
        """Установка режима по умолчанию"""
        self.config["default_mode"] = mode
        return self.save_config()

    def is_minimize_on_start_enabled(self):
        """Проверка включения сворачивания при запуске"""
        return self.config.get("minimize_on_start", self.default_config["minimize_on_start"])

    def set_minimize_on_start_enabled(self, enabled):
        """Установка сворачивания при запуске"""
        self.config["minimize_on_start"] = enabled
        return self.save_config()
        
    # === Telegram настройки ===

    # === Яндекс Smart Home ===
    def is_yandex_enabled(self):
        return self.config.get("yandex_enabled", self.default_config["yandex_enabled"])

    def set_yandex_enabled(self, enabled):
        self.config["yandex_enabled"] = bool(enabled)
        return self.save_config()

    def get_yandex_token(self):
        return self.config.get("yandex_token", self.default_config["yandex_token"])

    def set_yandex_token(self, token):
        self._clear_secrets.add('yandex_token')
        self.config["yandex_token"] = token.strip()
        self.config["yandex_verified"] = False
        return self.save_config()

    def get_yandex_scenario_id(self):
        return self.config.get("yandex_scenario_id", self.default_config["yandex_scenario_id"])

    def set_yandex_scenario(self, scenario_id, scenario_name):
        self.config["yandex_scenario_id"] = scenario_id
        self.config["yandex_scenario_name"] = scenario_name
        self.config["yandex_verified"] = False
        return self.save_config()

    def is_yandex_verified(self):
        return bool(self.config.get("yandex_verified", False))

    def set_yandex_verified(self, verified):
        self.config["yandex_verified"] = bool(verified)
        return self.save_config()

    def get_yandex_scenario_name(self):
        return self.config.get("yandex_scenario_name", self.default_config["yandex_scenario_name"])
    
    def is_telegram_enabled(self):
        """Проверка включения Telegram-уведомлений"""
        return self.config.get("telegram_enabled", self.default_config["telegram_enabled"])
        
    def set_telegram_enabled(self, enabled):
        """Установка включения Telegram-уведомлений"""
        self.config["telegram_enabled"] = enabled
        return self.save_config()
        
    def get_telegram_bot_token(self):
        """Получение токена Telegram-бота"""
        return self.config.get("telegram_bot_token", self.default_config["telegram_bot_token"])
        
    def set_telegram_bot_token(self, token):
        """Установка токена Telegram-бота"""
        self._clear_secrets.add('telegram_bot_token')
        self.config["telegram_bot_token"] = token.strip()
        self.config["telegram_verified"] = False
        return self.save_config()
        
    def get_telegram_chat_id(self):
        """Получение ID чата Telegram"""
        return self.config.get("telegram_chat_id", self.default_config["telegram_chat_id"])
        
    def set_telegram_chat_id(self, chat_id):
        """Установка ID чата Telegram"""
        self.config["telegram_chat_id"] = chat_id
        self.config["telegram_verified"] = False
        return self.save_config()

    def is_telegram_verified(self):
        return bool(self.config.get("telegram_verified", False))

    def set_telegram_verified(self, verified):
        self.config["telegram_verified"] = bool(verified)
        return self.save_config()
        
    def is_telegram_send_screenshot(self):
        """Проверка отправки скриншота в Telegram"""
        return self.config.get("telegram_send_screenshot", self.default_config["telegram_send_screenshot"])
        
    def set_telegram_send_screenshot(self, enabled):
        """Установка отправки скриншота в Telegram"""
        self.config["telegram_send_screenshot"] = enabled
        return self.save_config()

    def clear_connection(self, prefix):
        if prefix not in ('telegram', 'yandex'):
            raise ValueError('Unknown connection')
        secret = 'telegram_bot_token' if prefix == 'telegram' else 'yandex_token'
        self._clear_secrets.add(secret)
        self.config[secret] = ''
        self.config[prefix + '_enabled'] = False
        self.config[prefix + '_verified'] = False
        fields = ('telegram_chat_id', 'telegram_chat_name', 'telegram_bot_username') if prefix == 'telegram' else ('yandex_scenario_id', 'yandex_scenario_name')
        for field in fields:
            self.config[field] = ''
        if prefix == 'telegram':
            self.config['telegram_send_screenshot'] = False
        return self.save_config()
