"""Short-lived, private-chat pairing for a user's own Telegram bot."""
import re
import secrets
import time
import requests


class PairingError(Exception):
    """Safe user-facing error (never includes a credential-bearing URL)."""


class TelegramPairing:
    def __init__(self, token):
        self.token = token.strip()
        self.code = 'accepter_' + secrets.token_urlsafe(24)
        self.started = int(time.time())
        self.deadline = time.monotonic() + 300
        self.offset = 0
        self.username = ''

    def request(self, method, **payload):
        try:
            response = requests.post(
                f'https://api.telegram.org/bot{self.token}/{method}',
                json=payload, timeout=(5, 12))
            data = response.json()
            if not data.get('ok'):
                code = data.get('error_code', response.status_code)
                messages = {
                    401: 'Токен не принят. Скопируйте его заново из BotFather.',
                    404: 'Бот не найден. Проверьте токен из BotFather.',
                    409: 'Бот уже получает сообщения в другой программе. Закройте её или создайте отдельного бота.',
                    429: 'Telegram ограничил запросы. Подождите немного и повторите.',
                    403: 'Бот заблокирован. Откройте его в Telegram и нажмите «Запустить».',
                }
                raise PairingError(messages.get(code, 'Telegram не выполнил запрос. Проверьте настройки и повторите.'))
            return data['result']
        except PairingError:
            raise
        except (requests.RequestException, ValueError, KeyError, TypeError):
            raise PairingError('Нет ответа Telegram. Проверьте интернет и повторите.') from None

    def prepare(self):
        bot = self.request('getMe')
        username = bot.get('username', '')
        if not re.fullmatch(r'[A-Za-z0-9_]+', username):
            raise PairingError('Не удалось определить имя бота.')
        if self.request('getWebhookInfo').get('url'):
            raise PairingError('Этот бот подключён к серверу. Используйте отдельного бота для Accepter; его настройки не изменены.')
        self.username = username
        return self

    @property
    def url(self):
        return f'https://t.me/{self.username}?start={self.code}'

    def match(self, update):
        message = update.get('message', {})
        chat = message.get('chat', {})
        if (time.monotonic() > self.deadline
                or message.get('text') != '/start ' + self.code
                or chat.get('type') != 'private'
                or not chat.get('id')):
            return None
        return {'id': str(chat['id']), 'name': chat.get('first_name') or chat.get('username') or 'Личный чат'}

    def poll(self):
        if time.monotonic() > self.deadline:
            raise PairingError('Время привязки истекло. Нажмите «Подключить бота» ещё раз.')
        updates = self.request('getUpdates', offset=self.offset, timeout=5, allowed_updates=['message'])
        for update in updates:
            self.offset = max(self.offset, update['update_id'] + 1)
            match = self.match(update)
            if match:
                return match
        return None
