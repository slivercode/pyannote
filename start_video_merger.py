#!/usr/bin/env python3
"""
视频合并工具启动脚本
"""

import os
import sys
from pathlib import Path
from flask import Flask

# 添加项目路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "src"))

from src.api.video_merger_api import VideoMergerAPI


def create_app():
    """创建Flask应用"""
    app = Flask(__name__, 
                template_folder=str(project_root / "templates"),
                static_folder=str(project_root / "static"))
    
    # 配置
    app.config['MAX_CONTENT_LENGTH'] = 1024 * 1024 * 1024  # 1GB限制
    app.config['SECRET_KEY'] = 'video_merger_secret_key'
    
    # 创建必要的目录
    upload_dir = project_root / "uploads"
    output_dir = project_root / "output"
    upload_dir.mkdir(exist_ok=True)
    output_dir.mkdir(exist_ok=True)
    
    # 初始化视频合并API
    api = VideoMergerAPI(
        app, 
        upload_folder=str(upload_dir),
        output_folder=str(output_dir)
    )
    
    @app.route('/')
    def index():
        """首页"""
        return '''
        <!DOCTYPE html>
        <html lang="zh-CN">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>视频处理工具</title>
            <style>
                body {
                    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    min-height: 100vh;
                    margin: 0;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                }
                .container {
                    background: rgba(255, 255, 255, 0.95);
                    border-radius: 20px;
                    padding: 40px;
                    text-align: center;
                    box-shadow: 0 20px 40px rgba(0, 0, 0, 0.1);
                    max-width: 500px;
                }
                h1 {
                    color: #333;
                    margin-bottom: 20px;
                    background: linear-gradient(45deg, #667eea, #764ba2);
                    -webkit-background-clip: text;
                    -webkit-text-fill-color: transparent;
                }
                .tool-link {
                    display: inline-block;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white;
                    text-decoration: none;
                    padding: 15px 30px;
                    border-radius: 50px;
                    margin: 10px;
                    font-weight: 600;
                    transition: all 0.3s ease;
                    box-shadow: 0 10px 20px rgba(102, 126, 234, 0.3);
                }
                .tool-link:hover {
                    transform: translateY(-2px);
                    box-shadow: 0 15px 30px rgba(102, 126, 234, 0.4);
                }
                .description {
                    color: #666;
                    margin: 20px 0;
                    line-height: 1.6;
                }
            </style>
        </head>
        <body>
            <div class="container">
                <h1>🎬 视频处理工具</h1>
                <div class="description">
                    专业的视频合并和处理工具<br>
                    支持MP4视频、WAV音轨和SRT字幕的智能合并
                </div>
                <a href="/video_merger" class="tool-link">
                    🚀 进入视频合并工具
                </a>
            </div>
        </body>
        </html>
        '''
    
    return app


if __name__ == "__main__":
    print("🎬 启动视频合并工具...")
    print("="*50)
    
    app = create_app()
    
    # 检查FFmpeg
    try:
        from src.scripts.video_merger import VideoMerger
        
        ffmpeg_path = "ffmpeg"
        project_ffmpeg = Path("ffmpeg") / "ffmpeg.exe"
        if project_ffmpeg.exists():
            ffmpeg_path = str(project_ffmpeg)
        
        merger = VideoMerger(ffmpeg_path=ffmpeg_path)
        print("✅ FFmpeg检查通过")
    except Exception as e:
        print(f"⚠️ FFmpeg检查失败: {e}")
        print("   请确保FFmpeg已安装或位于 ffmpeg/ffmpeg.exe")
    
    print("\n🌐 服务信息:")
    print("   地址: http://localhost:8515")
    print("   视频合并: http://localhost:8515/video_merger")
    print("\n🔧 功能特性:")
    print("   ✅ 替换/混合音轨")
    print("   ✅ 嵌入/烧录字幕")
    print("   ✅ 去除原音轨")
    print("   ✅ 提取纯视频")
    print("\n按 Ctrl+C 停止服务")
    print("="*50)
    
    try:
        app.run(
            debug=False,
            host='0.0.0.0',
            port=8515,
            threaded=True
        )
    except KeyboardInterrupt:
        print("\n👋 服务已停止")