"""
视频合并API
提供视频合并功能的Web API接口
"""

import os
import time
import uuid
from pathlib import Path
from flask import Flask, request, jsonify, send_file, render_template
from werkzeug.utils import secure_filename
import sys

# 添加scripts目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from video_merger import VideoMerger


class VideoMergerAPI:
    """视频合并API类"""
    
    def __init__(self, app: Flask, upload_folder: str = "uploads", output_folder: str = "output"):
        """
        初始化API
        
        Args:
            app: Flask应用实例
            upload_folder: 上传文件夹
            output_folder: 输出文件夹
        """
        self.app = app
        self.upload_folder = Path(upload_folder)
        self.output_folder = Path(output_folder)
        
        # 创建必要的目录
        self.upload_folder.mkdir(exist_ok=True)
        self.output_folder.mkdir(exist_ok=True)
        
        # 初始化视频合并器
        try:
            # 尝试使用项目中的FFmpeg
            ffmpeg_path = "ffmpeg"
            project_ffmpeg = Path("ffmpeg") / "ffmpeg.exe"
            if project_ffmpeg.exists():
                ffmpeg_path = str(project_ffmpeg)
            
            self.merger = VideoMerger(ffmpeg_path=ffmpeg_path)
        except Exception as e:
            print(f"⚠️ VideoMerger初始化失败: {e}")
            self.merger = None
        
        # 注册路由
        self._register_routes()
    
    def _register_routes(self):
        """注册API路由"""
        
        @self.app.route('/video_merger')
        def video_merger_page():
            """视频合并页面"""
            return render_template('video_merger.html')
        
        @self.app.route('/api/merge_video', methods=['POST'])
        def merge_video():
            """合并视频API"""
            return self._merge_video()
        
        @self.app.route('/api/video_info', methods=['POST'])
        def get_video_info():
            """获取视频信息API"""
            return self._get_video_info()
        
        @self.app.route('/download/<filename>')
        def download_file(filename):
            """下载文件"""
            return self._download_file(filename)
    
    def _merge_video(self):
        """处理视频合并请求"""
        try:
            if not self.merger:
                return jsonify({
                    'success': False,
                    'error': 'VideoMerger未初始化，请检查FFmpeg安装'
                }), 500
            
            # 检查请求中的文件
            if 'video' not in request.files:
                return jsonify({
                    'success': False,
                    'error': '缺少视频文件'
                }), 400
            
            video_file = request.files['video']
            audio_file = request.files.get('audio')
            subtitle_file = request.files.get('subtitle')
            
            if video_file.filename == '':
                return jsonify({
                    'success': False,
                    'error': '未选择视频文件'
                }), 400
            
            # 获取参数
            mode = request.form.get('mode', 'replace_audio')
            remove_original_audio = request.form.get('remove_original_audio', 'true').lower() == 'true'
            
            # 生成唯一的任务ID
            task_id = str(uuid.uuid4())
            
            # 保存上传的文件
            video_path = self._save_uploaded_file(video_file, task_id, 'video')
            audio_path = None
            subtitle_path = None
            
            if audio_file and audio_file.filename:
                audio_path = self._save_uploaded_file(audio_file, task_id, 'audio')
            
            if subtitle_file and subtitle_file.filename:
                subtitle_path = self._save_uploaded_file(subtitle_file, task_id, 'subtitle')
            
            # 生成输出文件路径
            output_filename = f"{task_id}_merged.mp4"
            output_path = self.output_folder / output_filename
            
            # 记录开始时间
            start_time = time.time()
            
            # 执行合并
            try:
                result_path = self.merger.merge_video_audio_subtitle(
                    video_path=str(video_path),
                    audio_path=str(audio_path) if audio_path else None,
                    subtitle_path=str(subtitle_path) if subtitle_path else None,
                    output_path=str(output_path),
                    mode=mode,
                    remove_original_audio=remove_original_audio
                )
                
                # 计算处理时间
                processing_time = time.time() - start_time
                
                return jsonify({
                    'success': True,
                    'output_path': str(result_path),
                    'filename': output_filename,
                    'processing_time': f"{processing_time:.2f}秒",
                    'task_id': task_id
                })
                
            except Exception as e:
                return jsonify({
                    'success': False,
                    'error': f'合并失败: {str(e)}'
                }), 500
            
            finally:
                # 清理临时文件
                self._cleanup_temp_files(task_id)
        
        except Exception as e:
            return jsonify({
                'success': False,
                'error': f'处理请求失败: {str(e)}'
            }), 500
    
    def _get_video_info(self):
        """获取视频信息"""
        try:
            if not self.merger:
                return jsonify({
                    'success': False,
                    'error': 'VideoMerger未初始化'
                }), 500
            
            if 'video' not in request.files:
                return jsonify({
                    'success': False,
                    'error': '缺少视频文件'
                }), 400
            
            video_file = request.files['video']
            if video_file.filename == '':
                return jsonify({
                    'success': False,
                    'error': '未选择视频文件'
                }), 400
            
            # 保存临时文件
            task_id = str(uuid.uuid4())
            video_path = self._save_uploaded_file(video_file, task_id, 'video')
            
            try:
                # 获取视频信息
                info = self.merger.get_video_info(str(video_path))
                
                return jsonify({
                    'success': True,
                    'info': info
                })
            
            finally:
                # 清理临时文件
                try:
                    os.unlink(video_path)
                except:
                    pass
        
        except Exception as e:
            return jsonify({
                'success': False,
                'error': f'获取视频信息失败: {str(e)}'
            }), 500
    
    def _download_file(self, filename):
        """下载文件"""
        try:
            file_path = self.output_folder / filename
            if not file_path.exists():
                return jsonify({
                    'success': False,
                    'error': '文件不存在'
                }), 404
            
            return send_file(
                str(file_path),
                as_attachment=True,
                download_name=filename
            )
        
        except Exception as e:
            return jsonify({
                'success': False,
                'error': f'下载失败: {str(e)}'
            }), 500
    
    def _save_uploaded_file(self, file, task_id: str, file_type: str) -> Path:
        """
        保存上传的文件
        
        Args:
            file: 上传的文件对象
            task_id: 任务ID
            file_type: 文件类型 (video, audio, subtitle)
        
        Returns:
            保存的文件路径
        """
        # 获取安全的文件名
        filename = secure_filename(file.filename)
        
        # 生成唯一的文件名
        name, ext = os.path.splitext(filename)
        unique_filename = f"{task_id}_{file_type}_{name}{ext}"
        
        # 保存文件
        file_path = self.upload_folder / unique_filename
        file.save(str(file_path))
        
        return file_path
    
    def _cleanup_temp_files(self, task_id: str):
        """清理临时文件"""
        try:
            # 删除上传的临时文件
            for file_path in self.upload_folder.glob(f"{task_id}_*"):
                try:
                    os.unlink(file_path)
                except:
                    pass
        except:
            pass


# 使用示例
if __name__ == "__main__":
    from flask import Flask
    
    app = Flask(__name__)
    app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500MB限制
    
    # 初始化API
    api = VideoMergerAPI(app)
    
    @app.route('/')
    def index():
        return '''
        <h1>视频合并工具</h1>
        <p><a href="/video_merger">进入视频合并页面</a></p>
        '''
    
    app.run(debug=True, host='0.0.0.0', port=8515)