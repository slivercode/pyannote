#!/usr/bin/env python3
"""
综合验证音视频字幕同步
检查TTS配音后的音频、视频、字幕是否正确同步
"""

import sys
import re
from pathlib import Path


def get_audio_duration(audio_path):
    """获取音频时长（使用pydub）"""
    try:
        from pydub import AudioSegment
        audio = AudioSegment.from_file(audio_path)
        return len(audio) / 1000.0  # 转换为秒
    except Exception as e:
        print(f"⚠️ 无法获取音频时长: {e}")
        return None


def get_video_duration(video_path):
    """获取视频时长（使用FFmpeg）"""
    try:
        import subprocess
        
        cmd = [
            "ffmpeg",
            "-i", str(video_path),
            "-hide_banner"
        ]
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='ignore'
        )
        
        # FFmpeg的信息在stderr中
        info_text = result.stderr
        
        # 提取时长
        duration_match = re.search(r"Duration: (\d{2}):(\d{2}):(\d{2}\.\d{2})", info_text)
        if duration_match:
            h, m, s = duration_match.groups()
            duration_seconds = int(h) * 3600 + int(m) * 60 + float(s)
            return duration_seconds
        else:
            print(f"⚠️ 无法解析视频时长")
            return None
            
    except Exception as e:
        print(f"⚠️ 获取视频时长失败: {e}")
        return None


def get_subtitle_duration(subtitle_path):
    """获取字幕总时长"""
    try:
        with open(subtitle_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 找到所有时间戳
        pattern = r'(\d{2}):(\d{2}):(\d{2}),(\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2}),(\d{3})'
        matches = re.findall(pattern, content)
        
        if not matches:
            return None
        
        # 获取最后一个字幕的结束时间
        last_match = matches[-1]
        end_h, end_m, end_s, end_ms = map(int, last_match[4:])
        total_seconds = end_h * 3600 + end_m * 60 + end_s + end_ms / 1000.0
        
        return total_seconds
        
    except Exception as e:
        print(f"⚠️ 获取字幕时长失败: {e}")
        return None


def parse_subtitle_at_time(subtitle_path, time_seconds):
    """获取指定时间点的字幕内容"""
    try:
        with open(subtitle_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        blocks = re.split(r'\n\n+', content.strip())
        
        for block in blocks:
            lines = block.strip().split('\n')
            if len(lines) >= 3:
                # 解析时间轴
                time_line = lines[1]
                match = re.match(
                    r'(\d{2}):(\d{2}):(\d{2}),(\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2}),(\d{3})',
                    time_line
                )
                if match:
                    start_h, start_m, start_s, start_ms = map(int, match.groups()[:4])
                    end_h, end_m, end_s, end_ms = map(int, match.groups()[4:])
                    
                    start_seconds = start_h * 3600 + start_m * 60 + start_s + start_ms / 1000.0
                    end_seconds = end_h * 3600 + end_m * 60 + end_s + end_ms / 1000.0
                    
                    if start_seconds <= time_seconds <= end_seconds:
                        text = '\n'.join(lines[2:])
                        return text[:50] + "..." if len(text) > 50 else text
        
        return "[无字幕]"
        
    except Exception as e:
        return f"[错误: {e}]"


def verify_sync(video_path=None, audio_path=None, subtitle_path=None):
    """验证音视频字幕同步"""
    print("🔍 综合同步验证")
    print("="*60)
    
    # 检查文件是否存在
    files_exist = {}
    if video_path:
        files_exist['video'] = Path(video_path).exists()
    if audio_path:
        files_exist['audio'] = Path(audio_path).exists()
    if subtitle_path:
        files_exist['subtitle'] = Path(subtitle_path).exists()
    
    print(f"\n📁 文件检查:")
    if video_path:
        status = "✅" if files_exist['video'] else "❌"
        print(f"   {status} 视频: {video_path}")
    if audio_path:
        status = "✅" if files_exist['audio'] else "❌"
        print(f"   {status} 音频: {audio_path}")
    if subtitle_path:
        status = "✅" if files_exist['subtitle'] else "❌"
        print(f"   {status} 字幕: {subtitle_path}")
    
    # 如果有文件不存在，提前返回
    if not all(files_exist.values()):
        print(f"\n❌ 部分文件不存在，无法继续验证")
        return
    
    # 1. 获取各个时长
    durations = {}
    
    if video_path and files_exist.get('video'):
        print(f"\n📹 获取视频时长...")
        durations['video'] = get_video_duration(video_path)
    
    if audio_path and files_exist.get('audio'):
        print(f"🎵 获取音频时长...")
        durations['audio'] = get_audio_duration(audio_path)
    
    if subtitle_path and files_exist.get('subtitle'):
        print(f"📝 获取字幕时长...")
        durations['subtitle'] = get_subtitle_duration(subtitle_path)
    
    # 2. 显示时长对比
    print(f"\n📊 时长对比:")
    print("-"*60)
    
    if durations.get('video') is not None:
        print(f"   视频: {durations['video']:.2f}秒")
    if durations.get('audio') is not None:
        print(f"   音频: {durations['audio']:.2f}秒")
    if durations.get('subtitle') is not None:
        print(f"   字幕: {durations['subtitle']:.2f}秒")
    
    # 3. 检查差异
    if len(durations) >= 2:
        max_duration = max(d for d in durations.values() if d is not None)
        min_duration = min(d for d in durations.values() if d is not None)
        
        print(f"\n⚖️ 差异分析:")
        print("-"*60)
        print(f"   最长: {max_duration:.2f}秒")
        print(f"   最短: {min_duration:.2f}秒")
        print(f"   差异: {max_duration - min_duration:.2f}秒")
        
        if max_duration - min_duration > 1.0:
            print(f"   ⚠️ 时长差异过大，可能导致不同步")
        else:
            print(f"   ✅ 时长差异可接受")
        
        # 详细对比
        if durations.get('video') and durations.get('audio'):
            diff = abs(durations['video'] - durations['audio'])
            print(f"\n   视频 vs 音频: {diff:.2f}秒差异")
            if diff > 0.5:
                if durations['video'] > durations['audio']:
                    print(f"      ⚠️ 视频比音频长，可能需要裁剪视频")
                else:
                    print(f"      ⚠️ 音频比视频长，视频应该被慢放")
        
        if durations.get('audio') and durations.get('subtitle'):
            diff = abs(durations['audio'] - durations['subtitle'])
            print(f"\n   音频 vs 字幕: {diff:.2f}秒差异")
            if diff > 0.5:
                if durations['audio'] > durations['subtitle']:
                    print(f"      ⚠️ 音频比字幕长，字幕可能被压缩了")
                else:
                    print(f"      ⚠️ 字幕比音频长，可能有过多静音间隙")
        
        if durations.get('video') and durations.get('subtitle'):
            diff = abs(durations['video'] - durations['subtitle'])
            print(f"\n   视频 vs 字幕: {diff:.2f}秒差异")
            if diff > 0.5:
                if durations['video'] > durations['subtitle']:
                    print(f"      ⚠️ 视频比字幕长")
                else:
                    print(f"      ⚠️ 字幕比视频长，字幕时间轴可能未调整")
    
    # 4. 抽样检查关键时间点
    if subtitle_path and files_exist.get('subtitle'):
        print(f"\n🎯 关键时间点检查:")
        print("-"*60)
        
        min_dur = min(d for d in durations.values() if d is not None)
        check_points = [0, 10, 30, 60, 120]  # 检查0秒、10秒、30秒、60秒、120秒
        
        for t in check_points:
            if t < min_dur:
                subtitle_at_t = parse_subtitle_at_time(subtitle_path, t)
                print(f"   {t:3d}秒: {subtitle_at_t}")
    
    # 5. 建议
    print(f"\n💡 建议:")
    print("-"*60)
    
    suggestions = []
    
    if durations.get('video') and durations.get('audio'):
        if abs(durations['video'] - durations['audio']) > 0.5:
            suggestions.append("视频和音频时长不匹配")
            if durations['audio'] > durations['video']:
                suggestions.append("  → 使用视频合并功能，系统会自动慢放视频以匹配音频")
            else:
                suggestions.append("  → 检查音频是否完整生成")
    
    if durations.get('audio') and durations.get('subtitle'):
        if abs(durations['audio'] - durations['subtitle']) > 0.5:
            suggestions.append("音频和字幕时长不匹配")
            if durations['subtitle'] < durations['audio']:
                suggestions.append("  → 字幕可能被压缩了，建议关闭'保持SRT总时长'")
            else:
                suggestions.append("  → 字幕可能有过多静音间隙，建议启用'移除静音间隙'")
    
    if durations.get('video') and durations.get('subtitle'):
        if abs(durations['video'] - durations['subtitle']) > 0.5:
            suggestions.append("视频和字幕时长不匹配")
            if durations['video'] > durations['subtitle']:
                suggestions.append("  → 视频被慢放后，字幕时间轴也需要相应调整")
                suggestions.append("  → 使用视频合并功能会自动调整字幕时间轴")
    
    if suggestions:
        for suggestion in suggestions:
            print(f"   {suggestion}")
    else:
        print(f"   ✅ 所有时长匹配良好，未发现明显问题")
    
    # 6. 诊断命令
    print(f"\n🔧 进一步诊断:")
    print("-"*60)
    if subtitle_path and audio_path:
        print(f"   运行以下命令进行详细诊断:")
        print(f"   python diagnose_tts_timeline.py {subtitle_path} --audio {audio_path}")


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='综合验证音视频字幕同步')
    parser.add_argument('--video', help='视频文件路径（可选）')
    parser.add_argument('--audio', help='音频文件路径（可选）')
    parser.add_argument('--subtitle', help='字幕文件路径（可选）')
    
    args = parser.parse_args()
    
    # 至少需要提供一个文件
    if not any([args.video, args.audio, args.subtitle]):
        print("错误：至少需要提供一个文件路径")
        print("\n使用方法:")
        print("  python verify_sync.py --video <视频> --audio <音频> --subtitle <字幕>")
        print("\n示例:")
        print("  python verify_sync.py --audio output/dubbing_result.wav --subtitle output/updated_subtitles.srt")
        print("  python verify_sync.py --video output/final_video.mp4 --audio output/dubbing_result.wav --subtitle output/updated_subtitles.srt")
        return
    
    verify_sync(args.video, args.audio, args.subtitle)


if __name__ == "__main__":
    # 如果没有命令行参数，使用默认路径
    if len(sys.argv) == 1:
        print("使用方法:")
        print("  python verify_sync.py --video <视频> --audio <音频> --subtitle <字幕>")
        print("\n示例:")
        print("  python verify_sync.py --audio output/dubbing_result.wav --subtitle output/updated_subtitles.srt")
        print("  python verify_sync.py --video output/final_video.mp4 --audio output/dubbing_result.wav --subtitle output/updated_subtitles.srt")
        print("\n或者直接修改下面的路径进行测试:")
        
        # 默认路径（用户可以修改）
        video_path = "output/final_video.mp4"
        audio_path = "output/dubbing_result.wav"
        subtitle_path = "output/updated_subtitles.srt"
        
        # 检查哪些文件存在
        existing_files = {}
        if Path(video_path).exists():
            existing_files['video'] = video_path
        if Path(audio_path).exists():
            existing_files['audio'] = audio_path
        if Path(subtitle_path).exists():
            existing_files['subtitle'] = subtitle_path
        
        if existing_files:
            print(f"\n找到以下文件，开始验证:")
            verify_sync(
                existing_files.get('video'),
                existing_files.get('audio'),
                existing_files.get('subtitle')
            )
        else:
            print(f"\n❌ 默认路径下没有找到文件")
            print("请指定正确的文件路径")
    else:
        main()
