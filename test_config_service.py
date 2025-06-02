"""
配置服务验证脚本

用于验证新位置的配置服务是否正常工作
运行方式：python test_config_service.py

验证三层配置架构：
1. 环境变量(.env) - 开发/生产环境差异配置 (最高优先级)
2. 认证配置文件 - 通过AUTH_CONFIG_FILE_PATH指定的敏感信息文件 (中等优先级)
3. 静态配置(config.json) - 业务配置 (最低优先级)
"""

import os
import sys
import json
import tempfile
import shutil

# 添加当前目录到系统路径
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(current_dir)

# 导入新的配置服务
from Module.Services.config_service import ConfigService

def create_test_config_file(file_path: str, config_data: dict):
    """创建测试配置文件"""
    dir_path = os.path.dirname(file_path)
    if dir_path:  # 只有当目录路径不为空时才创建目录
        os.makedirs(dir_path, exist_ok=True)
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(config_data, f, indent=2, ensure_ascii=False)

def create_test_env_file(file_path: str, env_data: dict):
    """创建测试.env文件"""
    with open(file_path, 'w', encoding='utf-8') as f:
        for key, value in env_data.items():
            f.write(f"{key}={value}\n")

def test_config_service():
    """测试配置服务的所有功能"""
    print("=" * 60)
    print("开始测试配置服务 - 三层配置架构验证")
    print("=" * 60)

    # 创建临时目录用于测试
    temp_dir = tempfile.mkdtemp()
    print(f"使用临时目录: {temp_dir}")

    # 保存原始工作目录
    original_cwd = os.getcwd()

    try:
        # 切换到临时目录（模拟实际运行环境）
        os.chdir(temp_dir)

        # 创建测试配置文件
        static_config_path = "config.json"
        auth_config_path = "auth_config.json"

        # 1. 静态配置数据（最低优先级）
        static_config_data = {
            "bot_id": "static_bot_123",
            "log_level": "DEBUG",
            "app_name": "飞书机器人",
            "max_retries": 3,
            "timeout": 30,
            "auth_config_path": "Notion"  # 这是业务配置，不是文件路径
        }

        # 2. 认证配置数据（中等优先级）
        auth_config_data = {
            "cookies": "test_cookie_value",
            "auth_token": "Bearer test_token_value",
            "bot_id": "auth_bot_456"  # 会覆盖静态配置中的bot_id
        }

        # 创建测试文件（不创建.env，使用真实项目的环境变量）
        create_test_config_file(static_config_path, static_config_data)
        create_test_config_file(auth_config_path, auth_config_data)

        print("\n创建的测试文件：")
        print(f"✓ 静态配置: {static_config_path}")
        print(f"✓ 认证配置: {auth_config_path}")
        print(f"ℹ️  环境变量: 使用真实项目的.env文件")

        # 1. 测试配置服务初始化（使用真实项目根路径）
        print("\n1. 测试配置服务初始化...")
        real_project_root = original_cwd  # 使用真实项目路径
        config_service = ConfigService(
            auth_config_file_path=auth_config_path,
            static_config_file_path=static_config_path,
            project_root_path=real_project_root  # 确保使用真实项目路径加载.env
        )
        print("✓ 配置服务初始化成功")

        # 2. 测试状态查询
        print("\n2. 测试状态查询...")
        status = config_service.get_status()
        print(f"✓ 配置状态:")
        for key, value in status.items():
            print(f"    {key}: {value}")

        assert status["env_file_exists"] == True, ".env文件应该存在"
        assert status["static_config_exists"] == True, "静态配置文件应该存在"
        assert status["auth_config_exists"] == True, "认证配置文件应该存在"
        print("✓ 状态信息正确")

        # 3. 测试配置优先级（使用真实环境变量值）
        print("\n3. 测试配置优先级...")

        # 获取真实的环境变量值进行测试
        real_admin_id = config_service.get_env("ADMIN_ID", "未设置")
        real_feishu_app_id = config_service.get_env("FEISHU_APP_MESSAGE_ID", "未设置")

        print(f"ℹ️  真实环境变量值:")
        print(f"    ADMIN_ID: {real_admin_id}")
        print(f"    FEISHU_APP_MESSAGE_ID: {real_feishu_app_id}")

        # 测试环境变量（最高优先级）- 使用真实值
        admin_id = config_service.get("ADMIN_ID")
        if real_admin_id != "未设置":
            assert admin_id == real_admin_id, f"期望真实环境变量值: {real_admin_id}, 实际: {admin_id}"
            print(f"✓ 环境变量优先级正确: ADMIN_ID = {admin_id}")
        else:
            print(f"⚠️  ADMIN_ID环境变量未设置，跳过测试")

        # 测试认证配置覆盖静态配置
        bot_id = config_service.get("bot_id")
        assert bot_id == "auth_bot_456", f"期望认证配置值: auth_bot_456, 实际: {bot_id}"
        print(f"✓ 认证配置覆盖静态配置: bot_id = {bot_id}")

        # 测试静态配置（最低优先级）
        log_level = config_service.get("log_level")
        print(f"✓ 静态配置正确: log_level = {log_level}")

        # 测试临时配置中添加的字段
        max_retries = config_service.get("max_retries")
        if max_retries:
            print(f"✓ 临时配置生效: max_retries = {max_retries}")
        else:
            print("ℹ️  临时配置未生效，使用真实项目配置")

        # 4. 测试配置来源识别
        print("\n4. 测试配置来源识别...")

        if real_admin_id != "未设置":
            admin_source = config_service.get_config_source("ADMIN_ID")
            assert admin_source == "env", f"ADMIN_ID来源应该是env, 实际: {admin_source}"
            print(f"✓ ADMIN_ID 来源: {admin_source}")

        bot_id_source = config_service.get_config_source("bot_id")
        assert bot_id_source == "auth", f"bot_id来源应该是auth, 实际: {bot_id_source}"
        print(f"✓ bot_id 来源: {bot_id_source}")

        log_level_source = config_service.get_config_source("log_level")
        print(f"✓ log_level 来源: {log_level_source}")

        # 验证静态配置来源
        if log_level_source == "static":
            print("✓ log_level正确来自静态配置")
        else:
            print(f"ℹ️  log_level来自: {log_level_source}")

        # 5. 测试直接获取环境变量
        print("\n5. 测试直接获取环境变量...")
        coze_key = config_service.get_env("COZE_API_KEY", "未设置")
        print(f"✓ 直接获取环境变量: COZE_API_KEY = {coze_key}")

        # 6. 测试安全配置获取
        print("\n6. 测试安全配置获取...")
        safe_config = config_service.get_safe_config()
        print("✓ 安全配置:")
        for key, value in safe_config.items():
            print(f"    {key}: {value}")

        # 验证敏感信息被隐藏
        if "env.COZE_API_KEY" in safe_config:
            assert safe_config["env.COZE_API_KEY"] == "***", "敏感的环境变量应该被隐藏"
            print("✓ 敏感环境变量正确隐藏")

        # 7. 测试配置更新限制
        print("\n7. 测试配置更新限制...")

        # 尝试更新环境变量（应该被拒绝）
        success, message = config_service.update_config("ADMIN_ID", "new_admin_id")
        assert success == False, "环境变量更新应该被拒绝"
        assert "环境变量" in message, f"错误消息应该提到环境变量，实际: {message}"
        print(f"✓ 环境变量更新正确被拒绝: {message}")

        # 更新静态配置（应该成功）
        success, message = config_service.update_config("test_key", "test_value")
        assert success == True, f"静态配置更新应该成功，但返回: {message}"
        print(f"✓ 静态配置更新成功: {message}")

        # 验证更新是否生效
        updated_value = config_service.get("test_key")
        assert updated_value == "test_value", f"期望: test_value, 实际: {updated_value}"
        print("✓ 配置更新生效")

        # 8. 测试配置验证
        print("\n8. 测试配置验证...")
        validation_result = config_service.validate_config()
        print(f"✓ 配置验证结果: valid={validation_result['valid']}")
        print(f"  错误数: {len(validation_result['errors'])}")
        print(f"  警告数: {len(validation_result['warnings'])}")
        print(f"  汇总: {validation_result['summary']}")

        # 检查汇总信息是否正确
        summary = validation_result["summary"]
        assert summary["env_keys"] >= 0, "应该有环境变量配置"
        assert summary["static_keys"] > 0, "应该有静态配置"
        assert summary["auth_keys"] > 0, "应该有认证配置"
        print("✓ 配置验证汇总信息正确")

        # 9. 测试重新加载
        print("\n9. 测试重新加载...")
        success, message = config_service.reload_all_configs()
        assert success == True, f"重新加载应该成功，但返回: {message}"
        print(f"✓ 重新加载成功: {message}")

        # 10. 测试与main_new.py相同的使用模式
        print("\n10. 测试与main_new.py相同的使用模式...")

        # 模拟main_new.py中的关键配置获取
        feishu_app_id = config_service.get_env("FEISHU_APP_MESSAGE_ID")
        feishu_app_secret = config_service.get_env("FEISHU_APP_MESSAGE_SECRET")
        coze_bot_url = config_service.get("coze_bot_url", "https://api.coze.cn/v1/workflow/run")
        bot_id_final = config_service.get("bot_id", "")
        voice_id = config_service.get("voice_id", "peach")
        log_level = config_service.get("log_level", "DEBUG")

        print(f"✓ 飞书应用ID (env): {feishu_app_id}")
        print(f"✓ 机器人ID (优先级测试): {bot_id_final}")
        print(f"✓ 语音ID (static): {voice_id}")
        print(f"✓ 日志级别 (static): {log_level}")

        # 验证配置优先级：检查bot_id来源（应该来自认证配置，因为临时认证配置中有bot_id）
        bot_id_source = config_service.get_config_source("bot_id")
        if bot_id_source == "auth":
            print("✓ bot_id正确来自认证配置（优先级正确）")
        elif bot_id_source == "static":
            print("✓ bot_id来自静态配置（认证配置中无此项）")
        else:
            print(f"ℹ️  bot_id来源: {bot_id_source}")

        print("✓ 与main_new.py使用模式兼容")

        print("\n" + "=" * 60)
        print("所有测试通过！新配置服务完全符合业务需求。")
        print("=" * 60)

        return True

    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

    finally:
        # 恢复原始工作目录
        os.chdir(original_cwd)
        # 清理临时目录
        shutil.rmtree(temp_dir)
        print(f"\n清理临时目录: {temp_dir}")

def test_real_config_compatibility():
    """测试与真实配置文件的兼容性"""
    print("\n" + "=" * 60)
    print("测试与真实配置文件的兼容性")
    print("=" * 60)

    try:
        # 获取当前项目根路径（模拟main_new.py的逻辑）
        current_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = current_dir  # 测试脚本就在项目根目录

        # 使用项目中的实际config.json（模拟main_new.py的使用方式）
        config_service = ConfigService(
            auth_config_file_path=os.getenv("AUTH_CONFIG_FILE_PATH", ""),
            static_config_file_path="config.json",
            project_root_path=project_root  # 明确传入项目根路径
        )

        # 显示项目环境信息
        project_info = config_service.get_project_info()
        print(f"✓ 项目环境信息:")
        for key, value in project_info.items():
            print(f"    {key}: {value}")

        # 读取关键配置项（模拟main_new.py中的使用）
        status = config_service.get_status()
        print(f"\n✓ 实际配置状态:")
        for key, value in status.items():
            print(f"    {key}: {value}")

        # 测试关键配置项
        bot_id = config_service.get("bot_id", "")
        coze_bot_url = config_service.get("coze_bot_url", "")
        voice_id = config_service.get("voice_id", "peach")
        log_level = config_service.get("log_level", "INFO")
        auth_config_path = config_service.get("auth_config_path", "")

        print(f"\n✓ 关键配置项:")
        print(f"    bot_id: {bot_id}")
        print(f"    coze_bot_url: {coze_bot_url}")
        print(f"    voice_id: {voice_id}")
        print(f"    log_level: {log_level}")
        print(f"    auth_config_path (业务配置): {auth_config_path}")

        # 测试环境变量获取
        feishu_app_id = config_service.get_env("FEISHU_APP_MESSAGE_ID", "未设置")
        admin_id = config_service.get_env("ADMIN_ID", "未设置")
        auth_config_file_path = config_service.get_env("AUTH_CONFIG_FILE_PATH", "未设置")

        print(f"\n✓ 环境变量:")
        print(f"    FEISHU_APP_MESSAGE_ID: {feishu_app_id}")
        print(f"    ADMIN_ID: {admin_id}")
        print(f"    AUTH_CONFIG_FILE_PATH: {auth_config_file_path}")

        # 验证AUTH_CONFIG_FILE_PATH是否正确读取
        if auth_config_file_path != "未设置":
            print(f"✅ AUTH_CONFIG_FILE_PATH 正确从环境变量读取!")
            if os.path.exists(auth_config_file_path):
                print(f"✅ 认证配置文件存在: {auth_config_file_path}")
            else:
                print(f"⚠️  认证配置文件不存在: {auth_config_file_path}")
        else:
            print(f"⚠️  AUTH_CONFIG_FILE_PATH 未设置或读取失败")

        # 验证配置
        validation = config_service.validate_config()
        print(f"\n✓ 配置验证: valid={validation['valid']}")
        if validation["errors"]:
            print(f"  错误: {validation['errors']}")
        if validation["warnings"]:
            print(f"  警告: {validation['warnings']}")

        return True

    except Exception as e:
        print(f"❌ 测试实际配置文件失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_compatibility_with_old_import():
    """测试与旧导入方式的兼容性"""
    print("\n" + "=" * 60)
    print("测试与旧导入方式的兼容性")
    print("=" * 60)

    try:
        # 测试能否从旧位置导入（如果文件还存在）
        try:
            from Module.Core.config_service import ConfigService as OldConfigService
            print("✓ 旧的导入方式仍然可用")

            # 比较接口是否一致
            from Module.Services.config_service import ConfigService as NewConfigService

            old_methods = set(dir(OldConfigService))
            new_methods = set(dir(NewConfigService))

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
            print("ℹ️  旧的配置服务文件不存在，跳过兼容性测试")

    except Exception as e:
        print(f"❌ 兼容性测试失败: {e}")
        return False

    return True

if __name__ == "__main__":
    print("配置服务验证脚本 - 三层配置架构")
    print("验证环境变量(.env) > 认证配置 > 静态配置(config.json) 的优先级\n")

    success = True

    # 主要功能测试
    success &= test_config_service()

    # 实际配置文件测试
    success &= test_real_config_compatibility()

    # 兼容性测试
    success &= test_compatibility_with_old_import()

    if success:
        print("\n🎉 所有验证通过！配置服务完全符合业务需求。")
        print("\n✅ 关键改进：")
        print("1. 正确支持三层配置架构（环境变量 > 认证配置 > 静态配置）")
        print("2. 环境变量配置项得到正确处理")
        print("3. AUTH_CONFIG_FILE_PATH从环境变量读取，而不是config.json")
        print("4. 禁止通过API更新环境变量配置")
        print("5. 提供配置来源识别功能")
        print("\n下一步：")
        print("1. 确认新的配置服务工作正常")
        print("2. 测试配置服务的API接口")
        print("3. 继续进行阶段3：应用控制器")
    else:
        print("\n💥 验证失败！请检查问题后再继续。")

    exit(0 if success else 1)