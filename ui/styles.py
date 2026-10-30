"""Shared desktop design tokens and native Qt styling."""
def get_stylesheet():
    return '''
    QWidget { color: #202a37; font-family: "Segoe UI"; font-size: 10pt; }
    QMainWindow, QDialog { background: #eef1f5; }
    QWidget#content, QWidget#page { background: #ffffff; }
    QLabel { background: transparent; }
    QLabel[role="muted"] { color: #596575; }
    QLabel[role="title"] { font-size: 19pt; font-weight: 600; }
    QLabel[role="state"] { font-size: 23pt; font-weight: 600; }
    QLabel[role="section"] { font-size: 12pt; font-weight: 600; }
    QLabel[role="error"] { color: #a33330; background: #fff0ef; padding: 10px; border-radius: 6px; }
    QLabel[role="notice"] { color: #465468; background: #eef2f8; padding: 10px; border-radius: 6px; }
    QListWidget#navigation { background: #eef1f5; border: none; outline: none; }
    QListWidget#navigation::item { padding: 12px 10px; margin: 2px 4px; border-radius: 6px; }
    QListWidget#navigation::item:selected { background: #ffffff; color: #a83430; font-weight: 600; }
    QListWidget#navigation::item:hover:!selected { background: #e3e8ef; }
    QPushButton { background: #ffffff; border: 1px solid #cbd3de; border-radius: 6px; padding: 8px 12px; min-height: 20px; }
    QPushButton:hover { background: #f1f4f8; border-color: #909eaf; }
    QPushButton:pressed { background: #e4e9f0; }
    QPushButton:focus { border: 2px solid #b43e38; padding: 7px 11px; }
    QPushButton:disabled { color: #8993a0; background: #f4f6f8; border-color: #e2e6ec; }
    QPushButton[role="primary"] { background: #b43e38; color: #ffffff; border-color: #b43e38; font-weight: 600; }
    QPushButton[role="primary"]:hover { background: #9d322d; }
    QPushButton[role="primary"]:disabled { background: #e4c7c5; border-color: #e4c7c5; color: #ffffff; }
    QPushButton[role="link"] { border: none; color: #a83430; background: transparent; text-align: left; padding-left: 0; }
    QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox { background: #ffffff; border: 1px solid #cbd3de; border-radius: 6px; padding: 8px; min-height: 20px; selection-background-color: #b43e38; }
    QLineEdit:focus, QComboBox:focus, QDoubleSpinBox:focus { border-color: #b43e38; }
    QLineEdit:disabled, QComboBox:disabled { background: #f4f6f8; color: #8993a0; }
    QComboBox::drop-down { width: 24px; border: none; }
    QComboBox QAbstractItemView { background: white; selection-background-color: #f6e8e7; selection-color: #202a37; }
    QGroupBox { border: 1px solid #d9dfe7; border-radius: 8px; margin-top: 16px; padding: 18px 12px 12px; font-weight: 600; }
    QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 5px; }
    QRadioButton, QCheckBox { spacing: 9px; padding: 6px 0; }
    QRadioButton::indicator, QCheckBox::indicator { width: 17px; height: 17px; }
    QRadioButton::indicator { border: 1px solid #8b98a9; border-radius: 9px; background: white; }
    QRadioButton::indicator:checked { background: #b43e38; border: 4px solid #f0d8d6; }
    QCheckBox::indicator { border: 1px solid #8b98a9; border-radius: 4px; background: white; }
    QCheckBox::indicator:checked { background: #b43e38; border: 3px solid #efd7d5; }
    QCheckBox::indicator:disabled { background: #e2e6ec; border-color: #cbd3de; }
    QCheckBox:disabled { color: #8993a0; }
    QScrollArea, QTabWidget::pane { border: none; background: #ffffff; }
    QScrollBar:vertical { width: 10px; background: #f2f4f7; margin: 0; }
    QScrollBar::handle:vertical { background: #b8c1ce; border-radius: 5px; min-height: 30px; }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
    QTextEdit { background: #f5f7fa; border: 1px solid #d9dfe7; border-radius: 6px; padding: 8px; font-size: 9pt; }
    QProgressBar { border: none; background: #f0e2e1; border-radius: 2px; max-height: 4px; }
    QProgressBar::chunk { background: #b43e38; }
    QSlider::groove:horizontal { height: 5px; background: #dce2ea; border-radius: 2px; }
    QSlider::sub-page:horizontal { background: #b43e38; border-radius: 2px; }
    QSlider::handle:horizontal { background: #b43e38; border: 2px solid white; width: 15px; margin: -7px 0; border-radius: 9px; }
    QToolTip { background: #202a37; color: white; border: none; padding: 8px; }
    '''
