"""
缓存服务API演示

展示如何为缓存服务创建真实的HTTP API接口
运行方式：python api_demo.py
然后访问：http://localhost:8000/docs 查看API文档
"""

import os
import sys
import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any

# 添加当前目录到系统路径
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(current_dir)

# 导入缓存服务
from Module.Services.cache_service import CacheService

# 创建FastAPI应用
app = FastAPI(
    title="飞书机器人缓存API",
    description="缓存服务的HTTP API接口",
    version="1.0.0"
)

# 创建缓存服务实例
cache_service = CacheService()

# 数据模型
class UserUpdate(BaseModel):
    user_id: str
    name: str

class EventAdd(BaseModel):
    event_id: str

class ApiResponse(BaseModel):
    success: bool
    data: Optional[Any] = None
    message: Optional[str] = None

# API路由
@app.get("/", response_model=Dict[str, str])
async def root():
    """根路径，返回API信息"""
    return {
        "name": "飞书机器人缓存API",
        "version": "1.0.0",
        "docs": "/docs"
    }

@app.get("/api/cache/status", response_model=ApiResponse)
async def get_cache_status():
    """获取缓存状态"""
    try:
        status = cache_service.get_status()
        return ApiResponse(success=True, data=status)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/cache/clear", response_model=ApiResponse)
async def clear_expired_cache():
    """清理过期缓存"""
    try:
        result = cache_service.clear_expired()
        return ApiResponse(
            success=True,
            data=result,
            message=f"清理完成：用户缓存清理 {result['user_cache_cleared']} 条，事件缓存清理 {result['event_cache_cleared']} 条"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/users/{user_id}", response_model=ApiResponse)
async def get_user(user_id: str):
    """获取用户信息"""
    try:
        name = cache_service.get_user_name(user_id)
        if name is None:
            return ApiResponse(success=False, message="用户不存在")
        return ApiResponse(success=True, data={"user_id": user_id, "name": name})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/users", response_model=ApiResponse)
async def update_user(user_data: UserUpdate):
    """更新用户信息"""
    try:
        cache_service.update_user(user_data.user_id, user_data.name)
        cache_service.save_user_cache()
        return ApiResponse(
            success=True,
            data={"user_id": user_data.user_id, "name": user_data.name},
            message="用户信息已更新"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/events/{event_id}", response_model=ApiResponse)
async def check_event(event_id: str):
    """检查事件是否已处理"""
    try:
        exists = cache_service.check_event(event_id)
        return ApiResponse(
            success=True,
            data={"event_id": event_id, "exists": exists},
            message="事件已处理" if exists else "事件未处理"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/events", response_model=ApiResponse)
async def add_event(event_data: EventAdd):
    """添加已处理事件"""
    try:
        cache_service.add_event(event_data.event_id)
        cache_service.save_event_cache()
        return ApiResponse(
            success=True,
            data={"event_id": event_data.event_id},
            message="事件已记录"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

def main():
    """启动API服务器"""
    print("启动缓存服务API演示...")
    print("API文档: http://localhost:8000/docs")
    print("API状态: http://localhost:8000/api/cache/status")
    print("按 Ctrl+C 停止服务器")

    # 启动服务器
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info"
    )

if __name__ == "__main__":
    # 检查依赖
    try:
        import uvicorn
        import fastapi
        import pydantic
    except ImportError as e:
        print(f"❌ 缺少依赖: {e}")
        print("请安装依赖: pip install fastapi uvicorn")
        sys.exit(1)

    main()