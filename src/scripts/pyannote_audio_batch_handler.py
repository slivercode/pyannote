import os
import json
import numpy as np
import soundfile as sf 
import pathlib
import argparse
import subprocess
import sys
import time
import shutil 


current_script_dir = os.path.dirname(os.path.abspath(__file__))
if current_script_dir not in sys.path:
    sys.path.insert(0, current_script_dir)  # 插入到最前面，优先搜索
print("子进程 sys.path：", sys.path)  # 打印所有模块搜索路径     


from torch_loader import use_gpu,torch,torch_path
     
from util import ( 
    get_audio_info,
    get_audio_duration, 
    convert_to_wav,
    load_wav,
    extract_media_segment,
    stitch_segments_with_empty_timeline,
    
)

from pyannote.audio import Pipeline
from pyannote.audio.pipelines.speaker_diarization import DiarizeOutput
import wave  # 需在文件顶部导入wave库
from pyannote.audio.pipelines.utils.hook import ProgressHook
import concurrent.futures  # 新增：并发处理模块 

device = "cuda" if use_gpu  else "cpu"
# device = "cuda"
print(f"使用设备: {device}")

MIN_SEGMENT_DURATION = 0.5  # 最短片段长度（秒）
LARGE_AUDIO_CHUNK_MIN = 60
NUM_SPEAKERS = 0  # 0表示自动检测
MAX_SPEAKERS = 0  # 0表示自动检测
MIN_SPEAKERS = 0  # 0表示自动检测
# 定义时间比较的精度（根据实际情况调整）
EPSILON = 1e-3  # 0.001秒的误差容忍
TRANSLATE = False  # 默认不翻译
SPEAKER_TYPES = {
    "EXCLUSIVE": "spk",  # 明确单人
    "MIX": "mix",  # 多人重叠
    "UNKNOWN": "unknown",  # 未识别（无明确/重叠说话人）
}
# 新增：并发转录配置（IO密集型，建议4-8线程，避免服务器过载）
TRANSCRIBE_THREADS = 8  # 默认线程数
MAX_TRANSCRIBE_THREADS = 8  # 最大线程数限制
EXTRACT_AUDIO_BY_ROLE = True  # 按说话人提取音频片段
PRESERVE_TIMELINE = False  # 提取音频片段保留时间线




# ==============================================================================
# 工具函数（统一路径处理：绝对路径 + / 分隔符）
# ==============================================================================
def get_packaged_cache_path():
    if getattr(sys, "frozen", False):
        exe_dir = pathlib.Path(sys.executable).parent
    else:
        exe_dir = pathlib.Path(__file__).parent.parent.parent
    # 转绝对路径 + / 分隔符
    return os.path.abspath(str(exe_dir)).replace(os.sep, "/")


def load_model(auth_token="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", retry=3):
    print(f"=== 初始化 Pyannote 模型 ===")
    if not auth_token:
        raise ValueError("请提供有效的 Hugging Face 访问令牌！")

    packaged_cache = get_packaged_cache_path()
    hf_cache = os.path.join(packaged_cache, "hf_cache")
    os.makedirs(hf_cache, exist_ok=True)
    hf_cache = hf_cache.replace(os.sep, "/")  # 统一分隔符
    print(f"Hugging Face 缓存目录: {hf_cache}")

    for attempt in range(retry):
        try:
            pipeline = Pipeline.from_pretrained(
                "pyannote/speaker-diarization-community-1",
                token=auth_token,
                cache_dir=hf_cache,
            )
            if device == "cuda":
                pipeline.to(torch.device("cuda")) # type: ignore
            print("模型加载成功！")
            return pipeline
        except Exception as e:
            if attempt == retry - 1:
                raise RuntimeError(f"模型加载失败：{str(e)}")
            print(f"⚠️  模型加载失败，重试 {attempt+1}/{retry}...")
            time.sleep(5)


DIARIZATION_PIPELINE = load_model()


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


class LogHook(ProgressHook):
    def before_pipeline(self, pipeline, **kwargs):
        print(f"开始处理音频...")

    def before_step(self, step_name, **kwargs):
        print(f"即将执行步骤：{step_name}")

    def update_progress(self, step_name, progress):
        # 打印进度百分比
        print(f"步骤 {step_name} 进度：{progress*100:.1f}%")

    def after_pipeline(self, pipeline, result, **kwargs):
        print("处理完成！")

def transcribe_with_qwen_asr(task_id, segment_audio_path, tmp_dir):
    """
    子进程方式（Windows兼容版）：解决参数错位+路径问题
    """
    # 1. 基础校验：音频文件存在
    if not os.path.exists(segment_audio_path):
        err_msg = "转录失败（音频文件不存在）"
        print(f"警告：{err_msg} → 片段{task_id}（{segment_audio_path}）")
        return (task_id, err_msg)

    # 2. 关键：确保Python路径正确（项目内嵌入式Python）
    # --- 请根据你项目内Python的实际位置修改此处路径 ---
    python_exe_path = os.path.abspath("./python/python.exe")  # 示例：项目根目录下的python文件夹
    # 检查Python路径是否存在
    if not os.path.exists(python_exe_path):
        err_msg = f"转录失败（Python解释器不存在：{python_exe_path}）"
        print(f"警告：{err_msg} → 片段{task_id}")
        return (task_id, err_msg)

    # 3. 处理Windows路径格式（避免/和\混用导致解析错误）
    segment_audio_path = os.path.normpath(segment_audio_path)  # 转为 D:\xxx\seg_1.WAV
    tmp_dir = os.path.normpath(tmp_dir)
    print(f"片段{os.path.exists(tmp_dir)}：临时路径 → {tmp_dir}")    
    # 确保临时目录存在（call_api可能不自动创建）
    os.makedirs(tmp_dir, exist_ok=True)
 
    # 4. 构造子进程命令（每个参数独立，无拼接）
    site_pkgs = os.path.join(os.path.dirname(python_exe_path), "Lib", "site-packages")
    tmp_pth = os.path.join(site_pkgs, f"tmp_torch_{task_id}.pth")
    with open(tmp_pth, "w") as f:
        f.write(torch_path)
    cmd = [
        python_exe_path,
        # "-c", f"import sys; sys.path.insert(0, '{torch_path}')",
        "-m", "qwen3_asr_toolkit.call_api",  # 直接调用call_api模块
        "-i", segment_audio_path,
        "-t", tmp_dir,
        "-j", "1",
        "--silence"
    ]
    # 调试：打印实际执行的命令（关键！看参数是否正确）
    print(f"\n片段{task_id}：子进程命令 → {cmd}")

    try:
        # 5. 执行子进程（移除Windows不兼容的环境变量，避免编码干扰）
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",  # Windows下用utf-8确保参数解析无乱码
            check=True,
        )
        print(f"片段{task_id}：子进程执行成功 → {result.returncode}")

        # 6. 读取转录结果（和原逻辑一致）
        transcript_txt = os.path.splitext(segment_audio_path)[0] + ".txt"
        if os.path.exists(transcript_txt):
            print(f"打开 → {transcript_txt}")
            try:
                with open(transcript_txt, "r", encoding="utf-8") as f:
                    lines = f.read().strip().split("\n")
            except UnicodeDecodeError as e:
                print(f"⚠️ UTF-8 解码失败：{e}，尝试使用 GBK 编码")
                try:
                    with open(transcript_txt, "r", encoding="gbk") as f:
                        lines = f.read().strip().split("\n")
                except Exception as e2:
                    print(f"❌ GBK 解码也失败：{e2}，使用默认内容")
                    lines = ["未知语言", "转录失败"]
            # os.remove(transcript_txt)
            language = lines[0] if len(lines) >= 1 else "未知语言"
            full_text = lines[1] if len(lines) >= 2 else "无有效内容"
            return (task_id, f"{full_text}")
        print(f"不存在 → {transcript_txt}")
        return (task_id, "转录失败（未生成结果文件）")

    except subprocess.CalledProcessError as e:
        # 捕获子进程执行错误（打印详细stderr，帮助定位）
        # 打印完整的stderr，不截断（关键：获取具体错误原因）
        err_detail = f"返回码：{e.returncode}\n完整错误信息：{e.stderr}"
        err_msg = f"转录失败（子进程执行错误）：\n{err_detail}"
        # 完整打印错误，方便定位
        print(f"警告：片段{task_id}（{os.path.basename(segment_audio_path)}）→ {err_msg}")
        return (task_id, err_msg)
    except Exception as e:
        err_msg = f"转录失败（其他错误）：{str(e)[:100]}..."
        print(f"警告：片段{task_id} → {err_msg}")
        return (task_id, err_msg)
    finally:
        if os.path.exists(tmp_pth):
            os.remove(tmp_pth)

def get_single_and_mix_segments(speaker_diarization, min_duration):
    """
    从完整的speaker_diarization中区分单人片段和mix片段
    :param speaker_diarization: 完整的说话人分割结果
    :param min_duration: 最小片段时长阈值
    :return: (single_segs, mix_segs) —— 单人片段列表、mix片段列表
    """
    all_turns = []
    for seg in speaker_diarization:
        turn, spk = seg
        all_turns.append(
            (turn.start, turn.end, spk)
        )  # 存储所有turn（开始、结束、说话人）

    # 步骤1：生成所有事件点（开始/结束），用于扫描重叠
    events = []
    for s, e, _ in all_turns:
        events.append((s, "start"))  # 开始事件
        events.append((e, "end"))  # 结束事件
    # 排序：先按时间，结束事件优先于同时刻的开始事件（避免重复计算）
    events.sort(key=lambda x: (x[0], 0 if x[1] == "end" else 1))

    # 步骤2：扫描事件点，统计每个时间段的说话人数量
    time_segments = []  # 存储 (时间段开始, 时间段结束, 该时间段内说话人数量)
    current_time = None
    current_spk_count = 0

    for time, event_type in events:
        if current_time is not None and time > current_time + EPSILON:
            # 新增一个时间段（current_time 到 time）
            time_segments.append((current_time, time, current_spk_count))
        # 更新当前状态
        if event_type == "start":
            current_spk_count += 1
        else:
            current_spk_count -= 1
        current_time = time

    # 步骤3：分类为“单人片段”和“mix片段”，并过滤短片段
    single_segs = []  # 格式：(start, end, speaker_list) —— speaker_list仅1个元素
    mix_segs = []  # 格式：(start, end, speaker_list) —— speaker_list≥2个元素

    for s, e, spk_count in time_segments:
        duration = e - s
        if duration < min_duration:
            continue  # 过滤短片段

        # 找到该时间段内所有的说话人（去重）
        current_speakers = set()
        for turn_s, turn_e, spk in all_turns:
            # 判断turn与当前时间段是否重叠（重叠部分≥0.01秒）
            overlap_s = max(s, turn_s)
            overlap_e = min(e, turn_e)
            if overlap_e - overlap_s > 0.01:
                current_speakers.add(spk)
        current_speakers = list(current_speakers)

        # 分类
        if len(current_speakers) == 1:
            single_segs.append((s, e, current_speakers[0]))
        elif len(current_speakers) >= 2:
            mix_segs.append((s, e, current_speakers))

    return single_segs, mix_segs


def get_unknown_segments(single_segs, mix_segs, total_duration):
    """
    计算未识别区间：总时长 - 明确说话人区间 - mix区间
    :param single_segs: 明确说话人区间（list of (s,e)）
    :param mix_segs: mix区间（list of (s,e)）
    :param total_duration: 音频总时长
    :return: unknown区间列表
    """
    # 合并明确和mix的所有已占用区间
    used_segs = single_segs + mix_segs
    if not used_segs:
        return [(0.0, total_duration)] if total_duration >= MIN_SEGMENT_DURATION else []
    # 排序并合并已占用区间
    used_segs.sort()
    merged_used = [list(used_segs[0])]
    for s, e in used_segs[1:]:
        last_s, last_e = merged_used[-1]
        if s <= last_e + EPSILON:
            merged_used[-1][1] = max(last_e, e)
        else:
            merged_used.append([s, e])
    # 计算未占用区间（unknown）
    unknown_segs = []
    prev_end = 0.0
    for s, e in merged_used:
        if s - prev_end >= MIN_SEGMENT_DURATION:
            unknown_segs.append((prev_end, s))
        prev_end = e
    # 检查最后一段（merged_used结束到总时长）
    if total_duration - prev_end >= MIN_SEGMENT_DURATION:
        unknown_segs.append((prev_end, total_duration))
    return unknown_segs

    # -------------------------- 新增4：合并音频并更新时间记录 --------------------------

def diarization(file_path, output_path):
    # 转绝对路径
    file_path = os.path.abspath(file_path).replace(os.sep, "/")
    output_path = os.path.abspath(output_path).replace(os.sep, "/")
    # 重新创建目录
    os.makedirs(output_path, exist_ok=True)

    # 创建输出目录
    base_name = os.path.basename(os.path.normpath(file_path))
    output_dir = os.path.join(output_path, base_name)
    output_dir = output_dir.replace(os.sep, "/")
    # 如果output_dir存在，先删除再创建
    if os.path.exists(output_dir):
        # 递归删除目录（包括所有子文件和子目录）
        shutil.rmtree(output_dir)
    os.makedirs(output_dir, exist_ok=True)

    # 创建输出目录-临时文件夹
    tmp_dir = os.path.join(output_dir, "tmp")
    tmp_dir = tmp_dir.replace(os.sep, "/")
    os.makedirs(tmp_dir, exist_ok=True)
    tmp_dir = os.path.abspath(tmp_dir).replace(os.sep, "/")
    print(f"\n处理文件：{file_path}")

    # 新增：校验文件有效性
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"文件不存在：{file_path}")
    if os.path.getsize(file_path) == 0:
        raise RuntimeError(f"空文件：{file_path}")
    # 校验音频可读取（替换为内置open，避免soundfile依赖）
    try:
        # 读取文件前1024字节（验证文件可访问且非空音频）
        with open(file_path, "rb") as f:
            header = f.read(1024)
            if len(header) < 10:  # 音频文件头至少有基础标识（如MP3的ID3、WAV的RIFF）
                raise RuntimeError("文件过小，可能不是有效音频")
    except Exception as e:
        raise RuntimeError(f"无效音频文件（{file_path}）：{str(e)}")

    transcode_dir = os.path.join(tmp_dir, "transcoded")
    transcode_dir = transcode_dir.replace(os.sep, "/")
    os.makedirs(transcode_dir, exist_ok=True)

    # 转码
    convert_start = time.perf_counter()
    wav_path = convert_to_wav(file_path, transcode_dir)
    print(f"  [耗时] 转码：{time.perf_counter() - convert_start:.2f} 秒")

    # 关键修改1：用新函数解析原音频真实总时长
    total_duration = get_audio_duration(wav_path)
    # 关键修改2：读取原音频采样率（确保与总时长匹配）
    orig_info = get_audio_info(file_path)
    sr_orig = orig_info.get("sample_rate", 44100)
    print(f"  原音频真实信息：时长{total_duration:.2f}秒，采样率{sr_orig}Hz")

    input_audio, sr = load_wav(wav_path)
    input_audio_tensor = (
        torch.from_numpy(input_audio.astype(np.float32)).unsqueeze(0).to(device)
    )
    transcode_duration = len(input_audio) / sr
    if abs(total_duration - transcode_duration) > 0.1:  # 允许0.1秒误差
        print(
            f"⚠️  转码后WAV时长（{transcode_duration:.2f}秒）与原音频（{total_duration:.2f}秒）不一致，可能影响时间映射！"
        )

    # 识别
    # 使用自定义 hook
    with LogHook() as hook:
        if NUM_SPEAKERS > 0:
            diarize_result: DiarizeOutput = DIARIZATION_PIPELINE(
                {"waveform": input_audio_tensor, "sample_rate": sr},
                hook=hook,
                num_speakers=NUM_SPEAKERS,
            ) # type: ignore
        elif MIN_SPEAKERS > 0 and MAX_SPEAKERS > 0:
            diarize_result: DiarizeOutput = DIARIZATION_PIPELINE(
                {"waveform": input_audio_tensor, "sample_rate": sr},
                hook=hook,
                min_speakers=MIN_SPEAKERS,
                max_speakers=MAX_SPEAKERS,
            ) # type: ignore
        else:
            diarize_result: DiarizeOutput = DIARIZATION_PIPELINE(
                {"waveform": input_audio_tensor, "sample_rate": sr}, hook=hook
            ) # type: ignore

    print(
        f"  → 共识别出 {len(list(diarize_result.speaker_diarization.labels()))} 个说话人"
    )
    print(f"count_role：{len(list(diarize_result.speaker_diarization.labels()))} ")

    translate_dir = os.path.join(tmp_dir, "translated")
    translate_dir = translate_dir.replace(os.sep, "/")
    os.makedirs(translate_dir, exist_ok=True)

    return diarize_result, output_dir, translate_dir, total_duration, wav_path, sr_orig


def process_single_file(file_path, output_path):
    diarize_result, output_dir, translate_dir, total_duration, wav_path, sr_orig = (
        diarization(file_path, output_path)
    )
    file_name, ext_with_dot = os.path.splitext(file_path)
    # 去掉扩展名前的点，得到纯后缀
    seg_ext = f".{ ext_with_dot.lstrip('.') }" # lstrip('.') 用于移除开头的点
    print(f"PROGRESS:40%")
    print(f"result_root：{output_dir}")

    # 替换原步骤1和2：统一从speaker_diarization提取并区分单人/mix
    single_segs, mix_segs = get_single_and_mix_segments(
        diarize_result.speaker_diarization, MIN_SEGMENT_DURATION
    )
    # 3. 获取unknown区间
    unknown_segs = get_unknown_segments(
        [(s, e) for s, e, _ in single_segs],
        [(s, e) for s, e, _ in mix_segs],
        total_duration,
    )

    # -------------------------- 统一记录所有片段数据（含翻译） --------------------------
    all_records = []  # 存储所有片段记录：序号、开始、结束、时长、说话人、内容
    transcribe_tasks = []  # 待转录任务列表：(task_id, 片段路径, 临时目录)
    global_seq = 1  # 全局序号（跨类型连续）
    speaker_audio_map = {
        SPEAKER_TYPES["MIX"]: [],
        SPEAKER_TYPES["UNKNOWN"]: [],
    }  # 音频片段路径映射：说话人→[片段路径列表]

    # 创建保存目录/output/speaker_audios
    speaker_dir = os.path.join(output_dir, "speaker_audios")
    speaker_dir = speaker_dir.replace(os.sep, "/")
    os.makedirs(speaker_dir, exist_ok=True)

    # （1）处理明确说话人（spkXX）
    for s, e, spk in single_segs:
        duration = round(e - s, 2)
        spk_id = spk.replace("SPEAKER_", SPEAKER_TYPES["EXCLUSIVE"])  # 转为spk00格式
        # 初始化说话人音频列表
        if spk_id not in speaker_audio_map:
            speaker_audio_map[spk_id] = []
        # 提取音频片段
        spk_dir = os.path.join(speaker_dir, spk_id).replace(os.sep, "/")
        os.makedirs(spk_dir, exist_ok=True) 
        seg_path = os.path.join(spk_dir, f"seg_{global_seq}{seg_ext}").replace(
            os.sep, "/"
        )
        if EXTRACT_AUDIO_BY_ROLE:
            extract_media_segment(file_path, seg_path, s, e)

        # 记录数据
        all_records.append(
            {
                "序号": global_seq,
                "开始时间(秒)": round(s, 2),
                "结束时间(秒)": round(e, 2),
                "持续时间(秒)": duration,
                "说话人": spk_id,
                "说话内容": "待转录",
                "音频路径": seg_path,
            }
        )
        # 加入音频映射
        speaker_audio_map[spk_id].append((seg_path, round(s, 2), round(e, 2), duration))

        # 收集转录任务（仅开启TRANSLATE时添加）
        if TRANSLATE:
            transcribe_tasks.append((global_seq, seg_path, translate_dir))
        global_seq += 1

    # （2）处理mix（多人重叠）- 新增内容识别
    for s, e, spk in mix_segs:
        duration = round(e - s, 2)
        mix_dir = os.path.join(speaker_dir, SPEAKER_TYPES["MIX"]).replace(os.sep, "/")
        os.makedirs(mix_dir, exist_ok=True) 
        seg_path = os.path.join(mix_dir, f"seg_{global_seq}{seg_ext}").replace(
            os.sep, "/"
        )
        # 提取mix片段音频
        if EXTRACT_AUDIO_BY_ROLE:
            extract_media_segment(file_path, seg_path, s, e)

        # 记录数据（更新为实际转录内容）
        all_records.append(
            {
                "序号": global_seq,
                "开始时间(秒)": round(s, 2),
                "结束时间(秒)": round(e, 2),
                "持续时间(秒)": duration,
                "说话人": SPEAKER_TYPES["MIX"],
                "说话内容": "待转录",
                "音频路径": seg_path,
            }
        )
        # 加入音频映射（格式不变）
        speaker_audio_map[SPEAKER_TYPES["MIX"]].append(
            (seg_path, round(s, 2), round(e, 2), duration)
        )
        if TRANSLATE:
            transcribe_tasks.append((global_seq, seg_path, translate_dir))
        global_seq += 1

    # （3）处理unknown（未识别）
    for s, e in unknown_segs:
        duration = round(e - s, 2)
        unknown_dir = os.path.join(speaker_dir, SPEAKER_TYPES["UNKNOWN"]).replace(
            os.sep, "/"
        )
        os.makedirs(unknown_dir, exist_ok=True) 
        seg_path = os.path.join(unknown_dir, f"seg_{global_seq}{seg_ext}").replace(
            os.sep, "/"
        )
        if EXTRACT_AUDIO_BY_ROLE:
            extract_media_segment(file_path, seg_path, s, e)
        # 记录数据（unknown无翻译内容）
        all_records.append(
            {
                "序号": global_seq,
                "开始时间(秒)": round(s, 2),
                "结束时间(秒)": round(e, 2),
                "持续时间(秒)": duration,
                "说话人": SPEAKER_TYPES["UNKNOWN"],
                "说话内容": "",
                "音频路径": seg_path,
            }
        )
        # 加入音频映射
        speaker_audio_map[SPEAKER_TYPES["UNKNOWN"]].append(
            (seg_path, round(s, 2), round(e, 2), duration)
        )
        global_seq += 1

    # -------------------------- 步骤2：并发执行转录任务（核心优化） --------------------------
    if TRANSLATE and transcribe_tasks:
        print(f"\n=== 并发转录语音片段（线程数：{TRANSCRIBE_THREADS}）===")
        # 创建线程池（限制最大线程数，避免服务器拒绝连接）
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=TRANSCRIBE_THREADS
        ) as executor:
            # 1. 提交所有转录任务到线程池
            future_map = {}  # 关联：Future对象 → (任务ID, 片段路径)
            for task in transcribe_tasks:
                tid, spath, tdir = task
                future = executor.submit(transcribe_with_qwen_asr, tid, spath, tdir)
                future_map[future] = (tid, spath)

            # 2. 异步获取结果并更新到all_records
            completed_count = 0
            total_tasks = len(transcribe_tasks)
            for future in concurrent.futures.as_completed(future_map):
                tid, spath = future_map[future]
                try:
                    # 获取转录结果（task_id, 内容）
                    task_id, transcript = future.result()
                    # 根据任务ID匹配并更新记录
                    for record in all_records:
                        if record["序号"] == task_id:
                            record["说话内容"] = transcript
                            break
                    completed_count += 1
                    print(
                        f"✅ 进度：{completed_count}/{total_tasks} → 片段{tid}（{os.path.basename(spath)}）"
                    )
                except Exception as e:
                    print(
                        f"❌ 转录线程异常 → 片段{tid}（{os.path.basename(spath)}）：{str(e)}"
                    )
    else:
        # 未开启转录，更新占位符为“未翻译”
        for record in all_records:
            if record["说话内容"] == "待转录":
                record["说话内容"] = "未翻译"

    print(f"PROGRESS:70%")
    # -------------------------- 保存最终数据--------------------------
    # 1. 单独保存【原始时间顺序记录】（按音频时间排序，含原始时间+内容）
    # 按原始开始时间排序（确保顺序正确）
    all_records_sorted = sorted(all_records, key=lambda x: x["开始时间(秒)"])
    raw_record_path = os.path.join(output_dir, f"原始时间顺序记录.json").replace(
        os.sep, "/"
    )
    with open(raw_record_path, "w", encoding="utf-8") as f:
        json.dump(all_records_sorted, f, ensure_ascii=False, indent=2)
    print(f"✅ 原始时间顺序记录已保存：{raw_record_path}")
    # 2. 分说话人合并音频并保存【说话人合并后记录】
    for speaker_id, audio_list in speaker_audio_map.items():
        if not audio_list:
            print(f"⚠️  说话人{speaker_id}无有效片段，跳过合并")
            continue

        # 步骤1：合并当前说话人的音频（按原始时间排序）
        audio_list_sorted = sorted(audio_list, key=lambda x: x[1]) 

        # 提前生成merged_path（和concat_audio_with_ffmpeg的路径完全一致）
        merged_path = os.path.join(speaker_dir, speaker_id, f"merged{seg_ext}").replace(
            os.sep, "/"
        )

        # 新增：打印当前合并模式（关键验证）
        print(f"\n=== 处理说话人 {speaker_id} ===")
        print(f"  保留时间线模式：{PRESERVE_TIMELINE}")
        print(f"  提取音频开关：{EXTRACT_AUDIO_BY_ROLE}")
        print(f"  合并路径：{merged_path}")

        # 根据参数选择合并方式（两者均接收merged_path）
        if EXTRACT_AUDIO_BY_ROLE:
            stitch_segments_with_empty_timeline(
                    media_list_sorted=audio_list_sorted,  
                    model_input_path=file_path,
                    output_path=merged_path,
                    fill_empty=PRESERVE_TIMELINE,
            )
            print(f"✅ 拼接生成{'保留' if PRESERVE_TIMELINE else '无'}时间线 {speaker_id} 合并音频：{merged_path}") 
            print(f"result_merge_speaker：{merged_path}")

        # 步骤2：计算合并后的总时长和各片段相对时间
        merged_seg_list = []
        current_offset = 0.0  # 合并后的时间偏移（累计时长）

        for seg_path, orig_s, orig_e, orig_duration in audio_list_sorted:
            # 查找该片段的原始记录（获取说话内容）
            seg_content = "未获取内容"
            for raw_rec in all_records_sorted:
                s_diff = abs(raw_rec["开始时间(秒)"] - orig_s)
                e_diff = abs(raw_rec["结束时间(秒)"] - orig_e)
                if (
                    s_diff < EPSILON
                    and e_diff < EPSILON
                    and raw_rec["说话人"] == speaker_id
                ):
                    seg_content = raw_rec["说话内容"]
                    break

            # 记录合并后的片段信息
            merged_seg = {
                "原始序号": next(
                    # 迭代器：寻找匹配的记录
                    (
                        rec["序号"]
                        for rec in all_records_sorted
                        if (
                            abs(rec["开始时间(秒)"] - orig_s) < EPSILON * 2
                        )  # 放宽精度到2倍误差
                        and (
                            abs(rec["结束时间(秒)"] - orig_e) < EPSILON * 2
                        )  # 增加结束时间校验
                        and rec["说话人"] == speaker_id
                    ),
                    -1,  # 找不到时返回默认值-1，避免StopIteration
                ),
                "原始开始时间(秒)": round(orig_s, 2),
                "原始结束时间(秒)": round(orig_e, 2),
                "合并后开始时间(秒)": round(current_offset, 2),
                "合并后结束时间(秒)": round(current_offset + orig_duration, 2),
                "持续时间(秒)": orig_duration,
                "说话内容": seg_content,
            }
            merged_seg_list.append(merged_seg)
            current_offset += orig_duration

        # 3. 单独保存【说话人合并后记录】（按说话人分组）
        merged_record_path = os.path.join(
            speaker_dir, speaker_id, f"{speaker_id}_合并后时间顺序记录.json"
        ).replace(os.sep, "/")
        try:
            with open(merged_record_path, "w", encoding="utf-8") as f:
                json.dump(merged_seg_list, f, ensure_ascii=False, indent=2)
            print(f"✅ 说话人合并后记录已保存：{merged_record_path}")
        except UnicodeEncodeError as e:
            print(f"❌ {speaker_id}_合并后时间顺序记录.json未写入：{e}")
            print(f"尝试清理数据中的非法字符后重新保存...")
            # 清理数据中可能的编码问题
            cleaned_list = []
            for seg in merged_seg_list:
                cleaned_seg = {}
                for key, value in seg.items():
                    if isinstance(value, str):
                        # 移除或替换非法字符
                        cleaned_seg[key] = value.encode('utf-8', errors='ignore').decode('utf-8')
                    else:
                        cleaned_seg[key] = value
                cleaned_list.append(cleaned_seg)
            try:
                with open(merged_record_path, "w", encoding="utf-8") as f:
                    json.dump(cleaned_list, f, ensure_ascii=False, indent=2)
                print(f"✅ 清理后成功保存：{merged_record_path}")
            except Exception as e2:
                print(f"❌ 清理后仍然失败：{e2}")
    print(f"PROGRESS:100%")

    # 递归删除目录（包括所有子文件和子目录）
    # shutil.rmtree(translate_dir)


# -------------------------- 主程序 --------------------------
if __name__ == "__main__":
    print(f"PROGRESS:5%")
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input-path",
        type=str,
        required=True,
        help="单个文件或文件夹的绝对路径/相对路径",
    )
    parser.add_argument(
        "--output-path",
        type=str,
        default="output",
        help="输出根目录（默认当前目录下的 output）",
    )
    parser.add_argument(
        "--translate",
        type=str,
        default="false",
        help="是否翻译，默认步翻译",
    )
    parser.add_argument(
        "--extract-speech",
        type=str,
        default="true",
        help="是否翻译，默认步翻译",
    )
    parser.add_argument(
        "--preserve-timeline",
        type=str,
        default="false",
        help="是否生成保留时间线的完整音频（默认不保留）",
    )
    parser.add_argument(
        "--keep-tmp",
        type=str,
        default="false",
        help="是否保留未被识别的片段（默认不保留）",
    )
    parser.add_argument(
        "--min-segment-duration",
        type=float,
        default=0.5,
        help="过滤短于 x 秒的片段（默认0.1秒）",
    )

    parser.add_argument(
        "--num-speakers",
        type=int,
        default=0,
        help="角色数量",
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

    args = parser.parse_args()

    try:
        MIN_SEGMENT_DURATION = args.min_segment_duration
        NUM_SPEAKERS = args.num_speakers
        MIN_SPEAKERS = args.min_speakers
        MAX_SPEAKERS = args.max_speakers
        TRANSLATE = args.translate == "true"
        EXTRACT_AUDIO_BY_ROLE = args.extract_speech == "true"
        PRESERVE_TIMELINE = args.preserve_timeline == "true"
        start_time = time.time()
        if os.path.isfile(args.input_path):
            process_single_file(
                file_path=args.input_path,
                output_path=args.output_path,
            )
        else:
            raise RuntimeError(f"输入路径不存在：{args.input_path}")

        # 耗时统计
        total_time = (time.time() - start_time) / 60
        print(f"\n⏱️  总耗时：{total_time:.2f} 分钟")

    except Exception as e:
        print(f"\n❌ 执行失败：{str(e)}")
        sys.exit(1)
