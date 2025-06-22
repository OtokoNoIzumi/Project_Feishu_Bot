"""
定时任务处理器

处理每日汇总、B站更新等定时任务相关功能
"""

import re
from typing import Dict, Any, List, Optional
from datetime import datetime
from .base_processor import BaseProcessor, MessageContext, ProcessResult, require_service, safe_execute
from Module.Common.scripts.common import debug_utils
from Module.Services.constants import SchedulerTaskTypes, ServiceNames, ResponseTypes


class ScheduleProcessor(BaseProcessor):
    """
    定时任务处理器

    处理各种定时任务相关的功能
    """

    @safe_execute("创建定时消息失败")
    def create_scheduled_message(self, scheduler_type: str, **kwargs) -> ProcessResult:
        """
        创建定时任务消息（供SchedulerService调用）

        Args:
            scheduler_type: 定时任务类型 ('daily_schedule', 'bilibili_updates')
            **kwargs: 消息相关参数

        Returns:
            ProcessResult: 包含富文本卡片的处理结果
        """
        match scheduler_type:
            case SchedulerTaskTypes.DAILY_SCHEDULE:
                services_status = kwargs.get('services_status', None)
                return self.create_daily_schedule_message(services_status)
            case SchedulerTaskTypes.BILI_UPDATES:
                sources = kwargs.get('sources', None)
                api_result = kwargs.get('api_result', None)
                return self.create_bilibili_updates_message(sources, api_result)
            case _:
                return ProcessResult.error_result(f"不支持的定时消息类型: {scheduler_type}")

    @safe_execute("创建每日信息汇总失败")
    def create_daily_schedule_message(self, services_status: Dict[str, Any] = None) -> ProcessResult:
        """创建每日信息汇总消息（7:30定时卡片容器）"""
        # 构建B站信息cache分析数据
        analysis_data = self.build_bilibili_cache_analysis()

        # 将服务状态信息加入分析数据
        if services_status:
            analysis_data['services_status'] = services_status

        card_content = self.create_daily_summary_card(analysis_data)

        return ProcessResult.success_result("interactive", card_content)

    def build_bilibili_cache_analysis(self) -> Dict[str, Any]:
        """
        构建B站信息cache分析数据（获取统计信息用于7:30定时任务）
        """
        now = datetime.now()

        # 尝试从notion服务获取B站视频统计数据
        if self.app_controller:
            notion_service = self.app_controller.get_service(ServiceNames.NOTION)
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
                    debug_utils.log_and_print(f"获取notion B站统计数据失败: {e}", log_level="WARNING")

        # 基础状态信息作为fallback
        return {
            "date": now.strftime("%Y年%m月%d日"),
            "weekday": ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][now.weekday()],
            "status": "目前没有待看的B站视频",
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
                                    "content": "📺 B站"
                                },
                                "type": "default",
                                "size": "tiny",
                                "behaviors": [
                                    {
                                        "type": "open_url",
                                        "default_url": video_url,
                                        "pc_url": video_url,
                                        "ios_url": video_url,
                                        "android_url": self.convert_to_bili_app_link(video_url)
                                    }
                                ]
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

    @safe_execute("创建B站更新提醒失败")
    def create_bilibili_updates_message(self, sources: Optional[List[str]] = None, api_result: Dict[str, Any] = None) -> ProcessResult:
        """创建B站更新提醒消息"""
        # 生成B站更新通知卡片，传入API结果数据
        card_content = self.create_bilibili_updates_card(sources, api_result)

        return ProcessResult.success_result("interactive", card_content)

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

        # 添加分隔线
        card["elements"].append({
            "tag": "hr"
        })

        # 如果有API结果数据，展示详细统计
        if api_result and api_result.get('success') and api_result.get('data'):
            data = api_result['data']

            # 处理统计信息
            if 'processing_stats' in data:
                stats = data['processing_stats']
                total_videos = data.get('total_videos', 0)
                total_minutes = stats.get('total_minutes', 0)

                # 总体统计
                hours = total_minutes // 60
                minutes = total_minutes % 60
                time_display = f"{hours}小时{minutes}分钟" if hours > 0 else f"{minutes}分钟"

                card["elements"].append({
                    "tag": "div",
                    "text": {
                        "content": f"📊 **总体统计：** {total_videos} 个视频，总时长 {time_display}",
                        "tag": "lark_md"
                    }
                })

                # 优先级分布（使用饼图）
                if 'priority_stats' in stats and total_videos > 0:
                    priority_stats = stats['priority_stats']

                    # 定义优先级排序（确保按High→Medium→Low→None顺序显示）
                    priority_order = ['😍高', '😜中', '😐低', '😶无']
                    # 也支持英文优先级名
                    priority_order_en = ['High', 'Medium', 'Low', 'None']

                    # 构建饼图数据（官方格式，按优先级排序）
                    chart_data = []

                    # 按照定义的顺序处理优先级
                    all_priorities = list(priority_stats.keys())
                    ordered_priorities = []

                    # 先添加预定义顺序中存在的优先级
                    for priority in priority_order + priority_order_en:
                        if priority in all_priorities:
                            ordered_priorities.append(priority)
                            all_priorities.remove(priority)

                    # 再添加其他未预定义的优先级
                    ordered_priorities.extend(all_priorities)

                    for priority in ordered_priorities:
                        if priority in priority_stats:
                            info = priority_stats[priority]
                            count = info.get('count', 0)
                            total_mins = info.get('total_minutes', 0)
                            percentage = round((count / total_videos) * 100, 1) if total_videos > 0 else 0

                            # 时长格式化
                            p_hours = total_mins // 60
                            p_minutes = total_mins % 60
                            p_time_display = f"{p_hours}h{p_minutes}m" if p_hours > 0 else f"{p_minutes}m"

                            chart_data.append({
                                "type": f"{priority} {percentage}%",
                                "value": str(count)
                            })

                    # 添加优先级分布饼图
                    card["elements"].extend([
                        {
                            "tag": "hr"
                        },
                        {
                            "tag": "div",
                            "text": {
                                "content": "🎯 **优先级分布**",
                                "tag": "lark_md"
                            }
                        },
                        {
                            "tag": "chart",
                            "aspect_ratio": "4:3",
                            "chart_spec": {
                                "type": "pie",
                                "title": {
                                    "text": "优先级分布"
                                },
                                "data": {
                                    "values": chart_data
                                },
                                "valueField": "value",
                                "categoryField": "type",
                                "outerRadius": 0.7,
                                "legends": {
                                    "visible": True,
                                    "orient": "bottom",
                                    "maxRow": 3,
                                    "itemWidth": 80,
                                    "itemGap": 8
                                },
                                "label": {
                                    "visible": True
                                },
                                "padding": {
                                    "left": 10,
                                    "top": 10,
                                    "bottom": 80,
                                    "right": 10
                                }
                            }
                        }
                    ])

                # 类型分布（使用环状图）
                if 'category_stats' in stats and total_videos > 0:
                    category_stats = stats['category_stats']

                    # 构建环状图数据（官方格式，添加百分比）
                    category_chart_data = []
                    for category, info in category_stats.items():
                        count = info.get('count', 0)
                        total_mins = info.get('total_minutes', 0)
                        percentage = round((count / total_videos) * 100, 1) if total_videos > 0 else 0

                        c_hours = total_mins // 60
                        c_minutes = total_mins % 60
                        c_time_display = f"{c_hours}h{c_minutes}m" if c_hours > 0 else f"{c_minutes}m"

                        category_chart_data.append({
                            "type": f"{category} {percentage}%",
                            "value": str(count)
                        })

                    card["elements"].extend([
                        {
                            "tag": "hr"
                        },
                        {
                            "tag": "div",
                            "text": {
                                "content": "📂 **类型分布**",
                                "tag": "lark_md"
                            }
                        },
                        {
                            "tag": "chart",
                            "aspect_ratio": "4:3",
                            "chart_spec": {
                                "type": "pie",
                                "title": {
                                    "text": "类型分布"
                                },
                                "data": {
                                    "values": category_chart_data
                                },
                                "valueField": "value",
                                "categoryField": "type",
                                "outerRadius": 0.7,
                                "innerRadius": 0.3,
                                "legends": {
                                    "visible": True,
                                    "orient": "bottom",
                                    "maxRow": 3,
                                    "itemWidth": 80,
                                    "itemGap": 8
                                },
                                "label": {
                                    "visible": True
                                },
                                "padding": {
                                    "left": 10,
                                    "top": 10,
                                    "bottom": 80,
                                    "right": 10
                                }
                            }
                        }
                    ])

                # 新旧视频分布（使用对比饼图）
                if 'new_old_stats' in stats:
                    new_old = stats['new_old_stats']
                    new_count = new_old.get('new_videos', 0)
                    old_count = new_old.get('old_videos', 0)
                    new_minutes = new_old.get('new_total_minutes', 0)
                    old_minutes = new_old.get('old_total_minutes', 0)

                    if new_count + old_count > 0:
                        total_count = new_count + old_count
                        new_percentage = round((new_count / total_count) * 100, 1) if total_count > 0 else 0
                        old_percentage = round((old_count / total_count) * 100, 1) if total_count > 0 else 0

                        new_old_data = [
                            {
                                "type": f"新视频(48h内) {new_percentage}%",
                                "value": str(new_count)
                            },
                            {
                                "type": f"旧视频(48h外) {old_percentage}%",
                                "value": str(old_count)
                            }
                        ]

                        card["elements"].extend([
                            {
                                "tag": "hr"
                            },
                            {
                                "tag": "div",
                                "text": {
                                    "content": "🕒 **新旧视频分布**",
                                    "tag": "lark_md"
                                }
                            },
                            {
                                "tag": "chart",
                                "aspect_ratio": "4:3",
                                "chart_spec": {
                                    "type": "pie",
                                    "title": {
                                        "text": "新旧视频分布"
                                    },
                                    "data": {
                                        "values": new_old_data
                                    },
                                    "valueField": "value",
                                    "categoryField": "type",
                                    "outerRadius": 0.7,
                                    "legends": {
                                        "visible": True,
                                        "orient": "bottom",
                                        "maxRow": 3,
                                        "itemWidth": 80,
                                        "itemGap": 8
                                    },
                                    "label": {
                                        "visible": True
                                    },
                                    "padding": {
                                        "left": 10,
                                        "top": 10,
                                        "bottom": 80,
                                        "right": 10
                                    }
                                }
                            }
                        ])

                # 广告检测统计（使用对比饼图）
                if 'ad_timestamp_stats' in stats:
                    ad_stats = stats['ad_timestamp_stats']
                    ad_count = ad_stats.get('videos_with_ads', 0)
                    no_ad_count = ad_stats.get('videos_without_ads', 0)
                    ad_percentage_global = ad_stats.get('ads_percentage', 0)
                    avg_ad_duration = ad_stats.get('avg_ad_duration_seconds', 0)

                    if ad_count + no_ad_count > 0:
                        total_ad_count = ad_count + no_ad_count
                        ad_percentage = round((ad_count / total_ad_count) * 100, 1) if total_ad_count > 0 else 0
                        no_ad_percentage = round((no_ad_count / total_ad_count) * 100, 1) if total_ad_count > 0 else 0

                        ad_data = [
                            {"type": f"含广告 {ad_percentage}%", "value": str(ad_count)},
                            {"type": f"无广告 {no_ad_percentage}%", "value": str(no_ad_count)}
                        ]

                        card["elements"].extend([
                            {
                                "tag": "hr"
                            },
                            {
                                "tag": "div",
                                "text": {
                                    "content": f"📺 **广告检测** (检测到{ad_percentage_global:.1f}%包含广告)",
                                    "tag": "lark_md"
                                }
                            },
                            {
                                "tag": "chart",
                                "aspect_ratio": "4:3",
                                "chart_spec": {
                                    "type": "pie",
                                    "title": {
                                        "text": "广告检测分布"
                                    },
                                    "data": {
                                        "values": ad_data
                                    },
                                    "valueField": "value",
                                    "categoryField": "type",
                                    "outerRadius": 0.7,
                                    "legends": {
                                        "visible": True,
                                        "orient": "bottom",
                                        "maxRow": 3,
                                        "itemWidth": 80,
                                        "itemGap": 8
                                    },
                                    "label": {
                                        "visible": True
                                    },
                                    "padding": {
                                        "left": 10,
                                        "top": 10,
                                        "bottom": 80,
                                        "right": 10
                                    }
                                }
                            }
                        ])

                        if avg_ad_duration > 0:
                            card["elements"].append({
                                "tag": "div",
                                "text": {
                                    "content": f"💡 平均广告时长: {int(avg_ad_duration)}秒",
                                    "tag": "lark_md"
                                }
                            })

                # 作者排行（文本显示，图表对名字太长不友好）
                if 'author_stats' in stats and stats['author_stats']:
                    author_stats = stats['author_stats'][:5]  # 只显示前5名
                    if author_stats:
                        card["elements"].extend([
                            {
                                "tag": "hr"
                            },
                            {
                                "tag": "div",
                                "text": {
                                    "content": "👤 **作者排行** (前5名)",
                                    "tag": "lark_md"
                                }
                            }
                        ])

                        for i, author in enumerate(author_stats, 1):
                            name = author.get('name', '未知')
                            count = author.get('count', 0)
                            total_mins = author.get('total_minutes', 0)
                            a_time_display = f"{total_mins//60}h{total_mins%60}m" if total_mins//60 > 0 else f"{total_mins}m"

                            card["elements"].append({
                                "tag": "div",
                                "text": {
                                    "content": f"{i}. **{name}:** {count}个视频 ({a_time_display})",
                                    "tag": "lark_md"
                                }
                            })

            # 显示处理结果概要
            card["elements"].extend([
                {
                    "tag": "hr"
                },
                {
                    "tag": "div",
                    "text": {
                        "content": "💡 点击菜单中的\"B站\"获取最新无广告的视频",
                        "tag": "lark_md"
                    }
                }
            ])
        else:
            # 没有详细数据时的简化显示
            card["elements"].append({
                "tag": "div",
                "text": {
                    "content": "**📋 处理完成**\n\n系统已自动处理B站数据源，新内容已添加到数据库。",
                    "tag": "lark_md"
                }
            })

        return card

    @require_service('notion', "标记服务暂时不可用")
    @safe_execute("定时卡片标记已读失败")
    def handle_mark_bili_read(self, context: MessageContext, action_value: Dict[str, Any]) -> ProcessResult:
        """
        处理定时卡片中的标记B站视频为已读
        """
        # 获取notion服务
        notion_service = self.app_controller.get_service(ServiceNames.NOTION)

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

                return ProcessResult.success_result(ResponseTypes.SCHEDULER_CARD_UPDATE_BILI_BUTTON, {
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
                return ProcessResult.success_result(ResponseTypes.SCHEDULER_CARD_UPDATE_BILI_BUTTON, {
                    "toast": {
                        "type": "success",
                        "content": f"已标记第{video_index + 1}个推荐为已读"
                    }
                })
        except Exception as e:
            # 如果重新生成失败，只返回toast
            debug_utils.log_and_print(f"❌ 重新生成定时卡片失败: {str(e)}", log_level="ERROR")
            return ProcessResult.success_result(ResponseTypes.SCHEDULER_CARD_UPDATE_BILI_BUTTON, {
                "toast": {
                    "type": "success",
                    "content": f"已标记第{video_index + 1}个推荐为已读"
                }
            })
