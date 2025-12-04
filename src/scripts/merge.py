import os
import json
import argparse
import time
import sys

current_script_dir = os.path.dirname(os.path.abspath(__file__))
if current_script_dir not in sys.path:
    sys.path.insert(0, current_script_dir)  # 插入到最前面，优先搜索
    print("子进程 sys.path：", sys.path)  # 打印所有模块搜索路径  

from util import (
    stitch_segments_with_empty_timeline,
)  # 确保util中函数兼容

# 全局配置（与主脚本保持一致）
EPSILON = 1e-3  # 时间误差容忍（秒）
MERGED_AUDIO_NAME = "merged.wav"  # 覆盖主脚本生成的合并音频
MERGED_JSON_NAME = "合并后时间顺序记录.json"  # 覆盖主脚本生成的JSON
TRANSCODED_WAV_SR = 16000  # 主脚本固定转码为16kHz，无需从原始文件读


def parse_args():
    """参数解析（保持你的--input-path命名）"""
    parser = argparse.ArgumentParser(
        description="合并手动剪切后的说话人音频（不依赖原始输入文件）"
    )
    parser.add_argument(
        "--input-path",  # 你的参数名：目标说话人目录（如spk01）
        type=str,
        required=True,
        help="目标说话人目录的绝对/相对路径（如：output/对话-medium.MP3/speaker_audios/spk01）",
    )
    parser.add_argument(
        "--preserve-timeline",
        type=str,
        default="false",
        help="是否保留原始时间线（基于转码WAV），默认false（直接拼接）",
    )
    return parser.parse_args()


def get_transcoded_wav_path(target_dir):
    """
    从目标目录推导主脚本生成的转码WAV路径（核心：不再找原始文件）
    逻辑：target_dir → speaker_audios → 原音频输出目录 → tmp/transcoded/xxx.wav
    """
    target_dir = os.path.abspath(target_dir).replace(os.sep, "/")
    # 向上追溯2级：spk01 → speaker_audios → 原音频输出目录（如：output/对话-medium.MP3）
    current_dir = os.path.dirname(target_dir)  # speaker_audios
    current_dir = os.path.dirname(current_dir)  # 原音频输出目录（如：对话-medium.MP3）
    # 转码WAV路径：原音频输出目录/tmp/transcoded/[原音频输出目录名].wav
    transcoded_dir = os.path.join(current_dir, "tmp", "transcoded").replace(os.sep, "/")
    orig_audio_output_name = os.path.basename(current_dir)  # 如：对话-medium.MP3
    orig_audio_no_ext = os.path.splitext(orig_audio_output_name)[0]  # 如：对话-medium
    wav_path = os.path.join(transcoded_dir, f"{orig_audio_no_ext}.wav").replace(
        os.sep, "/"
    )

    # 校验转码WAV是否存在（主脚本临时文件未被删除）
    if not os.path.exists(wav_path):
        raise RuntimeError(
            f"转码WAV文件缺失：{wav_path}\n"
            f"原因：主脚本生成的临时文件已删除，需重新运行主脚本分离角色后再合并"
        )
    return wav_path


def collect_all_segments(target_dir, seg_ext):
    """
    收集片段信息（仅依赖转码WAV和JSON，不找原始文件）
    :param transcoded_wav_path: 主脚本生成的转码WAV路径（时间基准）
    """
    target_dir = os.path.abspath(target_dir).replace(os.sep, "/")
    all_segments = []

    # 1. 读取目标目录内所有JSON记录（获取片段时间和内容）
    json_files = [f for f in os.listdir(target_dir) if f.endswith(MERGED_JSON_NAME)]
    if not json_files:
        raise RuntimeError(f"目标目录{target_dir}下未找到任何{MERGED_JSON_NAME}")

    # 2. 遍历JSON提取片段信息
    for json_filename in json_files:
        json_path = os.path.join(target_dir, json_filename).replace(os.sep, "/")
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                seg_records = json.load(f)
        except UnicodeDecodeError as e:
            print(f"❌ 读取 {json_filename} 时编码错误：{e}")
            print(f"尝试使用 GBK 编码重新读取...")
            try:
                with open(json_path, "r", encoding="gbk") as f:
                    seg_records = json.load(f)
                print(f"✅ 使用 GBK 编码成功读取")
            except Exception as e2:
                print(f"❌ GBK 编码也失败：{e2}，跳过该文件")
                continue

        for record in seg_records:
            required_fields = [
                "原始序号",
                "原始开始时间(秒)",
                "原始结束时间(秒)",
                "持续时间(秒)",
                "说话内容",
            ]
            if not all(field in record for field in required_fields):
                print(f"⚠️  {json_filename}中记录字段不完整，跳过该条")
                continue

            # 提取核心信息（JSON中的时间已基于转码WAV，无需原始文件）
            orig_start = round(record["原始开始时间(秒)"], 2)
            orig_end = round(record["原始结束时间(秒)"], 2)
            orig_duration = round(record["持续时间(秒)"], 2)
            seg_seq = record["原始序号"]
            seg_content = record["说话内容"] or "无内容"

            # 推导片段音频路径（目标目录下直接匹配seg_xxx.wav）
            seg_path = os.path.join(target_dir, f"seg_{seg_seq}{seg_ext}").replace(
                os.sep, "/"
            )
            if not os.path.exists(seg_path):
                print(f"⚠️  片段文件缺失，跳过：{seg_path}")
                continue

            # 存储片段信息（无需原始文件相关信息）
            all_segments.append(
                (seg_path, orig_start, orig_end, orig_duration, seg_seq, seg_content)
            )

    # 校验与排序（按转码WAV的时间轴排序）
    if not all_segments:
        raise RuntimeError(f"目标目录{target_dir}下无有效可合并的片段")
    # 按原始开始时间排序（确保合并后时间线正确，基于转码WAV的时间轴）
    all_segments.sort(key=lambda x: x[1])

    print(f"✅ 成功收集 {len(all_segments)} 个有效片段")
    return all_segments


def generate_unified_json(all_segments, merged_json_path):
    """生成统一JSON（逻辑不变，基于转码WAV时间轴）"""
    merged_records = []
    current_offset = 0.0  # 非时间线模式的合并后偏移

    for seg in all_segments:
        seg_path, orig_start, orig_end, orig_duration, seg_seq, seg_content = seg
        merged_records.append(
            {
                "原始序号": seg_seq,
                "原始开始时间(秒)": orig_start,  # 基于转码WAV的时间
                "原始结束时间(秒)": orig_end,
                "合并后开始时间(秒)": round(current_offset, 2),
                "合并后结束时间(秒)": round(current_offset + orig_duration, 2),
                "持续时间(秒)": orig_duration,
                "说话内容": seg_content,
            }
        )
        current_offset += orig_duration

    with open(merged_json_path, "w", encoding="utf-8") as f:
        json.dump(merged_records, f, ensure_ascii=False, indent=2)
    print(f"✅ 已生成统一JSON记录（覆盖原文件）：{merged_json_path}")
    return merged_records


def clean_old_json(target_dir):
    """清理旧JSON（逻辑不变）"""
    old_json_files = [
        f
        for f in os.listdir(target_dir)
        if f.endswith(MERGED_JSON_NAME) and f != MERGED_JSON_NAME
    ]
    if old_json_files:
        print(f"\n⚠️  清理 {len(old_json_files)} 个旧JSON记录：")
        for old_json in old_json_files:
            os.remove(os.path.join(target_dir, old_json))
            print(f"   - 已删除：{old_json}")


def merge_speaker_audio(file_path, target_dir, preserve_timeline):
    """核心合并逻辑（彻底移除原始文件依赖）"""
    target_dir = os.path.abspath(target_dir).replace(os.sep, "/")

    file_name, ext_with_dot = os.path.splitext(file_path)
    MERGED_AUDIO_NAME = f"merged{ext_with_dot}"  # 覆盖主脚本生成的合并音频

    print(f"\n=== 开始合并：{target_dir} ===")
    print(f"⚠️  脚本将直接覆盖以下文件：")
    print(f"   - 合并音频：{os.path.join(target_dir, MERGED_AUDIO_NAME)}")
    print(f"   - JSON记录：{os.path.join(target_dir, MERGED_JSON_NAME)}")

    # 步骤1：收集片段信息（基于转码WAV和JSON）
    print(f"\n=== 步骤1/4：收集片段信息 ===")
    all_segments = collect_all_segments(target_dir, ext_with_dot)
    audio_list_sorted = sorted(all_segments, key=lambda x: x[1])  # 根据开始时间排序

    # 步骤2：准备合并参数（用转码WAV参数替代原始文件）
    print(f"\n=== 步骤2/4：准备合并参数 ===")
    merged_media_path = os.path.join(target_dir, MERGED_AUDIO_NAME).replace(os.sep, "/")
    # 覆盖路径
    merged_json_path = os.path.join(target_dir, MERGED_JSON_NAME).replace(
        os.sep, "/"
    )  # 覆盖路径

    # 步骤3：执行音频合并（核心调整：用转码WAV替代原始文件）
    print(f"\n=== 步骤3/4：执行音频合并 ===")
    new_segments = [segment[:4] for segment in audio_list_sorted]
    stitch_segments_with_empty_timeline(
        media_list_sorted=new_segments,
        model_input_path=file_path,
        output_path=merged_media_path,
        fill_empty=preserve_timeline,
    )
    print(f"result_merge_speaker：{  merged_media_path}")

    # 步骤4：更新JSON+清理旧文件
    print(f"\n=== 步骤4/4：更新JSON记录 ===")
    generate_unified_json(all_segments, merged_json_path)
    clean_old_json(target_dir)

    # 最终校验
    if (
        not os.path.exists(merged_media_path)
        or os.path.getsize(merged_media_path) < 1024
    ):
        raise RuntimeError(f"合并失败：生成的音频文件无效（{merged_media_path}）")

    print(f"\n✅ 合并完成！结果已覆盖目标目录：")
    print(f"   合并音频：{merged_media_path}")
    print(f"   统一JSON：{merged_json_path}")
    return merged_media_path


if __name__ == "__main__":
    try:
        parser = argparse.ArgumentParser()
        parser.add_argument(
            "--preserve-timeline",
            type=str,
            default="false",
            help="是否保留时间线（基于转码WAV），默认false",
        )
        parser.add_argument(
            "--input-dir",
            type=str,
            required=True,
            help="目标说话人目录路径（如：output/对话-medium.MP3/speaker_audios/spk01）",
        )
        parser.add_argument(
            "--original-file", type=str, required=True, help="原始输入音频文件路径"
        )
        args = parser.parse_args()  # 之前漏了这行！导致参数无法解析

        start_time = time.time()
        # 转换参数类型
        preserve_timeline = args.preserve_timeline.lower() == "true"
        # 执行合并
        merge_speaker_audio(
            file_path=args.original_file,
            target_dir=args.input_dir,
            preserve_timeline=preserve_timeline,
        )
        # 输出耗时
        total_time = (time.time() - start_time) / 60
        print(f"\n⏱️  总耗时：{total_time:.2f} 分钟")
        print(f"PROGRESS:100%")
    except Exception as e:
        print(f"\n❌ 合并失败：{str(e)}")
        exit(1)
