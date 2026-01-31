#!/bin/bash

echo "========================================"
echo "品类匹配工具 - 打包脚本 (使用 uv)"
echo "========================================"
echo

echo "[1/3] 检查 uv 是否可用..."
if ! command -v uv &> /dev/null; then
    echo "错误: 未找到 uv 命令！"
    echo "请先安装 uv: curl -LsSf https://astral.sh/uv/install.sh | sh"
    exit 1
fi
echo "uv 已安装。"
echo

echo "[2/3] 同步项目依赖..."
uv sync --group dev
if [ $? -ne 0 ]; then
    echo "依赖同步失败！请检查网络连接或 Python 环境。"
    exit 1
fi
echo "依赖同步成功！"
echo

echo "[3/3] 开始打包..."
echo "打包配置文件: build.spec"
echo "输出目录: dist/CategoryMatching"
echo
uv run pyinstaller --clean build.spec
if [ $? -ne 0 ]; then
    echo "打包失败！请检查错误信息。"
    exit 1
fi
echo

echo "========================================"
echo "打包成功！"
echo "输出目录: dist/CategoryMatching/"
echo "  - CategoryMatching (可执行文件，无后缀)"
echo "  - 及全部依赖 (.so 等)"
echo
echo "使用说明:"
echo "1. 分发请使用整个 dist/CategoryMatching 目录"
echo "2. 在可执行文件同目录下放置 excel、model、output 文件夹"
echo "3. 终端运行: ./CategoryMatching"
echo "========================================"
