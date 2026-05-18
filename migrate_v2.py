import sqlite3
import os
import sys

# 1. 首先确保我们在项目根目录
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "diaoyu.db")

print(f"正在检查数据库: {DB_PATH}")

if not os.path.exists(DB_PATH):
    print("数据库文件不存在，系统会在启动时自动创建完整的新表结构。")
else:
    print("找到现有数据库，开始执行 V2.0 字段升级...")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 尝试为 sensor_records 增加 t_water 列
    try:
        cursor.execute("ALTER TABLE sensor_records ADD COLUMN t_water FLOAT")
        print("✅ 成功添加列: sensor_records.t_water")
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e).lower():
            print("ℹ️ 列已存在: sensor_records.t_water")
        else:
            print(f"⚠️ 添加 t_water 时遇到异常: {e}")

    # 尝试为 sensor_records 增加 t_air 列
    try:
        cursor.execute("ALTER TABLE sensor_records ADD COLUMN t_air FLOAT")
        print("✅ 成功添加列: sensor_records.t_air")
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e).lower():
            print("ℹ️ 列已存在: sensor_records.t_air")
        else:
            print(f"⚠️ 添加 t_air 时遇到异常: {e}")

    conn.commit()
    conn.close()
    print("V2.0 字段升级完毕！")

# 2. 调用 SQLAlchemy 的 create_all 生成新表 (如 fishing_sessions)
print("\n开始扫描并创建缺失的新表结构...")
try:
    from infrastructure.database import engine, Base
    # 必须导入所有模型文件，确保注册到 Base.metadata
    from infrastructure.models import User, SensorRecord, PredictionHistory, FishingSession
    
    Base.metadata.create_all(bind=engine)
    print("✅ 缺失的新表创建/同步成功！")
except ImportError as e:
    print(f"❌ 导入模型失败，请确保您在项目根目录下执行此脚本。错误: {e}")
except Exception as e:
    print(f"❌ 创建新表时遇到异常: {e}")

print("\n🎉 V2.0 数据库处理流程结束，您可以正常启动服务了！")
