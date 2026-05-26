# 后端服务 Wiki

> 范围：仅覆盖后端服务（FastAPI 应用），即 `server.py` / `main.py` / `gunicorn.conf.py` / `migrate_v2.py` / `domain/` / `infrastructure/` / `deploy/`。
> ESP32 固件、微信小程序不在本 Wiki 范围内。

## 目录

| # | 文档 | 内容摘要 |
|---|------|----------|
| 01 | [项目概述](./01-项目概述.md) | 项目定位、后端模块全貌、关键特性 |
| 02 | [快速开始](./02-快速开始.md) | 安装依赖、配置环境、本地启动、测试 |
| 03 | [系统架构](./03-系统架构.md) | 分层设计、请求处理链路、核心数据流 |
| 04 | [API 参考](./04-API参考.md) | 所有 HTTP 接口（系统 / 预测 / 数据 / 钓箱 / V2） |
| 05 | [领域层详解](./05-领域层详解.md) | `domain/` 每个模块的职责、关键函数与调用关系 |
| 06 | [基础设施层](./06-基础设施层.md) | 数据库连接、ORM 模型与表关系 |
| 08 | [部署与运维](./08-部署与运维.md) | Gunicorn、systemd、Nginx 反向代理 |
| 09 | [外部集成与配置](./09-外部集成与配置.md) | 和风天气 / 腾讯 LBS / 通义千问 / 环境变量 |
| 10 | [大师知识库 RAG](./10-大师知识库RAG.md) | 《大师战术与配方百科全书》清洗 · 检索 · 注入救场接口 |

## 后端文件全景

```
diaoyu/
├── server.py                # FastAPI 应用入口（HTTP 路由）
├── main.py                  # 命令行算法演示
├── gunicorn.conf.py         # 生产 Gunicorn 配置
├── migrate_v2.py            # V1→V2 数据库迁移脚本
├── requirements.txt         # 依赖清单
├── 大师战术与配方百科全书.md   # RAG 知识库原始语料
│
├── domain/                  # 领域层（DDD 核心业务）
│   ├── value_objects.py     # 不可变值对象
│   ├── constants.py         # 鱼种 / 阈值 / 时段 / 季节 等所有可调参数
│   ├── services.py          # FishingPredictionService 核心服务
│   ├── engine.py            # 物理变率引擎（供 LLM 消费）
│   ├── analyzers.py         # 时序分析器
│   ├── tags.py              # 战术标签枚举
│   ├── time_utils.py        # 时段 / 季节 / 阶段判定
│   ├── solunar.py           # 月相计算
│   ├── forecast.py          # 逐小时 / 3 天鱼情预报
│   ├── weather.py           # 和风天气 API
│   ├── lbs.py               # 腾讯 LBS 逆地址解析
│   ├── prescription.py      # 通义千问 LLM 处方（集成 RAG）
│   ├── prompts.py           # LLM Prompt 模板
│   ├── master_kb.py         # 大师知识库检索器（RAG）
│   ├── poster.py            # 战报海报数据
│   └── symptom_tags.py      # 主观症状标签
│
├── data/                     # 运行期数据
│   └── master_kb.jsonl       # 清洗后的大师秘籍知识库（322 条）
│
├── scripts/                  # 工具脚本
│   └── build_master_kb.py    # 将百科全书 md 清洗为 JSONL
│
├── infrastructure/          # 基础设施层
│   ├── database.py          # SQLAlchemy 引擎 / Session 工厂
│   └── models.py            # ORM 模型（用户 / 传感器 / 预测 / 会话 / 装备库）
│
│
└── deploy/                  # 生产运维
    ├── fishapp.service      # systemd 单元
    └── nginx-fishapp.conf   # Nginx 反代
```
