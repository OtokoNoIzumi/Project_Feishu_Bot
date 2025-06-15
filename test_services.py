#!/usr/bin/env python3
"""
临时测试脚本 - 检查服务初始化状态
"""

from Module.Application.app_controller import AppController

def test_services():
    print("=== 服务初始化测试 ===")

    # 创建应用控制器
    app = AppController()

    # 自动注册服务
    print("1. 注册服务...")
    register_results = app.auto_register_services()
    print(f"注册结果: {register_results}")

    # 初始化所有服务
    print("\n2. 初始化服务...")
    init_results = app.initialize_all_services()
    print(f"初始化结果: {init_results}")

    # 检查关键服务状态
    print("\n3. 检查服务状态...")
    for service_name in ['config', 'llm', 'router']:
        service = app.get_service(service_name)
        print(f"\n{service_name}服务:")
        print(f"  - 实例: {service}")

        if service:
            # 检查是否有is_available方法
            if hasattr(service, 'is_available'):
                try:
                    available = service.is_available()
                    print(f"  - 可用性: {available}")
                except Exception as e:
                    print(f"  - 可用性检查失败: {e}")

            # 检查是否有get_status方法
            if hasattr(service, 'get_status'):
                try:
                    status = service.get_status()
                    print(f"  - 状态: {status}")
                except Exception as e:
                    print(f"  - 状态检查失败: {e}")

    # 测试RouterService的LLM依赖
    print("\n4. 测试RouterService的LLM依赖...")
    router_service = app.get_service('router')
    if router_service:
        print(f"RouterService.llm_service: {router_service.llm_service}")
        if router_service.llm_service:
            print(f"LLM服务可用性: {router_service.llm_service.is_available()}")
        else:
            print("❌ RouterService没有获取到LLM服务!")

if __name__ == "__main__":
    test_services()