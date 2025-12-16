import json
import os
import re

def remove_punctuation(text):
    """去除文本句末的标点符号（保留句中标点）"""
    # 句末标点（中英文）
    ending_punctuation = '。！？.!?;；…'
    
    # 去除句末的标点符号
    text = text.strip()
    while text and text[-1] in ending_punctuation:
        text = text[:-1].strip()
    
    return text

def seconds_to_srt_time(seconds):
    """将秒数转换为 SRT 时间格式: HH:MM:SS,mmm"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"

def convert_json_to_srt(json_file, output_srt=None):
    """转换 JSON 对话文件为 SRT 字幕"""
    
    # 读取 JSON 文件
    with open(json_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # 自动命名输出文件
    if output_srt is None:
        output_srt = os.path.splitext(json_file)[0] + '.srt'
    
    srt_lines = []
    subtitle_index = 1
    
    # 按开始时间排序（根据您的数据，似乎已经排序）
    sorted_data = sorted(data, key=lambda x: x['开始时间(秒)'])
    
    for item in sorted_data:
        text = item.get('说话内容', '').strip()
        
        # 跳过空文本或无效内容
        if not text or text in ['', 'N/A', '无']:
            continue
        
        # 去除标点符号
        text = remove_punctuation(text)
        
        # 再次检查去除标点后是否为空
        if not text:
            continue
        
        speaker = item.get('说话人', '')
        start_time = item['开始时间(秒)']
        end_time = item['结束时间(秒)']
        
        # 生成 SRT 格式
        srt_lines.append(str(subtitle_index))
        srt_lines.append(f"{seconds_to_srt_time(start_time)} --> {seconds_to_srt_time(end_time)}")
        
        # 添加说话人标签（可选）
        if speaker and speaker != 'unknown':
            srt_lines.append(f"[{speaker}] {text}")
        else:
            srt_lines.append(text)
        
        srt_lines.append("")  # 空行分隔
        subtitle_index += 1
    
    # 写入 SRT 文件
    with open(output_srt, 'w', encoding='utf-8') as f:
        f.write('\n'.join(srt_lines))
    
    print(f"✓ 转换完成: {output_srt}")
    print(f"  共生成 {subtitle_index-1} 条字幕")
    
    return output_srt

# 使用示例
if __name__ == "__main__":
    # 替换为您的 JSON 文件路径
    json_file = "字幕说话人分配结果.json"  # 您的文件名
    
    if os.path.exists(json_file):
        convert_json_to_srt(json_file)
    else:
        print(f"错误: 文件 {json_file} 不存在")