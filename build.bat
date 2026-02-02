@echo off
chcp 65001 >nul
REM 品类匹配工具 - 打包脚本（uv）
REM 委托给 scripts/build.py，默认 onefile；可通过环境变量覆盖。

if not defined BUILD_TARGET set BUILD_TARGET=onefile
if not defined OUTPUT_DIR set OUTPUT_DIR=dist
cd /d "%~dp0"
uv run python scripts/build.py
pause
