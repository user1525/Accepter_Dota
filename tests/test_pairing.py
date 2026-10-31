import unittest
from unittest.mock import patch, Mock
from core.telegram_pairing import TelegramPairing, PairingError


class PairingTests(unittest.TestCase):
    def message(self, pairing, text=None, kind='private', date=None):
        return {'update_id': 21, 'message': {
            'text': text or '/start ' + pairing.code,
            'date': date if date is not None else pairing.started,
            'chat': {'id': 123, 'type': kind, 'first_name': 'Test'}}}

    def test_only_exact_private_recent_message(self):
        p = TelegramPairing('secret')
        self.assertIsNone(p.match(self.message(p, '/start wrong')))
        self.assertIsNone(p.match(self.message(p, kind='group')))
        # Telegram and Windows clocks may differ; the nonce provides freshness.
        self.assertEqual(p.match(self.message(p, date=p.started - 600))['id'], '123')
        self.assertEqual(p.match(self.message(p))['id'], '123')

    def test_expired_code(self):
        p = TelegramPairing('secret')
        with patch('core.telegram_pairing.time.monotonic', return_value=p.deadline + 1):
            self.assertIsNone(p.match(self.message(p)))

    def test_poll_advances_offset(self):
        p = TelegramPairing('secret')
        p.request = Mock(return_value=[self.message(p, '/start wrong')])
        self.assertIsNone(p.poll())
        self.assertEqual(p.offset, 22)

    def test_webhook_never_removed(self):
        p = TelegramPairing('secret')
        p.request = Mock(side_effect=[{'username': 'sample_bot'}, {'url': 'https://example.org'}])
        with self.assertRaises(PairingError):
            p.prepare()
        self.assertEqual([c.args[0] for c in p.request.call_args_list], ['getMe', 'getWebhookInfo'])

    def test_request_error_does_not_expose_token(self):
        import requests
        p = TelegramPairing('secret')
        with patch('core.telegram_pairing.requests.post', side_effect=requests.ConnectionError('secret')):
            with self.assertRaises(PairingError) as error:
                p.prepare()
        self.assertNotIn('secret', str(error.exception))

    def test_link_contains_nonce_not_token(self):
        p = TelegramPairing('secret')
        p.request = Mock(side_effect=[{'username': 'sample_bot'}, {'url': ''}])
        p.prepare()
        self.assertEqual(p.url, 'https://t.me/sample_bot?start=' + p.code)
        self.assertNotIn('secret', p.url)
