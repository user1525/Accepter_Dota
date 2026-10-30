"""Compact product identity; typography stays native and scales with Windows."""
from pathlib import Path
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import QFrame,QLabel,QHBoxLayout,QVBoxLayout

class BrandHeader(QFrame):
    def __init__(self,parent=None):
        super().__init__(parent)
        self.setAccessibleName('Dota Accepter — разработчик Zorg')
        layout=QHBoxLayout(self); layout.setContentsMargins(0,0,0,0); layout.setSpacing(12)
        mark=QLabel(); mark.setFixedSize(48,48)
        pixmap=QPixmap(str(Path(__file__).resolve().parents[1]/'resources/icons/accepter_icon.png'))
        ratio=self.devicePixelRatioF()
        scaled=pixmap.scaled(round(48*ratio),round(48*ratio),Qt.KeepAspectRatio,Qt.SmoothTransformation)
        scaled.setDevicePixelRatio(ratio); mark.setPixmap(scaled)
        layout.addWidget(mark)
        text=QVBoxLayout(); text.setSpacing(0)
        title=QLabel('Dota Accepter'); title.setProperty('role','section')
        subtitle=QLabel('Помощник для Dota 2'); subtitle.setProperty('role','muted')
        text.addWidget(title); text.addWidget(subtitle); layout.addLayout(text); layout.addStretch()
