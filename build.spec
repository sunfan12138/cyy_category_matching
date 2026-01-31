# -*- mode: python ; coding: utf-8 -*-
# 使用 onedir 模式：输出目录 dist/CategoryMatching/，内含 exe 与全部 DLL 依赖，
# 发布/分发时需打包整个目录（或上传该目录的 zip），不可只上传单个 exe。
# excludes 与 strip 用于缩小体积。

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
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='CategoryMatching',
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

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='CategoryMatching',
)
