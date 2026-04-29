import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# 数据库文件路径 (使用绝对路径或相对路径)
# 这里默认在项目根目录下生成 diaoyu.db 文件
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "diaoyu.db")

SQLALCHEMY_DATABASE_URL = f"sqlite:///{DB_PATH}"

# 初始化引擎
# check_same_thread=False 是 SQLite 在 FastAPI (多线程异步环境) 必须的配置
engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)

# 创建会话工厂
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 创建基类，用于后续定义所有 ORM 模型
Base = declarative_base()

# 依赖注入，用于 FastAPI 获取数据库 Session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
