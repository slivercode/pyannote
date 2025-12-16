# ClearVoice 语音增强功能说明

## 功能简介

已成功集成阿里达摩院的 **ClearVoice 语音增强**功能到本项目中。该功能使用 **MossFormer2_SE_48K** 模型，可以有效去除音频中的噪声，提升语音质量。

## 脚本位置

```
src/scripts/clear_voice_enhance.py
```

## 功能特点

- ✅ **降噪增强**：去除背景噪声，提升人声清晰度
- ✅ **高质量输出**：使用 48kHz 采样率的专业模型
- ✅ **在线处理**：支持流式输出，边处理边保存
- ✅ **进度反馈**：实时显示处理进度（15% → 90% → 100%）

## 使用方法

### 方法一：通过 Web UI 使用（推荐）

1. 启动项目服务：
   ```bash
   start.bat
   ```

2. 在浏览器中打开 Web 界面

3. 上传音频文件

4. 在脚本列表中选择 `clear_voice_enhance.py`

5. 设置参数：
   - `--input-wav`: 输入音频文件路径（必填）
   - `--output-path`: 输出目录（默认：output）
   - `--min-segment-duration`: 最小片段时长（默认：0.5秒）

6. 点击"开始处理"，等待任务完成

### 方法二：命令行直接调用

```bash
python src/scripts/clear_voice_enhance.py --input-wav "input/your_audio.wav" --output-path "output"
```

## 参数说明

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `--input-wav` | string | ✅ | - | 输入音频文件路径 |
| `--output-path` | string | ❌ | output | 输出目录路径 |
| `--min-segment-duration` | float | ❌ | 0.5 | 过滤短于指定秒数的片段 |
| `--huggingface-token` | string | ❌ | 已内置 | HuggingFace 访问令牌 |

## 输出结果

处理完成后，增强后的音频将保存在：

```
output/
  └── YYYY-MM-DD_HHMMSS/        # 时间戳目录
      └── 原文件名/
          └── MossFormer2_SE_48K/
              └── 增强后的音频文件.wav
```

## 依赖安装

### 必需依赖

该功能需要安装 `clearvoice` 库。请在项目的 Python 环境中执行：

```bash
# 进入项目的 Python 环境
cd python

# 安装 clearvoice 库
Scripts\pip.exe install clearvoice
```

### 依赖说明

- **clearvoice**: 阿里达摩院开源的语音处理工具包
- **torch**: PyTorch 深度学习框架（通常已安装）
- **torchaudio**: 音频处理库（通常已安装）
- **librosa**: 音频分析库（通常已安装）

## 技术原理

### MossFormer2_SE_48K 模型

- **模型类型**: 基于 Transformer 的语音增强模型
- **采样率**: 48kHz（高保真）
- **任务**: Speech Enhancement（语音增强）
- **优势**: 
  - 高效去除背景噪声
  - 保留语音细节
  - 支持多种噪声类型

### 处理流程

```
输入音频 → 模型加载 → 降噪处理 → 质量增强 → 输出保存
   ↓           ↓           ↓           ↓           ↓
  15%        15%         90%         90%        100%
```

## 使用场景

1. **会议录音清理**: 去除环境噪声，提升会议记录质量
2. **播客制作**: 改善录音质量，提升听众体验
3. **视频配音**: 清理背景杂音，获得专业音质
4. **语音识别预处理**: 提高 ASR 识别准确率
5. **音频修复**: 修复低质量录音

## 注意事项

1. **首次运行**: 首次使用会自动下载模型（约 100MB），需要网络连接
2. **处理时间**: 取决于音频长度和硬件性能，通常 1 分钟音频需要 10-30 秒
3. **GPU 加速**: 如果有 NVIDIA GPU，会自动使用 CUDA 加速
4. **音频格式**: 支持 WAV、MP3、FLAC、M4A 等常见格式
5. **内存占用**: 长音频可能占用较多内存，建议分段处理

## 常见问题

### Q1: 提示找不到 clearvoice 模块？

**A**: 需要在项目的 Python 环境中安装：
```bash
python\Scripts\pip.exe install clearvoice
```

### Q2: 处理速度很慢？

**A**: 
- 检查是否有 GPU 可用（NVIDIA 显卡）
- 长音频建议分段处理
- 关闭其他占用 GPU 的程序

### Q3: 输出音质不理想？

**A**:
- 确保输入音频质量足够（建议 16kHz 以上）
- 调整 `--min-segment-duration` 参数
- 尝试多次处理或使用其他增强参数

### Q4: 模型下载失败？

**A**:
- 检查网络连接
- 确认 HuggingFace 访问正常
- 可以手动下载模型到缓存目录

## 技术支持

如遇到问题，请检查：
1. Python 环境是否正确
2. 依赖库是否完整安装
3. 输入文件路径是否正确
4. 输出目录是否有写入权限

## 更新日志

- **2024-12-08**: 初次集成 ClearVoice 语音增强功能
  - 添加 MossFormer2_SE_48K 模型支持
  - 实现进度实时反馈
  - 支持 Web UI 调用

## 相关链接

- [ClearVoice 官方文档](https://github.com/modelscope/ClearerVoice-Studio)
- [MossFormer2 论文](https://arxiv.org/abs/2312.11825)
- [阿里达摩院语音实验室](https://www.modelscope.cn/models/iic/speech_mossformer2_ans_16k)
