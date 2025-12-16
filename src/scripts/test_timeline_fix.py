"""
测试脚本：验证保持总时长功能的修复
"""

import os
import sys
from pathlib import Path

# 添加父目录到路径
sys.path.insert(0, str(Path(__file__).parent))

from timeline_adjuster import TimelineAdjuster


def create_mock_audio_files(durations, output_dir):
    """
    创建模拟音频文件（使用pydub生成静音）
    
    Args:
        durations: 音频时长列表（毫秒）
        output_dir: 输出目录
        
    Returns:
        音频文件路径列表
    """
    from pydub import AudioSegment
    
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    audio_files = []
    for i, duration in enumerate(durations):
        # 创建静音音频
        audio = AudioSegment.silent(duration=duration)
        
        # 保存
        output_path = output_dir / f"mock_audio_{i:04d}.wav"
        audio.export(str(output_path), format="wav")
        audio_files.append(str(output_path))
        
        print(f"  创建模拟音频 {i+1}: {duration}ms -> {output_path.name}")
    
    return audio_files


def test_scenario_1():
    """
    测试场景1：配音超出原始时长（需要加速）
    
    原始SRT总时长: 8000ms (8秒)
    配音总时长: 12000ms (12秒)
    超出: 4000ms
    """
    print("\n" + "="*80)
    print("测试场景1：配音超出原始时长（需要加速）")
    print("="*80)
    
    # 原始字幕
    subtitles = [
        {'start_ms': 0, 'end_ms': 2000, 'text': '第一句话'},
        {'start_ms': 2500, 'end_ms': 5000, 'text': '第二句话'},
        {'start_ms': 5500, 'end_ms': 8000, 'text': '第三句话'},
    ]
    
    print(f"\n原始SRT总时长: {subtitles[-1]['end_ms']}ms")
    
    # 模拟配音时长（比原始时长长）
    audio_durations = [3000, 4500, 4500]  # 总计 12000ms
    print(f"配音总时长: {sum(audio_durations)}ms")
    print(f"超出: {sum(audio_durations) - subtitles[-1]['end_ms']}ms")
    
    # 创建模拟音频文件
    temp_dir = Path("temp_test")
    audio_files = create_mock_audio_files(audio_durations, temp_dir)
    
    # 创建时间轴调整器
    adjuster = TimelineAdjuster(
        subtitles=subtitles,
        audio_files=audio_files,
        preserve_total_time=True
    )
    
    # 调整时间轴
    updated_subtitles = adjuster.adjust_timeline()
    
    # 验证结果
    print("\n" + "="*80)
    print("验证结果")
    print("="*80)
    
    final_time = updated_subtitles[-1]['end_ms']
    original_time = subtitles[-1]['end_ms']
    
    print(f"原始总时长: {original_time}ms")
    print(f"调整后总时长: {final_time}ms")
    print(f"误差: {final_time - original_time:+d}ms")
    
    if abs(final_time - original_time) < 100:
        print("✅ 测试通过：总时长保持一致")
    else:
        print("❌ 测试失败：总时长不一致")
    
    # 检查是否有加速信息
    has_speedup = any(
        sub.get('original_duration_ms', 0) != sub.get('adjusted_duration_ms', 0)
        for sub in updated_subtitles
    )
    
    if has_speedup:
        print("✅ 测试通过：配音被加速")
        for i, sub in enumerate(updated_subtitles):
            orig = sub.get('original_duration_ms', 0)
            adj = sub.get('adjusted_duration_ms', 0)
            if orig != adj:
                print(f"  字幕 {i+1}: {orig}ms -> {adj}ms (加速 {orig/adj:.2f}x)")
    else:
        print("❌ 测试失败：配音未被加速")
    
    # 清理临时文件
    for f in audio_files:
        os.remove(f)
    temp_dir.rmdir()
    
    return abs(final_time - original_time) < 100 and has_speedup


def test_scenario_2():
    """
    测试场景2：配音短于原始时长（需要扩展间隙）
    
    原始SRT总时长: 8000ms (8秒)
    配音总时长: 6000ms (6秒)
    短缺: 2000ms
    """
    print("\n" + "="*80)
    print("测试场景2：配音短于原始时长（需要扩展间隙）")
    print("="*80)
    
    # 原始字幕
    subtitles = [
        {'start_ms': 0, 'end_ms': 2000, 'text': '第一句话'},
        {'start_ms': 2500, 'end_ms': 5000, 'text': '第二句话'},
        {'start_ms': 5500, 'end_ms': 8000, 'text': '第三句话'},
    ]
    
    print(f"\n原始SRT总时长: {subtitles[-1]['end_ms']}ms")
    
    # 模拟配音时长（比原始时长短）
    audio_durations = [1500, 2000, 2500]  # 总计 6000ms
    print(f"配音总时长: {sum(audio_durations)}ms")
    print(f"短缺: {subtitles[-1]['end_ms'] - sum(audio_durations)}ms")
    
    # 创建模拟音频文件
    temp_dir = Path("temp_test")
    audio_files = create_mock_audio_files(audio_durations, temp_dir)
    
    # 创建时间轴调整器
    adjuster = TimelineAdjuster(
        subtitles=subtitles,
        audio_files=audio_files,
        preserve_total_time=True
    )
    
    # 调整时间轴
    updated_subtitles = adjuster.adjust_timeline()
    
    # 验证结果
    print("\n" + "="*80)
    print("验证结果")
    print("="*80)
    
    final_time = updated_subtitles[-1]['end_ms']
    original_time = subtitles[-1]['end_ms']
    
    print(f"原始总时长: {original_time}ms")
    print(f"调整后总时长: {final_time}ms")
    print(f"误差: {final_time - original_time:+d}ms")
    
    if abs(final_time - original_time) < 100:
        print("✅ 测试通过：总时长保持一致")
    else:
        print("❌ 测试失败：总时长不一致")
    
    # 清理临时文件
    for f in audio_files:
        os.remove(f)
    temp_dir.rmdir()
    
    return abs(final_time - original_time) < 100


def test_scenario_3():
    """
    测试场景3：配音与原始时长接近（无需调整）
    
    原始SRT总时长: 8000ms (8秒)
    配音总时长: 8050ms (8.05秒)
    差异: 50ms (< 100ms)
    """
    print("\n" + "="*80)
    print("测试场景3：配音与原始时长接近（无需调整）")
    print("="*80)
    
    # 原始字幕
    subtitles = [
        {'start_ms': 0, 'end_ms': 2000, 'text': '第一句话'},
        {'start_ms': 2500, 'end_ms': 5000, 'text': '第二句话'},
        {'start_ms': 5500, 'end_ms': 8000, 'text': '第三句话'},
    ]
    
    print(f"\n原始SRT总时长: {subtitles[-1]['end_ms']}ms")
    
    # 模拟配音时长（与原始时长接近）
    audio_durations = [2000, 2550, 2500]  # 总计 7050ms
    print(f"配音总时长: {sum(audio_durations)}ms")
    print(f"差异: {abs(sum(audio_durations) - subtitles[-1]['end_ms'])}ms")
    
    # 创建模拟音频文件
    temp_dir = Path("temp_test")
    audio_files = create_mock_audio_files(audio_durations, temp_dir)
    
    # 创建时间轴调整器
    adjuster = TimelineAdjuster(
        subtitles=subtitles,
        audio_files=audio_files,
        preserve_total_time=True
    )
    
    # 调整时间轴
    updated_subtitles = adjuster.adjust_timeline()
    
    # 验证结果
    print("\n" + "="*80)
    print("验证结果")
    print("="*80)
    
    final_time = updated_subtitles[-1]['end_ms']
    original_time = subtitles[-1]['end_ms']
    
    print(f"原始总时长: {original_time}ms")
    print(f"调整后总时长: {final_time}ms")
    print(f"误差: {final_time - original_time:+d}ms")
    
    if abs(final_time - original_time) < 100:
        print("✅ 测试通过：总时长保持一致")
    else:
        print("❌ 测试失败：总时长不一致")
    
    # 清理临时文件
    for f in audio_files:
        os.remove(f)
    temp_dir.rmdir()
    
    return abs(final_time - original_time) < 100


if __name__ == "__main__":
    print("\n" + "🧪"*40)
    print("开始测试：保持总时长功能")
    print("🧪"*40)
    
    # 运行测试
    test1_passed = test_scenario_1()
    test2_passed = test_scenario_2()
    test3_passed = test_scenario_3()
    
    # 总结
    print("\n" + "="*80)
    print("测试总结")
    print("="*80)
    print(f"场景1（配音超出）: {'✅ 通过' if test1_passed else '❌ 失败'}")
    print(f"场景2（配音短缺）: {'✅ 通过' if test2_passed else '❌ 失败'}")
    print(f"场景3（配音接近）: {'✅ 通过' if test3_passed else '❌ 失败'}")
    
    if test1_passed and test2_passed and test3_passed:
        print("\n🎉 所有测试通过！")
        sys.exit(0)
    else:
        print("\n❌ 部分测试失败")
        sys.exit(1)
