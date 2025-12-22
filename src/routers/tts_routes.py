"""
TTS路由模块
处理文本转语音相关功能
"""
import json as json_module
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict

import requests
from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse

router = APIRouter(prefix="/api", tags=["TTS功能"])

from config.dependencies import get_tts_dubbing_tasks, get_current_dir, get_output_dir

router = APIRouter(prefix="/api", tags=["TTS功能"])


@router.get("/tts-proxy/gpt-sovits", summary="GPT-SoVITS TTS代理")
async def gpt_sovits_proxy(
    text: str,
    text_lang: str,
    ref_audio_path: str,
    prompt_text: str,
    prompt_lang: str,
    speed_factor: float = 1.0,
    api_url: str = Query(..., description="GPT-SoVITS API地址")
):
    """
    代理GPT-SoVITS TTS请求，解决跨域问题
    前端通过本地后端访问远程GPT-SoVITS服务
    """
    try:
        # 确保API地址正确
        if not api_url.endswith('/tts'):
            api_url += '/tts'
        
        # 构建请求参数
        params = {
            "text": text,
            "text_lang": text_lang,
            "ref_audio_path": ref_audio_path,
            "prompt_text": prompt_text,
            "prompt_lang": prompt_lang,
            "speed_factor": speed_factor
        }
        
        print(f"🔄 代理TTS请求: {api_url}")
        print(f"📋 参数: {params}")
        
        # 发送请求到GPT-SoVITS服务器
        response = requests.get(api_url, params=params, timeout=30, stream=True)
        response.raise_for_status()
        
        # 获取Content-Type
        content_type = response.headers.get('Content-Type', 'audio/wav')
        
        print(f"✅ TTS请求成功，Content-Type: {content_type}")
        
        # 流式返回音频数据
        return StreamingResponse(
            response.iter_content(chunk_size=8192),
            media_type=content_type,
            headers={
                "Content-Disposition": "attachment; filename=tts_output.wav"
            }
        )
        
    except requests.exceptions.Timeout:
        raise HTTPException(status_code=504, detail="TTS服务请求超时")
    except requests.exceptions.ConnectionError:
        raise HTTPException(status_code=503, detail="无法连接到TTS服务器")
    except requests.exceptions.HTTPError as e:
        raise HTTPException(status_code=e.response.status_code, detail=f"TTS服务返回错误: {e.response.text}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"TTS代理失败: {str(e)}")


@router.post("/tts-dubbing/start", summary="启动TTS配音任务")
async def start_tts_dubbing(
    srt_file: UploadFile = File(...),
    engine: str = Form(...),
    role: str = Form(...),
    text_lang: str = Form('zh'),  # 新增：合成语言
    speed_factor: float = Form(1.0),
    silence_duration: float = Form(0.5),
    auto_align: bool = Form(True),
    api_url: str = Form(None),
    api_key: str = Form(None),
    # 新增：智能双重变速机制参数
    enable_smart_speedup: bool = Form(False),
    enable_audio_speedup: bool = Form(True),
    enable_video_slowdown: bool = Form(False),
    max_audio_speed_rate: float = Form(2.0),
    max_video_pts_rate: float = Form(10.0),
    remove_silent_gaps: bool = Form(False),
    preserve_total_time: bool = Form(True)
):
    """
    启动TTS配音任务
    上传SRT文件，选择TTS引擎和角色，生成配音音频
    """
    try:
        print(f"\n{'='*50}")
        print(f"🎬 启动TTS配音任务")
        print(f"引擎: {engine}")
        print(f"合成语言: {text_lang}")  # 新增：输出语言参数
        print(f"语速: {speed_factor}")
        print(f"静音间隔: {silence_duration}")
        print(f"自动对齐: {auto_align}")
        
        # 生成任务ID
        task_id = str(uuid.uuid4())
        print(f"任务ID: {task_id}")
        
        # 保存SRT文件
        srt_content = await srt_file.read()
        srt_text = srt_content.decode('utf-8')
        print(f"SRT文件大小: {len(srt_text)} 字符")
        
        # 解析角色信息
        print(f"角色数据: {role[:100]}...")  # 只打印前100个字符
        role_data = json_module.loads(role)
        print(f"角色解析成功: {role_data.get('name', 'Unknown')}")
        
        # 创建任务目录
        output_path = Path(get_output_dir())
        task_dir = output_path / f"tts_dubbing_{task_id}"
        task_dir.mkdir(parents=True, exist_ok=True)
        
        # 保存SRT文件
        srt_path = task_dir / "subtitles.srt"
        with open(srt_path, 'w', encoding='utf-8') as f:
            f.write(srt_text)
        
        # 初始化任务状态
        tts_dubbing_tasks = get_tts_dubbing_tasks()
        tts_dubbing_tasks[task_id] = {
            "task_id": task_id,
            "status": "running",
            "progress": 0,
            "current_subtitle": None,
            "result_path": None,
            "error": None,
            "created_at": datetime.now().isoformat()
        }
        
        # 在后台线程中执行配音任务
        def run_dubbing_task():
            try:
                import sys
                sys.path.insert(0, str(get_current_dir() / "src" / "scripts"))
                from tts_dubbing_processor import TTSDubbingProcessor
                
                processor = TTSDubbingProcessor(
                    srt_path=str(srt_path),
                    output_dir=str(task_dir),
                    engine=engine,
                    role_data=role_data,
                    text_lang=text_lang,  # 新增：传递语言参数
                    speed_factor=speed_factor,
                    silence_duration=silence_duration,
                    auto_align=auto_align,
                    api_url=api_url,
                    api_key=api_key,
                    task_id=task_id,
                    task_dict=tts_dubbing_tasks,
                    # 新增：智能双重变速机制参数
                    enable_smart_speedup=enable_smart_speedup,
                    enable_audio_speedup=enable_audio_speedup,
                    enable_video_slowdown=enable_video_slowdown,
                    max_audio_speed_rate=max_audio_speed_rate,
                    max_video_pts_rate=max_video_pts_rate,
                    remove_silent_gaps=remove_silent_gaps,
                    preserve_total_time=preserve_total_time
                )
                
                result = processor.process()
                
                tts_dubbing_tasks[task_id]["status"] = "completed"
                tts_dubbing_tasks[task_id]["progress"] = 100
                tts_dubbing_tasks[task_id]["result_path"] = result['audio_path']
                tts_dubbing_tasks[task_id]["srt_path"] = result.get('srt_path', None)
                
            except Exception as e:
                print(f"❌ TTS配音任务失败: {e}")
                import traceback
                traceback.print_exc()
                tts_dubbing_tasks[task_id]["status"] = "failed"
                tts_dubbing_tasks[task_id]["error"] = str(e)
        
        # 启动后台线程
        thread = threading.Thread(target=run_dubbing_task, daemon=True)
        thread.start()
        
        print(f"✅ TTS配音任务已启动")
        print(f"{'='*50}\n")
        
        return tts_dubbing_tasks[task_id]
        
    except Exception as e:
        print(f"❌ 启动TTS配音任务失败: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"启动TTS配音任务失败: {str(e)}")


@router.get("/tts-dubbing/status/{task_id}", summary="获取TTS配音任务状态")
async def get_tts_dubbing_status(task_id: str):
    """获取TTS配音任务的当前状态"""
    tts_dubbing_tasks = get_tts_dubbing_tasks()
    if task_id not in tts_dubbing_tasks:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    return tts_dubbing_tasks[task_id]


@router.post("/tts-dubbing/multi-role", summary="多角色TTS配音（基于带说话人SRT）")
async def start_multi_role_dubbing(
    srt_file: UploadFile = File(..., description="带说话人标识的SRT文件"),
    engine: str = Form(..., description="TTS引擎"),
    roles_mapping: str = Form(..., description="角色映射JSON字符串"),
    text_lang: str = Form(default='zh'),
    speed_factor: float = Form(default=1.0),
    silence_duration: float = Form(default=0.5),
    auto_align: bool = Form(default=True),
    api_url: str = Form(default=None),
    api_key: str = Form(default=None),
    # 新增：智能双重变速机制参数
    enable_smart_speedup: bool = Form(default=False),
    enable_audio_speedup: bool = Form(default=True),
    enable_video_slowdown: bool = Form(default=False),
    max_audio_speed_rate: float = Form(default=2.0),
    max_video_pts_rate: float = Form(default=10.0),
    remove_silent_gaps: bool = Form(default=False),
    preserve_total_time: bool = Form(default=True)
):
    """
    多角色配音接口
    
    roles_mapping格式示例:
    {
        "spk00": {"name": "角色1", "refAudioPath": "...", "promptText": "...", ...},
        "spk01": {"name": "角色2", "refAudioPath": "...", "promptText": "...", ...}
    }
    """
    try:
        print(f"\n{'='*50}")
        print(f"🎬 启动多角色TTS配音任务")
        print(f"引擎: {engine}")
        print(f"合成语言: {text_lang}")
        print(f"语速: {speed_factor}")
        print(f"静音间隔: {silence_duration}")
        print(f"自动对齐: {auto_align}")
        
        # 生成任务ID
        task_id = str(uuid.uuid4())
        print(f"任务ID: {task_id}")
        
        # 保存上传的SRT文件
        srt_content = await srt_file.read()
        srt_text = srt_content.decode('utf-8')
        print(f"SRT文件大小: {len(srt_text)} 字符")
        
        # 解析角色映射
        roles_config = json_module.loads(roles_mapping)
        print(f"角色配置: {list(roles_config.keys())}")
        
        # 创建任务目录
        output_path = Path(get_output_dir())
        task_dir = output_path / f"multi_role_dubbing_{task_id}"
        task_dir.mkdir(parents=True, exist_ok=True)
        
        # 保存SRT文件
        srt_path = task_dir / "subtitles_with_speakers.srt"
        with open(srt_path, 'w', encoding='utf-8') as f:
            f.write(srt_text)
        
        # 保存角色配置
        roles_config_path = task_dir / "roles_config.json"
        with open(roles_config_path, 'w', encoding='utf-8') as f:
            json_module.dump(roles_config, f, ensure_ascii=False, indent=2)
        
        # 初始化任务状态
        tts_dubbing_tasks = get_tts_dubbing_tasks()
        tts_dubbing_tasks[task_id] = {
            "task_id": task_id,
            "status": "running",
            "progress": 0,
            "current_subtitle": None,
            "result_path": None,
            "error": None,
            "created_at": datetime.now().isoformat()
        }
        
        # 在后台线程中执行配音任务
        def run_multi_role_dubbing_task():
            try:
                import sys
                sys.path.insert(0, str(get_current_dir() / "src" / "scripts"))
                from tts_multi_role_dubbing import MultiRoleDubbingProcessor
                
                processor = MultiRoleDubbingProcessor(
                    srt_path=str(srt_path),
                    output_dir=str(task_dir),
                    engine=engine,
                    roles_config=roles_config,
                    text_lang=text_lang,
                    speed_factor=speed_factor,
                    silence_duration=silence_duration,
                    auto_align=auto_align,
                    api_url=api_url,
                    api_key=api_key,
                    task_id=task_id,
                    task_dict=tts_dubbing_tasks,
                    # 新增：智能双重变速机制参数
                    enable_smart_speedup=enable_smart_speedup,
                    enable_audio_speedup=enable_audio_speedup,
                    enable_video_slowdown=enable_video_slowdown,
                    max_audio_speed_rate=max_audio_speed_rate,
                    max_video_pts_rate=max_video_pts_rate,
                    remove_silent_gaps=remove_silent_gaps,
                    preserve_total_time=preserve_total_time
                )
                
                result = processor.process()
                
                tts_dubbing_tasks[task_id]["status"] = "completed"
                tts_dubbing_tasks[task_id]["progress"] = 100
                tts_dubbing_tasks[task_id]["result_path"] = result['audio_path']
                tts_dubbing_tasks[task_id]["srt_path"] = result.get('srt_path', None)
                
            except Exception as e:
                print(f"❌ 多角色TTS配音任务失败: {e}")
                import traceback
                traceback.print_exc()
                tts_dubbing_tasks[task_id]["status"] = "failed"
                tts_dubbing_tasks[task_id]["error"] = str(e)
        
        # 启动后台线程
        thread = threading.Thread(target=run_multi_role_dubbing_task, daemon=True)
        thread.start()
        
        print(f"✅ 多角色TTS配音任务已启动")
        print(f"{'='*50}\n")
        
        return {"task_id": task_id, "message": "多角色配音任务已启动"}
        
    except Exception as e:
        print(f"❌ 启动多角色TTS配音任务失败: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"启动多角色TTS配音任务失败: {str(e)}")