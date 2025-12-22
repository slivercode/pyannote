#!/usr/bin/env python3
"""
诊断TTS配音时间轴问题
检查字幕、音频、视频的时间对齐情况
"""

import sys
from pathlib import Path
import re

def parse_srt(srt_path):
    """解析SRT文件"""
    with open(srt_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    subtitles = []
    blocks = re.split(r'\n\n+', content.strip())
    
    for block in blocks:
        lines = block.strip().split('\n')
        if len(lines) >= 3:
            # 解析时间轴
            time_line = lines[1]
            match = re.match(r'(\d{2}):(\d{2}):(\d{2}),(\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2}),(\d{3})', time_line)
            if match:
                start_h, start_m, start_s, start_ms = map(int, match.groups()[:4])
                end_h, end_m, end_s, end_ms = map(int, match.groups()[4:])
                
                start_total_ms = (start_h * 3600 + start_m * 60 + start_s) * 1000 + start_ms
                end_total_ms = (end_h * 3600 + end_m * 60 + end_s) * 1000 + end_ms
                
                text = '\n'.join(lines[2:])
                
                subtitles.append({
                    'index': len(subtitles) + 1,
                    'start_ms': start_total_ms,
                    'end_ms': end_total_ms,
                    'duration_ms': end_total_ms - start_total_ms,
                    'text': text
                })
    
    return subtitles


def get_audio_duration(audio_path):
    """获取音频时长（需要pydub）"""
    try:
        from pydub import AudioSegment
        audio = AudioSegment.from_file(audio_path)
        return len(audio)
    except Exception as e:
        print(f"⚠️ 无法获取音频时长: {e}")
        return None


def diagnose_timeline(srt_path, audio_path=None, video_path=None):
    """诊断时间轴问题"""
    print("🔍 TTS配音时间轴诊断")
    print("="*60)
    
    # 1. 解析字幕
    print(f"\n📝 解析字幕文件: {srt_path}")
    if not Path(srt_path).exists():
        print(f"❌ 字幕文件不存在: {srt_path}")
        return
    
    subtitles = parse_srt(srt_path)
    print(f"✅ 找到 {len(subtitles)} 条字幕")
    
    # 2. 分析字幕时间轴
    print(f"\n📊 字幕时间轴分析:")
    print("-"*60)
    
    if not subtitles:
        print("❌ 没有字幕数据")
        return
    
    total_subtitle_duration = sum(s['duration_ms'] for s in subtitles)
    total_timeline_duration = subtitles[-1]['end_ms']
    gaps_duration = total_timeline_duration - total_subtitle_duration
    
    print(f"字幕总数: {len(subtitles)}")
    print(f"字幕总时长: {total_subtitle_duration/1000:.2f}秒 ({total_subtitle_duration}ms)")
    print(f"时间轴总长: {total_timeline_duration/1000:.2f}秒 ({total_timeline_duration}ms)")
    print(f"间隙总时长: {gaps_duration/1000:.2f}秒 ({gaps_duration}ms)")
    
    # 3. 显示前5条字幕详情
    print(f"\n📋 前5条字幕详情:")
    print("-"*60)
    for i, sub in enumerate(subtitles[:5]):
        start_sec = sub['start_ms'] / 1000
        end_sec = sub['end_ms'] / 1000
        duration_sec = sub['duration_ms'] / 1000
        
        print(f"\n字幕 {sub['index']}:")
        print(f"  时间: {start_sec:.2f}s - {end_sec:.2f}s (时长: {duration_sec:.2f}s)")
        print(f"  文本: {sub['text'][:50]}...")
        
        # 检查间隙
        if i > 0:
            prev_end = subtitles[i-1]['end_ms']
            gap = sub['start_ms'] - prev_end
            if gap > 0:
                print(f"  间隙: {gap/1000:.2f}s (与上一条字幕)")
            elif gap < 0:
                print(f"  ⚠️ 重叠: {abs(gap)/1000:.2f}s (与上一条字幕)")
    
    # 4. 检查音频文件
    if audio_path and Path(audio_path).exists():
        print(f"\n🎵 检查音频文件: {audio_path}")
        print("-"*60)
        
        audio_duration_ms = get_audio_duration(audio_path)
        if audio_duration_ms:
            audio_duration_sec = audio_duration_ms / 1000
            print(f"音频时长: {audio_duration_sec:.2f}秒 ({audio_duration_ms}ms)")
            
            # 对比音频和字幕时间轴
            diff_ms = audio_duration_ms - total_timeline_duration
            diff_sec = diff_ms / 1000
            
            print(f"\n⚖️ 音频 vs 字幕时间轴:")
            print(f"  音频时长: {audio_duration_sec:.2f}秒")
            print(f"  字幕时间轴: {total_timeline_duration/1000:.2f}秒")
            print(f"  差异: {diff_sec:+.2f}秒 ({diff_ms:+d}ms)")
            
            if abs(diff_ms) < 100:
                print(f"  ✅ 差异很小，基本匹配")
            elif diff_ms > 0:
                print(f"  ⚠️ 音频比字幕长 {diff_sec:.2f}秒")
                print(f"     可能原因：字幕时间轴被压缩了")
            else:
                print(f"  ⚠️ 音频比字幕短 {abs(diff_sec):.2f}秒")
                print(f"     可能原因：字幕时间轴被拉伸了")
    
    # 5. 问题诊断
    print(f"\n🔍 问题诊断:")
    print("-"*60)
    
    issues = []
    
    # 检查间隙是否过大
    if gaps_duration > total_subtitle_duration * 0.5:
        issues.append(f"⚠️ 间隙过大 ({gaps_duration/1000:.2f}秒)，占总时长的 {gaps_duration/total_timeline_duration*100:.1f}%")
    
    # 检查是否有重叠
    for i in range(1, len(subtitles)):
        if subtitles[i]['start_ms'] < subtitles[i-1]['end_ms']:
            issues.append(f"⚠️ 字幕 {i} 和 {i+1} 存在重叠")
    
    # 检查字幕时长是否异常
    for sub in subtitles:
        if sub['duration_ms'] < 100:
            issues.append(f"⚠️ 字幕 {sub['index']} 时长过短 ({sub['duration_ms']}ms)")
        elif sub['duration_ms'] > 30000:
            issues.append(f"⚠️ 字幕 {sub['index']} 时长过长 ({sub['duration_ms']/1000:.1f}秒)")
    
    if issues:
        print("发现以下问题:")
        for issue in issues[:10]:  # 只显示前10个问题
            print(f"  {issue}")
    else:
        print("✅ 未发现明显问题")
    
    # 6. 建议
    print(f"\n💡 建议:")
    print("-"*60)
    
    if audio_path and Path(audio_path).exists() and audio_duration_ms:
        if abs(diff_ms) > 1000:
            print("1. 字幕时间轴与音频不匹配")
            print("   - 检查是否启用了'保持SRT总时长'功能")
            print("   - 如果启用，时间轴会被压缩/拉伸以匹配原视频")
            print("   - 建议：关闭'保持SRT总时长'，让字幕跟随音频")
        else:
            print("1. 字幕时间轴与音频基本匹配")
    
    print("2. 如果字幕和画面不同步:")
    print("   - 检查视频是否被慢放")
    print("   - 如果视频被慢放，字幕时间轴也需要相应调整")
    print("   - 使用视频合并模块会自动调整字幕时间轴")


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='诊断TTS配音时间轴问题')
    parser.add_argument('srt_path', help='字幕文件路径')
    parser.add_argument('--audio', help='音频文件路径（可选）')
    parser.add_argument('--video', help='视频文件路径（可选）')
    
    args = parser.parse_args()
    
    diagnose_timeline(args.srt_path, args.audio, args.video)


if __name__ == "__main__":
    # 如果没有命令行参数，使用默认路径
    if len(sys.argv) == 1:
        print("使用方法:")
        print("  python diagnose_tts_timeline.py <字幕文件路径> [--audio 音频文件路径]")
        print("\n示例:")
        print("  python diagnose_tts_timeline.py output/updated_subtitles.srt --audio output/dubbing_result.wav")
        print("\n或者直接修改下面的路径进行测试:")
        
        # 默认路径（用户可以修改）
        srt_path = "output/updated_subtitles.srt"
        audio_path = "output/dubbing_result.wav"
        
        if Path(srt_path).exists():
            diagnose_timeline(srt_path, audio_path if Path(audio_path).exists() else None)
        else:
            print(f"\n❌ 默认字幕文件不存在: {srt_path}")
            print("请指定正确的文件路径")
    else:
        main()
