from typing import Dict, Any, List
from apps.common.record_service import RecordService
from libs.llm_gemini.gemini_client import GeminiClientConfig, GeminiStructuredClient
from libs.api_keys.api_key_manager import get_default_api_key_manager

class DietReportUsecase:
    def __init__(self, gemini_model_name: str):
        self.api_keys = get_default_api_key_manager()
        self.client = GeminiStructuredClient(
            api_key_manager=self.api_keys,
            config=GeminiClientConfig(model_name=gemini_model_name, temperature=0.7),
        )

    async def generate_daily_report(self, user_id: str, date_str: str) -> Dict[str, Any]:
        records = RecordService.get_diet_records_by_date(user_id, date_str)
        if not records:
            return {"error": "该日期无饮食记录"}
            
        # Aggregate logic (Total energy, macros, dish list)
        total_kj = 0.0
        total_p = 0.0
        total_f = 0.0
        total_c = 0.0
        total_na = 0.0
        total_fib = 0.0
        
        transcript = []
        
        # Records are stored Newest->Oldest by default read_dataset logic usually, 
        # but let's just iterate and not worry about order for sum, but for text transcript we want Chronological.
        # record_service.read_dataset returns lines list which is usually appended.
        # Wait, My storage_lib.read_dataset returns [Newest, ..., Oldest] (reversed lines).
        # So we should reverse it back to get Chronological.
        
        chronological_records = list(reversed(records))
        
        for rec in chronological_records:
            meal = rec.get("meal_summary", {})
            diet_time = meal.get("diet_time", "snack")
            
            # Sum up meal totals if available, or re-sum from dishes to be safe?
            # meal_summary.total_energy_kj is trustworthy.
            total_kj += float(meal.get("total_energy_kj") or 0)
            
            dish_desc = []
            for d in rec.get("dishes", []):
                d_name = d.get("standard_name", "Unknown")
                dish_desc.append(d_name)
                
                # Sum macros from ingredients
                for ing in d.get("ingredients", []):
                    m = ing.get("macros", {})
                    total_p += float(m.get("protein_g") or 0)
                    total_f += float(m.get("fat_g") or 0)
                    total_c += float(m.get("carbs_g") or 0)
                    total_na += float(m.get("sodium_mg") or 0)
                    total_fib += float(m.get("fiber_g") or 0)
            
            transcript.append(f"- {diet_time}: {', '.join(dish_desc)}")

        # Build Prompt
        prompt = f"""
你是一位专业营养师。请根据以下用户今日饮食记录生成一份简短精炼的【每日营养总结报告】。

【今日数据】
日期：{date_str}
总能量：{total_kj:.0f} KJ
三大营养素：蛋白质 {total_p:.1f}g, 脂肪 {total_f:.1f}g, 碳水 {total_c:.1f}g
微量元素关注：钠 {total_na:.0f}mg, 膳食纤维 {total_fib:.1f}g

【进食流水】
{chr(10).join(transcript)}

【生成要求】
1. 你的总结应该包含：总体评价（热量是否超标、三大营养素比例是否均衡）、亮点（如摄入了优质蛋白、高纤维等）、不足与改进建议。
2. 语气亲切、专业、鼓励性。
3. 篇幅控制在 200 字以内。
"""
        # Call LLM
        report_text = await self.client.generate_text_async(prompt)
        
        return {
            "date": date_str,
            "stats": {
                "energy_kj": round(total_kj, 1), 
                "protein_g": round(total_p, 1), 
                "fat_g": round(total_f, 1), 
                "carbs_g": round(total_c, 1),
                "sodium_mg": round(total_na, 1),
                "fiber_g": round(total_fib, 1)
            },
            "report_text": report_text
        }
