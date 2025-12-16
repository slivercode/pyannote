import requests

url = "http://192.168.110.204:9880/tts"  # GPT-SoVITS API地址

# ========== 重要：参考音频路径配置 ==========
# 根据 pyvideotrans 项目的实现，GPT-SoVITS 的参考音频有两种配置方式：
# 
# 方案1：只填写文件名（推荐）- 文件必须在 GPT-SoVITS 服务器的项目根目录
# 例如：如果 GPT-SoVITS 安装在 /home/fuxin/GPT-SoVITS/
#      那么 cs3.mp3 应该放在 /home/fuxin/GPT-SoVITS/cs3.mp3
REF_AUDIO_PATH = "cs3.mp3"  # 只写文件名，GPT-SoVITS 会在根目录查找

# 方案2：填写完整的服务器路径（如果方案1不工作）
# REF_AUDIO_PATH = "/home/fuxin/GPT-SoVITS/cs3.mp3"

# 必须包含所有字段，且 prompt_text 不能空
data = {
    "text": "你好，这是测试文本",  # 要合成的文本
    "text_lang": "zh",  # 合成文本的语言

    "prompt_text": "何でだよ 私たちは治療を受けに来たんだよ そうだよ ここはお前の家じゃないだろ",  # 参考音频对应的文本
    "prompt_lang": "ja",  # 参考音频语言（这里是日文，根据prompt_text内容判断）

    "ref_audio_path": REF_AUDIO_PATH,  # 参考音频路径

    # 以下字段建议显式指定
    "cut_punc": "，。！？",  # 断句标点
    "top_k": 15,  # 采样参数
    "top_p": 0.85,
    "temperature": 1.0,
    "use_gpt": True,  # V4 可以设为 True 试试
}

print(f"正在请求TTS服务: {url}")
print(f"参考音频路径: {REF_AUDIO_PATH}")
print("-" * 50)

try:
    # 重要：GPT-SoVITS 使用 GET 请求，不是 POST！
    # 参数通过 params 传递，不是 json
    response = requests.get(url, params=data, timeout=30)
    print(f"状态码: {response.status_code}")
    print(f"请求URL: {response.url}")
    
    if response.status_code == 200:
        # 检查返回的内容类型
        content_type = response.headers.get('Content-Type', '')
        print(f"返回类型: {content_type}")
        
        if 'audio' in content_type:
            # 成功：保存音频文件
            output_file = "output_tts.wav"
            with open(output_file, "wb") as f:
                f.write(response.content)
            print(f"✅ TTS合成成功！音频已保存到: {output_file}")
        elif 'json' in content_type:
            # 返回的是JSON错误信息
            print(f"❌ API返回错误: {response.json()}")
        else:
            print(f"❌ 未知的返回类型: {content_type}")
    else:
        # 失败：打印错误信息
        print(f"❌ TTS合成失败")
        print(f"返回内容: {response.text}")
        
except requests.exceptions.Timeout:
    print("❌ 请求超时，请检查服务器是否正常运行")
except requests.exceptions.ConnectionError:
    print("❌ 连接失败，请检查服务器地址和端口")
except Exception as e:
    print(f"❌ 发生错误: {str(e)}")