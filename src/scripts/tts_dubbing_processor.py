"""
TTS配音处理器
解析SRT字幕文件，调用TTS API生成语音，按时间轴拼接音频
支持双重变速机制：智能音频加速和视频慢速
"""

import os
import re
import requests
from pathlib import Path
from pydub import AudioSegment
from pydub.generators import Sine
import time
from speed_rate_adjuster import SpeedRateAdjuster
from timeline_adjuster import TimelineAdjuster


class TTSDubbingProcessor:
    def __init__(self, srt_path, output_dir, engine, role_data, text_lang='zh',
                 speed_factor=1.0, silence_duration=0.5, auto_align=True, 
                 api_url=None, api_key=None, task_id=None, task_dict=None,
                 enable_smart_speedup=False, enable_audio_speedup=True, 
                 enable_video_slowdown=False, max_audio_speed_rate=2.0,
                 max_video_pts_rate=10.0, remove_silent_gaps=False,
                 preserve_total_time=True):
        """
        初始化TTS配音处理器
        
        Args:
            srt_path: SRT字幕文件路径
            output_dir: 输出目录
            engine: TTS引擎 ('gpt-sovits' 或 'qwen-tts')
            role_data: 角色配置数据
            text_lang: 合成语言 ('zh', 'en', 'ja', 'ko')
            speed_factor: 语速系数
            silence_duration: 静音间隔时长(秒)
            auto_align: 是否自动对齐时间轴
            api_url: GPT-SoVITS API地址
            api_key: QwenTTS API密钥
            task_id: 任务ID
            task_dict: 任务状态字典
            enable_smart_speedup: 是否启用智能双重变速机制
            enable_audio_speedup: 是否启用音频加速
            enable_video_slowdown: 是否启用视频慢速
            max_audio_speed_rate: 音频最大加速倍率
            max_video_pts_rate: 视频最大慢速倍率
            remove_silent_gaps: 是否移除字幕间静音间隙
            preserve_total_time: 是否保持SRT总时长不变（动态调整时间轴）
        """
        self.srt_path = srt_path
        self.output_dir = Path(output_dir)
        self.engine = engine
        self.role_data = role_data
        self.text_lang = text_lang  # 新增：合成语言
        self.speed_factor = speed_factor
        self.silence_duration = silence_duration
        self.auto_align = auto_align
        self.api_url = api_url
        self.api_key = api_key
        self.task_id = task_id
        self.task_dict = task_dict
        
        # 双重变速机制参数
        self.enable_smart_speedup = enable_smart_speedup
        self.enable_audio_speedup = enable_audio_speedup
        self.enable_video_slowdown = enable_video_slowdown
        self.max_audio_speed_rate = max_audio_speed_rate
        self.max_video_pts_rate = max_video_pts_rate
        self.remove_silent_gaps = remove_silent_gaps
        self.preserve_total_time = preserve_total_time
        
        # 创建临时目录
        self.temp_dir = self.output_dir / "temp_audio"
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        
    def parse_srt(self):
        """解析SRT文件（支持说话人标记）"""
        print(f"📖 开始解析SRT文件: {self.srt_path}")
        
        with open(self.srt_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        print(f"📄 文件大小: {len(content)} 字符")
        print(f"📄 文件前200字符: {repr(content[:200])}")
        
        subtitles = []
        # 规范化换行符
        content_normalized = content.replace('\r\n', '\n').replace('\r', '\n')
        
        # 处理两种格式：
        # 1. 标准格式：行间单换行，块间双换行
        # 2. 非标净格式：行间双换行，块间多个换行
        # 先尝试标准格式
        blocks = re.split(r'\n\n+', content_normalized.strip())
        
        # 如果所有块都只有1行，说明是非标准格式，需要重新分组
        if all(len(block.strip().split('\n')) == 1 for block in blocks if block.strip()):
            print("⚠️ 检测到非标准SRT格式（行间双换行），重新分组...")
            # 每3行为一组（序号、时间、文本）
            lines = [line for line in content_normalized.strip().split('\n') if line.strip()]
            blocks = []
            for i in range(0, len(lines), 3):
                if i + 2 < len(lines):
                    blocks.append('\n'.join(lines[i:i+3]))
                elif i < len(lines):
                    # 处理最后不完整的块
                    blocks.append('\n'.join(lines[i:]))
        
        print(f"📦 分割后的块数: {len(blocks)}")
        
        for i, block in enumerate(blocks):
            block = block.strip()
            if not block:
                continue
                
            lines = block.split('\n')
            print(f"🔍 块 {i+1}: {len(lines)} 行 - {lines[0] if lines else 'empty'}")
            
            if len(lines) >= 3:
                # 解析时间轴
                time_match = re.match(r'(\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2},\d{3})', lines[1])
                if time_match:
                    text_content = ' '.join(lines[2:])
                    
                    # 提取说话人信息（支持多种格式）
                    speaker = None
                    clean_text = text_content
                    
                    # 匹配 [spkXX] 格式（多角色配音）
                    speaker_match = re.match(r'\[(spk\d+)\]\s*(.*)', text_content)
                    if speaker_match:
                        speaker = speaker_match.group(1)
                        clean_text = speaker_match.group(2)
                    else:
                        # 匹配 [SPEAKER_XX] 格式
                        speaker_match = re.match(r'\[(SPEAKER_\d+)\]\s*(.*)', text_content)
                        if speaker_match:
                            speaker = speaker_match.group(1)
                            clean_text = speaker_match.group(2)
                        else:
                            # 匹配 spkXX: 格式
                            speaker_match = re.match(r'(spk\d+):\s*(.*)', text_content)
                            if speaker_match:
                                speaker = speaker_match.group(1)
                                clean_text = speaker_match.group(2)
                            else:
                                # 匹配 SPEAKER_XX: 格式
                                speaker_match = re.match(r'(SPEAKER_\d+):\s*(.*)', text_content)
                                if speaker_match:
                                    speaker = speaker_match.group(1)
                                    clean_text = speaker_match.group(2)
                    
                    subtitle = {
                        'index': int(lines[0]),
                        'start': time_match.group(1),
                        'end': time_match.group(2),
                        'text': clean_text.strip(),
                        'speaker': speaker  # 添加说话人信息
                    }
                    subtitles.append(subtitle)
                    
                    if speaker:
                        print(f"✅ 解析字幕 {subtitle['index']} [{speaker}]: {clean_text[:30]}...")
                    else:
                        print(f"✅ 解析字幕 {subtitle['index']}: {clean_text[:30]}...")
                else:
                    print(f"⚠️ 块 {i+1} 时间格式不匹配: {lines[1] if len(lines) > 1 else 'N/A'}")
            else:
                print(f"⚠️ 块 {i+1} 行数不足 ({len(lines)} < 3)")
        
        print(f"✅ 解析SRT文件成功，共 {len(subtitles)} 条字幕")
        return subtitles
    
    def time_to_ms(self, time_str):
        """将SRT时间格式转换为毫秒"""
        # 格式: 00:00:05,500
        h, m, s_ms = time_str.split(':')
        s, ms = s_ms.split(',')
        total_ms = int(h) * 3600000 + int(m) * 60000 + int(s) * 1000 + int(ms)
        return total_ms
    
    def synthesize_speech(self, text, index, speaker=None):
        """
        调用TTS API合成语音
        
        Args:
            text: 要合成的文本
            index: 字幕索引
            speaker: 说话人标识（可选）
            
        Returns:
            音频文件路径
        """
        output_path = self.temp_dir / f"audio_{index:04d}.wav"
        
        try:
            if self.engine == 'gpt-sovits':
                return self._synthesize_gpt_sovits(text, output_path, speaker)
            elif self.engine == 'qwen-tts':
                return self._synthesize_qwen_tts(text, output_path, speaker)
            else:
                raise ValueError(f"不支持的TTS引擎: {self.engine}")
        except Exception as e:
            print(f"❌ 合成语音失败 (字幕{index}): {e}")
            raise
    
    def _synthesize_gpt_sovits(self, text, output_path, speaker=None):
        """使用GPT-SoVITS合成语音（支持多角色）"""
        # 确保API地址正确
        api_url = self.api_url
        if not api_url.endswith('/tts'):
            api_url += '/tts'
        
        # 根据说话人选择角色配置
        if speaker and isinstance(self.role_data, dict) and speaker in self.role_data:
            # 多角色模式：从role_data中获取对应角色的配置
            role_config = self.role_data[speaker]
            print(f"🎭 使用角色配置: {speaker}")
        elif isinstance(self.role_data, dict) and 'refAudioPath' in self.role_data:
            # 单角色模式：直接使用role_data
            role_config = self.role_data
        else:
            # 兜底：使用默认配置
            role_config = self.role_data.get('default', {}) if isinstance(self.role_data, dict) else {}
            print(f"⚠️ 未找到角色 {speaker} 的配置，使用默认配置")
        
        # 获取该角色的语速系数（优先使用角色配置，否则使用全局配置）
        role_speed_factor = role_config.get('speed_factor', self.speed_factor)
        
        # 构建请求参数
        params = {
            'text': text,
            'text_lang': role_config.get('text_lang', self.text_lang),
            'ref_audio_path': role_config.get('refAudioPath', ''),
            'prompt_text': role_config.get('promptText', ''),
            'prompt_lang': role_config.get('promptLang', 'zh'),
            'speed_factor': role_speed_factor  # 使用角色特定的语速
        }
        
        if speaker:
            print(f"🔄 调用GPT-SoVITS API [{speaker}, 语速={role_speed_factor}]: {text[:30]}...")
        else:
            print(f"🔄 调用GPT-SoVITS API [语速={role_speed_factor}]: {text[:30]}...")
        
        # 发送请求
        response = requests.get(api_url, params=params, timeout=60)
        response.raise_for_status()
        
        # 保存音频
        with open(output_path, 'wb') as f:
            f.write(response.content)
        
        print(f"✅ 语音合成成功: {output_path.name}")
        return str(output_path)
    
    def _synthesize_qwen_tts(self, text, output_path, speaker=None):
        """使用QwenTTS合成语音"""
        # TODO: 实现QwenTTS API调用
        raise NotImplementedError("QwenTTS暂未实现")
    
    def create_silence(self, duration_ms):
        """创建静音音频"""
        return AudioSegment.silent(duration=duration_ms)
    
    def update_progress(self, current, total, subtitle_data=None):
        """更新任务进度"""
        if self.task_dict and self.task_id:
            progress = int((current / total) * 100)
            self.task_dict[self.task_id]["progress"] = progress
            if subtitle_data:
                self.task_dict[self.task_id]["current_subtitle"] = subtitle_data
    
    def process(self):
        """
        处理完整的配音流程（支持双重变速机制）
        
        Returns:
            dict: {
                'audio_path': str,  # 最终音频文件路径
                'srt_path': str or None  # 更新后的SRT文件路径（如果有）
            }
        """
        print("🎬 开始TTS配音处理...")
        
        # 1. 解析SRT文件
        subtitles = self.parse_srt()
        total_subtitles = len(subtitles)
        
        if total_subtitles == 0:
            raise ValueError("SRT文件中没有字幕")
        
        # 2. 合成每条字幕的语音
        audio_files = []
        subtitle_data = []
        
        for i, subtitle in enumerate(subtitles):
            # 更新进度
            self.update_progress(i, total_subtitles, subtitle)
            
            print(f"\n📝 处理字幕 {i+1}/{total_subtitles}: {subtitle['text'][:50]}...")
            
            # 获取时间信息
            start_ms = self.time_to_ms(subtitle['start'])
            end_ms = self.time_to_ms(subtitle['end'])
            
            # 合成语音（传递说话人信息）
            speaker = subtitle.get('speaker', None)
            audio_path = self.synthesize_speech(subtitle['text'], i + 1, speaker)
            audio_files.append(audio_path)
            
            # 构建字幕数据（用于双重变速）
            subtitle_data.append({
                'start_ms': start_ms,
                'end_ms': end_ms,
                'text': subtitle['text'],
                'audio_file': audio_path,
                'speaker': speaker
            })
        
        # 3. 判断是否使用保持总时长功能（优先级最高）
        print(f"\n🔍 调试信息:")
        print(f"   preserve_total_time = {self.preserve_total_time}")
        print(f"   enable_smart_speedup = {self.enable_smart_speedup}")
        print(f"   auto_align = {self.auto_align}")
        
        if self.preserve_total_time:
            print("\n🚀 启用保持SRT总时长不变功能...")
            
            # 使用TimelineAdjuster动态调整时间轴
            if True:
                print("\n" + "⏱️ "*30)
                print("⏱️  使用动态时间轴调整（保持总时长）")
                print(f"📊 原始SRT总时长: {subtitle_data[-1]['end_ms']}ms")
                print(f"📊 字幕数量: {len(subtitle_data)}")
                print(f"📊 配音文件数量: {len(audio_files)}")
                print(f"📊 语速系数: {self.speed_factor}")
                print("⏱️ "*30 + "\n")
                
                # 使用TimelineAdjuster动态调整时间轴
                timeline_adjuster = TimelineAdjuster(
                    subtitles=subtitle_data,
                    audio_files=audio_files,
                    preserve_total_time=True
                )
                
                # 调整时间轴
                updated_subtitles = timeline_adjuster.adjust_timeline()
                
                # 输出调整结果
                if updated_subtitles:
                    final_time = updated_subtitles[-1]['end_ms']
                    original_time = subtitle_data[-1]['end_ms']
                    print(f"\n📊 调整结果:")
                    print(f"   原始总时长: {original_time}ms")
                    print(f"   调整后总时长: {final_time}ms")
                    print(f"   时长差异: {final_time - original_time:+d}ms")
                    if abs(final_time - original_time) < 100:
                        print(f"   ✅ 总时长保持一致（误差 < 0.1秒）")
                    else:
                        print(f"   ⚠️ 总时长有差异（误差 = {abs(final_time - original_time)}ms）")
                
                # 根据更新后的时间轴合并音频
                output_path = self._merge_audio_with_timeline(updated_subtitles, audio_files)
                
                # 保存更新后的字幕
                updated_srt_path = self._save_updated_srt(updated_subtitles)
        
        # 4. 判断是否使用智能双重变速机制（不保持总时长）
        elif self.enable_smart_speedup:
            print("\n🚀 启用智能双重变速机制...")
            
            if False:  # 这个分支已经被上面的preserve_total_time处理了
                pass
            else:
                print("⚡ 使用传统双重变速机制（不保持总时长）")
                
                # 计算原始视频总时长
                raw_total_time_ms = subtitle_data[-1]['end_ms'] if subtitle_data else 0
                
                # 创建双重变速调整器
                adjuster = SpeedRateAdjuster(
                    subtitles=subtitle_data,
                    audio_files=audio_files,
                    output_dir=str(self.output_dir),
                    enable_audio_speedup=self.enable_audio_speedup,
                    enable_video_slowdown=self.enable_video_slowdown,
                    max_audio_speed_rate=self.max_audio_speed_rate,
                    max_video_pts_rate=self.max_video_pts_rate,
                    remove_silent_gaps=self.remove_silent_gaps,
                    align_subtitle_audio=self.auto_align,
                    raw_total_time_ms=raw_total_time_ms
                )
                
                # 执行双重变速处理
                output_path, updated_subtitles = adjuster.process()
                
                # 保存更新后的字幕
                updated_srt_path = self._save_updated_srt(updated_subtitles)
        
        # 5. 使用传统方式拼接音频
        else:
            print("\n🔗 使用传统方式拼接音频...")
            audio_segments = []
            last_end_time = 0
            
            for i, subtitle_info in enumerate(subtitle_data):
                start_ms = subtitle_info['start_ms']
                end_ms = subtitle_info['end_ms']
                duration_ms = end_ms - start_ms
                
                # 如果需要，添加静音以对齐时间轴
                if start_ms > last_end_time:
                    silence_duration = start_ms - last_end_time
                    print(f"  ⏸️  添加静音: {silence_duration}ms")
                    audio_segments.append(self.create_silence(silence_duration))
                
                # 加载音频
                audio = AudioSegment.from_wav(subtitle_info['audio_file'])
                
                # 如果启用自动对齐，调整音频长度以匹配字幕时长
                if self.auto_align:
                    audio_duration = len(audio)
                    if audio_duration > duration_ms:
                        # 音频太长，加速
                        speed_ratio = audio_duration / duration_ms
                        print(f"  ⚡ 加速音频: {speed_ratio:.2f}x")
                        audio = audio.speedup(playback_speed=speed_ratio)
                    elif audio_duration < duration_ms:
                        # 音频太短，添加静音
                        padding = duration_ms - audio_duration
                        print(f"  ⏸️  添加尾部静音: {padding}ms")
                        audio = audio + self.create_silence(padding)
                
                audio_segments.append(audio)
                last_end_time = end_ms
                
                # 添加字幕间隔静音
                if i < total_subtitles - 1:
                    silence_ms = int(self.silence_duration * 1000)
                    audio_segments.append(self.create_silence(silence_ms))
                    last_end_time += silence_ms
            
            # 拼接所有音频
            final_audio = sum(audio_segments)
            
            # 导出最终音频
            output_path = self.output_dir / "dubbing_result.wav"
            print(f"💾 导出最终音频: {output_path}")
            final_audio.export(output_path, format="wav")
            output_path = str(output_path)
            updated_srt_path = None  # 传统方式不生成更新后的SRT
        
        # 6. 清理临时文件
        print("🧹 清理临时文件...")
        for temp_file in self.temp_dir.glob("*.wav"):
            temp_file.unlink()
        
        print(f"✅ TTS配音完成！输出文件: {output_path}")
        if updated_srt_path:
            print(f"✅ 更新后的字幕: {updated_srt_path}")
        
        return {
            'audio_path': output_path,
            'srt_path': updated_srt_path
        }
    
    def _speedup_audio_ffmpeg(self, input_file, output_file, speed_ratio, target_duration_ms):
        """
        使用FFmpeg高质量加速音频
        
        Args:
            input_file: 输入音频文件
            output_file: 输出音频文件
            speed_ratio: 加速倍率
            target_duration_ms: 目标时长（毫秒）
        
        Returns:
            是否成功
        """
        try:
            import subprocess
            
            target_duration_sec = target_duration_ms / 1000.0
            
            # 尝试使用 rubberband 滤镜（高质量）
            cmd = [
                'ffmpeg', '-y', '-i', input_file,
                '-filter:a', f'rubberband=tempo={speed_ratio}',
                '-t', f'{target_duration_sec:.4f}',
                '-ar', '44100',
                '-ac', '2',
                '-c:a', 'pcm_s16le',
                output_file
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='ignore')
            
            if result.returncode != 0:
                # rubberband 不可用，使用 atempo
                print(f"    ⚠️ rubberband 不可用，使用 atempo")
                
                # atempo 限制在 0.5-2.0 之间，需要链式处理
                tempo_filters = []
                current_tempo = speed_ratio
                while current_tempo > 2.0:
                    tempo_filters.append("atempo=2.0")
                    current_tempo /= 2.0
                while current_tempo < 0.5:
                    tempo_filters.append("atempo=0.5")
                    current_tempo /= 0.5
                if 0.5 <= current_tempo <= 2.0:
                    tempo_filters.append(f"atempo={current_tempo}")
                
                filter_str = ",".join(tempo_filters)
                
                cmd = [
                    'ffmpeg', '-y', '-i', input_file,
                    '-filter:a', filter_str,
                    '-t', f'{target_duration_sec:.4f}',
                    '-ar', '44100',
                    '-ac', '2',
                    '-c:a', 'pcm_s16le',
                    output_file
                ]
                
                result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='ignore')
                
                if result.returncode != 0:
                    print(f"    ❌ FFmpeg 加速失败: {result.stderr}")
                    return False
            
            return True
            
        except Exception as e:
            print(f"    ❌ 音频加速异常: {e}")
            return False
    
    def _merge_audio_with_timeline(self, updated_subtitles, audio_files):
        """
        根据更新后的时间轴合并音频
        
        Args:
            updated_subtitles: 更新后的字幕列表（包含新的start_ms和end_ms）
            audio_files: 配音文件列表
            
        Returns:
            最终音频文件路径
        """
        print("\n🔗 根据动态时间轴合并音频...")
        
        audio_segments = []
        current_time = 0
        
        # 创建临时目录用于存放加速后的音频
        speedup_temp_dir = self.temp_dir / "speedup"
        speedup_temp_dir.mkdir(parents=True, exist_ok=True)
        
        for i, subtitle in enumerate(updated_subtitles):
            # 添加字幕前的静音间隙
            if subtitle['start_ms'] > current_time:
                gap = subtitle['start_ms'] - current_time
                print(f"  字幕 {i+1} 前添加静音: {gap}ms")
                audio_segments.append(AudioSegment.silent(duration=gap))
                current_time += gap
            
            # 加载配音音频
            audio_file = audio_files[i] if i < len(audio_files) else None
            if audio_file and os.path.exists(audio_file):
                try:
                    audio = AudioSegment.from_file(audio_file)
                    audio_duration = len(audio)
                    
                    # 计算目标时长
                    target_duration = subtitle['end_ms'] - subtitle['start_ms']
                    
                    # 检查是否需要加速（使用 original_duration_ms 和 adjusted_duration_ms）
                    original_duration = subtitle.get('original_duration_ms', audio_duration)
                    adjusted_duration = subtitle.get('adjusted_duration_ms', target_duration)
                    
                    # 如果调整后时长 < 原始时长，说明需要加速
                    if original_duration > adjusted_duration and abs(original_duration - adjusted_duration) > 10:
                        speed_ratio = original_duration / adjusted_duration
                        print(f"  字幕 {i+1}: 加速音频 {speed_ratio:.2f}x ({original_duration}ms -> {adjusted_duration}ms)")
                        
                        # 使用FFmpeg加速
                        speedup_output = speedup_temp_dir / f"speedup_{i:04d}.wav"
                        if self._speedup_audio_ffmpeg(audio_file, str(speedup_output), speed_ratio, adjusted_duration):
                            # 加速成功，加载加速后的音频
                            audio = AudioSegment.from_file(str(speedup_output))
                            print(f"    ✅ 加速成功，实际时长: {len(audio)}ms")
                        else:
                            # 加速失败，使用pydub的speedup作为备选
                            print(f"    ⚠️ FFmpeg加速失败，使用pydub备选方案")
                            audio = audio.speedup(playback_speed=speed_ratio)
                    
                    # 确保音频时长匹配目标时长
                    actual_audio_duration = len(audio)
                    if abs(actual_audio_duration - target_duration) > 10:
                        if actual_audio_duration > target_duration:
                            # 音频仍然太长，截断
                            audio = audio[:target_duration]
                            print(f"    ⚠️ 音频仍然太长，截断到 {target_duration}ms")
                        else:
                            # 音频太短，添加尾部静音
                            padding = target_duration - actual_audio_duration
                            audio = audio + AudioSegment.silent(duration=padding)
                            print(f"    ⚠️ 音频太短，添加尾部静音 {padding}ms")
                    
                    audio_segments.append(audio)
                    current_time += len(audio)
                    print(f"  字幕 {i+1}: 添加配音 {len(audio)}ms")
                    
                except Exception as e:
                    print(f"  ⚠️ 字幕 {i+1} 加载音频失败: {e}，使用静音")
                    silence_duration = subtitle['end_ms'] - subtitle['start_ms']
                    audio_segments.append(AudioSegment.silent(duration=silence_duration))
                    current_time += silence_duration
            else:
                # 使用静音填充
                silence_duration = subtitle['end_ms'] - subtitle['start_ms']
                print(f"  字幕 {i+1}: 使用静音填充 {silence_duration}ms")
                audio_segments.append(AudioSegment.silent(duration=silence_duration))
                current_time += silence_duration
        
        # 合并所有音频片段
        print(f"\n  🔗 合并 {len(audio_segments)} 个音频片段...")
        final_audio = sum(audio_segments)
        
        # 导出最终音频
        output_path = self.output_dir / "dubbing_result.wav"
        print(f"  💾 导出最终音频: {output_path}")
        final_audio.export(str(output_path), format="wav")
        
        print(f"  ✅ 最终音频时长: {len(final_audio)}ms ({len(final_audio)/1000:.1f}秒)")
        
        return str(output_path)
    
    def _save_updated_srt(self, subtitles):
        """
        保存更新后的字幕文件
        
        Returns:
            str: 保存的SRT文件路径
        """
        output_srt = self.output_dir / "updated_subtitles.srt"
        
        with open(output_srt, 'w', encoding='utf-8') as f:
            for i, subtitle in enumerate(subtitles):
                f.write(f"{i+1}\n")
                
                # 转换毫秒为SRT时间格式
                start_time = self._ms_to_srt_time(subtitle['start_ms'])
                end_time = self._ms_to_srt_time(subtitle['end_ms'])
                
                f.write(f"{start_time} --> {end_time}\n")
                f.write(f"{subtitle['text']}\n\n")
        
        print(f"💾 保存更新后的字幕: {output_srt}")
        return str(output_srt)
    
    def _ms_to_srt_time(self, ms):
        """将毫秒转换为SRT时间格式"""
        hours = int(ms // 3600000)
        minutes = int((ms % 3600000) // 60000)
        seconds = int((ms % 60000) // 1000)
        milliseconds = int(ms % 1000)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"


if __name__ == "__main__":
    # 测试代码
    processor = TTSDubbingProcessor(
        srt_path="test.srt",
        output_dir="output",
        engine="gpt-sovits",
        role_data={
            "refAudioPath": "cs3.mp3",
            "promptText": "测试文本",
            "promptLang": "zh"
        },
        api_url="http://192.168.110.204:9880"
    )
    
    result = processor.process()
    print(f"结果: {result}")
