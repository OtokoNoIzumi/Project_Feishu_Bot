"""
临时搬家助手模块

这是一个临时功能模块，用于处理搬家项目的状态管理和报告生成。
后续应完整移除，包括此文件和相关路由逻辑。

职责：
1. 管理根目录的 move_project.toml 文件（项目状态配置）
2. 生成搬家项目报告（基于TOML状态）
3. 合并新内容到TOML配置中
"""

import os
import re
import html
import difflib
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime
import toml
from redlines import Redlines
from Module.Common.scripts.common import debug_utils


# 常量定义
MOVE_TOML_FILENAME = "move_project.toml"

# 初始TOML模板（字段为中文，值为自然语言）
# 注意：TOML标准要求中文字段名和表名必须使用引号
# 新结构：使用点式键（dotted keys）格式，符合TOML v1.0.0最佳实践
INITIAL_MOVE_TOML = '''
'''

# 提示词模板（硬编码在模块内）

PROMPT_MOVE_REPORT = """角色：搬家项目的计划顾问。

输入：以下是 TOML 格式的"项目状态配置"，描述当前的真实状态，请完整理解：
{TOML_TEXT}

当前系统时间：{CURRENT_TIME}

任务：仅根据 TOML 信息，生成"中文行动报告"。报告应基于当前时间进行时间规划和行动建议。

输出要求（严格遵守）：
- 格式要求：使用飞书文本消息兼容的格式
  - 只允许使用内联HTML标签：<b>加粗</b> 和 <i>斜体</i>
  - 严格禁止使用任何块级HTML标签：<p>、<div>、<h1>、<h2>、<br/>、<br> 等
  - 严格禁止使用Markdown语法：#、##、###、**、*、-、`、[]() 等
  - 换行：直接使用换行符 \n，不要使用任何HTML标签换行
  - 列表项：使用 • 符号（U+2022字符）开头，后跟空格
  - 段落分隔：使用 \n\n（两个换行符）分隔不同段落
- 内容要求：必须包含三部分
  1) <b>下一步行动</b>（2-5条，可执行，按优先级排序；每条用动词开头）
     - 优先从`["行动计划"]`的"⏰ 近期（本周内）关键行动"中提取
     - 结合`["各区域采购与布置"]`中各条目的`status`字段中提到的待办事项
  2) <b>三次往返计划</b>（每次包含：时间窗口建议 + 本次要完成的事项清单）
     - 优先从`["行动计划"]`的"📋 下次往返（11月18日-19日）任务清单"中提取
     - 结合`["各区域采购与布置"]`中各条目的`status`字段中提到的送货、安装时间
  3) <b>缺失信息检查</b>（列出阻碍决策或执行的关键缺失信息，并给出如何补齐的建议）
     - 扫描`["各区域采购与布置"]`中`status`字段包含"待决策"、"待采购"、"待确认"等词语的条目
     - 检查`["风险管理"]`中提到的风险点
- 其他要求：
  - 若信息不足，给出合理假设，但在"缺失信息检查"中明确标注
  - 只输出报告正文，不要解释你的过程，不要添加任何说明文字
  - 可适当使用emoji增强可读性（如 ✅、⚠️、📋、⏰ 等）

正确格式示例：
<b>下一步行动</b>
• 联系所有已购大件的客服，协调统一送货时间
• 在双十一期间完成冰箱下单

<b>三次往返计划</b>
• 第一次往返：核心安装与初步布置
  时间窗口：建议在工作日中午出发，避开高峰期
  待办事项：接收并监督空调安装；接收并监督洗衣机安装；办理水电燃气开通

<b>缺失信息检查</b>
• 需要确认具体安装师傅联系方式
• 需要获取详细尺寸图以验证采购物品适配性
"""

PROMPT_MOVE_MERGE = '''角色：智能项目助理。

输入1：当前 TOML 项目状态配置：
{TOML_TEXT}

输入2：需要并入的新进展（自然语言）：
{NEW_TEXT}

任务：智能地将"新进展"整合到 TOML 状态中，并保持文档的清晰与连贯。

1. **理解与定位**：解析"新进展"的核心信息，在`["各区域采购与布置"]`中找到对应的条目（按区域分类：睡眠区、办公区、大家电、基础设施与安防、软装与其他）。

2. **更新状态**：用自然语言流畅地更新该条目的 `status` 字段，使其反映最新的情况。如果涉及金额，同步更新 `["预算与支出"]` 中的相关字段。

3. **重新生成行动计划**：**删除并完全重写** `["行动计划"]` 章节。仔细阅读整个`["各区域采购与布置"]`的所有`status`字段，提取出所有未来的、需要执行的动作，将它们分类放入"⏰ 近期（本周内）关键行动"、"📋 下次往返（11月18日-19日）任务清单"和"⏳ 后续待办"中。

4. **更新概览**：根据整体变化，用多行字符串格式重写`["项目仪表盘"]`下的`状态速览`，提炼出当前的项目焦点。

**重要：Diff友好性原则（严格遵守）**：
- **禁止无意义的修改**：不要修改与"新进展"无关的内容，包括：
  * 不要调换列表项的顺序（如"空调、床垫"改为"床垫、空调"）
  * 不要修改标点符号（如逗号改为顿号，除非是明显的错误）
  * 不要修改措辞（如"和"改为"并与"，除非是语法错误）
  * 不要修改格式（如空格、换行等）
- **最小化变更**：只修改与新进展直接相关的字段，其他内容保持原样
- **保持一致性**：如果新进展没有明确要求修改某个字段，就不要修改它

输出格式（严格遵守）：
===TOML_START===
[在此处输出完整的TOML文本]
===TOML_END===

如果有建议修改（如措辞优化、格式改进等），请在TOML之后添加：
===SUGGESTIONS_START===
[在此处输出建议，每行一个建议]
===SUGGESTIONS_END===

TOML格式规范：
- 只输出TOML文本，不要任何说明文字或Markdown代码块标记
- 所有中文字段名和表名必须使用双引号，例如 ["项目基础"] 和 "目标" = "..."
- **重要：必须使用点式键（dotted keys）格式**，例如：
  ["各区域采购与布置"."睡眠区"."床垫"]
  item = "..."
  cost = 2598.0
  status = "..."
  不要使用内联表格格式（不要写成 "睡眠区" = {{ "床垫" = {{ ... }} }} 这种格式）
- 日期使用原生类型：`"目标入住日期" = 2025-12-01`（不是字符串）
- 状态速览使用多行字符串：`"状态速览" = """..."""`
- 字段名使用可读的中文短语；字段值保持自然语言；不要使用英文大写枚举。
- 保持段落顺序与层级结构一致；如需新增条目，放在最合适的区域下。
- 数值类型（如 cost、discount）使用数字而非字符串，例如 cost = 3820.0 而不是 cost = "3820.0"
- `status` 字段是核心，应包含完整的状态描述（历史、现状、下一步计划）
- **不要修改"更新时间"字段**，该字段由程序自动更新
'''

PROMPT_DECISION_ADVISOR = """角色：精通生活方式与消费决策的顾问。

输入1：TOML 格式的"项目状态配置"（含核心目标、健康考量、预算与已购情况等）：
{TOML_TEXT}

输入2：待决策项目与两个候选方案：
- 项目：{ITEM_TO_DECIDE}
- 选项A：{OPTION_A}
- 选项B：{OPTION_B}

任务：基于 TOML 中的"核心目标""健康考量""预算与支出""已采购/待决策"等，做出唯一的购买建议。

输出要求（严格遵守）：
- 中文 Markdown 输出。
- 结构：
  - 关联分析（严格引用 TOML 中的相关约束逐点对照）
  - 明确建议（只给 A 或 B 其一）
  - 理由阐述（解释该建议如何更好服务长期核心目标；如有风险，给出缓解方式）
- 不要输出 TOML/代码块。
"""


class TempMoveModule:
    """临时搬家助手模块"""

    @staticmethod
    def get_toml_path(project_root: str) -> Path:
        """获取TOML文件路径"""
        return Path(project_root) / MOVE_TOML_FILENAME

    @staticmethod
    def ensure_file(project_root: str) -> Path:
        """
        确保TOML文件存在，如果不存在则创建初始模板

        Args:
            project_root: 项目根目录路径

        Returns:
            Path: TOML文件路径
        """
        toml_path = TempMoveModule.get_toml_path(project_root)

        if not toml_path.exists():
            debug_utils.log_and_print(
                f"创建初始搬家项目配置文件: {toml_path}", log_level="INFO"
            )
            try:
                toml_path.write_text(INITIAL_MOVE_TOML, encoding="utf-8")
            except Exception as e:
                debug_utils.log_and_print(
                    f"创建初始TOML文件失败: {e}", log_level="ERROR"
                )
                raise

        return toml_path

    @staticmethod
    def read_toml_text(project_root: str) -> str:
        """
        读取TOML文件内容（原始文本）

        Args:
            project_root: 项目根目录路径

        Returns:
            str: TOML文件内容
        """
        toml_path = TempMoveModule.ensure_file(project_root)
        try:
            return toml_path.read_text(encoding="utf-8")
        except Exception as e:
            debug_utils.log_and_print(
                f"读取TOML文件失败: {e}", log_level="ERROR"
            )
            raise

    @staticmethod
    def write_toml_text(project_root: str, text: str) -> bool:
        """
        写入TOML文件（覆盖写入）

        Args:
            project_root: 项目根目录路径
            text: 完整的TOML文本内容

        Returns:
            bool: 是否写入成功
        """
        toml_path = TempMoveModule.get_toml_path(project_root)
        try:
            toml_path.write_text(text, encoding="utf-8")
            debug_utils.log_and_print(
                f"TOML文件已更新: {toml_path}", log_level="INFO"
            )
            return True
        except Exception as e:
            debug_utils.log_and_print(
                f"写入TOML文件失败: {e}", log_level="ERROR"
            )
            return False

    @staticmethod
    def generate_report(llm_service, toml_text: str) -> str:
        """
        生成搬家项目报告

        Args:
            llm_service: LLM服务实例
            toml_text: TOML配置文本

        Returns:
            str: Markdown格式的报告
        """
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        prompt = PROMPT_MOVE_REPORT.format(
            TOML_TEXT=toml_text,
            CURRENT_TIME=current_time
        )

        try:
            report = llm_service.simple_chat(prompt, max_tokens=2000)
            return report
        except Exception as e:
            debug_utils.log_and_print(
                f"生成搬家报告失败: {e}", log_level="ERROR"
            )
            return f"生成报告时发生错误: {str(e)}"

    @staticmethod
    def _update_toml_timestamp_programmatic(toml_text: str) -> str:
        """
        程序化方式更新TOML中的"更新时间"字段为当前时间
        使用TOML解析获取旧值，然后进行简单的文本替换，保持其他格式不变
        新结构：更新时间位于["项目仪表盘"]章节，使用ISO 8601格式（2025-11-06T19:47:36）

        Args:
            toml_text: TOML文本内容

        Returns:
            str: 更新后的TOML文本
        """
        try:
            # 解析TOML为结构化数据，获取旧的时间戳值
            toml_dict = toml.loads(toml_text)

            # 检查结构（新结构：更新时间在"项目仪表盘"中）
            if "项目仪表盘" not in toml_dict:
                # 兼容旧结构：尝试"采购进度"
                if "采购进度" in toml_dict:
                    old_timestamp = toml_dict["采购进度"].get("更新时间", "")
                    section_name = "采购进度"
                else:
                    debug_utils.log_and_print(
                        "TOML配置中未找到'项目仪表盘'或'采购进度'章节，跳过更新时间更新", log_level="WARNING"
                    )
                    return toml_text
            else:
                old_timestamp = toml_dict["项目仪表盘"].get("更新时间", "")
                section_name = "项目仪表盘"

            if not old_timestamp:
                debug_utils.log_and_print(
                    f"TOML配置中未找到'更新时间'字段（在{section_name}章节），跳过更新时间更新", log_level="WARNING"
                )
                return toml_text

            # 获取新的时间戳（ISO 8601格式：2025-11-06T19:47:36）
            current_time = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

            # 处理旧时间戳可能是字符串或datetime对象的情况
            if isinstance(old_timestamp, str):
                # 旧格式可能是 "2025-11-06 19:47:36" 或 "2025-11-06T19:47:36"
                old_timestamp_str = old_timestamp
            else:
                # 如果是datetime对象，转换为字符串
                old_timestamp_str = old_timestamp.strftime("%Y-%m-%dT%H:%M:%S")

            # 尝试多种可能的旧格式进行替换
            possible_old_formats = [
                f'"{old_timestamp_str}"',  # 字符串格式
                old_timestamp_str,  # 直接格式（ISO 8601）
                old_timestamp_str.replace('T', ' '),  # 空格分隔格式
                f'"{old_timestamp_str.replace("T", " ")}"',  # 字符串格式（空格分隔）
            ]

            for old_value in possible_old_formats:
                if old_value in toml_text:
                    # 根据旧格式确定新格式
                    if old_value.startswith('"'):
                        new_value = f'"{current_time}"'
                    else:
                        new_value = current_time

                    updated_toml = toml_text.replace(old_value, new_value, 1)

                    # 验证替换后的TOML仍然有效
                    try:
                        toml.loads(updated_toml)
                        return updated_toml
                    except Exception as parse_error:
                        debug_utils.log_and_print(
                            f"替换时间戳后TOML解析失败: {parse_error}，尝试其他格式", log_level="WARNING"
                        )
                        continue

            # 如果所有格式都失败，记录警告但返回原文本
            debug_utils.log_and_print(
                f"未在文本中找到时间戳值，跳过更新时间更新", log_level="WARNING"
            )
            return toml_text

        except Exception as e:
            debug_utils.log_and_print(
                f"程序化更新TOML时间戳失败: {e}，返回原文本", log_level="ERROR"
            )
            return toml_text

    @staticmethod
    def _format_value_for_display(value: Any, max_length: int = 150) -> str:
        """
        格式化值用于显示（友好格式）

        Args:
            value: 要格式化的值
            max_length: 最大显示长度

        Returns:
            str: 格式化后的字符串
        """
        if isinstance(value, dict):
            return TempMoveModule._format_dict_summary(value, max_length)
        elif isinstance(value, list):
            if len(value) == 0:
                return "[]"
            display_list = ", ".join(str(v) for v in value[:3])
            if len(value) > 3:
                display_list += f" ...（共{len(value)}项）"
            return display_list
        elif isinstance(value, (int, float)):
            # 数值类型：如果是整数，不显示小数；如果是浮点数，保留2位小数
            if isinstance(value, int):
                return str(value)
            else:
                return f"{value:.2f}"
        else:
            val_str = str(value)
            if len(val_str) > max_length:
                return val_str[:max_length] + "..."
            return val_str

    @staticmethod
    def _compare_dict_fields(old_dict: dict, new_dict: dict) -> list:
        """
        比较两个字典的字段变化，返回变化列表

        Args:
            old_dict: 旧字典
            new_dict: 新字典

        Returns:
            list: 变化项列表，每个项包含 {'type': 'field_modified/field_added/field_deleted', 'field': '字段名', 'old_value': ..., 'new_value': ...}
        """
        changes = []
        all_keys = set(old_dict.keys()) | set(new_dict.keys())

        for key in all_keys:
            if key not in new_dict:
                # 字段被删除
                changes.append({
                    'type': 'field_deleted',
                    'field': key,
                    'old_value': old_dict[key],
                    'new_value': None
                })
            elif key not in old_dict:
                # 字段被新增
                changes.append({
                    'type': 'field_added',
                    'field': key,
                    'old_value': None,
                    'new_value': new_dict[key]
                })
            else:
                old_field_val = old_dict[key]
                new_field_val = new_dict[key]
                if old_field_val != new_field_val:
                    # 字段值被修改
                    changes.append({
                        'type': 'field_modified',
                        'field': key,
                        'old_value': old_field_val,
                        'new_value': new_field_val
                    })

        return changes

    @staticmethod
    def _format_dict_summary(d: dict, max_length: int = 150) -> str:
        """
        格式化字典为友好的摘要显示

        Args:
            d: 字典
            max_length: 最大显示长度

        Returns:
            str: 格式化后的摘要字符串
        """
        if not d:
            return "{}"

        # 优先显示关键字段（如果存在）
        key_fields = ['item', 'status', 'cost', 'description', 'priority']
        summary_parts = []

        for key in key_fields:
            if key in d:
                val = d[key]
                if isinstance(val, (int, float)):
                    val_str = f"{val:.2f}" if isinstance(val, float) else str(val)
                else:
                    val_str = str(val)
                if len(val_str) > 30:
                    val_str = val_str[:30] + "..."
                summary_parts.append(f"{key}: {val_str}")

        # 如果关键字段不够，补充其他字段
        if len(summary_parts) < 2:
            for key, val in d.items():
                if key not in key_fields:
                    val_str = str(val)
                    if len(val_str) > 30:
                        val_str = val_str[:30] + "..."
                    summary_parts.append(f"{key}: {val_str}")
                    if len(summary_parts) >= 3:
                        break

        result = "{" + ", ".join(summary_parts) + "}"
        if len(result) > max_length:
            result = result[:max_length] + "..."

        return result

    @staticmethod
    def _compare_lists(old_list: List[Any], new_list: List[Any], similarity_threshold: float = 0.6) -> List[Dict[str, Any]]:
        """
        高级列表比较函数，使用 difflib.SequenceMatcher 进行智能匹配

        算法优势（相比旧版本）：
        1. **基于替换块的匹配**：使用 SequenceMatcher 识别替换块，在块内寻找最佳匹配，
           能够准确识别"修改"、"移动并修改"、"删除"和"添加"操作
        2. **相似度匹配**：使用相似度阈值（默认0.6）判断是否为"修改"而非"删除+新增"，
           能够处理部分修改的情况（如："【决策并下单】冰箱" -> "【决策并下单】冰箱，利用尺寸信息"）
        3. **更准确的索引**：返回的索引更准确地反映变化位置
        4. **性能优化**：使用Python标准库的成熟算法，经过充分优化和测试

        旧算法的问题：
        1. **冗余代码**：需要4遍遍历，创建多个映射和标记数组
        2. **匹配不准确**：只能识别完全相同的项，无法处理部分修改
        3. **索引混乱**：对于移动的项，索引计算不准确
        4. **无法处理相似项**：如果项被修改但相似，会被误判为删除+新增

        difflib.SequenceMatcher 特性：
        - Python标准库，无需额外依赖
        - 使用最长公共子序列（LCS）算法，时间复杂度 O(n*m)
        - 支持 autojunk 参数，可以禁用自动垃圾检测以提高准确性
        - get_opcodes() 返回的操作码包括：'equal', 'delete', 'insert', 'replace'
        - ratio() 方法返回相似度（0.0-1.0），基于最长公共子序列计算

        Args:
            old_list: 旧列表
            new_list: 新列表
            similarity_threshold: 相似度阈值，用于判断是否为"修改"（默认0.6）

        Returns:
            List[Dict[str, Any]]: 排序后的差异项列表，每个项包含：
                - 'type': 'item_added'/'item_deleted'/'item_modified'
                - 'index': 索引位置
                - 'old_value': 旧值（删除和修改时）
                - 'new_value': 新值（新增和修改时）
        """
        changes: List[Dict[str, Any]] = []

        old_list_str = [str(item) for item in old_list]
        new_list_str = [str(item) for item in new_list]

        matcher = difflib.SequenceMatcher(None, old_list_str, new_list_str, autojunk=False)

        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == 'delete':
                for i in range(i1, i2):
                    changes.append({
                        'type': 'item_deleted',
                        'index': i,
                        'old_value': old_list[i],
                        'new_value': None
                    })
            elif tag == 'insert':
                for j in range(j1, j2):
                    changes.append({
                        'type': 'item_added',
                        'index': j,
                        'old_value': None,
                        'new_value': new_list[j]
                    })
            elif tag == 'replace':
                # 核心改进逻辑：在替换块内寻找最佳匹配
                old_chunk = [(old_list[i], i) for i in range(i1, i2)]
                new_chunk = [(new_list[j], j) for j in range(j1, j2)]

                # 记录新块中的项是否已被匹配
                new_matched = [False] * len(new_chunk)

                # 1. 为每个旧项寻找最佳匹配的新项
                for old_item, old_idx in old_chunk:
                    best_ratio = similarity_threshold - 0.001
                    best_match_j = -1

                    for j, (new_item, _) in enumerate(new_chunk):
                        if not new_matched[j]:
                            ratio = difflib.SequenceMatcher(None, str(old_item), str(new_item)).ratio()
                            if ratio > best_ratio:
                                best_ratio = ratio
                                best_match_j = j

                    # 如果找到了一个足够好的匹配
                    if best_match_j != -1:
                        new_matched[best_match_j] = True
                        new_item, new_idx = new_chunk[best_match_j]
                        changes.append({
                            'type': 'item_modified',
                            'index': old_idx,
                            'old_value': old_item,
                            'new_value': new_item
                        })
                    else:
                        # 如果没有找到匹配，则该旧项被删除
                        changes.append({
                            'type': 'item_deleted',
                            'index': old_idx,
                            'old_value': old_item,
                            'new_value': None
                        })

                # 2. 所有未被匹配的新项都是新增的
                for j, (new_item, new_idx) in enumerate(new_chunk):
                    if not new_matched[j]:
                        changes.append({
                            'type': 'item_added',
                            'index': new_idx,
                            'old_value': None,
                            'new_value': new_item
                        })

        # 按索引排序，使输出更可读
        changes.sort(key=lambda x: x['index'])
        return changes

    @staticmethod
    def _generate_toml_diff_rich_text(old_toml_text: str, new_toml_text: str, new_content: str, suggestions: Optional[str] = None) -> Dict[str, Any]:
        """
        生成TOML差异报告（程序化比对 + redline格式化变更字段）

        Args:
            old_toml_text: 原始TOML文本
            new_toml_text: 更新后的TOML文本
            new_content: 用户输入的新内容（用于显示）
            suggestions: LLM提供的优化建议（可选，不写入TOML）

        Returns:
            Dict[str, Any]: 飞书富文本内容结构
        """
        try:
            old_dict = toml.loads(old_toml_text)
            new_dict = toml.loads(new_toml_text)

            diff_items = []

            def compare_dict(old_d: dict, new_d: dict, path_prefix: str = ""):
                """递归比较字典，收集差异项"""
                all_keys = set(old_d.keys()) | set(new_d.keys())

                for key in all_keys:
                    current_path = f"{path_prefix}.{key}" if path_prefix else key

                    # 跳过程序控制的"更新时间"字段
                    if current_path == "项目仪表盘.更新时间" or current_path.endswith(".更新时间"):
                        continue

                    if key not in new_d:
                        # 键被删除
                        diff_items.append({
                            'path': current_path,
                            'type': 'deleted',
                            'old_value': old_d[key],
                            'new_value': None
                        })
                    elif key not in old_d:
                        # 键被新增
                        diff_items.append({
                            'path': current_path,
                            'type': 'added',
                            'old_value': None,
                            'new_value': new_d[key]
                        })
                    else:
                        old_val = old_d[key]
                        new_val = new_d[key]

                        # 如果是字典，递归比较
                        if isinstance(old_val, dict) and isinstance(new_val, dict):
                            compare_dict(old_val, new_val, current_path)
                        # 如果是列表，进行逐项比较
                        elif isinstance(old_val, list) and isinstance(new_val, list):
                            list_changes = TempMoveModule._compare_lists(old_val, new_val)
                            if list_changes:
                                # 如果有列表项的变化，记录为修改，但会在后续处理中展开显示
                                diff_items.append({
                                    'path': current_path,
                                    'type': 'list_modified',
                                    'old_value': old_val,
                                    'new_value': new_val,
                                    'list_changes': list_changes
                                })
                        # 如果是列表或字符串，比较值
                        elif old_val != new_val:
                            diff_items.append({
                                'path': current_path,
                                'type': 'modified',
                                'old_value': old_val,
                                'new_value': new_val
                            })

            compare_dict(old_dict, new_dict)

            # 构建富文本内容
            content_items = [
                [{"tag": "text", "text": "✅ 搬家项目信息已更新"}],
                [{"tag": "hr"}],
                [{"tag": "text", "text": f"📝 输入内容：{new_content[:50]}..."}],
                [{"tag": "hr"}]
            ]

            if not diff_items:
                content_items.append([{"tag": "text", "text": "未发现明显差异（可能是格式调整）"}])
            else:
                content_items.append([{"tag": "text", "text": "📋 更新差异：", "style": ["bold"]}])

                for diff in diff_items:
                    path = diff['path']
                    # 路径显示：将点号替换为箭头，更易读
                    path_display = path.replace(".", " → ")

                    if diff['type'] == 'added':
                        # 新增：使用emoji和样式标识
                        new_val = diff['new_value']
                        new_val_str = TempMoveModule._format_value_for_display(new_val)

                        content_items.append([
                            {"tag": "text", "text": "✅ "},
                            {"tag": "text", "text": "新增", "style": ["bold"]},
                            {"tag": "text", "text": f" {path_display}："}
                        ])
                        content_items.append([
                            {"tag": "text", "text": f"  {new_val_str}"}
                        ])

                    elif diff['type'] == 'deleted':
                        # 删除：使用emoji和删除线样式
                        old_val = diff['old_value']
                        old_val_str = TempMoveModule._format_value_for_display(old_val)

                        content_items.append([
                            {"tag": "text", "text": "❌ "},
                            {"tag": "text", "text": "删除", "style": ["bold"]},
                            {"tag": "text", "text": f" {path_display}："}
                        ])
                        # 使用markdown的删除线语法
                        content_items.append([
                            {"tag": "md", "text": f" ~~{old_val_str}~~ "}
                        ])

                    elif diff['type'] == 'list_modified':
                        # 列表修改：逐项显示增删改
                        list_changes = diff.get('list_changes', [])

                        content_items.append([
                            {"tag": "text", "text": "🔄 "},
                            {"tag": "text", "text": "修改", "style": ["bold"]},
                            {"tag": "text", "text": f" {path_display}："}
                        ])

                        for list_change in list_changes:
                            if list_change['type'] == 'item_added':
                                new_item_str = str(list_change['new_value'])
                                content_items.append([
                                    {"tag": "text", "text": f"  • 新增项[{list_change['index']}]：{new_item_str}"}
                                ])
                            elif list_change['type'] == 'item_deleted':
                                old_item_str = str(list_change['old_value'])
                                content_items.append([
                                    {"tag": "text", "text": f"  • 删除项[{list_change['index']}]："},
                                    {"tag": "md", "text": f" ~~{old_item_str}~~ "}
                                ])
                            elif list_change['type'] == 'item_modified':
                                old_item_str = str(list_change['old_value'])
                                new_item_str = str(list_change['new_value'])
                                try:
                                    item_diff = Redlines(old_item_str, new_item_str)
                                    item_diff_markdown = item_diff.output_markdown
                                    # 清理HTML标签
                                    line_through_pattern = r"<span[^>]*text-decoration:line-through[^>]*>(.*?)</span>"
                                    def replace_line_through(match):
                                        content = match.group(1)
                                        # 转义特殊字符，避免与Markdown语法冲突
                                        content = content.replace('*', r'\*').replace('_', r'\_').replace('[', r'\[').replace(']', r'\]').replace('`', r'\`')
                                        return f" ~~{content}~~ "
                                    cleaned_markdown = re.sub(line_through_pattern, replace_line_through, item_diff_markdown, flags=re.DOTALL)
                                    green_pattern = r"<span[^>]*color:green[^>]*>(.*?)</span>"
                                    cleaned_markdown = re.sub(green_pattern, r'\1', cleaned_markdown, flags=re.DOTALL)
                                    cleaned_markdown = re.sub(r'<[^>]+>', '', cleaned_markdown)
                                    cleaned_markdown = html.unescape(cleaned_markdown)

                                    if len(cleaned_markdown) > 200:
                                        cleaned_markdown = cleaned_markdown[:200] + "..."

                                    # 将修改项内容放在同一行，避免飞书显示问题
                                    content_items.append([
                                        {"tag": "text", "text": f"  • 修改项[{list_change['index']}]： "},
                                        {"tag": "md", "text": cleaned_markdown}
                                    ])
                                except Exception as e:
                                    debug_utils.log_and_print(
                                        f"列表项redline比对失败: {e}，使用简化显示", log_level="WARNING"
                                    )
                                    content_items.append([
                                        {"tag": "text", "text": f"  • 修改项[{list_change['index']}]："},
                                        {"tag": "md", "text": f" ~~{old_item_str}~~ → {new_item_str}"}
                                    ])
                        continue  # 跳过后续的通用处理

                    elif diff['type'] == 'modified':
                        # 修改：使用redline比对具体字段值的变化
                        old_val = diff['old_value']
                        new_val = diff['new_value']

                        # 对于字典类型，需要特殊处理：显示内部字段的变化
                        if isinstance(old_val, dict) and isinstance(new_val, dict):
                            # 字典类型：尝试找出内部字段的变化
                            dict_changes = TempMoveModule._compare_dict_fields(old_val, new_val)
                            if dict_changes:
                                # 有具体字段变化，显示每个字段的变化
                                content_items.append([
                                    {"tag": "text", "text": "🔄 "},
                                    {"tag": "text", "text": "修改", "style": ["bold"]},
                                    {"tag": "text", "text": f" {path_display}："}
                                ])
                                for field_change in dict_changes:
                                    field_path = f"{path_display}.{field_change['field']}" if field_change['field'] else path_display
                                    if field_change['type'] == 'field_modified':
                                        # 字段值变化：使用redline比对
                                        old_field_str = TempMoveModule._format_value_for_display(field_change['old_value'], max_length=100)
                                        new_field_str = TempMoveModule._format_value_for_display(field_change['new_value'], max_length=100)
                                        try:
                                            field_diff = Redlines(old_field_str, new_field_str)
                                            field_diff_markdown = field_diff.output_markdown
                                            # 清理HTML标签
                                            line_through_pattern = r"<span[^>]*text-decoration:line-through[^>]*>(.*?)</span>"
                                            def replace_line_through(match):
                                                content = match.group(1)
                                                content = content.replace('*', r'\*').replace('_', r'\_').replace('[', r'\[').replace(']', r'\]')
                                                return f" ~~{content}~~ "
                                            cleaned_markdown = re.sub(line_through_pattern, replace_line_through, field_diff_markdown, flags=re.DOTALL)
                                            green_pattern = r"<span[^>]*color:green[^>]*>(.*?)</span>"
                                            cleaned_markdown = re.sub(green_pattern, r'\1', cleaned_markdown, flags=re.DOTALL)
                                            cleaned_markdown = re.sub(r'<[^>]+>', '', cleaned_markdown)
                                            cleaned_markdown = html.unescape(cleaned_markdown)
                                            if len(cleaned_markdown) > 300:
                                                cleaned_markdown = cleaned_markdown[:300] + "..."
                                            content_items.append([
                                                {"tag": "text", "text": f"  • {field_change['field']}："}
                                            ])
                                            content_items.append([
                                                {"tag": "md", "text": f"    {cleaned_markdown}"}
                                            ])
                                        except Exception as e:
                                            debug_utils.log_and_print(
                                                f"字段redline比对失败: {field_change['field']}, 错误: {e}，使用简化显示",
                                                log_level="WARNING"
                                            )
                                            # redline失败，使用简化显示
                                            content_items.append([
                                                {"tag": "text", "text": f"  • {field_change['field']}："}
                                            ])
                                            content_items.append([
                                                {"tag": "md", "text": f"    ~~{old_field_str}~~ → {new_field_str}"}
                                            ])
                                    elif field_change['type'] == 'field_added':
                                        new_field_str = TempMoveModule._format_value_for_display(field_change['new_value'], max_length=100)
                                        content_items.append([
                                            {"tag": "text", "text": f"  • {field_change['field']}：新增 {new_field_str}"}
                                        ])
                                    elif field_change['type'] == 'field_deleted':
                                        old_field_str = TempMoveModule._format_value_for_display(field_change['old_value'], max_length=100)
                                        content_items.append([
                                            {"tag": "text", "text": f"  • {field_change['field']}：删除 "},
                                            {"tag": "md", "text": f" ~~{old_field_str}~~ "}
                                        ])
                                continue  # 跳过后续的通用redline处理
                            else:
                                # 字典整体被替换，但没有具体字段变化（不太可能，但保留兼容）
                                old_val_str = TempMoveModule._format_dict_summary(old_val)
                                new_val_str = TempMoveModule._format_dict_summary(new_val)
                        else:
                            # 其他类型：直接转换为字符串
                            old_val_str = str(old_val)
                            new_val_str = str(new_val)

                        # 通用处理：对非字典类型的修改或字典整体替换使用redline比对
                        content_items.append([
                            {"tag": "text", "text": "🔄 "},
                            {"tag": "text", "text": "修改", "style": ["bold"]},
                            {"tag": "text", "text": f" {path_display}："}
                        ])

                        # 对变更的字段值使用redline进行详细比对
                        try:
                            value_diff = Redlines(old_val_str, new_val_str)
                            # redline的output_markdown包含HTML标签，需要转换为飞书支持的格式
                            diff_markdown = value_diff.output_markdown

                            # 清理redline的HTML标签，转换为飞书支持的markdown格式
                            # redline输出格式: <span style='color:red;text-decoration:line-through'>删除</span><span style='color:green'>新增</span>
                            # 需要转换为: ~~删除~~新增

                            # 第一步：提取带删除线的内容，转换为markdown删除线
                            line_through_pattern = r"<span[^>]*text-decoration:line-through[^>]*>(.*?)</span>"
                            def replace_line_through(match):
                                content = match.group(1)
                                # 转义特殊字符
                                content = content.replace('*', r'\*').replace('_', r'\_').replace('[', r'\[').replace(']', r'\]')
                                return f" ~~{content}~~ "

                            cleaned_markdown = re.sub(
                                line_through_pattern,
                                replace_line_through,
                                diff_markdown,
                                flags=re.DOTALL
                            )

                            # 第二步：移除所有剩余的HTML标签（保留文本内容）
                            # 先移除绿色span的标签，保留内容（这部分是新增的）
                            green_pattern = r"<span[^>]*color:green[^>]*>(.*?)</span>"
                            cleaned_markdown = re.sub(
                                green_pattern,
                                r'\1',
                                cleaned_markdown,
                                flags=re.DOTALL
                            )

                            # 移除所有剩余的HTML标签
                            cleaned_markdown = re.sub(r'<[^>]+>', '', cleaned_markdown)

                            # 解码HTML实体（如果有）
                            cleaned_markdown = html.unescape(cleaned_markdown)

                            # 限制长度
                            if len(cleaned_markdown) > 500:
                                cleaned_markdown = cleaned_markdown[:500] + "..."

                            content_items.append([
                                {"tag": "md", "text": f"  {cleaned_markdown}"}
                            ])
                        except Exception as e:
                            # redline失败时降级显示
                            debug_utils.log_and_print(
                                f"redline比对失败: {e}，路径: {path_display}，使用简化显示",
                                log_level="WARNING"
                            )
                            old_display = old_val_str[:100] + ("..." if len(old_val_str) > 100 else "")
                            new_display = new_val_str[:100] + ("..." if len(new_val_str) > 100 else "")
                            content_items.append([
                                {"tag": "md", "text": f"  ~~{old_display}~~ → {new_display}"}
                            ])

            # 如果有建议，在最后添加建议部分
            if suggestions:
                content_items.append([{"tag": "hr"}])
                content_items.append([{"tag": "text", "text": "💡 优化建议（仅供参考，未写入配置）：", "style": ["bold"]}])
                for suggestion_line in suggestions.split('\n'):
                    suggestion_line = suggestion_line.strip()
                    if suggestion_line:
                        content_items.append([
                            {"tag": "text", "text": f"  • {suggestion_line}"}
                        ])

            rich_text_content = {
                "zh_cn": {
                    "title": "搬家项目更新差异",
                    "content": content_items
                }
            }

            return rich_text_content

        except Exception as e:
            error_msg = str(e)
            debug_utils.log_and_print(
                f"生成TOML差异报告失败: {error_msg}", log_level="ERROR"
            )
            # 尝试解析错误信息，提取行号和位置
            import re as re_module
            line_match = re_module.search(r'line (\d+)', error_msg, re_module.IGNORECASE)
            col_match = re_module.search(r'column (\d+)', error_msg, re_module.IGNORECASE)

            error_details = [f"⚠️ 差异分析失败：{error_msg}"]
            if line_match:
                line_num = int(line_match.group(1))
                error_details.append(f"错误位置：第 {line_num} 行")
                # 尝试显示该行的内容
                try:
                    lines = new_toml_text.split('\n')
                    if line_num <= len(lines):
                        error_line = lines[line_num - 1]
                        error_details.append(f"问题行内容：{error_line[:100]}")
                except:
                    pass
            if col_match:
                error_details.append(f"列位置：第 {col_match.group(1)} 列")

            # 降级：返回简单的文本格式
            return {
                "zh_cn": {
                    "title": "搬家项目更新",
                    "content": [
                        [{"tag": "text", "text": "✅ 搬家项目信息已更新"}],
                        [{"tag": "text", "text": f"📝 输入内容：{new_content[:50]}..."}],
                        [{"tag": "text", "text": detail} for detail in error_details]
                    ]
                }
            }

    @staticmethod
    def merge_new_content(llm_service, toml_text: str, new_text: str) -> tuple[Optional[str], Optional[str]]:
        """
        合并新内容到TOML配置

        Args:
            llm_service: LLM服务实例
            toml_text: 当前TOML配置文本
            new_text: 新增的自然语言内容

        Returns:
            tuple[Optional[str], Optional[str]]: (合并后的完整TOML文本, 建议文本)，失败返回(None, None)
        """
        prompt = PROMPT_MOVE_MERGE.format(
            TOML_TEXT=toml_text,
            NEW_TEXT=new_text
        )

        try:
            llm_response = llm_service.simple_chat(prompt, max_tokens=5000)

            # 提取TOML内容和建议
            toml_start_marker = "===TOML_START==="
            toml_end_marker = "===TOML_END==="
            suggestions_start_marker = "===SUGGESTIONS_START==="
            suggestions_end_marker = "===SUGGESTIONS_END==="

            merged_toml = None
            suggestions = None

            # 提取TOML部分
            if toml_start_marker in llm_response and toml_end_marker in llm_response:
                start_idx = llm_response.find(toml_start_marker) + len(toml_start_marker)
                end_idx = llm_response.find(toml_end_marker)
                merged_toml = llm_response[start_idx:end_idx].strip()
            else:
                # 如果没有标记，尝试提取（兼容旧格式）
                merged_toml = llm_response.strip()
                # 清理可能的markdown代码块标记
                if merged_toml.startswith("```toml"):
                    merged_toml = merged_toml[7:]
                if merged_toml.startswith("```"):
                    merged_toml = merged_toml[3:]
                if merged_toml.endswith("```"):
                    merged_toml = merged_toml[:-3]
                merged_toml = merged_toml.strip()
                # 如果包含建议标记，移除建议部分
                if suggestions_start_marker in merged_toml:
                    merged_toml = merged_toml[:merged_toml.find(suggestions_start_marker)].strip()

            # 提取建议部分
            if suggestions_start_marker in llm_response and suggestions_end_marker in llm_response:
                start_idx = llm_response.find(suggestions_start_marker) + len(suggestions_start_marker)
                end_idx = llm_response.find(suggestions_end_marker)
                suggestions_text = llm_response[start_idx:end_idx].strip()
                if suggestions_text:
                    suggestions = suggestions_text

            if not merged_toml:
                raise ValueError("未能从LLM响应中提取TOML内容")

            # 验证TOML格式
            try:
                test_dict = toml.loads(merged_toml)
            except Exception as parse_error:
                error_msg = str(parse_error)
                debug_utils.log_and_print(
                    f"清理后的TOML格式验证失败: {error_msg}", log_level="ERROR"
                )
                # 尝试解析错误信息
                import re as re_module
                line_match = re_module.search(r'line (\d+)', error_msg, re_module.IGNORECASE)
                col_match = re_module.search(r'column (\d+)', error_msg, re_module.IGNORECASE)

                debug_utils.log_and_print(
                    f"TOML解析错误详情 - 错误信息: {error_msg}", log_level="ERROR"
                )
                if line_match:
                    line_num = int(line_match.group(1))
                    debug_utils.log_and_print(f"错误行号: {line_num}", log_level="ERROR")
                    lines = merged_toml.split('\n')
                    if line_num <= len(lines):
                        error_line = lines[line_num - 1]
                        debug_utils.log_and_print(f"错误行内容: {error_line}", log_level="ERROR")
                        # 显示前后几行上下文
                        start_line = max(0, line_num - 3)
                        end_line = min(len(lines), line_num + 2)
                        context_lines = lines[start_line:end_line]
                        debug_utils.log_and_print(
                            f"上下文（行{start_line+1}-{end_line}）:\n" + "\n".join(context_lines),
                            log_level="ERROR"
                        )
                if col_match:
                    debug_utils.log_and_print(f"错误列号: {col_match.group(1)}", log_level="ERROR")

                # 不直接返回None，让调用方处理
                raise ValueError(f"LLM生成的TOML格式错误: {error_msg}")

            # 程序化方式更新"更新时间"字段（确保即使LLM没更新也能正确）
            merged_toml = TempMoveModule._update_toml_timestamp_programmatic(merged_toml)

            return merged_toml, suggestions
        except Exception as e:
            debug_utils.log_and_print(
                f"合并新内容失败: {e}", log_level="ERROR"
            )
            import traceback
            debug_utils.log_and_print(
                f"详细错误堆栈:\n{traceback.format_exc()}", log_level="ERROR"
            )
            return None, None

