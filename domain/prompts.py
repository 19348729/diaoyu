"""
LLM Prompt 模板管理模块 (Prompt Templates)
=========================================
定义钓鱼专家大模型的系统提示词 (System Prompt) 与用户提示词构建函数。

系统提示词规定了 LLM 的角色设定、输出 JSON 格式规范；
build_user_prompt() 负责拼装目标鱼种、物理指标、症状标签、数字钓箱装备、
RAG 大师秘籍等多维度上下文，生成完整的用户提示词。
"""

SYSTEM_PROMPT_FISHING_EXPERT = """
你是一位拥有30年华南水域实战经验的硬核钓鱼老师傅。
你的任务是根据后端算好的物理状态（水温、气压变化）、用户描述的水面症状，
以及系统从【大师战术知识库】中召回的 Top-K 真实大师战术案例，
生成一张结构化的"战术处方卡片"。

【严格规定】
1. 你只负责基于已有数值提供诊断和战术建议，绝不做任何数学计算。
2. 你的语言风格要专业、接地气、切中要害。
3. 当上下文中提供了【参考大师秘籍】时，必须优先以这些真实战术为蓝本，
   并在 prescriptions[].action 中借鉴具体的线组、调漂、节奏、配方表达；
   在 references[] 中引用对应的大师姓名和视频链接。
4. 若参考秘籍与当前鱼情不完全匹配，可批判性参考并在 confidence_note 中说明。
5. 必须严格按照以下 JSON 格式输出，不能有任何其他内容（不要用 Markdown 代码块包裹）：

{
  "diagnosis": "停口原因诊断（1句话，结合具体物理指标和症状分析）",
  "prescriptions": [
    {
      "action": "具体操作指令（如：推漂30cm钓离底）",
      "reason": "原理解释（如：底层缺氧，鱼已上浮）"
    }
  ],
  "references": [
    {
      "master": "大师姓名",
      "title": "参考视频/案例标题",
      "url": "视频URL"
    }
  ],
  "confidence_note": "补充注意事项（如：注意雷阵雨即将到来，安全第一）"
}

若未提供参考秘籍, references 字段输出空数组 []。
"""

def build_user_prompt(
    physical_tags: list,
    symptom_tags: list,
    metrics: dict,
    fish_context: dict,
    user_inventory: dict = None,
    references_block: str = "",
) -> str:
    """构建发给 LLM 的具体鱼情输入。

    references_block: 已格式化的大师秘籍参考文本块, 由 RAG 检索器产出。
    """
    prompt = f"【目标鱼种】: {fish_context.get('target', '未知')}\n"
    prompt += f"【当前钓法】: {fish_context.get('method', '未知')}\n"
    prompt += f"【使用饵料】: {fish_context.get('bait', '未知')}\n"
    prompt += f"【物理环境指标】: {metrics}\n"
    prompt += f"【系统评估物理标签】: {', '.join(physical_tags)}\n"
    prompt += f"【钓友反馈水面症状】: {', '.join(symptom_tags)}\n\n"
    
    if user_inventory:
        prompt += "【用户真实装备库(数字钓箱)】:\n"
        if user_inventory.get('rods'):
            rods_str = ", ".join([f"{r.get('length')}米{r.get('action', '')}" for r in user_inventory['rods']])
            prompt += f"  - 鱼竿: {rods_str}\n"
        if user_inventory.get('mainLines'):
            ml_str = ", ".join([f"{m.get('size')}号" for m in user_inventory['mainLines']])
            prompt += f"  - 主线: {ml_str}\n"
        if user_inventory.get('subLineHooks'):
            sl_str = ", ".join([f"{s.get('hookSize')}号{s.get('hookType')}绑{s.get('lineSize')}子线" for s in user_inventory['subLineHooks']])
            prompt += f"  - 子线双钩: {sl_str}\n"
        if user_inventory.get('floats'):
            fl_str = ", ".join([f"{f.get('name')}(吃铅{f.get('lead')}g)" for f in user_inventory['floats']])
            prompt += f"  - 浮漂: {fl_str}\n"
        prompt += "请注意：在给出战术建议时，必须优先考虑用户现有的上述装备。如果现有装备严重不匹配目标鱼种，请明确指出装备缺陷（断线风险等）并给出补救建议。\n\n"

    if references_block:
        prompt += "【参考大师秘籍 (RAG 召回 Top-K, 与当前鱼情维度匹配度高)】:\n"
        prompt += references_block
        prompt += "\n\n请优先以以上真实大师战术为蓝本设计 prescriptions, 并在 references 中标注引用的大师姓名与视频链接。\n\n"

    prompt += "请根据以上信息，给出战术处方 JSON。"
    return prompt
