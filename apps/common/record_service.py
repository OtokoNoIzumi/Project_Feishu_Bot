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
            
        # 5. 保存菜式库 (Personal Dish Library) - For UI Quick Add, not for LLM Context
        # Automatically calculate per-100g normalization
        RecordService._archive_dishes_to_library(user_id, dishes)

        return {"status": "success", "action": status_msg, "items_count": len(dishes), "labels_upserted": len(captured_labels)}

    @staticmethod
    def _archive_dishes_to_library(user_id: str, dishes: List[Dict]):
        """
        将非标品菜式（Dish）归一化后存入 dish_library.jsonl。
        供 UI 层做数据分析和快捷录入。
        """
        filename = "dish_library.jsonl"
        
        for dish in dishes:
            name = dish.get("standard_name")
            if not name:
                continue

            # [Filter] 只存档纯估算的菜式。如果包含 label_ocr (标品/包装食品)，跳过。
            has_ocr = False
            for ing in dish.get("ingredients", []):
                if ing.get("data_source") == "label_ocr":
                    has_ocr = True
                    break
            if has_ocr:
                continue
                
            # Aggregate totals
            d_weight = 0.0
            d_energy = 0.0
            d_p = 0.0
            d_f = 0.0
            d_c = 0.0
            d_na = 0.0
            d_fib = 0.0
            
            valid_calc = True
            for ing in dish.get("ingredients", []):
                w = float(ing.get("weight_g") or 0)
                d_weight += w
                
                d_energy += float(ing.get("energy_kj") or 0)
                
                m = ing.get("macros", {})
                d_p += float(m.get("protein_g") or 0)
                d_f += float(m.get("fat_g") or 0)
                d_c += float(m.get("carbs_g") or 0)
                d_na += float(m.get("sodium_mg") or 0)
                d_fib += float(m.get("fiber_g") or 0)
                
            if d_weight <= 0:
                continue
                
            # Normalize to per 100g
            ratio = 100.0 / d_weight
            
            entry = {
                "dish_name": name,
                "recorded_weight_g": round(d_weight, 2),
                "macros_per_100g": {
                    "energy_kj": round(d_energy * ratio, 2),
                    "protein_g": round(d_p * ratio, 2),
                    "fat_g": round(d_f * ratio, 2),
                    "carbs_g": round(d_c * ratio, 2),
                    "sodium_mg": round(d_na * ratio, 2),
                    "fiber_g": round(d_fib * ratio, 2)
                },
                "ingredients_snapshot": [i.get("name_zh") for i in dish.get("ingredients", [])],
                "created_at": datetime.now().isoformat()
            }
            
            global_storage.append(user_id, "diet", filename, entry)

    @staticmethod
    def get_todays_diet_records(user_id: str) -> List[Dict[str, Any]]:
        """
        获取今日已记录的饮食流水（倒序，最新的在前）
        """
        now = datetime.now()
        date_str = now.strftime("%Y-%m-%d")
        return RecordService.get_diet_records_by_date(user_id, date_str)

    @staticmethod
    def get_diet_records_by_date(user_id: str, date_str: str) -> List[Dict[str, Any]]:
        """
        获取指定日期的饮食流水
        """
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

    @staticmethod
    def get_diet_records_range(user_id: str, start_date: str, end_date: str) -> List[Dict[str, Any]]:
        """
        获取指定日期范围内的饮食记录（包含 start 和 end）。
        返回顺序：按时间正序排列（Oldest -> Newest），方便报表生成。
        """
        try:
            start = datetime.strptime(start_date, "%Y-%m-%d")
            end = datetime.strptime(end_date, "%Y-%m-%d")
        except ValueError:
            return []
        
        all_records = []
        delta = end - start
        
        # 遍历日期范围
        for i in range(delta.days + 1):
            day = start + timedelta(days=i)
            day_str = day.strftime("%Y-%m-%d")
            
            # 读取该日所有记录
            day_recs = global_storage.read_dataset(user_id, "diet", f"ledger_{day_str}.jsonl", limit=9999)
            
            # read_dataset 返回倒序（新->旧），我们需要正序（旧->新）拼接
            all_records.extend(reversed(day_recs))
            
        return all_records
