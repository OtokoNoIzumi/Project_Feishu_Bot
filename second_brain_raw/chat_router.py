"""
Chat router implementation.
"""

from typing import List, Dict, Optional, Any
from PIL import Image
import json
# scripts/llm/router/chat_router.py
class LLMRouter:
    def __init__(self, llm_client):
        self.llm_client = llm_client
        self.context_manager = llm_client.context_manager

    def route_chat(
        self,
        user_input: str,
        chat_history: Optional[List[Dict[str, str]]] = None,
        images: Optional[List[Image.Image]] = None,
        stream: bool = False,
        default_talk: str = "",
        pre_talk: str = "",
        stream_dict: Optional[List] = None,
        verbose: bool = False,
    ) -> tuple[str, Dict[str, Any]]:
        """
        处理用户输入并进行路由

        Args:
            user_input: 用户输入的文本
            chat_history: 聊天历史记录
            images: 可选的图片列表
            stream: 是否使用流式响应
            default_talk: 默认对话内容
            pre_talk: 模型回复前的预设文本
            stream_dict: 用于存储流式响应的列表
            verbose: 是否输出详细信息
        """
        # 获取上下文数据
        context_data = self.context_manager.collect_context_data(user_input)

        # 生成路由提示词
        context_prompt = self.context_manager.generate_context_prompt(
            user_input, context_data
        )

        # 准备聊天历史
        if chat_history is None:
            chat_history = []
        chat_history.append({"role": "user", "content": context_prompt})

        # 调用 LLM 获取路由决策
        response, prompt_tokens, answer_tokens, cost, complete = self.llm_client.chat(
            chat_history=chat_history,
            system_role_info=self.context_manager.module_manager.generate_system_prompt(),
            stream=stream,
            default_talk=default_talk,
            pre_talk=pre_talk,
            stream_dict=stream_dict,
            images=images,
            verbose=verbose,
        )

        # 解析响应，进行二次路由
        router_result = self._parse_routing_response(response)

        # 提取最高置信度
        highest_confidence = router_result[0]["confidence"]

        module_info = self.context_manager.module_manager.list_modules()

        # 根据置信度处理
        if verbose:
            if highest_confidence >= 0.9:
                # 执行最高置信度对应的模块
                print(f"执行 {router_result[0]['target_module']} 模块")
                print(f"参数: {module_info[router_result[0]['target_module']]['data_structure']}")
            else:
                print("置信度不足,请选择:")
                print(f"1. {router_result[0]['target_module']}: {module_info[router_result[0]['target_module']]['data_structure']}")
                print(f"2. {router_result[1]['target_module']}: {module_info[router_result[1]['target_module']]['data_structure']}")
                print("3. 其他可用模块:")
                for module in module_info:
                    if module_info[module]["enable"] and module not in [r["target_module"] for r in router_result]:
                        print(f"   - {module}")

        return response, {
            "routing": router_result,
            "stats": {
                "prompt_tokens": prompt_tokens,
                "answer_tokens": answer_tokens,
                "cost": cost,
                "complete": complete
            }
        }

    def _parse_routing_response(self, response: str) -> Dict[str, Any]:
        test_split = response.split("json")
        use_pos = min(len(test_split) - 1, 1)
        finaltext = response.split("json")[use_pos].strip().replace("```", "")
        router_result = json.loads(finaltext, strict=False)

        return router_result
