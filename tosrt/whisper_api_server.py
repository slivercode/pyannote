"""
Whisper API 服务器示例
用于部署 Whisper 模型并提供 HTTP API 接口
"""

from flask import Flask, request, jsonify
import whisper
import os
import tempfile
from werkzeug.utils import secure_filename

app = Flask(__name__)

# 配置
ALLOWED_EXTENSIONS = {'mp3', 'wav', 'm4a', 'flac', 'ogg', 'mp4', 'avi', 'mkv'}
MAX_CONTENT_LENGTH = 500 * 1024 * 1024  # 500MB

# 预加载模型（可选，提高响应速度）
# 如果内存充足，可以预加载常用模型
PRELOADED_MODELS = {}

def allowed_file(filename):
    """检查文件扩展名是否允许"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_model(model_size):
    """获取或加载模型"""
    if model_size not in PRELOADED_MODELS:
        print(f"加载模型: {model_size}")
        PRELOADED_MODELS[model_size] = whisper.load_model(model_size)
    return PRELOADED_MODELS[model_size]

@app.route('/transcribe', methods=['POST'])
def transcribe():
    """
    转录音频文件的 API 端点
    
    参数:
        file: 音频文件（multipart/form-data）
        model: 模型大小 (tiny, base, small, medium, large)，默认 base
        language: 语言代码，默认 zh
        task: transcribe 或 translate，默认 transcribe
    
    返回:
        JSON 格式的转录结果
    """
    
    # 检查是否有文件
    if 'file' not in request.files:
        return jsonify({'error': '没有上传文件'}), 400
    
    file = request.files['file']
    
    if file.filename == '':
        return jsonify({'error': '文件名为空'}), 400
    
    if not allowed_file(file.filename):
        return jsonify({'error': '不支持的文件格式'}), 400
    
    # 获取参数
    model_size = request.form.get('model', 'base')
    language = request.form.get('language', 'zh')
    task = request.form.get('task', 'transcribe')
    
    # 验证模型大小
    valid_models = ['tiny', 'base', 'small', 'medium', 'large', 'large-v2', 'large-v3']
    if model_size not in valid_models:
        return jsonify({'error': f'无效的模型大小: {model_size}'}), 400
    
    try:
        # 保存临时文件
        temp_dir = tempfile.gettempdir()
        filename = secure_filename(file.filename)
        temp_path = os.path.join(temp_dir, filename)
        file.save(temp_path)
        
        print(f"开始转录: {filename}")
        print(f"  模型: {model_size}, 语言: {language}, 任务: {task}")
        
        # 加载模型并转录
        model = get_model(model_size)
        result = model.transcribe(
            temp_path,
            language=language,
            task=task,
            verbose=False
        )
        
        # 清理临时文件
        os.remove(temp_path)
        
        print(f"转录完成: {filename}")
        
        # 返回结果
        return jsonify({
            'text': result['text'],
            'language': result['language'],
            'segments': [
                {
                    'id': seg['id'],
                    'start': seg['start'],
                    'end': seg['end'],
                    'text': seg['text'].strip()
                }
                for seg in result['segments']
            ]
        })
        
    except Exception as e:
        # 清理临时文件（如果存在）
        if os.path.exists(temp_path):
            os.remove(temp_path)
        
        print(f"错误: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/health', methods=['GET'])
def health():
    """健康检查端点"""
    return jsonify({
        'status': 'ok',
        'loaded_models': list(PRELOADED_MODELS.keys())
    })

@app.route('/models', methods=['GET'])
def models():
    """列出可用的模型"""
    return jsonify({
        'available_models': ['tiny', 'base', 'small', 'medium', 'large', 'large-v2', 'large-v3'],
        'loaded_models': list(PRELOADED_MODELS.keys())
    })

if __name__ == '__main__':
    # 可选：预加载常用模型
    # print("预加载模型...")
    # get_model('base')
    
    print("🚀 启动 Whisper API 服务器")
    print("="*60)
    print("API 端点:")
    print("  POST /transcribe - 转录音频")
    print("  GET  /health    - 健康检查")
    print("  GET  /models    - 列出模型")
    print("="*60)
    
    # 启动服务器
    # 生产环境建议使用 gunicorn 或 uwsgi
    app.run(
        host='0.0.0.0',  # 允许外部访问
        port=5000,
        debug=False,
        threaded=True
    )
