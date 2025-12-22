# Design Document

## Overview

本设计文档描述了如何修复TTS配音系统中"保持SRT总时长不变"功能的问题。当前系统存在以下主要问题：

1. **阈值设置不当**：时长差异阈值设置为10ms过小，导致大部分情况被判定为"差异很小"而跳过调整
2. **音频加速未正确执行**：TimelineAdjuster计算了加速倍率，但在音频合并阶段未正确应用
3. **日志信息不足**：缺少详细的调试信息，用户无法判断功能是否正常工作
4. **TTS语速与后处理混淆**：用户不清楚TTS生成语速和后期加速的关系

本设计将通过以下方式解决这些问题：

1. 调整时长差异阈值从10ms提高到100ms
2. 修复TimelineAdjuster的压缩逻辑，确保正确标记需要加速的音频
3. 修复音频合并逻辑，确保正确读取和应用加速参数
4. 增强日志输出，提供详细的调试信息
5. 添加最终验证步骤，确保输出时长符合预期

## Architecture

系统采用分层架构：

```
┌─────────────────────────────────────────────────────────┐
│                    Web Interface                         │
│  (用户配置: 启用保持总时长、语速系数、最大加速倍率)      │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│              TTSDubbingProcessor                         │
│  - 解析SRT文件                                           │
│  - 调用TTS API生成配音                                   │
│  - 决定是否使用TimelineAdjuster                          │
│  - 合并音频片段                                          │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│              TimelineAdjuster                            │
│  - 计算配音实际时长                                      │
│  - 计算时长差异                                          │
│  - 选择调整策略(压缩/扩展/简单)                          │
│  - 计算加速倍率                                          │
│  - 生成更新后的字幕列表(包含加速标记)                    │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│           Audio Processing Layer                         │
│  - FFmpeg音频加速(rubberband/atempo)                     │
│  - pydub音频加速(备选方案)                               │
│  - 音频时长验证                                          │
│  - 音频截断/填充                                         │
└─────────────────────────────────────────────────────────┘
```

## Components and Interfaces

### 1. TimelineAdjuster

**职责**：
- 分析配音时长与原始SRT时长的差异
- 决定调整策略
- 计算加速倍率
- 生成包含加速标记的字幕列表

**接口**：

```python
class TimelineAdjuster:
    def __init__(
        self,
        subtitles: List[Dict],
        audio_files: List[str],
        preserve_total_time: bool = True
    ):
        """
        Args:
            subtitles: 原始字幕列表
            audio_files: 配音文件路径列表
            preserve_total_time: 是否保持总时长不变
        """
        pass
    
    def adjust_timeline(self) -> List[Dict]:
        """
        调整时间轴
        
        Returns:
            更新后的字幕列表，每个字幕包含:
            - start_ms: 新的开始时间
            - end_ms: 新的结束时间
            - original_duration_ms: 原始配音时长(如果需要加速)
            - adjusted_duration_ms: 调整后的目标时长(如果需要加速)
            - text: 字幕文本
        """
        pass
```

**关键修改**：

1. 调整差异阈值：
```python
# 修改前
if not self.preserve_total_time or abs(time_diff) < 10:
    return self._simple_timeline_adjustment(actual_durations)

# 修改后
if not self.preserve_total_time:
    print("⚠️ 未启用保持总时长，直接按实际时长排列")
    return self._simple_timeline_adjustment(actual_durations)

if abs(time_diff) < 100:  # 提高到100ms
    print(f"✅ 差异很小({time_diff:+d}ms < 100ms)，直接按实际时长排列")
    return self._simple_timeline_adjustment(actual_durations)
```

2. 确保正确标记需要加速的音频：
```python
def _compress_timeline(self, actual_durations, excess_time):
    # ... 计算加速倍率 ...
    
    # 关键：保存原始时长和调整后时长
    for i, (subtitle, duration) in enumerate(zip(self.subtitles, adjusted_durations)):
        updated_subtitle = subtitle.copy()
        updated_subtitle['start_ms'] = current_time
        updated_subtitle['end_ms'] = current_time + duration
        updated_subtitle['original_duration_ms'] = actual_durations[i]  # 原始时长
        updated_subtitle['adjusted_duration_ms'] = duration  # 调整后时长
        updated_subtitles.append(updated_subtitle)
```

### 2. TTSDubbingProcessor

**职责**：
- 协调整个配音流程
- 调用TimelineAdjuster
- 合并音频片段并应用加速

**接口修改**：

```python
def _merge_audio_with_timeline(
    self,
    updated_subtitles: List[Dict],
    audio_files: List[str]
) -> str:
    """
    根据更新后的时间轴合并音频
    
    关键逻辑：
    1. 检查每个字幕是否包含 original_duration_ms 和 adjusted_duration_ms
    2. 如果 original_duration_ms > adjusted_duration_ms，说明需要加速
    3. 计算加速倍率 = original_duration_ms / adjusted_duration_ms
    4. 调用 _speedup_audio_ffmpeg 或 pydub.speedup 进行加速
    5. 验证加速后的时长是否符合预期
    """
    pass
```

**关键修改**：

```python
def _merge_audio_with_timeline(self, updated_subtitles, audio_files):
    for i, subtitle in enumerate(updated_subtitles):
        # 加载配音音频
        audio = AudioSegment.from_file(audio_file)
        audio_duration = len(audio)
        
        # 计算目标时长
        target_duration = subtitle['end_ms'] - subtitle['start_ms']
        
        # 关键：检查是否需要加速
        original_duration = subtitle.get('original_duration_ms', audio_duration)
        adjusted_duration = subtitle.get('adjusted_duration_ms', target_duration)
        
        # 如果调整后时长 < 原始时长，说明需要加速
        if original_duration > adjusted_duration and abs(original_duration - adjusted_duration) > 10:
            speed_ratio = original_duration / adjusted_duration
            print(f"  字幕 {i+1}: 加速音频 {speed_ratio:.2f}x ({original_duration}ms -> {adjusted_duration}ms)")
            
            # 使用FFmpeg加速
            speedup_output = speedup_temp_dir / f"speedup_{i:04d}.wav"
            if self._speedup_audio_ffmpeg(audio_file, str(speedup_output), speed_ratio, adjusted_duration):
                audio = AudioSegment.from_file(str(speedup_output))
                print(f"    ✅ 加速成功，实际时长: {len(audio)}ms")
            else:
                # 备选方案：使用pydub
                audio = audio.speedup(playback_speed=speed_ratio)
        
        # 验证时长
        actual_audio_duration = len(audio)
        if abs(actual_audio_duration - target_duration) > 10:
            if actual_audio_duration > target_duration:
                audio = audio[:target_duration]  # 截断
            else:
                padding = target_duration - actual_audio_duration
                audio = audio + AudioSegment.silent(duration=padding)  # 填充
        
        audio_segments.append(audio)
```

### 3. 日志增强模块

**职责**：
- 在关键步骤输出详细的调试信息
- 帮助用户和开发者诊断问题

**日志输出点**：

1. **功能启用检测**：
```python
if self.preserve_total_time:
    print("\n" + "⏱️ "*30)
    print("⏱️  使用动态时间轴调整（保持总时长）")
    print(f"📊 原始SRT总时长: {subtitle_data[-1]['end_ms']}ms")
    print(f"📊 字幕数量: {len(subtitle_data)}")
    print(f"📊 配音文件数量: {len(audio_files)}")
    print(f"📊 语速系数: {self.speed_factor}")
    print("⏱️ "*30 + "\n")
```

2. **时长差异分析**：
```python
print(f"\n总配音时长: {total_actual_duration}ms")
print(f"原始SRT总时长: {self.original_total_time}ms")
print(f"时长差异: {time_diff:+d}ms")
```

3. **策略选择**：
```python
if time_diff > 0:
    print(f"⚠️ 配音超出 {time_diff}ms，需要压缩静音间隙")
elif time_diff < 0:
    print(f"✅ 配音短于原始 {abs(time_diff)}ms，需要扩展静音间隙")
else:
    print(f"✅ 差异很小，直接按实际时长排列")
```

4. **加速处理**：
```python
print(f"  字幕 {i+1}: 加速音频 {speed_ratio:.2f}x ({original_duration}ms -> {adjusted_duration}ms)")
print(f"    ✅ 加速成功，实际时长: {len(audio)}ms")
```

5. **最终验证**：
```python
final_duration = len(final_audio)
original_duration = subtitle_data[-1]['end_ms']
diff = final_duration - original_duration

print(f"\n📊 最终验证:")
print(f"   原始SRT总时长: {original_duration}ms ({original_duration/1000:.1f}秒)")
print(f"   最终音频时长: {final_duration}ms ({final_duration/1000:.1f}秒)")
print(f"   时长差异: {diff:+d}ms")

if abs(diff) < 100:
    print(f"   ✅ 总时长保持一致（误差 < 0.1秒）")
else:
    print(f"   ⚠️ 总时长有差异（误差 = {abs(diff)}ms）")
```

## Data Models

### Subtitle对象

```python
{
    'index': int,                    # 字幕序号
    'start': str,                    # 原始开始时间 "HH:MM:SS,mmm"
    'end': str,                      # 原始结束时间 "HH:MM:SS,mmm"
    'start_ms': int,                 # 开始时间(毫秒)
    'end_ms': int,                   # 结束时间(毫秒)
    'text': str,                     # 字幕文本
    'speaker': str,                  # 说话人标识(可选)
    'audio_file': str,               # 配音文件路径
    
    # TimelineAdjuster添加的字段(如果需要加速)
    'original_duration_ms': int,     # 原始配音时长
    'adjusted_duration_ms': int,     # 调整后的目标时长
}
```

### 配置参数

```python
{
    'preserve_total_time': bool,     # 是否保持总时长不变
    'speed_factor': float,           # TTS生成语速系数
    'max_audio_speed_rate': float,   # 最大音频加速倍率
    'enable_smart_speedup': bool,    # 是否启用智能加速
}
```

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system-essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: 日志输出完整性
*For any* 启用"保持总时长不变"功能的配音任务，系统日志应该包含以下关键信息：TimelineAdjuster启用标记、原始SRT总时长、配音总时长、时长差异、选择的调整策略。
**Validates: Requirements 1.1, 1.2, 1.3**

### Property 2: 差异阈值正确性
*For any* 配音任务，当配音总时长与原始SRT总时长的差异大于100毫秒时，系统应该进入时间轴调整逻辑；当差异小于等于100毫秒时，系统应该输出"差异很小"的提示。
**Validates: Requirements 2.1, 2.2**

### Property 3: 功能开关有效性
*For any* 配音任务，当用户未启用"保持总时长不变"功能时，系统应该直接按实际配音时长排列，不进行任何时间轴调整。
**Validates: Requirements 2.3**

### Property 4: 压缩策略正确性
*For any* 配音总时长超出原始SRT总时长的情况，系统应该首先尝试压缩静音间隙；如果间隙不足，则应该计算音频加速倍率并标记需要加速的音频。
**Validates: Requirements 3.1, 3.2, 3.3, 3.4**

### Property 5: 加速倍率计算正确性
*For any* 需要加速音频的情况，计算的加速倍率应该等于 original_duration_ms / adjusted_duration_ms，且该倍率应该大于1.0。
**Validates: Requirements 3.3**

### Property 6: 加速标记完整性
*For any* 需要加速的字幕，TimelineAdjuster返回的字幕对象应该包含 original_duration_ms 和 adjusted_duration_ms 两个字段，且 original_duration_ms > adjusted_duration_ms。
**Validates: Requir