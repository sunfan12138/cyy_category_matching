#!/usr/bin/env python3
"""
基于 uv 的跨平台构建脚本：同步依赖并通过 uv run 调用 PyInstaller 打包。

环境变量：
  VERSION        可选，用于产物命名，默认从 pyproject.toml 读取
  BUILD_TARGET   onedir | onefile，默认：Windows 为 onefile，其他为 onedir
  OUTPUT_DIR     构建输出根目录，默认 dist

用法（在项目根目录）：
  uv run python scripts/build.py
  BUILD_TARGET=onefile uv run python scripts/build.py
  VERSION=0.2.0 OUTPUT_DIR=release uv run python scripts/build.py
"""

from __future__ import annotations

import io
import os
import re
import subprocess
import sys
from pathlib import Path

# 项目根目录（脚本所在目录的上一级）
ROOT = Path(__file__).resolve().parent.parent


def _ensure_utf8_io() -> None:
    """On Windows, force stdout/stderr to UTF-8 so Chinese and other Unicode print without UnicodeEncodeError."""
    if sys.platform != "win32":
        return
    for name, stream in [("stdout", sys.stdout), ("stderr", sys.stderr)]:
        if stream is None:
            continue
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError):
            buf = getattr(stream, "buffer", None)
            if buf is not None:
                setattr(
                    sys,
                    name,
                    io.TextIOWrapper(buf, encoding="utf-8", errors="replace", line_buffering=True),
                )


def get_version_from_pyproject() -> str:
    """从 pyproject.toml 读取 version。"""
    path = ROOT / "pyproject.toml"
    if not path.exists():
        return "0.0.0"
    text = path.read_text(encoding="utf-8")
    m = re.search(r'^version\s*=\s*["\']?([\w.]+)', text, re.MULTILINE)
    return m.group(1) if m else "0.0.0"


def get_default_build_target() -> str:
    """默认打包模式：Windows 单文件，其他 onedir。"""
    if sys.platform == "win32":
        return "onefile"
    return "onedir"


def main() -> int:
    _ensure_utf8_io()
    version = os.environ.get("VERSION") or get_version_from_pyproject()
    build_target = (os.environ.get("BUILD_TARGET") or get_default_build_target()).lower()
    output_dir = Path(os.environ.get("OUTPUT_DIR", "dist")).resolve()

    if build_target not in ("onedir", "onefile"):
        print(f"错误: BUILD_TARGET 必须为 onedir 或 onefile，当前为 {build_target!r}", file=sys.stderr)
        return 1

    spec_name = "build-onefile.spec" if build_target == "onefile" else "build.spec"
    spec_path = ROOT / spec_name
    if not spec_path.exists():
        print(f"错误: 未找到 spec 文件 {spec_path}", file=sys.stderr)
        return 1

    print("========================================")
    print("品类匹配工具 - 打包脚本 (uv)")
    print("========================================")
    print(f"  VERSION       = {version}")
    print(f"  BUILD_TARGET  = {build_target}")
    print(f"  OUTPUT_DIR   = {output_dir}")
    print(f"  spec         = {spec_name}")
    print()

    uv_cmd = os.environ.get("UV", "uv")

    # 1. 同步依赖（含 dev，用于 PyInstaller）
    print("[1/3] 同步项目依赖 (uv sync --group dev)...")
    r = subprocess.run(
        [uv_cmd, "sync", "--group", "dev"],
        cwd=str(ROOT),
        shell=False,
    )
    if r.returncode != 0:
        print("依赖同步失败。", file=sys.stderr)
        return r.returncode
    print("依赖同步成功。\n")

    # 2. 调用 PyInstaller（通过 uv run 保证使用项目环境）
    print("[2/3] 调用 PyInstaller...")
    r = subprocess.run(
        [uv_cmd, "run", "pyinstaller", "--clean", "--distpath", str(output_dir), str(spec_path)],
        cwd=str(ROOT),
        shell=False,
    )
    if r.returncode != 0:
        print("打包失败。", file=sys.stderr)
        return r.returncode
    print("打包完成。\n")

    # 4. 提示产物位置
    if build_target == "onefile":
        exe = "CategoryMatching.exe" if sys.platform == "win32" else "CategoryMatching"
        out_exe = output_dir / exe
        print(f"[3/3] 产物: {out_exe}")
    else:
        out_dir = output_dir / "CategoryMatching"
        print(f"[3/3] 产物目录: {out_dir}/")
    print("========================================")
    print("构建成功")
    print("========================================")
    return 0


if __name__ == "__main__":
    sys.exit(main())
