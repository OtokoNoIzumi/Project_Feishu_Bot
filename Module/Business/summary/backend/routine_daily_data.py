"""日常分析数据处理模块

负责日常分析相关的数据获取和分析处理
"""

from typing import Dict, Any, List
from datetime import datetime, timedelta
import json
import os
import copy
import pandas as pd
import numpy as np

from Module.Services.constants import (
    ServiceNames,
    AdapterNames,
    ColorTypes,
    RoutineReminderTimeOptions,
)
from Module.Business.routine_record import RoutineRecord, wax_stamp_prompt


class RoutineDailyData:
    """日常分析数据处理器"""

    GRANULARITY_MINUTES = 120
    FORCE_MONDAY = False
    REPORT_MODE = "save"

    def __init__(self, app_controller):
        self.app_controller = app_controller
        self.routine_business = RoutineRecord(app_controller)

    # region 外部调用接口
    def get_routine_data(self, data_params: Dict[str, Any] = None) -> Dict[str, Any]:
        """获取日常分析数据（总入口）"""
        if not data_params:
            return {}
        user_id = data_params.get("user_id")
        image_generator = data_params.get("image_generator", "hunyuan_image_generator")

        now = datetime.now()
        is_monday = now.weekday() == 0 or self.FORCE_MONDAY  # 0是周一
        is_first_day_of_month = now.day == 1
        is_first_day_of_quarter = now.month % 3 == 1 and now.day == 1
        is_first_day_of_year = now.month == 1 and now.day == 1

        # 日：待办事项，提醒事项，image_key，主颜色
        # 周：日 + 周日程分析，周image_key，周的日程记录表，规律分析
        # 月：日 + 周 + 月程分析——最好维度有区别，否则就要因为月把周关闭掉，我不想有多份重复信息

        daily_data = self.get_daily_data(user_id, image_generator)

        weekly_data = None
        if is_monday:
            weekly_data = self.get_weekly_data(
                user_id, granularity_minutes=self.GRANULARITY_MINUTES
            )

        routine_data = {
            "daily": daily_data,
            "weekly": weekly_data,
        }

        return routine_data

    def analyze_routine_data(
        self, routine_data: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """分析routine数据"""

        daily_data = routine_data.get("daily", {})
        active_records = daily_data.get("active_records", {})
        interval_definitions = daily_data.get("interval_definitions", [])
        if active_records or interval_definitions:
            daily_data["reminder"] = self.analyze_daily_today_reminder(daily_data)

        weekly_raw = routine_data.get("weekly", {})
        formatted_weekly_data = {}
        weekly_document: Dict[str, Any] = {}
        if weekly_raw:
            # 生成周文档
            weekly_document = self.analyze_weekly_document(weekly_raw)
            # 生成卡片用时间表
            formatted_weekly_data = self.format_table_data(
                weekly_raw.get("records", []),
                weekly_raw.get("start_time"),
                weekly_raw.get("event_map"),
                weekly_raw.get("granularity_minutes", 120),
            )
            weekly_document["timetable"] = formatted_weekly_data

            ai_analysis = self._generate_routine_ai_analysis(
                weekly_raw, weekly_document
            )
            weekly_document["ai_analysis"] = ai_analysis

        # 分析routine数据，包括日、周、月、季、年
        # 日：待办事项，提醒事项，image_key，主颜色
        # 周：日 + 周日程分析，周image_key，周的日程记录表，规律分析
        # 月：日 + 周 + 月程分析——最好维度有区别，否则就要因为月把周关闭掉，我不想有多份重复信息

        routine_info = {
            "daily": daily_data,
            "weekly": weekly_document,
        }
        return routine_info

    # endregion

    # region 数据获取

    def get_daily_data(
        self, user_id: str = None, image_generator: str = None
    ) -> Dict[str, Any]:
        """获取日常数据

        Args:
            user_id: 用户ID，可选参数，默认为None

        Returns:
            Dict[str, Any]: 日常数据
        """
        # 还需要加上一个今日提醒和今日待办，至于昨日思考，这个最后做
        # 待办永远都是日，所以也不存在为了本周处理，就算有也是在这个模块提醒，所以这里过滤本身到也不是大事，不过也可以在分析那边做。
        now = datetime.now()

        end_time = datetime(now.year, now.month, now.day)
        start_time = end_time - timedelta(days=1)

        active_records = self.routine_business.load_event_records(user_id).get(
            "active_records", {}
        )
        definitions = self.routine_business.load_event_definitions(user_id).get(
            "definitions", {}
        )
        interval_definitions = []
        for definition in definitions.values():
            interval_minutes = definition.get("stats", {}).get("interval_minutes", None)
            if interval_minutes is not None:
                interval_definitions.append(definition)

        main_color, color_palette = self.routine_business.calculate_color_palette(
            user_id,
            start_time,
            end_time,
        )
        raw_prompt = wax_stamp_prompt(
            color_palette, subject_name=main_color.get("max_weight_category", "")
        )

        image_service = self.app_controller.get_service(ServiceNames.IMAGE)
        match image_generator:
            case "coze_image_generator":
                result = image_service.coze_image_generator.generate_image(
                    raw_prompt,
                )
            case "hunyuan_image_generator":
                result = image_service.hunyuan_image_generator.generate_image(
                    raw_prompt,
                    size="3:4",
                )
            case _:
                result = image_service.hunyuan_image_generator.generate_image(
                    raw_prompt,
                    size="3:4",
                )

        image_path = result.get("file_path")
        image_key = self.app_controller.get_adapter(
            AdapterNames.FEISHU
        ).sender.upload_and_get_image_key(image_path)

        # 删除图片
        if image_path:
            os.remove(image_path)

        return {
            "image_key": image_key,
            "main_color": main_color,
            "color_palette": color_palette,
            "interval_definitions": interval_definitions,
            "active_records": active_records,
        }

    def get_weekly_data(
        self, user_id: str = None, granularity_minutes: int = 120
    ) -> Dict[str, Any]:
        """获取周分析数据"""
        now = datetime.now()
        end_time = datetime(now.year, now.month, now.day) - timedelta(
            days=now.weekday()
        )
        start_time = end_time - timedelta(days=7)

        records = self.routine_business.load_event_records(user_id)
        records = records.get("records", {})

        filtered_records = self.routine_business.preprocess_and_filter_records(
            records, start_time, end_time
        )

        event_map = self.routine_business.cal_event_map(user_id)

        weekly_raw_data = {
            "records": filtered_records,
            "definitions": self.routine_business.load_event_definitions(user_id).get(
                "definitions", {}
            ),
            "start_time": start_time,
            "end_time": end_time,
            "event_map": event_map,
            "granularity_minutes": granularity_minutes,
            "user_id": user_id,
        }

        return weekly_raw_data

    # endregion

    # region 数据分析

    def analyze_daily_today_reminder(
        self, daily_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """分析今日提醒"""
        tomorrow = datetime.now().date() + timedelta(days=1)
        active_records = daily_data.get("active_records", {})
        interval_definitions = daily_data.get("interval_definitions", [])

        # 来自事件规律的提醒
        reminder_info = []
        for definition in interval_definitions:
            interval_minutes = definition.get("stats", {}).get("interval_minutes", 0)
            last_record_time = definition.get("last_record_time", None)
            if last_record_time:
                last_record_time = datetime.strptime(last_record_time, "%Y-%m-%d %H:%M")
                next_trigger_time = last_record_time + timedelta(
                    minutes=interval_minutes
                )
                compare_time = (
                    tomorrow if interval_minutes >= 1440 else datetime.now().date()
                )
                compare_time = datetime.combine(compare_time, datetime.min.time())

                # 要么就是interval大于1天，要么就是interval小于1天，但last_record已经隔超1天
                # 小于1天的等以后每2小时的提醒里实现
                if next_trigger_time <= compare_time:
                    event_name = definition.get("name", "")
                    duration_info = definition.get("stats", {}).get("duration", {})
                    avg_duration_detail = duration_info.get(
                        "avg_duration_detail", {}
                    )  # 待增加的周记录属性
                    duration = (
                        definition.get("stats", {})
                        .get("duration", {})
                        .get("recent_values", [])
                    )
                    avg_duration = (
                        round(sum(duration) / len(duration), 1) if duration else 0
                    )
                    avg_duration_detail["预估"] = avg_duration

                    reminder_info.append(
                        {
                            "event_name": event_name,
                            "avg_duration_detail": avg_duration_detail,
                            "last_record_time": last_record_time,
                        }
                    )

        # 来自待办的提醒
        for record in active_records.values():
            in_reminder = False
            scheduled_start_time = record.get("scheduled_start_time", "")
            if scheduled_start_time:
                scheduled_start_time = datetime.strptime(
                    scheduled_start_time, "%Y-%m-%d %H:%M"
                )
                if scheduled_start_time.date() <= tomorrow:
                    in_reminder = True

                reminder_relative = record.get("reminder_relative", [])
                for reminder in reminder_relative:
                    minutes = RoutineReminderTimeOptions.get_minutes(reminder)
                    remind_time = scheduled_start_time - timedelta(minutes=minutes)
                    if remind_time.date() <= tomorrow:
                        in_reminder = True
                        break

                reminder_time = record.get("reminder_time", "")
                if reminder_time:
                    reminder_time = datetime.strptime(reminder_time, "%Y-%m-%d %H:%M")
                    if reminder_time.date() <= tomorrow:
                        in_reminder = True
                        break

            if in_reminder:
                event_name = record.get("event_name", "")
                priority = record.get("priority", "low")
                est_duration = record.get("estimated_duration", 0)
                avg_duration_detail = {"预估": est_duration}
                note = record.get("note", "")
                new_reminder_info = {
                    "event_name": event_name,
                    "scheduled_start_time": scheduled_start_time,
                    "priority": priority,
                    "avg_duration_detail": avg_duration_detail,
                    "note": note,
                }
                reminder_info.append(new_reminder_info)

        return reminder_info

    def analyze_weekly_document(self, weekly_raw: Dict[str, Any]) -> Dict[str, Any]:
        """分析周文档"""
        record_df = pd.DataFrame(weekly_raw.get("records", [])).fillna("")

        # event_df: 从定义中取出event_name行
        definitions = weekly_raw.get("definitions", {})
        event_df = pd.DataFrame(definitions).fillna("")
        if not event_df.empty:
            event_df = event_df.T.rename(columns={"name": "event_name"})
        else:
            event_df = pd.DataFrame(
                columns=["event_name", "category", "properties"]
            )  # 空表占位

        # 统计原子时间线时长（按 record_id 聚合）
        start_time = weekly_raw.get("start_time")
        end_time = weekly_raw.get("end_time")
        if start_time.year == end_time.year:
            document_title = (
                f"周报告{start_time.strftime('%y%m%d')}-{end_time.strftime('%m%d')}"
            )
        else:
            document_title = (
                f"周报告{start_time.strftime('%y%m%d')}-{end_time.strftime('%y%m%d')}"
            )
        atomic_timeline = self.routine_business.generate_atomic_timeline(
            weekly_raw.get("records", []),
            start_time,
            end_time,
            add_unrecorded_block=True,
        )
        atomic_df = pd.DataFrame(atomic_timeline)
        unrecorded_df = atomic_df[atomic_df["unrecorded"] == True].copy()
        atomic_df = atomic_df[atomic_df["unrecorded"].isna()].copy()
        del atomic_df["unrecorded"]

        record_define_time = atomic_df.groupby("record_id", as_index=False)[
            "duration_minutes"
        ].sum()

        # 单次apply直接操作event_df提取所有字段
        event_df[["interval_type", "target_value", "check_cycle"]] = event_df.apply(
            self._extract_all_event_fields, axis=1, result_type="expand"
        )
        # 合并记录与定义信息
        merged_df = record_df.merge(
            event_df[
                [
                    "event_name",
                    "category",
                    "interval_type",
                    "target_value",
                    "check_cycle",
                ]
            ],
            on="event_name",
            how="left",
        ).fillna(
            {
                "category": "",
                "interval_type": "degree",
                "target_value": 0,
                "check_cycle": "",
            }
        )
        merged_df = merged_df.merge(record_define_time, on="record_id", how="left")

        # 分组统计
        grouped = merged_df.groupby(["category", "event_name", "degree"])
        summary_df = grouped.agg(
            count=("event_name", "size"),
            total_duration=("duration_minutes", "sum"),
            avg_duration=("duration_minutes", "mean"),
            min_duration=("duration_minutes", "min"),
            max_duration=("duration_minutes", "max"),
        ).reset_index()

        # 计算最大duration对应的start_at与三类interval
        max_duration_start_at_list = []
        degree_interval_minutes_list = []
        category_interval_minutes_list = []
        event_interval_minutes_list = []
        display_unit_list = []

        for name, group in grouped:
            max_duration_start_at_list.append(self._get_max_start_at(group))
            category_val = name[0]  # 对应 category
            event_name_val = name[1]  # 对应 event_name
            degree_val = name[2]  # 对应 degree

            interval_type_val = (
                group["interval_type"].iloc[0]
                if ("interval_type" in group.columns and not group.empty)
                else "degree"
            )
            if interval_type_val not in ["event", "degree", "ignore"]:
                interval_type_val = "ignore"

            # degree分组
            mask_degree = (
                (merged_df["category"] == category_val)
                & (merged_df["event_name"] == event_name_val)
                & (merged_df["degree"] == degree_val)
            )
            degree_group = merged_df[mask_degree].sort_values("start_dt")
            if not degree_group.empty and len(degree_group) > 1:
                degree_interval = self._calc_avg_interval(degree_group["start_dt"])
                degree_interval_minutes_list.append(degree_interval)
            else:
                degree_interval_minutes_list.append(np.nan)

            # event分组
            mask_category = (merged_df["category"] == category_val) & (
                merged_df["event_name"] == event_name_val
            )
            category_group = merged_df[mask_category].sort_values("start_dt")
            if not category_group.empty and len(category_group) > 1:
                category_interval = self._calc_avg_interval(category_group["start_dt"])
                category_interval_minutes_list.append(category_interval)
            else:
                category_interval_minutes_list.append(np.nan)

            # event口径
            if interval_type_val == "degree":
                event_interval = degree_interval_minutes_list[-1]
                display_unit_list.append(f"{event_name_val}({degree_val})")
            elif interval_type_val == "event":
                event_interval = category_interval_minutes_list[-1]
                display_unit_list.append(event_name_val)
            else:
                event_interval = np.nan
                display_unit_list.append("")
            event_interval_minutes_list.append(event_interval)

        summary_df["max_duration_start_at"] = max_duration_start_at_list
        summary_df["degree_interval_minutes"] = degree_interval_minutes_list
        summary_df["category_interval_minutes"] = category_interval_minutes_list
        summary_df["event_interval_minutes"] = event_interval_minutes_list
        summary_df["display_unit"] = display_unit_list

        # 事件总计与排序
        event_name_stats = (
            summary_df.groupby("event_name")
            .agg(
                event_total_count=("count", "sum"),
                event_total_duration=("total_duration", "sum"),
            )
            .reset_index()
        )

        unique_days = (weekly_raw.get("end_time") - weekly_raw.get("start_time")).days

        total_hours = unique_days * 24
        total_minutes = total_hours * 60

        category_stats = (
            summary_df.groupby("category")
            .agg(
                category_total_count=("count", "sum"),
                category_total_duration=("total_duration", "sum"),
            )
            .reset_index()
        )
        event_map = weekly_raw.get("event_map", {})
        category_color_map = {}
        for event_info in event_map.values():
            category_color_map[event_info.get("category", "")] = event_info.get(
                "color"
            ).pie_color

        category_stats["color"] = category_stats["category"].map(
            lambda x: category_color_map.get(x, "#959BEE")
        )

        if total_minutes > 0:
            category_stats["category_duration_percent"] = (
                category_stats["category_total_duration"] / total_minutes * 100
            ).round(1)
            recorded_minutes = category_stats["category_total_duration"].sum()
            unrecorded_minutes = total_minutes - recorded_minutes
            unrecorded_percent = round(unrecorded_minutes / total_minutes * 100, 1)
            category_stats = pd.concat(
                [
                    category_stats,
                    pd.DataFrame(
                        [
                            {
                                "category": "未记录",
                                "category_total_count": 0,
                                "category_total_duration": unrecorded_minutes,
                                "category_duration_percent": unrecorded_percent,
                                "color": "#d0d3d6",  # 灰色
                            }
                        ]
                    ),
                ],
                ignore_index=True,
            )
        else:
            category_stats["category_duration_percent"] = 0.0

        summary_df = summary_df.merge(event_name_stats, on="event_name", how="left")
        summary_df = summary_df.sort_values(
            by=[
                "event_total_count",
                "event_total_duration",
                "event_name",
                "total_duration",
                "count",
            ],
            ascending=[False, False, True, False, False],
        ).reset_index(drop=True)

        # 处理 note 信息
        current_year = datetime.now().year
        note_rows = merged_df[
            merged_df["note"].notnull() & (merged_df["note"] != "")
        ].copy()
        if not note_rows.empty:
            note_rows["note_info"] = note_rows.apply(
                lambda r: self._format_note_info(r, current_year), axis=1
            )
            note_infos = note_rows["note_info"].tolist()
        else:
            note_infos = []

        # 导出合并后的数据用于调试
        event_detail_df = merged_df.copy()

        # 需要删除的列
        columns_to_delete = [
            "create_time",
            "scheduled_start_time",
            "estimated_duration",
            "interval_type",
            "end_time",
            "record_id",
            "custom_degree",
            "reminder_relative",
            "reminder_mode",
            "priority",
            "duration",
        ]
        # 检查每个列是否存在，存在才删除
        for col in columns_to_delete:
            if col in event_detail_df.columns:
                event_detail_df.drop(columns=col, inplace=True)

        return {
            "note_list": note_infos,
            "event_summary": summary_df,  # 保持为DataFrame，后续使用处按需to_dict/to_csv
            "event_detail": event_detail_df,
            "category_stats": category_stats.to_dict(orient="records"),
            "document_title": document_title,
            "unrecorded_df": unrecorded_df,
        }

    # endregion

    # region 时间表处理

    def format_table_data(
        self,
        records: List[Dict[str, Any]],
        start_time: datetime,
        event_map: Dict[str, Any],
        granularity_minutes: int = 120,
    ) -> Dict[str, Any]:
        """格式化表格数据"""
        # 生成时间标签
        match granularity_minutes:
            case 30:
                time_labels = [
                    label
                    for hour in range(24)
                    for label in (f"{hour:02d}:00", f"{hour:02d}:30")
                ]
            case 60:
                time_labels = [f"{hour:02d}:00" for hour in range(24)]
            case _:
                time_labels = [f"{hour:02d}:00" for hour in range(0, 24, 2)]

        # 初始化周数据结构
        week_data = {
            "time_labels": time_labels,
            "days": {
                "mon": {},
                "tue": {},
                "wed": {},
                "thu": {},
                "fri": {},
                "sat": {},
                "sun": {},
            },
        }

        # 为每一天处理数据
        current_day = start_time
        day_keys = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]

        for day_idx in range(7):
            day_key = day_keys[day_idx]
            day_start = current_day
            day_end = day_start + timedelta(days=1)

            # 获取当天的记录
            day_records = []
            for record in records:
                record_start = record.get("start_dt")
                record_end = record.get("end_dt")

                # 判断记录是否与当天有交集
                if record_start < day_end and record_end > day_start:
                    day_records.append(record)

            # 为当天的每个时间槽生成数据
            for time_label in time_labels:
                hour_minute = time_label.split(":")
                slot_hour = int(hour_minute[0])
                slot_minute = int(hour_minute[1])

                slot_start = day_start.replace(
                    hour=slot_hour, minute=slot_minute, second=0, microsecond=0
                )
                slot_end = slot_start + timedelta(minutes=granularity_minutes)

                # 生成该时间槽的原子时间线
                atomic_timeline = self.routine_business.generate_atomic_timeline(
                    day_records, slot_start, slot_end
                )

                if atomic_timeline:
                    # 计算颜色和标签
                    # 周的模式显示的是event_name，不适合融合颜色，而是匹配颜色

                    # 找到持续时间最长的事件作为主要事件
                    sorted_atomic_timeline = sorted(
                        atomic_timeline,
                        key=lambda x: x["duration_minutes"],
                        reverse=True,
                    )
                    slot_event_label = sorted_atomic_timeline[0]["source_event"][
                        "event_name"
                    ]
                    slot_event_info = event_map.get(slot_event_label, {})
                    slot_event_color = slot_event_info.get("color", ColorTypes.GREY)

                    final_color, _ = self.routine_business.calculate_color_palette(
                        "no_user_id",
                        slot_start,
                        slot_end,
                        event_color_map=event_map,
                        timeline_data=atomic_timeline,
                    )

                    # slot_color_name = final_color

                    slot_category_label = final_color.get("max_weight_category", "空闲")

                    week_data["days"][day_key][time_label] = {
                        "text": slot_event_label,
                        "color": slot_event_color,
                        "category_label": slot_category_label,
                    }
                else:
                    # 空时间槽
                    week_data["days"][day_key][time_label] = {
                        "text": "空闲",
                        "color": ColorTypes.GREY,
                        "category_label": "空闲",
                    }

            current_day += timedelta(days=1)

        return week_data

    # endregion

    # region AI分析

    def _generate_routine_ai_analysis(
        self, weekly_raw: Dict[str, Any], weekly_document: Dict[str, Any]
    ) -> Dict[str, Any]:
        """使用AI一次性完成routine分析"""
        # 1) 依赖数据
        llm_service = self.app_controller.get_service(ServiceNames.LLM)
        end_time = weekly_raw.get("end_time")
        start_time = weekly_raw.get("start_time")
        ignore_year = start_time.year == end_time.year
        if ignore_year:
            time_str_mark = "%m-%d %H:%M"
        else:
            time_str_mark = "%Y-%m-%d %H:%M"
        user_id = weekly_raw.get("user_id")

        current_week_key = end_time.strftime("%y%m%d") if end_time else ""
        prev_week_key = (
            (end_time - timedelta(days=7)).strftime("%y%m%d") if end_time else ""
        )

        # 2) 数据一：本周明细CSV
        event_detail_df = weekly_document.get("event_detail")
        # 去掉 start_dt 和 end_dt 的秒，向量化处理
        if "start_dt" in event_detail_df.columns:
            event_detail_df = event_detail_df.copy()
            event_detail_df["start_dt"] = pd.to_datetime(
                event_detail_df["start_dt"]
            ).dt.strftime(time_str_mark)
        if "end_dt" in event_detail_df.columns:
            event_detail_df["end_dt"] = pd.to_datetime(
                event_detail_df["end_dt"]
            ).dt.strftime(time_str_mark)
        current_week_detail_data_csv = event_detail_df.to_csv(index=False)

        # 数据二：本周摘要CSV
        event_summary_df = weekly_document.get("event_summary")
        summary_df = event_summary_df[
            [
                "category",
                "event_name",
                "degree",
                "degree_interval_minutes",
                "category_interval_minutes",
            ]
        ].copy()
        # 对 interval 列做 round(1)
        summary_df["degree_interval_minutes"] = summary_df[
            "degree_interval_minutes"
        ].round(1)
        summary_df["category_interval_minutes"] = summary_df[
            "category_interval_minutes"
        ].round(1)
        summary_df.rename(
            columns={"category_interval_minutes": "event_interval_minutes"},
            inplace=True,
        )
        current_week_summary_data_csv = summary_df.to_csv(index=False)

        # 3) 数据三：上一周分析（不包含accepted）
        weekly_record_file = self.routine_business.load_weekly_record(user_id)
        weekly_record_map = weekly_record_file.get("weekly_record", {})

        prev_week_analysis = weekly_record_map.get(prev_week_key, {}) or {}

        prev_week_analysis_clean = (
            copy.deepcopy(prev_week_analysis)
            if isinstance(prev_week_analysis, dict)
            else {}
        )
        prev_week_analysis_clean.pop("strategic_action_suggestions", None)

        previous_week_analysis_json_str = json.dumps(
            prev_week_analysis_clean, ensure_ascii=False
        )

        # 4) 数据四：反馈历史（仅历史周，包含内容+week_key+accepted，不含ID）
        user_feedback_history = []
        # 仅收集严格小于prev_week_key的周
        for wk, node in weekly_record_map.items():
            if prev_week_key and int(wk) > int(prev_week_key):
                continue

            analysis_node = node

            suggestions_hist = (analysis_node or {}).get(
                "strategic_action_suggestions", []
            )
            for item in suggestions_hist:
                entry = {
                    "week_key": wk,
                    "accepted": item.get("accepted", True),
                    "properties": {
                        "spice_type": item.get("spice_type"),
                        "title": item.get("title"),
                        "reasoning": item.get("reasoning"),
                        "specific_action": item.get("specific_action"),
                        "expected_outcome": item.get("expected_outcome"),
                    },
                }
                user_feedback_history.append(entry)

        user_feedback_history_json_str = json.dumps(
            user_feedback_history, ensure_ascii=False
        )

        # 5) 构建提示词
        prompt = f"""请根据以下数据，执行一次完整的周度分析。
特别注意，过往建议的反馈采纳历史包含了所有的状况，用来让你指定新的行动建议，但回顾上周行动（previous_actions_review）只需要对上一周{prev_week_key}的进行回顾。

### 数据一：本周原始事件日志 (带时间戳的原子数据，{prev_week_key}为周一；注意其中可能会包含用户在记录时的备注note，这也是比较重要的线索)
```csv
{current_week_detail_data_csv}
```
### 数据二：本周关键节律的精确计算摘要 (辅助事实)
这是代码预计算的节律数据，请将其作为你进行深度解读的“事实基础”，而不是让你重复计算。你需要解释这些节律背后的原因和意义。
```csv
{current_week_summary_data_csv}
```

### 数据三：上一周的分析报告 (JSON格式，若为第一周则为空)
```json
{previous_week_analysis_json_str}
```

### 数据四：过往每周建议和用户的采纳情况 (JSON格式)
```json
{user_feedback_history_json_str}
```
"""

        unrecorded_df = weekly_document.get("unrecorded_df", []).to_dict(
            orient="records"
        )

        unrecorded_str = ""
        for record in unrecorded_df:
            duration = record["duration_minutes"]
            if duration < 5:
                continue
            start = str(record["start_time"])[:16]
            before = record["source_event"]["before"]
            after = record["source_event"]["after"]
            unrecorded_str += f"\n{start} {before} -> {after} 持续{duration}分钟"

        if unrecorded_str:
            prompt += f"\n### 数据五：未记录明细\n```{unrecorded_str}\n```"

        prompt += "\n请严格按照你在系统指令中被赋予的角色和原则，完成本次分析，并以指定的JSON Schema格式返回结果。"

        # 6) 调用LLM
        result = llm_service.structured_call(
            prompt=prompt,
            response_schema=self._build_routine_response_schema(),
            system_instruction=self._build_routine_system_instruction(),
            temperature=1,
        )

        # 处理结果
        if "error" in result:
            return {
                "analyst_foreword": f"AI分析失败: {result['error']}",
                "core_narrative": {},
                "rhythm_analysis": [],
                "hidden_data_insights": [],
                "previous_actions_review": {},
                "strategic_action_suggestions": [],
            }

        # 修正：原代码变量名错误，未定义index，且未将修改后的result保存到result_to_save
        # 正确做法：用ind作为索引，且应将result赋值给result_to_save
        for action_id, item in enumerate(
            result.get("strategic_action_suggestions", [])
        ):
            item["accepted"] = True
            item["id"] = f"{current_week_key}_{action_id}"

        report_method = self.REPORT_MODE

        match report_method:
            case "print":
                print("report-prompt", prompt)
                print(
                    "\nreport-system_prompt", self.AI_ROUTINE_ANALYSIS_BASE_INSTRUCTION
                )
                print("\nreport-response_schema", self._build_routine_response_schema())
            case "save":
                result_to_save = result  # 确保保存的是本次分析结果

                weekly_record_map[current_week_key] = result_to_save
                weekly_record_file["weekly_record"] = weekly_record_map
                weekly_record_file["last_updated"] = datetime.now().strftime(
                    "%Y-%m-%d %H:%M"
                )
                self.routine_business.save_weekly_record(user_id, weekly_record_file)
            case _:
                pass

        return result

    AI_ROUTINE_ANALYSIS_BASE_INSTRUCTION = """
# 角色与核心哲学
你是一个名为“数字分身分析师”的有洞察力、能适应、懂共情的顶尖分析师，专精于个人时间管理、行为模式分析和战略性生活规划。
你的核心使命是作为用户的“数字映射”和战略伙伴，通过深度分析其时间数据，帮助用户更好地理解自己，并找到成为更优自我的独特路径。
你的所有分析和建议**必须使用第二人称（‘你’、‘你的’）来称呼用户**，营造一种直接对话、为你服务的专属感。
你尊重用户的自主性，并将用户的反馈历史视为理解其个人偏好的“最高宪法”。

# 核心分析原则
1.  **进化式洞察**：分析必须具有连续性，将本周与过去的数据和反馈联系起来，揭示用户的成长和变化。
2.  **动态框架应用**：
你拥有一个包含多种心理学、行为学理论（如心流、精力管理、人物原型等）的分析工具箱。
你应在数据呈现出与某个模型高度相关时，**机会性地、创造性地**加以应用，并**确保分析视角的新颖性**，避免短期内重复。
3.  **反馈优先与演化识别**：
在处理用户反馈历史时，若出现冲突，**永远以最新的反馈为准**。
更重要的是，你必须**识别并高亮这种“偏好转变”**，将其作为用户个人系统进化的宝贵信号进行解读。
4.  **动机推断**：
你必须尝试推断其背后可能的动机或心理状态。你需要提出这种假设性解释，但注意不要用解释性的语气来描述，而是为你服务的用户提供一些潜在感受视角的方式。
5.  **S.P.I.C.E.多样性策略**：在提出新建议时，你应有意识地确保多样性，除非用户当前的数据里有显著有偏向性的信号，否则应尽可能覆盖以下一个或多个维度：系统(S)、模式(P)、洞察(I)、连接(C)、精力(E)。
6.  **回避用户反感的叙事**: 用户明确表示不接受中医、排毒等非询证医学的理由，不要基于这些角度阐述，这会让用户降低对你和报告的信任。

# 核心任务清单 (Task Checklist)
你必须严格按照以下清单顺序，完成分析并组织你的输出。

1.  **生成分析师前言 (`analyst_foreword`)**: 基于用户反馈历史，总结你本次分析将遵循的核心原则和看点。
2.  **提炼核心叙事 (`core_narrative`)**: 识别并总结本周最主要的故事线。如果数据特征显著，可选择一个动态分析框架进行深度解读并写入`dynamic_framework_insight`。
3.  **进行节律性分析 (`rhythm_analysis`)**:
基于`数据一`中的时序信息，并结合`数据二`中提供的精确节律计算结果，进行深度解读。
你的任务不是重复计算，而是**解释这些数字节律背后的行为模式、情境和意义，避免复述原始数据**。
你的分析必须基于事件的精确时间顺序，关注‘A事件之后发生了什么’这样的行为链条，而不仅仅是事件的频率。
记录的时序倾向于保留完整原始信息而不自动处理重叠区域，因而可能会存在多个事件在同一段时间发生，此时后开始的事件表示当前最新状况。
举例：在23:40开始了睡觉，到次日08:10结束，持续8小时，又在23:50-00:20 刷了B站，这并不是说睡醒后又在凌晨刷B站，而是大概率没入睡，在00:20-00:50刷完B站后才睡。
4.  **挖掘隐藏数据洞察 (`hidden_data_insights`)**:
深入分析备注、异常时长、分类等细节，找出至少2-3个有价值的深层发现。
特别关注那些打破常规模式的事件链，例如‘长时间工作后的异常娱乐选择’或‘特定用餐后的精力变化’。
你必须检查数据中包含的非0值的target_value和非空check_cycle的目标设定。你的任务不是报告完成度，而是去发现“目标与现实的冲突”。
如果一个设定了周期目标（如check_cycle: '天'）的活动，在某个周期内没有被执行或执行次数不足，亦或者执行次数远超目标，你应将其作为一个的“隐藏洞察”，并深入分析造成这种偏差的可能原因或对其他的影响，以及它揭示了关于我的何种行为偏好或内在冲突。
如果提供的数据中包括明确的未记录的时间段，这部分信息是并不是用户故意不记录，而是系统根据用户的记录时间表自动生成的，分析其中可能的规律，背后的原因和可能的解决方案，如果有所发现，请写入到报告里。
5.  **回顾上周行动 (`previous_actions_review`)**: 评估用户对上周建议的采纳与执行情况。如果发现用户偏好发生变化，必须在`feedback_evolution_note`中进行说明。
6.  **设计战略性行动建议 (`strategic_action_suggestions`)**: 基于以上所有分析，尤其是用户对过往每周行动建议的采纳情况，为用户提供5个全新的、具体的、可行的建议。并评估建议的执行挑战难度，以及哪怕不执行的最小可行动作。

# 输出要求
你的所有输出**必须且只能是**一个严格遵循用户提供的`response_schema`的、单一、有效的JSON对象。禁止在JSON之外添加任何说明性文字或标记。
"""

    def _build_routine_system_instruction(self) -> str:
        """构建系统提示词"""
        return self.AI_ROUTINE_ANALYSIS_BASE_INSTRUCTION

    def _build_routine_response_schema(self) -> Dict[str, Any]:
        """
        构建新版routine分析响应schema，采用三层结构，去除元数据内容的生成，交由业务代码处理
        每个object类型都显式声明required
        """
        return {
            "type": "object",
            "properties": {
                "analyst_foreword": {
                    "type": "string",
                    "description": "分析师基于用户反馈总结的核心原则和本次报告的看点。",
                },
                "core_narrative": {
                    "type": "object",
                    "description": "本周的核心故事线和高层洞察",
                    "properties": {
                        "theme": {
                            "type": "string",
                            "description": "本周核心主题，如“从极限冲刺到带病续航的系统性调整”",
                        },
                        "narrative_summary": {
                            "type": "string",
                            "description": "对本周故事线的详细阐述，连接关键事件和发现。",
                        },
                        "dynamic_framework_insight": {
                            "type": "object",
                            "description": "（可选）当数据触发时，应用的动态分析框架洞察。",
                            "properties": {
                                "framework_name": {
                                    "type": "string",
                                    "description": "所使用的分析框架名称，如“心流理论”",
                                },
                                "insight": {
                                    "type": "string",
                                    "description": "基于该框架的深度解读。",
                                },
                                "relevance_score": {
                                    "type": "integer",
                                    "minimum": 0,
                                    "maximum": 10,
                                    "description": "该分析框架与本周数据的相关性强度评分(0-10，10为最相关)",
                                },
                            },
                            "required": [
                                "framework_name",
                                "insight",
                                "relevance_score",
                            ],
                        },
                    },
                    "required": ["theme", "narrative_summary"],
                    # dynamic_framework_insight为可选
                },
                "rhythm_analysis": {
                    "type": "object",
                    "description": "节律性分析与预测",
                    "properties": {
                        "identified_rhythms": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "potential_new_rhythms": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "prediction": {"type": "string"},
                    },
                    "required": [
                        "identified_rhythms",
                        "potential_new_rhythms",
                        "prediction",
                    ],
                },
                "hidden_data_insights": {
                    "type": "array",
                    "description": "从数据细节中挖掘出的深层价值",
                    "items": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string"},
                            "finding": {"type": "string"},
                        },
                        "required": ["title", "finding"],
                    },
                },
                "previous_actions_review": {
                    "type": "object",
                    "description": "对上周行动建议的评估",
                    "properties": {
                        "feedback_evolution_note": {
                            "type": "string",
                            "description": "（可选）当检测到用户偏好发生转变时的特别说明。",
                        },
                        "detailed_review": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "suggestion_id": {"type": "string"},
                                    "user_choice": {"type": "boolean"},
                                    "analyst_assessment": {"type": "string"},
                                },
                                "required": [
                                    "suggestion_id",
                                    "user_choice",
                                    "analyst_assessment",
                                ],
                            },
                        },
                    },
                    "required": ["detailed_review"],
                    # feedback_evolution_note为可选
                },
                "strategic_action_suggestions": {
                    "type": "array",
                    "description": "为下周设计的五个战略性行动建议",
                    "items": {
                        "type": "object",
                        "properties": {
                            "spice_type": {
                                "type": "string",
                                "enum": [
                                    "System",
                                    "Pattern",
                                    "Insight",
                                    "Connection",
                                    "Energy",
                                ],
                            },
                            "title": {"type": "string"},
                            "reasoning": {"type": "string"},
                            "specific_action": {"type": "string"},
                            "expected_outcome": {"type": "string"},
                            "execution_difficulty": {
                                "type": "string",
                                "enum": ["低", "中", "高"],
                            },
                            "minimum_action": {"type": "string"},
                        },
                        "required": [
                            "spice_type",
                            "title",
                            "reasoning",
                            "specific_action",
                            "expected_outcome",
                            "execution_difficulty",
                            "minimum_action",
                        ],
                    },
                    "minItems": 5,
                    "maxItems": 5,
                },
            },
            "required": [
                "analyst_foreword",
                "core_narrative",
                "rhythm_analysis",
                "hidden_data_insights",
                "previous_actions_review",
                "strategic_action_suggestions",
            ],
        }

    # endregion

    # region 辅助方法

    def _extract_all_event_fields(self, row):
        """一次性从row中提取所有事件相关字段"""
        properties = row["properties"]
        interval_type = properties.get("interval_type", "degree")
        target_value = properties.get("target_value", 0)
        check_cycle = properties.get("check_cycle", None)

        return pd.Series([interval_type, target_value, check_cycle])

    def _calc_avg_interval(self, times):
        """计算平均间隔（分钟），times为升序datetime字符串列表"""
        if len(times) < 2:
            return np.nan
        times = pd.to_datetime(times)
        intervals = (times[1:].values - times[:-1].values) / np.timedelta64(1, "m")
        return np.mean(intervals) if len(intervals) > 0 else np.nan

    def _get_max_start_at(self, subdf):
        """获取duration最大值对应的start_at"""
        if subdf.empty:
            return ""
        idx = subdf["duration_minutes"].idxmax()
        return subdf.loc[idx, "start_dt"] if idx in subdf.index else ""

    def _format_note_info(self, row, current_year: int):
        # 处理分类
        category = (
            row["category"]
            if pd.notnull(row["category"]) and row["category"] != ""
            else ""
        )
        # 处理事件名
        event_name = (
            row["event_name"]
            if pd.notnull(row["event_name"]) and row["event_name"] != ""
            else ""
        )
        # 处理degree
        degree = (
            row["degree"] if pd.notnull(row["degree"]) and row["degree"] != "" else None
        )
        # 处理进度
        progress = (
            row["progress_value"]
            if "progress_value" in row
            and pd.notnull(row["progress_value"])
            and row["progress_value"] != ""
            else None
        )
        # 处理备注
        note = row["note"] if pd.notnull(row["note"]) else ""
        # 拼接degree部分，空则不显示括号
        if degree:
            degree_str = f"({degree})"
        else:
            degree_str = ""

        start_time = (
            row["start_dt"]
            if pd.notnull(row["start_dt"]) and row["start_dt"] != ""
            else ""
        )
        if start_time.year == current_year:
            start_time_str = start_time.strftime("%m-%d %H:%M")
        else:
            start_time_str = start_time.strftime("%Y-%m-%d %H:%M")
        # 拼接头部
        if category:
            head = f"[{start_time_str} 耗时{row['duration_minutes']}分] [{category}] {event_name} {degree_str}"
        else:
            head = f"[{start_time_str} 耗时{row['duration_minutes']}分] {event_name} {degree_str}"
        head = head.rstrip()  # 去除多余空格
        # 拼接进度
        progress_str = f" | 进度:{progress}" if progress else ""
        # 拼接备注
        note_str = f" | 备注:{note}" if note else ""
        # 最终拼接
        return f"{head}{progress_str}{note_str}"

    # endregion
