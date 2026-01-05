"""
SRT字幕清理工具
去除说话人标识，为视频字幕烧录做准备
"""

import re
from pathlib import Path
from typing import Optional


class SrtCleaner:
    """SRT字幕清理器"""
    
    def __init__(self):
        # 匹配说话人标识的正则表达式
        # 匹配格式：[spk01]:, [spk01] :, [spk00]:, [spk00] : 等（支持空格）
        # \s* 表示匹配0个或多个空白字符
        self.speaker_pattern = re.compile(r'\[spk\d+\]\s*:\s*')
        
        # 额外的清理模式，以防有其他格式
        self.additional_patterns = [
            re.compile(r'\[speaker\d+\]\s*:\s*', re.IGNORECASE),  # [speaker01]:
            re.compile(r'\[说话人\d+\]\s*:\s*'),                    # [说话人01]:
            re.compile(r'\[\w+\d*\]\s*:\s*'),                      # 通用格式 [xxx]:
        ]
    
    def clean_srt_content(self, content: str) -> str:
        """
        清理SRT内容，去除说话人标识
        
        Args:
            content: 原始SRT内容
            
        Returns:
            清理后的SRT内容
        """
        lines = content.split('\n')
        cleaned_lines = []
        
        for line in lines:
            # 首先使用主要的说话人模式清理
            cleaned_line = self.speaker_pattern.sub('', line)
            
            # 然后使用额外的模式进行清理
            for pattern in self.additional_patterns:
                cleaned_line = pattern.sub('', cleaned_line)
            
            cleaned_lines.append(cleaned_line)
        
        return '\n'.join(cleaned_lines)
    
    def clean_srt_file(self, input_path: str, output_path: Optional[str] = None) -> str:
        """
        清理SRT文件
        
        Args:
            input_path: 输入SRT文件路径
            output_path: 输出SRT文件路径（可选，默认添加_cleaned后缀）
            
        Returns:
            清理后的SRT文件路径
        """
        input_path = Path(input_path)
        
        if not input_path.exists():
            raise FileNotFoundError(f"SRT文件不存在: {input_path}")
        
        # 确定输出路径
        if output_path is None:
            output_path = input_path.parent / f"{input_path.stem}_cleaned{input_path.suffix}"
        else:
            output_path = Path(output_path)
        
        print(f"🧹 清理SRT文件:")
        print(f"   输入: {input_path}")
        print(f"   输出: {output_path}")
        
        try:
            # 读取原始文件
            with open(input_path, 'r', encoding='utf-8') as f:
                original_content = f.read()
            
            # 清理内容
            cleaned_content = self.clean_srt_content(original_content)
            
            # 保存清理后的文件
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(cleaned_content)
            
            print(f"✅ SRT清理完成: {output_path}")
            return str(output_path)
            
        except Exception as e:
            print(f"❌ SRT清理失败: {e}")
            raise
    
    def preview_cleaning(self, input_path: str, lines_to_show: int = 10) -> None:
        """
        预览清理效果
        
        Args:
            input_path: 输入SRT文件路径
            lines_to_show: 显示的行数
        """
        input_path = Path(input_path)
        
        if not input_path.exists():
            raise FileNotFoundError(f"SRT文件不存在: {input_path}")
        
        with open(input_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        lines = content.split('\n')
        cleaned_content = self.clean_srt_content(content)
        cleaned_lines = cleaned_content.split('\n')
        
        print(f"\n🔍 SRT清理预览 (前{lines_to_show}行):")
        print("="*60)
        
        for i in range(min(lines_to_show, len(lines))):
            if i < len(lines) and i < len(cleaned_lines):
                original = lines[i]
                cleaned = cleaned_lines[i]
                
                if original != cleaned:
                    print(f"行 {i+1}:")
                    print(f"  原始: {original}")
                    print(f"  清理: {cleaned}")
                    print()


# 使用示例
if __name__ == "__main__":
    cleaner = SrtCleaner()
    
    # 预览清理效果
    try:
        cleaner.preview_cleaning("srt_ep/lao1.srt")
        
        # 执行清理
        cleaned_file = cleaner.clean_srt_file("srt_ep/lao1.srt")
        print(f"\n✅ 清理完成: {cleaned_file}")
        
    except Exception as e:
        print(f"❌ 处理失败: {e}")