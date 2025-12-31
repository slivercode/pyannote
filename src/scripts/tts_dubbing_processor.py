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
                 preserve_total_time=False):  # 默认不保持总时长，保持原始间隔
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
    
    def synthesize_speech(self, text, index, speaker=None, target_duration_ms=None):
        """
        调用TTS API合成语音
        
        Args:
            text: 要合成的文本
            index: 字幕索引
            speaker: 说话人标识（可选）
            target_duration_ms: 目标时长（毫秒），如果提供则自动调整语速
            
        Returns:
            音频文件路径
        """
        output_path = self.temp_dir / f"audio_{index:04d}.wav"
        
        try:
            if self.engine == 'gpt-sovits':
                return self._synthesize_gpt_sovits(text, output_path, speaker, target_duration_ms)
            elif self.engine == 'qwen-tts':
                return self._synthesize_qwen_tts(text, output_path, speaker, target_duration_ms)
            else:
                raise ValueError(f"不支持的TTS引擎: {self.engine}")
        except Exception as e:
            print(f"❌ 合成语音失败 (字幕{index}): {e}")
            raise
    
    def _synthesize_gpt_sovits(self, text, output_path, speaker=None, target_duration_ms=None):
        """使用GPT-SoVITS合成语音（支持多角色和自动语速调整）"""
        # 确保API地址正确
        api_url = self.api_url
        if not api_url.endswith('/tts'):
            api_url += '/tts'
        
        # 根据说话人选择角色配置
        role_config = None
        if speaker and isinstance(self.role_data, dict) and speaker in self.role_data:
            # 多角色模式：从role_data中获取对应角色的配置
            role_config = self.role_data[speaker]
            print(f"🎭 使用角色配置: {speaker}")
        elif isinstance(self.role_data, dict) and 'refAudioPath' in self.role_data:
            # 单角色模式：直接使用role_data
            role_config = self.role_data
        else:
            # 兜底：尝试使用默认配置
            if isinstance(self.role_data, dict) and 'default' in self.role_data:
                role_config = self.role_data['default']
                print(f"⚠️ 未找到角色 {speaker} 的配置，使用默认配置")
            else:
                # 完全没有配置，生成静音音频作为占位
                print(f"❌ 未找到角色 {speaker} 的配置，且无默认配置")
                print(f"   生成静音音频作为占位（时长: {target_duration_ms or 1000}ms）")
                
                # 生成静音音频
                duration_ms = target_duration_ms if target_duration_ms else 1000
                silence = AudioSegment.silent(duration=duration_ms)
                silence.export(output_path, format="wav")
                
                return str(output_path)
        
        # 验证必要字段
        if not role_config.get('refAudioPath'):
            print(f"⚠️ 角色 {speaker} 缺少参考音频路径，生成静音占位")
            duration_ms = target_duration_ms if target_duration_ms else 1000
            silence = AudioSegment.silent(duration=duration_ms)
            silence.export(output_path, format="wav")
            return str(output_path)
        
        # 获取该角色的语速系数（优先使用角色配置，否则使用全局配置）
        role_speed_factor = role_config.get('speed_factor', self.speed_factor)
        
        # 如果提供了目标时长，先用标准语速生成一次，测量实际时长，然后计算需要的语速
        if target_duration_ms and self.auto_align:
            # 第一次：用标准语速生成，测量时长
            temp_output = self.temp_dir / f"temp_{output_path.name}"
            
            # 获取目标语言
            target_lang_test = role_config.get('text_lang', self.text_lang)
            
            params_test = {
                'text': text,
                'text_lang': target_lang_test,
                'ref_audio_path': role_config.get('refAudioPath', ''),
                'prompt_text': role_config.get('promptText', ''),
                'prompt_lang': role_config.get('promptLang', target_lang_test),  # 使用目标语言作为默认值
                'speed_factor': 1.0  # 先用标准语速测试
            }
            
            response_test = requests.get(api_url, params=params_test, timeout=60)
            response_test.raise_for_status()
            
            with open(temp_output, 'wb') as f:
                f.write(response_test.content)
            
            # 测量实际时长
            audio_test = AudioSegment.from_file(str(temp_output))
            actual_duration_ms = len(audio_test)
            
            # 计算需要的语速（限制在合理范围内）
            required_speed = actual_duration_ms / target_duration_ms
            
            # 限制语速范围（0.5x - 2.0x）
            required_speed = max(0.5, min(2.0, required_speed))
            
            tts_speed_factor = required_speed
            
            print(f"  📊 测试时长: {actual_duration_ms}ms, 目标: {target_duration_ms}ms, 计算语速: {required_speed:.2f}x")
            
            # 清理临时文件
            try:
                os.unlink(temp_output)
            except:
                pass
        else:
            # 直接使用设定的语速
            tts_speed_factor = role_speed_factor
        
        # 获取目标语言
        target_lang = role_config.get('text_lang', self.text_lang)
        
        # 智能获取参考文本语言
        # 优先使用配置中的promptLang，如果没有则使用目标语言
        prompt_lang = role_config.get('promptLang', target_lang)
        
        # 构建请求参数
        params = {
            'text': text,
            'text_lang': target_lang,
            'ref_audio_path': role_config.get('refAudioPath', ''),
            'prompt_text': role_config.get('promptText', ''),
            'prompt_lang': prompt_lang,  # 使用智能获取的语言
            'speed_factor': tts_speed_factor  # 使用计算后的语速
        }
        
        if speaker:
            print(f"🔄 调用GPT-SoVITS API [{speaker}, 语速={tts_speed_factor:.2f}x]: {text[:30]}...")
        else:
            print(f"🔄 调用GPT-SoVITS API [语速={tts_speed_factor:.2f}x]: {text[:30]}...")
        
        # 输出详细参数（用于诊断）
        print(f"   目标语言: {target_lang}")
        print(f"   参考文本: {params['prompt_text'][:30]}...")
        print(f"   参考语言: {prompt_lang}")  # 重点：检查这个是否正确
        
        # 发送请求
        response = requests.get(api_url, params=params, timeout=60)
        response.raise_for_status()
        
        # 保存音频
        with open(output_path, 'wb') as f:
            f.write(response.content)
        
        # 验证最终时长
        if target_duration_ms:
            audio_final = AudioSegment.from_file(str(output_path))
            final_duration = len(audio_final)
            print(f"✅ 语音合成成功: {output_path.name}, 时长: {final_duration}ms (目标: {target_duration_ms}ms)")
        else:
            print(f"✅ 语音合成成功: {output_path.name}")
        
        return str(output_path)
    
    def _synthesize_qwen_tts(self, text, output_path, speaker=None, target_duration_ms=None):
        """使用QwenTTS合成语音（支持多角色）"""
        import dashscope
        from dashscope.audio.tts import SpeechSynthesizer
        
        # 设置API密钥
        dashscope.api_key = self.api_key
        
        # 根据说话人选择角色配置
        role_config = None
        if speaker and isinstance(self.role_data, dict) and speaker in self.role_data:
            # 多角色模式：从role_data中获取对应角色的配置
            role_config = self.role_data[speaker]
            print(f"🎭 使用角色配置: {speaker}")
        elif isinstance(self.role_data, dict) and 'voice' in self.role_data:
            # 单角色模式：直接使用role_data
            role_config = self.role_data
        else:
            # 兜底：尝试使用默认配置
            if isinstance(self.role_data, dict) and 'default' in self.role_data:
                role_config = self.role_data['default']
                print(f"⚠️ 未找到角色 {speaker} 的配置，使用默认配置")
            else:
                # 完全没有配置，生成静音音频作为占位
                print(f"❌ 未找到角色 {speaker} 的配置，且无默认配置")
                print(f"   生成静音音频作为占位（时长: {target_duration_ms or 1000}ms）")
                
                # 生成静音音频
                duration_ms = target_duration_ms if target_duration_ms else 1000
                silence = AudioSegment.silent(duration=duration_ms)
                silence.export(output_path, format="wav")
                
                return str(output_path)
        
        # 获取该角色的语速系数（优先使用角色配置，否则使用全局配置）
        role_speed_factor = role_config.get('speed_factor', self.speed_factor)
        
        # 获取声音配置
        voice = role_config.get('voice', '墨讲师')  # 默认使用墨讲师
        
        # 根据文本语言选择合适的模型
        model = self._select_qwen_model(text, role_config)
        
        # 构建请求参数
        params = {
            'model': model,
            'text': text,
            'sample_rate': 48000
        }
        
        # 如果指定了声音，尝试使用（某些模型支持）
        if voice and voice != 'default':
            # 对于支持多声音的模型，可以添加voice参数
            # params['voice'] = voice
            pass
        
        if speaker:
            print(f"🔄 调用Qwen TTS API [{speaker}, 声音={voice}, 语速={role_speed_factor}]: {text[:30]}...")
        else:
            print(f"🔄 调用Qwen TTS API [声音={voice}, 语速={role_speed_factor}]: {text[:30]}...")
        
        try:
            # 调用TTS API
            response = SpeechSynthesizer.call(**params)
            
            # 检查响应状态
            resp_dict = response.get_response()
            if resp_dict.get('status_code') == 200:
                # 获取音频数据
                audio_data = response.get_audio_data()
                
                if audio_data:
                    # 保存音频文件
                    with open(output_path, 'wb') as f:
                        f.write(audio_data)
                    
                    print(f"✅ 语音合成成功: {output_path.name}")
                    return str(output_path)
                else:
                    raise Exception("音频数据为空")
            else:
                raise Exception(f"API调用失败: {resp_dict}")
                
        except Exception as e:
            print(f"❌ Qwen TTS合成失败: {e}")
            raise
    
    def _select_qwen_model(self, text, role_config):
        """
        根据文本内容和角色配置选择合适的Qwen TTS模型
        
        Args:
            text: 要合成的文本
            role_config: 角色配置
            
        Returns:
            str: 模型名称
        """
        # 检查角色配置中是否指定了模型
        if 'model' in role_config:
            return role_config['model']
        
        # 检查全局text_lang设置
        if hasattr(self, 'text_lang'):
            if self.text_lang == 'ja':
                return 'sambert-zhiying-v1'  # 日语模型
            elif self.text_lang == 'en':
                return 'sambert-zhiying-v1'  # 英语也用这个多语言模型
            elif self.text_lang == 'zh':
                return 'sambert-zhichu-v1'   # 中文模型
        
        # 简单的语言检测
        import re
        
        # 检测日语字符（平假名、片假名、汉字）
        japanese_pattern = r'[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FAF]'
        if re.search(japanese_pattern, text):
            # 进一步检测是否包含假名（更确定是日语）
            kana_pattern = r'[\u3040-\u309F\u30A0-\u30FF]'
            if re.search(kana_pattern, text):
                print(f"   🎌 检测到日语文本，使用日语模型")
                return 'sambert-zhiying-v1'
        
        # 检测英语字符
        english_pattern = r'^[a-zA-Z\s\.,!?;:\'\"()-]+$'
        if re.match(english_pattern, text.strip()):
            print(f"   🇺🇸 检测到英语文本，使用多语言模型")
            return 'sambert-zhiying-v1'
        
        # 默认使用中文模型
        print(f"   🇨🇳 默认使用中文模型")
        return 'sambert-zhichu-v1'
    
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
            target_duration_ms = end_ms - start_ms
            
            # 合成语音（传递说话人信息和目标时长）
            speaker = subtitle.get('speaker', None)
            
            # 如果启用自动对齐，传入目标时长让TTS自动调整语速
            if self.auto_align:
                audio_path = self.synthesize_speech(subtitle['text'], i + 1, speaker, target_duration_ms)
            else:
                audio_path = self.synthesize_speech(subtitle['text'], i + 1, speaker)
            
            audio_files.append(audio_path)
            
            # 测量实际音频时长（方案B需要）
            from pydub import AudioSegment
            actual_audio = AudioSegment.from_file(audio_path)
            actual_duration_ms = len(actual_audio)
            
            # 构建字幕数据（用于双重变速）
            subtitle_data.append({
                'start_ms': start_ms,
                'end_ms': end_ms,
                'text': subtitle['text'],
                'audio_file': audio_path,
                'speaker': speaker,
                'original_duration_ms': target_duration_ms,  # 原始字幕时长
                'actual_duration_ms': actual_duration_ms     # 实际音频时长
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
                
                # 使用TimelineAdjuster动态调整时间轴（带语速限制）
                timeline_adjuster = TimelineAdjuster(
                    subtitles=subtitle_data,
                    audio_files=audio_files,
                    preserve_total_time=True,
                    target_speed_factor=self.speed_factor,
                    max_speed_limit=2.0  # 限制最大语速为2.0x
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
            print("\n🔗 使用传统方式拼接音频（强制保留原始间隔）...")
            print(f"   策略：顺序拼接，强制保留原始SRT间隔")
            
            audio_segments = []
            
            # 步骤0：添加第一条字幕前的初始空白
            if subtitle_data:
                first_start_ms = subtitle_data[0]['start_ms']
                if first_start_ms > 0:
                    print(f"   ⏱️  添加第一条字幕前的初始空白: {first_start_ms}ms ({first_start_ms/1000:.1f}秒)")
                    audio_segments.append(self.create_silence(first_start_ms))
            
            for i, subtitle_info in enumerate(subtitle_data):
                start_ms = subtitle_info['start_ms']  # 原始开始时间
                end_ms = subtitle_info['end_ms']      # 原始结束时间
                
                # 计算原始间隔（如果不是第一条）
                if i > 0:
                    prev_subtitle = subtitle_data[i - 1]
                    original_gap = start_ms - prev_subtitle['end_ms']
                    
                    if original_gap > 0:
                        if i <= 5:
                            print(f"   字幕{i}到{i+1}添加原始间隔: {original_gap}ms ({original_gap/1000:.1f}秒)")
                        audio_segments.append(self.create_silence(original_gap))
                
                # 加载配音音频
                audio = AudioSegment.from_wav(subtitle_info['audio_file'])
                audio_duration = len(audio)
                
                audio_segments.append(audio)
                
                # 关键修复：如果配音时长小于字幕时长，需要填充静音
                original_duration = end_ms - start_ms
                if audio_duration < original_duration:
                    padding_ms = original_duration - audio_duration
                    if i < 5:
                        print(f"   字幕{i+1}: 配音时长={audio_duration}ms, 原始时长={original_duration}ms, 填充={padding_ms}ms")
                    audio_segments.append(self.create_silence(padding_ms))
                else:
                    if i < 5:
                        print(f"   字幕{i+1}: 配音时长={audio_duration}ms ({audio_duration/1000:.1f}秒)")
                
                if i == 5:
                    print(f"   ... (省略后续字幕)")
            
            # 步骤N：验证音频总时长（不再需要手动添加尾部空白，因为已经在循环中处理了）
            if subtitle_data:
                last_subtitle = subtitle_data[-1]
                expected_duration_ms = last_subtitle['end_ms']  # 期望的总时长
                
                # 计算当前音频的实际时长
                actual_duration_ms = sum(len(seg) for seg in audio_segments)
                
                duration_diff = actual_duration_ms - expected_duration_ms
                
                if abs(duration_diff) < 100:  # 误差小于100ms
                    print(f"\n   ✅ 音频时长验证通过:")
                    print(f"      期望: {expected_duration_ms}ms ({expected_duration_ms/1000:.1f}秒)")
                    print(f"      实际: {actual_duration_ms}ms ({actual_duration_ms/1000:.1f}秒)")
                    print(f"      误差: {duration_diff:+d}ms")
                else:
                    print(f"\n   ⚠️  音频时长有差异:")
                    print(f"      期望: {expected_duration_ms}ms ({expected_duration_ms/1000:.1f}秒)")
                    print(f"      实际: {actual_duration_ms}ms ({actual_duration_ms/1000:.1f}秒)")
                    print(f"      差异: {duration_diff:+d}ms ({duration_diff/1000:+.1f}秒)")
                    
                    # 如果实际时长小于期望，添加尾部空白补齐
                    if actual_duration_ms < expected_duration_ms:
                        tail_padding = expected_duration_ms - actual_duration_ms
                        print(f"      🔧 添加尾部填充: {tail_padding}ms")
                        audio_segments.append(self.create_silence(tail_padding))
            
            # 拼接所有音频
            if not audio_segments:
                raise ValueError("没有音频片段可以拼接")
            
            final_audio = audio_segments[0]
            for segment in audio_segments[1:]:
                final_audio += segment
            
            # 导出最终音频
            output_path = self.output_dir / "dubbing_result.wav"
            final_duration = len(final_audio)
            print(f"\n💾 导出最终音频: {output_path}")
            print(f"   总时长: {final_duration}ms ({final_duration/1000:.1f}秒)")
            
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
                # 考虑语速调整和静音间隔
                updated_srt_path = self._generate_traditional_subtitle(
                    subtitle_data,
                    silence_duration_ms=int(self.silence_duration * 1000)
                )
        
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
        根据更新后的时间轴合并音频，并验证时长准确性
        
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
        
        # 用于验证的统计信息
        total_audio_duration = 0
        total_gap_duration = 0
        duration_mismatches = []
        
        for i, subtitle in enumerate(updated_subtitles):
            # 添加字幕前的静音间隙
            if subtitle['start_ms'] > current_time:
                gap = subtitle['start_ms'] - current_time
                print(f"  字幕 {i+1} 前添加静音: {gap}ms")
                audio_segments.append(AudioSegment.silent(duration=gap))
                current_time += gap
                total_gap_duration += gap
            
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
                    
                    # 记录时长差异（用于验证）
                    final_audio_duration = len(audio)
                    if abs(final_audio_duration - target_duration) > 50:
                        duration_mismatches.append({
                            'index': i+1,
                            'expected': target_duration,
                            'actual': final_audio_duration,
                            'diff': final_audio_duration - target_duration
                        })
                    
                    audio_segments.append(audio)
                    current_time += len(audio)
                    total_audio_duration += len(audio)
                    print(f"  字幕 {i+1}: 添加配音 {len(audio)}ms (预期: {target_duration}ms)")
                    
                except Exception as e:
                    print(f"  ⚠️ 字幕 {i+1} 加载音频失败: {e}，使用静音")
                    silence_duration = subtitle['end_ms'] - subtitle['start_ms']
                    audio_segments.append(AudioSegment.silent(duration=silence_duration))
                    current_time += silence_duration
                    total_audio_duration += silence_duration
            else:
                # 使用静音填充
                silence_duration = subtitle['end_ms'] - subtitle['start_ms']
                print(f"  字幕 {i+1}: 使用静音填充 {silence_duration}ms")
                audio_segments.append(AudioSegment.silent(duration=silence_duration))
                current_time += silence_duration
                total_audio_duration += silence_duration
        
        # 合并所有音频片段
        print(f"\n  🔗 合并 {len(audio_segments)} 个音频片段...")
        
        if not audio_segments:
            raise ValueError("没有音频片段可以拼接")
        
        # 使用第一个片段作为起点，然后逐个拼接
        final_audio = audio_segments[0]
        for segment in audio_segments[1:]:
            final_audio += segment
        
        # 导出最终音频
        output_path = self.output_dir / "dubbing_result.wav"
        print(f"  💾 导出最终音频: {output_path}")
        final_audio.export(str(output_path), format="wav")
        
        # 验证最终时长
        final_duration = len(final_audio)
        expected_duration = updated_subtitles[-1]['end_ms'] if updated_subtitles else 0
        
        print(f"\n📊 音频拼接验证:")
        print(f"   配音总时长: {total_audio_duration/1000:.2f}秒 ({total_audio_duration}ms)")
        print(f"   间隙总时长: {total_gap_duration/1000:.2f}秒 ({total_gap_duration}ms)")
        print(f"   预期总时长: {expected_duration/1000:.2f}秒 ({expected_duration}ms)")
        print(f"   实际总时长: {final_duration/1000:.2f}秒 ({final_duration}ms)")
        print(f"   差异: {abs(final_duration - expected_duration)/1000:.2f}秒 ({abs(final_duration - expected_duration)}ms)")
        
        if abs(final_duration - expected_duration) < 100:
            print(f"   ✅ 时长匹配良好（误差 < 0.1秒）")
        elif abs(final_duration - expected_duration) < 1000:
            print(f"   ⚠️ 时长有小幅差异（误差 < 1秒）")
        else:
            print(f"   ❌ 时长差异较大（误差 >= 1秒）")
        
        if duration_mismatches:
            print(f"\n   发现 {len(duration_mismatches)} 个音频时长不匹配:")
            for mismatch in duration_mismatches[:5]:
                print(f"      字幕{mismatch['index']}: 预期{mismatch['expected']}ms, 实际{mismatch['actual']}ms, 差异{mismatch['diff']:+d}ms")
            if len(duration_mismatches) > 5:
                print(f"      ... 还有 {len(duration_mismatches)-5} 个不匹配")
        
        return str(output_path)
    
    def _generate_precise_subtitle_from_segments(self, subtitle_data, min_gap_ms=300):
        """
        基于音频片段的实际时长生成精确的字幕文件（方案B）
        
        Args:
            subtitle_data: 字幕数据列表，每项包含 text, actual_duration_ms, speaker 等
            min_gap_ms: 片段之间的最小间隙（毫秒），默认300ms
            
        Returns:
            str: 生成的精确字幕文件路径
        """
        print(f"\n🎯 生成精确字幕（方案B - 基于实际音频时长）:")
        print(f"   字幕数量: {len(subtitle_data)}")
        print(f"   最小间隙: {min_gap_ms}ms")
        
        # 累积计算每条字幕的新时间轴
        precise_subtitles = []
        current_time_ms = 0
        
        for i, segment in enumerate(subtitle_data):
            # 获取实际音频时长
            actual_duration = segment.get('actual_duration_ms', 0)
            
            # 计算新的开始和结束时间
            new_start_ms = current_time_ms
            new_end_ms = current_time_ms + actual_duration
            
            precise_subtitles.append({
                'index': i + 1,
                'start_ms': new_start_ms,
                'end_ms': new_end_ms,
                'text': segment['text'],
                'speaker': segment.get('speaker', None),
                'original_start_ms': segment['start_ms'],
                'original_end_ms': segment['end_ms'],
                'actual_duration_ms': actual_duration
            })
            
            # 更新当前时间（加上音频时长和最小间隙）
            current_time_ms = new_end_ms + min_gap_ms
            
            # 打印调整信息（前5条）
            if i < 5:
                original_duration = segment['end_ms'] - segment['start_ms']
                print(f"   字幕{i+1}: {segment['start_ms']}ms → {new_start_ms}ms, "
                      f"时长 {original_duration}ms → {actual_duration}ms")
        
        # 保存精确字幕
        output_srt = self.output_dir / "precise_subtitles.srt"
        
        with open(output_srt, 'w', encoding='utf-8') as f:
            for subtitle in precise_subtitles:
                f.write(f"{subtitle['index']}\n")
                
                # 转换毫秒为SRT时间格式
                start_time = self._ms_to_srt_time(subtitle['start_ms'])
                end_time = self._ms_to_srt_time(subtitle['end_ms'])
                
                f.write(f"{start_time} --> {end_time}\n")
                
                # 如果有说话人标记，保留它
                if subtitle['speaker']:
                    f.write(f"[{subtitle['speaker']}] {subtitle['text']}\n\n")
                else:
                    f.write(f"{subtitle['text']}\n\n")
        
        # 统计信息
        total_audio_duration = sum(s['actual_duration_ms'] for s in precise_subtitles)
        total_gaps = (len(precise_subtitles) - 1) * min_gap_ms
        final_duration = precise_subtitles[-1]['end_ms'] + min_gap_ms if precise_subtitles else 0
        
        print(f"\n✅ 精确字幕生成完成:")
        print(f"   总音频时长: {total_audio_duration/1000:.2f}秒")
        print(f"   总间隙时长: {total_gaps/1000:.2f}秒")
        print(f"   最终总时长: {final_duration/1000:.2f}秒")
        print(f"   保存位置: {output_srt}")
        
        return str(output_srt)
    
    def _adjust_subtitle_timeline_for_audio(self, original_srt_path, audio_duration_ms):
        """
        根据实际音频时长自动调整字幕时间轴（方案A）
        当TTS音频比原字幕时间轴长时，按比例拉伸字幕时间轴
        
        Args:
            original_srt_path: 原始SRT文件路径
            audio_duration_ms: 实际音频总时长（毫秒）
            
        Returns:
            str: 调整后的SRT文件路径，如果不需要调整则返回None
        """
        # 解析原始SRT获取原始时间轴
        print(f"\n🔍 解析字幕文件: {original_srt_path}")
        
        # 临时保存当前的srt_path，然后使用传入的路径
        original_srt_path_backup = self.srt_path
        self.srt_path = original_srt_path
        
        subtitles = self.parse_srt()
        
        # 恢复原来的srt_path
        self.srt_path = original_srt_path_backup
        
        if not subtitles:
            print(f"⚠️ 未能解析字幕文件")
            return None
        
        print(f"✅ 成功解析 {len(subtitles)} 条字幕")
        
        # 获取原始字幕的总时长
        original_duration_ms = self.time_to_ms(subtitles[-1]['end'])
        
        # 判断是否需要调整（音频比字幕长10%以上）
        if audio_duration_ms <= original_duration_ms * 1.1:
            print(f"\n📊 字幕时间轴无需调整:")
            print(f"   原始字幕时长: {original_duration_ms/1000:.2f}秒")
            print(f"   实际音频时长: {audio_duration_ms/1000:.2f}秒")
            print(f"   差异: {(audio_duration_ms - original_duration_ms)/1000:.2f}秒 (< 10%)")
            return None
        
        # 计算拉伸比例
        stretch_ratio = audio_duration_ms / original_duration_ms
        
        print(f"\n🎯 自动调整字幕时间轴（方案A）:")
        print(f"   原始字幕时长: {original_duration_ms/1000:.2f}秒 ({original_duration_ms}ms)")
        print(f"   实际音频时长: {audio_duration_ms/1000:.2f}秒 ({audio_duration_ms}ms)")
        print(f"   拉伸比例: {stretch_ratio:.2f}x")
        
        # 调整每条字幕的时间戳
        adjusted_subtitles = []
        for subtitle in subtitles:
            start_ms = self.time_to_ms(subtitle['start'])
            end_ms = self.time_to_ms(subtitle['end'])
            
            # 按比例拉伸
            new_start_ms = int(start_ms * stretch_ratio)
            new_end_ms = int(end_ms * stretch_ratio)
            
            adjusted_subtitles.append({
                'index': subtitle['index'],
                'start_ms': new_start_ms,
                'end_ms': new_end_ms,
                'text': subtitle['text'],
                'speaker': subtitle.get('speaker', None)
            })
        
        # 保存调整后的字幕
        output_srt = self.output_dir / "adjusted_subtitles.srt"
        
        with open(output_srt, 'w', encoding='utf-8') as f:
            for subtitle in adjusted_subtitles:
                f.write(f"{subtitle['index']}\n")
                
                # 转换毫秒为SRT时间格式
                start_time = self._ms_to_srt_time(subtitle['start_ms'])
                end_time = self._ms_to_srt_time(subtitle['end_ms'])
                
                f.write(f"{start_time} --> {end_time}\n")
                
                # 如果有说话人标记，保留它
                if subtitle['speaker']:
                    f.write(f"[{subtitle['speaker']}] {subtitle['text']}\n\n")
                else:
                    f.write(f"{subtitle['text']}\n\n")
        
        # 验证调整结果
        final_duration_ms = adjusted_subtitles[-1]['end_ms']
        print(f"\n✅ 字幕时间轴调整完成:")
        print(f"   调整后总时长: {final_duration_ms/1000:.2f}秒 ({final_duration_ms}ms)")
        print(f"   与音频差异: {abs(final_duration_ms - audio_duration_ms)}ms")
        print(f"   保存位置: {output_srt}")
        
        return str(output_srt)
    
    def _generate_traditional_subtitle(self, subtitle_data, silence_duration_ms=500):
        """
        传统模式：根据实际音频拼接逻辑生成字幕文件（方案D）
        
        这个方法完全模拟音频拼接的逻辑，确保字幕和音频完全同步：
        1. 累积计算时间轴
        2. 添加原始间隙（从SRT读取）
        3. 添加音频片段（使用实际时长）
        
        Args:
            subtitle_data: 字幕数据列表，每项包含 text, actual_duration_ms, start_ms, end_ms 等
            silence_duration_ms: 字幕间的静音间隔（毫秒），默认500ms（未使用，保留原始间隔）
            
        Returns:
            str: 生成的字幕文件路径
        """
        print(f"\n🎯 生成传统模式字幕（方案D - 修复版）:")
        print(f"   字幕数量: {len(subtitle_data)}")
        print(f"   策略: 累积计算时间轴，保持原始SRT间隔")
        print(f"   自动对齐: {self.auto_align}")
        
        # 累积计算每条字幕的新时间轴（完全模拟音频拼接逻辑）
        traditional_subtitles = []
        
        # 步骤0：处理第一条字幕前的初始空白时间
        if subtitle_data:
            first_start_ms = subtitle_data[0]['start_ms']
            if first_start_ms > 0:
                current_time_ms = first_start_ms
                print(f"   ⏱️  第一条字幕前的初始空白: {first_start_ms}ms ({first_start_ms/1000:.1f}秒)")
            else:
                current_time_ms = 0
        else:
            current_time_ms = 0
        
        for i, segment in enumerate(subtitle_data):
            # 获取原始时间信息
            original_start_ms = segment['start_ms']
            original_end_ms = segment['end_ms']
            original_duration_ms = original_end_ms - original_start_ms
            
            # 步骤1：计算并添加原始间隔（如果不是第一条）
            if i > 0:
                prev_segment = subtitle_data[i - 1]
                original_gap = original_start_ms - prev_segment['end_ms']
                
                if original_gap > 0:
                    # 添加原始间隔到累积时间
                    current_time_ms += original_gap
                    if i <= 5:
                        print(f"   字幕{i}到{i+1}添加原始间隔: {original_gap}ms ({original_gap/1000:.1f}秒)")
            
            # 步骤2：获取实际音频时长
            actual_duration_ms = segment.get('actual_duration_ms', original_duration_ms)
            
            # 步骤3：计算新的时间轴（使用累积时间）
            new_start_ms = current_time_ms
            new_end_ms = current_time_ms + actual_duration_ms
            
            traditional_subtitles.append({
                'index': i + 1,
                'start_ms': new_start_ms,
                'end_ms': new_end_ms,
                'text': segment['text'],
                'speaker': segment.get('speaker', None),
                'original_start_ms': original_start_ms,
                'original_end_ms': original_end_ms,
                'original_duration_ms': original_duration_ms,
                'actual_duration_ms': actual_duration_ms
            })
            
            # 步骤4：更新累积时间
            current_time_ms = new_end_ms
            
            # 打印调整信息（前5条）
            if i < 5:
                print(f"   字幕{i+1}: 开始={new_start_ms}ms ({new_start_ms/1000:.2f}s), "
                      f"结束={new_end_ms}ms ({new_end_ms/1000:.2f}s), "
                      f"时长={actual_duration_ms}ms ({actual_duration_ms/1000:.2f}s)")
                print(f"           原始: {original_start_ms}ms-{original_end_ms}ms "
                      f"(时长{original_duration_ms}ms)")
            elif i == 5:
                print(f"   ... (省略后续字幕)")
        
        # 保存字幕
        output_srt = self.output_dir / "traditional_subtitles.srt"
        
        with open(output_srt, 'w', encoding='utf-8') as f:
            for subtitle in traditional_subtitles:
                f.write(f"{subtitle['index']}\n")
                
                # 转换毫秒为SRT时间格式
                start_time = self._ms_to_srt_time(subtitle['start_ms'])
                end_time = self._ms_to_srt_time(subtitle['end_ms'])
                
                f.write(f"{start_time} --> {end_time}\n")
                
                # 如果有说话人标记，保留它
                if subtitle['speaker']:
                    f.write(f"[{subtitle['speaker']}] {subtitle['text']}\n\n")
                else:
                    f.write(f"{subtitle['text']}\n\n")
        
        # 统计信息
        total_subtitle_duration = sum(s['actual_duration_ms'] for s in traditional_subtitles)
        final_duration = current_time_ms  # 使用累积时间作为最终时长
        
        # 计算总间隔
        total_gaps = 0
        for i in range(1, len(subtitle_data)):
            original_gap = subtitle_data[i]['start_ms'] - subtitle_data[i-1]['end_ms']
            if original_gap > 0:
                total_gaps += original_gap
        
        original_total_duration = subtitle_data[-1]['end_ms'] if subtitle_data else 0
        
        print(f"\n✅ 传统模式字幕生成完成:")
        print(f"   原始SRT总时长: {original_total_duration/1000:.2f}秒 ({original_total_duration}ms)")
        print(f"   配音总时长: {total_subtitle_duration/1000:.2f}秒 ({total_subtitle_duration}ms)")
        print(f"   间隔总时长: {total_gaps/1000:.2f}秒 ({total_gaps}ms)")
        print(f"   最终总时长: {final_duration/1000:.2f}秒 ({final_duration}ms)")
        print(f"   时长变化: {(final_duration - original_total_duration)/1000:+.2f}秒")
        
        # 验证间隔是否保持
        if len(traditional_subtitles) > 1:
            print(f"\n🔍 间隔验证（前3个）:")
            for i in range(1, min(4, len(traditional_subtitles))):
                new_gap = traditional_subtitles[i]['start_ms'] - traditional_subtitles[i-1]['end_ms']
                original_gap = subtitle_data[i]['start_ms'] - subtitle_data[i-1]['end_ms']
                match = "✅" if abs(new_gap - original_gap) < 1 else "❌"
                print(f"   字幕{i}到{i+1}: 原始间隔={original_gap}ms, 新间隔={new_gap}ms {match}")
        
        print(f"   保存位置: {output_srt}")
        
        return str(output_srt)
    
    def _save_updated_srt(self, subtitles):
        """
        保存更新后的字幕文件，并验证时间轴
        
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
        
        # 验证时间轴
        print(f"\n📊 字幕时间轴验证:")
        total_subtitle_duration = sum(s['end_ms'] - s['start_ms'] for s in subtitles)
        total_timeline = subtitles[-1]['end_ms'] if subtitles else 0
        
        print(f"   字幕总数: {len(subtitles)}")
        print(f"   字幕总时长: {total_subtitle_duration/1000:.2f}秒 ({total_subtitle_duration}ms)")
        print(f"   时间轴总长: {total_timeline/1000:.2f}秒 ({total_timeline}ms)")
        print(f"   间隙总时长: {(total_timeline - total_subtitle_duration)/1000:.2f}秒 ({total_timeline - total_subtitle_duration}ms)")
        
        # 检查异常
        warnings = []
        for i, sub in enumerate(subtitles):
            duration = sub['end_ms'] - sub['start_ms']
            if duration < 100:
                warnings.append(f"   ⚠️ 字幕{i+1}时长过短: {duration}ms")
            if i > 0:
                gap = sub['start_ms'] - subtitles[i-1]['end_ms']
                if gap < 0:
                    warnings.append(f"   ⚠️ 字幕{i}和{i+1}重叠: {abs(gap)}ms")
                elif gap > 5000:
                    warnings.append(f"   ⚠️ 字幕{i}和{i+1}间隙过大: {gap}ms ({gap/1000:.1f}秒)")
        
        if warnings:
            print(f"\n   发现 {len(warnings)} 个警告:")
            for warning in warnings[:5]:  # 只显示前5个
                print(warning)
            if len(warnings) > 5:
                print(f"   ... 还有 {len(warnings)-5} 个警告")
        else:
            print(f"   ✅ 未发现异常")
        
        print(f"\n💾 保存更新后的字幕: {output_srt}")
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
