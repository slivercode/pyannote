"""
配置管理路由模块
处理TTS配置和其他系统配置
"""
import json
from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api", tags=["配置管理"])

from config.dependencies import get_current_dir

router = APIRouter(prefix="/api", tags=["配置管理"])


@router.get("/tts-config", summary="获取TTS配置")
async def get_tts_config():
    """获取当前TTS配置"""
    current_dir = get_current_dir()
    config_path = current_dir / "tts_config.json"
    example_config_path = current_dir / "tts_config.example.json"
    
    if not config_path.exists():
        # 如果示例配置存在，从示例配置复制
        if example_config_path.exists():
            try:
                print(f"📋 首次启动，从示例配置加载: {example_config_path}")
                with open(example_config_path, "r", encoding="utf-8") as f:
                    example_config = json.load(f)
                
                # 保存为实际配置文件
                with open(config_path, "w", encoding="utf-8") as f:
                    json.dump(example_config, f, ensure_ascii=False, indent=2)
                
                print(f"✅ 已创建配置文件: {config_path}")
                return example_config
            except Exception as e:
                print(f"⚠️ 加载示例配置失败: {e}")
        
        # 返回默认空配置
        print(f"⚠️ 使用默认空配置")
        return {
            "gptSovits": {
                "enabled": False,
                "apiUrl": "http://127.0.0.1:9880",
                "roles": []
            },
            "qwenTts": {
                "enabled": False,
                "apiKey": "",
                "roles": []
            }
        }
    
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"读取配置失败：{str(e)}")


@router.post("/tts-config/save", summary="保存TTS配置")
async def save_tts_config(config: dict):
    """保存TTS配置到文件"""
    current_dir = get_current_dir()
    config_path = current_dir / "tts_config.json"
    
    try:
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        return {"status": "success", "message": "配置保存成功"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"保存配置失败：{str(e)}")