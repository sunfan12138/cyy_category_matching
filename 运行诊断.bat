@echo off
chcp 65001 >nul
echo ========================================
echo 品类匹配工具 - 运行诊断
echo ========================================
echo.
echo 当前目录: %CD%
echo 当前目录（短路径）: 
for %%I in (.) do echo   %%~sI
echo.
echo 正在启动 CategoryMatching.exe ...
echo 若下方报错中出现路径，请确认该路径中是否包含中文或特殊字符。
echo ----------------------------------------
CategoryMatching.exe
echo ----------------------------------------
echo 退出码: %errorlevel%
echo.
pause
