#!/usr/bin/env python3
"""
Модуль для отправки уведомлений в Telegram
"""

import requests
from io import BytesIO
from datetime import datetime
from html import escape


class TelegramSender:
    """Класс для отправки уведомлений в Telegram"""

    def __init__(self, bot_token, chat_id):
        """
        Инициализация отправителя

        Args:
            bot_token (str): Токен Telegram-бота
            chat_id (str): ID чата или пользователя
        """
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.api_url = f"https://api.telegram.org/bot{bot_token}"

    @staticmethod
    def _api_error(result):
        # Never echo arbitrary remote text into the UI or logs: it could contain
        # request details. Keep errors useful without exposing credentials.
        messages = {
            401: 'Токен не принят. Подключите бота заново.',
            403: 'Бот заблокирован. Откройте личный чат с ним в Telegram.',
            400: 'Не удалось доставить. Проверьте привязку личного чата.',
            429: 'Telegram ограничил запросы. Повторите позже.',
        }
        return messages.get(result.get('error_code'), 'Telegram не подтвердил доставку. Проверьте подключение.')

    def test_connection(self):
        """
        Проверка подключения к Telegram API

        Returns:
            tuple: (success: bool, message: str)
        """
        try:
            # Проверяем, что бот доступен через getMe
            response = requests.get(f"{self.api_url}/getMe", timeout=10)
            data = response.json()

            if data.get("ok"):
                bot_name = data["result"]["username"]
                return True, f"✅ Подключение успешно! Бот: @{bot_name}"
            else:
                return False, self._api_error(data)

        except requests.exceptions.Timeout:
            return False, "❌ Таймаут соединения"
        except requests.exceptions.ConnectionError:
            return False, "❌ Ошибка подключения к интернету"
        except Exception as e:
            return False, "❌ Не удалось выполнить запрос Telegram. Проверьте сеть и токен."

    def send_message(self, text):
        """
        Отправка текстового сообщения

        Args:
            text (str): Текст сообщения

        Returns:
            tuple: (success: bool, message: str)
        """
        try:
            data = {
                "chat_id": self.chat_id,
                "text": text,
                "parse_mode": "HTML"
            }
            response = requests.post(f"{self.api_url}/sendMessage", json=data, timeout=10)
            result = response.json()

            if result.get("ok"):
                return True, "✅ Сообщение отправлено"
            else:
                return False, self._api_error(result)

        except Exception as e:
            return False, "❌ Не удалось отправить сообщение. Проверьте сеть и доступ бота к чату."

    def send_screenshot(self, text, screenshot=None):
        """
        Отправка сообщения со скриншотом

        Args:
            text (str): Текст сообщения
            screenshot (PIL.Image, optional): Скриншот для отправки

        Returns:
            tuple: (success: bool, message: str)
        """
        try:
            if screenshot is None:
                # Делаем скриншот экрана
                import pyautogui
                screenshot = pyautogui.screenshot()

            # Keep screen contents in memory, including on encode/network errors.
            with BytesIO() as photo:
                screenshot.save(photo, format='PNG')
                photo.seek(0)
                files = {"photo": ('screen.png', photo, 'image/png')}
                data = {"chat_id": self.chat_id, "caption": text, "parse_mode": "HTML"}
                result = requests.post(f"{self.api_url}/sendPhoto", files=files, data=data, timeout=30).json()
                if result.get('ok'):
                    return True, 'Скриншот отправлен'
                return False, self._api_error(result)

        except Exception as e:
            return False, "❌ Не удалось отправить скриншот. Проверьте сеть и настройки Telegram."

    def send_game_accepted_notification(self, screenshot=None, message="Enter отправлен. Принятие матча не подтверждено."):
        """
        Отправка фактического результата ожидания, без обещания принятия матча

        Args:
            screenshot (PIL.Image, optional): Скриншот для отправки

        Returns:
            tuple: (success: bool, message: str)
        """
        timestamp = datetime.now().strftime("%H:%M:%S")
        text = f"🎮 <b>Dota Accepter</b>\n{escape(message)}\n\nВремя: {timestamp}"

        if screenshot is None:
            return self.send_message(text)
        return self.send_screenshot(text, screenshot)


if __name__ == "__main__":
    # Тестирование модуля
    print("Тестирование TelegramSender...")

    # Пример использования (замените на реальные данные)
    # sender = TelegramSender("BOT_TOKEN", "CHAT_ID")
    # success, message = sender.test_connection()
    # print(message)
