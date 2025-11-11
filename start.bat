@echo off
chcp 65001 > nul & rem 解决中文乱码问题（使用rem作为注释符号）

echo ==============================================
echo 人声处理工具 - 启动中...
echo 首次运行若提示下载模型，请确保网络正常
echo ==============================================

:: 1. 动态获取当前项目根目录（兼容任意解压位置）
set "PROJECT_ROOT=%~dp0"

:: 2. 定位关键路径（使用双引号避免路径含空格/中文的问题）
set "PYTHON_EXE=%PROJECT_ROOT%python\python.exe"
set "RUN_SCRIPT=%PROJECT_ROOT%src\main.py"
set "FFMPEG_PATH=%PROJECT_ROOT%ffmpeg\bin\ffmpeg.exe"

:: 3. 检查核心文件是否存在
if not exist "%PYTHON_EXE%" (
    echo 【错误】未找到Python解释器！请检查 python 文件夹是否完整。
    pause
    exit /b 1
)
if not exist "%RUN_SCRIPT%" (
    echo 【错误】未找到项目入口脚本！请检查 src 文件夹是否完整。
    pause
    exit /b 1
)
if not exist "%FFMPEG_PATH%" (
    echo 【错误】未找到FFmpeg！请检查 ffmpeg\bin\ffmpeg.exe 是否存在。
    pause
    exit /b 1
)

:: 4. 启动项目（传递FFMPEG路径环境变量）
set "FFMPEG_EXE=%FFMPEG_PATH%"
"%PYTHON_EXE%" "%RUN_SCRIPT%"

:: 5. 防止窗口关闭
echo.
echo 服务已停止，按任意键关闭窗口...
pause > nul
