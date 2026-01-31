# -*- mode: python ; coding: utf-8 -*-
# OneFile 备用构建：生成单个 exe，运行时解压到 %TEMP%。
# 若 onedir 版报 "Failed to load Python DLL"，可尝试本版本（从临时目录加载，路径通常为纯英文）。

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[
        'parser',
        'app',
        'paths',
        'torch',
        'torch.nn',
        'torch.nn.functional',
        'sentence_transformers',
        'transformers',
        'modelscope',
        'numpy',
        'openpyxl',
        'tqdm',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter', '_tkinter',
        'matplotlib', 'matplotlib.pyplot',
        'PIL', 'Pillow',
        'pytest', '_pytest', 'test', 'tests',
        'IPython', 'jupyter', 'notebook', 'nbformat',
        'sphinx', 'docutils',
        'cv2', 'opencv',
        'pandas',
        'unittest', 'doctest',
    ],
    win_no_prefer_redirects=True,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='CategoryMatching-OneFile',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
