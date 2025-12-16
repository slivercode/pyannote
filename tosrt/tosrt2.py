#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
将带说话人信息的JSON字幕文件转换为SRT格式
支持按说话人分组输出或合并输出
"""

import json
import os
import argparse
from collections import defaultdict


def seconds_to_srt_time(seconds):
    """将秒数转换为 SRT 时间格式: HH:MM:SS,mmm"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def load_json_subtitles(json_file):
    """加载JSON字幕文件"""
    with open(json_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return data


def generate_srt_content(subtitles, include_speaker=True):
    """
    生成SRT格式内容
    
    Args:
        subtitles: 字幕列表
        include_speaker: 是否在文本中包含说话人标识
    
    Returns:
        SRT格式的字符串
    """
    srt_lines = []
    subtitle_index = 1
    
    for item in subtitles:
        text = item.get('文本内容', '').strip()
        
        # 跳过空文本
        if not text:
            continue
        
        speaker = item.get('说话人', '')
        start_time = item['开始时间(秒)']
        end_time = item['结束时间(秒)']
        
        # 生成 SRT 格式
        srt_lines.append(str(subtitle_index))
        srt_lines.append(f"{seconds_to_srt_time(start_time)} --> {seconds_to_srt_time(end_time)}")
        
        # 添加说话人标签（可选）
        if include_speaker and speaker and speaker != 'UNKNOWN':
            srt_lines.append(f"[{speaker}] {text}")
        else:
            srt_lines.append(text)
        
        srt_lines.append("")  # 空行分隔
        subtitle_index += 1
    
    return '\n'.join(srt_lines)


def group_by_speaker(subtitles):
    """按说话人分组字幕"""
    grouped = defaultdict(list)
    for sub in subtitles:
        speaker = sub['说话人']
        grouped[speaker].append(sub)
    return dict(grouped)


def save_srt_file(content, output_path):
    """保存SRT文件"""
    os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else '.', exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"✅ 已保存: {output_path}")


def convert_json_to_srt(json_file, output_srt=None, split_by_speaker=False, 
                        output_dir=None, no_speaker=False, exclude_unknown=False):
    """
    转换JSON字幕为SRT格式
    
    Args:
        json_file: 输入的JSON文件路径
        output_srt: 输出的SRT文件路径（合并模式）
        split_by_speaker: 是否按说话人分组输出
        output_dir: 输出目录（分组模式）
        no_speaker: 不在字幕文本中包含说话人标识
        exclude_unknown: 排除说话人为UNKNOWN的字幕
    """
    
    # 读取JSON文件
    print(f"📖 读取JSON文件: {json_file}")
    subtitles = load_json_subtitles(json_file)
    print(f"✅ 成功加载 {len(subtitles)} 条字幕")
    
    # 过滤UNKNOWN说话人（如果需要）
    if exclude_unknown:
        original_count = len(subtitles)
        subtitles = [s for s in subtitles if s['说话人'] != 'UNKNOWN']
        print(f"🔍 已排除 {original_count - len(subtitles)} 条UNKNOWN字幕，剩余 {len(subtitles)} 条")
    
    # 统计说话人
    speakers = set(s['说话人'] for s in subtitles)
    print(f"\n👥 检测到 {len(speakers)} 个说话人: {', '.join(sorted(speakers))}")
    
    # 按说话人分组模式
    if split_by_speaker:
        print("\n📂 按说话人分组输出...")
        
        # 确定输出目录
        if output_dir:
            out_dir = output_dir
        else:
            out_dir = os.path.join(os.path.dirname(json_file), 'speaker_srt')
        
        os.makedirs(out_dir, exist_ok=True)
        print(f"📁 输出目录: {out_dir}")
        
        # 按说话人分组
        grouped = group_by_speaker(subtitles)
        
        # 为每个说话人生成SRT文件
        for speaker, speaker_subs in sorted(grouped.items()):
            # 按时间排序
            speaker_subs.sort(key=lambda x: x['开始时间(秒)'])
            
            # 生成SRT内容（分组模式下不需要在文本中重复说话人标识）
            srt_content = generate_srt_content(speaker_subs, include_speaker=False)
            
            # 保存文件
            output_path = os.path.join(out_dir, f"{speaker}_字幕.srt")
            save_srt_file(srt_content, output_path)
            print(f"  - {speaker}: {len(speaker_subs)} 条字幕")
        
        print(f"\n✅ 完成！共生成 {len(grouped)} 个SRT文件")
    
    # 合并模式
    else:
        print("\n📝 生成合并的SRT文件...")
        
        # 按时间排序
        subtitles.sort(key=lambda x: x['开始时间(秒)'])
        
        # 生成SRT内容
        include_speaker = not no_speaker
        srt_content = generate_srt_content(subtitles, include_speaker=include_speaker)
        
        # 确定输出路径
        if output_srt:
            output_path = output_srt
        else:
            # 默认输出路径：与JSON文件同名，扩展名改为.srt
            base_name = os.path.splitext(json_file)[0]
            output_path = f"{base_name}.srt"
        
        # 保存文件
        save_srt_file(srt_content, output_path)
        
        if include_speaker:
            print("💡 提示: 字幕中已包含说话人标识 [spkXX]")
        else:
            print("💡 提示: 字幕中不包含说话人标识")
        
        print(f"\n✅ 完成！共 {len(subtitles)} 条字幕")


# 使用示例
if __name__ == "__main__":
    # 方式1: 直接使用（最简单）
    json_file = "字幕说话人分配结果.json"
    
    if os.path.exists(json_file):
        # 生成合并的SRT文件（包含说话人标识）
        convert_json_to_srt(json_file)
        
        # 或者按说话人分组输出
        # convert_json_to_srt(json_file, split_by_speaker=True)
        
        # 或者生成不含说话人标识的SRT
        # convert_json_to_srt(json_file, no_speaker=True)
        
        # 或者排除UNKNOWN说话人
        # convert_json_to_srt(json_file, exclude_unknown=True)
    else:
        print(f"❌ 错误: 文件 {json_file} 不存在")
    
    # 方式2: 使用命令行参数（更灵活）
    # 取消下面的注释以启用命令行模式
    """
    parser = argparse.ArgumentParser(
        description='将带说话人信息的JSON字幕转换为SRT格式',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
示例用法:
  # 生成合并的SRT文件（包含说话人标识）
  python json_to_srt.py 字幕说话人分配结果.json
  
  # 生成合并的SRT文件（不包含说话人标识）
  python json_to_srt.py 字幕说话人分配结果.json --no-speaker
  
  # 按说话人分组输出多个SRT文件
  python json_to_srt.py 字幕说话人分配结果.json --split-by-speaker
  
  # 指定输出文件
  python json_to_srt.py 字幕说话人分配结果.json -o output.srt
  
  # 排除UNKNOWN说话人
  python json_to_srt.py 字幕说话人分配结果.json --exclude-unknown
        '''
    )
    
    parser.add_argument('input_json', help='输入的JSON字幕文件路径')
    parser.add_argument('-o', '--output', help='输出的SRT文件路径（用于合并模式）')
    parser.add_argument('--split-by-speaker', action='store_true', 
                        help='按说话人分组，为每个说话人生成独立的SRT文件')
    parser.add_argument('-d', '--output-dir', 
                        help='输出目录（用于分组模式），默认为JSON文件所在目录')
    parser.add_argument('--no-speaker', action='store_true', 
                        help='不在字幕文本中包含说话人标识')
    parser.add_argument('--exclude-unknown', action='store_true', 
                        help='排除说话人为UNKNOWN的字幕')
    
    args = parser.parse_args()
    
    if not os.path.exists(args.input_json):
        print(f"❌ 错误: 输入文件不存在: {args.input_json}")
    else:
        convert_json_to_srt(
            args.input_json,
            output_srt=args.output,
            split_by_speaker=args.split_by_speaker,
            output_dir=args.output_dir,
            no_speaker=args.no_speaker,
            exclude_unknown=args.exclude_unknown
        )
    """