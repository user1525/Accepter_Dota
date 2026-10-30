"""Product facts; no invented release number or download destination."""
from PyQt5.QtCore import QUrl
from PyQt5.QtGui import QDesktopServices
from PyQt5.QtWidgets import QDialog,QVBoxLayout,QLabel,QPushButton,QDialogButtonBox,QScrollArea,QWidget
from ui.brand_header import BrandHeader
from ui.styles import get_stylesheet
REPOSITORY_URL='https://github.com/user1525/Accepter_Dota'

class AboutDialog(QDialog):
    def __init__(self,parent=None):
        super().__init__(parent)
        self.setWindowTitle('О программе'); self.resize(550,570); self.setStyleSheet(get_stylesheet())
        layout=QVBoxLayout(self); layout.setContentsMargins(24,24,24,24); layout.setSpacing(20)
        layout.addWidget(BrandHeader())
        scroll=QScrollArea(); scroll.setWidgetResizable(True); page=QWidget(); content=QVBoxLayout(page); content.setContentsMargins(0,0,8,0)
        for text,role in [
            ('Разработчик: Zorg','section'),
            ('Помощник для ожидания матча Dota 2. Распознаёт кнопку по изображению и отправляет Enter только в активное окно игры.',None),
            ('Два режима','section'),
            ('Остановиться после Enter или ждать появления экрана выбора героя. Отправка Enter сама по себе не подтверждает принятие матча.',None),
            ('Оповещения','section'),
            ('Три звуковых события с импортом MP3/WAV. Telegram — сообщение и, по желанию, снимок всего экрана. Алиса — запуск выбранного сценария. Оба подключения необязательны.',None),
            ('Условия работы','section'),
            ('Начните поиск в Dota 2 самостоятельно. Игра должна быть видна и активна. Другой язык, разрешение или оформление игры могут потребовать новых шаблонов. Программа не управляет поиском матчей.',None),
            ('Настройки и перенос','section'),
            ('Настройки и свои звуки хранятся рядом с программой. Токены защищаются учётной записью Windows. На другом компьютере подключите сервисы заново.',None),
        ]:
            item=QLabel(text); item.setWordWrap(True)
            if role: item.setProperty('role',role)
            content.addWidget(item)
        scroll.setWidget(page); layout.addWidget(scroll,1)
        github=QPushButton('Исходный код на GitHub'); github.setToolTip(REPOSITORY_URL); github.clicked.connect(lambda:QDesktopServices.openUrl(QUrl(REPOSITORY_URL))); layout.addWidget(github)
        buttons=QDialogButtonBox(QDialogButtonBox.Close); buttons.button(QDialogButtonBox.Close).setText('Закрыть'); buttons.rejected.connect(self.reject); layout.addWidget(buttons)
