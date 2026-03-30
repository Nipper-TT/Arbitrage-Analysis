"""FastAPI 应用入口，挂载路由和静态文件"""

import os

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from backend.api import router

app = FastAPI(title="对冲套利分析", version="1.0.0")

# 挂载 API 路由
app.include_router(router)

# 挂载静态文件服务
_static_dir = os.path.join(os.path.dirname(__file__), "static")
app.mount("/", StaticFiles(directory=_static_dir, html=True), name="static")
