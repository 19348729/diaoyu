import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from dotenv import load_dotenv

# 加载项目根目录的 .env 文件（如果存在）
load_dotenv()

# 从环境变量获取数据库连接字符串
# 例如在 .env 文件中配置：
# DATABASE_URL=mysql+pymysql://root:123456@127.0.0.1:3306/diaoyu_db?charset=utf8mb4
SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL")

if not SQLALCHEMY_DATABASE_URL:
    # 如果没有配置 MySQL，默认退回到原来的 SQLite 本地文件
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    DB_PATH = os.path.join(BASE_DIR, "diaoyu.db")
    SQLALCHEMY_DATABASE_URL = f"sqlite:///{DB_PATH}"

# 判断是否是 SQLite
is_sqlite = SQLALCHEMY_DATABASE_URL.startswith("sqlite")

if is_sqlite:
    # check_same_thread=False 是 SQLite 在 FastAPI (多线程异步环境) 必须的配置
    engine = create_engine(
        SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
    )
else:
    # MySQL 引擎配置 (增加连接池等优化)
    engine = create_engine(
        SQLALCHEMY_DATABASE_URL,
        pool_size=10,        # 连接池大小
        max_overflow=20,     # 最大超量连接
        pool_recycle=3600    # 定期回收连接，防止被数据库主动断开 (MySQL 默认 8小时)
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
