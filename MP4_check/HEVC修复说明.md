# HEVC (H.265) 视频切割拼接修复方案

## 问题诊断

你的 `1.mp4` 视频信息：
- **编码器**: HEVC (H.265) ⚠️
- **像素格式**: yuv420p10le (10-bit) ⚠️
- **分辨率**: 1080x1920 (竖屏)
- **时长**: 97分38秒
- **大小**: 6.8 GB

**问题**: 当前的视频切割代码使用 H.264 编码器，导致切割后的片段与原视频编码不一致，无法拼接。

## 解决方案

### 方案1: 修改代码支持 HEVC（推荐）

修改 `video_timeline_sync_processor.py` 中的切割和慢放代码，自动检测视频编码格式并使用相同的编码器。

#### 步骤1: 添加视频信息检测

```python
def _get_video_codec_info(self, video_path: str) -> dict:
    """获取视频编码信息"""
    cmd = [
        self.ffprobe_bin,
        '-v', 'error',
        '-select_streams', 'v:0',
        '-show_entries', 'stream=codec_name,pix_fmt,profile',
        '-of', 'json',
        str(video_path)
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        info = json.loads(result.stdout)
        stream = info['streams'][0]
        return {
            'codec': stream.get('codec_name', 'h264'),
            'pix_fmt': stream.get('pix_fmt', 'yuv420p'),
            'profile': stream.get('profile', '')
        }
    
    # 默认返回 H.264
    return {'codec': 'h264', 'pix_fmt': 'yuv420p', 'profile': ''}
```

#### 步骤2: 修改切割命令

```python
def _cut_segment(self, start_ms, end_ms, output_path):
    """切割视频片段 - 支持 HEVC"""
    
    # 获取视频编码信息
    codec_info = self._get_video_codec_info(self.video_path)
    
    # 根据编码器选择参数
    if codec_info['codec'] == 'hevc':
        # HEVC 编码
        video_codec = 'libx265'
        codec_params = [
            '-x265-params', 'keyint=1:min-keyint=1:scenecut=0'
        ]
    else:
        # H.264 编码
        video_codec = 'libx264'
        codec_params = [
            '-x264-params', 'keyint=1:min-keyint=1:scenecut=0'
        ]
    
    cmd = [
        self.ffmpeg_bin,
        '-y',
        '-ss', str(start_ms / 1000.0),
        '-to', str(end_ms / 1000.0),
        '-i', str(self.video_path),
        '-c:v', video_codec,
        '-pix_fmt', codec_info['pix_fmt'],  # 保持原始像素格式
        *codec_params,
        '-preset', self.preset,
        '-crf', self.crf,
        '-an',  # 移除音频
        str(output_path)
    ]
    
    subprocess.run(cmd, check=True, capture_output=True)
```

#### 步骤3: 修改慢放命令

```python
def _slowdown_segment(self, input_path, output_path, slowdown_ratio):
    """慢放视频片段 - 支持 HEVC"""
    
    # 获取视频编码信息
    codec_info = self._get_video_codec_info(input_path)
    
    # 根据编码器选择参数
    if codec_info['codec'] == 'hevc':
        video_codec = 'libx265'
    else:
        video_codec = 'libx264'
    
    cmd = [
        self.ffmpeg_bin,
        '-y',
        '-i', str(input_path),
        '-vf', f'setpts={slowdown_ratio}*PTS',
        '-c:v', video_codec,
        '-pix_fmt', codec_info['pix_fmt'],
        '-preset', self.preset,
        '-crf', self.crf,
        '-an',
        str(output_path)
    ]
    
    subprocess.run(cmd, check=True, capture_output=True)
```

### 方案2: 使用 -c copy（最快，但有限制）

如果不需要慢放，可以使用 `-c copy` 直接复制流，速度最快：

```python
def _cut_segment_fast(self, start_ms, end_ms, output_path):
    """快速切割 - 使用流复制"""
    cmd = [
        self.ffmpeg_bin,
        '-y',
        '-ss', str(start_ms / 1000.0),
        '-to', str(end_ms / 1000.0),
        '-i', str(self.video_path),
        '-c', 'copy',  # 直接复制流
        str(output_path)
    ]
    
    subprocess.run(cmd, check=True, capture_output=True)
```

**限制**: 
- 切割点必须在关键帧上，否则会有黑屏
- 无法进行慢放处理

### 方案3: 预先转换为 H.264（兼容性最好）

如果你经常处理视频，可以预先将所有视频转换为 H.264：

```bash
# 使用项目中的 Python 和 FFmpeg
pyannote-audio-web-ui\.venv\Scripts\python.exe ^
  pyannote-audio-web-ui\MP4_check\convert_to_h264.py ^
  1.mp4 --fast
```

**优点**:
- 兼容性最好
- 处理速度快（H.264 编码更快）
- 文件更小

**缺点**:
- 需要额外的转换时间
- 可能有轻微的质量损失

## 推荐方案

### 对于你的情况

由于你的视频是 HEVC 编码，我推荐：

1. **短期方案**: 使用方案1修改代码，自动检测并使用 HEVC 编码器
2. **长期方案**: 预先将视频转换为 H.264，提高处理速度

### 实施步骤

#### 立即修复（方案1）

1. 打开 `src/scripts/video_timeline_sync_processor.py`
2. 添加 `_get_video_codec_info()` 方法
3. 修改 `_cut_segment()` 和 `_slowdown_segment()` 方法
4. 重新运行处理

#### 预先转换（方案3）

```bash
# 转换视频（需要约30-60分钟）
pyannote-audio-web-ui\.venv\Scripts\python.exe ^
  pyannote-audio-web-ui\MP4_check\convert_to_h264.py ^
  1.mp4 --output 1_h264.mp4 --fast

# 然后使用转换后的视频
```

## 性能对比

| 方案 | 处理速度 | 质量 | 兼容性 | 推荐度 |
|------|---------|------|--------|--------|
| 方案1 (HEVC) | 慢 | 最高 | 中等 | ⭐⭐⭐⭐ |
| 方案2 (copy) | 最快 | 原始 | 低 | ⭐⭐ |
| 方案3 (H.264) | 快 | 高 | 最高 | ⭐⭐⭐⭐⭐ |

## 注意事项

### HEVC 编码速度

HEVC (H.265) 编码比 H.264 慢约 **2-5倍**：
- H.264: 1小时视频约需 10-20分钟
- HEVC: 1小时视频约需 30-60分钟

### 10-bit 像素格式

你的视频使用 10-bit 像素格式 (`yuv420p10le`)，需要确保：
- FFmpeg 支持 10-bit 编码
- 使用 `-pix_fmt yuv420p10le` 参数

### 文件大小

- HEVC 文件通常比 H.264 小 30-50%
- 转换为 H.264 后文件会变大

## 测试命令

### 测试 HEVC 切割

```bash
# 切割前10秒
ffmpeg -y -ss 0 -to 10 -i 1.mp4 ^
  -c:v libx265 ^
  -pix_fmt yuv420p10le ^
  -x265-params keyint=1:min-keyint=1:scenecut=0 ^
  -preset fast ^
  -crf 18 ^
  -an ^
  test_segment.mp4
```

### 测试拼接

```bash
# 创建 concat_list.txt
echo file 'test_segment.mp4' > concat_list.txt
echo file 'test_segment.mp4' >> concat_list.txt

# 拼接
ffmpeg -y -f concat -safe 0 -i concat_list.txt -c copy output.mp4
```

## 总结

你的视频无法切割拼接的根本原因是 **编码格式不一致**。

**最快的解决方案**: 修改代码自动检测并使用 HEVC 编码器（方案1）

**最稳定的解决方案**: 预先转换为 H.264（方案3）

---

**创建日期**: 2024-12-26  
**状态**: 待实施
