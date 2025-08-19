"""
飞书卡片JSON格式封装构建工具类
"""

from typing import List, Dict, Any
from Module.Services.constants import (
    ColorTypes,
)


class JsonBuilder:
    """飞书卡片JSON构建工具类

    提供静态方法用于构建飞书卡片的各种元素和结构
    """

    # region 卡片结构
    @staticmethod
    def build_base_card_structure(
        elements: List[Dict[str, Any]],
        header: Dict[str, Any],
        padding: str = "12px",
    ) -> Dict[str, Any]:
        """构建基础卡片结构"""
        return {
            "schema": "2.0",
            "config": {"update_multi": True, "wide_screen_mode": True},
            "body": {"direction": "vertical", "padding": padding, "elements": elements},
            "header": header,
        }

    # region 卡片结构
    @staticmethod
    def build_stream_card_structure(
        elements: List[Dict[str, Any]],
        header: Dict[str, Any],
        padding: str = "12px",
        summary: str = "",
        print_frequency_ms: int = 70,
        print_step: int = 1,
        print_strategy: str = "fast",
    ) -> Dict[str, Any]:
        """
        构建流式卡片结构，参考飞书官方流式卡片示例
        """
        return {
            "schema": "2.0",
            "header": header,
            "config": {
                "streaming_mode": True,
                "summary": {"content": summary},
                "streaming_config": {
                    "print_frequency_ms": {
                        "default": print_frequency_ms,
                    },
                    "print_step": {
                        "default": print_step,
                    },
                    "print_strategy": print_strategy,
                },
            },
            "body": {"direction": "vertical", "padding": padding, "elements": elements},
        }

    @staticmethod
    def build_card_header(
        title: str,
        subtitle: str = "",
        template: str = ColorTypes.BLUE.value,
        icon: str = "",
    ) -> Dict[str, Any]:
        """构建通用卡片头部"""
        header = {
            "title": {"tag": "plain_text", "content": title},
            "template": template,
        }

        if subtitle:
            header["subtitle"] = {"tag": "plain_text", "content": subtitle}

        if icon:
            header["icon"] = {"tag": "standard_icon", "token": icon}

        return header

    @staticmethod
    def build_status_based_header(
        base_title: str,
        is_confirmed: bool,
        result: str,
        confirmed_prefix: str = "",
    ) -> Dict[str, Any]:
        """构建基于状态的卡片头部 - 适用于确认类卡片"""
        if not is_confirmed:
            return JsonBuilder.build_card_header(
                base_title, "请确认记录信息", ColorTypes.BLUE.value, "edit_outlined"
            )

        if result == "确认":
            title = (
                f"{confirmed_prefix}{base_title}" if confirmed_prefix else base_title
            )
            return JsonBuilder.build_card_header(
                title, "记录信息已确认并保存", ColorTypes.GREEN.value, "done_outlined"
            )

        return JsonBuilder.build_card_header(
            "操作已取消", "", ColorTypes.GREY.value, "close_outlined"
        )

    # endregion

    # region 简单元素
    @staticmethod
    def build_input_element(
        placeholder: str,
        initial_value: str,
        disabled: bool,
        action_data: Dict[str, Any],
        name: str = "",
        element_id: str = "",
        required: bool = False,
    ) -> Dict[str, Any]:
        """构建输入框元素"""
        final_element = {
            "tag": "input",
            "element_id": element_id,
            "placeholder": {"tag": "plain_text", "content": placeholder},
            "default_value": str(initial_value),
            "disabled": disabled,
            "name": name or element_id,
            "behaviors": [{"type": "callback", "value": action_data}],
        }
        if required:
            # 仅表单里可用用，表单外赋值会报错。
            final_element["required"] = True
        return final_element

    @staticmethod
    def build_select_element(
        placeholder: str,
        options: List[Dict[str, Any]],
        initial_value: str,
        disabled: bool,
        action_data: Dict[str, Any],
        element_id: str = "",
        name: str = "",
    ) -> Dict[str, Any]:
        """构建选择器元素"""
        # 查找初始选择索引，对飞书来说，索引从1开始，所以需要+1
        initial_index = -1
        for i, option in enumerate(options):
            if option.get("value") == initial_value:
                initial_index = i + 1
                break

        return {
            "tag": "select_static",
            "element_id": element_id,
            "placeholder": {"tag": "plain_text", "content": placeholder},
            "options": options,
            "initial_index": initial_index if initial_index >= 0 else None,
            "width": "fill",
            "disabled": disabled,
            "name": name or element_id,
            "behaviors": [{"type": "callback", "value": action_data}],
        }

    @staticmethod
    def build_date_picker_element(
        placeholder: str,
        initial_date: str,
        disabled: bool,
        action_data: Dict[str, Any],
        name: str = "",
    ) -> Dict[str, Any]:
        """构建日期选择器元素"""
        element = {
            "tag": "picker_datetime",
            "placeholder": {"tag": "plain_text", "content": placeholder},
            "disabled": disabled,
            "behaviors": [{"type": "callback", "value": action_data}],
            "name": name,
        }

        if initial_date:
            element["initial_datetime"] = initial_date

        return element

    @staticmethod
    def build_checker_element(
        text: str,
        checked: bool,
        disabled: bool,
        action_data: Dict[str, Any] = None,
    ) -> Dict[str, Any]:
        """构建复选框元素"""
        final_element = {
            "tag": "checker",
            "text": {"tag": "plain_text", "content": text},
            "checked": checked,
            "disabled": disabled,
        }
        if action_data:
            final_element["behaviors"] = [{"type": "callback", "value": action_data}]
        return final_element

    @staticmethod
    def build_multi_select_element(
        placeholder: str,
        options: List[Dict[str, Any]],
        initial_values: List[str],
        disabled: bool,
        action_data: Dict[str, Any],
        element_id: str = "",
        name: str = "",
    ) -> Dict[str, Any]:
        """构建多选选择器元素"""
        return {
            "tag": "multi_select_static",
            "element_id": element_id,
            "placeholder": {"tag": "plain_text", "content": placeholder},
            "options": options,
            "selected_values": initial_values,
            "width": "fill",
            "disabled": disabled,
            "name": name or element_id,
            "behaviors": [{"type": "callback", "value": action_data}],
        }

    @staticmethod
    def build_markdown_element(
        content: str,
        text_size: str = "normal",
        element_id: str = "",
    ) -> Dict[str, Any]:
        """构建markdown元素"""
        final_element = {
            "tag": "markdown",
            "content": content,
            "text_size": text_size,
        }
        if element_id:
            final_element["element_id"] = element_id
        return final_element

    @staticmethod
    def build_line_element(
        margin: str = "6px 0px",
    ) -> Dict[str, Any]:
        """构建分割线元素"""
        return {
            "tag": "hr",
            "margin": margin,
        }

    @staticmethod
    def build_button_element(
        text: str,
        action_data: Dict[str, Any] = None,
        disabled: bool = False,
        element_id: str = "",
        name: str = "",
        button_type: str = "default",
        size: str = "medium",
        icon: str = "",
        form_action_type: str = "",
        url_data: Dict[str, Any] = None,
    ) -> Dict[str, Any]:
        """构建按钮元素"""
        final_element = {
            "tag": "button",
            "text": {"tag": "plain_text", "content": text},
            "disabled": disabled,
            "type": button_type,
            "size": size,
        }
        if action_data:
            final_element["behaviors"] = [{"type": "callback", "value": action_data}]
        elif url_data:
            final_element["behaviors"] = [{"type": "open_url", **url_data}]
        if name:
            final_element["name"] = name
        if element_id:
            final_element["element_id"] = element_id
        if icon:
            final_element["icon"] = {"tag": "standard_icon", "token": icon}
        if form_action_type:
            final_element["form_action_type"] = form_action_type
        return final_element

    @staticmethod
    def build_options(
        options_dict: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """构建选项元素 - 用于构建选择器元素的选项"""
        options = []
        for key, content in options_dict.items():
            options.append(
                {
                    "text": {"tag": "plain_text", "content": content},
                    "value": key,
                }
            )
        return options

    @staticmethod
    def build_image_element(
        image_key: str,
        alt: str,
        title: str,
        corner_radius: str = "",
        scale_type: str = "",
        size: str = "",
    ) -> Dict[str, Any]:
        """构建图片元素"""
        final_element = {
            "tag": "img",
            "img_key": image_key,
            "alt": {"tag": "plain_text", "content": alt},
        }
        if title:
            final_element["title"] = {"tag": "plain_text", "content": title}
        if corner_radius:
            final_element["corner_radius"] = corner_radius
        if scale_type:
            final_element["scale_type"] = scale_type
        if size and scale_type in ["crop_center", "crop_top"]:
            final_element["size"] = size
        return final_element

    @staticmethod
    def build_chart_element(
        chart_type: str,
        title: str,
        data: List[Dict[str, Any]],
        chart_spec: Dict[str, Any] = None,
        color_mapping: Dict[str, str] = None,
        formatter: str = "",
    ) -> Dict[str, Any]:
        """构建图表元素"""
        final_element = {
            "tag": "chart",
        }
        if chart_spec:
            final_element["chart_spec"] = chart_spec
        else:
            final_element["chart_spec"] = {
                "type": chart_type,
            }
            if chart_type == "pie":
                value_field = (
                    "value" if data and "value" in data[0].keys() else data[0].keys()[1]
                )
                category_field = (
                    "type" if data and "type" in data[0].keys() else data[0].keys()[0]
                )
                final_element["chart_spec"]["valueField"] = value_field
                final_element["chart_spec"]["categoryField"] = category_field
                final_element["chart_spec"]["outerRadius"] = 0.7
                final_element["chart_spec"]["innerRadius"] = 0.3
                final_element["chart_spec"]["legends"] = {
                    "visible": True,
                    "orient": "bottom",
                    "maxRow": 3,
                }
                final_element["chart_spec"]["label"] = {
                    "visible": True,
                }
                if formatter:
                    final_element["chart_spec"]["label"]["formatter"] = formatter

        if title:
            final_element["chart_spec"]["title"] = {"text": title}
        if data:
            final_element["chart_spec"]["data"] = {"values": data}
            if color_mapping:
                category_field = (
                    "type" if data and "type" in data[0].keys() else data[0].keys()[0]
                )
                colors = [
                    color_mapping.get(item.get(category_field), "#959BEE")
                    for item in data
                ]
                final_element["chart_spec"]["color"] = colors
        return final_element

    @staticmethod
    def build_audio_element(
        file_key: str,
        element_id: str = "",
        audio_id: str = "",
        style: str = "normal",  # 还可以用speak
    ) -> Dict[str, Any]:
        """构建音频元素"""
        final_element = {
            "tag": "audio",
            "file_key": file_key,
        }
        if element_id:
            final_element["element_id"] = element_id
        if audio_id:
            final_element["audio_id"] = audio_id
        if style:
            final_element["style"] = style

        return final_element

    # endregion

    # region 组合结构

    @staticmethod
    def build_form_row(
        label: str,
        element: Dict[str, Any],
        width_list: List[str] = None,
        element_id: str = "",
        third_element: Dict[str, Any] = None,
    ) -> Dict[str, Any]:
        """构建表单行"""
        if width_list is None:
            width_list = ["80px", "180px"]

        final_row = {
            "tag": "column_set",
            "horizontal_align": "left",
            "element_id": element_id,
            "columns": [
                {
                    "tag": "column",
                    "width": width_list[0],
                    "elements": [
                        {
                            "tag": "markdown",
                            "content": f"**{label}**",
                            "text_align": "left",
                        }
                    ],
                    "vertical_align": "center",
                },
                {"tag": "column", "width": width_list[1], "elements": [element]},
            ],
        }
        if third_element is not None:
            third_elem = third_element if third_element is not None else element
            final_row["columns"].append(
                {
                    "tag": "column",
                    "width": width_list[2] if len(width_list) > 2 else "auto",
                    "elements": [third_elem],
                    "vertical_align": "center",
                }
            )
        return final_row

    @staticmethod
    def build_column_set_element(
        columns: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """构建列组元素"""
        return {"tag": "column_set", "columns": columns}

    @staticmethod
    def build_column_element(
        elements: List[Dict[str, Any]],
        width: str = "auto",
        vertical_align: str = "top",
        horizontal_align: str = "left",
    ) -> Dict[str, Any]:
        """构建列元素"""
        return {
            "tag": "column",
            "width": width,
            "vertical_align": vertical_align,
            "horizontal_align": horizontal_align,
            "elements": elements,
        }

    @staticmethod
    def build_button_group_element(
        buttons: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """构建按钮组元素"""
        columns = [JsonBuilder.build_column_element([button]) for button in buttons]
        return JsonBuilder.build_column_set_element(columns)

    @staticmethod
    def build_collapsible_panel_element(
        header_text: str,
        header_icon: str,
        icon_size: str = "16px 16px",
        expanded: bool = False,
        content: List[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """构建折叠面板元素"""
        if content is None:
            content = []

        return {
            "tag": "collapsible_panel",
            "expanded": expanded,
            "header": {
                "title": {"tag": "markdown", "content": header_text},
                "icon": {
                    "tag": "standard_icon",
                    "token": header_icon,
                    "color": "",
                    "size": icon_size,
                },
                "icon_position": "right",
                "icon_expanded_angle": -180,
            },
            "elements": content,
        }

    @staticmethod
    def build_form_element(
        elements: List[Dict[str, Any]],
        name: str = "",
    ) -> Dict[str, Any]:
        """构建表单元素"""
        return {"tag": "form", "elements": elements, "name": name}

    @staticmethod
    def build_table_column_element(
        name: str,
        display_name: str,
        data_type: str,
        width: str = "auto",
        horizontal_align: str = "center",
    ) -> Dict[str, Any]:
        """构建表格列元素"""
        return {
            "name": name,
            "display_name": display_name,
            "data_type": data_type,
            "width": width,
            "horizontal_align": horizontal_align,
        }

    @staticmethod
    def build_table_element(
        columns: List[Dict[str, Any]],
        rows: List[Dict[str, Any]],
        page_size: int = 6,
        freeze_first_column: bool = False,
    ) -> Dict[str, Any]:
        """构建表格元素"""
        return {
            "tag": "table",
            "columns": columns,
            "rows": rows,
            "page_size": page_size,
            "freeze_first_column": freeze_first_column,
            "header_style": {
                "text_align": "center",
                "background_style": "grey",
            },
        }

    # endregion
