"""
AI 战术处方服务 (LLM Agent)
=========================
集成 RAG: 调用 LLM 前先从《大师战术与配方百科全书》检索
Top-K 匹配秘籍, 作为参考蜂蜂注入 user prompt, 提升处方专业度。
"""
import json
import os
import dashscope
from .prompts import SYSTEM_PROMPT_FISHING_EXPERT, build_user_prompt
from .master_kb import MasterKBRetriever, format_references_for_prompt

dashscope.api_key = os.getenv("DASHSCOPE_API_KEY", "")

class PrescriptionService:
    """调用通义千问大模型生成战术处方。

    集成了大师知识库 RAG 检索：调用 LLM 前会按
    (鱼种 / 季节 / 水温 / 气压状态) 收回 Top-K 大师战术，
    注入到 user prompt 中作为蓝本。
    """
    def __init__(self, model_name="qwen-turbo", top_k: int = 3):
        self.model_name = model_name
        self.top_k = top_k

    def _build_references(self, metrics: dict, fish_context: dict) -> str:
        """调用检索器生成参考秘籍文本块，失败时返回空串。"""
        try:
            kb = MasterKBRetriever.get()
            target_fish = (fish_context or {}).get("target")
            t_water = None
            if metrics:
                t_water = metrics.get("t_water_avg")
            # 气压趋势从 metrics 推导
            pressure_state = None
            dp = (metrics or {}).get("delta_p_2h")
            if isinstance(dp, (int, float)):
                if dp <= -3.0:
                    pressure_state = "骤降"
                elif dp <= -1.0:
                    pressure_state = "骤降"
                elif dp >= 1.0:
                    pressure_state = "上升"
                else:
                    pressure_state = "稳定"
            records = kb.search(
                target_fish=target_fish,
                t_water=t_water,
                pressure_state=pressure_state,
                top_k=self.top_k,
            )
            return format_references_for_prompt(records)
        except Exception:
            return ""

    def generate_prescription(
        self, physical_tags: list, symptom_tags: list, metrics: dict, fish_context: dict, user_inventory: dict = None
    ) -> dict:
        # 1. RAG 检索大师秘籍 (任何异常不阐断主流程)
        references_block = self._build_references(metrics, fish_context)

        # 2. 构建带参考的 prompt
        user_prompt = build_user_prompt(
            physical_tags,
            symptom_tags,
            metrics,
            fish_context,
            user_inventory,
            references_block=references_block,
        )

        messages = [
            {'role': 'system', 'content': SYSTEM_PROMPT_FISHING_EXPERT},
            {'role': 'user', 'content': user_prompt}
        ]
        
        if not dashscope.api_key:
            return self._fallback_prescription("未配置 DASHSCOPE_API_KEY 环境变量")
            
        try:
            response = dashscope.Generation.call(
                model=self.model_name,
                messages=messages,
                result_format='message',
                max_tokens=1500,
                temperature=0.7
            )
            
            if response.status_code == 200:
                content = response.output.choices[0]['message']['content']
                content = content.strip()
                if content.startswith("```json"):
                    content = content[7:]
                if content.startswith("```"):
                    content = content[3:]
                if content.endswith("```"):
                    content = content[:-3]
                    
                return json.loads(content.strip())
            else:
                return self._fallback_prescription(f"API Error: {response.code} - {response.message}")
        except Exception as e:
            return self._fallback_prescription(f"Exception: {str(e)}")
            
    def _fallback_prescription(self, error_msg: str) -> dict:
        """兑底返回，保证流程不断"""
        return {
            "diagnosis": "系统暂时无法呼叫云端老师傅，请根据自身经验调整。",
            "prescriptions": [
                {"action": "更换钓位或调整钓深", "reason": "当情况不明时，多尝试不同水层和位置是破局关键"}
            ],
            "references": [],
            "confidence_note": f"Fallback模式启动 ({error_msg})"
        }
