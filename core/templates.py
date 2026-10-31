"""One template policy for the UI and detector."""
from pathlib import Path
import cv2
import numpy as np

ACCEPT_NAMES = ('accept_button.png', 'accept_game.png', 'accept_match.png', 'button_accept.png')


def validate_templates(directory, mode='simple'):
    root = Path(directory)
    candidates = [root / name for name in ACCEPT_NAMES if (root / name).is_file()]
    if not candidates:
        return False, 'Нет шаблона кнопки принятия. Выберите папку с accept_button.png или восстановите встроенные шаблоны.'
    required = candidates + ([root / 'hero_select.png'] if mode == 'check' else [])
    for path in required:
        try:
            decoded = cv2.imdecode(np.fromfile(str(path), dtype=np.uint8), cv2.IMREAD_COLOR)
            if decoded is None or not decoded.size:
                raise ValueError()
        except (OSError, ValueError, cv2.error):
            return False, 'Не читается шаблон ' + path.name + '. Выберите другую папку или восстановите файл.'
    return True, 'Шаблоны готовы для выбранного режима.'
