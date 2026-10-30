# -*- mode: python ; coding: utf-8 -*-
"""
Spec file for Dota 2 Accepter - PyInstaller configuration
"""

from pathlib import Path

# Only distributable assets. User config, tokens and imported audio never enter EXE.
project_root = Path(SPECPATH)
resource_files = [
    (str(path), str(path.parent.relative_to(project_root)))
    for path in (project_root / 'resources').rglob('*')
    if path.is_file() and path.suffix.lower() in ('.png', '.ico', '.wav')
    and not {'user', 'user_sounds'}.intersection(path.relative_to(project_root).parts)
]
block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=resource_files + [(str(project_root / 'THIRD_PARTY_NOTICES.md'), '.'),
                            (str(project_root / 'licenses'), 'licenses')],
    hiddenimports=[
        'cv2',
        'numpy',
        'PyQt5',
        'pyautogui',
        'keyboard',
        'requests',
        'PIL',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='Accepter',
    icon=str(project_root / 'resources' / 'icons' / 'accepter_icon.ico'),
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # Set to False for GUI app
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
