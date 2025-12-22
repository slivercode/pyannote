#!/usr/bin/env python3
"""
语速限制时间轴对齐功能使用演示
展示如何在实际项目中使用新的语速限制功能
"""

import os
import sys
from pathlib import Path
import json

# 添加src目录到路径
sys.path.insert(0, str(Path(__file__).parent / "src" / "scripts"))

def demo_usage_in_tts_processor():
    """演示在TTS配音处理器中使用语速限制功能"""
    print("🎬 演示：在TTS配音处理器中使用语速限制功能")
    print("="*60)
    
    # 模拟TTS配音处理器的使用
    print("📝 示例代码：")
    print("""
from tts_dubbing_processor import TTSDubbingProcessor

# 创建TTS配音处理器（自动启用语速限制）
processor = TTSDubbingProcessor(
    srt_path="input/subtitles.srt",
    output_dir="output",
    engine="gpt-sovits",
    role_data={
        "refAudioPath": "reference.mp3",
        "promptText": "参考文本",
        "promptLang": "ja"
    },
    api_url="http://localhost:9880",
    preserve_total_time=True,  # 启用保持总时长功能
    # 系统会自动应用2.0x语速限制
)

# 处理配音（会自动应用语速限制）
result = processor.process()
print(f"配音完成: {result['audio_path']}")
print(f"更新字幕: {result['srt_path']}")
""")

def demo_custom_speed_limits():
    """演示自定义语速限制"""
    print("\n🎯 演示：自定义语速限制设置")
    print("="*60)
    
    print("📝 不同语速限制的效果：")
    
    scenarios = [
        {"limit": 1.2, "desc": "保守设置", "use_case": "专业配音、教育内容"},
        {"limit": 1.5, "desc": "平衡设置", "use_case": "一般视频、播客"},
        {"limit": 2.0, "desc": "标准设置", "use_case": "快节奏内容、新闻"},
        {"limit": 2.5, "desc": "宽松设置", "use_case": "紧急处理、预览版本"},
    ]
    
    for scenario in scenarios:
        print(f"\n🔧 语速限制: {scenario['limit']}x ({scenario['desc']})")
        print(f"   适用场景: {scenario['use_case']}")
        print(f"   代码示例:")
        print(f"""   adjuster = TimelineAdjuster(
       subtitles=subtitle_data,
       audio_files=audio_files,
       preserve_total_time=True,
       max_speed_limit={scenario['limit']}  # 自定义语速限制
   )""")

def demo_configuration_examples():
    """演示配置示例"""
    print("\n⚙️ 演示：配置文件示例")
    print("="*60)
    
    # 创建配置示例
    config_examples = {
        "conservative_config": {
            "name": "保守配置",
            "max_speed_limit": 1.2,
            "preserve_total_time": True,
            "description": "适用于专业配音，优先保证音质"
        },
        "balanced_config": {
            "name": "平衡配置", 
            "max_speed_limit": 1.8,
            "preserve_total_time": True,
            "description": "平衡语速和时长，适用于大多数场景"
        },
        "performance_config": {
            "name": "性能配置",
            "max_speed_limit": 2.5,
            "preserve_total_time": False,
            "description": "优先处理速度，允许适当延长时长"
        }
    }
    
    print("📄 配置文件示例 (speed_limit_config.json):")
    print(json.dumps(config_examples, indent=2, ensure_ascii=False))

def demo_real_world_scenarios():
    """演示真实世界的使用场景"""
    print("\n🌍 演示：真实世界使用场景")
    print("="*60)
    
    scenarios = [
        {
            "name": "日语动漫配音",
            "challenge": "日语语速通常较快，配音时长容易超出",
            "solution": "设置1.5x语速限制，保持自然语调",
            "config": {"max_speed_limit": 1.5, "preserve_total_time": True}
        },
        {
            "name": "英语教育视频",
            "challenge": "需要清晰发音，不能过快",
            "solution": "设置1.2x语速限制，确保学习效果",
            "config": {"max_speed_limit": 1.2, "preserve_total_time": True}
        },
        {
            "name": "新闻快报配音",
            "challenge": "信息密度大，时间紧张",
            "solution": "设置2.0x语速限制，平衡速度和清晰度",
            "config": {"max_speed_limit": 2.0, "preserve_total_time": True}
        },
        {
            "name": "长视频批量处理",
            "challenge": "大量内容需要快速处理",
            "solution": "设置2.5x限制，允许适当延长总时长",
            "config": {"max_speed_limit": 2.5, "preserve_total_time": False}
        }
    ]
    
    for i, scenario in enumerate(scenarios, 1):
        print(f"\n📋 场景 {i}: {scenario['name']}")
        print(f"   挑战: {scenario['challenge']}")
        print(f"   解决方案: {scenario['solution']}")
        print(f"   配置: {scenario['config']}")

def demo_monitoring_and_debugging():
    """演示监控和调试功能"""
    print("\n🔍 演示：监控和调试功能")
    print("="*60)
    
    print("📊 系统会提供详细的处理信息：")
    print("""
⏱️  开始动态调整时间轴
原始总时长: 9500ms
目标语速系数: 1.0x
🎯 开始智能时间轴压缩（语速限制: 2.0x）
  📊 原始间隙总时长: 1500ms
  📊 配音总时长: 13300ms
  📊 需要压缩: 3800ms
  ✅ 压缩间隙: 1500ms
  📊 剩余需压缩: 2300ms
  🚀 加速配音: 1.21x，压缩 2300ms
  ✅ 语速限制严格执行！
""")
    
    print("\n🎯 关键监控指标：")
    indicators = [
        "最大语速是否超出限制",
        "总时长变化幅度",
        "间隙压缩比例", 
        "配音加速分布",
        "智能调整触发情况"
    ]
    
    for indicator in indicators:
        print(f"   • {indicator}")

def main():
    """主演示函数"""
    print("🚀 语速限制时间轴对齐功能 - 使用演示")
    print("="*80)
    
    demo_usage_in_tts_processor()
    demo_custom_speed_limits()
    demo_configuration_examples()
    demo_real_world_scenarios()
    demo_monitoring_and_debugging()
    
    print(f"\n" + "="*80)
    print("✅ 演示完成！")
    print("📚 更多详细信息请参考: doc/语速限制时间轴对齐功能说明.md")
    print("🧪 运行测试: python test_speed_limit_alignment.py")
    print("🚀 极端测试: python test_extreme_speed_limit.py")
    print("="*80)

if __name__ == "__main__":
    main()