"""
SRT字幕翻译模块
使用大语言模型翻译SRT字幕文件
支持：阿里云通义千问、OpenAI、DeepSeek、本地Ollama
"""
import re
import time
from pathlib import Path
from typing import List, Optional, Callable
from dataclasses import dataclass, field
import requests


@dataclass
class SubtitleEntry:
    """字幕条目"""
    index: int
    start_time: str
    end_time: str
    text: str
    translated_text: str = ""
    speaker: str = ""


class SRTParser:
    """SRT文件解析器 - 支持多种格式"""
    
    # 时间轴正则
    TIME_PATTERN = re.compile(
        r'(\d{1,2}:\d{2}:\d{2}[,\.]\d{1,3})\s*-->\s*(\d{1,2}:\d{2}:\d{2}[,\.]\d{1,3})'
    )
    
    @classmethod
    def parse(cls, content: str) -> List[SubtitleEntry]:
        """解析SRT内容为字幕条目列表"""
        entries = []
        
        # 移除BOM标记
        if content.startswith('\ufeff'):
            content = content[1:]
        
        # 统一换行符
        content = content.replace('\r\n', '\n').replace('\r', '\n')
        
        # 按行解析（支持无空行分隔的格式）
        lines = content.split('\n')
        
        print(f"[SRT解析] 文件共 {len(lines)} 行")
        
        i = 0
        entry_count = 0
        
        while i < len(lines):
            line = lines[i].strip()
            
            # 跳过空行
            if not line:
                i += 1
                continue
            
            # 尝试解析序号（纯数字行）
            index = None
            if line.isdigit():
                index = int(line)
                i += 1
                if i >= len(lines):
                    break
                line = lines[i].strip()
            
            # 尝试解析时间轴
            time_match = cls.TIME_PATTERN.search(line)
            if not time_match:
                # 不是时间轴，跳过这行
                i += 1
                continue
            
            start_time = time_match.group(1)
            end_time = time_match.group(2)
            
            # 如果没有序号，使用计数器
            if index is None:
                index = entry_count + 1
            
            # 读取文本行（下一行）
            i += 1
            text_lines = []
            
            while i < len(lines):
                text_line = lines[i].strip()
                
                # 空行表示当前字幕块结束
                if not text_line:
                    i += 1
                    break
                
                # 如果遇到纯数字（下一个序号）或时间轴，说明当前块结束
                if text_line.isdigit() or cls.TIME_PATTERN.search(text_line):
                    break
                
                text_lines.append(text_line)
                i += 1
            
            # 合并文本
            if text_lines:
                text = '\n'.join(text_lines)
                
                # 移除HTML标签
                text = re.sub(r'<[^>]+>', '', text)
                
                # 提取说话人标识
                speaker = ""
                # 支持格式: [spk01]: 文本 或 [角色]: 文本
                speaker_match = re.match(r'^\[([^\]]+)\]:\s*(.*)$', text)
                if speaker_match:
                    speaker = speaker_match.group(1).strip()
                    text = speaker_match.group(2).strip()
                
                if text:
                    entries.append(SubtitleEntry(
                        index=index,
                        start_time=start_time,
                        end_time=end_time,
                        text=text,
                        speaker=speaker
                    ))
                    entry_count += 1
        
        print(f"[SRT解析] 成功解析 {len(entries)} 条字幕")
        
        # 打印前3条用于调试
        for entry in entries[:3]:
            print(f"  [{entry.index}] {entry.start_time} --> {entry.end_time}")
            print(f"      Speaker: {entry.speaker}, Text: {entry.text[:50]}...")
        
        return entries
    
    @staticmethod
    def to_srt(entries: List[SubtitleEntry], use_translated: bool = True, keep_speaker: bool = True) -> str:
        """将字幕条目列表转换为SRT格式"""
        lines = []
        for i, entry in enumerate(entries, 1):
            text = entry.translated_text if use_translated and entry.translated_text else entry.text
            
            # 如果有说话人标识，添加回去
            if keep_speaker and entry.speaker:
                text = f"[{entry.speaker}]: {text}"
            
            lines.append(str(i))
            lines.append(f"{entry.start_time} --> {entry.end_time}")
            lines.append(text)
            lines.append("")  # 空行分隔
        
        return '\n'.join(lines)


class LLMTranslator:
    """大语言模型翻译器"""
    
    SUPPORTED_LANGUAGES = {
        "zh": "中文",
        "en": "English",
        "ja": "日本語",
        "ko": "한국어",
        "fr": "Français",
        "de": "Deutsch",
        "es": "Español",
        "ru": "Русский",
        "pt": "Português",
        "it": "Italiano",
        "ar": "العربية",
        "th": "ไทย",
        "vi": "Tiếng Việt"
    }
    
    def __init__(
        self,
        api_key: str,
        api_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
        model: str = "qwen-plus",
        target_lang: str = "zh",
        is_ollama: bool = False
    ):
        self.api_key = api_key
        self.api_url = api_url
        self.model = model
        self.target_lang = target_lang
        self.target_lang_name = self.SUPPORTED_LANGUAGES.get(target_lang, target_lang)
        self.is_ollama = is_ollama
    
    def translate_batch(
        self,
        texts: List[str],
        batch_size: int = 10,
        progress_callback: Optional[Callable[[int, int, str], None]] = None
    ) -> List[str]:
        """批量翻译文本"""
        results = []
        total = len(texts)
        
        for i in range(0, total, batch_size):
            batch = texts[i:i + batch_size]
            batch_results = self._translate_batch_request(batch)
            results.extend(batch_results)
            
            if progress_callback:
                progress = min(i + batch_size, total)
                progress_callback(progress, total, f"已翻译 {progress}/{total} 条")
            
            # 避免API限流
            if not self.is_ollama and i + batch_size < total:
                time.sleep(0.5)
        
        return results
    
    def _translate_batch_request(self, texts: List[str]) -> List[str]:
        """发送批量翻译请求"""
        numbered_texts = "\n".join([f"{i+1}. {text}" for i, text in enumerate(texts)])
        
        prompt = f"""请将以下字幕文本翻译成{self.target_lang_name}。

要求：
1. 保持原文的语气和风格
2. 翻译要自然流畅，符合目标语言的表达习惯
3. 保持编号格式，每行一条翻译结果
4. 只输出翻译结果，不要添加任何解释
5. 人名直接翻译或音译，不要使用括号标注原文读音或其他形式的注释
6. 不要在翻译结果中添加任何括号、注音或解释性文字

原文：
{numbered_texts}

翻译结果："""

        if self.is_ollama:
            headers = {"Content-Type": "application/json"}
        else:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
        
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "你是一个专业的字幕翻译专家，擅长将各种语言的字幕翻译成目标语言，保持原文的语气和风格。翻译时直接输出译文，人名直接翻译或音译，绝对不要使用括号添加原文读音或任何注释。"},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.3,
            "stream": False
        }
        
        if self.is_ollama:
            payload["options"] = {"num_predict": 4096}
        else:
            payload["max_tokens"] = 4096
        
        try:
            print(f"[翻译] 请求API: {self.api_url}, 模型: {self.model}")
            response = requests.post(
                self.api_url,
                headers=headers,
                json=payload,
                timeout=120
            )
            response.raise_for_status()
            
            result = response.json()
            
            if "choices" in result:
                content = result["choices"][0]["message"]["content"]
            elif "message" in result:
                content = result["message"]["content"]
            else:
                print(f"[翻译] 未知响应格式: {result}")
                return texts
            
            return self._parse_translation_result(content, len(texts))
            
        except requests.exceptions.RequestException as e:
            print(f"[翻译] 请求失败: {e}")
            return texts
        except (KeyError, IndexError) as e:
            print(f"[翻译] 解析结果失败: {e}")
            return texts
    
    def _parse_translation_result(self, content: str, expected_count: int) -> List[str]:
        """解析翻译结果"""
        lines = content.strip().split('\n')
        results = []
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # 移除编号前缀
            match = re.match(r'^\d+[\.\)、:：]\s*(.+)$', line)
            if match:
                results.append(match.group(1).strip())
            else:
                results.append(line)
        
        while len(results) < expected_count:
            results.append("")
        
        return results[:expected_count]


class SRTTranslator:
    """SRT字幕翻译器"""
    
    def __init__(
        self,
        api_key: str,
        api_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
        model: str = "qwen-plus",
        target_lang: str = "zh",
        batch_size: int = 10,
        is_ollama: bool = False
    ):
        self.translator = LLMTranslator(
            api_key=api_key,
            api_url=api_url,
            model=model,
            target_lang=target_lang,
            is_ollama=is_ollama
        )
        self.batch_size = batch_size
    
    def translate_file(
        self,
        input_path: str,
        output_path: str,
        progress_callback: Optional[Callable[[int, int, str], None]] = None
    ) -> str:
        """翻译SRT文件"""
        content = None
        encodings = ['utf-8', 'utf-8-sig', 'gbk', 'gb2312', 'latin-1', 'cp1252']
        
        for encoding in encodings:
            try:
                with open(input_path, 'r', encoding=encoding) as f:
                    content = f.read()
                print(f"[SRT翻译] 使用编码 {encoding} 读取文件成功")
                break
            except (UnicodeDecodeError, UnicodeError):
                continue
        
        if content is None:
            raise ValueError(f"无法读取文件，尝试了以下编码: {encodings}")
        
        print(f"[SRT翻译] 文件内容长度: {len(content)} 字符")
        print(f"[SRT翻译] 文件前300字符:\n{content[:300]}")
        
        entries = SRTParser.parse(content)
        if not entries:
            raise ValueError("无法解析SRT文件或文件为空，请检查文件格式")
        
        print(f"[SRT翻译] 解析到 {len(entries)} 条字幕")
        
        texts = [entry.text for entry in entries]
        
        translated_texts = self.translator.translate_batch(
            texts,
            batch_size=self.batch_size,
            progress_callback=progress_callback
        )
        
        for entry, translated in zip(entries, translated_texts):
            entry.translated_text = translated
        
        output_content = SRTParser.to_srt(entries, use_translated=True)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(output_content)
        
        return output_path
    
    def translate_content(
        self,
        content: str,
        progress_callback: Optional[Callable[[int, int, str], None]] = None
    ) -> str:
        """翻译SRT内容"""
        entries = SRTParser.parse(content)
        if not entries:
            raise ValueError("无法解析SRT内容或内容为空")
        
        texts = [entry.text for entry in entries]
        
        translated_texts = self.translator.translate_batch(
            texts,
            batch_size=self.batch_size,
            progress_callback=progress_callback
        )
        
        for entry, translated in zip(entries, translated_texts):
            entry.translated_text = translated
        
        return SRTParser.to_srt(entries, use_translated=True)


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="SRT字幕翻译工具")
    parser.add_argument("input", help="输入SRT文件路径")
    parser.add_argument("output", help="输出SRT文件路径")
    parser.add_argument("--api-key", default="", help="API密钥")
    parser.add_argument("--api-url", default="https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions")
    parser.add_argument("--model", default="qwen-plus")
    parser.add_argument("--target-lang", default="zh")
    parser.add_argument("--batch-size", type=int, default=10)
    parser.add_argument("--ollama", action="store_true")
    
    args = parser.parse_args()
    
    def progress_callback(current, total, message):
        print(f"PROGRESS:{int(current/total*100)}%")
        print(message)
    
    translator = SRTTranslator(
        api_key=args.api_key,
        api_url=args.api_url,
        model=args.model,
        target_lang=args.target_lang,
        batch_size=args.batch_size,
        is_ollama=args.ollama
    )
    
    result = translator.translate_file(
        args.input,
        args.output,
        progress_callback=progress_callback
    )
    
    print(f"翻译完成: {result}")
