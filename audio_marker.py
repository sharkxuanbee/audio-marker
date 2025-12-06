import http.server
import socketserver
import webbrowser
import json
import os
import urllib.parse
import threading
import time

# --- 配置 ---
PORT = 9999
MARKER_FILE = "markers.json"

# --- HTML 前端页面 (包含 CSS 和 JS) ---
# 这里我们将整个网页界面嵌入到 Python 代码中
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="zh">
<head>
    <meta charset="UTF-8">
    <title>简易听力标记助手 (无需安装版)</title>
    <style>
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; max-width: 1000px; margin: 0 auto; padding: 20px; background: #f5f5f5; }
        .container { display: flex; gap: 20px; }
        .player-section { flex: 2; background: white; padding: 20px; border-radius: 10px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }
        .list-section { flex: 1; background: white; padding: 20px; border-radius: 10px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); height: 80vh; overflow-y: auto; }
        h2 { margin-top: 0; color: #333; }
        input[type="file"] { margin-bottom: 20px; }
        video { width: 100%; border-radius: 5px; background: #000; }
        .controls { margin-top: 15px; display: flex; gap: 10px; align-items: center; }
        input[type="text"] { padding: 8px; border: 1px solid #ddd; border-radius: 4px; flex-grow: 1; }
        button { padding: 8px 15px; border: none; border-radius: 4px; cursor: pointer; transition: background 0.2s; }
        .btn-add { background: #28a745; color: white; }
        .btn-add:hover { background: #218838; }
        .marker-item { background: #f8f9fa; border: 1px solid #e9ecef; padding: 10px; margin-bottom: 8px; border-radius: 5px; display: flex; justify-content: space-between; align-items: center; }
        .marker-info { cursor: pointer; flex-grow: 1; }
        .marker-time { color: #007bff; font-weight: bold; font-size: 0.9em; }
        .btn-del { background: #dc3545; color: white; font-size: 0.8em; margin-left: 10px; }
        .btn-del:hover { background: #c82333; }
        #current-time-display { font-family: monospace; font-size: 1.2em; color: #555; }
    </style>
</head>
<body>
    <h1>🎧 简易听力标记助手</h1>
    <div class="container">
        <div class="player-section">
            <h2>1. 选择文件 & 播放</h2>
            <input type="file" id="fileInput" accept="video/*,audio/*">
            <video id="mediaPlayer" controls></video>
            
            <hr>
            
            <h2>2. 添加标记</h2>
            <div style="margin-bottom: 10px;">当前时间: <span id="current-time-display">00:00</span></div>
            <div class="controls">
                <input type="text" id="markerLabel" placeholder="输入标记名称 (如: Part 1)">
                <button class="btn-add" onclick="addMarker()">添加标记</button>
            </div>
        </div>

        <div class="list-section">
            <h2>3. 标记列表</h2>
            <div id="markerList">
                <p style="color:#777">请先上传文件...</p>
            </div>
        </div>
    </div>

    <script>
        const player = document.getElementById('mediaPlayer');
        const fileInput = document.getElementById('fileInput');
        let currentFileName = "";
        let markers = {};

        // 监听文件上传
        fileInput.addEventListener('change', function(e) {
            const file = e.target.files[0];
            if (!file) return;
            
            currentFileName = file.name;
            const fileURL = URL.createObjectURL(file);
            player.src = fileURL;
            
            // 加载标记
            loadMarkers();
        });

        // 更新当前时间显示
        player.addEventListener('timeupdate', function() {
            document.getElementById('current-time-display').innerText = formatTime(player.currentTime);
        });

        // 格式化时间
        function formatTime(seconds) {
            const m = Math.floor(seconds / 60);
            const s = Math.floor(seconds % 60);
            return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
        }

        // 添加标记
        function addMarker() {
            if (!currentFileName) { alert("请先选择文件！"); return; }
            const label = document.getElementById('markerLabel').value;
            if (!label) { alert("请输入名称"); return; }
            
            const time = player.currentTime;
            
            if (!markers[currentFileName]) markers[currentFileName] = [];
            markers[currentFileName].push({ label: label, time: time });
            // 排序
            markers[currentFileName].sort((a, b) => a.time - b.time);
            
            saveMarkers();
            renderMarkers();
            document.getElementById('markerLabel').value = "";
        }

        // 渲染列表
        function renderMarkers() {
            const listDiv = document.getElementById('markerList');
            listDiv.innerHTML = "";
            
            const currentList = markers[currentFileName] || [];
            if (currentList.length === 0) {
                listDiv.innerHTML = "<p>暂无标记</p>";
                return;
            }

            currentList.forEach((item, index) => {
                const div = document.createElement('div');
                div.className = 'marker-item';
                div.innerHTML = `
                    <div class="marker-info" onclick="jumpTo(${item.time})">
                        <div class="marker-time">⏱️ ${formatTime(item.time)}</div>
                        <div>${item.label}</div>
                    </div>
                    <button class="btn-del" onclick="deleteMarker(${index})">删除</button>
                `;
                listDiv.appendChild(div);
            });
        }

        function jumpTo(time) {
            player.currentTime = time;
            player.play();
        }

        function deleteMarker(index) {
            markers[currentFileName].splice(index, 1);
            saveMarkers();
            renderMarkers();
        }

        // --- 与 Python 后端通信 ---

        function saveMarkers() {
            fetch('/save', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(markers)
            });
        }

        function loadMarkers() {
            fetch('/load')
            .then(response => response.json())
            .then(data => {
                markers = data;
                renderMarkers();
            })
            .catch(err => {
                markers = {};
                renderMarkers();
            });
        }
        
        // 初始加载
        loadMarkers();

    </script>
</body>
</html>
"""

class CustomHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        # 如果访问根目录，返回我们的 HTML 界面
        if self.path == '/':
            self.send_response(200)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(HTML_TEMPLATE.encode('utf-8'))
        elif self.path == '/load':
            # 加载 JSON 数据
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            if os.path.exists(MARKER_FILE):
                with open(MARKER_FILE, 'rb') as f:
                    self.wfile.write(f.read())
            else:
                self.wfile.write(b'{}')
        else:
            # 其他情况（如浏览器请求图标等），按默认处理
            super().do_GET()

    def do_POST(self):
        # 保存 JSON 数据
        if self.path == '/save':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            
            try:
                # 写入本地文件
                with open(MARKER_FILE, 'wb') as f:
                    f.write(post_data)
                
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'{"status": "success"}')
            except Exception as e:
                self.send_response(500)
                self.end_headers()
                print(f"Error saving: {e}")

def open_browser():
    """等待1秒后自动打开浏览器"""
    time.sleep(1)
    webbrowser.open(f"http://localhost:{PORT}")

if __name__ == "__main__":
    # 切换到脚本所在目录，确保 JSON 文件保存在正确位置
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    
    print(f"✅ 服务已启动！")
    print(f"👉 如果浏览器没有自动打开，请手动访问: http://localhost:{PORT}")
    print("❌ 关闭此窗口即可停止程序")

    # 启动自动打开浏览器的线程
    threading.Thread(target=open_browser).start()

    # 启动服务器
    with socketserver.TCPServer(("", PORT), CustomHandler) as httpd:
        httpd.serve_forever()