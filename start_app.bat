@echo off
chcp 65001 > nul & rem 解决中文乱码问题（使用rem作为注释符号）

echo ==============================================
echo 重构后应用 - 启动中...
echo 基于FastAPI的Web服务版本
echo ==============================================

:: 1. 动态获取当前项目根目录（兼容任意解压位置）
set "PROJECT_ROOT=%~dp0"

:: 2. 定位关键路径（使用双引号避免路径含空格/中文的问题）
set "VENV_ACTIVATE=%PROJECT_ROOT%.venv\Scripts\activate.bat"
set "VENV_PYTHON=%PROJECT_ROOT%.venv\Scripts\python.exe"
set "RUN_SCRIPT=%PROJECT_ROOT%start_app.py"
set "FFMPEG_PATH=%PROJECT_ROOT%ffmpeg\bin\ffmpeg.exe"

:: 3. 检查核心文件是否存在
if not exist "%VENV_ACTIVATE%" (
    echo 【错误】未找到虚拟环境！请检查 .venv 文件夹是否完整。
    echo 请先运行以下命令创建虚拟环境：
    echo python -m venv .venv
    echo .venv\Scripts\activate
    echo pip install -r requirements.txt
    pause
    exit /b 1
)
if not exist "%VENV_PYTHON%" (
    echo 【错误】虚拟环境中未找到Python解释器！请重新安装虚拟环境。
    pause
    exit /b 1
)
if not exist "%RUN_SCRIPT%" (
    echo 【错误】未找到应用启动脚本！请检查 start_app.py 是否存在。
    pause
    exit /b 1
)
if not exist "%FFMPEG_PATH%" (
    echo 【错误】未找到FFmpeg！请检查 ffmpeg\bin\ffmpeg.exe 是否存在。
    pause
    exit /b 1
)

:: 4. 激活虚拟环境并启动应用
echo 正在激活虚拟环境...
call "%VENV_ACTIVATE%"
if errorlevel 1 (
    echo 【错误】虚拟环境激活失败！
    pause
    exit /b 1
)

echo 虚拟环境已激活
echo 正在启动Web服务，请稍候...
echo 服务启动后将自动打开浏览器

:: 设置FFMPEG路径环境变量
set "FFMPEG_EXE=%FFMPEG_PATH%"

:: 使用虚拟环境中的Python运行应用
"%VENV_PYTHON%" "%RUN_SCRIPT%"

:: 5. 防止窗口关闭
echo.
echo Web服务已停止，按任意键关闭窗口...
pause > nul