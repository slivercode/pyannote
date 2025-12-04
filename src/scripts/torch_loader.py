# torch_loader.py（单独的加载模块，放在项目根目录或子目录均可）
import sys
import os
import pathlib
import subprocess
import platform


def _is_gpu_available(required_cuda_main=126):
    """内部函数：检测GPU和兼容CUDA，不对外暴露"""
    #return False
    if platform.system() not in ["Windows", "Linux"]:
        return False

    # 调用nvidia-smi检测NVIDIA GPU
    try:
        if platform.system() == "Windows":
            result = subprocess.run(
                ["cmd", "/c", "nvidia-smi"],
                capture_output=True,
                text=True,
                check=True
            )
        else:
            result = subprocess.run(
                ["nvidia-smi"],
                capture_output=True,
                text=True,
                check=True
            )
        nvidia_output = result.stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False

    # 提取CUDA版本
    cuda_version = None
    for line in nvidia_output.splitlines():
        if "CUDA Version:" in line:
            cuda_version = line.split("CUDA Version:")[-1].strip().split()[0]
            break
    if not cuda_version:
        return False

    # 对比版本（12.6→126）
    try:
        cuda_main = int(cuda_version.replace(".", "").split("_")[0])
        return cuda_main >= required_cuda_main
    except:
        return False


# ---------------------- 核心加载逻辑（仅执行一次） ----------------------
# 1. 定位vendor目录（基于torch_loader.py的位置，确保路径正确）
# 若torch_loader.py放在子目录（如utils/），需多写一个.parent（如.parent.parent.parent）
current_dir = pathlib.Path(__file__).parent.parent.parent  # 假设放在项目根目录，若在utils/则改为.parent.parent
VENDOR_DIR = os.path.join(current_dir, "vendor")

# 2. 检测GPU
use_gpu = _is_gpu_available(required_cuda_main=126)

# 3. 选择并加载对应PyTorch版本
if use_gpu:
    torch_path = os.path.join(VENDOR_DIR, "torch_gpu")
    print(f"[TorchLoader] 检测到兼容GPU，加载: {torch_path}")
else:
    torch_path = os.path.join(VENDOR_DIR, "torch_cpu")
    print(f"[TorchLoader] 加载CPU版，路径: {torch_path}")

# 将 torch_path 转换为绝对路径（避免子进程路径解析问题）
torch_path = os.path.abspath(torch_path)  # 确保是绝对路径

# 4. 优先加载目标PyTorch（插入sys.path最前面）
sys.path.insert(0, torch_path)

# 5. 导入torch并验证
try:
    import torch  # type: ignore
except ImportError as e:
    raise RuntimeError(f"[TorchLoader] 加载PyTorch失败！请检查{torch_path}是否存在torch核心库") from e

# 6. 导入torchvision并验证（先查路径，再查版本）
try:
    import torchvision  # type: ignore
    # 关键：打印实际加载的torchvision路径，确认是否在vendor目录下
    print(f"[TorchLoader] 实际加载的torchvision路径: {torchvision.__file__}")
except ImportError as e:
    raise RuntimeError(f"[TorchLoader] 加载torchvision失败！请检查{torch_path}是否存在torchvision") from e

# 7. 验证版本和CUDA
print(f"[TorchLoader] 已加载 PyTorch {torch.__version__}，torchvision {torchvision.__version__}，CUDA可用: {torch.cuda.is_available()}")

# ---------------------- 导出供其他脚本使用的对象 ----------------------
__all__ = ["torch", "torchvision", "use_gpu", "torch_path"]  # 导出torchvision，方便其他脚本直接使用