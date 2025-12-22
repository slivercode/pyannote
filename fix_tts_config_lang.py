"""
TTS配置语言修复脚本
自动检测并修复tts_config.json中的promptLang设置
"""

import json
import re
from pathlib import Path


def detect_language(text):
    """检测文本语言"""
    if not text:
        return None
    
    # 检测日语字符（平假名、片假名）
    if re.search(r'[\u3040-\u309F\u30A0-\u30FF]', text):
        return 'ja'
    
    # 检测韩语字符
    if re.search(r'[\uAC00-\uD7AF]', text):
        return 'ko'
    
    # 检测中文字符
    if re.search(r'[\u4E00-\u9FFF]', text):
        return 'zh'
    
    # 检测英文
    if re.match(r'^[a-zA-Z\s\.,!?;:\'\"()-]+$', text.strip()):
        return 'en'
    
    return None


def fix_tts_config():
    """修复TTS配置文件"""
    config_path = Path('tts_config.json')
    
    if not config_path.exists():
        print(f"❌ 配置文件不存在: {config_path}")
        return
    
    print("=" * 60)
    print("TTS配置语言修复工具")
    print("=" * 60)
    
    # 读取配置
    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)
    
    # 备份原配置
    backup_path = config_path.with_suffix('.json.backup')
    with open(backup_path, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
    print(f"✅ 已备份原配置到: {backup_path}")
    
    # 检查并修复GPT-SoVITS配置
    if 'gptSovits' in config and 'roles' in config['gptSovits']:
        print(f"\n检查GPT-SoVITS配置...")
        roles = config['gptSovits']['roles']
        fixed_count = 0
        
        for i, role in enumerate(roles):
            role_name = role.get('name', f'角色{i+1}')
            prompt_text = role.get('promptText', '')
            current_lang = role.get('promptLang', None)
            
            # 检测参考文本的语言
            detected_lang = detect_language(prompt_text)
            
            print(f"\n角色: {role_name}")
            print(f"  参考文本: {prompt_text[:50]}...")
            print(f"  当前promptLang: {current_lang}")
            print(f"  检测到的语言: {detected_lang}")
            
            # 如果没有设置promptLang，或者设置错误
            if not current_lang:
                if detected_lang:
                    role['promptLang'] = detected_lang
                    print(f"  ✅ 已设置promptLang为: {detected_lang}")
                    fixed_count += 1
                else:
                    print(f"  ⚠️ 无法检测语言，请手动设置")
            elif current_lang != detected_lang and detected_lang:
                print(f"  ⚠️ 语言不匹配！")
                print(f"     当前设置: {current_lang}")
                print(f"     检测结果: {detected_lang}")
                
                # 询问是否修复
                response = input(f"     是否修改为 {detected_lang}? (y/n): ")
                if response.lower() == 'y':
                    role['promptLang'] = detected_lang
                    print(f"  ✅ 已修改promptLang为: {detected_lang}")
                    fixed_count += 1
            else:
                print(f"  ✅ promptLang设置正确")
        
        print(f"\n共修复 {fixed_count} 个角色配置")
    
    # 保存修复后的配置
    with open(config_path, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
    
    print(f"\n✅ 配置已保存到: {config_path}")
    print(f"✅ 原配置备份到: {backup_path}")
    
    print("\n" + "=" * 60)
    print("修复完成！")
    print("=" * 60)
    print("\n建议：")
    print("1. 重启TTS服务")
    print("2. 在TTS模型管理界面测试每个角色")
    print("3. 确认输出的是合成音色，而不是参考音频原声")


def check_config_only():
    """只检查配置，不修改"""
    config_path = Path('tts_config.json')
    
    if not config_path.exists():
        print(f"❌ 配置文件不存在: {config_path}")
        return
    
    print("=" * 60)
    print("TTS配置检查")
    print("=" * 60)
    
    # 读取配置
    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)
    
    # 检查GPT-SoVITS配置
    if 'gptSovits' in config and 'roles' in config['gptSovits']:
        roles = config['gptSovits']['roles']
        issues = []
        
        for i, role in enumerate(roles):
            role_name = role.get('name', f'角色{i+1}')
            prompt_text = role.get('promptText', '')
            current_lang = role.get('promptLang', None)
            detected_lang = detect_language(prompt_text)
            
            print(f"\n角色: {role_name}")
            print(f"  参考文本: {prompt_text[:50]}...")
            print(f"  promptLang: {current_lang}")
            print(f"  检测语言: {detected_lang}")
            
            if not current_lang:
                print(f"  ❌ 问题：未设置promptLang")
                issues.append(f"{role_name}: 未设置promptLang")
            elif current_lang != detected_lang and detected_lang:
                print(f"  ⚠️ 警告：语言可能不匹配")
                issues.append(f"{role_name}: promptLang={current_lang}, 但检测到{detected_lang}")
            else:
                print(f"  ✅ 正常")
        
        print("\n" + "=" * 60)
        if issues:
            print(f"发现 {len(issues)} 个问题：")
            for issue in issues:
                print(f"  - {issue}")
            print("\n运行 'python fix_tts_config_lang.py fix' 来修复")
        else:
            print("✅ 所有配置正常")
        print("=" * 60)


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == 'fix':
        fix_tts_config()
    else:
        print("使用方法：")
        print("  python fix_tts_config_lang.py        # 只检查，不修改")
        print("  python fix_tts_config_lang.py fix    # 检查并修复")
        print()
        check_config_only()
