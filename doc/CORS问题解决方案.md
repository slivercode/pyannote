# CORS 跨域问题解决方案

## 🔍 问题分析

### 现象
- 服务器返回 200 OK
- 但前端显示"无法连接到服务器"
- Network 面板显示响应大小为 0 B

### 原因
**跨域资源共享（CORS）限制**

浏览器的同源策略阻止了从 `http://127.0.0.1:8514` 访问 `http://192.168.110.204:9880`。

虽然服务器成功返回了数据，但浏览器拦截了响应体，导致前端无法接收音频数据。

## ✅ 解决方案：后端代理

### 架构变化

**之前（直接访问，被CORS阻止）:**
```
前端 (127.0.0.1:8514) 
  ↓ ❌ CORS阻止
GPT-SoVITS (192.168.110.204:9880)
```

**现在（通过代理）:**
```
前端 (127.0.0.1:8514)
  ↓ ✅ 同源请求
本地后端代理 (127.0.0.1:8514/api/tts-proxy/gpt-sovits)
  ↓ ✅ 服务器间通信（无CORS限制）
GPT-SoVITS (192.168.110.204:9880)
```

### 实现细节

#### 1. 后端代理API (`main.py`)

```python
@app.get("/api/tts-proxy/gpt-sovits")
async def gpt_sovits_proxy(
    text: str,
    text_lang: str,
    ref_audio_path: str,
    prompt_text: str,
    prompt_lang: str,
    speed_factor: float = 1.0,
    api_url: str = Query(...)
):
    # 转发请求到GPT-SoVITS
    response = requests.get(api_url, params={...}, stream=True)
    
    # 流式返回音频数据
    return StreamingResponse(
        response.iter_content(chunk_size=8192),
        media_type='audio/wav'
    )
```

**优势:**
- ✅ 解决CORS问题
- ✅ 流式传输，节省内存
- ✅ 统一错误处理
- ✅ 可以添加日志和监控

#### 2. 前端调用 (`index.html`)

```javascript
// 之前：直接访问（被CORS阻止）
const response = await axios.get('http://192.168.110.204:9880/tts', {
  params: { ... }
});

// 现在：通过代理
const response = await axios.get('/api/tts-proxy/gpt-sovits', {
  params: {
    ...params,
    api_url: 'http://192.168.110.204:9880'
  }
});
```

## 🚀 使用方法

### 1. 重启服务

修改后需要重启 FastAPI 服务：

```bash
# 停止当前服务（Ctrl+C）
# 重新运行
python src/main.py
```

### 2. 测试TTS

1. 打开 TTS 模型管理
2. 配置 GPT-SoVITS
3. 点击"测试合成"按钮
4. 现在应该可以成功了！

### 3. 查看日志

后端控制台会显示：
```
🔄 代理TTS请求: http://192.168.110.204:9880/tts
📋 参数: {'text': '你好，这是测试文本', ...}
✅ TTS请求成功，Content-Type: audio/wav
```

## 🔧 技术细节

### 为什么会有CORS问题？

1. **同源策略**: 浏览器安全机制，限制跨域请求
2. **不同源的定义**:
   - 协议不同: `http` vs `https`
   - 域名不同: `127.0.0.1` vs `192.168.110.204`
   - 端口不同: `8514` vs `9880`

### 为什么代理可以解决？

1. **前端→后端**: 同源请求（都是 `127.0.0.1:8514`），无CORS限制
2. **后端→GPT-SoVITS**: 服务器间通信，不受浏览器CORS限制

### 其他解决方案对比

| 方案 | 优点 | 缺点 |
|------|------|------|
| **后端代理** ✅ | 完全解决CORS，安全可控 | 需要修改后端代码 |
| 修改GPT-SoVITS服务器 | 直接访问 | 需要修改第三方服务 |
| 浏览器插件 | 快速测试 | 不安全，仅限开发 |
| JSONP | 简单 | 仅支持GET，已过时 |

## 📊 性能优化

### 流式传输

代理使用 `StreamingResponse`，优势：
- ✅ 边接收边发送，降低延迟
- ✅ 不需要将整个音频加载到内存
- ✅ 支持大文件传输

### 错误处理

代理统一处理各种错误：
- `504`: 超时
- `503`: 连接失败
- `500`: 其他错误

## 🎯 最佳实践

### 1. 生产环境配置

```python
# 限制允许的API地址（安全）
ALLOWED_TTS_HOSTS = [
    "192.168.110.204:9880",
    "localhost:9880"
]

@app.get("/api/tts-proxy/gpt-sovits")
async def gpt_sovits_proxy(api_url: str, ...):
    # 验证API地址
    if not any(host in api_url for host in ALLOWED_TTS_HOSTS):
        raise HTTPException(403, "不允许的API地址")
    ...
```

### 2. 添加缓存

```python
from functools import lru_cache

@lru_cache(maxsize=100)
def get_tts_audio(text, ref_audio, ...):
    # 缓存相同参数的请求结果
    ...
```

### 3. 添加监控

```python
import time

@app.get("/api/tts-proxy/gpt-sovits")
async def gpt_sovits_proxy(...):
    start_time = time.time()
    try:
        response = requests.get(...)
        duration = time.time() - start_time
        print(f"⏱️ TTS请求耗时: {duration:.2f}秒")
        return StreamingResponse(...)
    except Exception as e:
        print(f"❌ TTS请求失败: {e}")
        raise
```

## 🐛 故障排查

### 问题1: 仍然显示"无法连接"

**检查:**
1. 是否重启了服务？
2. 浏览器是否刷新了页面？
3. 查看浏览器控制台的错误信息

### 问题2: 代理超时

**解决:**
```python
# 增加超时时间
response = requests.get(api_url, params=params, timeout=60)
```

### 问题3: 音频播放失败

**检查:**
1. Content-Type 是否正确
2. 音频文件是否完整
3. 浏览器是否支持该音频格式

## 📚 相关资源

- [MDN: CORS](https://developer.mozilla.org/zh-CN/docs/Web/HTTP/CORS)
- [FastAPI: StreamingResponse](https://fastapi.tiangolo.com/advanced/custom-response/#streamingresponse)
- [Axios: 请求配置](https://axios-http.com/docs/req_config)
