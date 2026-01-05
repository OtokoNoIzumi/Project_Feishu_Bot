from typing import Any, Dict, List

from Module.Adapters.feishu.cards.json_builder import JsonBuilder


class DietAnalysisCardBuilder:
    """
    饮食分析结果卡片（v0）

    说明：
    - 当前仅用于“展示，不写入”（二次确认在后续阶段实现）
    - 后续 v2 会演进为 First Paint + Auto Update + 缓存三态
    """

    @staticmethod
    def build_result_markdown(result: Dict[str, Any]) -> str:
        meal = result.get("meal_summary") or {}
        labels = result.get("captured_labels") or []
        dishes = result.get("dishes") or []
        user_note_process = result.get("user_note_process") or ""

        lines: List[str] = []
        lines.append(
            "**结果仅展示，不会写入 user_data。写入需卡片二次确认（后续实现）。**"
        )
        lines.append("")
        lines.append(f"**总能量(kJ)**：{meal.get('total_energy_kj', '')}")
        lines.append(f"**净重(g)**：{meal.get('net_weight_g', '')}")

        advice = meal.get("advice", "")
        if advice:
            lines.append("")
            lines.append("**建议**：")
            lines.append(str(advice))

        if labels:
            lines.append("")
            lines.append("**识别到的包装标签（每 100g/ml）**：")
            for lb in labels[:10]:
                pn = lb.get("product_name", "")
                brand = lb.get("brand", "")
                variant = lb.get("variant", "")
                serving = lb.get("serving_size", "")
                # 兼容：后端可能返回 energy_kj/energy_unit 或 *_per_serving 命名
                energy = lb.get("energy_kj_per_serving", lb.get("energy_kj", ""))
                p = lb.get("protein_g_per_serving", lb.get("protein_g", ""))
                f = lb.get("fat_g_per_serving", lb.get("fat_g", ""))
                c = lb.get("carbs_g_per_serving", lb.get("carbs_g", ""))
                lines.append(
                    f"- {pn} / {brand} / {variant}（{serving}）：能量 {energy} kJ，P {p}g，F {f}g，C {c}g"
                )

        if dishes:
            lines.append("")
            lines.append("**菜品与食材**：")
            for dish in dishes[:10]:
                lines.append(f"- **{dish.get('standard_name', '')}**")
                for ing in (dish.get("ingredients") or [])[:30]:
                    name = ing.get("name_zh", "")
                    w = ing.get("weight_g", "")
                    ekj = ing.get("energy_kj", "")
                    wm = ing.get("weight_method", "")
                    ds = ing.get("data_source", "")
                    lines.append(f"  - {name}：{w}g，{ekj} kJ（{wm}/{ds}）")

        if user_note_process:
            lines.append("")
            lines.append("**处理说明**：")
            lines.append(str(user_note_process))

        return "\n".join(lines)

    @staticmethod
    def build_card_dsl(result: Dict[str, Any]) -> Dict[str, Any]:
        md = DietAnalysisCardBuilder.build_result_markdown(result)
        card_header = JsonBuilder.build_card_header(
            title="饮食分析结果",
            subtitle="仅展示，不写入",
        )
        card_body_elements = [
            JsonBuilder.build_markdown_element(content=md, text_size="normal")
        ]
        return JsonBuilder.build_base_card_structure(card_body_elements, card_header)
