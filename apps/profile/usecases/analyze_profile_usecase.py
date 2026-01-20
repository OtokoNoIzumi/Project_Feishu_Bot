from typing import List, Dict, Any
from datetime import date
import json
import logging
from apps.common.record_service import RecordService
from apps.profile.schemas import UserProfile, ProfileAnalyzeResponse, DietTarget, KeepTarget
from apps.profile.llm_schema import PROFILE_LLM_SCHEMA
from apps.profile.service import ProfileService
from libs.llm_gemini.gemini_client import GeminiStructuredClient, GeminiClientConfig
from libs.api_keys.api_key_manager import get_default_api_key_manager
from libs.storage_lib import global_storage
logger = logging.getLogger(__name__)


class AnalyzeProfileUsecase:
    """
    Profile 智能分析用例。
    
    核心逻辑：
    1. 根据用户设定的目标类型 (goal) 和计算出的 TDEE，推算饮食目标数值
    2. 如果有历史围度数据，且用户未手动设定过对应目标，则推算 Keep 目标
    3. 用户已手动设定的目标进入上下文（作为参考），不让 LLM 重新输出
    """

    def __init__(self, settings):
        self.client = GeminiStructuredClient(
            api_key_manager=get_default_api_key_manager(),
            config=GeminiClientConfig(model_name=settings.gemini_model_name, temperature=0.5)
        )

    async def execute(
        self, 
        user_id: str, 
        user_note: str, 
        target_months: int = None, 
        auto_save: bool = False,
        profile_override: "UserProfile" = None,
        metrics_override: "MetricsOverride" = None
    ) -> ProfileAnalyzeResponse:
        # 1. 加载当前 Profile 设定（优先使用前端传入的数据）
        if profile_override:
            current_profile = profile_override
        else:
            current_profile = ProfileService.load_profile(user_id)

        # 2. 获取最新身体状态（体重/身高）
        # 优先使用前端传入的数据
        if metrics_override:
            current_weight = metrics_override.weight_kg
            current_height = metrics_override.height_cm
        else:
            latest_metrics = RecordService.get_latest_body_metrics(user_id)
            current_weight = latest_metrics.get("weight_kg")
            current_height = latest_metrics.get("height_cm")

        # 3. 前置校验：检查是否有足够的基础信息进行分析（体重/身高来自 Keep 数据）
        missing_info = []
        if not current_weight:
            missing_info.append("体重（请先在 Keep 模块录入体重数据）")
        if not current_height:
            missing_info.append("身高（请先在 Keep 模块录入围度数据）")

        if missing_info:
            # 缺少必要信息，不调用 LLM，直接返回提示
            advice = f"""## 无法进行分析

您尚未填写以下必要信息，请先完善后再进行智能分析：

{chr(10).join(f"- {item}" for item in missing_info)}

填写基础信息后，我可以为您推算合理的饮食和健身目标。"""
            return ProfileAnalyzeResponse(
                advice=advice,
                suggested_profile=current_profile,
                estimated_months=None,
                saved=False
            )

        # 4. 计算 BMR/TDEE（Python 侧计算，不让 LLM 算）
        calculated_stats = self._calculate_stats(current_profile, current_weight, current_height)

        # 5. 获取历史数据（表格格式，复用 weekly 模块的样式）
        scale_records = self._get_scale_records(user_id, limit=10)
        dimension_records = self._get_dimension_records(user_id, limit=5)
        has_dimension_history = len(dimension_records) > 0

        scale_table = self._format_scale_data(scale_records)
        dimension_table = self._format_dimension_data(dimension_records)

        # 6. 判断哪些 Keep 目标是用户已手动设定的（进入上下文，不输出）
        user_set_keep_targets = self._get_user_set_keep_targets(current_profile.keep)

        # 7. 目标月份默认值为 2 个月
        effective_target_months = target_months if target_months else 2

        # 8. 构建 Prompt
        prompt = self._build_prompt(
            user_note=user_note,
            profile=current_profile,
            calculated_stats=calculated_stats,
            scale_table=scale_table,
            dimension_table=dimension_table,
            has_dimension_history=has_dimension_history,
            user_set_keep_targets=user_set_keep_targets,
            target_months=effective_target_months,
        )
        print('test-prompt', prompt)

        # 8. 调用 LLM
        try:
            result = await self.client.generate_json_async(prompt, [], PROFILE_LLM_SCHEMA)
        except Exception as e:
            logger.error(f"Profile analysis LLM error: {e}")
            raise e

        if isinstance(result, dict) and result.get("error"):
            raise Exception(result["error"])

        # 9. 解析结果并合并到 Profile
        advice = result.get("advice", "")
        suggested_diet = result.get("suggested_diet_targets", {})
        suggested_keep = result.get("suggested_keep_targets", {})
        suggested_user_info = result.get("suggested_user_info")

        # 合并 Diet Targets（保留用户的 goal/energy_unit，只更新数值）
        updated_diet = current_profile.diet.model_copy(update=suggested_diet)

        # 合并 Keep Targets（允许 LLM 覆盖现有值，前端有二次确认）
        updated_keep_data = current_profile.keep.model_dump()
        for key, val in suggested_keep.items():
            if key == "dimensions_target" and val:
                # 合并围度目标
                current_dims = updated_keep_data.get("dimensions_target") or {}
                for dim_key, dim_val in val.items():
                    current_dims[dim_key] = dim_val
                updated_keep_data["dimensions_target"] = current_dims
            else:
                updated_keep_data[key] = val

        updated_keep = KeepTarget.model_validate(updated_keep_data)

        # 10. 处理 user_info（用户关键主张）
        # LLM 返回的是全量更新版本，直接替换
        updated_user_info = suggested_user_info if suggested_user_info else current_profile.user_info

        # 11. 获取 LLM 推算的达成时间
        estimated_months = result.get("estimated_months")

        # 构建更新后的 Profile（包含 estimated_months）
        updated_profile = current_profile.model_copy(update={
            "diet": updated_diet,
            "keep": updated_keep,
            "user_info": updated_user_info,
            "estimated_months": estimated_months,
        })

        # 12. 自动保存（如果请求）
        saved = False
        if auto_save:
            ProfileService.save_profile(user_id, updated_profile)
            saved = True

        return ProfileAnalyzeResponse(
            advice=advice,
            suggested_profile=updated_profile,
            estimated_months=estimated_months,
            saved=saved
        )

    def _calculate_stats(self, profile, weight, height) -> Dict[str, Any]:
        """计算 BMR 和 TDEE。"""
        stats = {
            "weight_kg": weight,
            "height_cm": height,
            "age": profile.age,
            "gender": profile.gender,
            "bmr": None,
            "tdee": None
        }

        if weight and height:
            # Mifflin-St Jeor 公式
            w = float(weight)
            h = float(height)
            
            # 计算年龄：优先使用 profile.age（前端直接传入），否则从 birth_date 推算
            if profile.age:
                age = profile.age
            elif profile.birth_date:
                try:
                    birth = date.fromisoformat(profile.birth_date)
                    today = date.today()
                    age = today.year - birth.year - ((today.month, today.day) < (birth.month, birth.day))
                except ValueError:
                    age = 25
            else:
                age = 25  # 默认

            stats["age"] = age
            a = int(age)

            val = 10 * w + 6.25 * h - 5 * a
            if profile.gender == "male":
                bmr = val + 5
            else:
                bmr = val - 161

            stats["bmr"] = int(bmr)
            # TDEE：默认久坐 (1.2)
            stats["tdee"] = int(bmr * 1.2)

        return stats

    def _get_scale_records(self, user_id: str, limit: int = 10) -> List[Dict]:
        """
        获取近期体重记录（扁平结构）。
        数据来源：keep/scale_YYYY_MM.jsonl
        """
        today = date.today()
        months_to_check = [today]
        if today.month == 1:
            months_to_check.append(today.replace(year=today.year-1, month=12, day=1))
        else:
            months_to_check.append(today.replace(month=today.month-1, day=1))

        records = []
        for d in months_to_check:
            filename = f"scale_{d.strftime('%Y_%m')}.jsonl"
            recs = global_storage.read_dataset(user_id, "keep", filename, limit=limit)
            records.extend(recs)
        
        # 按日期降序排列
        records.sort(key=lambda x: x.get("occurred_at", ""), reverse=True)
        return records[:limit]

    def _get_dimension_records(self, user_id: str, limit: int = 5) -> List[Dict]:
        """
        获取近期围度记录（扁平结构）。
        数据来源：keep/dimensions_YYYY_MM.jsonl
        """
        today = date.today()
        months_to_check = [today]
        if today.month == 1:
            months_to_check.append(today.replace(year=today.year-1, month=12, day=1))
        else:
            months_to_check.append(today.replace(month=today.month-1, day=1))

        records = []
        for d in months_to_check:
            filename = f"dimensions_{d.strftime('%Y_%m')}.jsonl"
            recs = global_storage.read_dataset(user_id, "keep", filename, limit=limit)
            records.extend(recs)
        
        # 按日期降序排列
        records.sort(key=lambda x: x.get("occurred_at", ""), reverse=True)
        return records[:limit]

    def _format_scale_data(self, records: List[Dict]) -> str:
        """复用 weekly 模块的表格格式，同一天只保留最新一条"""
        if not records:
            return "无体重记录"

        lines = ["日期|体重kg|体脂%|骨骼肌%|水分%|内脏脂肪"]
        lines.append("-" * 60)

        seen_dates = set()
        for rec in records:
            occurred = rec.get("occurred_at", "")[:10]
            # 同一天只保留最新一条（records 已按降序排列）
            if occurred in seen_dates:
                continue
            seen_dates.add(occurred)
            
            weight = rec.get("weight_kg", "-")
            fat = rec.get("body_fat_pct", "-")
            skeletal_muscle = rec.get("skeletal_muscle_pct", "-")
            water = rec.get("water_pct", "-")
            visceral_fat = rec.get("visceral_fat_level", "-")
            lines.append(f"{occurred}|{weight}|{fat}|{skeletal_muscle}|{water}|{visceral_fat}")

        return "\n".join(lines)

    def _format_dimension_data(self, records: List[Dict]) -> str:
        """复用 weekly 模块的表格格式，同一天只保留最新一条"""
        if not records:
            return "无围度记录"

        lines = ["日期|胸围cm|腰围cm|臀围cm|大腿cm|小腿cm|手臂cm"]
        lines.append("-" * 60)

        seen_dates = set()
        for rec in records:
            d = rec.get("occurred_at", "")[:10]
            # 同一天只保留最新一条（records 已按降序排列）
            if d in seen_dates:
                continue
            seen_dates.add(d)
            
            chest = rec.get("bust", "-")
            waist = rec.get("waist", "-")
            hips = rec.get("hip_circ", "-")
            thigh = rec.get("thigh", "-")
            calf = rec.get("calf", "-")
            arm = rec.get("arm", "-")
            lines.append(f"{d}|{chest}|{waist}|{hips}|{thigh}|{calf}|{arm}")

        return "\n".join(lines)

    def _get_user_set_keep_targets(self, keep: KeepTarget) -> Dict[str, list]:
        """
        判断用户已手动设定的 Keep 目标。
        返回 {"scalars": ["weight_kg_target", ...], "dimensions": ["waist", ...]}
        """
        user_set = {"scalars": [], "dimensions": []}

        if keep.weight_kg_target is not None:
            user_set["scalars"].append("weight_kg_target")
        if keep.body_fat_pct_target is not None:
            user_set["scalars"].append("body_fat_pct_target")
        if keep.dimensions_target:
            user_set["dimensions"] = list(keep.dimensions_target.keys())

        return user_set

    def _build_prompt(
        self,
        user_note: str,
        profile: UserProfile,
        calculated_stats: Dict,
        scale_table: str,
        dimension_table: str,
        has_dimension_history: bool,
        user_set_keep_targets: Dict,
        target_months: int = None,
    ) -> str:
        stats_json = json.dumps(calculated_stats, indent=2, ensure_ascii=False)
        user_set_json = json.dumps(user_set_keep_targets, ensure_ascii=False)
        
        target_months_info = f"用户期望在 {target_months} 个月内达成目标。" if target_months else "用户未指定达成时间。"

        return f"""
角色: 智能健康目标推算助手。

任务: 
根据用户的目标类型 (goal) 和身体数据，推算合理的饮食与健身目标数值，并评估达成时间。

---
## 用户当前设定

Profile 设定:
{profile.model_dump_json(indent=2)}

当前身体状态:
{stats_json}

---
## 历史数据
注意：历史数据可能存在录入错误的异常值（如身高 1cm、体重 2kg），分析时请自行筛选合理数据。

### 体重记录
{scale_table}

### 围度记录
{dimension_table}

---
## 用户已设定的 Keep 目标（作为参考）:
{user_set_json}

---
## 用户关键主张（已记录）
{profile.user_info if profile.user_info else "无"}

---
## 用户期望达成时间
{target_months_info}

---
## 用户备注
"{user_note}"

---
## 指令

### 1. 推算饮食目标 (Diet Targets)
根据用户的 `goal` 和 TDEE ({calculated_stats.get('tdee', '未知')} kcal) 推算：
- 减脂 (fat_loss): 热量 = TDEE - 300~500 kcal，蛋白质 = 1.2~1.5g/kg
- 增肌 (muscle_gain): 热量 = TDEE + 200~300 kcal，蛋白质 = 1.5~2.0g/kg
- 维持 (maintain): 热量 ≈ TDEE

核心公式：目标 = 每日热量缺口/盈余 × 时间

输出 `suggested_diet_targets`，包含：
- daily_energy_kj_target (整数，1 kcal = 4.184 kJ)
- protein_g_target
- fat_g_target
- carbs_g_target
- fiber_g_target
- sodium_mg_target

### 2. 推算 Keep 目标
综合根据用户备注、历史数据、用户已设定的目标，推算合理的 Keep 目标。

参考用户的关键主张进行分析（如特殊的身材目标偏好）。

可推算的围度目标字段：waist, bust, hip_circ, thigh, calf, arm

### 3. 预估达成时间
{"根据每日热量缺口/盈余和目标差值，验证用户期望的 " + str(target_months) + " 个月是否合理。如果过于激进（如每日缺口需超过 800 kcal），在 advice 中提出警告。" if target_months else "根据每日热量缺口/盈余和目标差值，推算需要多少个月达成目标。"}

输出 `estimated_months` (整数)。

### 4. 维护用户关键主张
从用户备注中识别影响分析的**非结构化**关键信息（如：特殊目标、偏好、约束）。
例如："想要 female 的身材围度" "需要考虑姨妈期" "有糖尿病需控糖"

**重要规则**：
1. 不要重复已有结构化字段的信息（如体重目标、饮食目标）。
2. **严禁包含 AI 的建议或提醒**（如"建议配合运动"、"需警惕..."）。
3. 只客观记录用户**明确表达**的能影响分析结果的主张。

如果有新主张或需修改，输出 `suggested_user_info` —— 完整更新版本。
如果没有变化，不输出此字段。

### 5. 输出格式
- advice: 分析建议（Markdown 简体中文），解释推算依据和达成时间评估
- suggested_diet_targets: 推荐的饮食目标数值
- suggested_keep_targets: 推荐的 Keep 目标（如果适用）
- estimated_months: 预估达成时间（月）
- suggested_user_info: 用户关键主张（如果有变化）
"""
