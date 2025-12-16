"""
双重变速机制测试脚本
用于验证音频加速和智能策略选择功能
"""

import os
import sys
from pathlib import Path
from pydub import AudioSegment
from pydub.generators import Sine

# 添加当前目录到路径
current_dir = Path(__file__).parent
sys.path.insert(0, str(current_dir))

from speed_rate_adjuster import SpeedRateAdjuster


def create_test_audio(duration_ms, frequency=440, output_path="test_audio.wav"):
    """创建测试音频文件"""
    print(f"📝 创建测试音频: {duration_ms}ms, {frequency}Hz")
    
    # 生成正弦波
    audio = Sine(frequency).to_audio_segment(duration=duration_ms)
    
    # 导出为WAV
    audio.export(output_path, format="wav")
    print(f"✅ 测试音频已保存: {output_path}")
    return output_path


def test_basic_speedup():
    """测试基础音频加速功能"""
    print("\n" + "="*60)
    print("测试1: 基础音频加速")
    print("="*60)
    
    # 创建测试目录
    test_dir = Path("./test_output")
    test_dir.mkdir(exist_ok=True)
    
    # 创建测试音频（配音时长大于字幕时长）
    audio1 = create_test_audio(3000, 440, str(test_dir / "audio_001.wav"))  # 3秒
    audio2 = create_test_audio(4000, 550, str(test_dir / "audio_002.wav"))  # 4秒
    
    # 准备字幕数据
    subtitles = [
        {'start_ms': 0, 'end_ms': 2000, 'text': '第一句话（需要加速）'},
        {'start_ms': 2500, 'end_ms': 5000, 'text': '第二句话（需要加速）'},
    ]
    
    audio_files = [audio1, audio2]
    
    # 创建调整器
    adjuster = SpeedRateAdjuster(
        subtitles=subtitles,
        audio_files=audio_files,
        output_dir=str(test_dir),
        enable_audio_speedup=True,
        enable_video_slowdown=False,
        max_audio_speed_rate=2.0,
        remove_silent_gaps=False,
        align_subtitle_audio=True,
        raw_total_time_ms=5000
    )
    
    # 执行处理
    final_audio, updated_subtitles = adjuster.process()
    
    print(f"\n✅ 测试完成！")
    print(f"  最终音频: {final_audio}")
    print(f"  更新后的字幕数量: {len(updated_subtitles)}")
    
    # 验证结果
    for i, sub in enumerate(updated_subtitles):
        print(f"  字幕 {i+1}: {sub['start_ms']}ms - {sub['end_ms']}ms | {sub['text']}")
    
    return final_audio


def test_silent_gap_utilization():
    """测试静音间隙利用策略"""
    print("\n" + "="*60)
    print("测试2: 静音间隙利用")
    print("="*60)
    
    test_dir = Path("./test_output2")
    test_dir.mkdir(exist_ok=True)
    
    # 创建测试音频（配音略长，但可以利用静音间隙）
    audio1 = create_test_audio(2200, 440, str(test_dir / "audio_001.wav"))  # 2.2秒
    audio2 = create_test_audio(2300, 550, str(test_dir / "audio_002.wav"))  # 2.3秒
    
    # 字幕有较大的静音间隙
    subtitles = [
        {'start_ms': 0, 'end_ms': 2000, 'text': '第一句话'},
        {'start_ms': 3000, 'end_ms': 5000, 'text': '第二句话（间隙1秒）'},
    ]
    
    audio_files = [audio1, audio2]
    
    adjuster = SpeedRateAdjuster(
        subtitles=subtitles,
        audio_files=audio_files,
        output_dir=str(test_dir),
        enable_audio_speedup=True,
        enable_video_slowdown=False,
        max_audio_speed_rate=2.0,
        raw_total_time_ms=5000
    )
    
    final_audio, updated_subtitles = adjuster.process()
    
    print(f"\n✅ 测试完成！")
    print(f"  最终音频: {final_audio}")
    
    return final_audio


def test_dual_speedup():
    """测试音频加速+视频慢速双重机制"""
    print("\n" + "="*60)
    print("测试3: 双重变速机制")
    print("="*60)
    
    test_dir = Path("./test_output3")
    test_dir.mkdir(exist_ok=True)
    
    # 创建测试音频（配音远超字幕时长）
    audio1 = create_test_audio(5000, 440, str(test_dir / "audio_001.wav"))  # 5秒
    audio2 = create_test_audio(6000, 550, str(test_dir / "audio_002.wav"))  # 6秒
    
    # 字幕时长较短
    subtitles = [
        {'start_ms': 0, 'end_ms': 2000, 'text': '第一句话（配音超长）'},
        {'start_ms': 2500, 'end_ms': 4000, 'text': '第二句话（配音超长）'},
    ]
    
    audio_files = [audio1, audio2]
    
    # 启用双重变速
    adjuster = SpeedRateAdjuster(
        subtitles=subtitles,
        audio_files=audio_files,
        output_dir=str(test_dir),
        enable_audio_speedup=True,
        enable_video_slowdown=True,  # 启用视频慢速
        max_audio_speed_rate=2.0,
        max_video_pts_rate=2.0,
        raw_total_time_ms=4000
    )
    
    final_audio, updated_subtitles = adjuster.process()
    
    print(f"\n✅ 测试完成！")
    print(f"  最终音频: {final_audio}")
    
    return final_audio


def test_no_speedup_needed():
    """测试无需加速的情况"""
    print("\n" + "="*60)
    print("测试4: 无需加速（配音短于字幕）")
    print("="*60)
    
    test_dir = Path("./test_output4")
    test_dir.mkdir(exist_ok=True)
    
    # 创建测试音频（配音短于字幕时长）
    audio1 = create_test_audio(1500, 440, str(test_dir / "audio_001.wav"))  # 1.5秒
    audio2 = create_test_audio(2000, 550, str(test_dir / "audio_002.wav"))  # 2秒
    
    # 字幕时长较长
    subtitles = [
        {'start_ms': 0, 'end_ms': 2000, 'text': '第一句话'},
        {'start_ms': 2500, 'end_ms': 5000, 'text': '第二句话'},
    ]
    
    audio_files = [audio1, audio2]
    
    adjuster = SpeedRateAdjuster(
        subtitles=subtitles,
        audio_files=audio_files,
        output_dir=str(test_dir),
        enable_audio_speedup=True,
        enable_video_slowdown=False,
        max_audio_speed_rate=2.0,
        raw_total_time_ms=5000
    )
    
    final_audio, updated_subtitles = adjuster.process()
    
    print(f"\n✅ 测试完成！")
    print(f"  最终音频: {final_audio}")
    
    return final_audio


def main():
    """运行所有测试"""
    print("🚀 开始双重变速机制测试")
    print("="*60)
    
    try:
        # 测试1: 基础音频加速
        test_basic_speedup()
        
        # 测试2: 静音间隙利用
        test_silent_gap_utilization()
        
        # 测试3: 双重变速机制
        test_dual_speedup()
        
        # 测试4: 无需加速
        test_no_speedup_needed()
        
        print("\n" + "="*60)
        print("✅ 所有测试完成！")
        print("="*60)
        print("\n查看输出目录:")
        print("  - test_output/")
        print("  - test_output2/")
        print("  - test_output3/")
        print("  - test_output4/")
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
