#!/usr/bin/env python3
"""
最终日语TTS测试
"""

def test_final_japanese():
    """最终日语TTS测试"""
    try:
        import dashscope
        from dashscope.audio.tts import SpeechSynthesizer
        print("✅ dashscope库已安装")
    except ImportError as e:
        print(f"❌ dashscope库未安装: {e}")
        return False
    
    # 设置API密钥
    api_key = "sk-67f587a8e4564f6ea15c57e78a2a1652"
    dashscope.api_key = api_key
    
    # 测试文本
    test_cases = [
        {
            'text': '你好，这是中文测试。',
            'model': 'sambert-zhichu-v1',
            'lang': '中文'
        },
        {
            'text': 'こんにちは、これは日本語のテストです。何でだよ、私たちは治療を受けに来たんだよ。',
            'model': 'sambert-zhiying-v1', 
            'lang': '日语'
        },
        {
            'text': 'Hello, this is an English test.',
            'model': 'sambert-zhiying-v1',
            'lang': '英语'
        }
    ]
    
    for i, case in enumerate(test_cases):
        print(f"\n🔄 测试 {case['lang']} - 模型: {case['model']}")
        print(f"   文本: {case['text']}")
        
        try:
            # 调用API
            response = SpeechSynthesizer.call(
                model=case['model'],
                text=case['text'],
                sample_rate=48000
            )
            
            # 检查响应
            resp_dict = response.get_response()
            
            if resp_dict.get('status_code') == 200:
                # 获取音频数据
                audio_data = response.get_audio_data()
                
                if audio_data:
                    # 保存测试音频
                    output_file = f"test_final_{case['lang']}_{i+1}.wav"
                    with open(output_file, 'wb') as f:
                        f.write(audio_data)
                    
                    print(f"✅ {case['lang']} 测试成功！")
                    print(f"   音频文件: {output_file}")
                    print(f"   音频大小: {len(audio_data)} bytes")
                else:
                    print(f"❌ {case['lang']} 音频数据为空")
            else:
                print(f"❌ {case['lang']} 调用失败: {resp_dict}")
                
        except Exception as e:
            print(f"❌ {case['lang']} 测试异常: {e}")
    
    return True

if __name__ == "__main__":
    print("🧪 开始最终多语言TTS测试...")
    test_final_japanese()
    print("\n🏁 测试完成")