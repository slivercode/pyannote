"""
任务管理路由模块
处理脚本任务的启动、监控和取消
"""
import asyncio
import os
import pathlib
import sys
import threading
import uuid
from datetime import datetime
from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from models.responses import TaskStatus
from config.dependencies import get_scripts_dir, get_tasks, get_task_lock

router = APIRouter(prefix="/api", tags=["任务管理"])


class TaskRequest(BaseModel):
    """启动任务的请求参数：脚本名 + 脚本参数"""
    script_name: str  # 脚本文件名（如long_task.py）
    script_args: Optional[List[str]] = []  # 传递给脚本的参数（可选）


def generate_task_id() -> str:
    """生成唯一任务ID（UUID简化版）"""
    return str(uuid.uuid4()).split("-")[0]


def get_script_path(script_name: str) -> str:
    """获取脚本的绝对路径，验证脚本是否存在"""
    scripts_dir = get_scripts_dir()
    script_path = os.path.join(scripts_dir, script_name)
    if not os.path.exists(script_path):
        raise HTTPException(status_code=404, detail=f"脚本不存在：{script_name}")
    if not script_path.endswith(".py"):
        raise HTTPException(status_code=400, detail="仅支持.py脚本")
    return script_path


def parse_script_output(line: str, task_info: Dict):
    """解析脚本输出，提取进度（兼容行首带空格/换行的情况）"""
    # 1. 保留原始输出（包括空格和换行），直接追加到output中
    task_info["output"] += line + "\n"

    # 2. 处理行首空白（仅去除左侧空白，保留右侧和中间的格式）
    processed_line = line.lstrip()  # 只去掉左侧空白，右侧空白不影响判断

    # 3. 解析进度（约定脚本输出PROGRESS:XX%格式的行表示进度）
    if processed_line.startswith("PROGRESS:"):
        try:
            # 分割后处理可能的空格（如"PROGRESS:  50%"）
            progress_part = processed_line.split(":", 1)[1].strip()
            progress_str = progress_part.rstrip("%").strip()
            # 去除百分号并转换为整数（兼容"50%"或"50"的情况）
            progress_float = float(progress_str)

            # 四舍五入成整数百分比（如果需要保留小数，可以直接存 float）
            progress = round(progress_float)

            # 确保进度在 0-100 之间
            task_info["progress"] = max(0, min(100, progress))
        except (ValueError, IndexError):
            # 格式错误时忽略，不影响其他输出解析
            pass


async def run_script_async(task_id: str, script_path: str, script_args: List[str]):
    """异步启动子进程，避免与 asyncio 事件循环冲突"""
    tasks = get_tasks()
    task_lock = get_task_lock()
    scripts_dir = get_scripts_dir()
    
    task_info = tasks[task_id]
    try:
        # 1. 获取主程序路径（打包后是 vocal_separation.exe，开发时是 python.exe）
        main_exe_path = pathlib.Path(sys.executable)
        if not main_exe_path.exists():
            raise FileNotFoundError(f"找不到主程序：{main_exe_path}")
        print(f"子进程使用的主程序路径：{main_exe_path}")

        # 2. 验证子脚本存在（script_path 已由 get_script_path 处理为绝对路径）
        script_abs_path = pathlib.Path(script_path)
        if not script_abs_path.exists():
            raise FileNotFoundError(f"脚本不存在：{script_abs_path}")
        print(f"子进程执行的脚本路径：{script_abs_path}")

        # 复制父进程环境变量，新增 PYTHONIOENCODING 强制子程序用UTF-8输出
        sub_env = os.environ.copy()
        sub_env["PYTHONIOENCODING"] = "utf-8"
        
        # 将 scripts_dir 添加到 PYTHONPATH 中
        scripts_dir_str = str(scripts_dir.resolve())
        if "PYTHONPATH" in sub_env:
            sub_env["PYTHONPATH"] = scripts_dir_str + os.pathsep + sub_env["PYTHONPATH"]
        else:
            sub_env["PYTHONPATH"] = scripts_dir_str
        
        sub_env["LC_ALL"] = "en_US.UTF-8"
        sub_env["LANG"] = "en_US.UTF-8"

        # 启动子进程
        cmd = [
            str(main_exe_path),  # Python解释器（python.exe）
            str(script_abs_path),  # 子脚本路径
            *script_args,  # 子脚本参数
        ]
        print(f"子进程启动命令：{' '.join(cmd)}")

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=sub_env,
        )
        task_info["process"] = process

        # 异步读取 stdout
        async def read_stdout_async():
            async for line_bytes in process.stdout:
                line = line_bytes.decode("utf-8", errors="replace")
                if line:
                    print(line, end="")
                with task_lock:
                    parse_script_output(line, task_info)

        # 异步读取 stderr
        async def read_stderr_async():
            async for line_bytes in process.stderr:
                line = line_bytes.decode("utf-8", errors="replace")
                if line:
                    print(f"[ERROR] {line}", end="", file=sys.stderr)
                with task_lock:
                    task_info["output"] += f"[ERROR] {line}\n"

        # 并发执行两个异步读取任务
        await asyncio.gather(read_stdout_async(), read_stderr_async())

        # 等待子进程结束并更新状态
        returncode = await process.wait()

        with task_lock:
            end_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            task_info["end_time"] = end_time
            if returncode == 0:
                task_info["status"] = "completed"
                task_info["progress"] = min(task_info["progress"], 100)
            else:
                task_info["status"] = "failed"
                task_info["error"] = f"脚本返回码：{returncode}"

    except Exception as e:
        end_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with task_lock:
            task_info["status"] = "failed"
            task_info["error"] = str(e)
            task_info["end_time"] = end_time
            task_info["output"] += f"\n[系统错误] {str(e)}"


async def stop_script_async(task_id: str) -> Dict:
    tasks = get_tasks()
    task_lock = get_task_lock()
    
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="任务不存在")

    with task_lock:
        task_info = tasks[task_id]
        process = task_info.get("process")
        if not process or process.returncode is not None:
            task_info["output"] += "\n[系统信息] 任务已结束，无需终止"
            return task_info

        # 异步终止子进程
        try:
            process.terminate()
            await asyncio.wait_for(process.wait(), timeout=5)  # 等待5秒终止
        except asyncio.TimeoutError:
            process.kill()  # 超时则强制杀死
            await process.wait()

        # 更新任务状态
        end_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        task_info["status"] = "stopped"
        task_info["end_time"] = end_time
        task_info["output"] += "\n[系统信息] 任务已被手动终止"
        return task_info


@router.get("/scripts", summary="获取所有可用脚本列表")
def get_scripts() -> List[str]:
    """返回scripts目录下所有.py脚本的文件名"""
    scripts_dir = get_scripts_dir()
    if not os.path.exists(scripts_dir):
        os.makedirs(scripts_dir)
    return [
        f
        for f in os.listdir(scripts_dir)
        if os.path.isfile(os.path.join(scripts_dir, f)) and f.endswith(".py")
    ]


@router.post("/tasks", summary="启动一个脚本任务", response_model=TaskStatus)
async def create_task(req: TaskRequest) -> TaskStatus:
    tasks = get_tasks()
    task_lock = get_task_lock()
    
    script_path = get_script_path(req.script_name)
    task_id = generate_task_id()
    start_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 初始化任务状态
    with task_lock:
        tasks[task_id] = {
            "task_id": task_id,
            "status": "running",
            "progress": 10,
            "output": f"任务启动时间：{start_time}\n脚本路径：{script_path}\n参数：{req.script_args}\n\n",
            "error": None,
            "start_time": start_time,
            "end_time": None,
        }

    # 用 asyncio 任务启动异步子进程
    asyncio.create_task(
        run_script_async(task_id, pathlib.Path(script_path), req.script_args)
    )

    return tasks[task_id]


@router.get("/tasks/{task_id}", summary="轮询获取任务进度", response_model=TaskStatus)
def get_task_progress(task_id: str) -> TaskStatus:
    """根据任务ID获取当前进度、输出和状态"""
    tasks = get_tasks()
    task_lock = get_task_lock()
    
    with task_lock:
        if task_id not in tasks:
            raise HTTPException(
                status_code=404, detail=f"任务不存在：{task_id}（可能已过期清理）"
            )
        # 返回当前任务状态（深拷贝避免外部修改）
        return tasks[task_id].copy()


@router.get("/tasks/{task_id}/cancel", summary="取消任务", response_model=TaskStatus)
async def cancel_task_progress(task_id: str) -> TaskStatus:
    return await stop_script_async(task_id)