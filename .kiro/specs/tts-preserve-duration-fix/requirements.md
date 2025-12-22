# Requirements Document

## Introduction

本需求文档旨在解决TTS配音系统中"保持SRT总时长不变"功能的问题。当前用户反馈该功能启用后没有明显效果，输出音频时长仍然受到TTS生成语速的影响，无法保证输出时间为原始SRT总时长。

## Glossary

- **SRT**: SubRip字幕文件格式，包含时间轴和文本内容
- **TTS**: Text-to-Speech，文本转语音技术
- **配音时长**: TTS引擎生成的音频文件的实际时长
- **原始SRT总时长**: SRT文件中最后一条字幕的结束时间
- **TimelineAdjuster**: 时间轴动态调整器，负责调整字幕时间轴以保持总时长不变
- **语速系数**: TTS引擎生成配音时的速度参数，影响生成音频的时长
- **音频加速**: 使用FFmpeg等工具对已生成的音频进行变速处理

## Requirements

### Requirement 1

**User Story:** 作为一个视频制作者，我希望能够准确诊断"保持总时长不变"功能的当前状态，以便了解问题的根本原因。

#### Acceptance Criteria

1. WHEN 用户启用"保持SRT总时长不变"功能 THEN 系统SHALL在控制台输出明确的调试信息，包括是否进入TimelineAdjuster逻辑
2. WHEN TimelineAdjuster计算时长差异 THEN 系统SHALL输出原始SRT总时长、配音总时长和时长差异的详细数值
3. WHEN 系统决定调整策略时 THEN 系统SHALL明确输出选择的策略（简单调整/压缩时间轴/扩展时间轴）
4. WHEN 音频加速处理执行时 THEN 系统SHALL输出每段音频的加速倍率和处理结果
5. WHEN 最终音频生成完成时 THEN 系统SHALL输出最终音频时长与原始SRT总时长的对比

### Requirement 2

**User Story:** 作为一个视频制作者，我希望"保持总时长不变"功能能够正确识别需要调整的情况，而不是因为阈值设置不当而跳过调整。

#### Acceptance Criteria

1. WHEN 配音总时长与原始SRT总时长的差异大于100毫秒 THEN 系统SHALL进入时间轴调整逻辑
2. WHEN 配音总时长与原始SRT总时长的差异小于等于100毫秒 THEN 系统SHALL输出"差异很小"的提示信息
3. WHEN 用户未启用"保持总时长不变"功能 THEN 系统SHALL直接按实际配音时长排列，不进行任何调整
4. IF 系统因差异过小而跳过调整 THEN 系统SHALL在日志中明确说明跳过的原因和差异数值
5. WHEN 系统评估是否需要调整时 THEN 系统SHALL使用合理的阈值（100毫秒而非10毫秒）

### Requirement 3

**User Story:** 作为一个视频制作者，我希望当配音总时长超出原始SRT总时长时，系统能够正确计算并执行音频加速，确保最终输出符合预期。

#### Acceptance Criteria

1. WHEN 配音总时长超出原始SRT总时长 THEN 系统SHALL首先尝试压缩静音间隙
2. WHEN 静音间隙不足以吸收超出的时长 THEN 系统SHALL计算需要的音频加速倍率
3. WHEN 计算加速倍率时 THEN 系统SHALL使用公式：加速倍率 = 配音总时长 / 目标时长
4. WHEN 系统确定需要加速音频时 THEN 系统SHALL在每个字幕对象中保存original_duration_ms和adjusted_duration_ms字段
5. WHEN 合并音频时检测到adjusted_duration_ms小于original_duration_ms THEN 系统SHALL使用FFmpeg或pydub对音频进行加速处理

### Requirement 4

**User Story:** 作为一个视频制作者，我希望音频加速处理能够正确执行，并且能够验证加速后的音频时长是否符合预期。

#### Acceptance Criteria

1. WHEN 系统需要加速音频时 THEN 系统SHALL优先使用FFmpeg的rubberband或atempo滤镜进行高质量变速
2. WHEN FFmpeg加速失败时 THEN 系统SHALL回退到使用pydub的speedup方法
3. WHEN 音频加速完成后 THEN 系统SHALL验证加速后的音频实际时长是否接近目标时长（误差小于10毫秒）
4. IF 加速后的音频时长仍然超出目标时长 THEN 系统SHALL截断音频到目标时长
5. IF 加速后的音频时长短于目标时长 THEN 系统SHALL添加尾部静音以达到目标时长

### Requirement 5

**User Story:** 作为一个视频制作者，我希望最终生成的音频文件的总时长能够精确等于原始SRT的总时长，误差控制在合理范围内。

#### Acceptance Criteria

1. WHEN "保持总时长不变"功能启用时 THEN 最终音频文件的总时长SHALL等于原始SRT总时长，误差小于100毫秒
2. WHEN 系统完成音频合并时 THEN 系统SHALL输出最终音频时长与原始SRT总时长的对比
3. WHEN 最终时长与原始时长的误差大于100毫秒时 THEN 系统SHALL输出警告信息
4. WHEN 最终时长与原始时长的误差小于100毫秒时 THEN 系统SHALL输出成功信息
5. WHEN 生成更新后的SRT文件时 THEN 最后一条字幕的结束时间SHALL等于原始SRT的总时长

### Requirement 6

**User Story:** 作为一个视频制作者，我希望系统能够正确处理TTS语速系数与"保持总时长不变"功能的叠加效果，避免混淆。

#### Acceptance Criteria

1. WHEN TTS生成配音时 THEN 系统SHALL使用用户设置的语速系数参数
2. WHEN "保持总时长不变"功能启用时 THEN 系统SHALL在TTS生成完成后对音频进行二次调整
3. WHEN 系统输出日志时 THEN 系统SHALL明确区分TTS生成阶段和后处理阶段的语速调整
4. WHEN 用户查看日志时 THEN 用户SHALL能够清楚地看到TTS语速系数和后期加速倍率的分别数值
5. WHEN 系统计算最终加速倍率时 THEN 系统SHALL基于TTS生成的实际音频时长，而不是基于理论时长

