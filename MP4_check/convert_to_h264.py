#!/usr/bin/env python3
"""
将 HEVC (H.265) 视频转换为 H.264，以便 FFmpeg 切割和拼接

使用方法:
    python convert_to_h264.py 1.mp4
    python convert_to_h264.py 1.mp4 --output 1_h264.mp4
    python convert_to_h264.py 1.mp4 --fast  # 快速模式
"""

import subprocess
import sys
from pathlib import Path
import time

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent
FFMPEG_BIN = PROJECT_ROOT / "ffmpeg" / "bin" / "ffmpeg.exe"

def convert_to_h264(input_file: str, output_file: str = None, fast_mode: bool = False):
    """
    将视频转换为 H.264 编码
    
    Args:
        input_file: 输入文件路径
        output_file: 输出文件路径（可选）
        fast_mode: 是否使用快速模式
    """
    input_path = Path(input_file)
    
    if not input_path.exists():
        print(f"❌ 文件不存在: {input_path}")
        return False
    
    # 默认输出文件名
    if output_file is None:
        output_file = input_path.stem + "_h264" + input_path.suffix
    
    output_path = Path(output_file)
    
    print(f"{'='*60}")
    print(f"视频转换工具 - HEVC 转 H.264")
    print(f"{'='*60}\n")
    print(f"输入文件: {input_path}")
    print(f"输出文件: {output_path}")
    
    # 检查输入文件大小
    input_size = input_path.stat().st_size
    print(f"输入大小: {input_size / 1024 / 1024:.2f} MB")
    
    # 构建 FFmpeg 命令
    if fast_mode:
        # 快速模式：使用 ultrafast preset，质量稍低但速度快
        print(f"\n⚡ 使用快速模式（速度优先）")
        cmd = [
            str(FFMPEG_BIN),
            '-i', str(input_path),
            '-c:v', 'libx264',           # H.264 编码器
            '-preset', 'ultrafast',      # 最快速度
            '-crf', '23',                # 质量（23 = 中等质量）
            '-pix_fmt', 'yuv420p',       # 8-bit 像素格式
            '-c:a', 'copy',              # 音频直接复制
            '-movflags', '+faststart',   # 优化流媒体播放
            '-y',                        # 覆盖输出文件
            str(output_path)
        ]
    else:
        # 平衡模式：使用 fast preset，质量和速度平衡
        print(f"\n⚖️  使用平衡模式（质量和速度平衡）")
        cmd = [
            str(FFMPEG_BIN),
            '-i', str(input_path),
            '-c:v', 'libx264',           # H.264 编码器
            '-preset', 'fast',           # 快速预设
            '-crf', '18',                # 高质量（18 = 接近无损）
            '-pix_fmt', 'yuv420p',       # 8-bit 像素格式
            '-c:a', 'copy',              # 音频直接复制
            '-movflags', '+faststart',   # 优化流媒体播放
            '-y',                        # 覆盖输出文件
            str(output_path)
        ]
    
    print(f"\n🎬 开始转换...")
    print(f"命令: {' '.join([str(c) for c in cmd[:10]])} ...")
    
    # 执行转换
    start_time = time.time()
    
    try:
        # 使用 Popen 以便实时显示进度
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            encoding='utf-8',
            errors='replace'
        )
        
        # 读取输出
        last_progress = ""
        for line in process.stdout:
            # FFmpeg 的进度信息在 stderr，但我们重定向到了 stdout
            if 'frame=' in line or 'time=' in line:
                # 提取进度信息
                if 'time=' in line:
                    # 清除上一行
                    print(f"\r{' ' * len(last_progress)}\r", end='')
                    # 显示新进度
                    last_progress = line.strip()[:80]  # 限制长度
                    print(f"\r   {last_progress}", end='', flush=True)
        
        process.wait()
        print()  # 换行
        
        if process.returncode != 0:
            print(f"\n❌ 转换失败，返回码: {process.returncode}")
            return False
        
        # 转换成功
        elapsed_time = time.time() - start_time
        
        # 检查输出文件
        if not output_path.exists():
            print(f"\n❌ 输出文件未生成")
            return False
        
        output_size = output_path.stat().st_size
        
        print(f"\n{'='*60}")
        print(f"✅ 转换完成!")
        print(f"{'='*60}")
        print(f"输出文件: {output_path}")
        print(f"输出大小: {output_size / 1024 / 1024:.2f} MB")
        print(f"大小变化: {(output_size - input_size) / input_size * 100:+.1f}%")
        print(f"耗时: {elapsed_time:.1f} 秒")
        
        # 计算速度
        minutes = int(elapsed_time // 60)
        seconds = int(elapsed_time % 60)
        print(f"处理时间: {minutes}分{seconds}秒")
        
        print(f"\n💡 提示:")
        print(f"   现在可以使用 {output_path.name} 进行切割和拼接了")
        print(f"   原始文件 {input_path.name} 已保留")
        
        return True
        
    except KeyboardInterrupt:
        print(f"\n\n⚠️  用户中断")
        process.kill()
        return False
    except Exception as e:
        print(f"\n❌ 转换失败: {e}")
        return False

def main():
    if len(sys.argv) < 2:
        print("用法:")
        print("  python convert_to_h264.py <输入文件>")
        print("  python convert_to_h264.py <输入文件> --output <输出文件>")
        print("  python convert_to_h264.py <输入文件> --fast")
        print()
        print("示例:")
        print("  python convert_to_h264.py 1.mp4")
        print("  python convert_to_h264.py 1.mp4 --output 1_converted.mp4")
        print("  python convert_to_h264.py 1.mp4 --fast")
        sys.exit(1)
    
    # 检查 FFmpeg
    if not FFMPEG_BIN.exists():
        print(f"❌ FFmpeg 不存在: {FFMPEG_BIN}")
        sys.exit(1)
    
    input_file = sys.argv[1]
    output_file = None
    fast_mode = False
    
    # 解析参数
    i = 2
    while i < len(sys.argv):
        if sys.argv[i] == '--output' and i + 1 < len(sys.argv):
            output_file = sys.argv[i + 1]
            i += 2
        elif sys.argv[i] == '--fast':
            fast_mode = True
            i += 1
        else:
            i += 1
    
    # 执行转换
    success = convert_to_h264(input_file, output_file, fast_mode)
    
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
