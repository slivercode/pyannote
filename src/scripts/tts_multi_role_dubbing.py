"""
多角色TTS配音处理器（基于带说话人标识的SRT）
自动解析SRT中的角色标识，按角色分配不同的TTS配音
"""

import os
import re
import json
import sys
from pathlib import Path
from collections import defaultdict

# 添加当前目录到路径
current_script_dir = os.path.dirname(os.path.abspath(__file__))
if current_script_dir not in sys.path:
    sys.path.insert(0, current_script_dir)

from tts_dubbing_processor import TTSDubbingProcessor


class MultiRoleDubbingProcessor(TTSDubbingProcessor):
    """多角色配音处理器"""
    
    def __init__(self, srt_path, output_dir, engine, roles_config, 
                 text_lang='zh', speed_factor=1.0, silence_duration=0.5, 
                 auto_align=True, api_url=None, api_key=None, 
                 task_id=None, task_dict=None,
                 enable_smart_speedup=False, enable_audio_speedup=True,
                 enable_video_slowdown=False, max_audio_speed_rate=2.0,
                 max_video_pts_rate=10.0, remove_silent_gaps=False,
                 preserve_total_time=False):  # 默认不保持总时长，保持原始间隔
        """
        初始化多角色配音处理器
        
        Args:
            srt_path: 带说话人标识的SRT文件路径
            output_dir: 输出目录
            engine: TTS引擎 ('gpt-sovits' 或 'qwen-tts')
            roles_config: 角色配置字典 {角色名: 角色配置数据}
                例如: {
                    "spk00": {"refAudioPath": "...", "promptText": "...", ...},
                    "spk01": {"refAudioPath": "...", "promptText": "...", ...}
                }
            text_lang: 合成语言 ('zh', 'en', 'ja', 'ko')
            speed_factor: 语速系数
            silence_duration: 静音间隔时长(秒)
            auto_align: 是否自动对齐时间轴
            api_url: GPT-SoVITS API地址
            api_key: QwenTTS API密钥
            task_id: 任务ID
            task_dict: 任务状态字典
        """
        # 不传递单个role_data，使用roles_config
        super().__init__(
            srt_path=srt_path,
            output_dir=output_dir,
            engine=engine,
            role_data={},  # 临时空字典
            text_lang=text_lang,
            speed_factor=speed_factor,
            silence_duration=silence_duration,
            auto_align=auto_align,
            api_url=api_url,
            api_key=api_key,
            task_id=task_id,
            task_dict=task_dict,
            # 新增：智能双重变速机制参数
            enable_smart_speedup=enable_smart_speedup,
            enable_audio_speedup=enable_audio_speedup,
            enable_video_slowdown=enable_video_slowdown,
            max_audio_speed_rate=max_audio_speed_rate,
            max_video_pts_rate=max_video_pts_rate,
            remove_silent_gaps=remove_silent_gaps,
            preserve_total_time=preserve_total_time
        )
        
        self.roles_config = roles_config  # {spk00: {...}, spk01: {...}}
        self.speaker_stats = defaultdict(int)  # 统计每个角色的字幕数
        
    def parse_srt_with_speakers(self):
        """
        解析带说话人标识的SRT文件
        
        Returns:
            List[Dict]: [{
                'index': 1,
                'start': '00:00:00,000',
                'end': '00:00:03,500',
                'speaker': 'spk00',
                'text': '大家好，欢迎收看今天的节目'
            }, ...]
        """
        print(f"📖 开始解析带说话人标识的SRT文件: {self.srt_path}")
        
        with open(self.srt_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        print(f"📄 文件大小: {len(content)} 字符")
        
        # 调试：打印文件前500个字符
        print(f"📝 文件前500字符预览:")
        print("-" * 50)
        print(content[:500])
        print("-" * 50)
        
        subtitles = []
        # 标准化换行符（注意：某些文件可能使用 \r\r\n）
        content_normalized = content.replace('\r\r\n', '\n').replace('\r\n', '\n').replace('\r', '\n')
        
        # 调试：显示标准化后的前500字符
        print(f"🔍 标准化后前500字符:")
        print("-" * 50)
        print(repr(content_normalized[:500]))
        print("-" * 50)
        
        # 使用更灵活的分割方式：按3个或更多换行符分割（即空行）
        # 因为每行结尾是 \n\n，空行是 \n\n\n\n，所以用 \n{3,} 来分割
        blocks = re.split(r'\n{3,}', content_normalized.strip())
        
        print(f"📦 分割后的块数: {len(blocks)}")
        
        # 调试：显示前3个块
        for i in range(min(3, len(blocks))):
            print(f"🔍 块 {i+1}: {repr(blocks[i])}")
        
        # 说话人标识正则：[spk00] 或 [SPEAKER_00] 或任意方括号内容
        speaker_pattern = re.compile(r'^\[([^\]]+)\]\s*(.*)$')
        
        # 时间轴正则
        time_pattern = re.compile(r'(\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2},\d{3})')
        
        for i, block in enumerate(blocks):
            block = block.strip()
            if not block:
                continue
            
            lines = [line.strip() for line in block.split('\n') if line.strip()]
            
            # 至少需要：序号、时间轴、文本
            if len(lines) < 3:
                if len(lines) > 0:
                    print(f"⚠️ 块 {i+1} 行数不足 ({len(lines)} < 3)，内容: {lines}")
                continue
            
            # 尝试解析序号（第一行应该是数字）
            try:
                index = int(lines[0])
            except ValueError:
                print(f"⚠️ 块 {i+1} 序号解析失败: {lines[0]}")
                continue
            
            # 查找时间轴（可能在第2行或第3行）
            time_match = None
            time_line_idx = -1
            for idx in range(1, min(3, len(lines))):
                time_match = time_pattern.match(lines[idx])
                if time_match:
                    time_line_idx = idx
                    break
            
            if not time_match:
                print(f"⚠️ 块 {i+1} 未找到时间轴，前3行: {lines[:3]}")
                continue
            
            # 提取文本（时间轴之后的所有行）
            text_lines = lines[time_line_idx + 1:]
            if not text_lines:
                print(f"⚠️ 块 {i+1} 没有文本内容")
                continue
            
            # 第一行可能包含说话人标识
            first_line = text_lines[0]
            speaker_match = speaker_pattern.match(first_line)
            
            if speaker_match:
                # 有说话人标识
                speaker = speaker_match.group(1)
                text_parts = [speaker_match.group(2).strip()]
                # 添加后续行（如果有多行文本）
                if len(text_lines) > 1:
                    text_parts.extend(text_lines[1:])
                text = '\n'.join([t for t in text_parts if t]).strip()
                
                # 调试信息
                if i < 3:  # 只打印前3条
                    print(f"  🔍 调试 - 原始行: {first_line}")
                    print(f"  🔍 调试 - 说话人: {speaker}")
                    print(f"  🔍 调试 - 提取文本: {text}")
            else:
                # 没有说话人标识，使用默认
                speaker = 'default'
                text = '\n'.join(text_lines).strip()
                if i < 3:
                    print(f"  ⚠️ 调试 - 未匹配说话人，原始行: {first_line}")
            
            # 跳过空文本
            if not text:
                print(f"⚠️ 块 {i+1} 文本为空")
                continue
            
            subtitle = {
                'index': index,
                'start': time_match.group(1),
                'end': time_match.group(2),
                'speaker': speaker,
                'text': text
            }
            
            subtitles.append(subtitle)
            self.speaker_stats[speaker] += 1
            
            # 只打印前10条和每100条
            if len(subtitles) <= 10 or len(subtitles) % 100 == 0:
                print(f"✅ 解析字幕 {subtitle['index']}: [{speaker}] {text[:30]}...")
        
        print(f"\n✅ 解析完成，共 {len(subtitles)} 条字幕")
        print(f"👥 说话人统计:")
        for speaker, count in sorted(self.speaker_stats.items()):
            print(f"  - {speaker}: {count} 条字幕")
        
        return subtitles
    
    def validate_roles_config(self):
        """验证角色配置是否完整"""
        print("\n🔍 验证角色配置...")
        
        missing_roles = []
        for speaker in self.speaker_stats.keys():
            if speaker not in self.roles_config and speaker != 'default':
                missing_roles.append(speaker)
        
        if missing_roles:
            print(f"⚠️ 警告：以下说话人缺少配音配置: {', '.join(missing_roles)}")
            
            # 检查是否有默认配置
            if 'default' in self.roles_config:
                print(f"   这些字幕将使用默认配置")
            else:
                print(f"   ❌ 错误：缺少默认配置，无法处理这些字幕")
                return False
        else:
            print(f"✅ 所有说话人均已配置")
        
        return True
    
    def synthesize_speech_with_role(self, text, speaker, index):
        """
        根据说话人调用对应的TTS配置合成语音
        
        Args:
            text: 要合成的文本
            speaker: 说话人标识
            index: 字幕索引
            
        Returns:
            音频文件路径
        """
        # 获取该说话人的配置
        if speaker in self.roles_config:
            role_config = self.roles_config[speaker]
            print(f"  🎭 使用角色配置: {speaker}")
        elif 'default' in self.roles_config:
            role_config = self.roles_config['default']
            print(f"  ⚠️ 说话人 {speaker} 无配置，使用默认配置")
        else:
            raise ValueError(f"说话人 {speaker} 缺少配音配置，且无默认配置")
        
        # 临时设置当前角色配置
        self.role_data = role_config
        
        # 调用父类的合成方法
        return super().synthesize_speech(text, index)
    
    def process(self):
        """
        处理完整的多角色配音流程
        
        Returns:
            dict: {
                'audio_path': str,  # 最终音频文件路径
                'srt_path': str or None  # 更新后的SRT文件路径（如果有）
            }
        """
        print("🎬 开始多角色TTS配音处理...")
        print(f"PROGRESS:5%")
        
        # 调试信息
        print(f"\n🔍 调试信息:")
        print(f"   preserve_total_time = {self.preserve_total_time}")
        print(f"   enable_smart_speedup = {self.enable_smart_speedup}")
        print(f"   auto_align = {self.auto_align}")
        
        # 1. 解析带说话人标识的SRT文件
        subtitles = self.parse_srt_with_speakers()
        total_subtitles = len(subtitles)
        
        if total_subtitles == 0:
            raise ValueError("SRT文件中没有字幕")
        
        # 1.5. 智能语速优化：如果启用保持总时长且使用默认语速，自动提升到1.2
        original_speed_factor = self.speed_factor
        if self.preserve_total_time and abs(self.speed_factor - 1.0) < 0.01:
            self.speed_factor = 1.2
            print(f"\n🚀 智能语速优化: {original_speed_factor} → {self.speed_factor} (保持总时长模式)")
            print(f"   这将加快TTS生成速度，减少后期调整时间\n")
        
        print(f"PROGRESS:10%")
        
        # 2. 验证角色配置
        if not self.validate_roles_config():
            raise ValueError("角色配置验证失败，请检查配置")
        
        print(f"PROGRESS:15%")
        
        # 3. 合成每条字幕的语音
        audio_files = []
        subtitle_data = []
        
        for i, subtitle in enumerate(subtitles):
            # 更新进度 (15% - 85%)
            progress = 15 + int((i / total_subtitles) * 70)
            print(f"PROGRESS:{progress}%")
            
            # 更新任务状态
            self.update_progress(i, total_subtitles, subtitle)
            
            print(f"\n📝 处理字幕 {i+1}/{total_subtitles}: [{subtitle['speaker']}] {subtitle['text'][:50]}...")
            
            # 获取时间信息
            start_ms = self.time_to_ms(subtitle['start'])
            end_ms = self.time_to_ms(subtitle['end'])
            
            # 使用对应角色的配置合成语音
            target_duration_ms = end_ms - start_ms
            
            try:
                audio_path = self.synthesize_speech_with_role(
                    subtitle['text'], 
                    subtitle['speaker'], 
                    i + 1
                )
                
                # 测量实际音频时长
                from pydub import AudioSegment
                actual_audio = AudioSegment.from_file(audio_path)
                actual_duration_ms = len(actual_audio)
                synthesis_success = True
                
            except Exception as e:
                # TTS合成失败时，生成静音占位音频以保持时间轴同步
                print(f"⚠️ 字幕 {i+1} 合成失败，跳过: {e}")
                print(f"   🔇 生成静音占位音频 ({target_duration_ms}ms) 以保持时间轴同步")
                
                # 生成静音占位音频
                from pydub import AudioSegment
                silence_audio = AudioSegment.silent(duration=target_duration_ms)
                audio_path = self.temp_dir / f"silence_{i+1:04d}.wav"
                silence_audio.export(str(audio_path), format="wav")
                audio_path = str(audio_path)
                
                actual_duration_ms = target_duration_ms
                synthesis_success = False
            
            # 无论成功还是失败，都添加到列表中保持索引对齐
            audio_files.append(audio_path)
            
            # 构建字幕数据
            subtitle_data.append({
                'start_ms': start_ms,
                'end_ms': end_ms,
                'text': subtitle['text'],
                'audio_file': audio_path,
                'speaker': subtitle['speaker'],
                'original_duration_ms': target_duration_ms,  # 原始字幕时长
                'actual_duration_ms': actual_duration_ms,    # 实际音频时长
                'synthesis_success': synthesis_success       # 标记是否合成成功
            })
        
        print(f"PROGRESS:85%")
        
        # 4. 判断是否使用保持总时长功能
        if self.preserve_total_time:
            print("\n🚀 启用保持SRT总时长不变功能（多角色）...")
            
            from timeline_adjuster import TimelineAdjuster
            
            print(f"📊 TTS生成语速: {self.speed_factor}x")
            
            # 使用TimelineAdjuster动态调整时间轴
            timeline_adjuster = TimelineAdjuster(
                subtitles=subtitle_data,
                audio_files=audio_files,
                preserve_total_time=True,
                target_speed_factor=self.speed_factor,
                max_speed_limit=2.0
            )
            
            # 调整时间轴
            updated_subtitles = timeline_adjuster.adjust_timeline()
            
            # 根据更新后的时间轴合并音频
            output_path = self._merge_audio_with_timeline_multi(updated_subtitles, audio_files)
            
            # 保存更新后的字幕
            updated_srt_path = self._save_updated_srt_multi(updated_subtitles)
            
        else:
            # 使用传统方式拼接音频
            print("\n🔗 拼接音频片段（传统方式）...")
            from pydub import AudioSegment
            
            audio_segments = []
            last_end_time = 0
            
            for i, subtitle_info in enumerate(subtitle_data):
                start_ms = subtitle_info['start_ms']
                end_ms = subtitle_info['end_ms']
                duration_ms = end_ms - start_ms
                
                # 添加字幕前的静音间隙
                if start_ms > last_end_time:
                    silence_duration = start_ms - last_end_time
                    
                    if self.remove_silent_gaps:
                        # 移除静音间隙模式：只保留短暂的自然停顿（最多300ms）
                        natural_pause = min(silence_duration, 300)
                        if natural_pause > 0:
                            print(f"  ⏸️  添加自然停顿: {natural_pause}ms")
                            audio_segments.append(self.create_silence(natural_pause))
                            last_end_time += natural_pause
                    else:
                        # 保留时间轴模式：添加完整的静音间隙
                        print(f"  ⏸️  添加原始间隙: {silence_duration}ms")
                        audio_segments.append(self.create_silence(silence_duration))
                        last_end_time = start_ms
                
                # 加载音频
                audio = AudioSegment.from_wav(subtitle_info['audio_file'])
                
                # 自动对齐
                if self.auto_align:
                    audio_duration = len(audio)
                    if audio_duration > duration_ms:
                        speed_ratio = audio_duration / duration_ms
                        print(f"  ⚡ 加速音频: {speed_ratio:.2f}x")
                        audio = audio.speedup(playback_speed=speed_ratio)
                    elif audio_duration < duration_ms:
                        padding = duration_ms - audio_duration
                        print(f"  ⏸️  添加尾部静音: {padding}ms")
                        audio = audio + self.create_silence(padding)
                
                audio_segments.append(audio)
                last_end_time += len(audio)
                
                # 添加字幕间隔静音（仅在没有原始间隙时）
                if not self.remove_silent_gaps and i < len(subtitle_data) - 1:
                    # 检查下一条字幕是否有原始间隙
                    next_subtitle = subtitle_data[i + 1]
                    next_start_ms = next_subtitle['start_ms']
                    
                    if next_start_ms <= end_ms:
                        # 没有原始间隙，添加静音间隔
                        silence_ms = int(self.silence_duration * 1000)
                        audio_segments.append(self.create_silence(silence_ms))
                        last_end_time += silence_ms
                        print(f"  ⏸️  添加字幕间隔静音: {silence_ms}ms")
                    # 如果有原始间隙，会在下一次循环开始时添加
            
            # 拼接所有音频
            if not audio_segments:
                raise ValueError("没有音频片段可以拼接")
            
            # 使用第一个片段作为起点，然后逐个拼接
            final_audio = audio_segments[0]
            for segment in audio_segments[1:]:
                final_audio += segment
            
            # 导出最终音频
            output_path = self.output_dir / "multi_role_dubbing_result.wav"
            print(f"💾 导出最终音频: {output_path}")
            final_audio.export(output_path, format="wav")
            output_path = str(output_path)
            
            # 生成字幕文件
            updated_srt_path = None
            if self.remove_silent_gaps:
                # 方案B：基于实际音频片段时长生成精确字幕（移除间隙）
                updated_srt_path = self._generate_precise_subtitle_from_segments(
                    subtitle_data,
                    min_gap_ms=300  # 片段之间保留300ms间隙
                )
            else:
                # 方案D：传统模式 - 根据实际拼接的音频生成字幕
                updated_srt_path = self._generate_traditional_subtitle(
                    subtitle_data,
                    silence_duration_ms=int(self.silence_duration * 1000)
                )
        
        print(f"PROGRESS:90%")
        
        # 5. 清理临时文件
        print("🧹 清理临时文件...")
        for temp_file in self.temp_dir.glob("*.wav"):
            temp_file.unlink()
        
        # 6. 统计合成结果
        success_count = sum(1 for s in subtitle_data if s.get('synthesis_success', True))
        failed_count = len(subtitle_data) - success_count
        
        # 7. 保存角色统计信息
        stats_path = self.output_dir / "role_stats.json"
        import json
        stats_data = {
            "total_subtitles": total_subtitles,
            "synthesis_success": success_count,
            "synthesis_failed": failed_count,
            "speakers": dict(self.speaker_stats),
            "output_file": str(output_path)
        }
        with open(stats_path, 'w', encoding='utf-8') as f:
            json.dump(stats_data, f, ensure_ascii=False, indent=2)
        
        print(f"PROGRESS:100%")
        
        print(f"\n✅ 多角色TTS配音完成！")
        print(f"   音频文件: {output_path}")
        print(f"   合成成功: {success_count}/{total_subtitles} 条字幕")
        if failed_count > 0:
            print(f"   ⚠️ 合成失败: {failed_count} 条字幕（已用静音占位，时间轴保持同步）")
        print(f"   统计信息: {stats_path}")
        if updated_srt_path:
            print(f"   更新后的字幕: {updated_srt_path}")
        
        return {
            'audio_path': str(output_path),
            'srt_path': updated_srt_path
        }
    
    def _merge_audio_with_timeline_multi(self, updated_subtitles, audio_files):
        """
        根据更新后的时间轴合并音频（多角色版本）
        """
        print("\n🔗 根据动态时间轴合并音频（多角色）...")
        
        from pydub import AudioSegment
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
                    
                    # 检查是否需要加速
                    original_duration = subtitle.get('original_duration_ms', audio_duration)
                    adjusted_duration = subtitle.get('adjusted_duration_ms', target_duration)
                    
                    if original_duration > adjusted_duration and abs(original_duration - adjusted_duration) > 10:
                        speed_ratio = original_duration / adjusted_duration
                        print(f"  字幕 {i+1}: 加速音频 {speed_ratio:.2f}x ({original_duration}ms -> {adjusted_duration}ms)")
                        
                        # 使用pydub加速（简单方式）
                        audio = audio.speedup(playback_speed=speed_ratio)
                    
                    # 确保音频时长匹配
                    actual_audio_duration = len(audio)
                    if abs(actual_audio_duration - target_duration) > 10:
                        if actual_audio_duration > target_duration:
                            audio = audio[:target_duration]
                        else:
                            padding = target_duration - actual_audio_duration
                            audio = audio + AudioSegment.silent(duration=padding)
                    
                    audio_segments.append(audio)
                    current_time += len(audio)
                    
                except Exception as e:
                    print(f"  ⚠️ 字幕 {i+1} 加载音频失败: {e}，使用静音")
                    silence_duration = subtitle['end_ms'] - subtitle['start_ms']
                    audio_segments.append(AudioSegment.silent(duration=silence_duration))
                    current_time += silence_duration
            else:
                silence_duration = subtitle['end_ms'] - subtitle['start_ms']
                print(f"  字幕 {i+1}: 使用静音填充 {silence_duration}ms")
                audio_segments.append(AudioSegment.silent(duration=silence_duration))
                current_time += silence_duration
        
        # 合并所有音频片段
        print(f"\n  🔗 合并 {len(audio_segments)} 个音频片段...")
        final_audio = sum(audio_segments)
        
        # 导出最终音频
        output_path = self.output_dir / "multi_role_dubbing_result.wav"
        print(f"  💾 导出最终音频: {output_path}")
        final_audio.export(str(output_path), format="wav")
        
        print(f"  ✅ 最终音频时长: {len(final_audio)}ms ({len(final_audio)/1000:.1f}秒)")
        
        return str(output_path)
    
    def _save_updated_srt_multi(self, subtitles):
        """保存更新后的字幕文件（多角色版本）"""
        output_srt = self.output_dir / "updated_subtitles.srt"
        
        with open(output_srt, 'w', encoding='utf-8') as f:
            for i, subtitle in enumerate(subtitles):
                f.write(f"{i+1}\n")
                
                # 转换毫秒为SRT时间格式
                start_time = self._ms_to_srt_time(subtitle['start_ms'])
                end_time = self._ms_to_srt_time(subtitle['end_ms'])
                
                f.write(f"{start_time} --> {end_time}\n")
                
                # 添加说话人标记
                speaker = subtitle.get('speaker', '')
                text = subtitle['text']
                if speaker:
                    text = f"[{speaker}] {text}"
                
                f.write(f"{text}\n\n")
        
        print(f"💾 保存更新后的字幕: {output_srt}")
        return str(output_srt)


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="多角色TTS配音处理器")
    parser.add_argument("--srt-path", required=True, help="带说话人标识的SRT文件路径")
    parser.add_argument("--output-dir", required=True, help="输出目录")
    parser.add_argument("--engine", required=True, choices=['gpt-sovits', 'qwen-tts'], help="TTS引擎")
    parser.add_argument("--roles-config", required=True, help="角色配置JSON文件路径")
    parser.add_argument("--text-lang", default='zh', help="合成语言")
    parser.add_argument("--speed-factor", type=float, default=1.0, help="语速系数")
    parser.add_argument("--silence-duration", type=float, default=0.5, help="静音间隔时长(秒)")
    parser.add_argument("--auto-align", action='store_true', default=True, help="自动对齐时间轴")
    parser.add_argument("--api-url", help="GPT-SoVITS API地址")
    parser.add_argument("--api-key", help="QwenTTS API密钥")
    
    args = parser.parse_args()
    
    # 加载角色配置
    with open(args.roles_config, 'r', encoding='utf-8') as f:
        roles_config = json.load(f)
    
    # 创建处理器
    processor = MultiRoleDubbingProcessor(
        srt_path=args.srt_path,
        output_dir=args.output_dir,
        engine=args.engine,
        roles_config=roles_config,
        text_lang=args.text_lang,
        speed_factor=args.speed_factor,
        silence_duration=args.silence_duration,
        auto_align=args.auto_align,
        api_url=args.api_url,
        api_key=args.api_key
    )
    
    # 执行处理
    try:
        result = processor.process()
        print(f"\n✅ 处理成功: {result}")
    except Exception as e:
        print(f"\n❌ 处理失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
