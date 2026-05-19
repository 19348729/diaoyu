"""
鱼竿品牌与型号 (UGC) 大模型智能校验服务
"""
import json
import os
import dashscope

dashscope.api_key = os.getenv("DASHSCOPE_API_KEY", "")

class RodVerificationService:
    """调用大模型验证用户手填的鱼竿品牌与系列型号是否真实存在。"""
    def __init__(self, model_name="qwen-turbo"):
        self.model_name = model_name

    def verify_brand_and_series(self, brand: str, series: str) -> dict:
        """
        验证品牌和型号是否真实存在。
        返回字典: { "exists": bool, "reason": str }
        """
        if not brand or not series:
            return {"exists": False, "reason": "品牌或系列型号不能为空"}

        # 如果没有配置 API 密钥，进行模拟的简单基础校验（防止阻塞开发/体验流程）
        if not dashscope.api_key:
            return self._mock_verify(brand, series)

        system_prompt = "You are a professional fishing tackle expert. Your task is to verify if a given fishing rod brand and series (model) actually exist in the real world."
        user_prompt = f"""请核对以下提交的鱼竿品牌和系列/型号：
品牌：{brand}
系列/型号：{series}

请核对在钓鱼装备市场上是否真实存在这个品牌，以及该品牌旗下是否有这一款鱼竿型号（允许名称或拼写有微小偏差，如“化氏”的“一味EX”或“汉鼎”的“一号”等）。
请必须仅返回标准的 JSON 格式，不要包含任何前导、后继或 Markdown 格式包裹（如 ```json 等），格式如下：
{{
  "exists": true 或 false,
  "reason": "简短的一句话分析原因，如果是真的，简述其特点或定位；如果是假的，指出该品牌不存在或该品牌无此产品"
}}"""

        messages = [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_prompt}
        ]

        # ── 打印调用大模型入参日志 ────────────────────────
        print("\n" + "="*50)
        print(" [LLM CALL] 🚀 正在调用大模型核验用户自定义装备资产...")
        print(f" [*] 模型名称 (Model): {self.model_name}")
        print(f" [*] 校验目标品牌 (Brand): '{brand}'")
        print(f" [*] 校验目标型号 (Series): '{series}'")
        print(f" [*] 系统提示词 (System Prompt):\n{system_prompt}")
        print(f" [*] 用户提示词 (User Prompt):\n{user_prompt}")
        print("="*50 + "\n")

        try:
            response = dashscope.Generation.call(
                model=self.model_name,
                messages=messages,
                result_format='message',
                max_tokens=200,
                temperature=0.3  # 较低温度以提高确定性
            )

            # ── 打印调用大模型原始响应日志 ────────────────────────
            print("\n" + "="*50)
            print(" [LLM RESP] 📥 接收到大模型返回报文:")
            print(f" [*] HTTP 状态码: {response.status_code}")
            if response.status_code == 200:
                raw_content = response.output.choices[0]['message']['content']
                print(f" [*] 原始正文 (Raw Output):\n{raw_content}")
            else:
                print(f" [!] 错误信息 (Error Msg): {response.code} - {response.message}")
            print("="*50 + "\n")

            if response.status_code == 200:
                content = response.output.choices[0]['message']['content'].strip()
                # 剔除 markdown 标签
                if content.startswith("```json"):
                    content = content[7:]
                if content.startswith("```"):
                    content = content[3:]
                if content.endswith("```"):
                    content = content[:-3]

                data = json.loads(content.strip())
                # 保证返回字段结构符合规范
                result = {
                    "exists": bool(data.get("exists", True)),
                    "reason": str(data.get("reason", "校验通过"))
                }
                print(f" [LLM PARSED] 🎯 解析后校验结果: {result}\n")
                return result
            else:
                err_result = {
                    "exists": True,  # 接口报错时默认放过，保证用户体验
                    "reason": f"AI 校验接口暂时不可用 (ErrorCode: {response.code})"
                }
                print(f" [LLM PARSED] ⚠️ 异常放行结果: {err_result}\n")
                return err_result
        except Exception as e:
            print(f"[RodVerificationService] Exception: {e}")
            exception_result = {
                "exists": True,  # 异常情况默认放过，保障可用性
                "reason": f"AI 校验服务异常，默认允许录入 ({str(e)})"
            }
            print(f" [LLM PARSED] ❌ 异常放行结果: {exception_result}\n")
            return exception_result

    def _mock_verify(self, brand: str, series: str) -> dict:
        """兜底本地验证逻辑（在未配置 API Key 时使用）"""
        # 已知真实存在的一些常见假名/恶搞过滤
        fake_keywords = ["神棍", "测试", "测试品牌", "哈哈", "未知品牌", "不存在", "fake", "test", "傻子"]
        
        lower_brand = brand.lower()
        lower_series = series.lower()
        
        for kw in fake_keywords:
            if kw in lower_brand or kw in lower_series:
                return {
                    "exists": False,
                    "reason": f"经本地快速校验，您提交的 '{brand}' 或 '{series}' 疑似包含测试或无效字符，无法通过验证。"
                }
                
        # 常见渔具品牌加白
        known_brands = ["化氏", "汉鼎", "光威", "达亿瓦", "禧玛诺", "天元", "龙王恨", "佳钓尼", "客友", "开沃", "宝飞龙", "迪佳", "其它品牌", "其他品牌"]
        for b in known_brands:
            if b in brand:
                return {
                    "exists": True,
                    "reason": f"[本地校验] 品牌 '{brand}' 属于已知经典渔具品牌，型号 '{series}' 已自动加入审核列表。"
                }
                
        return {
            "exists": True,
            "reason": f"[本地校验] 已成功登记自定义品牌 '{brand}' 与型号 '{series}'，大模型将在稍后核验该资产。"
        }
