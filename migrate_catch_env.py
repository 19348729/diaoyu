"""
迁移脚本：渔获环境字段 + 预测反馈表
====================================
对应改动：
  - catch_logs 新增列：t_air / humidity / wind_desc
  - 新增表：prediction_feedback

特性：
  - 幂等：可重复执行，已存在的表/列自动跳过
  - DB 无关：自动适配 SQLite(本地) 与 MySQL(生产)，走 SQLAlchemy 引擎
  - 不破坏数据：只做 CREATE TABLE(缺失时) 与 ADD COLUMN(缺失时)
  - 纯 ASCII 输出，避免不同服务器/控制台编码问题

用法（项目根目录，需能读到 .env 的 DATABASE_URL）：
    python migrate_catch_env.py
"""
import sys

# 尽量让中文输出走 UTF-8（Windows GBK 控制台兜底）
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from sqlalchemy import inspect, text

# 必须导入所有模型，确保注册到 Base.metadata（create_all 才能建新表）
from infrastructure.database import engine, Base
from infrastructure.models import (
    User, SensorRecord, PredictionHistory, FishingSession,
    UserRod, PublicRod, UserMainLine, UserSubLineHook,
    UserFloat, UserBait, PublicBait, CatchLog, PredictionFeedback,
)

# catch_logs 需要补的列： 列名 -> SQL 类型（SQLite/MySQL 通用）
CATCH_LOG_NEW_COLUMNS = {
    "t_air": "FLOAT",
    "humidity": "FLOAT",
    "wind_desc": "VARCHAR(64)",
}


def main():
    print("=" * 56)
    print("  migrate: catch_logs env columns + prediction_feedback")
    print(f"  dialect: {engine.dialect.name}")
    print("=" * 56)

    # 1. create_all：自动创建缺失的新表（prediction_feedback；
    #    若 catch_logs 尚不存在，会直接按最新 schema 建好，后面加列即成空操作）
    print("\n[1/2] create_all (sync missing tables) ...")
    try:
        Base.metadata.create_all(bind=engine)
        print("  [OK] tables synced")
    except Exception as e:
        print(f"  [ERR] create_all failed: {e}")
        sys.exit(1)

    # 2. 给已存在的 catch_logs 补列（create_all 不会给旧表加列）
    print("\n[2/2] ensure catch_logs columns ...")
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    if "catch_logs" not in tables:
        print("  [i] catch_logs not found (fresh deploy) -> created by create_all with latest schema, no ALTER needed.")
    else:
        existing = {c["name"] for c in inspector.get_columns("catch_logs")}
        added = 0
        for col, col_type in CATCH_LOG_NEW_COLUMNS.items():
            if col in existing:
                print(f"  [SKIP] column exists: catch_logs.{col}")
                continue
            ddl = f"ALTER TABLE catch_logs ADD COLUMN {col} {col_type}"
            try:
                with engine.begin() as conn:
                    conn.execute(text(ddl))
                print(f"  [ADD]  catch_logs.{col} ({col_type})")
                added += 1
            except Exception as e:
                msg = str(e).lower()
                if "duplicate" in msg or "exists" in msg:
                    print(f"  [SKIP] column exists: catch_logs.{col}")
                else:
                    print(f"  [WARN] add catch_logs.{col} failed: {e}")
        print(f"  done, {added} column(s) added this run.")

    # 3. 验证
    print("\n[verify] current schema:")
    inspector = inspect(engine)
    tabs = inspector.get_table_names()
    print(f"  prediction_feedback table: {'present' if 'prediction_feedback' in tabs else 'MISSING'}")
    if "catch_logs" in tabs:
        cols = {c["name"] for c in inspector.get_columns("catch_logs")}
        have = [c for c in CATCH_LOG_NEW_COLUMNS if c in cols]
        miss = [c for c in CATCH_LOG_NEW_COLUMNS if c not in cols]
        print(f"  catch_logs new columns present: {have}")
        if miss:
            print(f"  catch_logs still MISSING: {miss}")

    print("\n[done] migration finished. You can (re)start the service.")


if __name__ == "__main__":
    main()
