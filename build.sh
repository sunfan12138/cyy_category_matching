#!/usr/bin/env bash
# 品类匹配工具 - 打包脚本（uv）
# 委托给 scripts/build.py，默认 onedir；可通过环境变量覆盖。

set -e
export BUILD_TARGET="${BUILD_TARGET:-onedir}"
export OUTPUT_DIR="${OUTPUT_DIR:-dist}"
cd "$(dirname "$0")"
exec uv run python scripts/build.py
