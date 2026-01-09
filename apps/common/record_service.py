from datetime import datetime, timedelta
from typing import Any, Dict, List
from pydantic import BaseModel, Field

from libs.storage_lib import global_storage

class RecordService:
    @staticmethod
    async def save_keep_event(user_id: str, event_type: str, event_data: Dict[str, Any]):
        """
        保存 Keep 事件（体重 scale / 睡眠 sleep / 围度 dimensions）
        文件名按月归档，例如 keep_scale_2023_10.jsonl
        """
        now = datetime.now()
        month_str = now.strftime("%Y_%m")
        filename = f"{event_type}_{month_str}.jsonl"
        
        # 增加 type 字段方便索引
        event_data["event_type"] = event_type
        
        global_storage.append(
            user_id=user_id,
            category="keep",
            filename=filename,
            data=event_data
        )
        return {"saved_to": filename, "status": "success"}

    @staticmethod
    async def save_diet_record(user_id: str, meal_summary: Dict, dishes: List[Dict], captured_labels: List[Dict]):
        """
        保存饮食记录。这是核心业务逻辑：拆分保存。
        1. dishes -> records (日记)
        2. captured_labels -> library (标签库)
        """
        now = datetime.now()
        date_str = now.strftime("%Y-%m-%d")
        
        # 1. 保存流水 (Ledger)
        ledger_entry = {
            "type": "diet_log",
            "meal_summary": meal_summary,
            "dishes": dishes,
            # 将 label 也冗余存一份在流水里，保证历史可回溯
            "labels_snapshot": captured_labels 
        }
        
        global_storage.append(
            user_id=user_id,
            category="diet",
            filename=f"ledger_{date_str}.jsonl",
            data=ledger_entry
        )

        # 2. 保存标签库 (Knowledge Base) - 不按日期，按单一文件追加
        # 简单去重逻辑可以在这里做，或者是单纯追加，读取时去重
        for label in captured_labels:
            global_storage.append(
                user_id=user_id,
                category="diet",
                filename="product_library.jsonl",
                data=label
            )
            
        return {"status": "success", "items_count": len(dishes), "labels_archived": len(captured_labels)}

    @staticmethod
    def get_todays_diet_records(user_id: str) -> List[Dict[str, Any]]:
        """
        获取今日已记录的饮食流水（倒序，最新的在前）
        """
        now = datetime.now()
        date_str = now.strftime("%Y-%m-%d")
        return global_storage.read_dataset(
            user_id=user_id, 
            category="diet", 
            filename=f"ledger_{date_str}.jsonl",
            limit=100
        )

    @staticmethod
    def get_recent_diet_records(user_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        """
        获取最近的饮食记录（跨越过去 7 天查找，填满 limit 为止）
        """
        
        all_records = []
        now = datetime.now()
        
        # Look back 7 days
        for i in range(7):
            if len(all_records) >= limit:
                break
                
            day_cursor = now - timedelta(days=i)
            date_str = day_cursor.strftime("%Y-%m-%d")
            
            day_records = global_storage.read_dataset(
                user_id=user_id, 
                category="diet", 
                filename=f"ledger_{date_str}.jsonl",
                limit=limit - len(all_records)
            )
            
            all_records.extend(day_records)
            
        return all_records[:limit]
