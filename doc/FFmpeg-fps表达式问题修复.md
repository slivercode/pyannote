# FFmpeg fps表达式问题修复

## 🐛 新问题

在修复画面静止问题后，使用 `fps=fps/{ratio}` 表达式时，FFmpeg报错：

```
[Parsed_fps_1] [Eval] Undefined constant or missing '(' in 'fps/1.9906147348662602'
[Parsed_fps_1] Failed to configure output pad on Parsed_fps_1
```

## 🔍 问题原因

**FFmpeg的fps滤镜不支持动态表达式**

- `fps` 不是FFmpeg滤镜中的预定义常量
- 不能使用 `fps=fps/1.5` 这样的表达式
- 必须提供具体的数值，如 `fps=20`

## ✅ 正确的修复方案

### 步骤1：获取原视频帧率

添加方法获取视频的实际帧率：

```python
def _get_video_fps(self, video_path: Path) -> float:
    """获取视频帧率"""
    cmd = [
        self.ffmpeg_path,
        "-i", str(video_path),
        "-hide_banner"
    ]
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='ignore'
        )
        
        # FFmpeg的信息在stderr中
        info_text = result.stderr
        
        # 提取帧率 (例如: "30 fps" 或 "29.97 fps")
        import re
        fps_match = re.search(r'(\d+(?:\.\d+)?)\s*fps', info_text)
        if fps_match:
            return float(fps_match.group(1))
        else:
            print(f"⚠️ 无法解析帧率，使用默认值30fps")
            return 30.0
        
    except Exception as e:
        print(f"⚠️ 获取视频帧率失败: {e}，使用默认值30fps")
        return 30.0
```

### 步骤2：计算目标帧率

在需要慢放时，先获取原帧率，然后计算目标帧率：

```python
if need_stretch:
    # 获取原视频帧率
    original_fps = self._get_video_fps(video_path)
    
    # 计算目标帧率
    target_fps = original_fps / stretch_ratio
    
    print(f"   原视频帧率: {original_fps:.2f}fps")
    print(f"   目标帧率: {target_fps:.2f}fps")
```

### 步骤3：使用具体数值

在滤镜中使用计算出的具体帧率值：

```python
# ❌ 错误：使用表达式
video_filter = f"[0:v]setpts={stretch_ratio}*PTS,fps=fps/{stretch_ratio}[vout]"

# ✅ 正确：使用具体数值
video_filter = f"[0:v]setpts={stretch_ratio}*PTS,fps={target_fps}[vout]"
```

## 📊 示例

### 场景：视频30秒@30fps，音频45秒

```python
# 计算拉伸系数
stretch_ratio = 45 / 30 = 1.5

# 获取原视频帧率
original_fps = 30.0

# 计算目标帧率
target_fps = 30.0 / 1.5 = 20.0

# 生成滤镜命令
video_filter = "[0:v]setpts=1.5*PTS,fps=20.0[vout]"
```

### FFmpeg命令

```bash
ffmpeg -i input.mp4 -i audio.wav \
  -filter_complex "[0:v]setpts=1.5*PTS,fps=20[vout]" \
  -map "[vout]" -map "1:a" \
  -c:v libx264 -c:a aac output.mp4
```

## 🔧 修复的代码位置

### 1. 替换音轨模式
```python
if need_stretch:
    original_fps = self._get_video_fps(video_path)
    target_fps = original_fps / stretch_ratio
    video_filter = f"[0:v]setpts={stretch_ratio}*PTS,fps={target_fps}[vout]"
```

### 2. 混合音轨模式
```python
if need_stretch:
    original_fps = self._get_video_fps(video_path)
    target_fps = original_fps / stretch_ratio
    filter_complex = f"[0:v]setpts={stretch_ratio}*PTS,fps={target_fps}[vout]; ..."
```

### 3. 嵌入字幕模式
```python
if need_stretch:
    original_fps = self._get_video_fps(video_path)
    target_fps = original_fps / stretch_ratio
    video_filter = f"[0:v]setpts={stretch_ratio}*PTS,fps={target_fps}[vout]"
```

## 🧪 验证

### 测试命令
```bash
# 查看视频帧率
ffprobe -v error -select_streams v:0 -show_entries stream=r_frame_rate -of default=noprint_wrappers=1:nokey=1 input.mp4

# 测试慢放
ffmpeg -i input.mp4 -filter_complex "[0:v]setpts=1.5*PTS,fps=20[vout]" -map "[vout]" -c:v libx264 test.mp4
```

### 预期结果
- ✅ FFmpeg执行成功，无错误
- ✅ 输出视频帧率为20fps
- ✅ 视频时长正确（45秒）
- ✅ 画面流畅播放，无静止

## 📚 技术总结

### FFmpeg滤镜表达式限制

1. **支持的表达式**
   - 数学运算：`setpts=1.5*PTS`
   - 内置变量：`PTS`, `N`, `T` 等
   - 数学函数：`sin()`, `cos()`, `sqrt()` 等

2. **不支持的表达式**
   - 动态变量：`fps=fps/1.5`（fps不是预定义变量）
   - 字符串操作
   - 外部变量引用

3. **解决方案**
   - 在Python中预先计算
   - 传递具体数值给FFmpeg
   - 不依赖FFmpeg的动态计算

### 最佳实践

```python
# ✅ 推荐：在Python中计算
original_fps = get_video_fps(video_path)
target_fps = original_fps / ratio
cmd = f"fps={target_fps}"

# ❌ 不推荐：依赖FFmpeg表达式
cmd = f"fps=fps/{ratio}"  # FFmpeg不支持
```

## ✅ 修复状态

- [x] 添加 `_get_video_fps()` 方法
- [x] 修复替换音轨模式
- [x] 修复混合音轨模式
- [x] 修复嵌入字幕模式
- [x] 更新文档
- [ ] 等待用户验证

---

**修复日期**: 2024-12-17  
**版本**: v1.3.2
