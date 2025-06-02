"""
配置服务API演示

展示如何为配置服务创建真实的HTTP API接口
运行方式：python config_api_demo.py
然后访问：http://localhost:8001/docs 查看API文档
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

# 导入配置服务
from Module.Services.config_service import ConfigService

# 创建FastAPI应用
app = FastAPI(
    title="飞书机器人配置API",
    description="配置服务的HTTP API接口",
    version="1.0.0"
)

# 创建配置服务实例
config_service = ConfigService(static_config_file_path="config.json")

# 数据模型
class ConfigUpdate(BaseModel):
    key: str
    value: str

class ApiResponse(BaseModel):
    success: bool
    data: Optional[Any] = None
    message: Optional[str] = None

# API路由
@app.get("/", response_model=Dict[str, str])
async def root():
    """根路径，返回API信息"""
    return {
        "name": "飞书机器人配置API",
        "version": "1.0.0",
        "docs": "/docs"
    }

@app.get("/api/config/status", response_model=ApiResponse)
async def get_config_status():
    """获取配置服务状态"""
    try:
        status = config_service.get_status()
        return ApiResponse(success=True, data=status)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/config/validate", response_model=ApiResponse)
async def validate_config():
    """验证配置完整性"""
    try:
        validation = config_service.validate_config()
        return ApiResponse(
            success=validation["valid"],
            data=validation,
            message="配置验证完成"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/config/safe", response_model=ApiResponse)
async def get_safe_config():
    """获取安全配置（隐藏敏感信息）"""
    try:
        safe_config = config_service.get_safe_config()
        return ApiResponse(success=True, data=safe_config)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/config/key/{key}", response_model=ApiResponse)
async def get_config_key(key: str, default_value: Optional[str] = None):
    """获取指定配置项"""
    try:
        value = config_service.get(key, default_value)
        return ApiResponse(
            success=True,
            data={"key": key, "value": value},
            message=f"获取配置项 '{key}'"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/config/update", response_model=ApiResponse)
async def update_config(config_data: ConfigUpdate):
    """更新配置项"""
    try:
        success, message = config_service.update_config(config_data.key, config_data.value)
        if success:
            return ApiResponse(
                success=True,
                data={"key": config_data.key, "value": config_data.value},
                message=message
            )
        else:
            return ApiResponse(success=False, message=message)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/config/reload", response_model=ApiResponse)
async def reload_config():
    """重新加载所有配置文件"""
    try:
        success, message = config_service.reload_all_configs()
        if success:
            return ApiResponse(success=True, message=message)
        else:
            return ApiResponse(success=False, message=message)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/config/keys", response_model=ApiResponse)
async def list_config_keys():
    """列出所有配置键"""
    try:
        status = config_service.get_status()
        all_keys = set(status["static_config_keys"] + status["auth_config_keys"])
        return ApiResponse(
            success=True,
            data={
                "all_keys": sorted(list(all_keys)),
                "static_keys": status["static_config_keys"],
                "auth_keys": status["auth_config_keys"],
                "total_count": len(all_keys)
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

def main():
    """启动API服务器"""
    print("启动配置服务API演示...")
    print("API文档: http://localhost:8001/docs")
    print("配置状态: http://localhost:8001/api/config/status")
    print("安全配置: http://localhost:8001/api/config/safe")
    print("按 Ctrl+C 停止服务器")

    # 启动服务器
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8001,  # 使用不同的端口避免与缓存API冲突
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