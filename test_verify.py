import sys
import os

# 确保能正常导入 domain 里的模块
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

# 处理 Windows 控制台中文和字符集编码问题
if sys.stdout.encoding != 'utf-8':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from domain.verification import RodVerificationService

def run_test():
    print("==================================================")
    print(" [TEST] 开始在本地执行自定义鱼竿大模型核验测试...")
    
    # 1. 检查环境变量配置
    api_key = os.getenv("DASHSCOPE_API_KEY")
    print(f" [*] 当前读取到的 DASHSCOPE_API_KEY: {api_key}")
    
    if not api_key or api_key == "your_dashscope_key_here":
        print(" [!] 警告: 检测到当前使用的是占位符或未配置 API Key，系统将执行本地 Mock 兜底校验逻辑！")
    else:
        print(" [+] 成功读取到有效 API Key，系统将真实发起大模型联网核验请求...")

    # 2. 执行核验逻辑
    service = RodVerificationService()
    
    print("\n [*] 正在核验对象 —— 品牌: '光威', 型号/系列: '剑手鲤' ...")
    res = service.verify_brand_and_series("光威", "剑手鲤")
    
    print("\n [RESULT] 最终核验输出结果:")
    print(res)
    print("==================================================")

if __name__ == "__main__":
    run_test()
