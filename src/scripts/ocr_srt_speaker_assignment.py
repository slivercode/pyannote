import os
import json
import argparse
import sys
import time
import pathlib
import shutil
import re

current_script_dir = os.path.dirname(os.path.abspath(__file__))
if current_script_dir not in sys.path:
    sys.path.insert(0, current_script_dir)
print("子进程 sys.path：", sys.path)

# 检查是否有强制CPU参数（需要在导入torch_loader之前设置）
FORCE_CPU = "--force-cpu" in sys.argv
if FORCE_CPU:
    os.environ["FORCE_CPU_MODE"] = "1"
    print("⚠️ 检测到 --force-cpu 参数，将强制使用CPU运行")

from torch_loader import use_gpu, torch
from util import (
    get_audio_duration,
    convert_to_wav,
    load_wav,
    extract_media_segment,
)

from pyannote.audio import Pipeline
from pyannote.audio.pipelines.speaker_diarization import DiarizeOutput
import wave
from pyannote.audio.pipelines.utils.hook import ProgressHook
import numpy as np

device = "cuda" if use_gpu else "cpu"
print(f"使用设备: {device}")

EPSILON = 0.1  # 时间匹配容差（秒）
NUM_SPEAKERS = 0  # 0表示自动检测
MAX_SPEAKERS = 0
MIN_SPEAKERS = 0


def sanitize_filename(filename):
    """
    清理文件名中的非法字符（Windows 文件系统限制）
    禁用字符：< > : " / \ | ? *
    """
    # Windows 文件名禁用字符映射表
    illegal_chars = {
        ':': '：',   # 冒号 -> 中文冒号
        '<': '＜',   # 小于 -> 全角小于
        '>': '＞',   # 大于 -> 全角大于
        '"': '"',    # 双引号 -> 中文引号
        '/': '／',   # 斜杠 -> 全角斜杠
        '\\': '＼',  # 反斜杠 -> 全角反斜杠
        '|': '｜',   # 竖线 -> 全角竖线
        '?': '？',   # 问号 -> 中文问号
        '*': '＊',   # 星号 -> 全角星号
    }
    
    for char, replacement in illegal_chars.items():
        filename = filename.replace(char, replacement)
    
    # 移除首尾空格和点号（Windows 限制）
    filename = filename.strip('. ')
    
    return filename


def get_packaged_cache_path():
    """获取缓存路径"""
    if getattr(sys, "frozen", False):
        exe_dir = pathlib.Path(sys.executable).parent
    else:
        exe_dir = pathlib.Path(__file__).parent.parent.parent
    return os.path.abspath(str(exe_dir)).replace(os.sep, "/")


def load_model(auth_token="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", retry=3):
    """加载 Pyannote 模型"""
    print(f"=== 初始化 Pyannote 模型 ===")
    if not auth_token:
        raise ValueError("请提供有效的 Hugging Face 访问令牌！")

    packaged_cache = get_packaged_cache_path()
    hf_cache = os.path.join(packaged_cache, "hf_cache")
    os.makedirs(hf_cache, exist_ok=True)
    hf_cache = hf_cache.replace(os.sep, "/")
    print(f"Hugging Face 缓存目录: {hf_cache}")

    for attempt in range(retry):
        try:
            pipeline = Pipeline.from_pretrained(
                "pyannote/speaker-diarization-community-1",
                token=auth_token,
                cache_dir=hf_cache,
            )
            if device == "cuda":
                pipeline.to(torch.device("cuda"))
            print("模型加载成功！")
            return pipeline
        except Exception as e:
            if attempt == retry - 1:
                raise RuntimeError(f"模型加载失败：{str(e)}")
            print(f"⚠️  模型加载失败，重试 {attempt+1}/{retry}...")
            time.sleep(5)


class LogHook(ProgressHook):
    """进度钩子"""
    def before_pipeline(self, pipeline, **kwargs):
        print(f"开始处理音频...")

    def before_step(self, step_name, **kwargs):
        print(f"即将执行步骤：{step_name}")

    def update_progress(self, step_name, progress):
        print(f"步骤 {step_name} 进度：{progress*100:.1f}%")

    def after_pipeline(self, pipeline, result, **kwargs):
        print("处理完成！")


def parse_srt_file(srt_path):
    """
    解析 SRT 字幕文件
    返回格式: [(start_time, end_time, text), ...]
    时间单位：秒
    """
    if not os.path.exists(srt_path):
        raise FileNotFoundError(f"SRT文件不存在：{srt_path}")

    subtitles = []
    with open(srt_path, "r", encoding="utf-8") as f:
        content = f.read()

    # 分割字幕块（以空行分隔）
    blocks = re.split(r'\n\s*\n', content.strip())

    for block in blocks:
        lines = block.strip().split('\n')
        if len(lines) < 3:
            continue

        # 解析时间轴（第二行）
        # 格式: 00:00:01,000 --> 00:00:03,500
        time_line = lines[1]
        time_match = re.match(
            r'(\d{2}):(\d{2}):(\d{2}),(\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2}),(\d{3})',
            time_line
        )

        if not time_match:
            continue

        # 转换为秒
        start_h, start_m, start_s, start_ms = map(int, time_match.groups()[:4])
        end_h, end_m, end_s, end_ms = map(int, time_match.groups()[4:])

        start_time = start_h * 3600 + start_m * 60 + start_s + start_ms / 1000
        end_time = end_h * 3600 + end_m * 60 + end_s + end_ms / 1000

        # 提取文本（第三行及之后）
        text = '\n'.join(lines[2:]).strip()

        subtitles.append((start_time, end_time, text))

    print(f"✅ 成功解析 {len(subtitles)} 条字幕")
    return subtitles


def assign_speakers_to_subtitles(subtitles, diarization_result):
    """
    将说话人分配给字幕
    :param subtitles: [(start, end, text), ...]
    :param diarization_result: pyannote 的分割结果
    :return: [(start, end, text, speaker), ...]
    """
    assigned_subtitles = []

    # 构建说话人时间段映射
    speaker_segments = []
    for seg in diarization_result.speaker_diarization:
        turn, spk = seg
        speaker_segments.append((turn.start, turn.end, spk))

    for sub_start, sub_end, text in subtitles:
        # 找到与字幕时间重叠最多的说话人
        best_speaker = "UNKNOWN"
        max_overlap = 0

        for spk_start, spk_end, speaker in speaker_segments:
            # 计算重叠时间
            overlap_start = max(sub_start, spk_start)
            overlap_end = min(sub_end, spk_end)
            overlap_duration = max(0, overlap_end - overlap_start)

            if overlap_duration > max_overlap:
                max_overlap = overlap_duration
                best_speaker = speaker

        # 如果重叠时间太短，标记为未知
        subtitle_duration = sub_end - sub_start
        if max_overlap < subtitle_duration * 0.3:  # 至少30%重叠
            best_speaker = "UNKNOWN"

        assigned_subtitles.append((sub_start, sub_end, text, best_speaker))

    return assigned_subtitles


def process_video_with_srt(video_path, srt_path, output_path):
    """
    处理视频和SRT文件，分配说话人
    """
    print(f"PROGRESS:10%")
    
    # 规范化路径（修复小写盘符、混合斜杠等问题）
    video_path = os.path.normpath(video_path)  # 先规范化
    video_path = os.path.abspath(video_path).replace(os.sep, "/")
    srt_path = os.path.normpath(srt_path)
    srt_path = os.path.abspath(srt_path).replace(os.sep, "/")
    # output_path 可能是相对路径，需要转换为绝对路径
    output_path = os.path.normpath(output_path)
    if not os.path.isabs(output_path):
        output_path = os.path.abspath(output_path).replace(os.sep, "/")
    else:
        output_path = output_path.replace(os.sep, "/")

    # 创建输出目录（清理文件名中的非法字符）
    base_name = os.path.basename(os.path.normpath(video_path))
    base_name = sanitize_filename(base_name)  # 清理非法字符
    output_dir = os.path.join(output_path, base_name)
    output_dir = output_dir.replace(os.sep, "/")

    if os.path.exists(output_dir):
        shutil.rmtree(output_dir)
    os.makedirs(output_dir, exist_ok=True)

    # 创建临时目录
    tmp_dir = os.path.join(output_dir, "tmp")
    os.makedirs(tmp_dir, exist_ok=True)

    print(f"\n处理视频：{video_path}")
    print(f"处理字幕：{srt_path}")
    print(f"PROGRESS:20%")

    # 步骤1：解析SRT文件
    subtitles = parse_srt_file(srt_path)
    print(f"PROGRESS:30%")

    # 步骤2：转码音频
    print("=== 转码音频 ===")
    transcode_dir = os.path.join(tmp_dir, "transcoded")
    os.makedirs(transcode_dir, exist_ok=True)
    wav_path = convert_to_wav(video_path, transcode_dir)
    print(f"PROGRESS:40%")

    # 步骤3：加载音频并进行说话人分割
    print("=== 加载 Pyannote 模型 ===")
    pipeline = load_model()
    print(f"PROGRESS:50%")

    print("=== 执行说话人分割 ===")
    input_audio, sr = load_wav(wav_path)
    input_audio_tensor = (
        torch.from_numpy(input_audio.astype(np.float32)).unsqueeze(0).to(device)
    )

    with LogHook() as hook:
        if NUM_SPEAKERS > 0:
            diarize_result: DiarizeOutput = pipeline(
                {"waveform": input_audio_tensor, "sample_rate": sr},
                hook=hook,
                num_speakers=NUM_SPEAKERS,
            )
        elif MIN_SPEAKERS > 0 and MAX_SPEAKERS > 0:
            diarize_result: DiarizeOutput = pipeline(
                {"waveform": input_audio_tensor, "sample_rate": sr},
                hook=hook,
                min_speakers=MIN_SPEAKERS,
                max_speakers=MAX_SPEAKERS,
            )
        else:
            diarize_result: DiarizeOutput = pipeline(
                {"waveform": input_audio_tensor, "sample_rate": sr}, hook=hook
            )

    speakers = list(diarize_result.speaker_diarization.labels())
    print(f"  → 共识别出 {len(speakers)} 个说话人")
    print(f"count_role：{len(speakers)}")
    print(f"PROGRESS:70%")

    # 步骤4：分配说话人到字幕
    print("=== 分配说话人到字幕 ===")
    assigned_subtitles = assign_speakers_to_subtitles(subtitles, diarize_result)

    # 步骤5：按说话人分组字幕
    speaker_subtitles = {}
    for start, end, text, speaker in assigned_subtitles:
        speaker_id = speaker.replace("SPEAKER_", "spk")
        if speaker_id not in speaker_subtitles:
            speaker_subtitles[speaker_id] = []
        speaker_subtitles[speaker_id].append({
            "开始时间(秒)": round(start, 2),
            "结束时间(秒)": round(end, 2),
            "持续时间(秒)": round(end - start, 2),
            "文本内容": text
        })

    print(f"PROGRESS:80%")

    # 步骤6：保存结果
    # 保存完整的字幕分配结果
    all_results = []
    for start, end, text, speaker in assigned_subtitles:
        speaker_id = speaker.replace("SPEAKER_", "spk")
        all_results.append({
            "开始时间(秒)": round(start, 2),
            "结束时间(秒)": round(end, 2),
            "持续时间(秒)": round(end - start, 2),
            "说话人": speaker_id,
            "文本内容": text
        })

    result_path = os.path.join(output_dir, "字幕说话人分配结果.json")
    with open(result_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)
    print(f"✅ 完整结果已保存：{result_path}")

    # 调用 tosrt2.py 生成合并的 SRT 文件
    try:
        # 导入 tosrt2.py 的转换函数
        tosrt2_path = os.path.join(pathlib.Path(__file__).parent.parent.parent, "tosrt", "tosrt2.py")
        if os.path.exists(tosrt2_path):
            # 动态导入 tosrt2 模块
            import importlib.util
            spec = importlib.util.spec_from_file_location("tosrt2", tosrt2_path)
            tosrt2 = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(tosrt2)
            
            # 生成合并的 SRT 文件（包含说话人标识）
            print(f"\n📝 正在生成合并的 SRT 文件...")
            tosrt2.convert_json_to_srt(result_path, no_speaker=False)
            
            # 生成输出路径
            merged_srt_path = os.path.splitext(result_path)[0] + ".srt"
            print(f"✅ 合并 SRT 文件已保存：{merged_srt_path}")
            print(f"result_merged_srt：{merged_srt_path}")
        else:
            print(f"⚠️ 警告：未找到 tosrt2.py，跳过合并 SRT 生成")
    except Exception as e:
        print(f"⚠️ 生成合并 SRT 文件时出错：{e}")

    # 按说话人保存分组结果
    speaker_dir = os.path.join(output_dir, "speaker_subtitles")
    os.makedirs(speaker_dir, exist_ok=True)

    for speaker_id, subs in speaker_subtitles.items():
        # 保存JSON格式
        speaker_json_path = os.path.join(speaker_dir, f"{speaker_id}_字幕.json")
        with open(speaker_json_path, "w", encoding="utf-8") as f:
            json.dump(subs, f, ensure_ascii=False, indent=2)
        print(f"✅ {speaker_id} 字幕已保存：{speaker_json_path}")

        # 保存SRT格式
        speaker_srt_path = os.path.join(speaker_dir, f"{speaker_id}_字幕.srt")
        with open(speaker_srt_path, "w", encoding="utf-8") as f:
            for idx, sub in enumerate(subs, 1):
                start_sec = sub["开始时间(秒)"]
                end_sec = sub["结束时间(秒)"]
                
                # 转换为SRT时间格式
                start_h = int(start_sec // 3600)
                start_m = int((start_sec % 3600) // 60)
                start_s = int(start_sec % 60)
                start_ms = int((start_sec % 1) * 1000)
                
                end_h = int(end_sec // 3600)
                end_m = int((end_sec % 3600) // 60)
                end_s = int(end_sec % 60)
                end_ms = int((end_sec % 1) * 1000)
                
                f.write(f"{idx}\n")
                f.write(f"{start_h:02d}:{start_m:02d}:{start_s:02d},{start_ms:03d} --> ")
                f.write(f"{end_h:02d}:{end_m:02d}:{end_s:02d},{end_ms:03d}\n")
                f.write(f"{sub['文本内容']}\n\n")
        
        print(f"✅ {speaker_id} SRT字幕已保存：{speaker_srt_path}")
        print(f"result_speaker_srt：{speaker_srt_path}")

    print(f"PROGRESS:90%")
    print(f"result_root：{output_dir}")
    print(f"PROGRESS:100%")

    # 清理临时文件
    # shutil.rmtree(tmp_dir)


if __name__ == "__main__":
    print(f"PROGRESS:5%")
    parser = argparse.ArgumentParser(description="视频+OCR字幕说话人分配")
    parser.add_argument(
        "--video-path",
        type=str,
        required=True,
        help="视频文件路径（MP4等格式）",
    )
    parser.add_argument(
        "--srt-path",
        type=str,
        required=True,
        help="SRT字幕文件路径",
    )
    parser.add_argument(
        "--output-path",
        type=str,
        default="output",
        help="输出根目录（默认当前目录下的 output）",
    )
    parser.add_argument(
        "--num-speakers",
        type=int,
        default=0,
        help="角色数量（0为自动检测）",
    )
    parser.add_argument(
        "--min-speakers",
        type=int,
        default=0,
        help="角色数量范围最小值",
    )
    parser.add_argument(
        "--max-speakers",
        type=int,
        default=0,
        help="角色数量范围最大值",
    )
    parser.add_argument(
        "--force-cpu",
        action="store_true",
        help="强制使用CPU运行（忽略GPU）",
    )

    args = parser.parse_args()

    try:
        NUM_SPEAKERS = args.num_speakers
        MIN_SPEAKERS = args.min_speakers
        MAX_SPEAKERS = args.max_speakers

        start_time = time.time()
        process_video_with_srt(
            video_path=args.video_path,
            srt_path=args.srt_path,
            output_path=args.output_path,
        )

        total_time = (time.time() - start_time) / 60
        print(f"\n⏱️  总耗时：{total_time:.2f} 分钟")

    except Exception as e:
        print(f"\n❌ 执行失败：{str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
