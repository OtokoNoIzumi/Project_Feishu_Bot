"""
Diet Advice Usecase.
"""

from typing import Any, Dict, Optional

from libs.api_keys.api_key_manager import get_default_api_key_manager
from libs.llm_gemini.gemini_client import GeminiClientConfig, GeminiStructuredClient

from apps.common.utils import parse_occurred_at
from apps.diet.context_provider import get_context_bundle
from apps.diet.prompt_builder_advice import build_diet_advice_prompt, build_independent_chat_prompt
from apps.diet.llm_schema import ADVISOR_CHAT_SCHEMA
from apps.common.dialogue_service import DialogueService
from apps.common.user_bio_service import UserBioService

class DietAdviceUsecase:
    """
    Usecase for generating diet advice.
    """

    # pylint: disable=too-few-public-methods

    def __init__(self, gemini_model_name: str):
        self.api_keys = get_default_api_key_manager()
        self.client = GeminiStructuredClient(
            api_key_manager=self.api_keys,
            config=GeminiClientConfig(model_name=gemini_model_name, temperature=0.4),
        )


    async def execute_async(
        self, 
        user_id: str, 
        facts: Dict[str, Any], 
        user_note: Optional[str] = None,
        dialogue_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Execute advice generation.
        
        Modes:
        1. Independent Chat Mode: If facts are empty (or nearly empty).
           - Output: JSON Schema (ADVISOR_CHAT_SCHEMA)
           - Focus: General Q&A, Planning, User Bio Update.
           
        2. Analysis Critique Mode: If facts contain diet data (dishes/summary).
           - Output: Free Text (+ optional UPDATE_USER_BIO command side-effect)
           - Focus: Critiquing the specific meal.
        """
        # 0. 尝试从 facts 中提取发生时间 & 排重ID
        target_date_str = None
        occurred_at = facts.get("occurred_at")
        if occurred_at:
            dt = parse_occurred_at(occurred_at)
            if dt:
                target_date_str = dt.strftime("%Y-%m-%d")

        # [Deduplication] 获取前端正在编辑的旧记录 ID，以便在 Context 中排除它
        ignore_record_id = facts.get("saved_record_id")

        # 1. 获取上下文 (Apply Filter)
        context_bundle = get_context_bundle(
            user_id=user_id, 
            target_date=target_date_str,
            ignore_record_id=ignore_record_id
        )

        # 2. 获取对话历史 (if in Chat Mode or needed)
        # 仅在 Independent Mode 中我们强烈需要对话历史来维持上下文
        recent_messages = []
        if dialogue_id:
            try:
                svc = DialogueService(user_id) # Direct instantiation for internal use
                dialogue = svc.get_dialogue(dialogue_id)
                if dialogue and dialogue.messages:
                    recent_messages = dialogue.messages[-10:] # Last 10 messages
            except Exception as e:
                print(f"Failed to fetch dialogue history: {e}")

        # 3. 判断模式
        has_analyze_data = bool(facts.get("dishes")) or bool(facts.get("meal_summary"))
        
        # === MODE 1: Independent Chat (Structure Output) ===
        if not has_analyze_data:

            # [Logic: Dialogue Cleaning & Incremental Info]
            
            # A. 清洗对话流：剔除 Card 关联消息，只保留纯对话
            clean_messages = []
            last_msg_time = None
            
            if recent_messages:
                for msg in recent_messages:
                    # Filter out messages that generated cards (functional noise)
                    if msg.linked_card_id:
                        continue
                    # Filter out empty messages
                    if not msg.content or not msg.content.strip():
                        continue
                    
                    clean_messages.append(msg)
                    
                    # Track timestamp of the last valid message
                    if msg.timestamp:
                         last_msg_time = msg.timestamp

            # B. 计算增量信息 (The Delta)
            # 找出那些发生在 last_msg_time 之后的饮食记录
            incremental_records = []
            recent_history = context_bundle.get("recent_history", []) # List[{occurred_at, line_str}]
            
            # Prepare Base History Strings (All history - Incremental)
            # Initial Assumption: Recent History contains EVERYTHING needed.
            # But Prompt Builder needs "History Table" AND "Incremental".
            # We should probably pass ALL into "History Table" OR split them.
            # User request: "Incremental Info" section.
            # Let's split:
            # 1. Base History (Before Dialogue) -> Goes to History Table
            # 2. Incremental (After Dialogue) -> Goes to New Info
            
            # Split History into Base (Before Dialogue) and Incremental (After Dialogue) to restore context accurately.
            base_history_lines = []
            
            if last_msg_time:
                try:
                    cutoff_dt = last_msg_time
                    if isinstance(cutoff_dt, str):
                        cutoff_dt = datetime.fromisoformat(cutoff_dt)
                    if cutoff_dt.tzinfo:
                         cutoff_dt = cutoff_dt.replace(tzinfo=None)
                    
                    for item in recent_history:
                        occurred = item.get("occurred_at")
                        line = item.get("line_str")
                        if not occurred or not line: continue
                        
                        rec_dt = datetime.fromisoformat(occurred)
                        if rec_dt.tzinfo:
                             rec_dt = rec_dt.replace(tzinfo=None)
                        
                        if rec_dt > cutoff_dt:
                            incremental_records.append(line)
                        else:
                            base_history_lines.append(line)
                except Exception as e:
                    print(f"[Warning] Incremental calc failed: {e}")
                    # Fallback: All to base
                    base_history_lines = [x.get("line_str") for x in recent_history]
            else:
                # No dialogue history -> All base
                base_history_lines = [x.get("line_str") for x in recent_history]

            # [Key Logic Fix] 
            # We pass ONLY base_history to the Prompt's "History Table" section.
            # The "Incremental Section" will handle the new records.
            context_bundle_for_prompt = context_bundle.copy()
            context_bundle_for_prompt["recent_history"] = base_history_lines
            
            # C. Build Prompt
            user_input = user_note or ""
            prompt = build_independent_chat_prompt(
                context_bundle=context_bundle_for_prompt, 
                user_input=user_input,
                recent_messages=clean_messages, # Pass Cleaned Msg
                incremental_records=incremental_records # Pass Delta Strings
            )
            print("test-advice-chat-prompt", prompt)
            
            # 使用 JSON Schema 生成
            llm_result = await self.client.generate_json_async(
                prompt=prompt,
                images=[],
                schema=ADVISOR_CHAT_SCHEMA,
                scene="advisor_chat",
                user_id=user_id
            )
            
            if isinstance(llm_result, dict) and llm_result.get("error"):
                return {"error": llm_result.get("error")}
            
            # 处理 Bio Update (Structured)
            bio_update = llm_result.get("user_bio_update")
            if bio_update:
                self._apply_bio_update(user_id, bio_update)
            
            return {"advice_text": llm_result.get("reply_text", "")}

        # === MODE 2: Analysis Critique (Text Output + Side-effect Command) ===
        else:
            # [Fix] Pre-process recent_history (List[Dict]) -> List[Str] for Prompt Builder
            raw_history = context_bundle.get("recent_history", []) # List[{occurred_at, line_str}]
            str_history = [x.get("line_str",str(x)) for x in raw_history if isinstance(x, dict)]
            
            context_bundle_for_prompt = context_bundle.copy()
            context_bundle_for_prompt["recent_history"] = str_history

            prompt = build_diet_advice_prompt(
                facts=facts, context_bundle=context_bundle_for_prompt, user_input=user_note.strip()
            )
            print("test-advice-critique-prompt", prompt)
            
            advice_text = await self.client.generate_text_async(
                prompt=prompt, 
                images=[], 
                scene="diet_advice", 
                user_id=user_id
            )
            
            if advice_text.startswith("Gemini") and "失败" in advice_text:
                return {"error": advice_text}

            return {"advice_text": advice_text}

    def _apply_bio_update(self, user_id: str, update_data: Dict[str, Any]):
        add_list = update_data.get("add", [])
        remove_list = update_data.get("remove", [])
        if add_list or remove_list:
            try:
                UserBioService.update_bio(user_id, add=add_list, remove=remove_list)
                print(f"Updated user bio (Structured) for {user_id}: +{add_list} -{remove_list}")
            except Exception as e:
                print(f"Failed to update bio: {e}")
