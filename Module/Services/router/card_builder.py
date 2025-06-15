"""
卡片构建器 - 生成意图识别后的确认和编辑卡片

提供高效的编辑交互界面
"""

from typing import Dict, Any, List
from datetime import datetime


class CardBuilder:
    """
    卡片构建器 - 生成飞书交互卡片
    """

    def __init__(self):
        """初始化卡片构建器"""
        pass

    def build_intent_confirmation_card(self, route_result: Dict[str, Any]) -> Dict[str, Any]:
        """
        构建意图识别确认卡片

        Args:
            route_result: 路由结果

        Returns:
            Dict[str, Any]: 飞书卡片JSON
        """
        intent = route_result.get('intent', '未知')
        confidence = route_result.get('confidence', 0)
        content = route_result.get('content', '')
        route_type = route_result.get('route_type', 'unknown')

        # 根据意图类型构建不同的卡片
        if intent == "记录思考":
            return self._build_thought_record_card(route_result)
        elif intent == "记录日程":
            return self._build_schedule_record_card(route_result)
        elif intent == "点餐":
            return self._build_food_order_card(route_result)
        else:
            return self._build_unknown_intent_card(route_result)

    def _build_thought_record_card(self, route_result: Dict[str, Any]) -> Dict[str, Any]:
        """构建思考记录确认卡片"""
        content = route_result.get('content', '')
        confidence = route_result.get('confidence', 0)
        route_type = route_result.get('route_type', 'unknown')
        parameters = route_result.get('parameters', {})

        # 获取建议的标签（新格式：字符串列表）
        suggested_tags = parameters.get('suggested_tags', [])
        category = parameters.get('category', '')

        # 构建标签选择元素
        tag_elements = []
        if suggested_tags and isinstance(suggested_tags, list):
            tag_options = []

            # 处理建议标签（最多显示3个）
            for i, tag in enumerate(suggested_tags[:3]):
                if isinstance(tag, str):
                    tag_options.append({
                        "text": {
                            "tag": "plain_text",
                            "content": f"{tag}"
                        },
                        "value": tag
                    })

            # 如果标签少于3个，添加一些通用备选标签
            if len(tag_options) < 3:
                backup_tags = ["学习", "工作", "生活", "想法"]
                for backup_tag in backup_tags:
                    if backup_tag not in suggested_tags and len(tag_options) < 3:
                        tag_options.append({
                            "text": {
                                "tag": "plain_text",
                                "content": f"{backup_tag} (备选)"
                            },
                            "value": backup_tag
                        })

            if tag_options:
                tag_elements.append({
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": "**标签选择：**"
                    }
                })

                tag_elements.append({
                    "tag": "action",
                    "layout": "flow",
                    "actions": [
                        {
                            "tag": "select_static",
                            "placeholder": {
                                "tag": "plain_text",
                                "content": "选择标签"
                            },
                            "options": tag_options,
                            "value": {
                                "action": "select_tag",
                                "intent": "记录思考"
                            }
                        }
                    ]
                })

        # 构建内容显示
        content_display = f"**内容：** {content}"
        if category:
            content_display += f"\n**分类：** {category}"

        card = {
            "config": {
                "wide_screen_mode": True
            },
            "header": {
                "template": "blue",
                "title": {
                    "tag": "plain_text",
                    "content": "📝 AI识别结果 - 记录思考"
                }
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"**识别方式：** {'快捷指令' if route_type == 'shortcut' else 'AI识别'} | **置信度：** {confidence}%"
                    }
                },
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": content_display
                    }
                },
                {
                    "tag": "hr"
                }
            ] + tag_elements + [
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": "**自定义标签：**"
                    }
                },
                {
                    "tag": "action",
                    "layout": "flow",
                    "actions": [
                        {
                            "tag": "input",
                            "name": "custom_tag",
                            "placeholder": {
                                "tag": "plain_text",
                                "content": "输入自定义标签"
                            }
                        }
                    ]
                },
                {
                    "tag": "hr"
                },
                {
                    "tag": "action",
                    "layout": "flow",
                    "actions": [
                        {
                            "tag": "button",
                            "text": {
                                "tag": "plain_text",
                                "content": "✅ 直接确认"
                            },
                            "type": "primary",
                            "value": {
                                "action": "confirm_thought",
                                "content": content,
                                "intent": "记录思考",
                                "route_result": route_result
                            }
                        },
                        {
                            "tag": "button",
                            "text": {
                                "tag": "plain_text",
                                "content": "✏️ 编辑内容"
                            },
                            "type": "default",
                            "value": {
                                "action": "edit_content",
                                "content": content,
                                "intent": "记录思考"
                            }
                        },
                        {
                            "tag": "button",
                            "text": {
                                "tag": "plain_text",
                                "content": "❌ 取消"
                            },
                            "type": "danger",
                            "value": {
                                "action": "cancel",
                                "intent": "记录思考"
                            }
                        }
                    ]
                }
            ]
        }

        return card

    def _build_schedule_record_card(self, route_result: Dict[str, Any]) -> Dict[str, Any]:
        """构建日程记录确认卡片"""
        content = route_result.get('content', '')
        confidence = route_result.get('confidence', 0)
        route_type = route_result.get('route_type', 'unknown')
        parameters = route_result.get('parameters', {})

        # 获取参数信息（新格式）
        event_content = parameters.get('event_content', content)
        time_info = parameters.get('time_info', '未指定时间')
        status = parameters.get('status', '计划')

        # 构建时间信息显示
        time_display = f"**时间信息：** {time_info}" if time_info and time_info != '未指定时间' else "**时间信息：** 未指定"

        card = {
            "config": {
                "wide_screen_mode": True
            },
            "header": {
                "template": "green",
                "title": {
                    "tag": "plain_text",
                    "content": "📅 AI识别结果 - 记录日程"
                }
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"**识别方式：** {'快捷指令' if route_type == 'shortcut' else 'AI识别'} | **置信度：** {confidence}%"
                    }
                },
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"**日程内容：** {event_content}"
                    }
                },
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": time_display
                    }
                },
                {
                    "tag": "hr"
                },
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": "**事件状态：**"
                    }
                },
                {
                    "tag": "action",
                    "layout": "flow",
                    "actions": [
                        {
                            "tag": "select_static",
                            "placeholder": {
                                "tag": "plain_text",
                                "content": "选择状态"
                            },
                            "options": [
                                {
                                    "text": {
                                        "tag": "plain_text",
                                        "content": "📋 计划"
                                    },
                                    "value": "计划"
                                },
                                {
                                    "text": {
                                        "tag": "plain_text",
                                        "content": "🔄 进行中"
                                    },
                                    "value": "进行中"
                                },
                                {
                                    "text": {
                                        "tag": "plain_text",
                                        "content": "✅ 完成"
                                    },
                                    "value": "完成"
                                }
                            ],
                            "value": {
                                "action": "select_status",
                                "intent": "记录日程",
                                "default_status": status
                            }
                        }
                    ]
                },
                {
                    "tag": "hr"
                },
                {
                    "tag": "action",
                    "layout": "flow",
                    "actions": [
                        {
                            "tag": "button",
                            "text": {
                                "tag": "plain_text",
                                "content": "✅ 直接确认"
                            },
                            "type": "primary",
                            "value": {
                                "action": "confirm_schedule",
                                "content": event_content,
                                "intent": "记录日程",
                                "route_result": route_result
                            }
                        },
                        {
                            "tag": "button",
                            "text": {
                                "tag": "plain_text",
                                "content": "✏️ 编辑内容"
                            },
                            "type": "default",
                            "value": {
                                "action": "edit_content",
                                "content": event_content,
                                "intent": "记录日程"
                            }
                        },
                        {
                            "tag": "button",
                            "text": {
                                "tag": "plain_text",
                                "content": "❌ 取消"
                            },
                            "type": "danger",
                            "value": {
                                "action": "cancel",
                                "intent": "记录日程"
                            }
                        }
                    ]
                }
            ]
        }

        return card

    def _build_food_order_card(self, route_result: Dict[str, Any]) -> Dict[str, Any]:
        """构建点餐确认卡片"""
        content = route_result.get('content', '')
        confidence = route_result.get('confidence', 0)
        route_type = route_result.get('route_type', 'unknown')
        parameters = route_result.get('parameters', {})

        # 获取参数信息（新格式）
        food_item = parameters.get('food_item_or_type', content)
        quantity = parameters.get('quantity', '')

        # 构建点餐信息显示
        food_display = f"**点餐需求：** {food_item}"
        if quantity:
            food_display += f"\n**数量：** {quantity}"

        card = {
            "config": {
                "wide_screen_mode": True
            },
            "header": {
                "template": "orange",
                "title": {
                    "tag": "plain_text",
                    "content": "🍽️ AI识别结果 - 点餐"
                }
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"**识别方式：** {'快捷指令' if route_type == 'shortcut' else 'AI识别'} | **置信度：** {confidence}%"
                    }
                },
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": food_display
                    }
                },
                {
                    "tag": "hr"
                },
                {
                    "tag": "action",
                    "layout": "flow",
                    "actions": [
                        {
                            "tag": "button",
                            "text": {
                                "tag": "plain_text",
                                "content": "✅ 确认点餐"
                            },
                            "type": "primary",
                            "value": {
                                "action": "confirm_food_order",
                                "content": food_item,
                                "intent": "点餐",
                                "route_result": route_result
                            }
                        },
                        {
                            "tag": "button",
                            "text": {
                                "tag": "plain_text",
                                "content": "✏️ 编辑内容"
                            },
                            "type": "default",
                            "value": {
                                "action": "edit_content",
                                "content": food_item,
                                "intent": "点餐"
                            }
                        },
                        {
                            "tag": "button",
                            "text": {
                                "tag": "plain_text",
                                "content": "❌ 取消"
                            },
                            "type": "danger",
                            "value": {
                                "action": "cancel",
                                "intent": "点餐"
                            }
                        }
                    ]
                }
            ]
        }

        return card

    def _build_unknown_intent_card(self, route_result: Dict[str, Any]) -> Dict[str, Any]:
        """构建未知意图卡片"""
        content = route_result.get('content', '')
        reasoning = route_result.get('reasoning', '无法识别意图')
        other_intent_name = route_result.get('other_intent_name', '')
        if other_intent_name:
            extra_info = {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": f"**AI识别为：**\n• `{other_intent_name}`"
                }
            }
        else:
            extra_info = ""

        card = {
            "config": {
                "wide_screen_mode": True
            },
            "header": {
                "template": "grey",
                "title": {
                    "tag": "plain_text",
                    "content": "❓ 无法识别意图"
                }
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"**原始内容：** {content}"
                    }
                },
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"**分析结果：** {reasoning}"
                    }
                },
                extra_info,
                {
                    "tag": "hr"
                },
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": "**建议使用快捷指令：**\n• `jl` - 记录思考\n• `rc` - 记录日程\n• `cx` - 查询内容\n• `dc` - 点餐"
                    }
                }
            ]
        }

        return card