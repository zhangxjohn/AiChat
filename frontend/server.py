import http.server
import os

# 设置工作目录为当前文件所在目录
os.chdir(os.path.dirname(os.path.abspath(__file__)))

class Handler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        super().end_headers()

print("启动服务器...")
server = http.server.HTTPServer(('localhost', 5173), Handler)
print(f"前端服务器运行在 http://localhost:5173")
server.serve_forever() 