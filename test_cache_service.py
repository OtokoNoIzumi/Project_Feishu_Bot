"""
缓存服务验证脚本

用于验证新位置的缓存服务是否正常工作
运行方式：python test_cache_service.py
"""

import os
import sys
import json
import tempfile
import shutil

# 添加当前目录到系统路径
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(current_dir)

# 导入新的缓存服务
from Module.Services.cache_service import CacheService

def test_cache_service():
    """测试缓存服务的所有功能"""
    print("=" * 50)
    print("开始测试缓存服务")
    print("=" * 50)

    # 创建临时目录用于测试
    temp_dir = tempfile.mkdtemp()
    print(f"使用临时目录: {temp_dir}")

    try:
        # 1. 测试缓存服务初始化
        print("\n1. 测试缓存服务初始化...")
        cache_service = CacheService(temp_dir)
        print("✓ 缓存服务初始化成功")

        # 2. 测试状态查询
        print("\n2. 测试状态查询...")
        status = cache_service.get_status()
        print(f"✓ 缓存状态: {json.dumps(status, indent=2, ensure_ascii=False)}")

        # 3. 测试用户缓存
        print("\n3. 测试用户缓存...")
        test_user_id = "test_user_123"
        test_user_name = "测试用户"

        # 添加用户
        cache_service.update_user(test_user_id, test_user_name)
        print(f"✓ 添加用户: {test_user_name}")

        # 获取用户
        cached_name = cache_service.get_user_name(test_user_id)
        assert cached_name == test_user_name, f"期望: {test_user_name}, 实际: {cached_name}"
        print(f"✓ 获取用户: {cached_name}")

        # 4. 测试事件缓存
        print("\n4. 测试事件缓存...")
        test_event_id = "test_event_456"

        # 检查事件（应该不存在）
        exists_before = cache_service.check_event(test_event_id)
        assert not exists_before, "事件不应该存在"
        print("✓ 事件初始状态正确（不存在）")

        # 添加事件
        cache_service.add_event(test_event_id)
        print(f"✓ 添加事件: {test_event_id}")

        # 检查事件（应该存在）
        exists_after = cache_service.check_event(test_event_id)
        assert exists_after, "事件应该存在"
        print("✓ 事件添加后状态正确（存在）")

        # 5. 测试保存和加载
        print("\n5. 测试保存和加载...")
        cache_service.save_all()
        print("✓ 保存缓存文件")

        # 创建新的缓存服务实例来测试加载
        cache_service2 = CacheService(temp_dir)
        loaded_name = cache_service2.get_user_name(test_user_id)
        assert loaded_name == test_user_name, f"加载的用户名不匹配: {loaded_name}"
        print("✓ 从文件加载缓存成功")

        # 6. 测试清理过期缓存
        print("\n6. 测试清理过期缓存...")
        clear_result = cache_service.clear_expired()
        print(f"✓ 清理结果: {json.dumps(clear_result, ensure_ascii=False)}")

        # 7. 最终状态检查
        print("\n7. 最终状态检查...")
        final_status = cache_service.get_status()
        print(f"✓ 最终状态: {json.dumps(final_status, indent=2, ensure_ascii=False)}")

        print("\n" + "=" * 50)
        print("所有测试通过！缓存服务工作正常。")
        print("=" * 50)

        return True

    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

    finally:
        # 清理临时目录
        shutil.rmtree(temp_dir)
        print(f"\n清理临时目录: {temp_dir}")

def test_compatibility_with_old_import():
    """测试与旧导入方式的兼容性"""
    print("\n" + "=" * 50)
    print("测试与旧导入方式的兼容性")
    print("=" * 50)

    try:
        # 测试能否从旧位置导入（如果文件还存在）
        try:
            from Module.Core.cache_service import CacheService as OldCacheService
            print("✓ 旧的导入方式仍然可用")

            # 比较接口是否一致
            from Module.Services.cache_service import CacheService as NewCacheService

            old_methods = set(dir(OldCacheService))
            new_methods = set(dir(NewCacheService))

            # 检查是否有缺失的方法
            missing_methods = old_methods - new_methods
            if missing_methods:
                print(f"⚠️  新服务缺失方法: {missing_methods}")
            else:
                print("✓ 所有旧方法在新服务中都存在")

            # 检查是否有新增的方法
            new_additions = new_methods - old_methods
            if new_additions:
                print(f"✓ 新服务增加方法: {new_additions}")

        except ImportError:
            print("ℹ️  旧的缓存服务文件不存在，跳过兼容性测试")

    except Exception as e:
        print(f"❌ 兼容性测试失败: {e}")
        return False

    return True

if __name__ == "__main__":
    print("缓存服务验证脚本")
    print("这个脚本会测试新位置的缓存服务是否正常工作\n")

    success = True

    # 主要功能测试
    success &= test_cache_service()

    # 兼容性测试
    success &= test_compatibility_with_old_import()

    if success:
        print("\n🎉 所有验证通过！你可以安全地使用新的缓存服务。")
        print("\n下一步：")
        print("1. 确认新的缓存服务工作正常")
        print("2. 可以开始迁移其他服务")
        print("3. 或者为缓存服务添加FastAPI接口")
    else:
        print("\n💥 验证失败！请检查问题后再继续。")

    exit(0 if success else 1)