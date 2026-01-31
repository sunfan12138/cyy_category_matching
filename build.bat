@echo off
chcp 65001 >nul
echo ========================================
echo 品类匹配工具 - 打包脚本 (使用 uv)
echo ========================================
echo.

echo [1/3] 检查 uv 是否可用...
where uv >nul 2>&1
if %errorlevel% neq 0 (
    echo 错误: 未找到 uv 命令！
    echo 请先安装 uv: powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
    pause
    exit /b 1
)
echo uv 已安装。
echo.

echo [2/3] 同步项目依赖...
uv sync --group dev
if %errorlevel% neq 0 (
    echo 依赖同步失败！请检查网络连接或 Python 环境。
    pause
    exit /b 1
)
echo 依赖同步成功！
echo.

echo [3/3] 开始打包 (OneFile: 单 exe)...
echo 打包配置文件: build-onefile.spec
echo 输出: dist\CategoryMatching.exe
echo.
uv run pyinstaller --clean build-onefile.spec
if %errorlevel% neq 0 (
    echo 打包失败！请检查错误信息。
    pause
    exit /b 1
)
echo.

echo ========================================
echo 打包成功！
echo 输出: dist\CategoryMatching.exe （单文件）
echo.
echo 使用说明:
echo 1. 分发/发布可单独分发 exe 或与使用说明等一起打 zip
echo 2. 在 exe 同目录下放置 excel、model、output 文件夹
echo 3. 运行 CategoryMatching.exe 开始使用
echo ========================================
pause
