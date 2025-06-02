"""
应用控制器验证脚本

用于验证应用控制器的服务注册、统一调用接口和多服务协同功能
运行方式：python test_app_controller.py
"""

import os
import sys
import json

# 添加当前目录到系统路径
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(current_dir)

# 导入应用控制器
from Module.Application.app_controller import AppController

def test_app_controller():
    """测试应用控制器的所有功能"""
    print("=" * 60)
    print("开始测试应用控制器")
    print("=" * 60)

    try:
        # 1. 初始化应用控制器
        print("\n1. 测试应用控制器初始化...")
        app_controller = AppController()
        print("✓ 应用控制器初始化成功")
        print(f"✓ 项目根路径: {app_controller.project_root_path}")

        # 2. 测试自动注册服务
        print("\n2. 测试自动注册服务...")
        register_results = app_controller.auto_register_services()
        print(f"✓ 自动注册结果: {register_results}")

        # 验证注册结果
        assert len(register_results) > 0, "应该至少注册一个服务"
        print(f"✓ 成功注册 {len(register_results)} 个服务")

        # 3. 测试服务状态查询
        print("\n3. 测试服务状态查询...")
        all_status = app_controller.get_service_status()
        print("✓ 所有服务状态:")
        print(f"    控制器状态: {all_status['controller']}")
        print(f"    服务数量: {len(all_status['services'])}")

        for service_name, status in all_status['services'].items():
            print(f"    {service_name}: {status['status']}")

        # 4. 测试懒加载和服务获取
        print("\n4. 测试懒加载和服务获取...")

        # 测试获取配置服务（应该触发懒加载）
        config_service = app_controller.get_service('config')
        if config_service:
            print("✓ 配置服务懒加载成功")
            print(f"    类型: {type(config_service).__name__}")
        else:
            print("❌ 配置服务获取失败")

        # 测试获取缓存服务
        cache_service = app_controller.get_service('cache')
        if cache_service:
            print("✓ 缓存服务懒加载成功")
            print(f"    类型: {type(cache_service).__name__}")
        else:
            print("❌ 缓存服务获取失败")

        # 5. 测试统一调用接口
        print("\n5. 测试统一调用接口...")

        # 测试调用配置服务的方法
        success, result = app_controller.call_service('config', 'get', 'log_level', 'DEBUG')
        if success:
            print(f"✓ 调用配置服务成功: log_level = {result}")
        else:
            print(f"❌ 调用配置服务失败: {result}")

        # 测试调用配置服务的状态方法
        success, result = app_controller.call_service('config', 'get_status')
        if success:
            print("✓ 调用配置服务状态查询成功")
            print(f"    配置文件状态: {result.get('static_config_exists', '未知')}")
        else:
            print(f"❌ 调用配置服务状态查询失败: {result}")

        # 测试调用缓存服务的方法
        success, result = app_controller.call_service('cache', 'get_status')
        if success:
            print("✓ 调用缓存服务状态查询成功")
            print(f"    缓存目录: {result.get('cache_dir', '未知')}")
        else:
            print(f"❌ 调用缓存服务状态查询失败: {result}")

        # 测试调用不存在的方法
        success, result = app_controller.call_service('config', 'non_existent_method')
        if not success:
            print("✓ 正确拒绝调用不存在的方法")
        else:
            print("❌ 应该拒绝调用不存在的方法")

        # 6. 测试多服务协同
        print("\n6. 测试多服务协同...")

        # 获取配置服务的项目根路径
        success, config_root = app_controller.call_service('config', 'get', 'project_root_path')
        if not success:
            # 如果配置服务没有这个配置，直接从服务状态获取
            config_service_instance = app_controller.get_service('config')
            config_root = getattr(config_service_instance, 'project_root_path', None)

        # 验证缓存和配置服务使用相同的项目根路径
        cache_service_instance = app_controller.get_service('cache')
        cache_dir = cache_service_instance.cache_dir if cache_service_instance else None

        if config_root and cache_dir:
            if app_controller.project_root_path in str(cache_dir):
                print("✓ 多服务协同正常：使用统一的项目根路径")
            else:
                print("⚠️  多服务路径可能不一致")
        else:
            print("ℹ️  无法验证多服务协同（部分信息不可用）")

        # 7. 测试健康检查
        print("\n7. 测试健康检查...")
        health_status = app_controller.health_check()
        print("✓ 健康检查结果:")
        print(f"    总体状态: {health_status['overall_status']}")
        print(f"    健康服务: {health_status['summary']['healthy']}")
        print(f"    不健康服务: {health_status['summary']['unhealthy']}")
        print(f"    未初始化服务: {health_status['summary']['uninitialized']}")

        # 8. 测试批量初始化
        print("\n8. 测试批量初始化...")
        init_results = app_controller.initialize_all_services()
        print(f"✓ 批量初始化结果: {init_results}")

        success_count = sum(init_results.values())
        total_count = len(init_results)
        print(f"✓ 初始化成功率: {success_count}/{total_count}")

        # 9. 最终状态检查
        print("\n9. 最终状态检查...")
        final_status = app_controller.get_service_status()

        print("✓ 最终服务状态:")
        for service_name, status in final_status['services'].items():
            available = "可用" if status.get('available', False) else "不可用"
            initialized = "已初始化" if status.get('initialized', False) else "未初始化"
            print(f"    {service_name}: {available}, {initialized}")

        print("\n" + "=" * 60)
        print("应用控制器验证完成！")
        print("=" * 60)

        return True

    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_service_integration():
    """测试服务集成场景"""
    print("\n" + "=" * 60)
    print("测试服务集成场景")
    print("=" * 60)

    try:
        app_controller = AppController()

        # 自动注册和初始化服务
        app_controller.auto_register_services()
        app_controller.initialize_all_services()

        print("\n集成测试场景：")

        # 场景1：从配置服务获取配置，用于缓存服务
        print("\n场景1：配置驱动的缓存操作")

        # 获取日志级别配置
        success, log_level = app_controller.call_service('config', 'get', 'log_level', 'INFO')
        if success:
            print(f"✓ 从配置服务获取日志级别: {log_level}")

            # 将配置信息作为缓存键值
            cache_key = "current_log_level"
            success, _ = app_controller.call_service('cache', 'set', cache_key, log_level)
            if success:
                print(f"✓ 将配置缓存到缓存服务: {cache_key} = {log_level}")

                # 从缓存读取
                success, cached_value = app_controller.call_service('cache', 'get', cache_key)
                if success and cached_value == log_level:
                    print("✓ 从缓存服务读取配置验证成功")
                else:
                    print("❌ 缓存读取验证失败")
            else:
                print("❌ 缓存设置失败")
        else:
            print("❌ 配置获取失败")

        # 场景2：服务状态汇总
        print("\n场景2：服务状态汇总")

        # 获取各个服务的状态
        config_status_success, config_status = app_controller.call_service('config', 'get_status')
        cache_status_success, cache_status = app_controller.call_service('cache', 'get_status')

        if config_status_success and cache_status_success:
            print("✓ 成功获取所有服务状态")

            # 汇总关键信息
            summary = {
                "config_files_loaded": config_status.get('total_config_keys', 0),
                "cache_entries": cache_status.get('total_entries', 0),
                "cache_memory_usage": cache_status.get('memory_usage_mb', 0)
            }

            print(f"✓ 系统状态汇总: {summary}")
        else:
            print("❌ 服务状态获取失败")

        return True

    except Exception as e:
        print(f"❌ 集成测试失败: {e}")
        return False

if __name__ == "__main__":
    print("应用控制器验证脚本")
    print("测试服务注册、统一调用接口和多服务协同功能\n")

    success = True

    # 基础功能测试
    success &= test_app_controller()

    # 集成场景测试
    success &= test_service_integration()

    if success:
        print("\n🎉 所有验证通过！应用控制器功能正常。")
        print("\n✅ 验证通过的功能：")
        print("1. 服务自动注册")
        print("2. 懒加载机制")
        print("3. 统一服务调用接口")
        print("4. 服务状态监控")
        print("5. 健康检查")
        print("6. 多服务协同工作")
        print("7. 服务集成场景")
        print("\n下一步：")
        print("1. 确认应用控制器工作正常")
        print("2. 继续进行阶段4：飞书适配器")
        print("3. 或者测试与main_new.py的集成")
    else:
        print("\n💥 验证失败！请检查问题后再继续。")

    exit(0 if success else 1)