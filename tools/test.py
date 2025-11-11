import torch
import torchvision
import torchaudio  # 如果你用到了torchaudio

# 打印完整版本号（包含CUDA信息）
print("PyTorch版本：", torch.__version__)
print("TorchVision版本：", torchvision.__version__)
print("Torchaudio版本：", torchaudio.__version__)  # 若未安装可忽略

# 额外确认CUDA适配版本（GPU版关键信息）
print("CUDA版本（PyTorch编译时）：", torch.version.cuda) # type: ignore