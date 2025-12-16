import os
import numpy as np
import subprocess
import re
import time
import shutil
import wave  # 需在文件顶部导入wave库
from typing import List, Tuple
import json

def get_audio_info(input_path):
    # 转绝对路径
    input_path = os.path.abspath(input_path).replace(os.sep, "/")
    cmd = ["ffmpeg", "-hide_banner", "-i", input_path]
    # 关键：传递UTF-8环境变量，避免ffmpeg输出中文；同时指定encoding="utf-8"
    env = os.environ.copy()
    env["LC_ALL"] = "en_US.UTF-8"  # 强制ffmpeg输出英文，减少中文解码问题
    env["LANG"] = "en_US.UTF-8"
    try:
        # 必须添加 encoding="utf-8"，避免subprocess默认用GBK读取输出
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
            env=env,
            encoding="utf-8",  # 这行是新增的核心配置
        )
    except FileNotFoundError:
        raise RuntimeError("ffmpeg 未找到，请配置到 PATH 环境变量中。")
    output = result.stderr if result.stderr else result.stdout
    audio_info = {}
    audio_stream_line = re.search(r"Stream #\d+:\d+.*?Audio: (.*)", output)
    if audio_stream_line:
        audio_desc = audio_stream_line.group(1)
        audio_info["codec"] = (
            re.search(r"pcm_s16le|pcm_s16be|pcm_s16", audio_desc).group(0)
            if re.search(r"pcm_s16le|pcm_s16be|pcm_s16", audio_desc)
            else None
        )
        audio_info["channels"] = (
            2
            if "stereo" in audio_desc
            else (
                1
                if "mono" in audio_desc
                else (
                    int(re.search(r"(\d+) (channels?|声道)", audio_desc).group(1))
                    if re.search(r"(\d+) (channels?|声道)", audio_desc)
                    else None
                )
            )
        )
        audio_info["sample_rate"] = (
            int(re.search(r"(\d+) Hz", audio_desc).group(1))
            if re.search(r"(\d+) Hz", audio_desc)
            else None
        )
        if re.search(r"s16", audio_desc):
            audio_info["bit_depth"] = 16
        elif re.search(r"s24", audio_desc):
            audio_info["bit_depth"] = 24
        elif re.search(r"s32", audio_desc):
            audio_info["bit_depth"] = 32
        else:
            audio_info["bit_depth"] = 16  # 默认16位，避免None
    return audio_info


def convert_to_wav(input_path, output_dir):
    # 转绝对路径（先规范化路径格式）
    # 修复：Windows 下小写盘符路径问题（e:/xx.wav -> E:/xx.wav）
    input_path = os.path.normpath(input_path)  # 规范化路径分隔符
    input_path = os.path.abspath(input_path).replace(os.sep, "/")
    output_dir = os.path.normpath(output_dir)
    output_dir = os.path.abspath(output_dir).replace(os.sep, "/")
    os.makedirs(output_dir, exist_ok=True)

    info = get_audio_info(input_path)
    if (
        info.get("codec")
        and "pcm_s16" in info["codec"]
        and info.get("sample_rate") == 16000
        and info.get("channels") == 1
        and info.get("bit_depth") == 16
    ):
        return input_path

    base_name = os.path.basename(input_path)
    name_no_ext = os.path.splitext(base_name)[0]
    output_wav = os.path.join(output_dir, f"{name_no_ext}.wav")
    output_wav = output_wav.replace(os.sep, "/")  # 统一分隔符

    # 关键：传递UTF-8环境变量，避免ffmpeg输出中文；同时指定encoding="utf-8"
    env = os.environ.copy()
    env["LC_ALL"] = "en_US.UTF-8"  # 强制ffmpeg输出英文，减少中文解码问题
    env["LANG"] = "en_US.UTF-8"

    # 列表形式调用 ffmpeg，避免转义
    cmd = [
        "ffmpeg",
        "-y",
        "-threads",
        "0",
        "-i",
        input_path,
        "-ac",
        "1",
        "-ar",
        "16000",
        "-sample_fmt",
        "s16",
        output_wav,
    ]
    subprocess.run(
        cmd,
        check=True,
        text=True,
        env=env,
        encoding="utf-8",
        stdout=subprocess.DEVNULL,  # 丢弃 stdout
        stderr=subprocess.PIPE,  # 捕获 stderr
        creationflags=subprocess.CREATE_NO_WINDOW,  # 关键参数
    )
    # 新增：校验转码后的WAV文件有效性
    if not os.path.exists(output_wav):
        raise RuntimeError(f"转码失败：未生成WAV文件（{output_wav}）")
    if os.path.getsize(output_wav) < 1024:  # 小于1KB视为空文件
        raise RuntimeError(f"转码生成空文件（{output_wav}），可能原文件损坏")
    return output_wav


def load_wav(file_path):
    # 转绝对路径并统一分隔符
    file_path = os.path.abspath(file_path).replace(os.sep, "/")

    # 用Python内置wave库读取WAV（避免soundfile依赖）
    try:
        with wave.open(file_path, "rb") as wf:
            # 获取WAV参数
            channels = wf.getnchannels()
            sr = wf.getframerate()
            sample_width = wf.getsampwidth()
            frames = wf.getnframes()

            # 校验采样率（必须16kHz，与原逻辑一致）
            assert sr == 16000, f"采样率必须是 16kHz，当前为 {sr}kHz"

            # 读取音频数据（转为numpy数组）
            data = wf.readframes(frames)
            # 根据采样宽度转为对应类型（s16格式对应int16）
            if sample_width == 2:
                data = np.frombuffer(data, dtype=np.int16)
            else:
                raise RuntimeError(f"不支持的采样宽度：{sample_width}（仅支持16位WAV）")

            # 多声道转单声道（与原逻辑一致）
            if channels > 1:
                data = data.reshape(-1, channels).mean(axis=1)

            # 转为float32格式（与soundfile输出格式一致，避免后续逻辑报错）
            data = data.astype(np.float32) / 32768.0
            return data, sr
    except Exception as e:
        raise RuntimeError(f"读取WAV文件失败（{file_path}）：{str(e)}")


def extract_audio_segment(input_path, output_path, start_sec, end_sec):
    try:
        input_path = os.path.abspath(input_path).replace(os.sep, "/")
        output_path = os.path.abspath(output_path).replace(os.sep, "/")
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        # 关键：先获取原音频的参数（位深、采样率等）
        orig_info = get_audio_info(input_path)
        bit_depth = orig_info.get("bit_depth", 16)  # 默认16位，避免None
        sample_rate = orig_info.get("sample_rate", 44100)
        channels = orig_info.get("channels", 2)

        # 根据原音频位深选择对应的PCM编码（确保无损转换）
        if bit_depth == 8:
            codec = "pcm_u8"  # 8位无符号PCM
        elif bit_depth == 16:
            codec = "pcm_s16le"  # 16位有符号PCM（小端）
        elif bit_depth == 24:
            codec = "pcm_s24le"  # 24位有符号PCM（小端）
        elif bit_depth == 32:
            codec = "pcm_s32le"  # 32位有符号PCM（小端）
        else:
            codec = "pcm_s16le"  # 未知位深时降级为16位（保底）
            print(f"⚠️  原音频位深{bit_depth}不支持，临时片段将使用16位PCM")

        env = os.environ.copy()
        env["LC_ALL"] = "en_US.UTF-8"
        env["LANG"] = "en_US.UTF-8"

        # 核心命令：仅转换为WAV封装，参数与原音频一致（无损）
        cmd = [
            "ffmpeg",
            "-y",  # 覆盖输出
            "-ss",
            str(start_sec),  # 开始时间
            "-to",
            str(end_sec),  # 结束时间
            "-i",
            input_path,  # 输入原音频
            "-f",
            "wav",  # 输出格式为WAV（确保wave库识别）
            "-c:a",
            codec,  # 音频编码匹配原音频位深
            "-ar",
            str(sample_rate),  # 采样率与原音频一致
            "-ac",
            str(channels),  # 声道数与原音频一致
            output_path,
        ]
        result = subprocess.run(
            cmd,
            env=env,
            text=True,
            encoding="utf-8",
            stdout=subprocess.DEVNULL,  # 丢弃 stdout
            stderr=subprocess.PIPE,  # 捕获 stderr
            creationflags=subprocess.CREATE_NO_WINDOW,  # 关键参数
        )
        result.check_returncode()
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"提取片段失败（{output_path}）：{e.stderr}")
    except OSError as e:
        if e.errno == 28:
            raise RuntimeError(f"磁盘空间不足，无法保存片段：{output_path}")
        elif e.errno == 13:
            raise RuntimeError(f"无写权限，无法保存片段：{output_path}")
        else:
            raise RuntimeError(f"IO错误（{output_path}）：{str(e)}")


def concat_audio_with_ffmpeg(input_paths, output_path):

    concat_audio_with_ffmpeg_consume = time.perf_counter()

    # 转绝对路径
    input_paths = [os.path.abspath(p).replace(os.sep, "/") for p in input_paths]
    output_path = os.path.abspath(output_path).replace(os.sep, "/")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    list_path = f"{output_path}.txt"
    list_path = list_path.replace(os.sep, "/")  # 统一分隔符

    # 生成 concat 列表（绝对路径 + 无引号）
    with open(list_path, "w", encoding="utf-8") as f:
        for path in input_paths:
            f.write(f"file {path}\n")  # 关键：无引号，绝对路径

    # 列表形式调用 ffmpeg
    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",  # 允许绝对路径
        "-i",
        list_path,
        "-c:a",
        "copy",
        output_path,
    ]
    # 关键：传递UTF-8环境变量，避免ffmpeg输出中文；同时指定encoding="utf-8"
    env = os.environ.copy()
    env["LC_ALL"] = "en_US.UTF-8"  # 强制ffmpeg输出英文，减少中文解码问题
    env["LANG"] = "en_US.UTF-8"
    print(f"result:10")
    result = subprocess.run(
        cmd, capture_output=True, text=True, env=env, encoding="utf-8"
    )
    os.remove(list_path)  # 删除临时列表

    print(
        f"  [耗时] 音频合并：{time.perf_counter() - concat_audio_with_ffmpeg_consume:.2f} 秒"
    )
    if result.returncode != 0:
        raise RuntimeError(f"拼接音频失败：{result.stderr}")


def generate_full_timeline_audio(
    original_audio_path,
    wav_path,
    speaker_segments,
    merged_path,
    total_duration,
    sr_orig,
):
    """
    生成单个说话人保留原始时间线的完整音频（保留wav_path用于转码一致性校验）
    :param original_audio_path: 原音频路径（用于提取片段，保留质量）
    :param wav_path: 转码后的16kHz WAV路径（模型输入，用于校验时长一致性）
    :param speaker_segments: 该说话人的时间片段列表，格式：[(s, e), ...]
    :param merged_path: 最终输出的合并音频路径
    :param total_duration: 原音频真实总时长（秒）
    :param sr_orig: 原音频采样率（Hz）
    :return: 生成的音频文件路径
    """
    # 从merged_path中解析说话人ID（用于日志显示）
    speaker_id = os.path.basename(os.path.dirname(merged_path))
    print(f"\n=== 生成说话人 {speaker_id} 的保留时间线音频 ===")

    # -------------------------- 新增：wav_path 转码一致性校验（核心作用） --------------------------
    # 转码后的WAV是模型输入，其时长是说话人分割的基准，需与原音频时长一致
    if not os.path.exists(wav_path):
        raise RuntimeError(f"转码后的WAV文件不存在：{wav_path}（模型输入文件丢失）")

    with wave.open(wav_path, "rb") as wf_model:
        sr_model = wf_model.getframerate()
        total_frames_model = wf_model.getnframes()
        transcode_duration = total_frames_model / sr_model  # 转码后WAV的时长

    # 校验转码后WAV与原音频的时长一致性（允许0.1秒误差）
    duration_diff = abs(total_duration - transcode_duration)
    print(f"  转码一致性校验（wav_path作用）：")
    print(f"    - 转码后WAV（模型输入）：{transcode_duration:.2f}秒（16kHz）")
    print(f"    - 原音频真实时长：{total_duration:.2f}秒（{sr_orig}Hz）")
    if duration_diff > 0.1:
        print(
            f"⚠️  转码时长偏差过大（{duration_diff:.2f}秒）！可能导致说话人片段时间映射错误"
        )
        print(f"    - 建议检查转码函数 convert_to_wav 是否正常工作")
    else:
        print(f"✅ 转码时长一致（偏差{duration_diff:.2f}秒），时间映射可靠")

    # 1. 获取原音频参数（关键：声道数、位深、采样率）
    orig_audio_info = get_audio_info(original_audio_path)
    channels_orig = orig_audio_info.get("channels", 2)  # 原声道数（默认2声道）
    bit_depth_orig = orig_audio_info.get("bit_depth", 16)  # 原位深（默认16位）
    sample_width_orig = bit_depth_orig // 8  # 样本宽度（字节数）
    total_frames_orig = int(round(total_duration * sr_orig))  # 原音频总帧数（关键参数）

    # 打印原音频核心参数（验证基础数据）
    print(f"  原音频核心参数：")
    print(f"    - 声道数：{channels_orig}（1=单声道，2=立体声）")
    print(f"    - 位深：{bit_depth_orig}位 → 样本宽度：{sample_width_orig}字节")
    print(f"    - 采样率：{sr_orig}Hz")
    print(f"    - 总时长：{total_duration:.2f}秒 → 总帧数：{total_frames_orig}")

    # 跳过无有效片段的说话人
    if not speaker_segments:
        print(f"⚠️  说话人{speaker_id}无有效片段，跳过生成")
        return None

    # 确保输出目录存在
    os.makedirs(os.path.dirname(merged_path), exist_ok=True)

    # 2. 创建与原音频等长、对应声道数的空音频数组（核心修复）
    # 单声道：1维数组 (总帧数,)；多声道：2维数组 (总帧数, 声道数)
    try:
        if bit_depth_orig == 16:
            if channels_orig == 1:
                empty_audio = np.zeros(total_frames_orig, dtype=np.int16)
            else:
                empty_audio = np.zeros(
                    (total_frames_orig, channels_orig), dtype=np.int16
                )
        elif bit_depth_orig == 24:
            # 24位用int32存储（高8位补0）
            if channels_orig == 1:
                empty_audio = np.zeros(total_frames_orig, dtype=np.int32)
            else:
                empty_audio = np.zeros(
                    (total_frames_orig, channels_orig), dtype=np.int32
                )
            empty_audio = empty_audio << 8  # 对齐24位数据
        elif bit_depth_orig == 32:
            if channels_orig == 1:
                empty_audio = np.zeros(total_frames_orig, dtype=np.int32)
            else:
                empty_audio = np.zeros(
                    (total_frames_orig, channels_orig), dtype=np.int32
                )
        else:
            # 未知位深默认按16位处理
            if channels_orig == 1:
                empty_audio = np.zeros(total_frames_orig, dtype=np.int16)
            else:
                empty_audio = np.zeros(
                    (total_frames_orig, channels_orig), dtype=np.int16
                )
    except MemoryError:
        raise RuntimeError(
            f"内存不足，无法创建{total_frames_orig}帧的空音频数组（尝试降低音频时长或位深）"
        )

    # 验证空音频数组维度（关键修复验证）
    expected_shape = (
        (total_frames_orig,)
        if channels_orig == 1
        else (total_frames_orig, channels_orig)
    )
    print(f"  空音频数组验证：")
    print(f"    - 实际维度：{empty_audio.shape} → 预期维度：{expected_shape}")
    print(f"    - 数据类型：{empty_audio.dtype} → 预期字节数/元素：{sample_width_orig}")

    # 3. 遍历片段并复制到空音频（按声道数处理）
    for idx, (s, e) in enumerate(speaker_segments):
        # 计算片段在原音频中的帧区间
        start_frame_orig = int(round(s * sr_orig))
        end_frame_orig = int(round(e * sr_orig))
        start_frame_orig = max(0, start_frame_orig)
        end_frame_orig = min(total_frames_orig, end_frame_orig)
        frame_count = end_frame_orig - start_frame_orig
        if frame_count <= 0:
            print(
                f"⚠️  片段 {idx+1} 无效（帧区间：{start_frame_orig}-{end_frame_orig}），跳过"
            )
            continue

        # 临时片段路径（避免特殊字符）
        temp_seg_name = (
            f"temp_{speaker_id}_{idx}_{int(s*1000)}.wav"  # 用毫秒整数避免小数点问题
        )
        temp_seg_path = os.path.join(
            os.path.dirname(merged_path), temp_seg_name
        ).replace(os.sep, "/")
        print(f"  处理片段 {idx+1}/{len(speaker_segments)}：")
        print(
            f"    - 时间区间：{s:.2f}~{e:.2f}秒 → 帧区间：{start_frame_orig}-{end_frame_orig}（{frame_count}帧）"
        )
        print(f"    - 临时路径：{temp_seg_path}")

        # 提取片段音频（用原音频参数确保一致性）
        extract_audio_segment(original_audio_path, temp_seg_path, s, e)
        if not os.path.exists(temp_seg_path) or os.path.getsize(temp_seg_path) < 1024:
            print(f"⚠️  片段 {idx+1} 提取失败或为空，跳过复制")
            continue

        # 读取片段并转换为数组（按片段声道数处理）
        with wave.open(temp_seg_path, "rb") as wf_seg:
            seg_channels = wf_seg.getnchannels()
            seg_sr = wf_seg.getframerate()
            seg_sample_width = wf_seg.getsampwidth()
            seg_frame_count = wf_seg.getnframes()
            seg_frames = wf_seg.readframes(seg_frame_count)

            # 验证片段参数与原音频一致
            if seg_sr != sr_orig:
                print(f"⚠️  片段采样率不匹配（{seg_sr}≠{sr_orig}），可能导致时间偏移")
            if seg_channels != channels_orig:
                print(
                    f"⚠️  片段声道数不匹配（{seg_channels}≠{channels_orig}），强制转换为原声道数"
                )

            # 根据位深解析片段数据
            if seg_sample_width == 2:  # 16位
                seg_audio = np.frombuffer(seg_frames, dtype=np.int16)
            elif seg_sample_width == 3:  # 24位（特殊处理，转为int32）
                seg_audio = np.frombuffer(seg_frames, dtype=np.uint8).reshape(-1, 3)
                seg_audio = (
                    seg_audio[:, 0] | (seg_audio[:, 1] << 8) | (seg_audio[:, 2] << 16)
                ).astype(np.int32)
            elif seg_sample_width == 4:  # 32位
                seg_audio = np.frombuffer(seg_frames, dtype=np.int32)
            else:
                print(f"⚠️  片段位深不支持（{seg_sample_width*8}位），转为16位处理")
                seg_audio = np.frombuffer(seg_frames, dtype=np.int16)

            # 多声道片段reshape为（帧数，声道数）
            if seg_channels > 1:
                seg_audio = seg_audio.reshape(-1, seg_channels)
                # 若声道数不匹配，强制转为原音频声道数（简单复制填充）
                if seg_channels != channels_orig:
                    seg_audio = np.tile(seg_audio, (1, channels_orig // seg_channels))[
                        :, :channels_orig
                    ]

        # 修正片段长度（确保与目标帧区间一致）
        seg_frame_actual = len(seg_audio) if channels_orig == 1 else seg_audio.shape[0]
        if seg_frame_actual != frame_count:
            print(
                f"    - 片段帧数修正：{seg_frame_actual} → {frame_count}（补零/截断）"
            )
            if channels_orig == 1:
                # 单声道补零
                seg_audio = np.pad(
                    seg_audio,
                    (0, max(0, frame_count - seg_frame_actual)),
                    mode="constant",
                )[:frame_count]
            else:
                # 多声道补零（按帧数补，保持声道数）
                pad_width = ((0, max(0, frame_count - seg_frame_actual)), (0, 0))
                seg_audio = np.pad(seg_audio, pad_width, mode="constant")[
                    :frame_count, :
                ]

        # 复制片段数据到空音频（按声道数匹配维度）
        try:
            if channels_orig == 1:
                empty_audio[start_frame_orig:end_frame_orig] = seg_audio
            else:
                empty_audio[start_frame_orig:end_frame_orig, :] = seg_audio
            print(
                f"    - 片段数据复制完成（区间：{start_frame_orig}-{end_frame_orig}）"
            )
        except ValueError as e:
            print(f"⚠️  片段数据复制失败：{str(e)}（维度不匹配，可能是声道数处理错误）")

        # 删除临时片段
        os.remove(temp_seg_path)

    # 4. 保存最终音频（确保字节流与声道数/位深匹配）
    with wave.open(merged_path, "wb") as wf:
        wf.setnchannels(channels_orig)
        wf.setsampwidth(sample_width_orig)
        wf.setframerate(sr_orig)

        # 处理不同位深的字节流
        if bit_depth_orig == 24:
            # 24位：从int32提取低24位，转为3字节/样本
            audio_data = (empty_audio >> 8).astype(np.uint8)  # 移除高8位
            if channels_orig > 1:
                audio_data = audio_data.reshape(
                    -1, channels_orig * 3
                )  # 多声道合并为1维字节流
            audio_bytes = audio_data.tobytes()
        else:
            # 16/32位：直接转换为字节流（numpy自动处理维度）
            audio_bytes = empty_audio.tobytes()

        # 验证字节数（关键：总帧数 × 样本宽度 × 声道数）
        expected_bytes = total_frames_orig * sample_width_orig * channels_orig
        actual_bytes = len(audio_bytes)
        if abs(actual_bytes - expected_bytes) > 10:
            print(
                f"⚠️  音频字节数不匹配：预期{expected_bytes}字节，实际{actual_bytes}字节（可能导致时长错误）"
            )
        else:
            print(
                f"✅ 音频字节数匹配：预期{expected_bytes}字节，实际{actual_bytes}字节"
            )

        # 写入音频数据并验证最终帧数
        wf.writeframes(audio_bytes)
        final_frame_count = wf.getnframes()
        print(f"  最终写入帧数：{final_frame_count} → 预期帧数：{total_frames_orig}")
        if final_frame_count != total_frames_orig:
            print(
                f"⚠️  帧数不匹配！生成音频时长可能异常（计算时长：{final_frame_count/sr_orig:.2f}秒）"
            )
        else:
            print(
                f"✅ 帧数匹配！生成音频时长：{final_frame_count/sr_orig:.2f}秒（与原音频一致）"
            )

    # 用ffmpeg验证生成的音频信息（最权威验证）
    cmd = ["ffmpeg", "-hide_banner", "-i", merged_path]
    env = os.environ.copy()
    env["LC_ALL"] = "en_US.UTF-8"
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        env=env,
        encoding="utf-8",
        stdin=subprocess.DEVNULL,
    )
    print(f"\n  ffmpeg验证生成的音频信息：")
    for line in result.stderr.splitlines():
        if "Duration" in line or "Audio" in line:
            print(f"  {line}")  # 打印时长和音频参数

    print(f"✅ 生成 {speaker_id} 完整时间线音频：{merged_path}")
    return merged_path


def get_audio_duration(input_path):
    """单独提取原音频的真实总时长（修复核心）"""
    input_path = os.path.abspath(input_path).replace(os.sep, "/")
    cmd = ["ffmpeg", "-hide_banner", "-i", input_path]
    env = os.environ.copy()
    env["LC_ALL"] = "en_US.UTF-8"
    env["LANG"] = "en_US.UTF-8"
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        env=env,
        encoding="utf-8",
        stdin=subprocess.DEVNULL,
    )
    output = result.stderr if result.stderr else result.stdout

    # 优先解析 Duration 字段（格式：00:01:23.45）
    duration_match = re.search(r"Duration: (\d+:\d+:\d+\.\d+)", output)
    if duration_match:
        h, m, s = duration_match.group(1).split(":")
        total_duration = float(h) * 3600 + float(m) * 60 + float(s)
        return total_duration

    # 降级方案：用转码后的WAV时长（仅当原解析失败时）
    wav_path = convert_to_wav(
        input_path, os.path.join(os.path.dirname(input_path), "temp_transcode")
    )
    with wave.open(wav_path, "rb") as wf:
        transcode_duration = wf.getnframes() / wf.getframerate()
    os.remove(wav_path)
    shutil.rmtree(os.path.dirname(wav_path))
    print(f"⚠️  原音频时长解析失败，使用转码后WAV时长：{transcode_duration:.2f}秒")
    return transcode_duration


def extract_media_segment(input_path, output_path, start_sec, end_sec):
    try:
        input_path = os.path.abspath(input_path).replace(os.sep, "/")
        output_path = os.path.abspath(output_path).replace(os.sep, "/")
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        # 1. 判断输入是视频还是音频
        media_type = get_media_type(input_path)
        is_video = media_type == "video"  # 安全访问，默认False
        is_audio = media_type == "audio"  # 安全访问，默认False

        if not (is_video or is_audio):
            raise RuntimeError(f"输入文件不是有效的视频或音频：{input_path}")

        # 2. 构造ffmpeg命令（核心：流复制，保持原格式）
        env = os.environ.copy()
        env["LC_ALL"] = "en_US.UTF-8"
        env["LANG"] = "en_US.UTF-8"

        cmd = [
            "ffmpeg",
            "-y",  # 覆盖输出
            "-ss",
            str(start_sec),  # 开始时间（秒）
            "-to",
            str(end_sec),  # 结束时间（秒）
            "-i",
            input_path,  # 输入文件
        ]

        # 关键：使用流复制（-c copy），不重新编码，保持原格式和质量
        # 视频文件保留视频流和音频流，音频文件只保留音频流
        if is_video:
            cmd.extend(["-c:v", "copy"])  # 复制视频流
            if is_audio:
                cmd.extend(["-c:a", "copy"])  # 同时复制音频流（若有）
        else:  # 纯音频
            cmd.extend(["-c:a", "copy"])  # 复制音频流

        # 输出路径（需确保扩展名与原格式一致，如输入video.mp4，输出xxx.mp4）
        cmd.append(output_path)

        # 执行命令
        result = subprocess.run(
            cmd,
            env=env,
            text=True,
            encoding="utf-8",
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        result.check_returncode()

        # 校验输出文件
        if not os.path.exists(output_path):
            raise RuntimeError(f"片段提取失败：未生成文件（{output_path}）")
        if os.path.getsize(output_path) < 1024:
            raise RuntimeError(
                f"提取的片段为空（{output_path}），可能原文件损坏或时间区间无效"
            )

        return output_path

    except subprocess.CalledProcessError as e:
        # 特殊处理：部分格式不支持流复制（如某些古老格式），可尝试重新编码（可选）
        if (
            "Invalid codec for stream" in e.stderr
            or "could not find codec parameters" in e.stderr
        ):
            raise RuntimeError(f"格式不支持无损提取，需重新编码：{e.stderr}")
        else:
            raise RuntimeError(f"提取片段失败（{output_path}）：{e.stderr}")
    except OSError as e:
        if e.errno == 28:
            raise RuntimeError(f"磁盘空间不足，无法保存片段：{output_path}")
        elif e.errno == 13:
            raise RuntimeError(f"无写权限，无法保存片段：{output_path}")
        else:
            raise RuntimeError(f"IO错误（{output_path}）：{str(e)}")


def get_media_type(input_path: str) -> str:
    """判断媒体文件类型（音频/视频），返回 'audio' 或 'video'"""
    input_path = os.path.abspath(input_path)
    env = os.environ.copy()
    env["LC_ALL"] = "en_US.UTF-8"

    try:
        cmd = [
            "ffprobe", "-v", "error", "-show_entries", "stream=codec_type",
            "-of", "json", input_path
        ]
        result = subprocess.run(
            cmd, capture_output=True, env=env, text=True, encoding="utf-8", stdin=subprocess.DEVNULL
        )
        result.check_returncode() 
        info = json.loads(result.stdout)
        streams = info.get("streams", [])
        return "video" if any(s.get("codec_type") == "video" for s in streams) else "audio"
    except Exception as e:
        ext = os.path.splitext(input_path)[1].lower()
        video_exts = [".mp4", ".avi", ".mov", ".mkv", ".flv"]
        audio_exts = [".wav", ".mp3", ".flac", ".aac", ".ogg"]
        if ext in video_exts:
            return "video"
        elif ext in audio_exts:
            return "audio"
        raise RuntimeError(f"无法判断媒体类型（{input_path}）：{str(e)}")


def get_media_info(input_path: str) -> dict:
    """纯工具函数：仅解析媒体文件的原始信息，不处理特殊逻辑，失败直接抛错"""
    input_path = os.path.abspath(input_path)
    env = os.environ.copy()
    env["LC_ALL"] = "en_US.UTF-8"

    # 初始化返回结构（仅包含默认键，值由解析填充）
    media_info = {
        "is_video": False,
        "is_audio": False,
        "sr": None,  # 采样率（音频）
        "channels": None,  # 声道数（音频）
        "channel_layout": None,  # 声道布局（音频）
        "width": None,  # 宽度（视频）
        "height": None,  # 高度（视频）
        "fps": None,  # 帧率（视频）
        "sample_fmt": None,  # 样本格式（音频）
        "format": os.path.splitext(input_path)[1].lower()  # 文件扩展名
    }

    try:
        # 调用ffprobe获取流信息
        cmd = [
            "ffprobe",
            "-v", "error",
            "-show_entries", "stream=codec_type,sample_rate,channels,channel_layout,width,height,r_frame_rate,sample_fmt",
            "-of", "json",
            input_path
        ]
        result = subprocess.run(
            cmd,
            capture_output=True,
            env=env,
            text=True,
            encoding="utf-8",
            stdin=subprocess.DEVNULL
        )
        result.check_returncode()  # 解析失败直接抛错

        import json
        info = json.loads(result.stdout)
        streams = info.get("streams", [])

        # 提取视频/音频流信息（仅做解析，不做强制修改）
        for stream in streams:
            codec_type = stream.get("codec_type")
            if codec_type == "video":
                media_info["is_video"] = True
                media_info["width"] = stream.get("width")
                media_info["height"] = stream.get("height")
                fps_str = stream.get("r_frame_rate")
                if fps_str:
                    num, den = map(int, fps_str.split("/"))
                    media_info["fps"] = num / den if den != 0 else None
            elif codec_type == "audio":
                media_info["is_audio"] = True
                media_info["sr"] = int(stream["sample_rate"]) if stream.get("sample_rate") else None
                media_info["channels"] = int(stream["channels"]) if stream.get("channels") else None
                media_info["channel_layout"] = stream.get("channel_layout")
                media_info["sample_fmt"] = stream.get("sample_fmt")

        return media_info

    except Exception as e:
        # 只抛错，不做兜底（兜底由上层业务决定）
        raise RuntimeError(f"解析媒体信息失败（{input_path}）：{str(e)}")

def generate_empty_media_segment(
    media_type: str, 
    duration: float, 
    output_dir: str, 
    seg_id: str,
    ref_width: int,   
    ref_height: int, 
    ref_fps: float   
) -> str:
    """生成空片段时，直接使用参考分辨率和帧率"""
    env = os.environ.copy()
    env["LC_ALL"] = "en_US.UTF-8"
    cmd = ["ffmpeg", "-y", "-hide_banner", "-t", f"{duration:.4f}"]

    # 音频参数不变
    sr = 44100
    channels = 2
    channel_layout = "stereo"

    if media_type == "video":
        # 核心修改：空片段使用参考分辨率和帧率
        output_path = os.path.join(output_dir, f"empty_{seg_id}.mp4")
        cmd.extend([
            # 黑画面尺寸直接用参考分辨率，帧率用参考帧率
            "-f", "lavfi", "-i", f"color=c=black:s={ref_width}x{ref_height}:r={ref_fps}",
            "-f", "lavfi", "-i", f"anullsrc=r={sr}:cl={channel_layout}",
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "0",
            "-c:a", "pcm_s16le", "-ar", str(sr), "-ac", str(channels),
            "-shortest",
            output_path
        ])
    else:
        # 音频空片段逻辑不变
        output_path = os.path.join(output_dir, f"empty_{seg_id}.wav")
        cmd.extend([
            "-f", "lavfi", "-i", f"anullsrc=r={sr}:cl={channel_layout}",
            "-c:a", "pcm_s16le", "-ar", str(sr), "-ac", str(channels),
            output_path
        ])

    # 执行生成（后续逻辑不变）
    result = subprocess.run(
        cmd, capture_output=True, env=env, text=True, encoding="utf-8", stdin=subprocess.DEVNULL
    )
    if result.returncode != 0:
        raise RuntimeError(f"生成空片段失败：{result.stderr}")
    print(f"✅ 生成空片段（{ref_width}x{ref_height}）：{os.path.basename(output_path)}（时长：{duration:.2f}秒）")
    return output_path


def get_media_duration(file_path: str) -> float:
    """获取媒体时长，失败直接抛错"""
    try:
        cmd = [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", os.path.abspath(file_path)
        ]
        result = subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8", stdin=subprocess.DEVNULL
        )
        return float(result.stdout.strip())
    except Exception as e:
        raise RuntimeError(f"获取时长失败（{file_path}）：{str(e)}")


# -------------------------- 业务逻辑函数 --------------------------
def transcode_to_intermediate(
    seg_path: str, 
    media_type: str, 
    output_dir: str, 
    seg_idx: int,
    ref_width: int,  
    ref_height: int, 
    ref_fps: float   
) -> str:
    """转码时对齐参考分辨率，保持原始画面比例（等比例缩放+黑边填充）"""
    env = os.environ.copy()
    env["LC_ALL"] = "en_US.UTF-8"
    seg_name = os.path.splitext(os.path.basename(seg_path))[0]
    mid_ext = ".mp4" if media_type == "video" else ".wav"
    temp_path = os.path.join(output_dir, f"temp_seg_{seg_idx}_{seg_name}{mid_ext}")

    transcode_cmd = ["ffmpeg", "-y", "-hide_banner", "-i", seg_path]
    if media_type == "video":
        # 核心修改：视频转码用滤镜保持比例，对齐参考分辨率 
        scale_filter = f"scale=w=min({ref_width}\\,iw*sar):h=min({ref_height}\\,ih)"  # 转义逗号
        pad_filter = f"pad={ref_width}:{ref_height}:(ow-iw)/2:(oh-ih)/2:black"
        transcode_cmd.extend([
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "0",
            "-vf", f"{scale_filter},{pad_filter}",  # 拼接滤镜
            "-r", f"{ref_fps}",
            "-c:a", "pcm_s16le", "-ar", "44100", "-ac", "2", "-channel_layout", "stereo"
        ])
    else:
        # 音频转码逻辑不变
        transcode_cmd.extend([
            "-c:a", "pcm_s16le", "-ar", "44100", "-ac", "2", "-channel_layout", "stereo", "-vn"
        ])
    transcode_cmd.append(temp_path)

    # 执行转码（后续逻辑不变）
    result = subprocess.run(
        transcode_cmd, capture_output=True, env=env, text=True, encoding="utf-8", stdin=subprocess.DEVNULL
    )
    if result.returncode != 0:
        raise RuntimeError(f"片段 {seg_idx+1} 转码失败：{result.stderr}")
    print(f"✅ 片段 {seg_idx+1} 转码完成（对齐至 {ref_width}x{ref_height}）：{os.path.basename(temp_path)}")
    return temp_path

 
# -------------------------- 核心拼接函数（完整修改版） --------------------------
def stitch_segments_with_empty_timeline(
    media_list_sorted: List[List],  # [[路径, 开始时间, 结束时间, 时长], ...]
    model_input_path: str,  # 原媒体文件（用于获取总时长和兜底格式）
    output_path: str,
    fill_empty: bool = True
) -> str:
    """核心拼接函数：优先稳定性，统一中间格式，简化流程"""
    temp_files = []  # 记录所有临时文件（转码片段+空片段+拼接列表）
    try:
        # 1. 初始化配置
        output_path = os.path.abspath(output_path)
        output_dir = os.path.dirname(output_path)
        os.makedirs(output_dir, exist_ok=True)
        output_name = os.path.splitext(os.path.basename(output_path))[0]
        original_duration = get_media_duration(model_input_path)  # 原媒体总时长
        media_type = get_media_type(model_input_path)  # 整体媒体类型（视频/音频）
        print(f"\n📌 媒体类型：{media_type}，原时长：{original_duration:.2f}秒")

        # 2. 过滤无效片段
        valid_media = []
        for idx, (seg_path, s, e, seg_duration) in enumerate(media_list_sorted):
            seg_path = os.path.abspath(seg_path)
            if not os.path.exists(seg_path) or os.path.getsize(seg_path) < 1024 or s >= e or seg_duration <= 0:
                print(f"⚠️  片段 {idx+1} 无效（路径：{seg_path}），已跳过")
                continue
            valid_media.append([seg_path, s, e, seg_duration])
        if not valid_media:
            raise RuntimeError("无有效片段可拼接")
        print(f"📌 有效片段：{len(valid_media)}个，总时长：{sum(item[3] for item in valid_media):.2f}秒")


        # 新增：解析第一个有效片段的原始分辨率（作为参考标准）
        first_seg_path = valid_media[0][0]
        first_seg_info = get_media_info(first_seg_path)
        ref_width = first_seg_info["width"]
        ref_height = first_seg_info["height"]
        ref_fps = first_seg_info["fps"] or 25  # 参考帧率（默认25）
        if not ref_width or not ref_height:
            # 极端情况：第一个片段无分辨率信息，用默认值
            ref_width, ref_height = 1280, 720
        print(f"📌 参考分辨率：{ref_width}x{ref_height}，参考帧率：{ref_fps:.2f}fps")

        # 3. 转码所有有效片段为中间格式（确保格式统一）
        transcoded_media = []
        for idx, (seg_path, s, e, seg_duration) in enumerate(valid_media):
            # 转码（无论原格式如何，统一为中间格式）
            try:
                transcoded_path = transcode_to_intermediate(
                    seg_path, media_type, output_dir, idx,
                    ref_width=ref_width, ref_height=ref_height, ref_fps=ref_fps
                )
                transcoded_media.append([transcoded_path, s, e, seg_duration])
                temp_files.append(transcoded_path)
            except Exception as e:
                raise RuntimeError(f"片段 {idx+1} 处理失败：{str(e)}")
        valid_media = transcoded_media

        # 4. 生成最终片段列表（有效片段+空片段）
        final_segments = []
        if fill_empty:
            print("\n🔧 填充空白部分...")
            # 4.1 开头空片段
            first_start = valid_media[0][1]
            if first_start > 0.01:
                empty_path = generate_empty_media_segment(
                    media_type, first_start, output_dir, "start",
                    ref_width=ref_width, ref_height=ref_height, ref_fps=ref_fps
                )
                final_segments.append(empty_path)
                temp_files.append(empty_path)

            # 4.2 中间空片段
            for i in range(1, len(valid_media)):
                prev_end = valid_media[i-1][2]
                curr_start = valid_media[i][1]
                gap = curr_start - prev_end
                if gap > 0.01:
                    # 添加前一个有效片段 + 中间空片段
                    final_segments.append(valid_media[i-1][0])
                    empty_path = generate_empty_media_segment(media_type, gap, output_dir, f"mid_{i}",ref_width=ref_width, ref_height=ref_height, ref_fps=ref_fps)
                    final_segments.append(empty_path)
                    temp_files.append(empty_path)
                else:
                    # 间隙过小，直接添加前一个有效片段
                    final_segments.append(valid_media[i-1][0])

            # 4.3 结尾空片段
            last_end = valid_media[-1][2]
            # 计算已填充的总时长（有效片段+已加空片段）
            filled_duration = first_start + sum(item[3] for item in valid_media)
            filled_duration += sum(valid_media[i][1] - valid_media[i-1][2] for i in range(1, len(valid_media)) if valid_media[i][1] - valid_media[i-1][2] > 0.01)
            end_gap = original_duration - filled_duration
            if end_gap > 0.01:
                final_segments.append(valid_media[-1][0])
                empty_path = generate_empty_media_segment(media_type, end_gap, output_dir, "end",ref_width=ref_width, ref_height=ref_height, ref_fps=ref_fps)
                final_segments.append(empty_path)
                temp_files.append(empty_path)
            else:
                final_segments.append(valid_media[-1][0])
        else:
            # 不填充空白，直接拼接有效片段
            final_segments = [item[0] for item in valid_media]
            print("\n🔧 不填充空白，仅拼接有效片段")

        # 5. 生成拼接列表文件
        concat_list_path = os.path.join(output_dir, f"{output_name}_concat.txt")
        with open(concat_list_path, "w", encoding="utf-8") as f:
            for path in final_segments:
                f.write(f"file '{os.path.abspath(path)}'\n")
        temp_files.append(concat_list_path)
        print(f"\n📌 拼接列表生成完成（{len(final_segments)}个片段）")

        # 6. 拼接中间格式片段（直接复制流，最快且稳定）
        mid_output_path = os.path.join(output_dir, f"{output_name}_mid.mp4" if media_type == "video" else f"{output_name}_mid.wav")
        concat_cmd = [
            "ffmpeg", "-y", "-hide_banner",
            "-f", "concat", "-safe", "0", "-i", concat_list_path,
            "-c:v", "copy" if media_type == "video" else "-vn",  # 视频复制流，音频忽略视频
            "-c:a", "copy",  # 音频复制流
            "-shortest",  # 确保时长匹配
            mid_output_path
        ]
        print(f"🚀 开始拼接中间格式片段...")
        env = os.environ.copy()
        env["LC_ALL"] = "en_US.UTF-8"
        result = subprocess.run(
            concat_cmd, capture_output=True, env=env, text=True, encoding="utf-8", stdin=subprocess.DEVNULL
        )
        if result.returncode != 0:
            raise RuntimeError(f"拼接失败：{result.stderr}")
        temp_files.append(mid_output_path)  # 中间文件后续会清理

        # 7. 转码为最终输出格式（根据用户输入的output_path后缀）
        final_ext = os.path.splitext(output_path)[1].lower()
        # 定义格式→编码器映射（确保兼容性）
        format_encoder = {
            "video": {
                ".mp4": ("libx264", ["-preset", "ultrafast", "-crf", "23"]),
                ".avi": ("mpeg4", ["-qscale:v", "2"]),
                ".mov": ("libx264", ["-preset", "ultrafast", "-crf", "23"]),
                ".mkv": ("libx264", ["-preset", "ultrafast", "-crf", "23"])
            },
            "audio": {
                ".wav": ("copy", []),
                ".mp3": ("libmp3lame", ["-b:a", "192k"]),
                ".flac": ("flac", []),
                ".aac": ("aac", ["-b:a", "128k"])
            }
        }
        # 校验最终格式，无效则用默认
        valid_exts = list(format_encoder[media_type].keys())
        if final_ext not in valid_exts:
            final_ext = ".mp4" if media_type == "video" else ".mp3"
            output_path = os.path.join(output_dir, f"{output_name}{final_ext}")
            print(f"⚠️  输出格式无效，自动使用默认：{final_ext}")

        # 执行最终转码
        enc, enc_params = format_encoder[media_type][final_ext]
        transcode_cmd = [
            "ffmpeg", "-y", "-hide_banner", "-i", mid_output_path,
            "-c:v", enc if media_type == "video" else "-vn",
            "-c:a", enc if media_type == "audio" else "aac",
            *enc_params,
            output_path
        ]
        print(f"🔄 转码为最终格式：{final_ext}...")
        result = subprocess.run(
            transcode_cmd, capture_output=True, env=env, text=True, encoding="utf-8", stdin=subprocess.DEVNULL
        )
        if result.returncode != 0:
            raise RuntimeError(f"最终转码失败：{result.stderr}")

        # 8. 结果校验
        final_duration = get_media_duration(output_path)
        target_duration = original_duration if fill_empty else sum(item[3] for item in valid_media)
        print(f"\n✅ 拼接完成！")
        print(f"  - 输出文件：{output_path}")
        print(f"  - 最终时长：{final_duration:.2f}秒（目标：{target_duration:.2f}秒）")
        return output_path

    finally:
        # 清理所有临时文件
        print("\n🔧 清理临时文件...")
        for p in temp_files:
            if os.path.exists(p):
                try:
                    os.remove(p)
                    print(f"✅ 清理：{os.path.basename(p)}")
                except PermissionError:
                    print(f"⚠️  无法删除（被占用）：{os.path.basename(p)}")
        # 终止残留FFmpeg进程（Windows）
        if os.name == "nt":
            try:
                subprocess.run(["taskkill", "/f", "/im", "ffmpeg.exe"], capture_output=True, stdin=subprocess.DEVNULL)
            except:
                pass