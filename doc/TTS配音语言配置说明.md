# TTS 配音语言配置说明

## 📋 功能概述

在 TTS 配音模块中，新增了 **合成语言 (text_lang)** 参数，允许你指定要合成的语音语言。这对于多语言字幕配音非常有用。

## 🌐 支持的语言

| 语言 | 代码 | 说明 |
|------|------|------|
| 中文 | `zh` | 简体中文、繁体中文 |
| 英文 | `en` | 英语 |
| 日文 | `ja` | 日语 |
| 韩文 | `ko` | 韩语 |

## 🎯 使用场景

### 1. 日文字幕配音
```srt
1
00:00:00,040 --> 00:00:00,639
早く

2
00:00:00,640 --> 00:00:01,239
どいて
```

**配置**:
- 合成语言: **日文 (ja)**
- 参考语言: **日文 (ja)**

### 2. 英文字幕配音
```srt
1
00:00:00,000 --> 00:00:03,000
Hello, welcome to our channel

2
00:00:03,500 --> 00:00:06,000
Today we will talk about AI
```

**配置**:
- 合成语言: **英文 (en)**
- 参考语言: **英文 (en)**

### 3. 中文字幕配音
```srt
1
00:00:00,000 --> 00:00:03,000
大家好，欢迎来到我们的频道

2
00:00:03,500 --> 00:00:06,000
今天我们要讲解人工智能
```

**配置**:
- 合成语言: **中文 (zh)**
- 参考语言: **中文 (zh)**

## 🔧 配置方法

### 在 UI 界面配置

1. **打开 TTS 配音模块**
   - 点击导航栏的 **"TTS配音"**

2. **上传 SRT 文件**
   - 选择你的字幕文件

3. **选择 TTS 引擎和角色**
   - 引擎: GPT-SoVITS 或 QwenTTS
   - 角色: 选择已配置的角色

4. **配置合成语言**
   - 在 **"高级选项"** 中找到 **"合成语言"**
   - 选择与字幕内容匹配的语言
   - 默认值: **中文 (zh)**

5. **开始配音**
   - 点击 **"开始配音"** 按钮

### 配置示例

#### 示例 1: 日文配音
```
SRT 文件: japanese_subtitle.srt
TTS 引擎: GPT-SoVITS
配音角色: 日文角色
合成语言: 日文 (ja)  ← 关键配置
参考语言: 日文 (ja)
```

#### 示例 2: 英文配音
```
SRT 文件: english_subtitle.srt
TTS 引擎: GPT-SoVITS
配音角色: 英文角色
合成语言: 英文 (en)  ← 关键配置
参考语言: 英文 (en)
```

## 📝 参数说明

### text_lang (合成语言)
- **作用**: 告诉 TTS 引擎要合成的文本是什么语言
- **位置**: 高级选项 → 合成语言
- **默认值**: `zh` (中文)
- **可选值**: `zh`, `en`, `ja`, `ko`

### promptLang (参考语言)
- **作用**: 参考音频的语言
- **位置**: TTS 模型管理 → 角色配置 → 参考语言
- **建议**: 与 `text_lang` 保持一致

## ⚙️ 技术细节

### 前端实现

**UI 组件**:
```html
<select v-model="ttsDubbing.textLang">
  <option value="zh">中文</option>
  <option value="en">英文</option>
  <option value="ja">日文</option>
  <option value="ko">韩文</option>
</select>
```

**默认值**:
```javascript
const ttsDubbing = ref({
  textLang: 'zh',  // 默认中文
  // ... 其他参数
});
```

**发送到后端**:
```javascript
formData.append('text_lang', ttsDubbing.value.textLang);
```

### 后端实现

**API 接收**:
```python
@app.post("/api/tts-dubbing/start")
async def start_tts_dubbing(
    text_lang: str = Form('zh'),  # 接收语言参数
    # ... 其他参数
):
```

**传递给处理器**:
```python
processor = TTSDubbingProcessor(
    text_lang=text_lang,  # 传递语言参数
    # ... 其他参数
)
```

### TTS 调用

**GPT-SoVITS API**:
```python
params = {
    'text': text,
    'text_lang': self.text_lang,  # 使用配置的语言
    'ref_audio_path': self.role_data.get('refAudioPath'),
    'prompt_text': self.role_data.get('promptText'),
    'prompt_lang': self.role_data.get('promptLang'),
    'speed_factor': self.speed_factor
}
```

## 🎨 最佳实践

### 1. 语言一致性
- ✅ **推荐**: `text_lang` 与 `promptLang` 保持一致
- ❌ **不推荐**: 中文字幕 + 英文参考音频

### 2. 参考音频选择
- 选择与目标语言匹配的参考音频
- 参考文本应该是参考音频的准确转录

### 3. 多语言项目
为不同语言创建不同的角色：

```json
{
  "gptSovits": {
    "roles": [
      {
        "name": "中文主播",
        "refAudioPath": "chinese_ref.wav",
        "promptText": "你好，欢迎收看",
        "promptLang": "zh"
      },
      {
        "name": "日文主播",
        "refAudioPath": "japanese_ref.wav",
        "promptText": "こんにちは、ようこそ",
        "promptLang": "ja"
      },
      {
        "name": "英文主播",
        "refAudioPath": "english_ref.wav",
        "promptText": "Hello, welcome",
        "promptLang": "en"
      }
    ]
  }
}
```

## 🔍 故障排查

### 问题 1: 语音合成失败

**可能原因**:
- `text_lang` 与实际字幕语言不匹配
- 参考音频语言与 `promptLang` 不匹配

**解决方案**:
1. 检查字幕文件的实际语言
2. 确保 `text_lang` 选择正确
3. 验证参考音频和参考文本的语言一致性

### 问题 2: 语音质量差

**可能原因**:
- 跨语言合成（如中文参考音频合成英文）

**解决方案**:
1. 使用与目标语言匹配的参考音频
2. 创建专门的多语言角色
3. 调整语速参数

### 问题 3: 发音不准确

**可能原因**:
- TTS 引擎对特定语言的支持有限
- 参考音频质量不佳

**解决方案**:
1. 使用高质量的参考音频
2. 确保参考文本准确
3. 尝试不同的角色配置

## 📊 语言支持对比

| 语言 | GPT-SoVITS | QwenTTS | 推荐度 |
|------|------------|---------|--------|
| 中文 | ✅ 优秀 | ✅ 优秀 | ⭐⭐⭐⭐⭐ |
| 英文 | ✅ 良好 | ✅ 良好 | ⭐⭐⭐⭐ |
| 日文 | ✅ 良好 | ⚠️ 一般 | ⭐⭐⭐ |
| 韩文 | ⚠️ 一般 | ⚠️ 一般 | ⭐⭐ |

## 💡 使用技巧

### 1. 快速切换语言
- 为常用语言创建预设角色
- 使用描述性的角色名称（如"日文-女声-温柔"）

### 2. 批量处理
- 相同语言的字幕使用相同的 `text_lang` 配置
- 可以创建配置模板

### 3. 质量优化
- 测试不同的参考音频
- 调整语速以匹配原始时间轴
- 使用自动对齐功能

## 🆕 更新日志

### 2024-12-09
- ✅ 新增 `text_lang` 参数
- ✅ 前端 UI 添加语言选择下拉框
- ✅ 后端 API 支持语言参数
- ✅ TTS 处理器集成语言配置
- ✅ 支持中文、英文、日文、韩文

## 📚 相关文档

- [TTS配音模块使用说明.md](./TTS配音模块使用说明.md) - 完整功能文档
- [TTS配音快速开始.md](./TTS配音快速开始.md) - 快速入门指南
- [TTS配置持久化说明.md](./TTS配置持久化说明.md) - 配置管理

## 🆘 获取帮助

如果遇到问题：

1. **检查配置**:
   - 合成语言是否正确
   - 参考语言是否匹配
   - 参考音频是否存在

2. **查看日志**:
   ```
   合成语言: ja
   🔄 调用GPT-SoVITS API: 早く...
   ✅ 语音合成成功
   ```

3. **测试角色**:
   - 在 TTS 模型管理中测试角色
   - 确认参考音频可以正常合成

---

现在你可以使用 **合成语言** 参数来配音多语言字幕了！🎉
