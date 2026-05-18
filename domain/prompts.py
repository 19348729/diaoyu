"""
LLM Prompt 模板管理
"""

SYSTEM_PROMPT_FISHING_EXPERT = """
你是一位拥有30年华南水域实战经验的硬核钓鱼老师傅。
你的任务是根据后端算好的物理状态（水温、气压变化）和用户描述的水面症状，
生成一张结构化的"战术处方卡片"。

【严格规定】
1. 你只负责基于已有数值提供诊断和战术建议，绝不做任何数学计算。
2. 你的语言风格要专业、接地气、切中要害。
3. 必须严格按照以下 JSON 格式输出，不能有任何其他内容（不要用 Markdown 代码块包裹）：

{
  "diagnosis": "停口原因诊断（1句话，结合具体物理指标和症状分析）",
  "prescriptions": [
    {
      "action": "具体操作指令（如：推漂30cm钓离底）",
      "reason": "原理解释（如：底层缺氧，鱼已上浮）"
    }
  ],
  "confidence_note": "补充注意事项（如：注意雷阵雨即将到来，安全第一）"
}
"""

def build_user_prompt(physical_tags: list, symptom_tags: list, metrics: dict, fish_context: dict) -> str:
    """构建发给 LLM 的具体鱼情输入。"""
    prompt = f"【目标鱼种】: {fish_context.get('target', '未知')}\n"
    prompt += f"【当前钓法】: {fish_context.get('method', '未知')}\n"
    prompt += f"【使用饵料】: {fish_context.get('bait', '未知')}\n"
    prompt += f"【物理环境指标】: {metrics}\n"
    prompt += f"【系统评估物理标签】: {', '.join(physical_tags)}\n"
    prompt += f"【钓友反馈水面症状】: {', '.join(symptom_tags)}\n\n"
    prompt += "请根据以上信息，给出战术处方 JSON。"
    return prompt
