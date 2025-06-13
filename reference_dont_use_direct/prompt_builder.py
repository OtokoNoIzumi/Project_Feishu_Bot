"""
提示词构建器模块 - 负责构建与管理Gemini API的提示词
对应原始代码的 PromptBuilder 类 (约108-183行)
"""
from datetime import datetime
from ..utils.formatter import calculate_pure_visual_or_music_time


class PromptBuilder:
    """
    提示词构建器 - 动态构建Gemini API的提示词
    """
    def __init__(self, field_keys, negative_field_keys, prompt_version="default"):
        """
        初始化提示词构建器

        参数:
        - field_keys: 字段描述字典，用于分类
        - negative_field_keys: 负面类型列表
        - prompt_version: 提示词版本，默认为"default"
        """
        self.field_keys = field_keys
        self.negative_field_keys = negative_field_keys
        self.prompt_version = prompt_version
        # 生成基础提示模板 - 保留占位符用于条件块
        self.base_template = self._generate_base_template()

    def _generate_base_template(self):
        """
        生成包含占位符的基础提示模板
        这里使用 {PLACEHOLDER_XXX} 作为后续条件内容的占位符
        """
        template = [
            # 基础描述部分
            "以下是视频的附属信息。",
            "请根据信息判断视频属于每个分组的置信度（0-100之间的整数，0表示完全不属于，100表示完全属于），",
            "请识别视频可能违反我们对内容的要求的情况，如果有这些倾向，请对这些情况的置信度评分（0-100之间的整数，0表示完全不违反）。",
            f"请全面评估视频内容的负面特征，包括但不限于以下类型：{', '.join(self.negative_field_keys)}，但显然在搞笑的除外。",
            "除了这些预设类型外，还应主动识别并标记出任何可能降低视频价值的因素，如引战的极端言论、误导性信息、虚假健康建议等，但不要把性和低俗相关的因素加入到负面特征里。",
            "识别额外类型需要结合上下文推断的情景，比如一个类脱口秀里面当然就会有一些冒犯，这显然不是引战极端言论；",
            "而一个相对离奇和诉诸情绪的标题，如果上下文没有可靠或匹配其主张强度的补充，则其主张也很可能有问题。",
            "对于每种发现的负面特征，请给出具体名称和置信度评分。",
            "{PLACEHOLDER_DURATION}",
            "",
            # 广告分析的常驻部分（推广广告评估）
            "特别注意区分以下两种情况：",
            "1. 推广广告：整个视频的主要目的是商业推广，内容重点是推销产品或服务。如果视频属于这类，应在负面分类中标记为'推广广告'。",
            "2. 植入广告：在有实质内容的视频中插入的广告片段。这种情况下视频本身不应被归类为推广广告。",
            "植入广告的特点是：在视频标题定义的主题概念下衍生的非广告主体内容中，出现与标题核心主题无关、且与视频主要叙述流程生硬切换的片段，其目的是推广标题未提及的外部品牌或产品。",
            "",
            "请针对每个视频信息组件进行单独的广告倾向性评估：",
            "- 1. 标题：视频稿件的标题，优秀作品通常也会和视频主题相关、亦或者是有设计的对主题的暗喻，但不会是广告。",
            "- 2. 投稿说明和作者动态：作者自己撰写的辅助信息，通常不会影响视频的观看。",
            "- 3. 字幕：视频字幕是AI根据视频内容生成的，可能包括视频里的所有人声，"
            "包括视频制作者的后期解说，以及视频里的角色的台词，还可能有错别字。",
            "每个组件的倾向性评分应独立进行，范围为0-100。如果某个组件内容不存在，则其倾向性为0。",
            "",
            # 植入广告分析占位符
            "{PLACEHOLDER_AD_TIMESTAMP}",

            # 时效性分析占位符
            "{PLACEHOLDER_TIME_RELEVANCE}",

            # 最后的推荐理由
            "最后，站在一个资深责编的视角，用一句不超过27个字的中文，基于广告之外的视频主题内容，写一个向我推荐看这个视频的最大的理由。"
            "不用强调广告如何，我会根据你给的广告片段做单独处理。",
            "",
            # 视频分类
            "可选的视频分组："
        ]

        # 添加分类描述，每个分类一行
        for key, desc in self.field_keys.items():
            template.append(f"- {key}：{desc}")

        template.append("--------------------------------")

        return template

    def _get_ad_timestamp_content(self, has_subtitle):
        """
        获取植入广告时间戳分析内容
        仅当有字幕时添加
        """
        if has_subtitle:
            return (
                "请结合标题、主题仔细阅读字幕内容，标注出广告片段的时间戳。",
                "注意，视频全程并不一定都会有字幕，对于没有字幕的内容部分，是你暂时无法访问但实际存在的纯视觉或音频内容，你要假定这些时间内的内容都是符合视频主题的。"
            )
        return "", ""

    def _get_time_relevance_analysis(self, has_pubdate):
        """
        获取时效性分析内容
        仅当有发布时间时添加
        """
        if has_pubdate:
            return (
                "请评估视频内容的时效性：\n"
                "  1. 时效性相关的置信度（0-100）\n"
                "  2. 时效性的信息价值系数（0-100，0表示完全过时无价值，100表示价值完全保留）\n"
                "  3. 时效性内容的具体内容概述（精简但不丢失关键要素）\n"
                "  4. 视频发布时间不算在待评估的视频内容中，而是用来衡量内容时效性是否过期的参数\n"
                "  5. 时效性内容摘要里不用包含视频发布时间，而是真的摘要。\n"
                "参考示例\n"
                "示例1：3月14日发布的视频，摘要是“2025年3月13日，美国宣布对中国进行贸易战，导致全球股市大跌。”，且当前时间不晚于3月14日，这就是高有效性；而如果摘要是“2025年3月13日，美国宣布对中国进行贸易战，导致全球股市大跌。”，这就是一个时效性信息。"
                "如果当前时间晚于3月15日，这就是低有效性；反之，这就是高有效性。\n"
                "示例2：2月17日发布的视频，摘要是“2025年2月18日，气温即将回升。”，且当前时间晚于2月18日，这就是低有效性；反之，这就是高有效性。"
            )
        return ""

    def update_categories(self, new_field_keys=None, new_negative_field_keys=None):
        """
        更新分类并重新生成基础提示

        参数:
        - new_field_keys: 新的字段描述字典
        - new_negative_field_keys: 新的负面类型列表
        """
        if new_field_keys:
            self.field_keys = new_field_keys
        if new_negative_field_keys:
            self.negative_field_keys = new_negative_field_keys
        self.base_template = self._generate_base_template()

    def build_prompt(self, video_info):
        """
        根据视频信息动态生成提示词

        参数:
        - video_info: 包含视频信息的字典

        返回:
        - 完整的提示词字符串和存在的组件信息
        """
        prompt_parts = self.base_template.copy()

        # 记录实际存在的组件
        existing_components = {'title': True}  # 标题总是存在的

        # 检测视频组件状态
        component_status = {
            'has_subtitle': False,
            'has_pubdate': False
        }

        # 添加当前评估时间（固定在开始）
        current_time = datetime.now()
        current_time_str = current_time.strftime('%Y年%m月%d日 %H:%M')

        prompt_parts.insert(0, f"当前的时间是：{current_time_str}")

        # 添加视频标题
        prompt_parts.append(f"视频标题：{video_info['title']}")

        # 添加发布时间（固定在标题后）
        if 'pubdate' in video_info and video_info['pubdate']:
            pub_timestamp = video_info['pubdate']
            pub_time = datetime.fromtimestamp(pub_timestamp)
            pub_time_str = pub_time.strftime('%Y年%m月%d日 %H:%M')
            prompt_parts.append(f"视频发布时间：{pub_time_str}")
            component_status['has_pubdate'] = True

        # 处理字段映射配置
        field_mapping = {
            'desc': {
                'condition': lambda x: x and x != '-',
                'name': "投稿说明",
                'prompt': "投稿说明：{}",
                'component': 'desc_dynamic'
            },
            'dynamic': {
                'condition': lambda x: x,
                'name': "作者动态",
                'prompt': "作者动态：{}",
                'component': 'desc_dynamic'
            },
            # 'summary_text': {
            #     'condition': lambda x: x,
            #     'name': None,
            #     'prompt': "视频摘要：{}",
            #     'component': 'summary'
            # }
        }

        # 处理用户内容和信息来源
        for field, config in field_mapping.items():
            if field in video_info and config['condition'](video_info[field]):
                # 记录组件存在
                existing_components[config['component']] = True
                # 添加到提示部分
                content = video_info[field]

                # 检查内容是否包含换行符或特殊格式
                needs_formatting = '\n' in content or ': ' in content
                formatted_content = f"\n```\n{content}\n```" if needs_formatting else content

                # 添加到提示部分
                prompt_parts.append(config['prompt'].format(formatted_content))
            else:
                prompt_parts.append(f"{config['prompt'].format('无')}")

        # 处理字幕内容
        subtitle_field = 'subtitle_content'
        subtitle_config = {
            'condition': lambda x: x and x != 'P1: []',
            'name': None,
            'prompt': "视频字幕：{}",
            'component': 'subtitle'
        }

        pure_time_total = 0
        if (
            subtitle_field in video_info and
            subtitle_config['condition'](video_info[subtitle_field])
        ):
            existing_components[subtitle_config['component']] = True
            content = video_info[subtitle_field]

            # 检查内容是否包含换行符或特殊格式
            needs_formatting = '\n' in content or ': ' in content
            formatted_content = f"\n```\n{content}\n```" if needs_formatting else content

            # 仅在有字幕时添加视频时长
            if 'duration' in video_info and video_info['duration']:
                duration_seconds = video_info['duration']
                durations = [page['duration'] for page in video_info['pages']]
                complement_intervals_total = []
                for i in range(len(video_info['subtitle_contents'])):
                    pure_time, complement_intervals = calculate_pure_visual_or_music_time(
                        video_info['subtitle_contents'][i], durations[i], use_dict_format=True
                    )
                    pure_time_total += pure_time
                    complement_intervals_total.extend(complement_intervals)

                plus_info = ""
                if pure_time_total > 1:  # 不用过于敏感
                    pure_time_total = round(pure_time_total, 1)
                    if len(complement_intervals_total) > 3:
                        plus_info = f"，有价值的纯视觉或音乐时长：{pure_time_total}秒"
                    else:
                        percentage = pure_time_total/duration_seconds*100
                        plus_info = (
                            "，其中不应被视为推广广告以及插入广告的，有实际体验内容的"
                            f"纯视觉或音乐区间：{complement_intervals_total}，占比{percentage:.2f}%"
                        )
            # 添加到提示部分
                prompt_parts.append(f"视频总时长：{duration_seconds}秒{plus_info}")
            prompt_parts.append(subtitle_config['prompt'].format(formatted_content))
            component_status['has_subtitle'] = True

        else:
            prompt_parts.append(subtitle_config['prompt'].format('无'))
        video_info['pure_time_total'] = pure_time_total
        # 合成最终提示词
        prompt_text = "\n".join(prompt_parts)

        # 分割为前半部分和后半部分，防止后半部分有注入内容
        separator = "--------------------------------"
        if separator in prompt_text:
            before_separator, after_separator = prompt_text.split(separator, 1)
        else:
            before_separator = prompt_text
            after_separator = ""

        # 添加植入广告分析（如果有字幕）
        ad_timestamp_content, ad_timestamp_content_note = self._get_ad_timestamp_content(
            component_status['has_subtitle']
        )
        time_relevance_content = self._get_time_relevance_analysis(component_status['has_pubdate'])

        # 只对前半部分进行格式化
        before_separator = before_separator.format(
            PLACEHOLDER_DURATION=ad_timestamp_content_note,
            PLACEHOLDER_AD_TIMESTAMP=ad_timestamp_content,
            PLACEHOLDER_TIME_RELEVANCE=time_relevance_content
        )

        # 重新拼接
        prompt_text = f"{before_separator}{separator}{after_separator}"

        return prompt_text, existing_components
