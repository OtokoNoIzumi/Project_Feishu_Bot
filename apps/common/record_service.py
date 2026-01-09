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
    async def save_diet_record(user_id: str, meal_summary: Dict, dishes: List[Dict], captured_labels: List[Dict], image_hashes: List[str] = None):
        """
        保存饮食记录。包含智能去重逻辑：
        1. 如果 image_hashes 完全一致 -> 视为修正，覆盖旧记录。
        2. 否则 -> 追加新记录。
        
        同时对 product_library 进行 Upsert（基于 Brand+Name+Variant），确保同一产品只保留最新数据。
        """
        now = datetime.now()
        date_str = now.strftime("%Y-%m-%d")
        filename = f"ledger_{date_str}.jsonl"
        
        new_record = {
            "type": "diet_log",
            "meal_summary": meal_summary,
            "dishes": dishes,
            "labels_snapshot": captured_labels,
            "image_hashes": image_hashes or [],
            "created_at": now.isoformat()
        }
        
        # 1. 读取今日所有记录 (read_dataset 返还倒序，需反转为正序处理)
        existing = global_storage.read_dataset(user_id, "diet", filename, limit=1000)
        existing = list(reversed(existing))
        
        replaced_index = -1
        
        # 2. 遍历查找是否有需要覆盖的目标 (Ledger Deduplication)
        for i, rec in enumerate(existing):
            # A. 强特征：图片 Hash 完全一致
            if image_hashes and rec.get("image_hashes"):
                h1 = set(image_hashes)
                h2 = set(rec["image_hashes"])
                if h1 == h2:
                    replaced_index = i
                    break
        
        # 3. 执行写入 (Ledger Write)
        if replaced_index != -1:
            # 覆盖模式
            existing[replaced_index] = new_record
            global_storage.write_dataset(user_id, "diet", filename, existing)
            status_msg = "updated"
        else:
            # 追加模式
            global_storage.append(user_id, "diet", filename, new_record)
            status_msg = "appended"

        # 4. 保存标签库 (Knowledge Base) - Upsert (按 Brand+Name+Variant 去重)
        if captured_labels:
            lib_file = "product_library.jsonl"
            # 读取现有库 (limit=2000, 假设长期积累需考虑性能优化，目前全读覆盖)
            # read_dataset returns [Newest, ..., Oldest]
            existing_lib = global_storage.read_dataset(user_id, "diet", lib_file, limit=2000)
            existing_lib = list(reversed(existing_lib)) # -> [Oldest, ..., Newest]
            
            new_keys = set()
            for l in captured_labels:
                # Key: (Brand, Product Name, Variant)
                k = (
                    str(l.get('brand','')).strip(), 
                    str(l.get('product_name','')).strip(), 
                    str(l.get('variant','')).strip()
                )
                if k != ('','',''): # Ignore empty keys
                    new_keys.add(k)
            
            final_lib = []
            
            # 保留不冲突的旧数据
            for old in existing_lib:
                k_old = (
                    str(old.get('brand','')).strip(), 
                    str(old.get('product_name','')).strip(), 
                    str(old.get('variant','')).strip()
                )
                # 如果旧数据的 Key 在本次新标签中存在，则丢弃旧数据（用新的替代）
                if k_old not in new_keys:
                    final_lib.append(old)
            
            # 追加新数据
            final_lib.extend(captured_labels)
            
            # 覆写文件
            global_storage.write_dataset(user_id, "diet", lib_file, final_lib)
            
        return {"status": "success", "action": status_msg, "items_count": len(dishes), "labels_upserted": len(captured_labels)}

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
