#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MP4/视频文件提取环境声音（背景音）

从视频中提取音频，然后使用AI模型分离出环境声音（去除人声）

支持的分离引擎：
1. Demucs (推荐，质量最好)
2. Spleeter (快速)
3. FFmpeg (简单滤波，质量较差)
"""

import os
import sys
import argparse
import subprocess
from pathlib import Path
from typing import Optional, Literal

# 添加当前脚本目录到 sys.path
current_script_dir = os.path.dirname(os.path.abspath(__file__))
if current_script_dir not in sys.path:
    sys.path.insert(0, current_script_dir)


class BackgroundAudioExtractor:
    """从视频中提取环境声音（背景音）"""
    
    def __init__(
        self,
        engine: Literal["demucs", "spleeter", "ffmpeg"] = "demucs",
        model: str = "htdemucs",
        device: str = "cpu",
        ffmpeg_path: str = None
    ):
        """
        初始化提取器
        
        Args:
            engine: 分离引擎 (demucs/spleeter/ffmpeg)
            model: Demucs模型名称 (htdemucs, htdemucs_ft, mdx_extra)
            device: 计算设备 (cpu/cuda)
            ffmpeg_path: FFmpeg路径
        """
        self.engine = engine
        self.model = model
        self.device = device
        self.ffmpeg_path = ffmpeg_path or self._detect_ffmpeg()
        
        self._check_dependencies()
    
    def _detect_ffmpeg(self) -> str:
        """自动检测FFmpeg路径"""
        import shutil
        import platform
        
        if platform.system() == "Windows":
            # 尝试多个可能的路径
            possible_paths = [
                Path("ffmpeg/bin/ffmpeg.exe"),
                Path("../ffmpeg/bin/ffmpeg.exe"),
                Path("../../ffmpeg/bin/ffmpeg.exe"),
            ]
            for path in possible_paths:
                if path.exists():
                    return str(path.resolve())
        
        system_ffmpeg = shutil.which("ffmpeg")
        if system_ffmpeg:
            return system_ffmpeg
        
        # 最后的备选方案
        return "ffmpeg"
    
    def _check_dependencies(self):
        """检查依赖"""
        if self.engine == "demucs":
            try:
                import demucs
                print(f"✅ Demucs 已安装: {demucs.__version__}")
            except ImportError:
                print(f"⚠️  Demucs 未安装，请运行: pip install demucs")
                print(f"   或使用 engine='ffmpeg' 作为备选")
        elif self.engine == "spleeter":
            try:
                import spleeter
                print(f"✅ Spleeter 已安装")
            except ImportError:
                print(f"⚠️  Spleeter 未安装，请运行: pip install spleeter")

    def extract_background_audio(
        self,
        input_path: str,
        output_dir: str = "output",
        sample_rate: int = 44100,
        channels: int = 2,
        keep_temp: bool = False
    ) -> str:
        """
        从视频中提取环境声音（背景音）
        
        Args:
            input_path: 输入视频文件路径
            output_dir: 输出目录
            sample_rate: 采样率（默认44100Hz）
            channels: 声道数（默认2=立体声）
            keep_temp: 是否保留临时文件
        
        Returns:
            背景音WAV文件路径
        """
        print(f"PROGRESS:5%")
        
        # 清理路径
        import unicodedata
        input_path = ''.join(c for c in input_path if unicodedata.category(c)[0] != 'C' or c in '\r\n\t').strip()
        output_dir = ''.join(c for c in output_dir if unicodedata.category(c)[0] != 'C' or c in '\r\n\t').strip()
        
        input_path = input_path.replace(os.sep, "/")
        output_dir = os.path.abspath(output_dir).replace(os.sep, "/")
        
        if not os.path.exists(input_path):
            raise FileNotFoundError(f"输入文件不存在：{input_path}")
        
        base_name = os.path.splitext(os.path.basename(input_path))[0]
        os.makedirs(output_dir, exist_ok=True)
        
        print(f"\n{'='*60}")
        print(f"🎬 从视频提取环境声音")
        print(f"{'='*60}")
        print(f"📹 输入: {input_path}")
        print(f"📁 输出: {output_dir}")
        print(f"🔧 引擎: {self.engine}")
        print(f"PROGRESS:10%")
        
        # Step 1: 从视频提取完整音频
        temp_audio = os.path.join(output_dir, f"{base_name}_temp_full_audio.wav")
        self._extract_audio_from_video(input_path, temp_audio, sample_rate, channels)
        print(f"PROGRESS:30%")
        
        # Step 2: 分离背景音
        background_path = os.path.join(output_dir, f"{base_name}_background.wav")
        
        if self.engine == "demucs":
            background_path = self._separate_with_demucs(temp_audio, output_dir, base_name)
        elif self.engine == "spleeter":
            background_path = self._separate_with_spleeter(temp_audio, output_dir, base_name)
        else:
            background_path = self._separate_with_ffmpeg(temp_audio, output_dir, base_name)
        
        print(f"PROGRESS:90%")
        
        # 清理临时文件
        if not keep_temp and os.path.exists(temp_audio):
            os.remove(temp_audio)
            print(f"🗑️  已清理临时文件")
        
        print(f"\n✅ 环境声音提取完成！")
        print(f"📁 输出文件: {background_path}")
        print(f"result_background_audio: {background_path}")
        print(f"PROGRESS:100%")
        
        return background_path
    
    def _extract_audio_from_video(
        self,
        video_path: str,
        output_path: str,
        sample_rate: int,
        channels: int
    ):
        """从视频提取音频"""
        print(f"\n📹 Step 1: 提取视频音轨...")
        
        env = os.environ.copy()
        env["LC_ALL"] = "en_US.UTF-8"
        
        cmd = [
            self.ffmpeg_path, "-y",
            "-i", video_path,
            "-vn",
            "-acodec", "pcm_s16le",
            "-ar", str(sample_rate),
            "-ac", str(channels),
            output_path
        ]
        
        result = subprocess.run(cmd, env=env, capture_output=True, text=True, errors="replace")
        
        if result.returncode != 0:
            raise RuntimeError(f"音频提取失败: {result.stderr}")
        
        print(f"✅ 音频提取完成: {output_path}")

    def _separate_with_demucs(self, audio_path: str, output_dir: str, base_name: str) -> str:
        """使用Demucs分离背景音（推荐）"""
        print(f"\n🎵 Step 2: 使用 Demucs 分离背景音...")
        print(f"   模型: {self.model}")
        print(f"   设备: {self.device}")
        print(f"PROGRESS:40%")
        
        try:
            # 使用当前 Python 解释器，确保使用正确的虚拟环境
            cmd = [
                sys.executable, "-m", "demucs.separate",
                "-n", self.model,
                "-d", self.device,
                "-o", output_dir,
                "--two-stems", "vocals",  # 只分离人声和其他，效果更好
                "--clip-mode", "rescale",  # 防止削波
                audio_path
            ]
            
            # 设置环境变量，将 FFmpeg 添加到 PATH
            env = os.environ.copy()
            ffmpeg_dir = Path(self.ffmpeg_path).parent
            if ffmpeg_dir.exists():
                env["PATH"] = str(ffmpeg_dir) + os.pathsep + env.get("PATH", "")
                print(f"   FFmpeg路径: {ffmpeg_dir}")
            
            print(f"   执行命令: {' '.join(cmd)}")
            result = subprocess.run(cmd, capture_output=True, text=True, errors="replace", env=env)
            
            if result.returncode != 0:
                print(f"   stdout: {result.stdout}")
                print(f"   stderr: {result.stderr}")
                raise RuntimeError(f"Demucs 分离失败: {result.stdout or result.stderr}")
            
            print(f"PROGRESS:70%")
            
            # 使用 --two-stems 时，输出是 vocals.wav 和 no_vocals.wav
            temp_name = os.path.splitext(os.path.basename(audio_path))[0]
            model_output_dir = Path(output_dir) / self.model / temp_name
            
            background_path = os.path.join(output_dir, f"{base_name}_background.wav")
            
            # 优先使用 no_vocals.wav（这就是背景音）
            no_vocals = model_output_dir / "no_vocals.wav"
            if no_vocals.exists():
                import shutil
                shutil.copy(str(no_vocals), background_path)
                print(f"✅ 使用 no_vocals.wav 作为背景音")
            else:
                # 回退到合并 drums + bass + other
                self._merge_background_tracks(model_output_dir, background_path)
            
            print(f"✅ 背景音分离完成")
            return background_path
            
        except Exception as e:
            print(f"❌ Demucs 失败: {e}")
            print(f"⚠️  回退到 FFmpeg 简单分离...")
            return self._separate_with_ffmpeg(audio_path, output_dir, base_name)
    
    def _merge_background_tracks(self, tracks_dir: Path, output_path: str):
        """合并背景音轨（drums + bass + other）"""
        drums = tracks_dir / "drums.wav"
        bass = tracks_dir / "bass.wav"
        other = tracks_dir / "other.wav"
        
        tracks = [str(t) for t in [drums, bass, other] if t.exists()]
        
        if not tracks:
            raise FileNotFoundError(f"未找到背景音轨: {tracks_dir}")
        
        cmd = [self.ffmpeg_path, "-y"]
        for track in tracks:
            cmd.extend(["-i", track])
        
        if len(tracks) == 1:
            cmd.extend(["-c:a", "pcm_s16le", output_path])
        else:
            filter_complex = f"amix=inputs={len(tracks)}:duration=longest"
            cmd.extend(["-filter_complex", filter_complex, "-c:a", "pcm_s16le", output_path])
        
        subprocess.run(cmd, check=True, capture_output=True)
    
    def _separate_with_spleeter(self, audio_path: str, output_dir: str, base_name: str) -> str:
        """使用Spleeter分离背景音"""
        print(f"\n🎵 Step 2: 使用 Spleeter 分离背景音...")
        print(f"PROGRESS:40%")
        
        try:
            from spleeter.separator import Separator
            
            separator = Separator('spleeter:2stems')
            separator.separate_to_file(audio_path, output_dir)
            
            print(f"PROGRESS:70%")
            
            temp_name = os.path.splitext(os.path.basename(audio_path))[0]
            accompaniment = Path(output_dir) / temp_name / "accompaniment.wav"
            
            if accompaniment.exists():
                background_path = os.path.join(output_dir, f"{base_name}_background.wav")
                import shutil
                shutil.copy(str(accompaniment), background_path)
                print(f"✅ 背景音分离完成")
                return background_path
            else:
                raise FileNotFoundError("Spleeter 输出文件未找到")
                
        except Exception as e:
            print(f"❌ Spleeter 失败: {e}")
            print(f"⚠️  回退到 FFmpeg 简单分离...")
            return self._separate_with_ffmpeg(audio_path, output_dir, base_name)
    
    def _separate_with_ffmpeg(self, audio_path: str, output_dir: str, base_name: str) -> str:
        """使用FFmpeg提取背景音（中置声道消除法）"""
        print(f"\n🎵 Step 2: 使用 FFmpeg 消除人声...")
        print(f"⚠️  注意: FFmpeg 分离质量一般，建议安装 Demucs 获得更好效果")
        print(f"PROGRESS:40%")
        
        background_path = os.path.join(output_dir, f"{base_name}_background.wav")
        
        # 方案1: 中置声道消除（最有效的 FFmpeg 人声消除方法）
        # 原理: 人声通常混音在立体声中央，左右声道相减可以消除中央的人声
        # pan=stereo|c0=c0-c1|c1=c1-c0 表示: 左声道=原左-原右, 右声道=原右-原左
        cmd = [
            self.ffmpeg_path, "-y",
            "-i", audio_path,
            "-af", "pan=stereo|c0=c0-c1|c1=c1-c0,volume=1.5",
            "-c:a", "pcm_s16le",
            "-ar", "44100",
            background_path
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, errors="replace")
        
        print(f"PROGRESS:70%")
        
        if result.returncode != 0:
            print(f"⚠️  方案1失败，尝试方案2...")
            # 方案2: 使用 extrastereo 增强立体声差异 + 中置消除
            cmd_fallback = [
                self.ffmpeg_path, "-y",
                "-i", audio_path,
                "-af", "extrastereo=m=2.5,pan=stereo|c0=c0-c1|c1=c1-c0,volume=1.2",
                "-c:a", "pcm_s16le",
                "-ar", "44100",
                background_path
            ]
            result2 = subprocess.run(cmd_fallback, capture_output=True, text=True, errors="replace")
            
            if result2.returncode != 0:
                print(f"⚠️  方案2失败，尝试方案3...")
                # 方案3: 频率滤波（去除人声主要频段 300Hz-3000Hz）
                cmd_freq = [
                    self.ffmpeg_path, "-y",
                    "-i", audio_path,
                    "-af", "highpass=f=3500,lowpass=f=15000,volume=2",
                    "-c:a", "pcm_s16le",
                    "-ar", "44100",
                    background_path
                ]
                subprocess.run(cmd_freq, capture_output=True)
        
        print(f"✅ 背景音提取完成")
        return background_path


def extract_background_audio(
    input_path: str,
    output_dir: str = "output",
    engine: str = "demucs",
    model: str = "htdemucs",
    device: str = "cpu",
    sample_rate: int = 44100,
    channels: int = 2,
    keep_temp: bool = False
) -> str:
    """
    便捷函数：从视频提取环境声音
    
    Args:
        input_path: 输入视频路径
        output_dir: 输出目录
        engine: 分离引擎 (demucs/spleeter/ffmpeg)
        model: Demucs模型
        device: 计算设备 (cpu/cuda)
        sample_rate: 采样率
        channels: 声道数
        keep_temp: 保留临时文件
    
    Returns:
        背景音文件路径
    """
    extractor = BackgroundAudioExtractor(
        engine=engine,
        model=model,
        device=device
    )
    return extractor.extract_background_audio(
        input_path=input_path,
        output_dir=output_dir,
        sample_rate=sample_rate,
        channels=channels,
        keep_temp=keep_temp
    )


def batch_extract_background(
    input_dir: str,
    output_dir: str = "output",
    engine: str = "demucs",
    model: str = "htdemucs",
    device: str = "cpu",
    extensions: tuple = ('.mp4', '.avi', '.mov', '.mkv', '.flv', '.wmv')
) -> list:
    """
    批量从视频提取环境声音
    
    Args:
        input_dir: 输入目录
        output_dir: 输出目录
        engine: 分离引擎
        model: Demucs模型
        device: 计算设备
        extensions: 支持的视频扩展名
    
    Returns:
        提取成功的文件列表
    """
    if not os.path.exists(input_dir):
        raise FileNotFoundError(f"输入目录不存在：{input_dir}")
    
    video_files = []
    for root, dirs, files in os.walk(input_dir):
        for file in files:
            if file.lower().endswith(extensions):
                video_files.append(os.path.join(root, file))
    
    if not video_files:
        print(f"⚠️  在 {input_dir} 中未找到视频文件")
        return []
    
    print(f"📂 找到 {len(video_files)} 个视频文件")
    
    extractor = BackgroundAudioExtractor(engine=engine, model=model, device=device)
    
    extracted_files = []
    for i, video_file in enumerate(video_files, 1):
        print(f"\n[{i}/{len(video_files)}] 处理：{os.path.basename(video_file)}")
        try:
            output_path = extractor.extract_background_audio(video_file, output_dir)
            extracted_files.append(output_path)
        except Exception as e:
            print(f"❌ 提取失败：{e}")
            continue
    
    print(f"\n✅ 批量提取完成！成功：{len(extracted_files)}/{len(video_files)}")
    return extracted_files


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="从MP4/视频文件提取环境声音（背景音）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例用法:
  # 使用Demucs提取（推荐，质量最好）
  python mp4_to_background_audio.py --input video.mp4
  
  # 使用GPU加速
  python mp4_to_background_audio.py --input video.mp4 --device cuda
  
  # 使用FFmpeg快速提取（质量较差）
  python mp4_to_background_audio.py --input video.mp4 --engine ffmpeg
  
  # 批量提取
  python mp4_to_background_audio.py --input-dir ./videos --output-dir ./background
  
  # 保留临时文件
  python mp4_to_background_audio.py --input video.mp4 --keep-temp

分离引擎说明:
  demucs  - AI模型，质量最好，需要安装: pip install demucs
  spleeter - AI模型，速度较快，需要安装: pip install spleeter
  ffmpeg  - 简单滤波，质量较差，无需额外安装
        """
    )
    
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument("--input", type=str, help="输入视频文件路径")
    input_group.add_argument("--input-dir", type=str, help="输入目录（批量提取）")
    
    parser.add_argument("--output-dir", type=str, default="output", help="输出目录（默认：output）")
    parser.add_argument("--engine", type=str, default="demucs", choices=["demucs", "spleeter", "ffmpeg"],
                        help="分离引擎（默认：demucs）")
    parser.add_argument("--model", type=str, default="htdemucs", help="Demucs模型（默认：htdemucs）")
    parser.add_argument("--device", type=str, default="cpu", choices=["cpu", "cuda"],
                        help="计算设备（默认：cpu）")
    parser.add_argument("--sample-rate", type=int, default=44100, help="采样率（默认：44100Hz）")
    parser.add_argument("--channels", type=int, default=2, choices=[1, 2], help="声道数（默认：2）")
    parser.add_argument("--keep-temp", action="store_true", help="保留临时文件")
    parser.add_argument("--ffmpeg-path", type=str, default=None, help="FFmpeg可执行文件路径（可选）")
    
    args = parser.parse_args()
    
    try:
        if args.input:
            extractor = BackgroundAudioExtractor(
                engine=args.engine,
                model=args.model,
                device=args.device,
                ffmpeg_path=args.ffmpeg_path
            )
            extractor.extract_background_audio(
                input_path=args.input,
                output_dir=args.output_dir,
                sample_rate=args.sample_rate,
                channels=args.channels,
                keep_temp=args.keep_temp
            )
        else:
            batch_extract_background(
                input_dir=args.input_dir,
                output_dir=args.output_dir,
                engine=args.engine,
                model=args.model,
                device=args.device
            )
    except Exception as e:
        print(f"\n❌ 执行失败：{str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
