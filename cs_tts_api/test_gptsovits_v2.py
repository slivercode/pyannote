import requests

url = "http://192.168.110.204:9880/tts"  # 确保没有尾部空格

# ========== 重要：修改这里的参考音频路径 ==========
# 方案1: 使用服务器上实际存在的音频文件绝对路径（推荐）
# 例如: "D:/audio/reference.wav" (Windows) 或 "/home/user/audio/reference.wav" (Linux)
REF_AUDIO_PATH = "D:\AI_video\pyannote-audio-web-ui\pyannote-audio-web-ui\cs_tts_api\cs3.mp3"  # 修改为你服务器上实际的音频文件路径

# 方案2: 如果不确定服务器路径，可以先上传音频文件到服务器
# 然后使用服务器返回的路径

# 必须包含所有字段，且 prompt_text 不能空
data = {
    "text": "你好，这是测试文本",  # 要合成的文本
    "text_lang": "zh",  # 合成文本的语言

    "prompt_text": "何でだよ 私たちは治療を受けに来たんだよ そうだよ ここはお前の家じゃないだろ",  # 参考音频对应的文本
    "prompt_lang": "ja",  # 参考音频语言（这里是日文，根据prompt_text内容判断）

    "ref_audio_path": "/home/fuxin/cs3.mp3",  # 服务器上的绝对路径

    # 以下字段建议显式指定
    "cut_punc": "，。！？",  # 断句标点
    "top_k": 15,  # 采样参数
    "top_p": 0.85,
    "temperature": 1.0,
    "use_gpt": True,  # V4 可以设为 True 试试
}
print("=" * 60)
print("GPT-SoVITS V2 模式测试")
print("=" * 60)
print(f"API地址: {url}")
print(f"参考音频: {data['ref_audio_path']}")
print(f"参考文本: {data['prompt_text']}")
print(f"参考语言: {data['prompt_lang']}")
print(f"合成文本: {data['text']}")
print(f"合成语言: {data['text_lang']}")
print("-" * 60)

try:
    # 使用 GET 请求，参数通过 params 传递
    print("正在发送请求...")
    response = requests.get(url, params=data, timeout=30)
    
    print(f"\n状态码: {response.status_code}")
    print(f"完整URL: {response.url}")
    
    if response.status_code == 200:
        # 检查返回的内容类型
        content_type = response.headers.get('Content-Type', '')
        print(f"返回类型: {content_type}")
        
        if 'audio' in content_type:
            # 成功：保存音频文件
            output_file = "output_tts_v2.wav"
            with open(output_file, "wb") as f:
                f.write(response.content)
            print(f"\n✅ TTS合成成功！")
            print(f"音频已保存到: {output_file}")
            print(f"文件大小: {len(response.content)} 字节")
        elif 'json' in content_type:
            # 返回的是JSON错误信息
            error_data = response.json()
            print(f"\n❌ API返回错误:")
            print(f"错误信息: {error_data}")
        else:
            print(f"\n⚠️ 未知的返回类型: {content_type}")
            print(f"返回内容前100字符: {response.text[:100]}")
    else:
        # 失败：打印错误信息
        print(f"\n❌ TTS合成失败 (HTTP {response.status_code})")
        print(f"返回内容: {response.text}")
        
except requests.exceptions.Timeout:
    print("\n❌ 请求超时")
    print("建议检查:")
    print("  1. GPT-SoVITS 服务是否正常运行")
    print("  2. 网络连接是否正常")
    
except requests.exceptions.ConnectionError as e:
    print("\n❌ 连接失败")
    print(f"错误详情: {str(e)}")
    print("建议检查:")
    print("  1. 服务器地址是否正确: 192.168.110.204:9880")
    print("  2. GPT-SoVITS 服务是否已启动")
    print("  3. 防火墙是否阻止了连接")
    
except Exception as e:
    print(f"\n❌ 发生未知错误")
    print(f"错误类型: {type(e).__name__}")
    print(f"错误详情: {str(e)}")

print("\n" + "=" * 60)
print("测试完成")
print("=" * 60)
