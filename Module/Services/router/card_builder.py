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
        print('test-',route_result)

        # 获取建议的标签
        suggested_tags = parameters.get('suggested_tags', [])

        # 构建标签选择元素
        tag_elements = []
        if suggested_tags:
            tag_options = []
            for tag_info in suggested_tags[:3]:  # 最多显示3个建议标签
                tag_options.append({
                    "text": {
                        "tag": "plain_text",
                        "content": f"{tag_info.get('tag', '')} ({tag_info.get('confidence', 0)}%)"
                    },
                    "value": tag_info.get('tag', '')
                })

            # 添加一个备选标签（如果少于3个）
            if len(tag_options) < 3:
                tag_options.append({
                    "text": {
                        "tag": "plain_text",
                        "content": "学习 (备选)"
                    },
                    "value": "学习"
                })

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
                        "content": f"**内容：** {content}"
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

        # 获取时间信息
        time_info = parameters.get('time_info', {})
        mentioned_time = time_info.get('mentioned_time', '未指定')
        is_future = time_info.get('is_future', True)
        urgency = time_info.get('urgency', 50)

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
                        "content": f"**日程内容：** {content}"
                    }
                },
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"**时间信息：** {mentioned_time} | **紧急程度：** {urgency}%"
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
                                        "content": "📋 计划中"
                                    },
                                    "value": "planned"
                                },
                                {
                                    "text": {
                                        "tag": "plain_text",
                                        "content": "🔄 进行中"
                                    },
                                    "value": "in_progress"
                                },
                                {
                                    "text": {
                                        "tag": "plain_text",
                                        "content": "✅ 已完成"
                                    },
                                    "value": "completed"
                                }
                            ],
                            "value": {
                                "action": "select_status",
                                "intent": "记录日程"
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
                                "content": content,
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
                                "content": content,
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
                        "content": f"**点餐需求：** {content}"
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
                                "content": content,
                                "intent": "点餐",
                                "route_result": route_result
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
        confidence = route_result.get('confidence', 0)
        reasoning = route_result.get('reasoning', '无法识别意图')

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