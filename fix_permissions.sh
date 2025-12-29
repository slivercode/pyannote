#!/bin/bash
# 跨平台权限修复脚本（Linux/Mac）
# 用于修复文件上传目录的权限问题

echo "=========================================="
echo "文件上传目录权限修复工具"
echo "=========================================="
echo ""

# 获取脚本所在目录
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

echo "当前目录: $SCRIPT_DIR"
echo ""

# 检查是否为Linux/Mac
if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "win32" ]]; then
    echo "检测到Windows系统，无需修复权限"
    exit 0
fi

# 创建目录（如果不存在）
echo "1. 创建必要的目录..."
mkdir -p input output logs hf_cache
echo "   ✅ 目录创建完成"
echo ""

# 修复目录权限
echo "2. 修复目录权限..."
chmod 755 input output logs hf_cache 2>/dev/null
if [ $? -eq 0 ]; then
    echo "   ✅ 目录权限设置为 755"
else
    echo "   ⚠️ 权限设置失败，可能需要sudo权限"
    echo "   请运行: sudo chmod 755 input output logs hf_cache"
fi
echo ""

# 修复文件权限
echo "3. 修复文件权限..."
find input output -type f -exec chmod 644 {} \; 2>/dev/null
if [ $? -eq 0 ]; then
    echo "   ✅ 文件权限设置为 644"
else
    echo "   ⚠️ 文件权限设置失败"
fi
echo ""

# 修复所有者（可选）
echo "4. 检查所有者..."
CURRENT_USER=$(whoami)
echo "   当前用户: $CURRENT_USER"

read -p "   是否修改所有者为当前用户? (y/n): " -n 1 -r
echo ""
if [[ $REPLY =~ ^[Yy]$ ]]; then
    chown -R $CURRENT_USER:$CURRENT_USER input output logs hf_cache 2>/dev/null
    if [ $? -eq 0 ]; then
        echo "   ✅ 所有者修改成功"
    else
        echo "   ⚠️ 所有者修改失败，可能需要sudo权限"
        echo "   请运行: sudo chown -R $CURRENT_USER:$CURRENT_USER input output logs hf_cache"
    fi
else
    echo "   跳过所有者修改"
fi
echo ""

# 测试写入权限
echo "5. 测试写入权限..."
TEST_FILE="input/.write_test"
echo "test" > "$TEST_FILE" 2>/dev/null
if [ $? -eq 0 ]; then
    rm "$TEST_FILE"
    echo "   ✅ input目录可写"
else
    echo "   ❌ input目录不可写"
    echo "   请检查权限或使用sudo运行此脚本"
fi

TEST_FILE="output/.write_test"
echo "test" > "$TEST_FILE" 2>/dev/null
if [ $? -eq 0 ]; then
    rm "$TEST_FILE"
    echo "   ✅ output目录可写"
else
    echo "   ❌ output目录不可写"
    echo "   请检查权限或使用sudo运行此脚本"
fi
echo ""

# 显示最终状态
echo "=========================================="
echo "权限修复完成"
echo "=========================================="
echo ""
echo "目录状态:"
ls -ld input output logs 2>/dev/null
echo ""
echo "如果仍有问题，请运行:"
echo "  python3 diagnose_upload.py"
echo ""
