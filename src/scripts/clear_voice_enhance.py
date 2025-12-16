import argparse 
import os
import sys
from datetime import datetime

# 导入统一的 GPU 检测模块
current_script_dir = os.path.dirname(os.path.abspath(__file__))
if current_script_dir not in sys.path:
    sys.path.insert(0, current_script_dir)

from torch_loader import use_gpu, torch
from clearvoice import ClearVoice

# 设置设备
device = "cuda" if use_gpu else "cpu"
print(f"ClearVoice 使用设备: {device}")
print(f"PyTorch CUDA 可用: {torch.cuda.is_available()}")

# -------------------------- 主程序（使用你的 token 配置） --------------------------
if __name__ == "__main__":
    # 配置参数（请根据需求修改）
    parser = argparse.ArgumentParser()
    parser.add_argument('--input-wav', type=str, required=True)
    parser.add_argument('--output-path', type=str, default="output") 
    parser.add_argument('--min-segment-duration', type=float, default=0.5, help="过滤短于 x 秒的片段") 
    parser.add_argument('--huggingface-token', type=str, default="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")  
    args = parser.parse_args()

    input_file = args.input_wav
    output_dir = args.output_path
    try:
        # 初始化在线模型（ClearVoice 会自动使用可用的 CUDA 设备）
        print(f"初始化 ClearVoice 模型，设备: {device}")
        myClearVoice = ClearVoice(task='speech_enhancement', model_names=['MossFormer2_SE_48K'])
        print(f"✅ ClearVoice 模型加载成功") 
        # 初始化输出目录
        file_name = os.path.splitext(os.path.basename(input_file))[0]
        date_dir = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        output_root = os.path.join(os.getcwd(), output_dir, date_dir, file_name)
        os.makedirs(output_root, exist_ok=True)
        print(f"PROGRESS:15%")
        # 语音增强并保存结果
        myClearVoice(input_path=input_file,output_path=output_root,online_write=True)
        print(f"PROGRESS:90%")
        # 打印output_root文件夹下所有的文件
        for filename in os.listdir(os.path.join(output_root,"MossFormer2_SE_48K")):
            file_path = os.path.join(output_root, filename)
            if os.path.isdir(file_path):
                print(f"[目录] {filename}")
            else:
                result_path = os.path.join(output_root,"MossFormer2_SE_48K",filename).replace(os.sep,"/")
                print(f"result: {result_path}")
        print(f"PROGRESS:100%")
    except Exception as e:
        print(f"\n❌ 执行失败：{str(e)}")
        sys.exit(1)

