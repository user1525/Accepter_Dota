"""Canonical single-chord hotkeys and transactional global registration."""
import re
import keyboard


_ALIASES = {
    'control': 'ctrl', 'ins': 'insert', 'del': 'delete', 'esc': 'escape',
    'return': 'enter', 'пробел': 'space', 'pageup': 'page up',
    'pagedown': 'page down', 'pgup': 'page up', 'pgdn': 'page down',
}
_KEYS = {'insert', 'delete', 'enter', 'space', 'tab', 'backspace',
         'home', 'end', 'page up', 'page down', 'left', 'right', 'up', 'down',
         'pause', 'print screen', 'caps lock', 'num lock', 'scroll lock'}
_MODIFIERS = ('ctrl', 'alt', 'shift')


def normalize_hotkey(value):
    """Return keyboard's stable English representation; reject sequences."""
    if not isinstance(value, str):
        raise ValueError('Нажмите клавишу или сочетание Ctrl, Alt, Shift с клавишей.')
    parts = [_ALIASES.get(part.strip().lower(), part.strip().lower())
             for part in value.split('+')]
    if not parts or any(not part for part in parts):
        raise ValueError('Сочетание не задано.')
    key = parts[-1]
    modifiers = parts[:-1]
    if (any(part not in _MODIFIERS for part in modifiers)
            or len(set(modifiers)) != len(modifiers)
            or not (key in _KEYS or re.fullmatch(r'[a-z0-9]|f(?:[1-9]|1[0-9]|2[0-4])', key))):
        raise ValueError('Выберите одну клавишу, при необходимости с Ctrl, Alt или Shift.')
    normalized = '+'.join([mod for mod in _MODIFIERS if mod in modifiers] + [key])
    if normalized in ('alt+f4', 'ctrl+alt+delete', 'alt+tab', 'ctrl+escape'):
        raise ValueError('Это системное сочетание Windows. Выберите другое.')
    return normalized


def display_hotkey(value):
    names = {'ctrl': 'Ctrl', 'alt': 'Alt', 'shift': 'Shift', 'insert': 'Insert',
             'page up': 'PageUp', 'page down': 'PageDown', 'space': 'Space'}
    return '+'.join(names.get(part, part.upper() if len(part) == 1 or part.startswith('f') else part.title())
                    for part in normalize_hotkey(value).split('+'))


class ReleaseHotkeyBackend:
    """Track the chord from ordered events, not keyboard's mutable pressed table."""
    def add_hotkey(self, key, callback, trigger_on_release=True):
        combinations = keyboard.parse_hotkey_combinations(key)[0]
        chords = [set(chord) for chord in combinations]
        pressed = set()
        armed = None

        def event_received(event):
            nonlocal armed
            if event.event_type == keyboard.KEY_DOWN:
                pressed.add(event.scan_code)
                if armed is not None and pressed != armed:
                    armed = None
                if armed is None:
                    armed = next((chord for chord in chords if chord == pressed), None)
            elif event.event_type == keyboard.KEY_UP:
                fire = armed is not None and event.scan_code in armed
                pressed.discard(event.scan_code)
                if fire:
                    armed = None
                    callback()

        return keyboard.hook(event_received, suppress=False)

    def remove_hotkey(self, handle):
        keyboard.unhook(handle)


class HotkeyBinding:
    """Keep an old working binding until both registration and persistence succeed.

    ``replace(key, persist)`` calls persist(canonical_key), which must return True
    only after successfully saving. The callback should emit a Qt signal, never
    manipulate widgets directly. Pausing keeps the OS hook but suppresses actions.
    """
    def __init__(self, callback, backend=None):
        self.callback = callback
        self.backend = backend if backend is not None else ReleaseHotkeyBackend()
        self.handle = None
        self.key = None
        self.paused = False
        self._active = None

    def replace(self, key, persist=None):
        canonical = normalize_hotkey(key)
        if canonical == self.key and self.handle is not None:
            if persist is not None and persist(canonical) is not True:
                raise RuntimeError('Не удалось сохранить сочетание. Прежняя клавиша сохранена.')
            return canonical
        identity = object()

        def activated():
            if not self.paused and self._active is identity:
                self.callback()

        new_handle = self.backend.add_hotkey(canonical, activated, trigger_on_release=True)
        try:
            if persist is not None and persist(canonical) is not True:
                raise RuntimeError('Не удалось сохранить сочетание. Прежняя клавиша сохранена.')
        except Exception:
            self.backend.remove_hotkey(new_handle)
            raise
        old_handle = self.handle
        self.handle, self.key, self._active = new_handle, canonical, identity
        if old_handle is not None:
            # A failed OS unhook must not make the old callback active again.
            try:
                self.backend.remove_hotkey(old_handle)
            except (KeyError, ValueError):
                pass
        return canonical

    def close(self):
        self._active = None
        handle, self.handle, self.key = self.handle, None, None
        if handle is not None:
            try:
                self.backend.remove_hotkey(handle)
            except (KeyError, ValueError):
                pass
