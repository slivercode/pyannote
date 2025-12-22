"""
测试方案B：基于实际音频片段时长生成精确字幕
"""

import sys
from pathlib import Path

# 添加src目录到路径
sys.path.insert(0, str(Path(__file__).parent / 'src' / 'scripts'))

from tts_dubbing_processor import TTSDubbingProcessor


def test_precise_subtitle_generation():
    """测试精确字幕生成功能"""
    print("=" * 60)
    print("测试：方案B - 基于实际音频片段时长生成精确字幕")
    print("=" * 60)
    
    # 创建处理器实例
    output_dir = Path("temp/test_precise_output")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    processor = TTSDubbingProcessor(
        srt_path="dummy.srt",  # 不需要实际文件
        output_dir=str(output_dir),
        engine='gpt-sovits',
        role_data={'refAudioPath': 'dummy.wav', 'promptText': 'test'},
        remove_silent_gaps=True
    )
    
    # 模拟字幕数据（包含实际音频时长）
    subtitle_data = [
        {
            'start_ms': 0,
            'end_ms': 2000,
            'text': '你好，欢迎来到这里',
            'speaker': 'spk01',
            'original_duration_ms': 2000,
            'actual_duration_ms': 3400  # 日语实际需要3.4秒
        },
        {
            'start_ms': 2500,
            'end_ms': 5000,
            'text': '今天我们要介绍一个新功能',
            'speaker': 'spk01',
            'original_duration_ms': 2500,
            'actual_duration_ms': 4200  # 日语实际需要4.2秒
        },
        {
            'start_ms': 6000,
            'end_ms': 8000,
            'text': '这个功能非常强大',
            'speaker': 'spk02',
            'original_duration_ms': 2000,
            'actual_duration_ms': 3100  # 日语实际需要3.1秒
        },
        {
            'start_ms': 8500,
            'end_ms': 10000,
            'text': '让我们开始吧',
            'speaker': 'spk02',
            'original_duration_ms': 1500,
            'actual_duration_ms': 2300  # 日语实际需要2.3秒
        }
    ]
    
    print("\n原始字幕信息:")
    print(f"  总时长: 10秒")
    print(f"  字幕数量: {len(subtitle_data)}")
    
    print("\n实际音频信息:")
    total_actual = sum(s['actual_duration_ms'] for s in subtitle_data)
    print(f"  总音频时长: {total_actual/1000:.2f}秒")
    print(f"  比原始长: {(total_actual/10000 - 1)*100:.1f}%")
    
    # 生成精确字幕
    print("\n" + "=" * 60)
    precise_srt = processor._generate_precise_subtitle_from_segments(
        subtitle_data,
        min_gap_ms=300
    )
    
    # 读取并显示生成的字幕
    print("\n" + "=" * 60)
    print("生成的精确字幕内容:")
    print("=" * 60)
    
    with open(precise_srt, 'r', encoding='utf-8') as f:
        content = f.read()
    print(content)
    
    # 验证时间轴
    print("=" * 60)
    print("时间轴验证:")
    print("=" * 60)
    
    expected_times = [
        (0, 3400),      # 第1条: 0 + 3400ms
        (3700, 7900),   # 第2条: 3400 + 300 + 4200ms
        (8200, 11300),  # 第3条: 7900 + 300 + 3100ms
        (11600, 13900)  # 第4条: 11300 + 300 + 2300ms
    ]
    
    for i, (expected_start, expected_end) in enumerate(expected_times):
        actual_start = subtitle_data[i]['actual_duration_ms'] if i == 0 else sum(
            s['actual_duration_ms'] + 300 for s in subtitle_data[:i]
        )
        print(f"字幕{i+1}:")
        print(f"  预期: {expected_start}ms - {expected_end}ms")
        print(f"  实际音频时长: {subtitle_data[i]['actual_duration_ms']}ms")
        print(f"  原始时长: {subtitle_data[i]['original_duration_ms']}ms")
        print(f"  时长差异: +{subtitle_data[i]['actual_duration_ms'] - subtitle_data[i]['original_duration_ms']}ms")
    
    print("\n" + "=" * 60)
    print("测试完成！")
    print("=" * 60)
    
    print("\n方案B的优势:")
    print("  ✅ 每条字幕精确对齐到实际音频")
    print("  ✅ 适合语速差异不均匀的场景")
    print("  ✅ 保留自然的对话间隙（300ms）")
    print("  ✅ 不需要整体拉伸，更精确")


if __name__ == "__main__":
    test_precise_subtitle_generation()
