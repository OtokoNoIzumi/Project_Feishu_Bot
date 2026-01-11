import hashlib
from datetime import datetime, timedelta
from typing import Any, Dict, List
from pydantic import BaseModel, Field

from libs.storage_lib import global_storage


class RecordService:
    @staticmethod
    async def save_keep_event(
        user_id: str,
        event_type: str,
        event_data: Dict[str, Any],
        image_hashes: List[str] = None,
        occurred_at: datetime = None,
        record_id: str = None,
    ):
        """
        保存 Keep 事件（体重 scale / 睡眠 sleep / 围度 dimensions）
        occurred_at: 事件发生时间。决定了文件名归档。
        record_id: 如提供则用于更新已有记录。
        """
        now = datetime.now()
        business_time = occurred_at if occurred_at else now

        month_str = business_time.strftime("%Y_%m")
        filename = f"{event_type}_{month_str}.jsonl"

        # 生成新的 record_id（如果没有提供）
        if not record_id:
            hash_str = "_".join(sorted(image_hashes or [])) + now.isoformat()
            record_id = hashlib.md5(hash_str.encode()).hexdigest()[:12]

        # 增加 type 字段方便索引
        event_data["event_type"] = event_type
        event_data["record_id"] = record_id

        # 元数据：创建时间 (System Time)
        if "created_at" not in event_data:
            event_data["created_at"] = now.isoformat()

        # 业务数据：发生时间 (Business Time)
        event_data["occurred_at"] = business_time.isoformat()

        if image_hashes:
            event_data["image_hashes"] = image_hashes

        # 1. 读取当月所有记录
        existing = global_storage.read_dataset(user_id, "keep", filename, limit=1000)
        existing = list(
            reversed(existing)
        )  # fix order to Oldest->Newest for processing

        replaced_index = -1

        # 2. 去重检查
        for i, rec in enumerate(existing):
            # A. 最优先：record_id 完全一致
            if record_id and rec.get("record_id") == record_id:
                replaced_index = i
                break
            # B. 次优先：图片 Hash 完全一致
            if image_hashes and rec.get("image_hashes"):
                h1 = set(image_hashes)
                h2 = set(rec["image_hashes"])
                if h1 == h2:
                    replaced_index = i
                    break

        # 3. 写入
        if replaced_index != -1:
            # 保留原始 created_at
            original_created = existing[replaced_index].get("created_at")
            if original_created:
                event_data["created_at"] = original_created
            event_data["updated_at"] = now.isoformat()
            existing[replaced_index] = event_data
            global_storage.write_dataset(user_id, "keep", filename, existing)
            return {"saved_to": filename, "status": "updated", "record_id": record_id}
        else:
            global_storage.append(
                user_id=user_id, category="keep", filename=filename, data=event_data
            )
            return {"saved_to": filename, "status": "appended", "record_id": record_id}

    @staticmethod
    async def save_diet_record(
        user_id: str,
        meal_summary: Dict,
        dishes: List[Dict],
        captured_labels: List[Dict],
        image_hashes: List[str] = None,
        occurred_at: datetime = None,
        record_id: str = None,
    ):
        """
        保存饮食记录。包含智能去重逻辑：
        1. 如果 record_id 已提供 -> 通过 record_id 匹配更新
        2. 如果 image_hashes 完全一致 -> 视为修正，覆盖旧记录。
        3. 否则 -> 追加新记录。
        occurred_at: 饮食发生时间，用于补录历史数据。如果不传则默认为当前时间。

        同时对 product_library 进行 Upsert（基于 Brand+Name+Variant），确保同一产品只保留最新数据。
        """
        
        now = datetime.now()
        business_time = occurred_at if occurred_at else now

        date_str = business_time.strftime("%Y-%m-%d")
        filename = f"ledger_{date_str}.jsonl"

        # 生成新的 record_id（如果没有提供）
        if not record_id:
            # 使用 image_hashes + timestamp 生成唯一 ID
            hash_str = "_".join(sorted(image_hashes or [])) + now.isoformat()
            record_id = hashlib.md5(hash_str.encode()).hexdigest()[:12]

        new_record = {
            "type": "diet_log",
            "record_id": record_id,
            "meal_summary": meal_summary,
            "dishes": dishes,
            "labels_snapshot": captured_labels,
            "image_hashes": image_hashes or [],
            "created_at": now.isoformat(),  # System Time
            "occurred_at": business_time.isoformat(),  # Business Time
        }

        # 1. 读取该日所有记录 (read_dataset 返还倒序，需反转为正序处理)
        existing = global_storage.read_dataset(user_id, "diet", filename, limit=1000)
        existing = list(reversed(existing))

        replaced_index = -1

        # 2. 遍历查找是否有需要覆盖的目标 (Ledger Deduplication)
        for i, rec in enumerate(existing):
            # A. 最优先：record_id 完全一致
            if record_id and rec.get("record_id") == record_id:
                replaced_index = i
                break
            # B. 次优先：图片 Hash 完全一致
            if image_hashes and rec.get("image_hashes"):
                h1 = set(image_hashes)
                h2 = set(rec["image_hashes"])
                if h1 == h2:
                    replaced_index = i
                    break

        # 3. 执行写入 (Ledger Write)
        if replaced_index != -1:
            # 覆盖模式 - 保留原始 created_at
            original_created = existing[replaced_index].get("created_at")
            if original_created:
                new_record["created_at"] = original_created
            new_record["updated_at"] = now.isoformat()
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
            existing_lib = global_storage.read_dataset(
                user_id, "diet", lib_file, limit=2000
            )
            existing_lib = list(reversed(existing_lib))  # -> [Oldest, ..., Newest]

            new_keys = set()
            for l in captured_labels:
                # Key: (Brand, Product Name, Variant)
                k = (
                    str(l.get("brand", "")).strip(),
                    str(l.get("product_name", "")).strip(),
                    str(l.get("variant", "")).strip(),
                )
                if k != ("", "", ""):  # Ignore empty keys
                    new_keys.add(k)

            final_lib = []

            # 保留不冲突的旧数据
            for old in existing_lib:
                k_old = (
                    str(old.get("brand", "")).strip(),
                    str(old.get("product_name", "")).strip(),
                    str(old.get("variant", "")).strip(),
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

        return {
            "status": "success",
            "action": status_msg,
            "record_id": record_id,
            "items_count": len(dishes),
            "labels_upserted": len(captured_labels),
        }

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
                    "fiber_g": round(d_fib * ratio, 2),
                },
                "ingredients_snapshot": [
                    i.get("name_zh") for i in dish.get("ingredients", [])
                ],
                "created_at": datetime.now().isoformat(),
            }

            global_storage.append(user_id, "diet", filename, entry)

    @staticmethod
    def get_todays_unified_records(user_id: str) -> List[Dict[str, Any]]:
        """
        获取今日已记录的综合流水（倒序，最新的在前）
        """
        now = datetime.now()
        date_str = now.strftime("%Y-%m-%d")
        return RecordService.get_unified_records_by_date(user_id, date_str)

    @staticmethod
    def _read_keep_records_for_period(
        user_id: str, start_dt: datetime, end_dt: datetime
    ) -> List[Dict[str, Any]]:
        """
        Helper: 读取指定时间段内的 Keep 记录 (Scale, Sleep, Dimensions)
        """
        # 1. 计算涉及的月份
        months = set()
        curr = start_dt
        while curr <= end_dt:
            months.add(curr.strftime("%Y_%m"))
            # increment by month logic (rough approx by 28 days is safer for loop, or logic calc)
            next_month = (curr.replace(day=1) + timedelta(days=32)).replace(day=1)
            if curr.month == 12:  # simple logic to just jump
                pass
            curr = next_month

        # Edge case: end_dt month might be missed if loop jumps over, ensure end_dt is covered
        months.add(end_dt.strftime("%Y_%m"))

        keep_types = ["scale", "sleep", "dimensions"]
        all_keep = []

        for m in months:
            for ktype in keep_types:
                fname = f"{ktype}_{m}.jsonl"
                recs = global_storage.read_dataset(user_id, "keep", fname, limit=500)
                all_keep.extend(recs)

        # Filter by exact range
        filtered = []
        for r in all_keep:
            # Strictly use occurred_at
            t_str = r.get("occurred_at")
            if not t_str:
                continue

            # Removed redundant try-except: stored data format is reliable.
            t = datetime.fromisoformat(t_str)
            # Ensure TZ-naive comparison if needed
            if t.tzinfo is not None:
                t = t.replace(tzinfo=None)

            if start_dt <= t <= end_dt:
                filtered.append(r)

        return filtered

    @staticmethod
    def get_unified_records_by_date(
        user_id: str, date_str: str
    ) -> List[Dict[str, Any]]:
        """
        获取指定日期的综合流水（Diet + Keep）
        """
        return RecordService.get_unified_records_range(user_id, date_str, date_str)

    @staticmethod
    def get_recent_unified_records(
        user_id: str, limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        获取最近的记录流水（饮食+Keep），逻辑基于 get_unified_records_range
        """
        now = datetime.now()
        start_date = (now - timedelta(days=7)).strftime("%Y-%m-%d")
        end_date = now.strftime("%Y-%m-%d")

        # Get unified history
        full_history = RecordService.get_unified_records_range(
            user_id, start_date, end_date
        )

        # Returns Oldest->Newest, so we slice the tail to get most recent
        if not full_history:
            return []

        return full_history[-limit:]

    @staticmethod
    def get_diet_records_range(
        user_id: str, start_date: str, end_date: str
    ) -> List[Dict[str, Any]]:
        """
        [Pure] 仅获取指定日期范围内的饮食记录 (Diet Log Only)。
        用于 get_unified_records_range 内部调用或仅需饮食数据的场景。
        """
        try:
            start = datetime.strptime(start_date, "%Y-%m-%d")
            end = datetime.strptime(end_date, "%Y-%m-%d")
        except ValueError:
            return []

        records = []
        delta = end - start

        for i in range(delta.days + 1):
            day = start + timedelta(days=i)
            day_str = day.strftime("%Y-%m-%d")
            # 读取该日所有记录
            day_recs = global_storage.read_dataset(
                user_id, "diet", f"ledger_{day_str}.jsonl", limit=9999
            )

            # Inject source date for reliable filtering later (fixes backfill issue)
            # We trust the filename date over created_at for determining "which day this belongs to"
            for r in day_recs:
                r["_source_date"] = day_str

            records.extend(reversed(day_recs))

        return records

    @staticmethod
    def get_unified_records_range(
        user_id: str, start_date: str, end_date: str
    ) -> List[Dict[str, Any]]:
        """
        获取指定日期范围内的【所有类型】记录（饮食 + Keep）。
        包含：
        1. 原始饮食记录 (Filter by occurred_at > _source_date)
        2. Keep 运动/睡眠/围度记录 (Filter by occurred_at > created_at)
        3. 结果合并排序
        """
        try:
            start = datetime.strptime(start_date, "%Y-%m-%d")
            # End date should be end of that day
            end = datetime.strptime(end_date, "%Y-%m-%d").replace(
                hour=23, minute=59, second=59, microsecond=999999
            )
        except ValueError:
            return []

        all_records = []

        # 1. 获取 Diet 原始数据 (文件名范围获取，已注入 _source_date)
        diet_recs = RecordService.get_diet_records_range(user_id, start_date, end_date)
        all_records.extend(diet_recs)

        # 2. 读取 Keep 数据 (Keep files are monthly)
        keep_recs = RecordService._read_keep_records_for_period(user_id, start, end)
        all_records.extend(keep_recs)

        # 3. 统一过滤
        # 使用 Tuple (datetime, dict) 暂存有效记录，避免重复解析和污染数据
        valid_entries = []

        for r in all_records:
            # Strictly rely on occurred_at
            t_str = r.get("occurred_at")
            if not t_str:
                continue

            # Removed redundant try-except: stored data format is reliable.
            dt = datetime.fromisoformat(t_str)

            # Filter range (Normalize TZ for strict comparison)
            check_dt = dt.replace(tzinfo=None) if dt.tzinfo else dt

            if start <= check_dt <= end:
                valid_entries.append((check_dt, r))

        # 4. Sort by effective business time (Tuple[0])
        valid_entries.sort(key=lambda x: x[0])

        # 5. Return only records
        return [x[1] for x in valid_entries]
