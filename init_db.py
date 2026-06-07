import os
import sys
from dotenv import load_dotenv

# 确保当前路径在系统路径中，以便能够顺利 import infrastructure
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from infrastructure.database import engine, Base
# 显式导入所有 Model 确保它们在 SQLAlchemy Registry (Metadata) 中全部注册
from infrastructure.models import User, SensorRecord, PredictionHistory, FishingSession, UserRod, CatchLog, PredictionFeedback

def init_database():
    print("====== AI Diaoyu System - Database Initialization Script ======")
    load_dotenv()
    db_url = os.getenv("DATABASE_URL")
    print(f"[*] 当前连接字符串: {db_url or 'SQLite 本地兜底模式'}")
    
    try:
        print("[*] 正在向数据库中生成所有的物理表...")
        # 临时开启 SQL 打印日志，让用户能直观看到底层执行的 CREATE TABLE 物理 SQL 语句
        engine.echo = True
        # create_all 是幂等的，表存在则跳过，不存在则新建，绝不会破坏已有数据！
        Base.metadata.create_all(bind=engine)
        # 关闭 SQL 打印
        engine.echo = False
        print("[+] Physical table creation commands completed successfully!")
        
        # 实时检测并列出当前库里真实存在的表，向用户进行确认
        import sqlalchemy as sa
        inspector = sa.inspect(engine)
        tables = inspector.get_table_names()
        print(f"[+] Detected tables in database: {tables}")
        print("====================================================")
    except Exception as e:
        print(f"[!] Database initialization failed! Error: {e}")
        print("[!] Please check if .env is configured correctly and database is running.")

if __name__ == "__main__":
    init_database()
