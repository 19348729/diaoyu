"""
战报海报数据生成器
"""
class PosterGenerator:
    def __init__(self):
        pass
        
    def generate_poster_data(self, session: dict) -> dict:
        """
        根据会话的汇总数据生成海报所需要的 JSON 参数
        session 应包含 duration_min, catch_level, delta_p 等字段
        """
        catch_level = session.get("catch_level", "空军")
        delta_p = session.get("delta_p", 0.0)
        
        if catch_level == "爆护":
            percentile = 99
            catch_desc = "无敌连竿爆护"
            bg_color = "red"
        elif catch_level == "稳赚":
            percentile = 85
            catch_desc = "稳稳拿捏"
            bg_color = "orange"
        elif catch_level == "惨淡":
            percentile = 30
            catch_desc = "几条小鱼"
            bg_color = "gray"
        else:
            percentile = 5
            catch_desc = "坚强空军"
            bg_color = "dark"
            
        trend_desc = f"迎战气压骤降 {delta_p}hPa" if delta_p < -1.0 else f"借助气压平稳 {delta_p}hPa"
        
        return {
            "title": "战况海报",
            "bg_color": bg_color,
            "text_lines": [
                f"今日出钓 {session.get('duration_min', 0)} 分钟",
                trend_desc,
                f"AI助攻战绩：{catch_desc}！",
                f"击败了全网 {percentile}% 的钓友"
            ],
            "percentile": percentile,
            "catch_desc": catch_desc
        }
