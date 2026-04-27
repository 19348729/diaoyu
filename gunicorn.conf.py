"""
Gunicorn 生产环境配置
====================
使用 Uvicorn worker 运行 FastAPI ASGI 应用。
"""
import multiprocessing

# ── 绑定地址（仅监听本地回环，由 Nginx 反向代理） ──
bind = "127.0.0.1:8000"

# ── Worker 进程数 ──
# 公式：CPU 核心数 × 2 + 1（小型服务器建议 2~4）
workers = min(multiprocessing.cpu_count() * 2 + 1, 4)

# ── 使用 Uvicorn 的 ASGI worker ──
worker_class = "uvicorn.workers.UvicornWorker"

# ── 超时设置 ──
timeout = 30           # Worker 响应超时（秒）
graceful_timeout = 10  # 优雅关闭等待时间
keepalive = 5          # Keep-Alive 超时

# ── 日志（使用相对路径，相对于 WorkingDirectory） ──
accesslog = "logs/access.log"
errorlog = "logs/error.log"
loglevel = "info"

# ── 进程管理 ──
pidfile = "gunicorn.pid"
daemon = False  # 由 systemd 管理，不启用守护模式

# ── 性能调优 ──
worker_connections = 1000
max_requests = 5000        # 每个 worker 处理 N 个请求后自动重启（防内存泄漏）
max_requests_jitter = 500  # 加随机抖动，避免所有 worker 同时重启
