"""Desktop entry point with per-user instance ownership and isolated UI QA."""
import sys
from PyQt5.QtWidgets import QApplication,QMessageBox
from PyQt5.QtCore import Qt
from ui.main_window_optimized import MainWindow
from core.single_instance import acquire_instance

def main():
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling,True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps,True)
    app=QApplication(sys.argv); app.setApplicationName('Dota Accepter'); app.setOrganizationName('Accepter')
    if '--ui-check' in sys.argv:
        from core.self_check import run_self_check
        index=sys.argv.index('--ui-check')
        if index+1>=len(sys.argv): return 2
        return run_self_check(app,sys.argv[index+1])
    if '--self-check' in sys.argv:
        QMessageBox.information(None,'Проверка','Для изолированной проверки используйте --ui-check с отдельной папкой результатов.'); return 2
    lock=acquire_instance()
    if lock is None:
        QMessageBox.information(None,'Dota Accepter уже открыт','Используйте уже открытое окно программы. Второй экземпляр не запускается.'); return 0
    window=MainWindow(); window.show()
    result=app.exec_(); lock.unlock(); return result

if __name__=='__main__': sys.exit(main())
