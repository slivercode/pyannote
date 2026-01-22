@echo off
chcp 65001 >nul
echo ============================================================
echo PaddleOCR oneDNN 错误修复脚本
echo ============================================================
echo.
echo 问题描述：
echo   ConvertPirAttribute2RuntimeAttribute not support
echo   [pir::ArrayAttribute^<pir::DoubleAttribute^>]
echo.
echo 这是PaddlePaddle 3.x版本与oneDNN的兼容性问题
echo.
echo ============================================================
echo 解决方案
echo ============================================================
echo.

echo 方案1: 降级到PaddlePaddle 2.6.1（推荐）
echo.
echo 正在卸载当前版本...
pip uninstall -y paddlepaddle paddlepaddle-gpu
echo.

echo 正在安装PaddlePaddle 2.6.1 GPU版本...
pip install paddlepaddle-gpu==2.6.1

if errorlevel 1 (
    echo.
    echo ❌ 安装失败，尝试使用国内镜像...
    pip install paddlepaddle-gpu==2.6.1 -i https://mirror.baidu.com/pypi/simple
)

echo.
echo ============================================================
echo 验证安装
echo ============================================================
echo.

python -c "import paddle; print('✅ PaddlePaddle版本:', paddle.__version__); print('✅ CUDA支持:', paddle.is_compiled_with_cuda())"

if errorlevel 1 (
    echo.
    echo ❌ 验证失败
    pause
    exit /b 1
)

echo.
echo ============================================================
echo 测试OCR功能
echo ============================================================
echo.

python test_paddleocr_gpu.py

echo.
echo ============================================================
echo 修复完成！
echo ============================================================
echo.
echo 📝 已安装：PaddlePaddle 2.6.1 GPU版本
echo 💡 此版本稳定且兼容性好，不会出现oneDNN错误
echo.
echo 🚀 现在可以正常使用OCR功能了
echo.

pause
