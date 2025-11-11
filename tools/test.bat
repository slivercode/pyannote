mkdir -p vendor/torch_cpu  # 创建目标目录
for whl in ./torch_cpu_wheels/*.whl; do
   .\python\python.exe -m wheel unpack "$whl" -d vendor/torch_cpu
done