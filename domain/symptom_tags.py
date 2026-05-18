from enum import Enum

class SymptomTag(str, Enum):
    """主观症状标签枚举。
    用于用户在 AI 救场（第二次握手）时勾选的水面状况。
    """
    SYM_BUBBLES_NO_BITE = "有地星跑泡但不咬钩"
    SYM_SMALL_FISH_INTERCEPT = "杂鱼截口严重"
    SYM_NO_ACTIVITY = "完全无口无鱼星"
    SYM_FLOAT_DRIFT = "浮漂频繁走水"
    SYM_FISH_JUMP = "看到鱼跳但不吃饵"
    SYM_SUDDEN_STOP = "原本连杆突然停口"
    SYM_WEAK_BITE = "鱼口极轻，有动作打不到"
    SYM_FISH_UP = "鱼层明显上浮"
