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
echo "可执行文件位于: dist/CategoryMatching/CategoryMatching"
echo
echo "使用说明:"
echo "1. 将 dist/CategoryMatching 文件夹复制到目标机器"
echo "2. 确保 excel 文件夹包含必要的规则文件"
echo "3. 确保 model 文件夹包含模型文件"
echo "4. 运行 CategoryMatching 开始使用"
echo "========================================"
