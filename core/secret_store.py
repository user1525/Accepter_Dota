"""Windows DPAPI current-user encryption. No application key or fallback plaintext."""
import base64
import ctypes
from ctypes import wintypes
import os


class SecretStoreError(Exception):
    pass


class DATA_BLOB(ctypes.Structure):
    _fields_ = [('cbData', wintypes.DWORD), ('pbData', ctypes.POINTER(ctypes.c_ubyte))]


def _transform(data, decrypt=False):
    if os.name != 'nt':
        raise SecretStoreError('Шифрование токенов доступно только в Windows.')
    crypt32 = ctypes.WinDLL('crypt32', use_last_error=True)
    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
    function = crypt32.CryptUnprotectData if decrypt else crypt32.CryptProtectData
    function.argtypes = [ctypes.POINTER(DATA_BLOB), ctypes.c_void_p,
                         ctypes.POINTER(DATA_BLOB), ctypes.c_void_p,
                         ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(DATA_BLOB)]
    function.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    buffer = ctypes.create_string_buffer(data, len(data))
    incoming = DATA_BLOB(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    outgoing = DATA_BLOB()
    # CRYPTPROTECT_UI_FORBIDDEN only: never use LOCAL_MACHINE scope.
    if not function(ctypes.byref(incoming), None, None, None, None, 1, ctypes.byref(outgoing)):
        raise SecretStoreError('Не удалось расшифровать токен. Подключите сервис заново.' if decrypt
                               else 'Windows не удалось зашифровать токен. Настройки не сохранены.')
    try:
        return ctypes.string_at(outgoing.pbData, outgoing.cbData)
    finally:
        kernel32.LocalFree(outgoing.pbData)


def protect_secret(value):
    if not value:
        return ''
    return {'scheme': 'dpapi-user-v1', 'blob': base64.b64encode(_transform(value.encode('utf-8'))).decode('ascii')}


def unprotect_secret(value):
    try:
        if not isinstance(value, dict) or value.get('scheme') != 'dpapi-user-v1':
            raise ValueError()
        blob = base64.b64decode(value['blob'], validate=True)
        return _transform(blob, decrypt=True).decode('utf-8')
    except (ValueError, KeyError, TypeError, UnicodeError, SecretStoreError):
        raise SecretStoreError('Не удалось расшифровать токен. Подключите сервис заново.') from None
