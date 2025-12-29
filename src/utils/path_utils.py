"""
跨平台路径处理工具模块
确保Windows和Linux环境下的路径处理一致性
"""
import os
import stat
import pathlib
from typing import Optional
import logging

logger = logging.getLogger(__name__)


def ensure_directory_exists(dir_path: pathlib.Path, mode: int = 0o755) -> bool:
    """
    确保目录存在且可写（跨平台）
    
    Args:
        dir_path: 目录路径
        mode: 目录权限模式（仅Linux/Mac有效）
    
    Returns:
        bool: 是否成功
    """
    try:
        # 创建目录（如果不存在）
        dir_path.mkdir(parents=True, exist_ok=True)
        
        # 在Linux/Mac上设置权限
        if os.name != 'nt':  # 非Windows系统
            try:
                os.chmod(dir_path, mode)
                logger.info(f"已设置目录权限: {dir_path} -> {oct(mode)}")
            except Exception as e:
                logger.warning(f"设置目录权限失败（可能无需修改）: {e}")
        
        # 验证目录可写
        test_file = dir_path / ".write_test"
        try:
            test_file.write_text("test")
            test_file.unlink()
            logger.debug(f"目录可写: {dir_path}")
            return True
        except Exception as e:
            logger.error(f"目录不可写: {dir_path}, 错误: {e}")
            return False
            
    except Exception as e:
        logger.error(f"创建目录失败: {dir_path}, 错误: {e}")
        return False


def normalize_path(path: str) -> pathlib.Path:
    """
    规范化路径（跨平台）
    
    处理：
    - 路径分隔符统一
    - 移除不可见字符
    - 解析相对路径
    - 展开用户目录
    
    Args:
        path: 原始路径字符串
    
    Returns:
        pathlib.Path: 规范化后的路径对象
    """
    # 1. 清理不可见Unicode控制字符
    import unicodedata
    cleaned_path = ''.join(
        char for char in path.strip()
        if unicodedata.category(char) not in ('Cc', 'Cf', 'Cn', 'Co', 'Cs')
        or char in ('\n', '\r', '\t')
    ).strip()
    
    # 2. 转换为pathlib.Path（自动处理路径分隔符）
    p = pathlib.Path(cleaned_path)
    
    # 3. 展开用户目录（~）
    p = p.expanduser()
    
    # 4. 解析为绝对路径
    p = p.resolve()
    
    return p


def safe_file_write(file_path: pathlib.Path, content: bytes, mode: int = 0o644) -> bool:
    """
    安全写入文件（跨平台）
    
    Args:
        file_path: 文件路径
        content: 文件内容（字节）
        mode: 文件权限模式（仅Linux/Mac有效）
    
    Returns:
        bool: 是否成功
    """
    try:
        # 确保父目录存在
        ensure_directory_exists(file_path.parent)
        
        # 写入文件
        file_path.write_bytes(content)
        
        # 在Linux/Mac上设置文件权限
        if os.name != 'nt':
            try:
                os.chmod(file_path, mode)
            except Exception as e:
                logger.warning(f"设置文件权限失败: {e}")
        
        logger.info(f"文件写入成功: {file_path}")
        return True
        
    except Exception as e:
        logger.error(f"文件写入失败: {file_path}, 错误: {e}")
        return False


def get_file_permissions(file_path: pathlib.Path) -> Optional[str]:
    """
    获取文件权限信息（跨平台）
    
    Args:
        file_path: 文件路径
    
    Returns:
        str: 权限信息字符串，Windows返回None
    """
    if os.name == 'nt':  # Windows
        return None
    
    try:
        st = os.stat(file_path)
        mode = st.st_mode
        
        # 转换为可读格式（如：rwxr-xr-x）
        perms = stat.filemode(mode)
        
        return f"{perms} (UID:{st.st_uid}, GID:{st.st_gid})"
    except Exception as e:
        logger.error(f"获取文件权限失败: {e}")
        return None


def fix_directory_permissions(dir_path: pathlib.Path, 
                              dir_mode: int = 0o755, 
                              file_mode: int = 0o644) -> bool:
    """
    递归修复目录权限（仅Linux/Mac）
    
    Args:
        dir_path: 目录路径
        dir_mode: 目录权限模式
        file_mode: 文件权限模式
    
    Returns:
        bool: 是否成功
    """
    if os.name == 'nt':  # Windows不需要修复权限
        return True
    
    try:
        # 修复目录本身
        os.chmod(dir_path, dir_mode)
        
        # 递归修复子目录和文件
        for root, dirs, files in os.walk(dir_path):
            # 修复子目录
            for d in dirs:
                try:
                    os.chmod(os.path.join(root, d), dir_mode)
                except Exception as e:
                    logger.warning(f"修复子目录权限失败 {d}: {e}")
            
            # 修复文件
            for f in files:
                try:
                    os.chmod(os.path.join(root, f), file_mode)
                except Exception as e:
                    logger.warning(f"修复文件权限失败 {f}: {e}")
        
        logger.info(f"目录权限修复完成: {dir_path}")
        return True
        
    except Exception as e:
        logger.error(f"目录权限修复失败: {e}")
        return False


def is_path_writable(path: pathlib.Path) -> bool:
    """
    检查路径是否可写（跨平台）
    
    Args:
        path: 路径（文件或目录）
    
    Returns:
        bool: 是否可写
    """
    try:
        if path.is_dir():
            # 测试目录可写性
            test_file = path / ".write_test"
            test_file.write_text("test")
            test_file.unlink()
            return True
        else:
            # 测试文件可写性
            return os.access(path, os.W_OK)
    except Exception:
        return False


def get_platform_info() -> dict:
    """
    获取平台信息（用于调试）
    
    Returns:
        dict: 平台信息
    """
    import platform
    
    info = {
        "system": platform.system(),  # Windows, Linux, Darwin
        "platform": platform.platform(),
        "python_version": platform.python_version(),
        "is_windows": os.name == 'nt',
        "path_separator": os.sep,
        "line_separator": repr(os.linesep),
    }
    
    # Linux/Mac特有信息
    if os.name != 'nt':
        try:
            info["uid"] = os.getuid()
            info["gid"] = os.getgid()
            info["username"] = os.getlogin()
        except Exception:
            pass
    
    return info


# 导出常用函数
__all__ = [
    'ensure_directory_exists',
    'normalize_path',
    'safe_file_write',
    'get_file_permissions',
    'fix_directory_permissions',
    'is_path_writable',
    'get_platform_info',
]
