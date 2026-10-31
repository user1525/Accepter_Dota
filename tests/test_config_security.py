import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from core.app_paths import resource_root, user_data_root
from core.config import Config
from core.secret_store import protect_secret, unprotect_secret, SecretStoreError


class ConfigSecurityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'config.json'

    def tearDown(self):
        self.temp.cleanup()

    def test_absent_config_creates_clean_defaults(self):
        config = Config(self.path)
        saved = json.loads(self.path.read_text(encoding='utf-8'))
        self.assertEqual(saved['telegram_bot_token'], '')
        self.assertEqual(saved['yandex_token'], '')
        self.assertFalse(saved['telegram_enabled'])
        self.assertFalse(saved['yandex_enabled'])
        self.assertFalse(config.last_error)

    @unittest.skipUnless(os.name == 'nt', 'Windows DPAPI')
    def test_dpapi_roundtrip_and_no_plaintext_on_disk(self):
        config = Config(self.path)
        token = 'test-only-private-token-123'
        self.assertTrue(config.set_yandex_token(token))
        disk = self.path.read_text(encoding='utf-8')
        self.assertNotIn(token, disk)
        self.assertEqual(json.loads(disk)['yandex_token']['scheme'], 'dpapi-user-v1')
        self.assertEqual(Config(self.path).get_yandex_token(), token)

    @unittest.skipUnless(os.name == 'nt', 'Windows DPAPI')
    def test_legacy_plaintext_migrates_without_plaintext_backup(self):
        self.path.write_text(json.dumps({'telegram_bot_token': 'legacy-test-secret', 'telegram_chat_id': '123'}), encoding='utf-8')
        config = Config(self.path)
        self.assertEqual(config.get_telegram_bot_token(), 'legacy-test-secret')
        self.assertNotIn('legacy-test-secret', self.path.read_text(encoding='utf-8'))
        self.assertEqual(list(self.path.parent.iterdir()), [self.path])

    def test_unreadable_secret_survives_unrelated_save(self):
        cipher = {'scheme': 'dpapi-user-v1', 'blob': 'invalid'}
        self.path.write_text(json.dumps({'yandex_token': cipher, 'yandex_verified': True}), encoding='utf-8')
        config = Config(self.path)
        self.assertEqual(config.get_yandex_token(), '')
        self.assertFalse(config.is_yandex_verified())
        self.assertIn('yandex_token', config.secret_errors)
        self.assertTrue(config.set_activation_key('F8'))
        self.assertEqual(json.loads(self.path.read_text(encoding='utf-8'))['yandex_token'], cipher)
        self.assertTrue(config.set_yandex_token(''))
        self.assertEqual(json.loads(self.path.read_text(encoding='utf-8'))['yandex_token'], '')

    def test_invalid_config_never_overwritten(self):
        self.path.write_text('{broken', encoding='utf-8')
        config = Config(self.path)
        self.assertTrue(config.load_error)
        self.assertFalse(config.set_activation_key('F8'))
        self.assertEqual(self.path.read_text(encoding='utf-8'), '{broken')
        self.assertEqual(config.get_activation_key(), 'INS')

    def test_wrong_types_and_partial_nested_settings(self):
        self.path.write_text(json.dumps({'notification_volumes': {'start': 250, 'stop': 'bad'},
            'check_interval': -1, 'notifications_enabled': 'yes', 'default_mode': 'bad',
            'notification_sounds': {'start': 'custom'}, 'image_threshold': None}), encoding='utf-8')
        config = Config(self.path)
        self.assertEqual(config.get_notification_volume_for_event('start'), 100)
        self.assertEqual(config.get_notification_volume_for_event('stop'), 100)
        self.assertEqual(config.get_notification_sounds()['detection'], 'target_detected')
        self.assertFalse(config.are_notifications_enabled())
        self.assertGreater(config.get_check_interval(), 0)
        self.assertEqual(config.get_default_mode(), 'simple')

    def test_failed_atomic_replace_preserves_disk_and_memory(self):
        config = Config(self.path)
        original = self.path.read_bytes()
        with patch('core.config.os.replace', side_effect=PermissionError):
            self.assertFalse(config.set_activation_key('F8'))
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(config.get_activation_key(), 'INS')
        self.assertTrue(config.last_error)
        self.assertEqual(list(self.path.parent.iterdir()), [self.path])

    def test_encryption_failure_never_saves_plaintext(self):
        config = Config(self.path)
        with patch('core.config.protect_secret', side_effect=SecretStoreError('Encryption failed')):
            self.assertFalse(config.set_telegram_bot_token('test-secret'))
        self.assertNotIn('test-secret', self.path.read_text(encoding='utf-8'))
        self.assertEqual(config.get_telegram_bot_token(), '')

    def test_no_fallback_when_portable_folder_unwritable(self):
        with patch('core.config.tempfile.mkstemp', side_effect=PermissionError):
            config = Config(self.path)
        self.assertFalse(self.path.exists())
        self.assertTrue(config.last_error)
        self.assertTrue(config.load_warnings)

    def test_bundle_resources_separate_from_config(self):
        with patch.object(sys, 'frozen', True, create=True), \
             patch.object(sys, '_MEIPASS', str(Path(self.temp.name) / 'bundle'), create=True), \
             patch.object(sys, 'executable', str(Path(self.temp.name) / 'portable' / 'Accepter.exe')):
            self.assertEqual(user_data_root(), Path(self.temp.name) / 'portable')
            self.assertEqual(resource_root(), Path(self.temp.name) / 'bundle')
            config = Config(self.path)
            self.assertEqual(config.get_template_path(), str((resource_root() / 'resources/templates').resolve()))

    def test_build_does_not_bundle_config_or_source_trees(self):
        spec = (Path(__file__).resolve().parents[1] / 'accepter.spec').read_text(encoding='utf-8')
        self.assertNotIn("('config.json',", spec)
        self.assertNotIn("('core', 'core')", spec)
        self.assertIn("{'user', 'user_sounds'}", spec)

    def test_legacy_master_volume_is_applied_once(self):
        self.path.write_text(json.dumps({'notification_volume': 20,
            'notification_volumes': {'start': 50, 'stop': 200}}), encoding='utf-8')
        config = Config(self.path)
        self.assertEqual(config.config['notification_volumes'],
                         {'start': 10, 'stop': 40, 'detection': 20})
        self.assertEqual(json.loads(self.path.read_text(encoding='utf-8'))['schema_version'], 2)
        self.assertEqual(Config(self.path).config['notification_volumes'],
                         {'start': 10, 'stop': 40, 'detection': 20})

    def test_new_schema_event_volumes_ignore_legacy_master(self):
        self.path.write_text(json.dumps({'schema_version': 2, 'notification_volume': 10,
            'notification_volumes': {'start': 50}}), encoding='utf-8')
        config = Config(self.path)
        self.assertEqual(config.get_notification_volume_for_event('start'), 50)

    def test_legacy_master_without_event_levels_and_muted(self):
        for master in (0, 16, 100):
            self.path.write_text(json.dumps({'notification_volume': master}), encoding='utf-8')
            config = Config(self.path)
            self.assertEqual(set(config.config['notification_volumes'].values()), {master})


if __name__ == '__main__':
    unittest.main()


def test_both_tokens_survive_fresh_process_and_unrelated_save(tmp_path):
    import subprocess
    path=tmp_path/'restart.json'
    config=Config(path)
    config.config.update(telegram_bot_token='synthetic-tg-restart',yandex_token='synthetic-ya-restart')
    assert config.save_config()
    script = "from core.config import Config; import sys; c=Config(sys.argv[1]); assert c.get_telegram_bot_token()=='synthetic-tg-restart'; assert c.get_yandex_token()=='synthetic-ya-restart'; assert c.set_notifications_enabled(True)"
    result=subprocess.run([sys.executable,'-B','-c',script,str(path)],capture_output=True,timeout=15)
    assert result.returncode==0,result.stderr.decode(errors='replace')
    restored=Config(path)
    assert restored.get_telegram_bot_token()=='synthetic-tg-restart'
    assert restored.get_yandex_token()=='synthetic-ya-restart'
    assert 'synthetic-' not in path.read_text(encoding='utf-8')
