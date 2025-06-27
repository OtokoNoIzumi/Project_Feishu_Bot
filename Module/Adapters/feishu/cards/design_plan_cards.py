"""
设计方案卡片管理器

专门处理智能家居设计方案咨询相关的飞书卡片
"""

from typing import Dict, Any
import json
from io import BytesIO
from lark_oapi.event.callback.model.p2_card_action_trigger import P2CardActionTriggerResponse
from Module.Services.constants import ResponseTypes, CardOperationTypes, DesignPlanConstants
from Module.Common.scripts.common import debug_utils
from Module.Business.processors import ProcessResult, MessageContext_Refactor
from .card_registry import BaseCardManager
from ..decorators import card_build_safe


class DesignPlanCardManager(BaseCardManager):
    """设计方案卡片管理器"""

    def get_interaction_components(self, operation_id: str, raw_card_data: Dict[str, Any]) -> Dict[str, Any]:
        """获取交互组件 - 生成确认和取消动作数据"""

        # ✅ card_config_key是路由必需信息，必须注入
        base_action_value = {
            "card_config_key": self.card_config_key  # ✅ MessageProcessor路由需要
        }

        return {
            "confirm_action": {
                **base_action_value,
                "card_action": "submit_design_plan",
                "process_result_type": ResponseTypes.DESIGN_PLAN_SUBMIT,
                "operation_id": operation_id,
                "raw_card_data": raw_card_data  # 存储完整的数据对象
            },
            "cancel_action": {
                **base_action_value,
                "card_action": "stop_modify_plan",
                "process_result_type": ResponseTypes.DESIGN_PLAN_CANCEL,
                "operation_id": operation_id,
                "raw_card_data": raw_card_data  # 存储完整的数据对象
            }
        }

    @card_build_safe("设计方案确认卡片构建失败")
    def build_card(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """构建设计方案确认卡片内容"""
        template_params = self._format_design_plan_params(data)
        return self._build_template_content(template_params)

    @card_build_safe("格式化设计方案参数失败")
    def _format_design_plan_params(self, card_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        格式化设计方案参数 - 处理扁平化的数据结构
        """
        # 直接从扁平化的card_data获取信息
        operation_id = card_data.get('operation_id', '')
        content = card_data.get('content', '')
        finished = card_data.get('finished', False)
        result = card_data.get('result', '')

        # 直接从card_data获取参数，不再进行嵌套解析
        custom_name = card_data.get('customer_name', '')
        custom_contact = card_data.get('phone_number', '')
        address = card_data.get('address', '')
        address_house_detail = card_data.get('address_detail', '')

        # --- 精确映射，不再进行模糊匹配，同时支持数字字符串和中文 ---
        ecosystem_mapping = {"小米": 1, "苹果": 2, "华为": 3}
        package_mapping = {"基础套餐": 1, "专业套餐": 2, "旗舰套餐": 3}
        room_type_mapping = {"两室两厅": 1, "三室两厅": 2, "四室两厅": 3, "别墅": 4}
        install_type_mapping = {"DIY自行安装": 1, "专业智能设计及落地": 2, "智能照明设计及落地": 3, "人车家生态设计及落地": 4}
        service_type_mapping = {"基础产品保障": 1, "放心保（一年）": 2, "放心保（二年）": 3, "放心保（五年）": 4}
        room_status_mapping = {"前装": 1, "后装": 2}

        # 反向映射，支持数字字符串直接传入
        def get_mapping_value(mapping: dict, value):
            """
            支持两种结构：
            1. 传入中文，如"小米"
            2. 传入数字字符串，如"1"
            """
            if value in mapping:
                return mapping[value]
            # 支持数字字符串直接传入
            try:
                int_value = int(value)
                # 检查该数字是否在映射值中
                if int_value in mapping.values():
                    return int_value
            except (ValueError, TypeError):
                pass
            return None

        select_fields = {}

        brand_type = card_data.get('brand_type')
        brand_type_val = get_mapping_value(ecosystem_mapping, brand_type)
        if brand_type_val is not None:
            select_fields["brand_type_select"] = brand_type_val

        set_type = card_data.get('set_type')
        set_type_val = get_mapping_value(package_mapping, set_type)
        if set_type_val is not None:
            select_fields["set_type_select"] = set_type_val

        room_type = card_data.get('room_type')
        room_type_val = get_mapping_value(room_type_mapping, room_type)
        if room_type_val is not None:
            select_fields["room_type_select"] = room_type_val

        install_type = card_data.get('install_type')
        install_type_val = get_mapping_value(install_type_mapping, install_type)
        if install_type_val is not None:
            select_fields["install_type_select"] = install_type_val

        service_type = card_data.get('service_type')
        service_type_val = get_mapping_value(service_type_mapping, service_type)
        if service_type_val is not None:
            select_fields["service_type_select"] = service_type_val

        room_status = card_data.get('room_status')
        room_status_val = get_mapping_value(room_status_mapping, room_status)
        if room_status_val is not None:
            select_fields["room_status_type_select"] = room_status_val

        # 获取交互组件 - 传入完整的card_data作为raw_card_data
        interaction_components = self.get_interaction_components(operation_id, card_data)

        result = {
            # 基本信息显示
            "admin_input": content,
            # 卡片模板必需参数
            "result": result,
            "finished": finished,
            # 表单预填值
            "custom_name": custom_name,
            "custom_contact": custom_contact,
            "address": address,
            "address_house_detail": address_house_detail,
            # 交互组件
            "confirm_action_data": interaction_components["confirm_action"],
            "cancel_action_data": interaction_components["cancel_action"],
            # 额外功能（暂时为空）
            "extra_functions": []
        }
        # 合并select字段
        result.update(select_fields)
        return result

    def handle_send_confirm_card(
        self, result: ProcessResult, context: MessageContext_Refactor
    ) -> P2CardActionTriggerResponse:
        """
        处理发送设计方案确认卡片动作
        """
        new_card_data = result.response_content
        new_card_data['result'] = '| 待检查⏰'
        return self._handle_card_operation_common(
            card_content=self.build_card(new_card_data),
            card_operation_type=CardOperationTypes.SEND,
            update_toast_type='success',
            message_id=context.message_id
        )

    def handle_submit_design_plan(self, context: MessageContext_Refactor) -> P2CardActionTriggerResponse:
        """
        处理设计方案提交 - 完整的业务逻辑处理
        通过ImageService生成带有客户信息的专属二维码，符合分层架构规范
        """
        # 从MessageContext_Refactor提取数据
        raw_card_data = context.content.value.get('raw_card_data', {})

        if context.content.form_data:
            # 使用DesignPlanConstants中的映射关系
            reverse_field_map = {v: k for k, v in DesignPlanConstants.FORM_FIELD_MAP.items()}
            for key, value in context.content.form_data.items():
                form_key = reverse_field_map.get(key)
                if form_key:
                    raw_card_data[form_key] = value

        customer_name = raw_card_data.get('customer_name', '客户')
        user_name = context.user_name

        # 1. 构建要编码到二维码中的数据
        plan_data = self._build_plan_data_for_qrcode(raw_card_data)
        final_str_to_encode = json.dumps(plan_data, ensure_ascii=False, indent=2)

        # 2. 通过ImageService生成二维码图片——这可以视作一个process，也可以在adapter层安全的直接引用，只要业务不耦合
        image_service = self.app_controller.get_service('image')
        final_img = image_service.generate_design_plan_qrcode(final_str_to_encode, customer_name)

        # 3. 将图片转换为bytes，以便适配器层处理
        img_buffer = BytesIO()
        final_img.save(img_buffer, format='PNG')
        image_bytes = img_buffer.getvalue()

        debug_utils.log_and_print(f"🏠 设计方案提交成功，客户: {customer_name}, 操作用户: {user_name}")

        # 4. 发送二维码图片给用户
        self.sender.send_image_with_context(context, image_bytes)

        # 5. 更新卡片状态
        new_card_data = {
            **raw_card_data,
            'result': " | 已提交检查"
        }

        # 使用基类的通用卡片操作方法
        return self._handle_card_operation_common(
            card_content=self.build_card(new_card_data),
            card_operation_type=CardOperationTypes.UPDATE_RESPONSE,
            update_toast_type='success',
            toast_message="已提交设计方案"
        )

    def handle_stop_modify_plan(self, context: MessageContext_Refactor) -> P2CardActionTriggerResponse:
        """
        处理停止修改设计方案动作
        """
        raw_card_data = context.content.value.get('raw_card_data', {})
        new_card_data = {
            **raw_card_data,
            'finished': True,
            'result': " | 结束检查"
        }

        # 使用基类的通用卡片操作方法
        return self._handle_card_operation_common(
            card_content=self.build_card(new_card_data),
            card_operation_type=CardOperationTypes.UPDATE_RESPONSE,
            update_toast_type='info',
            toast_message="已结束对设计方案的检查"
        )

    def _build_plan_data_for_qrcode(self, raw_card_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        构建设计方案数据字典

        注意：raw_card_data的字段名必须和下方映射的key严格对应，否则会导致plan_data内容为空或格式不正确。
        常见问题：
        - 字段名不一致（如address_detail和房间信息、brand_type和智能生态等）
        - 字段值为None或空字符串，导致映射失败
        """

        # 映射表
        room_type_value_map = {
            "1": "两房两厅",
            "2": "三房两厅",
            "3": "四房两厅",
            "4": "别墅"
        }
        brand_type_value_map = {
            "1": "🔶小米",
            "2": "💿苹果",
            "3": "🟥华为"
        }
        set_type_value_map = {
            "1": "基础",
            "2": "专业",
            "3": "旗舰"
        }
        install_type_value_map = {
            "1": "DIY自行安装",
            "2": "专业智能设计及落地",
            "3": "智能照明设计及落地",
            "4": "人车家生态设计及落地"
        }
        service_type_value_map = {
            "1": "基础产品保障",
            "2": "放心保（一年）",
            "3": "放心保（二年）",
            "4": "放心保（五年）"
        }
        room_status_value_map = {
            "2": "后装",
            "1": "前装"
        }

        # 直接使用扁平化的raw_card_data
        params = raw_card_data

        # 获取选择项的值（不是索引），注意参数名要和AI意图识别输出一致
        room_type_value = room_type_value_map.get(str(params.get('room_type', '2')), '三房两厅')
        brand_type_value = brand_type_value_map.get(str(params.get('brand_type', '1')), '🔶小米')
        set_type_value = set_type_value_map.get(str(params.get('set_type', '1')), '基础')
        install_type_value = install_type_value_map.get(str(params.get('install_type', '2')), '专业智能设计及落地')
        service_type_value = service_type_value_map.get(str(params.get('service_type', '3')), '放心保（二年）')
        room_status_value = room_status_value_map.get(str(params.get('room_status', '1')), '前装')

        # 构建完整的方案数据
        plan_data = {
            "设计方案信息": {
                "客户姓名": params.get('customer_name', ''),
                "联系电话": params.get('phone_number', ''),
                "地址": params.get('address', ''),
                "房间信息": params.get('address_detail', ''),
                "房型": room_type_value,
                "智能生态": brand_type_value,
                "套餐类型": set_type_value,
                "安装方式": install_type_value,
                "保障服务": service_type_value,
                "装修状态": room_status_value
            },
            "生成时间": __import__('datetime').datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

        return plan_data
