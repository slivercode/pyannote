import os
import sys
import subprocess
import shutil
import time
from pathlib import Path


class TorchDownloader:
    def __init__(
        self,
        # 核心配置：根据你的需求修改版本号和CUDA标签
        torch_version="2.8.0",
        cuda_tag="cu126",  # GPU版CUDA标签（如cu118、cu121）
        cpu_tag="cpu",     # CPU版标签
        # 路径配置
        download_root="./torch_wheels",  # 下载的wheel包存放根目录
        vendor_root="./vendor",          # 解压后的目标根目录
        # 源配置（加速下载）
        torch_index_url="https://download.pytorch.org/whl",
        extra_index_url="https://pypi.tuna.tsinghua.edu.cn/simple",
        # 嵌入式Python路径（若不指定则使用当前Python环境）
        python_path=None
    ):
        # 版本和标签
        self.torch_version = torch_version
        self.cuda_tag = cuda_tag
        self.cpu_tag = cpu_tag
        # 组件列表（确保版本匹配）
        self.components = [
            f"torch=={torch_version}+{cpu_tag}",
            f"torchvision=={torch_version.split('.')[0]}.{int(torch_version.split('.')[1])+19}.0+{cpu_tag}",  # 版本匹配规则
            f"torchaudio=={torch_version}+{cpu_tag}"
        ]
        self.gpu_components = [
            f"torch=={torch_version}+{cuda_tag}",
            f"torchvision=={torch_version.split('.')[0]}.{int(torch_version.split('.')[1])+19}.0+{cuda_tag}",
            f"torchaudio=={torch_version}+{cuda_tag}"
        ]
        # 路径
        self.download_root = Path(download_root)
        self.cpu_download_dir = self.download_root / "cpu"
        self.gpu_download_dir = self.download_root / "gpu"
        self.vendor_root = Path(vendor_root)
        self.cpu_target_dir = self.vendor_root / "torch_cpu"
        self.gpu_target_dir = self.vendor_root / "torch_gpu"
        # 源地址
        self.torch_index_url = f"{torch_index_url}/{cpu_tag}"
        self.gpu_torch_index_url = f"{torch_index_url}/{cuda_tag}"
        self.extra_index_url = extra_index_url
        # Python路径（优先使用指定路径，否则用当前Python）
        self.python_path = python_path or sys.executable
        # 确保目录存在
        self._init_dirs()

    def _init_dirs(self):
        """初始化下载和目标目录"""
        for dir_path in [
            self.download_root,
            self.cpu_download_dir,
            self.gpu_download_dir,
            self.vendor_root,
            self.cpu_target_dir,
            self.gpu_target_dir
        ]:
            dir_path.mkdir(parents=True, exist_ok=True)
            print(f"初始化目录: {dir_path}")

    def _run_cmd(self, cmd, retry=3):
        """执行命令并支持重试"""
        for i in range(retry):
            try:
                result = subprocess.run(
                    cmd,
                    check=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True
                )
                return result
            except subprocess.CalledProcessError as e:
                print(f"命令执行失败（第{i+1}/{retry}次）：{e.stderr}")
                if i == retry - 1:
                    raise RuntimeError(f"命令最终失败：{' '.join(cmd)}")
                time.sleep(2)  # 重试间隔

    def download_cpu(self):
        """下载CPU版wheel包"""
        print("\n===== 开始下载CPU版 =====")
        cmd = [
            self.python_path, "-m", "pip", "download",
            *self.components,
            "--index-url", self.torch_index_url,
            "--extra-index-url", self.extra_index_url,
            "--dest", str(self.cpu_download_dir)
        ]
        self._run_cmd(cmd)
        print(f"CPU版下载完成，存放于：{self.cpu_download_dir}")

    def download_gpu(self):
        """下载GPU版wheel包"""
        print("\n===== 开始下载GPU版 =====")
        cmd = [
            self.python_path, "-m", "pip", "download",
            *self.gpu_components,
            "--index-url", self.gpu_torch_index_url,
            "--extra-index-url", self.extra_index_url,
            "--dest", str(self.gpu_download_dir)
        ]
        self._run_cmd(cmd)
        print(f"GPU版下载完成，存放于：{self.gpu_download_dir}")

    def _unpack_wheels(self, wheel_dir, target_dir):
        """解压wheel包到目标目录并整理文件"""
        # 确保wheel工具已安装
        self._run_cmd([self.python_path, "-m", "pip", "install", "wheel"])
        
        # 解压所有wheel包
        wheel_files = list(Path(wheel_dir).glob("*.whl"))
        if not wheel_files:
            raise RuntimeError(f"未找到wheel包：{wheel_dir}")
        
        print(f"\n开始解压 {len(wheel_files)} 个包到 {target_dir}...")
        for wheel in wheel_files:
            print(f"解压：{wheel.name}")
            self._run_cmd([
                self.python_path, "-m", "wheel", "unpack",
                str(wheel), "-d", str(target_dir)
            ])
        
        # 整理文件（移动子文件夹内容到上层，处理Windows文件占用）
        subdirs = [d for d in target_dir.glob("*") if d.is_dir() and "-" in d.name]
        for subdir in subdirs:
            # 移动子文件夹内容到目标目录
            for item in subdir.glob("*"):
                dest = target_dir / item.name
                if dest.exists():
                    if dest.is_dir():
                        shutil.rmtree(dest)
                    else:
                        os.remove(dest)
                shutil.move(str(item), str(target_dir))
            # 重试删除空文件夹（解决Windows文件锁定）
            for i in range(3):
                try:
                    shutil.rmtree(subdir)
                    print(f"删除残留文件夹：{subdir.name}")
                    break
                except PermissionError:
                    print(f"删除 {subdir.name} 失败，重试第{i+1}次...")
                    time.sleep(1)
            else:
                print(f"警告：{subdir.name} 无法删除，可手动清理")

    def unpack_cpu(self):
        """解压CPU版到目标目录"""
        print("\n===== 开始解压CPU版 =====")
        self._unpack_wheels(self.cpu_download_dir, self.cpu_target_dir)
        print(f"CPU版解压完成，存放于：{self.cpu_target_dir}")

    def unpack_gpu(self):
        """解压GPU版到目标目录"""
        print("\n===== 开始解压GPU版 =====")
        self._unpack_wheels(self.gpu_download_dir, self.gpu_target_dir)
        print(f"GPU版解压完成，存放于：{self.gpu_target_dir}")

    def download_and_unpack_all(self):
        """一键下载并解压CPU和GPU版"""
        try:
            self.download_cpu()
            self.download_gpu()
            self.unpack_cpu()
            self.unpack_gpu()
            print("\n===== 所有操作完成！=====")
            print(f"CPU版路径：{self.cpu_target_dir}")
            print(f"GPU版路径：{self.gpu_target_dir}")
        except Exception as e:
            print(f"\n操作失败：{str(e)}")
            sys.exit(1)


if __name__ == "__main__":
    # 示例：根据你的需求修改参数
    downloader = TorchDownloader(
        torch_version="2.8.0",    # PyTorch主版本
        cuda_tag="cu126",         # GPU版CUDA标签（需与你的版本匹配）
        # python_path="./python/python.exe"  # 若使用嵌入式Python，取消注释并填写路径
    )
    # 执行全流程（下载+解压）
    downloader.download_and_unpack_all()