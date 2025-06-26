"""
设计方案卡片管理器

专门处理智能家居设计方案咨询相关的飞书卡片
"""

from typing import Dict, Any, List, Optional
from lark_oapi.event.callback.model.p2_card_action_trigger import P2CardActionTriggerResponse
from Module.Services.constants import CardActions, ResponseTypes, CardOperationTypes
from .card_registry import BaseCardManager
from ..decorators import card_build_safe
import qrcode
import json
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont
import os
from Module.Common.scripts.common import debug_utils

class QRCodeGenerator:
    """
    一个独立的、功能更强大的二维码生成器，基于用户提供的代码示例
    """
    def __init__(self):
        self.font_path = self._get_font_path()

    def _get_font_path(self):
        """获取系统字体路径，提供降级方案"""
        try:
            # 优先使用Windows下的微软雅黑
            path = os.path.join(os.environ.get('SystemRoot', 'C:/Windows'), 'Fonts', 'msyh.ttc')
            if os.path.exists(path):
                return path
            # 备选字体
            for font_name in ["simhei.ttf", "simsun.ttc"]:
                fallback_path = os.path.join(os.environ.get('SystemRoot', 'C:/Windows'), 'Fonts', font_name)
                if os.path.exists(fallback_path):
                    return fallback_path
        except Exception:
            pass
        return None

    def _get_optimal_font_size(self, text: str, max_width: int, start_size: int = 28, min_size: int = 20) -> int:
        """根据文字长度动态计算最佳字号"""
        current_size = start_size
        while current_size >= min_size:
            try:
                font = ImageFont.truetype(self.font_path, current_size) if self.font_path else ImageFont.load_default()
                # 使用 textlength 计算宽度，兼容性更好
                text_width = ImageDraw.Draw(Image.new('RGB', (1, 1))).textlength(text, font=font)
                if text_width <= max_width:
                    return current_size
            except Exception:
                # 字体加载失败等问题
                pass
            current_size -= 2
        return min_size

    def _add_text_to_image(self, img: Image, text: str, qr_height: int) -> None:
        """在图片上添加文字说明"""
        draw = ImageDraw.Draw(img)

        # 计算最佳字号并添加文字
        optimal_size = self._get_optimal_font_size(text, max_width=img.width - 20)
        font = ImageFont.truetype(self.font_path, optimal_size) if self.font_path else ImageFont.load_default()

        text_width = draw.textlength(text, font=font)
        # 文本位置微调，使其更美观
        text_position = ((img.width - text_width) / 2, qr_height + 15)
        draw.text(text_position, text, font=font, fill="black")
    @card_build_safe("生成二维码图片失败")
    def generate(self, data_to_encode: str, customer_name: str) -> Optional[Image.Image]:
        """
        生成带有文字说明的二维码图片

        Args:
            data_to_encode: 要编码到二维码中的字符串 (JSON格式)
            customer_name: 用于显示在二维码下方的客户姓名

        Returns:
            PIL.Image: 生成的图片对象, 或在失败时返回None
        """
        # 1. 生成基础二维码
        qr = qrcode.QRCode(version=1, box_size=10, border=4, error_correction=qrcode.constants.ERROR_CORRECT_L)
        qr.add_data(data_to_encode)
        qr.make(fit=True)
        qr_img = qr.make_image(fill_color="black", back_color="white").convert('RGB')
        qr_width, qr_height = qr_img.size

        # 2. 创建用于粘贴二维码和文字的最终画布
        text_area_height = 60
        final_img = Image.new('RGB', (qr_width, qr_height + text_area_height), color='white')
        final_img.paste(qr_img, (0, 0))

        # 3. 在图片下方添加说明文字
        text_to_add = f"尊敬的{customer_name}，扫码打开您专属的方案"
        self._add_text_to_image(final_img, text_to_add, qr_height)

        return final_img


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
                "card_action": "confirm_design_plan",
                "process_result_type": ResponseTypes.DESIGN_PLAN_SUBMIT,
                "operation_id": operation_id,
                "raw_card_data": raw_card_data  # 存储完整的数据对象
            },
            "cancel_action": {
                **base_action_value,
                "card_action": "cancel_design_plan",
                "process_result_type": ResponseTypes.DESIGN_PLAN_CANCEL,
                "operation_id": operation_id,
                "raw_card_data": raw_card_data  # 存储完整的数据对象
            }
        }

    @card_build_safe("设计方案确认卡片构建失败")
    def build_card(self, design_plan_data: Dict[str, Any]) -> Dict[str, Any]:
        """构建设计方案确认卡片内容"""
        template_params = self._format_design_plan_params(design_plan_data)
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

    def handle_design_plan_submit(self, raw_card_data: Dict[str, Any], context_info: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理设计方案提交确认 - 完整的业务逻辑处理
        使用全新的QRCodeGenerator生成二维码，并将结果以项目标准格式返回

        Args:
            raw_card_data: 原始卡片数据
            context_info: 上下文信息
        """
        try:
            customer_name = raw_card_data.get('customer_name', '客户')
            user_name = context_info.get('user_name', '未知用户')

            # 1. 构建要编码到二维码中的数据
            plan_data = self._build_plan_data_for_qrcode(raw_card_data)
            final_str_to_encode = json.dumps(plan_data, ensure_ascii=False, indent=2)

            # 2. 使用新的生成器创建二维码图片
            qr_generator = QRCodeGenerator()
            final_img = qr_generator.generate(final_str_to_encode, customer_name)

            if not final_img:
                raise ValueError("二维码图片生成失败，返回对象为None")

            # 3. 将图片转换为bytes，以便适配器层处理
            img_buffer = BytesIO()
            final_img.save(img_buffer, format='PNG')
            image_bytes = img_buffer.getvalue()

            debug_utils.log_and_print(f"🏠 设计方案提交成功，客户: {customer_name}, 操作用户: {user_name}")
            return {
                "success": True,
                "type": ResponseTypes.IMAGE,
                "data": {"image_data": image_bytes},
                "log_info": {
                    "user_name": user_name, "emoji": "🏠",
                    "action": "设计方案提交成功", "details": f"客户: {customer_name}"
                }
            }
        except Exception as e:
            debug_utils.log_and_print(f"❌ 设计方案提交处理失败: {e}", exc_info=True)
            customer_name = raw_card_data.get('customer_name', '客户')
            user_name = context_info.get('user_name', '未知用户')
            return {
                "success": True, "type": ResponseTypes.TEXT,
                "data": {"text": f"✅ 设计方案提交成功！\n\n尊敬的{customer_name}，您的专属方案已生成。\n\n💡 但在生成专属二维码时遇到问题，请联系客服获取详情。"},
                "log_info": {
                    "user_name": user_name, "emoji": "🏠",
                    "action": "设计方案提交异常", "details": f"客户: {customer_name}, 错误: {str(e)}"
                }
            }

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

    def _handle_design_plan_action_execute(self, action_data: Dict[str, Any], feishu_data) -> Any:
        """
        设计方案动作执行处理 - 供CardHandler调用的统一入口

        Args:
            action_data: 业务层传递的动作数据
            feishu_data: 飞书数据

        Returns:
            P2CardActionTriggerResponse: 动作响应
        """
        try:
            card_action = action_data.get("card_action")
            action_value = action_data.get("action_value", {})

            match card_action:
                case "confirm_design_plan":
                    # 入口1：生成二维码并更新卡片
                    result = self.process_design_plan_request(action_data)

                    if result.get("success") and result["type"] == ResponseTypes.IMAGE:
                        # 发送二维码图片
                        image_data = result["data"].get("image_data")
                        if image_data:
                            self.sender.upload_and_send_single_image_data(feishu_data, image_data)

                        # 更新卡片状态
                        raw_card_data = action_value.get('raw_card_data', {})
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
                    else:
                        return P2CardActionTriggerResponse({
                            "toast": {
                                "type": "error",
                                "content": "设计方案更新失败"
                            }
                        })

                case "cancel_design_plan":
                    # 入口2：更新卡片状态
                    raw_card_data = action_value.get('raw_card_data', {})
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

                case _:
                    debug_utils.log_and_print(f"未知的设计方案动作: {card_action}")
                    return P2CardActionTriggerResponse({
                        "toast": {
                            "type": "error",
                            "content": f"未知的设计方案动作: {card_action}"
                        }
                    })

        except Exception as e:
            debug_utils.log_and_print(f"设计方案动作执行失败: {e}", exc_info=True)
            return P2CardActionTriggerResponse({
                "toast": {
                    "type": "error",
                    "content": "设计方案处理失败"
                }
            })

    def process_design_plan_request(self, action_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        设计方案动作处理入口，仅处理handle_action

        Args:
            action_data: 动作数据

        Returns:
            Dict: 处理结果
        """
        try:
            card_action = action_data.get("card_action")
            action_value = action_data.get("action_value", {})
            context_info = action_data.get("context_info", {})

            if card_action == "confirm_design_plan":
                raw_card_data = action_value.get('raw_card_data', {})
                return self.handle_design_plan_submit(raw_card_data, context_info)
            else:
                debug_utils.log_and_print(f"未知的设计方案动作: {card_action}")
                return {
                    "success": False,
                    "error": f"未知的设计方案动作: {card_action}"
                }
        except Exception as e:
            debug_utils.log_and_print(f"设计方案处理失败: {e}", exc_info=True)
            return {
                "success": False,
                "error": f"处理失败: {str(e)}"
            }
