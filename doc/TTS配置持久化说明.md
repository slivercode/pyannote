# TTS 配置持久化说明

## 📋 功能概述

GPT-SoVITS 和 QwenTTS 的配置会自动保存到 `tts_config.json` 文件中，重启服务后配置会自动加载。

## 💾 保存位置

配置文件保存在项目根目录：
```
pyannote-audio-web-ui/
├── tts_config.json          ← 实际配置文件（自动生成）
├── tts_config.example.json  ← 示例配置文件（模板）
├── src/
├── input/
└── output/
```

### 首次启动自动加载

**首次启动时**，如果 `tts_config.json` 不存在，系统会：
1. ✅ 检查是否存在 `tts_config.example.json`
2. ✅ 自动复制示例配置到 `tts_config.json`
3. ✅ 加载配置到前端界面

**后端日志**:
```
📋 首次启动，从示例配置加载: d:\...\tts_config.example.json
✅ 已创建配置文件: d:\...\tts_config.json
```

## 📝 配置文件格式

```json
{
  "gptSovits": {
    "enabled": true,
    "apiUrl": "http://192.168.110.204:9880",
    "roles": [
      {
        "name": "角色A",
        "refAudioPath": "cs3.mp3",
        "promptText": "何でだよ 私たちは治療を受けに来たんだよ",
        "promptLang": "ja",
        "speedFactor": 1.0
      },
      {
        "name": "角色B",
        "refAudioPath": "voice2.wav",
        "promptText": "你好，欢迎使用",
        "promptLang": "zh",
        "speedFactor": 1.2
      }
    ]
  },
  "qwenTts": {
    "enabled": false,
    "apiKey": "sk-xxxxxxxxxxxxxxxx",
    "roles": [
      {
        "name": "龙小春",
        "voice": "longxiaochun"
      }
    ]
  }
}
```

## 🔄 使用流程

### 1. 配置角色

1. 打开 **TTS模型管理** 弹窗
2. 启用 GPT-SoVITS
3. 配置 API 地址
4. 添加角色并填写信息：
   - 角色名称
   - 参考音频路径
   - 参考文本
   - 参考语言
   - 语速

### 2. 保存配置

点击 **"保存配置"** 按钮，配置会保存到 `tts_config.json`。

**成功提示**:
```
TTS配置保存成功！
```

### 3. 自动加载

下次打开页面时，配置会自动从 `tts_config.json` 加载。

### 4. 重新加载

如果手动修改了配置文件，点击 **"重新加载"** 按钮刷新配置。

## 🎯 API 接口

### 获取配置

```http
GET /api/tts-config
```

**响应**:
```json
{
  "gptSovits": { ... },
  "qwenTts": { ... }
}
```

### 保存配置

```http
POST /api/tts-config/save
Content-Type: application/json

{
  "gptSovits": { ... },
  "qwenTts": { ... }
}
```

**响应**:
```json
{
  "status": "success",
  "message": "配置保存成功"
}
```

## 📊 配置字段说明

### GPT-SoVITS 配置

| 字段 | 类型 | 说明 | 示例 |
|------|------|------|------|
| `enabled` | boolean | 是否启用 | `true` |
| `apiUrl` | string | API地址 | `http://192.168.110.204:9880` |
| `roles` | array | 角色列表 | `[...]` |

### 角色配置

| 字段 | 类型 | 说明 | 示例 |
|------|------|------|------|
| `name` | string | 角色名称 | `"角色A"` |
| `refAudioPath` | string | 参考音频路径 | `"cs3.mp3"` |
| `promptText` | string | 参考文本 | `"你好啊"` |
| `promptLang` | string | 参考语言 | `"zh"`, `"en"`, `"ja"` |
| `speedFactor` | number | 语速 | `1.0` (0.5-2.0) |

### QwenTTS 配置

| 字段 | 类型 | 说明 | 示例 |
|------|------|------|------|
| `enabled` | boolean | 是否启用 | `false` |
| `apiKey` | string | API密钥 | `"sk-xxx"` |
| `roles` | array | 角色列表 | `[...]` |

## 🔧 手动编辑配置

你可以直接编辑 `tts_config.json` 文件：

1. **停止服务**（可选，建议）
2. **编辑文件**
   ```bash
   notepad tts_config.json
   ```
3. **保存文件**
4. **重启服务** 或 点击 **"重新加载"** 按钮

## ⚠️ 注意事项

### 1. 文件权限

确保程序有读写 `tts_config.json` 的权限。

### 2. JSON 格式

手动编辑时注意 JSON 格式：
- ✅ 使用双引号 `"key": "value"`
- ❌ 不要使用单引号 `'key': 'value'`
- ✅ 最后一项不要加逗号
- ✅ 使用 UTF-8 编码

### 3. 备份配置

重要配置建议备份：
```bash
copy tts_config.json tts_config.backup.json
```

### 4. 配置验证

保存后可以通过浏览器开发者工具查看配置是否正确：
```javascript
// 在控制台执行
axios.get('/api/tts-config').then(res => console.log(res.data))
```

## 🚀 高级用法

### 1. 导出配置

```bash
# 导出当前配置
curl http://127.0.0.1:8514/api/tts-config > my_config.json
```

### 2. 导入配置

```bash
# 导入配置
curl -X POST http://127.0.0.1:8514/api/tts-config/save \
  -H "Content-Type: application/json" \
  -d @my_config.json
```

### 3. 批量配置角色

直接编辑 JSON 文件，一次性添加多个角色：

```json
{
  "gptSovits": {
    "enabled": true,
    "apiUrl": "http://192.168.110.204:9880",
    "roles": [
      {
        "name": "男声1",
        "refAudioPath": "male1.wav",
        "promptText": "大家好",
        "promptLang": "zh",
        "speedFactor": 1.0
      },
      {
        "name": "女声1",
        "refAudioPath": "female1.wav",
        "promptText": "你好啊",
        "promptLang": "zh",
        "speedFactor": 1.1
      },
      {
        "name": "日语角色",
        "refAudioPath": "jp1.wav",
        "promptText": "こんにちは",
        "promptLang": "ja",
        "speedFactor": 1.0
      }
    ]
  }
}
```

## 🐛 故障排查

### 问题1: 配置保存失败

**可能原因**:
- 文件权限不足
- 磁盘空间不足
- JSON 格式错误

**解决方法**:
1. 检查文件权限
2. 检查磁盘空间
3. 查看浏览器控制台错误信息

### 问题2: 配置加载失败

**可能原因**:
- 配置文件不存在
- JSON 格式错误
- 文件编码问题

**解决方法**:
1. 检查 `tts_config.json` 是否存在
2. 验证 JSON 格式（使用在线工具）
3. 确保文件使用 UTF-8 编码

### 问题3: 配置丢失

**可能原因**:
- 未点击保存按钮
- 保存失败但未注意提示
- 文件被删除

**解决方法**:
1. 重新配置并保存
2. 从备份恢复
3. 检查是否有自动备份

## 💡 最佳实践

### 1. 定期备份

```bash
# Windows
copy tts_config.json tts_config_%date:~0,4%%date:~5,2%%date:~8,2%.json

# Linux/Mac
cp tts_config.json tts_config_$(date +%Y%m%d).json
```

### 2. 版本控制

如果使用 Git，将配置文件加入版本控制：
```bash
git add tts_config.json
git commit -m "更新TTS配置"
```

### 3. 环境隔离

不同环境使用不同的配置文件：
```
tts_config.dev.json    # 开发环境
tts_config.prod.json   # 生产环境
```

### 4. 配置模板

创建配置模板供新用户使用：
```json
{
  "gptSovits": {
    "enabled": false,
    "apiUrl": "http://127.0.0.1:9880",
    "roles": []
  },
  "qwenTts": {
    "enabled": false,
    "apiKey": "",
    "roles": []
  }
}
```

## 📚 相关文档

- [TTS模型管理使用说明.md](./TTS模型管理使用说明.md)
- [CORS问题解决方案.md](./CORS问题解决方案.md)
- [使用说明.md](./cs_tts_api/使用说明.md)
