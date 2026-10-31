"""Small client for the Yandex Smart Home user API."""

from __future__ import annotations

import json
import re
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit, parse_qs


class YandexError(Exception):
    """Safe, actionable error without token-bearing request details."""


def normalize_token(value):
    """Accept OAuth copy formats without leaking credentials in errors."""
    token = value.strip().strip('"\'').strip()
    if token.lower().startswith(('bearer ', 'oauth ')):
        token = token.split(None, 1)[1].strip()
    if token.startswith(('https://', 'http://')):
        parts = urlsplit(token)
        params = parse_qs(parts.fragment or parts.query)
        values = params.get('access_token', [])
        token = values[0] if len(values) == 1 else ''
    elif token.startswith(('access_token=', '#access_token=')):
        values = parse_qs(token.lstrip('#')).get('access_token', [])
        token = values[0] if len(values) == 1 else ''
    token = token.strip().strip('"\'').strip()
    if not token or not re.fullmatch(r'[A-Za-z0-9_~.+/-]+={0,2}', token):
        raise YandexError('Не удалось выделить access_token. Вставьте токен или ссылку, полученную после разрешения доступа.')
    if re.fullmatch(r'[0-9a-fA-F]{32}', token):
        raise YandexError('Это похоже на Client ID или Client Secret. Нужен access_token после разрешения доступа в Яндексе.')
    return token


class YandexSmartHome:
    API_BASE = "https://api.iot.yandex.net/v1.0"

    def __init__(self, token: str, timeout: int = 20):
        self.token = normalize_token(token)
        self.timeout = timeout

    def _request(self, method: str, path: str, payload=None):
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = Request(
            f"{self.API_BASE}{path}",
            data=body,
            method=method,
            headers={"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"},
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                raw = response.read()
            data = json.loads(raw.decode("utf-8")) if raw else {}
        except HTTPError as error:
            messages = {401: 'Яндекс не принял токен. Получите новый и подключитесь заново.',
                        403: 'Нет доступа. Для токена нужны права iot:view и iot:control.',
                        404: 'Сценарий не найден. Обновите список и выберите его заново.',
                        429: 'Слишком много запросов. Подождите немного и повторите.'}
            raise YandexError(messages.get(error.code, 'Яндекс временно недоступен. Повторите позже.')) from None
        except (URLError, TimeoutError, ValueError):
            raise YandexError('Нет корректного ответа Яндекса. Проверьте интернет и повторите.') from None
        if not isinstance(data, dict) or data.get('status') not in (None, 'ok'):
            raise YandexError('Яндекс не выполнил запрос. Обновите подключение и повторите.')
        return data

    def list_scenarios(self):
        data = self._request("GET", "/user/info")
        return [(item["id"], item["name"]) for item in data.get("scenarios", []) if item.get("id") and item.get("name")]

    def launch_scenario(self, scenario_id: str) -> bool:
        result = self._request("POST", f"/scenarios/{quote(scenario_id, safe='')}/actions")
        return result.get("status") == "ok"

    def test_scenario(self, scenario_id: str):
        """Launch a selected scenario only after confirming it still exists."""
        scenarios = self.list_scenarios()
        if not any(item_id == scenario_id for item_id, _ in scenarios):
            return False, "Сценарий не найден"
        if not self.launch_scenario(scenario_id):
            return False, "API не подтвердил запуск сценария"
        return True, "Сценарий запущен"

    def check_connection(self) -> bool:
        result = self._request("GET", "/user/info")
        return result.get("status") in (None, "ok")
