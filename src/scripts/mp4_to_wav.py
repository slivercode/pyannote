#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MP4/视频文件转换为WAV音频文件
支持批量转换和自定义参数
"""

import os
import sys
import argparse
import pathlib
import subprocess
from typing import Optional

# 添加当前脚本目录到 sys.path
current_script_dir = os.path.dirname(os.path.abspath(__file__))
if current_script_dir not in sys.path:
    sys.path.insert(0, current_script_dir)


def convert_video_to_wav(
    input_path: str,
    output_dir: str = "output",
    sample_rate: int = 16000,
    channels: int = 1
) -> str:
    """
    将视频文件转换为WAV音频文件
    
    Args:
        input_path: 输入视频文件路径
        output_dir: 输出目录
        sample_rate: 采样率（默认16000Hz）
        channels: 声道数（1=单声道，2=立体声）
    
    Returns:
        输出WAV文件的路径
    """
    print(f"PROGRESS:10%")
    
    # 清理路径中的不可见 Unicode 字符（如 \u202a, \u202c 等）
    import unicodedata
    input_path = ''.join(c for c in input_path if unicodedata.category(c)[0] != 'C' or c in '\r\n\t')
    output_dir = ''.join(c for c in output_dir if unicodedata.category(c)[0] != 'C' or c in '\r\n\t')
    
    # 去除首尾空格
    input_path = input_path.strip()
    output_dir = output_dir.strip()
    
    # 统一路径分隔符
    input_path = input_path.replace(os.sep, "/")
    if not os.path.isabs(output_dir):
        output_dir = os.path.abspath(output_dir).replace(os.sep, "/")
    else:
        output_dir = output_dir.replace(os.sep, "/")
    
    # 检查输入文件是否存在
    if not os.path.exists(input_path):
        raise FileNotFoundError(f"输入文件不存在：{input_path}")
    
    print(f"📹 输入文件：{input_path}")
    print(f"PROGRESS:20%")
    
    # 获取文件名（不含扩展名）
    base_name = os.path.splitext(os.path.basename(input_path))[0]
    
    # 创建输出目录
    os.makedirs(output_dir, exist_ok=True)
    
    # 生成输出文件路径
    output_path = os.path.join(output_dir, f"{base_name}.wav")
    output_path = output_path.replace(os.sep, "/")
    
    print(f"🎵 输出文件：{output_path}")
    print(f"⚙️  采样率：{sample_rate}Hz")
    print(f"⚙️  声道数：{channels}")
    print(f"PROGRESS:30%")
    
    # 转换为WAV
    print(f"\n🔄 开始转换...")
    try:
        # 使用 ffmpeg 直接转换
        env = os.environ.copy()
        env["LC_ALL"] = "en_US.UTF-8"
        env["LANG"] = "en_US.UTF-8"
        
        cmd = [
            "ffmpeg",
            "-y",  # 覆盖输出文件
            "-threads", "0",  # 使用所有CPU核心
            "-i", input_path,  # 输入文件
            "-ac", str(channels),  # 声道数
            "-ar", str(sample_rate),  # 采样率
            "-sample_fmt", "s16",  # 16位采样
            output_path  # 输出文件
        ]
        
        print(f"🔧 执行命令：{' '.join(cmd)}")
        print(f"PROGRESS:40%")
        
        # 执行 ffmpeg 命令
        result = subprocess.run(
            cmd,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace"
        )
        
        print(f"PROGRESS:80%")
        
        if result.returncode != 0:
            error_msg = result.stderr if result.stderr else "未知错误"
            raise RuntimeError(f"FFmpeg 转换失败：{error_msg}")
        
        # 检查输出文件是否存在
        if not os.path.exists(output_path):
            raise FileNotFoundError(f"输出文件未生成：{output_path}")
        
        print(f"PROGRESS:90%")
        print(f"\n✅ 转换成功！")
        print(f"📁 输出文件：{output_path}")
        print(f"result_wav_file：{output_path}")
        print(f"PROGRESS:100%")
        
        return output_path
        
    except Exception as e:
        print(f"\n❌ 转换失败：{str(e)}")
        raise


def batch_convert(
    input_dir: str,
    output_dir: str = "output",
    sample_rate: int = 16000,
    channels: int = 1,
    extensions: tuple = ('.mp4', '.avi', '.mov', '.mkv', '.flv', '.wmv')
) -> list:
    """
    批量转换目录中的视频文件为WAV
    
    Args:
        input_dir: 输入目录
        output_dir: 输出目录
        sample_rate: 采样率
        channels: 声道数
        extensions: 支持的视频文件扩展名
    
    Returns:
        转换成功的文件列表
    """
    if not os.path.exists(input_dir):
        raise FileNotFoundError(f"输入目录不存在：{input_dir}")
    
    # 查找所有视频文件
    video_files = []
    for root, dirs, files in os.walk(input_dir):
        for file in files:
            if file.lower().endswith(extensions):
                video_files.append(os.path.join(root, file))
    
    if not video_files:
        print(f"⚠️  在 {input_dir} 中未找到视频文件")
        return []
    
    print(f"📂 找到 {len(video_files)} 个视频文件")
    
    # 批量转换
    converted_files = []
    for i, video_file in enumerate(video_files, 1):
        print(f"\n[{i}/{len(video_files)}] 处理：{os.path.basename(video_file)}")
        try:
            output_path = convert_video_to_wav(
                video_file,
                output_dir,
                sample_rate,
                channels
            )
            converted_files.append(output_path)
        except Exception as e:
            print(f"❌ 转换失败：{e}")
            continue
    
    print(f"\n✅ 批量转换完成！成功：{len(converted_files)}/{len(video_files)}")
    return converted_files


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="将MP4/视频文件转换为WAV音频文件",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例用法:
  # 转换单个文件
  python mp4_to_wav.py --input video.mp4
  
  # 指定输出目录和采样率
  python mp4_to_wav.py --input video.mp4 --output-dir ./wav --sample-rate 44100
  
  # 批量转换目录中的所有视频
  python mp4_to_wav.py --input-dir ./videos --output-dir ./wav
        """
    )
    
    # 输入参数
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument(
        "--input",
        type=str,
        help="输入视频文件路径"
    )
    input_group.add_argument(
        "--input-dir",
        type=str,
        help="输入目录（批量转换）"
    )
    
    # 输出参数
    parser.add_argument(
        "--output-dir",
        type=str,
        default="output",
        help="输出目录（默认：output）"
    )
    
    # 音频参数
    parser.add_argument(
        "--sample-rate",
        type=int,
        default=16000,
        help="采样率（默认：16000Hz）"
    )
    parser.add_argument(
        "--channels",
        type=int,
        default=1,
        choices=[1, 2],
        help="声道数（1=单声道，2=立体声，默认：1）"
    )
    
    args = parser.parse_args()
    
    try:
        if args.input:
            # 单文件转换
            convert_video_to_wav(
                args.input,
                args.output_dir,
                args.sample_rate,
                args.channels
            )
        else:
            # 批量转换
            batch_convert(
                args.input_dir,
                args.output_dir,
                args.sample_rate,
                args.channels
            )
    except Exception as e:
        print(f"\n❌ 执行失败：{str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
