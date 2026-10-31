"""Isolated native UI inspection: synthetic data, no hooks/input/network/audio."""
import json,tempfile
from pathlib import Path
from contextlib import ExitStack
from unittest.mock import patch
from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QApplication,QScrollArea
from core.config import Config
from core.app_paths import resource_root

def run_self_check(app,output_directory):
    from ui.main_window_optimized import MainWindow
    from ui.about_dialog import AboutDialog
    output=Path(output_directory).resolve(); output.mkdir(parents=True,exist_ok=True)
    report={'platform':app.platformName(),'screens':[],'external_calls':[],'layout':[],'screens_saved':True}
    def forbidden(*args,**kwargs):
        report['external_calls'].append('blocked'); raise RuntimeError('UI QA: external effects disabled')
    with tempfile.TemporaryDirectory(prefix='accepter-ui-') as folder,ExitStack() as stack:
        for target in ('PIL.ImageGrab.grab','keyboard.add_hotkey','pyautogui.press','pyautogui.screenshot','requests.sessions.Session.request','core.yandex_smart_home.urlopen'):
            stack.enter_context(patch(target,side_effect=forbidden))
        stack.enter_context(patch('ui.main_window_optimized.MainWindow.start_accepter', side_effect=lambda: report['external_calls'].append('start blocked')))
        stack.enter_context(patch('PyQt5.QtGui.QDesktopServices.openUrl', return_value=False))
        stack.enter_context(patch('core.sound_manager.SoundManager.play_sound'))
        stack.enter_context(patch('core.sound_manager.SoundManager.test_sound',return_value=True))
        cfg=Config(Path(folder)/'config.json'); window=MainWindow(enable_hotkeys=False,config=cfg); window.show()
        initial_size=(window.width(),window.height()); report['scale']=window.devicePixelRatioF(); report['synthetic_states']=True
        report['resources']=all((resource_root()/p).is_file() for p in ('resources/templates/accept_button.png','resources/templates/hero_select.png','resources/sounds/program_activated.wav'))
        dialogs=[]
        def capture(name,widget=None):
            target=widget or window; saved=target.grab().save(str(output/(name+'.png'))); report['screens_saved']=report['screens_saved'] and saved; report['screens'].append(name)
            report['layout'].append({'screen':name,'width':target.width(),'height':target.height(),'horizontal_scroll':any(s.horizontalScrollBar().maximum()>0 for s in target.findChildren(QScrollArea) if s.isVisible())})
        def main():
            capture('main'); window.open_settings_section(0); QTimer.singleShot(180,management)
        def management():
            capture('management'); window.open_settings_section(1); QTimer.singleShot(180,sounds)
        def sounds():
            capture('sounds'); window.open_settings_section(2); QTimer.singleShot(180,telegram)
        def telegram():
            capture('telegram'); window.telegram_panel.status.setText('Нет ответа Telegram. Проверьте интернет и повторите.'); window.telegram_panel.last_operation_error='Нет ответа Telegram.'; QTimer.singleShot(180,telegram_error)
        def telegram_error():
            area=window.settings_sections.currentWidget(); area.verticalScrollBar().setValue(area.verticalScrollBar().maximum()); capture('telegram-error'); telegram_pairing()
        def telegram_pairing():
            from core.telegram_pairing import TelegramPairing
            panel=window.telegram_panel; panel.pairing=TelegramPairing('synthetic-qa-token'); panel.pairing.username='accepter_qa_demo_bot'
            panel.refresh_buttons(); panel.status.setText('Откройте бота и нажмите «Запустить». Ждём личный чат до 5 минут.')
            window.settings_sections.currentWidget().verticalScrollBar().setValue(0)
            QTimer.singleShot(180,telegram_linked)
        def telegram_linked():
            capture('telegram-pairing'); panel=window.telegram_panel
            panel.received({'id':'123456','name':'Демонстрационный чат'},None)
            panel.last_operation_error = ''
            panel.tested(True,None)
            panel.refresh_buttons()
            QTimer.singleShot(180,telegram_ready)
        def telegram_ready():
            capture('telegram-ready'); window.open_settings_section(3); QTimer.singleShot(180,yandex)
        def yandex():
            capture('yandex'); panel=window.yandex_panel; panel.token.setText('synthetic-qa-token'); panel.loaded(('synthetic-qa-token',[('qa-scenario','Матч найден')]),None); panel.scenarios.setCurrentIndex(1); QTimer.singleShot(180,yandex_selected)
        def yandex_selected():
            capture('yandex-selected'); window.yandex_panel.cancel(); QTimer.singleShot(180,yandex_cancel)
        def yandex_cancel():
            capture('yandex-cancelled'); window.navigation.setCurrentRow(0); window.set_running_ui(True); window.set_search_state('Вернитесь в Dota 2','Ожидание включено. Нажатия выполняются только в активном окне игры.'); QTimer.singleShot(180,waiting)
        def waiting():
            capture('waiting'); window.set_running_ui(False); window.set_search_state('Enter отправлен','Принятие матча не подтверждено. Ожидание завершено.'); window.record_delivery('Telegram',False,'Не удалось отправить. Проверьте сеть и подключение бота.'); window.log_toggle.setChecked(True)
            for i in range(320): window.log('Проверка ограниченного журнала')
            QTimer.singleShot(180,result)
        def result():
            capture('result'); report['log_blocks']=window.log_text.document().blockCount(); report['stable_geometry']=initial_size==(window.width(),window.height())
            about=AboutDialog(window); dialogs.append(about); screen=QApplication.primaryScreen().availableGeometry(); about.resize(min(550,screen.width()-40),min(570,screen.height()-60)); about.show(); QTimer.singleShot(180,finish)
        def finish():
            capture('about',dialogs[0]); dialogs[0].close(); window.close()
            report['success']=report['screens_saved'] and not report['external_calls'] and report['resources'] and report['stable_geometry'] and report['log_blocks']<=300 and not any(x['horizontal_scroll'] for x in report['layout'])
            (output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8'); app.quit()
        QTimer.singleShot(400,main); app.exec_()
    return 0 if report.get('success') else 1
