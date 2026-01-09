"""
翻译路由模块
处理SRT字幕翻译相关功能
支持：阿里云通义千问、OpenAI、DeepSeek、本地Ollama
"""
import json
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from config.dependencies import get_current_dir, get_output_dir

router = APIRouter(prefix="/api/translate", tags=["翻译功能"])

# 翻译任务存储
translate_tasks: Dict[str, Dict] = {}


@router.get("/languages", summary="获取支持的语言列表")
async def get_supported_languages():
    """获取翻译支持的语言列表"""
    languages = [
        {"code": "zh", "name": "中文"},
        {"code": "en", "name": "English"},
        {"code": "ja", "name": "日本語"},
        {"code": "ko", "name": "한국어"},
        {"code": "fr", "name": "Français"},
        {"code": "de", "name": "Deutsch"},
        {"code": "es", "name": "Español"},
        {"code": "ru", "name": "Русский"},
        {"code": "pt", "name": "Português"},
        {"code": "it", "name": "Italiano"},
        {"code": "ar", "name": "العربية"},
        {"code": "th", "name": "ไทย"},
        {"code": "vi", "name": "Tiếng Việt"}
    ]
    return {"languages": languages}


@router.get("/models", summary="获取支持的模型列表")
async def get_supported_models():
    """获取翻译支持的模型列表"""
    models = [
        # 阿里云
        {"id": "qwen-plus", "name": "通义千问Plus", "provider": "阿里云", "api_url": "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"},
        {"id": "qwen-turbo", "name": "通义千问Turbo", "provider": "阿里云", "api_url": "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"},
        {"id": "qwen-max", "name": "通义千问Max", "provider": "阿里云", "api_url": "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"},
        # OpenAI
        {"id": "gpt-3.5-turbo", "name": "GPT-3.5 Turbo", "provider": "OpenAI", "api_url": "https://api.openai.com/v1/chat/completions"},
        {"id": "gpt-4", "name": "GPT-4", "provider": "OpenAI", "api_url": "https://api.openai.com/v1/chat/completions"},
        {"id": "gpt-4o", "name": "GPT-4o", "provider": "OpenAI", "api_url": "https://api.openai.com/v1/chat/completions"},
        # DeepSeek
        {"id": "deepseek-chat", "name": "DeepSeek Chat", "provider": "DeepSeek", "api_url": "https://api.deepseek.com/v1/chat/completions"},
        # Ollama 本地模型
        {"id": "ollama:qwen2.5", "name": "Qwen2.5", "provider": "Ollama", "api_url": "http://192.168.110.204:11435/api/chat", "is_ollama": True},
        {"id": "ollama:llama3", "name": "Llama3", "provider": "Ollama", "api_url": "http://192.168.110.204:11435/api/chat", "is_ollama": True},
        {"id": "ollama:gemma2", "name": "Gemma2", "provider": "Ollama", "api_url": "http://192.168.110.204:11435/api/chat", "is_ollama": True},
        {"id": "ollama:mistral", "name": "Mistral", "provider": "Ollama", "api_url": "http://192.168.110.204:11435/api/chat", "is_ollama": True},
        {"id": "ollama:deepseek-r1", "name": "DeepSeek-R1", "provider": "Ollama", "api_url": "http://192.168.110.204:11435/api/chat", "is_ollama": True},
        {"id": "ollama:custom", "name": "自定义Ollama模型", "provider": "Ollama", "api_url": "http://192.168.110.204:11435/api/chat", "is_ollama": True},
    ]
    return {"models": models}


@router.get("/ollama/models", summary="获取Ollama已安装的模型")
async def get_ollama_models(host: str = "192.168.110.204", port: int = 11435):
    """获取Ollama已安装的模型列表"""
    import requests
    try:
        url = f"http://{host}:{port}/api/tags"
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            models = [{"name": m["name"], "size": m.get("size", 0)} for m in data.get("models", [])]
            return {"success": True, "models": models, "host": host, "port": port}
        else:
            return {"success": False, "error": "Ollama服务返回错误", "models": []}
    except requests.exceptions.ConnectionError:
        return {"success": False, "error": f"无法连接到Ollama服务 {host}:{port}，请确保Ollama已启动", "models": []}
    except Exception as e:
        return {"success": False, "error": str(e), "models": []}


@router.post("/start", summary="启动SRT翻译任务")
async def start_translate_task(
    srt_file: UploadFile = File(None, description="SRT字幕文件"),
    srt_path: str = Form(default="", description="SRT文件绝对路径（可选，与上传二选一）"),
    target_lang: str = Form(..., description="目标语言代码"),
    api_key: str = Form(default="", description="API密钥（Ollama可留空）"),
    api_url: str = Form(
        default="https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
        description="API地址"
    ),
    model: str = Form(default="qwen-plus", description="模型名称"),
    batch_size: int = Form(default=10, description="批量翻译大小"),
    is_ollama: bool = Form(default=False, description="是否使用Ollama")
):
    """
    启动SRT字幕翻译任务
    支持两种方式：
    1. 上传SRT文件
    2. 提供SRT文件的绝对路径
    """
    try:
        print(f"\n{'='*50}")
        print(f"🌐 启动SRT翻译任务")
        print(f"目标语言: {target_lang}")
        print(f"模型: {model}")
        print(f"API地址: {api_url}")
        print(f"是否Ollama: {is_ollama}")
        print(f"批量大小: {batch_size}")
        print(f"SRT路径: {srt_path}")
        
        # 处理Ollama模型名称
        actual_model = model
        if model.startswith("ollama:"):
            actual_model = model.replace("ollama:", "")
            is_ollama = True
            if api_url == "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions":
                api_url = "http://192.168.110.204:11435/api/chat"
        
        print(f"实际模型名: {actual_model}")
        
        # 生成任务ID
        task_id = str(uuid.uuid4())
        print(f"任务ID: {task_id}")
        
        # 创建任务目录
        output_path = Path(get_output_dir())
        task_dir = output_path / f"translate_{task_id}"
        task_dir.mkdir(parents=True, exist_ok=True)
        
        input_srt_path = None
        original_filename = "subtitles.srt"
        
        # 方式1：使用绝对路径
        if srt_path and srt_path.strip():
            srt_path = srt_path.strip()
            if not Path(srt_path).exists():
                raise HTTPException(status_code=400, detail=f"文件不存在: {srt_path}")
            input_srt_path = Path(srt_path)
            original_filename = input_srt_path.name
            print(f"使用绝对路径: {srt_path}")
        
        # 方式2：上传文件
        elif srt_file and srt_file.filename:
            srt_bytes = await srt_file.read()
            
            print(f"上传文件大小: {len(srt_bytes)} 字节")
            print(f"原始字节前50: {srt_bytes[:50]}")
            
            original_filename = srt_file.filename or "subtitles.srt"
            
            # 直接以二进制方式保存原始文件（保留原始换行符）
            input_srt_path = task_dir / f"original_{original_filename}"
            with open(input_srt_path, 'wb') as f:
                f.write(srt_bytes)
            print(f"文件已保存到: {input_srt_path}")
            
            # 验证保存的文件
            with open(input_srt_path, 'rb') as f:
                saved_bytes = f.read()
            print(f"验证保存的文件大小: {len(saved_bytes)} 字节")
            print(f"保存后字节前50: {saved_bytes[:50]}")
            
            # 尝试解码验证
            srt_text = None
            for encoding in ['utf-8', 'utf-8-sig', 'gbk', 'gb2312', 'latin-1', 'cp1252']:
                try:
                    srt_text = srt_bytes.decode(encoding)
                    print(f"使用编码 {encoding} 解码成功, 字符数: {len(srt_text)}")
                    break
                except (UnicodeDecodeError, UnicodeError):
                    continue
            
            if srt_text:
                print(f"文件前100字符: {repr(srt_text[:100])}")
        else:
            raise HTTPException(status_code=400, detail="请上传SRT文件或提供文件路径")
        
        # 生成输出文件名
        stem = Path(original_filename).stem
        output_filename = f"{stem}_{target_lang}.srt"
        output_srt_path = task_dir / output_filename
        
        # 初始化任务状态
        translate_tasks[task_id] = {
            "task_id": task_id,
            "status": "running",
            "progress": 0,
            "total": 0,
            "current_message": "正在初始化...",
            "result_path": None,
            "result_filename": output_filename,
            "error": None,
            "created_at": datetime.now().isoformat()
        }
        
        # 保存路径供后台线程使用
        input_path_str = str(input_srt_path)
        output_path_str = str(output_srt_path)
        
        # 在后台线程中执行翻译任务
        def run_translate_task():
            try:
                import sys
                import importlib
                
                scripts_path = str(get_current_dir() / "src" / "scripts")
                if scripts_path not in sys.path:
                    sys.path.insert(0, scripts_path)
                
                # 强制重新加载模块
                import srt_translator
                importlib.reload(srt_translator)
                from srt_translator import SRTTranslator
                
                print(f"[后台任务] 输入文件: {input_path_str}")
                print(f"[后台任务] 输出文件: {output_path_str}")
                
                # 验证输入文件存在
                if not Path(input_path_str).exists():
                    raise FileNotFoundError(f"输入文件不存在: {input_path_str}")
                
                # 读取并打印文件内容用于调试
                with open(input_path_str, 'r', encoding='utf-8') as f:
                    content = f.read()
                print(f"[后台任务] 文件内容长度: {len(content)}")
                print(f"[后台任务] 文件前200字符:\n{content[:200]}")
                
                def progress_callback(current, total, message):
                    translate_tasks[task_id]["progress"] = int(current / total * 100) if total > 0 else 0
                    translate_tasks[task_id]["total"] = total
                    translate_tasks[task_id]["current_message"] = message
                    print(f"📊 翻译进度: {current}/{total} - {message}")
                
                translator = SRTTranslator(
                    api_key=api_key,
                    api_url=api_url,
                    model=actual_model,
                    target_lang=target_lang,
                    batch_size=batch_size,
                    is_ollama=is_ollama
                )
                
                result_path = translator.translate_file(
                    input_path_str,
                    output_path_str,
                    progress_callback=progress_callback
                )
                
                translate_tasks[task_id]["status"] = "completed"
                translate_tasks[task_id]["progress"] = 100
                translate_tasks[task_id]["result_path"] = str(result_path)
                translate_tasks[task_id]["current_message"] = "翻译完成"
                print(f"✅ 翻译任务完成: {result_path}")
                
            except Exception as e:
                print(f"❌ 翻译任务失败: {e}")
                import traceback
                traceback.print_exc()
                translate_tasks[task_id]["status"] = "failed"
                translate_tasks[task_id]["error"] = str(e)
                translate_tasks[task_id]["current_message"] = f"翻译失败: {str(e)}"
        
        # 启动后台线程
        thread = threading.Thread(target=run_translate_task, daemon=True)
        thread.start()
        
        print(f"✅ 翻译任务已启动")
        print(f"{'='*50}\n")
        
        return {
            "task_id": task_id,
            "message": "翻译任务已启动",
            "output_filename": output_filename
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ 启动翻译任务失败: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"启动翻译任务失败: {str(e)}")


@router.get("/status/{task_id}", summary="获取翻译任务状态")
async def get_translate_status(task_id: str):
    """获取翻译任务的当前状态"""
    if task_id not in translate_tasks:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    return translate_tasks[task_id]


@router.get("/download/{task_id}", summary="下载翻译结果")
async def download_translate_result(task_id: str):
    """下载翻译完成的SRT文件"""
    if task_id not in translate_tasks:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    task = translate_tasks[task_id]
    
    if task["status"] != "completed":
        raise HTTPException(status_code=400, detail="任务尚未完成")
    
    result_path = task.get("result_path")
    if not result_path or not Path(result_path).exists():
        raise HTTPException(status_code=404, detail="结果文件不存在")
    
    return FileResponse(
        path=result_path,
        filename=task.get("result_filename", "translated.srt"),
        media_type="application/x-subrip"
    )
