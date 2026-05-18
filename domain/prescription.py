"""
AI 战术处方服务 (LLM Agent)
"""
import json
import os
import dashscope
from .prompts import SYSTEM_PROMPT_FISHING_EXPERT, build_user_prompt

dashscope.api_key = os.getenv("DASHSCOPE_API_KEY", "")

class PrescriptionService:
    """调用通义千问大模型生成战术处方。"""
    def __init__(self, model_name="qwen-turbo"):
        self.model_name = model_name

    def generate_prescription(
        self, physical_tags: list, symptom_tags: list, metrics: dict, fish_context: dict
    ) -> dict:
        user_prompt = build_user_prompt(physical_tags, symptom_tags, metrics, fish_context)
        
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
                max_tokens=500,
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
        """兜底返回，保证流程不断"""
        return {
            "diagnosis": "系统暂时无法呼叫云端老师傅，请根据自身经验调整。",
            "prescriptions": [
                {"action": "更换钓位或调整钓深", "reason": "当情况不明时，多尝试不同水层和位置是破局关键"}
            ],
            "confidence_note": f"Fallback模式启动 ({error_msg})"
        }
