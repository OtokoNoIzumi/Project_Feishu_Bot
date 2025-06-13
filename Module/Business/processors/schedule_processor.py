"""
定时任务处理器

处理每日汇总、B站更新等定时任务相关功能
"""

from typing import Dict, Any, List, Optional
from datetime import datetime
from .base_processor import BaseProcessor, MessageContext, ProcessResult
from Module.Common.scripts.common import debug_utils


class ScheduleProcessor(BaseProcessor):
    """
    定时任务处理器

    处理各种定时任务相关的功能
    """

    def create_scheduled_message(self, message_type: str, **kwargs) -> ProcessResult:
        """
        创建定时任务消息（供SchedulerService调用）

        Args:
            message_type: 消息类型 ('daily_schedule', 'bilibili_updates')
            **kwargs: 消息相关参数

        Returns:
            ProcessResult: 包含富文本卡片的处理结果
        """
        try:
            if message_type == "daily_schedule":
                services_status = kwargs.get('services_status', None)
                return self.create_daily_schedule_message(services_status)

            elif message_type == "bilibili_updates":
                sources = kwargs.get('sources', None)
                api_result = kwargs.get('api_result', None)
                return self.create_bilibili_updates_message(sources, api_result)

            else:
                return ProcessResult.error_result(f"不支持的定时消息类型: {message_type}")

        except Exception as e:
            return ProcessResult.error_result(f"创建定时消息失败: {str(e)}")

    def create_daily_schedule_message(self, services_status: Dict[str, Any] = None) -> ProcessResult:
        """创建每日信息汇总消息（7:30定时卡片容器）"""
        try:
            # 构建B站信息cache分析数据
            analysis_data = self.build_bilibili_cache_analysis()

            # 将服务状态信息加入分析数据
            if services_status:
                analysis_data['services_status'] = services_status

            card_content = self.create_daily_summary_card(analysis_data)

            return ProcessResult.success_result("interactive", card_content)

        except Exception as e:
            return ProcessResult.error_result(f"创建每日信息汇总失败: {str(e)}")

    def build_bilibili_cache_analysis(self) -> Dict[str, Any]:
        """
        构建B站信息cache分析数据（获取统计信息用于7:30定时任务）
        """
        now = datetime.now()

        # 尝试从notion服务获取B站视频统计数据
        if self.app_controller:
            notion_service = self.app_controller.get_service('notion')
            if notion_service:
                try:
                    # 调用统计方法获取B站数据分析
                    stats = notion_service.get_bili_videos_statistics()
                    # 兼容新版返回格式
                    if stats and stats.get("success", False):
                        # 兼容字段映射
                        total_count = stats.get("总未读数", 0)
                        priority_stats = stats.get("优先级统计", {})
                        duration_stats = stats.get("时长分布", {})
                        source_stats = stats.get("来源统计", {})
                        top_recommendations = stats.get("今日精选推荐", [])
                        return {
                            "date": now.strftime("%Y年%m月%d日"),
                            "weekday": ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][now.weekday()],
                            "statistics": {
                                "total_count": total_count,
                                "priority_stats": priority_stats,
                                "duration_stats": duration_stats,
                                "source_stats": source_stats,
                                "top_recommendations": top_recommendations
                            },
                            "source": "notion_statistics",
                            "timestamp": now.isoformat()
                        }
                except Exception as e:
                    from Module.Common.scripts.common import debug_utils
                    debug_utils.log_and_print(f"获取notion B站统计数据失败: {e}", log_level="WARNING")

        # 基础状态信息作为fallback
        return {
            "date": now.strftime("%Y年%m月%d日"),
            "weekday": ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][now.weekday()],
            "status": "notion服务B站数据获取中...",
            "source": "placeholder",
            "timestamp": now.isoformat()
        }

    def create_daily_summary_card(self, analysis_data: Dict[str, Any]) -> Dict[str, Any]:
        """创建每日信息汇总卡片"""
        source = analysis_data.get('source', 'unknown')

        if source == 'notion_statistics':
            # notion服务提供的B站分析数据
            content = self.format_notion_bili_analysis(analysis_data)
        else:
            # 占位信息
            content = f"📊 **{analysis_data['date']} {analysis_data['weekday']}** \n\n🔄 **系统状态**\n\n{analysis_data.get('status', '服务准备中...')}"

        # 添加服务状态信息
        services_status = analysis_data.get('services_status')
        if services_status:
            content += self.format_services_status(services_status)

        card = {
            "config": {
                "wide_screen_mode": True
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "content": content,
                        "tag": "lark_md"
                    }
                },
                {
                    "tag": "hr"
                },
            ],
            "header": {
                "template": "blue",
                "title": {
                    "content": "📊 每日信息汇总",
                    "tag": "plain_text"
                }
            }
        }

        # 如果有推荐视频，添加推荐链接部分
        if source == 'notion_statistics':
            statistics = analysis_data.get('statistics', {})

            # 兼容新版字段名
            top_recommendations = statistics.get('top_recommendations', None)
            if top_recommendations is None:
                top_recommendations = statistics.get('今日精选推荐', [])

            if top_recommendations:
                # 获取notion服务以检查已读状态
                notion_service = None
                if hasattr(self, 'app_controller') and self.app_controller:
                    notion_service = self.app_controller.get_service('notion')

                # 添加推荐视频标题
                card["elements"].extend([
                    {
                        "tag": "div",
                        "text": {
                            "content": "🎬 **今日精选推荐**",
                            "tag": "lark_md"
                        }
                    }
                ])

                # 添加每个推荐视频的简化展示
                for i, video in enumerate(top_recommendations, 1):
                    # 检查该视频是否已读（兼容新旧字段）
                    video_pageid = video.get('页面ID', video.get('pageid', ''))
                    video_read = notion_service.is_video_read(video_pageid) if notion_service and video_pageid else False

                    # 视频标题（兼容新旧字段）
                    title = video.get('标题', video.get('title', '无标题视频'))
                    if len(title) > 30:
                        title = title[:30] + "..."

                    # 兼容新旧字段格式
                    priority = video.get('优先级', video.get('chinese_priority', '未知'))
                    duration = video.get('时长', video.get('duration_str', '未知'))

                    card["elements"].append({
                        "tag": "div",
                        "text": {
                            "tag": "lark_md",
                            "content": f"**{title}** | 优先级: {priority} • 时长: {duration}{' | 已读' if video_read else ''}"
                        }
                    })

                    # 视频基本信息和链接按钮
                    video_url = video.get('链接', video.get('url', ''))
                    card["elements"].append({
                        "tag": "action",
                        "layout": "flow",  # 使用flow布局让按钮在一行显示
                        "actions": [
                            {
                                "tag": "button",
                                "text": {
                                    "tag": "plain_text",
                                    "content": "📱 手机"
                                },
                                "type": "default",
                                "size": "tiny",
                                "url": self.convert_to_bili_app_link(video_url)
                            },
                            {
                                "tag": "button",
                                "text": {
                                    "tag": "plain_text",
                                    "content": "💻 电脑"
                                },
                                "type": "default",
                                "size": "tiny",
                                "url": video_url
                            }
                        ] + ([] if video_read else [{
                            "tag": "button",
                            "text": {
                                "tag": "plain_text",
                                "content": "✅ 已读"
                            },
                            "type": "primary",
                            "size": "tiny",
                            "value": {
                                "action": "mark_bili_read",
                                "pageid": video_pageid,
                                "card_type": "daily",  # 定时卡片
                                "video_index": i - 1,  # 推荐视频序号 (0,1,2)
                                # 保存原始完整数据用于卡片重构（不重新获取统计数据）
                                "original_analysis_data": analysis_data
                            }
                        }] if video_pageid else [])
                    })

        return card

    def convert_to_bili_app_link(self, web_url: str) -> str:
        """
        将B站网页链接转换为B站应用链接
        """
        import re
        from Module.Common.scripts.common import debug_utils

        try:
            # 输入验证
            if not web_url or not isinstance(web_url, str):
                return web_url or ""

            # 检查是否是BV号格式
            bv_match = re.search(r'(/BV[a-zA-Z0-9]+)', web_url)
            if bv_match:
                bv_id = bv_match.group(1).replace('/', '')
                return f"bilibili://video/{bv_id}"

            # 检查是否包含av号
            av_match = re.search(r'av(\d+)', web_url)
            if av_match:
                av_id = av_match.group(1)
                return f"bilibili://video/av{av_id}"

            # 默认返回原始链接
            return web_url

        except Exception as e:
            debug_utils.log_and_print(f"[链接转换] 处理异常: {e}, URL: {web_url}", log_level="ERROR")
            return web_url  # 异常时返回原始链接

    def format_notion_bili_analysis(self, data: Dict[str, Any]) -> str:
        """格式化notion B站统计数据"""
        content = f"📊 **{data['date']} {data['weekday']}**"
        content += "\n\n🎯 **B站信息分析汇总**"

        statistics = data.get('statistics', {})

        # 总体统计
        total_count = statistics.get('total_count', None)
        # 兼容新版字段
        if total_count is None:
            total_count = statistics.get('总未读数', 0)
        content += f"\n\n📈 **总计:** {total_count} 个未读视频"

        if total_count > 0:
            # 优先级统计（增加时长总计）
            priority_stats = statistics.get('priority_stats', None)
            if priority_stats is None:
                priority_stats = statistics.get('优先级统计', {})
            if priority_stats:
                content += "\n\n🎯 **优先级分布:**"
                for priority, info in priority_stats.items():
                    # 新版格式：{'😜中': {'数量': 1, '总时长分钟': 51}}
                    count = info.get('数量', info.get('count', 0))
                    total_minutes = info.get('总时长分钟', info.get('total_minutes', 0))
                    hours = total_minutes // 60
                    minutes = total_minutes % 60
                    time_str = f"{hours}小时{minutes}分钟" if hours > 0 else f"{minutes}分钟"
                    content += f"\n• {priority}: {count} 个 ({time_str})"

            # 时长分布
            duration_stats = statistics.get('duration_stats', None)
            if duration_stats is None:
                duration_stats = statistics.get('时长分布', {})
            if duration_stats:
                content += "\n\n⏱️ **时长分布:**"
                for duration_type, count in duration_stats.items():
                    content += f"\n• {duration_type}: {count} 个"

            # 来源统计
            source_stats = statistics.get('source_stats', None)
            if source_stats is None:
                source_stats = statistics.get('来源统计', {})
            if source_stats:
                content += "\n\n📺 **来源分布:**"
                for source, count in source_stats.items():
                    content += f"\n• {source}: {count} 个"

        return content

    def format_services_status(self, services_status: Dict[str, Any]) -> str:
        """格式化服务状态信息"""
        content = "\n\n🔧 **外部服务状态检测**"
        check_time = services_status.get('check_time', '未知时间')
        content += f"\n检测时间: {check_time}"

        services = services_status.get('services', {})

        # B站API服务状态
        bili_api = services.get('bilibili_api', {})
        if bili_api.get('enabled', False):
            status = bili_api.get('status', 'unknown')
            message = bili_api.get('message', '')
            response_time = bili_api.get('response_time', '')
            url = bili_api.get('url', '')

            status_emoji = {
                'healthy': '✅',
                'warning': '⚠️',
                'error': '❌',
                'disabled': '⏸️'
            }.get(status, '❓')

            content += f"\n\n{status_emoji} **{bili_api.get('service_name', 'B站API服务')}**"
            content += f"\n状态: {message}"
            if response_time:
                content += f" ({response_time})"
            if url and status != 'error':
                # 截断长URL显示
                display_url = url if len(url) <= 40 else url[:37] + "..."
                content += f"\n地址: {display_url}"
        else:
            content += "\n\n⏸️ **B站API服务**: 未启用"

        # Gradio服务状态
        gradio = services.get('gradio', {})
        if gradio.get('enabled', False):
            status = gradio.get('status', 'unknown')
            message = gradio.get('message', '')
            response_time = gradio.get('response_time', '')
            url = gradio.get('url', '')

            status_emoji = {
                'healthy': '✅',
                'warning': '⚠️',
                'error': '❌',
                'disabled': '⏸️'
            }.get(status, '❓')

            content += f"\n\n{status_emoji} **{gradio.get('service_name', 'Gradio图像服务')}**"
            content += f"\n状态: {message}"
            if response_time:
                content += f" ({response_time})"
            if url and status != 'error':
                # 截断长URL显示
                display_url = url if len(url) <= 40 else url[:37] + "..."
                content += f"\n地址: {display_url}"

            # 显示令牌信息
            token_info = gradio.get('token_info', {})
            if token_info.get('has_token', False):
                token_status = token_info.get('status', 'unknown')
                if token_status == 'valid':
                    expires_in_hours = token_info.get('expires_in_hours', 0)
                    expires_at = token_info.get('expires_at', '')
                    # 格式化时间为 mm-dd hh:mm
                    formatted_expires_at = ""
                    if expires_at:
                        try:
                            # 兼容带时区的ISO格式
                            from datetime import datetime
                            if "+" in expires_at or "Z" in expires_at:
                                # 去掉时区信息
                                expires_at_clean = expires_at.split("+")[0].replace("Z", "")
                            else:
                                expires_at_clean = expires_at
                            dt = datetime.fromisoformat(expires_at_clean)
                            formatted_expires_at = dt.strftime("%m-%d %H:%M")
                        except Exception:
                            formatted_expires_at = expires_at  # 解析失败则原样输出
                    if expires_in_hours <= 24:  # 24小时内过期显示警告
                        content += f"\n⚠️ 令牌将在 {expires_in_hours}小时 后过期 ({formatted_expires_at})"
                    else:
                        content += f"\n🔑 令牌有效期至: {formatted_expires_at}"
                elif token_status == 'expired':
                    expires_at = token_info.get('expires_at', '')
                    formatted_expires_at = ""
                    if expires_at:
                        try:
                            from datetime import datetime
                            if "+" in expires_at or "Z" in expires_at:
                                expires_at_clean = expires_at.split("+")[0].replace("Z", "")
                            else:
                                expires_at_clean = expires_at
                            dt = datetime.fromisoformat(expires_at_clean)
                            formatted_expires_at = dt.strftime("%m-%d %H:%M")
                        except Exception:
                            formatted_expires_at = expires_at
                    content += f"\n❌ 令牌已于{formatted_expires_at}过期，需要更新"
                elif token_status == 'parse_error':
                    content += "\n⚠️ 令牌时间解析异常"
                elif token_status == 'no_expiry_info':
                    content += "\n🔑 令牌已配置 (无过期信息)"
        else:
            content += "\n\n⏸️ **Gradio图像服务**: 未启用"

        return content

    def create_bilibili_updates_message(self, sources: Optional[List[str]] = None, api_result: Dict[str, Any] = None) -> ProcessResult:
        """创建B站更新提醒消息"""
        try:
            # 生成B站更新通知卡片，传入API结果数据
            card_content = self.create_bilibili_updates_card(sources, api_result)

            return ProcessResult.success_result("interactive", card_content)

        except Exception as e:
            return ProcessResult.error_result(f"创建B站更新提醒失败: {str(e)}")

    def create_bilibili_updates_card(self, sources: Optional[List[str]] = None, api_result: Dict[str, Any] = None) -> Dict[str, Any]:
        """创建B站更新通知卡片"""
        source_text = "、".join(sources) if sources else "全部源"
        now = datetime.now()

        # 基础卡片结构
        card = {
            "config": {
                "wide_screen_mode": True
            },
            "header": {
                "template": "blue",
                "title": {
                    "content": "📺 B站数据处理完成",
                    "tag": "plain_text"
                }
            },
            "elements": []
        }

        # 添加基础信息
        card["elements"].extend([
            {
                "tag": "div",
                "text": {
                    "content": f"🔄 **数据源：** {source_text}\n⏰ **处理时间：** {now.strftime('%Y-%m-%d %H:%M:%S')}",
                    "tag": "lark_md"
                }
            }
        ])

        # 如果有API结果数据，添加详细信息
        if api_result and isinstance(api_result, dict):
            success = api_result.get('success', False)

            if success:
                # 成功情况：显示处理统计
                stats = api_result.get('stats', {})
                if stats:
                    content = "\n\n✅ **处理结果：**"

                    # 添加各种统计信息
                    for key, value in stats.items():
                        if isinstance(value, (int, float)):
                            content += f"\n• {key}: {value}"
                        elif isinstance(value, str):
                            content += f"\n• {key}: {value}"

                    card["elements"].append({
                        "tag": "div",
                        "text": {
                            "content": content,
                            "tag": "lark_md"
                        }
                    })
            else:
                # 失败情况：显示错误信息
                error_msg = api_result.get('error', '未知错误')
                card["elements"].append({
                    "tag": "div",
                    "text": {
                        "content": f"\n\n❌ **处理失败：** {error_msg}",
                        "tag": "lark_md"
                    }
                })
        else:
            # 没有详细结果，显示基本完成信息
            card["elements"].append({
                "tag": "div",
                "text": {
                    "content": "\n\n✅ **数据处理已完成**",
                    "tag": "lark_md"
                }
            })

        return card

    def handle_mark_bili_read(self, context: MessageContext, action_value: Dict[str, Any]) -> ProcessResult:
        """
        处理定时卡片中的标记B站视频为已读
        """
        try:
            if not self.app_controller:
                return ProcessResult.error_result("系统服务不可用")

            # 获取notion服务
            notion_service = self.app_controller.get_service('notion')
            if not notion_service:
                return ProcessResult.error_result("标记服务暂时不可用")

            # 获取参数
            pageid = action_value.get("pageid", "")
            video_index = action_value.get("video_index", 0)

            if not pageid:
                return ProcessResult.error_result("缺少页面ID，无法标记为已读")

            # 执行标记为已读操作
            success = notion_service.mark_video_as_read(pageid)
            if not success:
                return ProcessResult.error_result("标记为已读失败")

            # 定时卡片：基于原始数据重构，只更新已读状态，不重新获取统计数据
            try:
                original_analysis_data = action_value.get("original_analysis_data")
                if original_analysis_data:
                    # 使用原始数据重新生成卡片，已读状态会自动更新
                    updated_card = self.create_daily_summary_card(original_analysis_data)

                    return ProcessResult.success_result("card_action_response", {
                        "toast": {
                            "type": "success",
                            "content": f"已标记第{video_index + 1}个推荐为已读"
                        },
                        "card": {
                            "type": "raw",
                            "data": updated_card
                        }
                    })
                else:
                    # 如果没有原始数据，降级处理
                    return ProcessResult.success_result("card_action_response", {
                        "toast": {
                            "type": "success",
                            "content": f"已标记第{video_index + 1}个推荐为已读"
                        }
                    })
            except Exception as e:
                # 如果重新生成失败，只返回toast
                debug_utils.log_and_print(f"❌ 重新生成定时卡片失败: {str(e)}", log_level="ERROR")
                return ProcessResult.success_result("card_action_response", {
                    "toast": {
                        "type": "success",
                        "content": f"已标记第{video_index + 1}个推荐为已读"
                    }
                })

        except Exception as e:
            debug_utils.log_and_print(f"❌ 定时卡片标记已读失败: {str(e)}", log_level="ERROR")
            return ProcessResult.error_result(f"处理失败：{str(e)}")