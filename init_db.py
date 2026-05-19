import os
import sys
from dotenv import load_dotenv

# 确保当前路径在系统路径中，以便能够顺利 import infrastructure
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from infrastructure.database import engine, Base
# 显式导入所有 Model 确保它们在 SQLAlchemy Registry (Metadata) 中全部注册
from infrastructure.models import User, SensorRecord, PredictionHistory, FishingSession, UserRod

def init_database():
    print("====== 🎣 AI 钓鱼智能系统 - 数据库手动初始化脚本 ======")
    load_dotenv()
    db_url = os.getenv("DATABASE_URL")
    print(f"[*] 当前连接字符串: {db_url or 'SQLite 本地兜底模式'}")
    
    try:
        print("[*] 正在向数据库中生成所有的物理表...")
        # create_all 是幂等的，表存在则跳过，不存在则新建，绝不会破坏已有数据！
        Base.metadata.create_all(bind=engine)
        print("[+] 物理表自动生成指令执行完成！")
        
        # 实时检测并列出当前库里真实存在的表，向用户进行确认
        import sqlalchemy as sa
        inspector = sa.inspect(engine)
        tables = inspector.get_table_names()
        print(f"[+] 经实时检测，当前数据库中真实存在的表有: {tables}")
        print("====================================================")
    except Exception as e:
        print(f"[!] 数据库初始化失败！错误信息: {e}")
        print("[!] 请检查 .env 配置文件中的账号密码是否正确，或者 MySQL 服务是否正常运行。")

if __name__ == "__main__":
    init_database()
