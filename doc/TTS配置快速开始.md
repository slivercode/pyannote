# TTS 配置快速开始指南

## 🚀 5分钟快速配置

### 步骤1: 打开TTS管理界面

1. 启动服务
   ```bash
   python src/main.py
   ```

2. 浏览器会自动打开 `http://127.0.0.1:8514`

3. 点击导航栏右侧的 **"TTS模型管理"** 按钮

### 步骤2: 配置 GPT-SoVITS

#### 2.1 启用引擎

点击 GPT-SoVITS 右侧的开关 ✅

#### 2.2 填写 API 地址

```
http://192.168.110.204:9880
```

#### 2.3 添加第一个角色

1. 点击 **"添加角色"** 按钮
2. 填写信息：

| 字段 | 填写内容 |
|------|---------|
| 角色名称 | `测试角色` |
| 参考音频路径 | `cs3.mp3` |
| 参考文本 | `何でだよ 私たちは治療を受けに来たんだよ` |
| 参考语言 | 选择 `日文` |
| 语速 | `1.0` |

#### 2.4 测试角色

点击 **"测试合成"** 按钮

- ✅ 成功：会自动播放合成的音频
- ❌ 失败：查看错误提示，检查配置

### 步骤3: 保存配置

点击 **"保存配置"** 按钮

**成功提示**:
```
✅ TTS配置保存成功！

配置文件: tts_config.json
GPT-SoVITS角色数: 1
QwenTTS角色数: 0
```

### 步骤4: 验证持久化

1. **关闭浏览器标签页**
2. **重新打开** `http://127.0.0.1:8514`
3. **打开 TTS 管理**
4. **确认配置已自动加载** ✅

---

## 📋 配置检查清单

在保存配置前，请确认：

- [ ] GPT-SoVITS 服务已启动（`192.168.110.204:9880`）
- [ ] 参考音频文件在服务器根目录（`cs3.mp3`）
- [ ] 参考文本与音频内容匹配
- [ ] 参考语言选择正确
- [ ] 测试合成成功

---

## 🎯 常见配置示例

### 示例1: 单角色配置

```json
{
  "gptSovits": {
    "enabled": true,
    "apiUrl": "http://192.168.110.204:9880",
    "roles": [
      {
        "name": "主播",
        "refAudioPath": "host.wav",
        "promptText": "大家好，欢迎收看今天的节目",
        "promptLang": "zh",
        "speedFactor": 1.0
      }
    ]
  }
}
```

### 示例2: 多角色配置

```json
{
  "gptSovits": {
    "enabled": true,
    "apiUrl": "http://192.168.110.204:9880",
    "roles": [
      {
        "name": "男主角",
        "refAudioPath": "male_hero.wav",
        "promptText": "我会保护你的",
        "promptLang": "zh",
        "speedFactor": 1.0
      },
      {
        "name": "女主角",
        "refAudioPath": "female_hero.wav",
        "promptText": "谢谢你",
        "promptLang": "zh",
        "speedFactor": 1.1
      },
      {
        "name": "反派",
        "refAudioPath": "villain.wav",
        "promptText": "哈哈哈，你们逃不掉的",
        "promptLang": "zh",
        "speedFactor": 0.9
      }
    ]
  }
}
```

### 示例3: 多语言配置

```json
{
  "gptSovits": {
    "enabled": true,
    "apiUrl": "http://192.168.110.204:9880",
    "roles": [
      {
        "name": "中文配音",
        "refAudioPath": "cn.wav",
        "promptText": "你好，欢迎使用",
        "promptLang": "zh",
        "speedFactor": 1.0
      },
      {
        "name": "英文配音",
        "refAudioPath": "en.wav",
        "promptText": "Hello, welcome to use",
        "promptLang": "en",
        "speedFactor": 1.0
      },
      {
        "name": "日文配音",
        "refAudioPath": "jp.wav",
        "promptText": "こんにちは、ようこそ",
        "promptLang": "ja",
        "speedFactor": 1.0
      }
    ]
  }
}
```

---

## 🔧 故障排查

### 问题1: 测试失败 - "无法连接到服务器"

**原因**: CORS 跨域问题（已解决）

**解决**: 
1. 确认已重启服务（应用了代理API）
2. 刷新浏览器页面
3. 查看浏览器控制台（F12）

### 问题2: 测试失败 - "文件不存在"

**原因**: 参考音频文件不在 GPT-SoVITS 根目录

**解决**:
```bash
# 上传音频到服务器
scp cs3.mp3 user@192.168.110.204:/home/fuxin/GPT-SoVITS/

# 或使用完整路径
"refAudioPath": "/home/fuxin/GPT-SoVITS/cs3.mp3"
```

### 问题3: 保存失败

**原因**: 文件权限或磁盘空间

**解决**:
```bash
# 检查文件权限
ls -la tts_config.json

# 检查磁盘空间
df -h
```

### 问题4: 配置未加载

**原因**: 配置文件格式错误

**解决**:
1. 验证 JSON 格式：https://jsonlint.com/
2. 检查文件编码（应为 UTF-8）
3. 查看浏览器控制台错误

---

## 💡 最佳实践

### 1. 音频文件要求

- ✅ 格式：WAV（推荐）或 MP3
- ✅ 时长：3-10 秒
- ✅ 采样率：22050Hz 或 44100Hz
- ✅ 清晰度：无噪音，发音清晰

### 2. 参考文本要求

- ✅ 与音频内容完全一致
- ✅ 包含标点符号
- ✅ 语言标记正确

### 3. 角色命名规范

- ✅ 使用有意义的名称：`"主播"`、`"男主角"`
- ❌ 避免无意义名称：`"角色1"`、`"test"`

### 4. 定期备份

```bash
# 每次重要修改后备份
copy tts_config.json tts_config.backup.json
```

---

## 📊 配置文件位置

```
pyannote-audio-web-ui/
├── tts_config.json              ← 当前配置（自动生成）
├── tts_config.example.json      ← 示例配置（参考）
└── TTS配置持久化说明.md         ← 详细文档
```

---

## 🎓 进阶功能

### 1. 批量导入配置

```bash
# 从示例配置开始
copy tts_config.example.json tts_config.json

# 编辑配置
notepad tts_config.json

# 重启服务或点击"重新加载"
```

### 2. 导出配置

```bash
# 导出当前配置
curl http://127.0.0.1:8514/api/tts-config > my_config.json
```

### 3. 共享配置

```bash
# 团队成员可以共享配置文件
# 1. 发送 tts_config.json 给同事
# 2. 同事放到项目根目录
# 3. 重启服务或重新加载
```

---

## 📞 获取帮助

### 查看日志

打开浏览器控制台（F12），查看详细日志：

```javascript
// 查看当前配置
console.log(ttsConfig.value)

// 手动加载配置
loadTtsConfig()

// 手动保存配置
saveTtsConfig()
```

### 相关文档

- [TTS模型管理使用说明.md](./TTS模型管理使用说明.md) - 完整功能说明
- [TTS配置持久化说明.md](./TTS配置持久化说明.md) - 持久化详解
- [CORS问题解决方案.md](./CORS问题解决方案.md) - 跨域问题

---

## ✅ 完成！

现在你已经成功配置了 TTS 系统，配置会自动保存并在下次启动时加载。

**下一步**:
- 添加更多角色
- 调整语速参数
- 测试不同的音频文件
- 探索多语言配置

祝使用愉快！🎉
