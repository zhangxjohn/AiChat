import subprocess
import sys
import time
import os

def stop_existing_servers():
    print("正在停止已运行的服务...")
    # 停止后端服务
    subprocess.run(['pkill', '-f', 'python main.py'])
    # 停止前端服务
    subprocess.run(['pkill', '-f', 'python server.py'])
    # 强制释放端口
    subprocess.run(['fuser', '-k', '5173/tcp'], stderr=subprocess.DEVNULL)
    subprocess.run(['fuser', '-k', '8000/tcp'], stderr=subprocess.DEVNULL)
    # 等待服务完全停止
    time.sleep(1)
    print("已停止之前运行的服务\n")

def start_servers():
    print("正在启动聊天服务...")
    
    # 获取当前脚本所在目录
    current_dir = os.path.dirname(os.path.abspath(__file__))
    
    # 启动后端服务
    backend_process = subprocess.Popen(
        ['python', 'main.py'],
        cwd=os.path.join(current_dir, 'backend')
    )
    time.sleep(2)  # 等待后端启动
    print("后端 服务启动成功！")
    
    # 启动前端服务
    frontend_process = subprocess.Popen(
        ['python', 'server.py'],
        cwd=os.path.join(current_dir, 'frontend')
    )
    time.sleep(1)  # 等待前端启动
    print("前端 服务启动成功！")
    
    print("\n服务已启动！")
    print("后端地址: http://localhost:8000")
    print("前端地址: http://localhost:5173")
    print("\n按 Ctrl+C 停止服务...")
    
    try:
        backend_process.wait()
    except KeyboardInterrupt:
        print("\n正在停止服务...")
        backend_process.terminate()
        frontend_process.terminate()
        stop_existing_servers()
        print("服务已停止")
        sys.exit(0)

if __name__ == "__main__":
    stop_existing_servers()  # 先停止已存在的服务
    start_servers() 