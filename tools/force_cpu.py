import sys
import subprocess
import platform

def is_admin():
    """判断是否为管理员/root权限（避免安装失败）"""
    try:
        if platform.system() == "Windows":
            import ctypes
            return ctypes.windll.shell32.IsUserAnAdmin() != 0
        else:
            import os
            return os.geteuid() == 0
    except Exception:
        return False

def check_pytorch_type():
    """检测当前PyTorch版本类型：返回 (是否安装, 是否为CPU版本)"""
    print("=== 第一步：检测当前PyTorch状态 ===")
    try:
        import torch
        ver = torch.__version__
        is_cpu = "+cpu" in ver
        print(f"✅ 已安装PyTorch：{ver}")
        print(f"✅ 当前版本类型：{'CPU版本' if is_cpu else 'GPU版本'}")
        return (True, is_cpu)
    except ImportError:
        print("ℹ️ 未检测到已安装的PyTorch")
        return (False, False)
    except Exception as e:
        print(f"⚠️ 检测异常：{str(e)}，视为未正常安装")
        return (False, False)

def uninstall_pytorch():
    """卸载当前PyTorch（含torchvision、torchaudio）"""
    print("\n=== 第二步：卸载GPU版本PyTorch ===")
    # 使用当前Python的pip，避免环境冲突
    pip_cmd = [sys.executable, "-m", "pip", "uninstall", "-y", "torch", "torchvision", "torchaudio"]
    print(f"执行卸载命令：{' '.join(pip_cmd)}")
    
    try:
        result = subprocess.run(pip_cmd, capture_output=True, text=True, check=True)
        print("✅ PyTorch及其依赖已成功卸载")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ 卸载失败：{e.stderr[:300]}...")
        return False
    except Exception as e:
        print(f"❌ 卸载异常：{str(e)}")
        return False

def install_cpu_pytorch():
    """安装指定版本的PyTorch CPU版本（适配pyannote-audio的2.8.0+）"""
    print("\n=== 第三步：安装PyTorch CPU版本 ===")
    # 指定CPU版本（2.8.0，兼容pyannote-audio）+ 国内源加速
    install_cmd = [
        sys.executable, "-m", "pip", "install",
        "torch==2.8.0+cpu", "torchvision==0.23.0+cpu", "torchaudio==2.8.0",
        "--index-url", "https://download.pytorch.org/whl/cpu",
        "--extra-index-url", "https://pypi.tuna.tsinghua.edu.cn/simple"  # 国内源加速
    ]
    print(f"执行安装命令：{' '.join(install_cmd)}")
    
    try:
        # 显示实时安装日志
        result = subprocess.run(install_cmd, stdout=sys.stdout, stderr=sys.stderr, check=True)
        print("\n✅ PyTorch CPU版本安装完成")
        return True
    except subprocess.CalledProcessError as e:
        print(f"\n❌ 安装失败：{e.stderr[:300]}...")
        return False
    except Exception as e:
        print(f"\n❌ 安装异常：{str(e)}")
        return False

def verify_cpu_install():
    """验证最终是否为CPU版本"""
    print("\n=== 第四步：验证安装结果 ===")
    try:
        import torch
        ver = torch.__version__
        is_cpu = "+cpu" in ver
        cuda_available = torch.cuda.is_available()
        
        if is_cpu and not cuda_available:
            print(f"✅ 验证通过！当前版本：{ver}（CPU版本）")
            print(f"✅ GPU加速已禁用（符合预期）")
            return True
        else:
            print(f"⚠️ 验证失败！当前版本：{ver}（非CPU版本）")
            return False
    except ImportError:
        print("❌ 验证失败：PyTorch未成功导入")
        return False
    except Exception as e:
        print(f"⚠️ 验证异常：{str(e)}")
        return False

def main():
    print("="*50)
    print("       PyTorch GPU→CPU版本切换脚本")
    print("="*50)
    print(f"当前Python环境：{sys.executable}")
    print(f"当前系统：{platform.system()} {platform.release()}")
    
    # 权限提示
    if not is_admin():
        print("⚠️ 警告：建议用管理员/root权限运行，避免安装失败")
        confirm = input("是否继续？(y/n，默认n)：").strip().lower()
        if confirm != "y":
            print("❌ 用户取消操作")
            sys.exit(0)

    # 核心流程：检测→卸载（如需）→安装（如需）→验证
    installed, is_cpu = check_pytorch_type()
    
    if installed and is_cpu:
        print("\n✅ 无需操作：当前已为PyTorch CPU版本")
        sys.exit(0)
    
    # 卸载GPU版本（无论是否安装，都尝试卸载，确保干净）
    uninstall_success = uninstall_pytorch()
    if not uninstall_success:
        print("❌ 卸载失败，无法继续安装CPU版本")
        sys.exit(1)
    
    # 安装CPU版本
    install_success = install_cpu_pytorch()
    if not install_success:
        print("❌ 安装CPU版本失败")
        sys.exit(1)
    
    # 验证结果
    verify_success = verify_cpu_install()
    sys.exit(0 if verify_success else 1)

if __name__ == "__main__":
    main()