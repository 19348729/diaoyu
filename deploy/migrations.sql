-- =============================================================================
-- AI Fishing Tackle Box - Database SQL Migrations & Schema Definitions
-- =============================================================================

-- -----------------------------------------------------------------------------
-- PART 1: Safe Migration for `users.last_login` (From INT to DATETIME)
-- -----------------------------------------------------------------------------
-- 说明: 线上已通过 python + sqlalchemy 安全升级完毕。
-- 这里的 SQL 脚本用于备份、本地同步或其他环境（如开发/测试环境）的升级。
-- 该方法采用临时字段转换，可 100% 保证已有用户的历史登录时间数据不丢失！

-- 1. 新增一个临时的 DATETIME 类型字段
ALTER TABLE users ADD COLUMN last_login_dt DATETIME DEFAULT NULL;

-- 2. 将旧的 INT 类型 Unix 时间戳转换并填充到临时字段中
UPDATE users SET last_login_dt = FROM_UNIXTIME(last_login) WHERE last_login IS NOT NULL;

-- 3. 安全删除老的 INT 类型字段
ALTER TABLE users DROP COLUMN last_login;

-- 4. 重命名临时字段为 last_login，并设置当前默认时间以及自动更新机制
ALTER TABLE users CHANGE COLUMN last_login_dt last_login DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP;


-- -----------------------------------------------------------------------------
-- PART 2: Schema Definition for `public_rods` (公有鱼竿品牌型号标准库)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `public_rods` (
  `id` INT AUTO_INCREMENT PRIMARY KEY,
  `brand` VARCHAR(32) NOT NULL COMMENT '品牌，如 化氏',
  `series` VARCHAR(64) NOT NULL COMMENT '系列/型号，如 一味EX',
  `action` VARCHAR(32) DEFAULT NULL COMMENT '调性，如 28调',
  `rod_type` VARCHAR(32) DEFAULT '台钓竿' COMMENT '鱼竿种类',
  `length` DOUBLE NOT NULL COMMENT '长度(米)',
  `is_verified` INT DEFAULT 1 COMMENT '是否审核通过可用 (1:已审核, 0:待审)',
  `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
  INDEX `idx_brand` (`brand`),
  INDEX `idx_series` (`series`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='全球公共渔具品牌与型号库';


-- -----------------------------------------------------------------------------
-- PART 3: Schema Definition for `user_baits` (用户钓箱中的个人专属饵料表)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `user_baits` (
  `id` INT AUTO_INCREMENT PRIMARY KEY,
  `openid` VARCHAR(64) NOT NULL COMMENT '所属微信用户openid',
  `category` VARCHAR(32) NOT NULL COMMENT '饵料分类: 商品/自然/状态/小药',
  `brand` VARCHAR(32) NOT NULL COMMENT '品牌',
  `name` VARCHAR(64) NOT NULL COMMENT '饵料名称',
  `flavor` VARCHAR(64) NOT NULL COMMENT '主打味型',
  `target_fish` VARCHAR(64) NOT NULL COMMENT '主攻鱼种',
  `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
  INDEX `idx_openid` (`openid`),
  INDEX `idx_category` (`category`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='用户保存在数字钓箱里的饵料';


-- -----------------------------------------------------------------------------
-- PART 4: 为 fishing_sessions 表新增装备快照字段 (V2 装备闭环)
-- -----------------------------------------------------------------------------
-- 记录本次出钓使用的装备快照，后续可用于:
--   1) 战报展示"本次使用装备"与渔获联动
--   2) 长期沉淀装备表现评分、购置建议、大数据分析
ALTER TABLE fishing_sessions ADD COLUMN equipment_used JSON DEFAULT NULL COMMENT '本次出钓使用的装备快照 {rods, mainLines, subLineHooks, floats, baits}';


-- -----------------------------------------------------------------------------
-- PART 5: Schema Definition for `public_baits` (公共饵料品牌标准库)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `public_baits` (
  `id` INT AUTO_INCREMENT PRIMARY KEY,
  `category` VARCHAR(32) NOT NULL COMMENT '大类: 商品饵/自然饵/状态辅料/小药',
  `brand` VARCHAR(32) NOT NULL COMMENT '品牌',
  `name` VARCHAR(64) NOT NULL COMMENT '饵料名称',
  `flavor` VARCHAR(64) NOT NULL COMMENT '主打味型',
  `target_fish` VARCHAR(64) NOT NULL COMMENT '主攻鱼种',
  `is_verified` INT DEFAULT 1 COMMENT '是否审核通过 (1:已审核, 0:待审)',
  `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
  INDEX `idx_brand` (`brand`),
  INDEX `idx_category` (`category`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='全球公共饵料品牌与型号库';


-- -----------------------------------------------------------------------------
-- PART 6: Seed Data - 公共鱼竿品牌库 (public_rods)
-- -----------------------------------------------------------------------------
-- 来源: domain/rods.py ROD_DATABASE 迁移 (每个长度拆分为独立行)
INSERT INTO `public_rods` (`brand`, `series`, `action`, `rod_type`, `length`, `is_verified`) VALUES
  -- 化氏 一味EX (28调 台钓竿)
  ('化氏', '一味EX', '28调', '台钓竿', 3.6, 1),
  ('化氏', '一味EX', '28调', '台钓竿', 4.5, 1),
  ('化氏', '一味EX', '28调', '台钓竿', 5.4, 1),
  ('化氏', '一味EX', '28调', '台钓竿', 6.3, 1),
  ('化氏', '一味EX', '28调', '台钓竿', 7.2, 1),
  ('化氏', '一味EX', '28调', '台钓竿', 8.1, 1),
  -- 化氏 龙纹鲤 (19调 台钓竿)
  ('化氏', '龙纹鲤', '19调', '台钓竿', 4.5, 1),
  ('化氏', '龙纹鲤', '19调', '台钓竿', 5.4, 1),
  ('化氏', '龙纹鲤', '19调', '台钓竿', 6.3, 1),
  ('化氏', '龙纹鲤', '19调', '台钓竿', 7.2, 1),
  ('化氏', '龙纹鲤', '19调', '台钓竿', 8.1, 1),
  ('化氏', '龙纹鲤', '19调', '台钓竿', 9.0, 1),
  -- 汉鼎 螺纹钢 (19调 台钓竿)
  ('汉鼎', '螺纹钢', '19调', '台钓竿', 4.5, 1),
  ('汉鼎', '螺纹钢', '19调', '台钓竿', 5.4, 1),
  ('汉鼎', '螺纹钢', '19调', '台钓竿', 6.3, 1),
  ('汉鼎', '螺纹钢', '19调', '台钓竿', 7.2, 1),
  ('汉鼎', '螺纹钢', '19调', '台钓竿', 8.1, 1),
  ('汉鼎', '螺纹钢', '19调', '台钓竿', 9.0, 1),
  ('汉鼎', '螺纹钢', '19调', '台钓竿', 10.0, 1),
  -- 汉鼎 汉鼎1号 (37调 台钓竿)
  ('汉鼎', '汉鼎1号', '37调', '台钓竿', 2.7, 1),
  ('汉鼎', '汉鼎1号', '37调', '台钓竿', 3.6, 1),
  ('汉鼎', '汉鼎1号', '37调', '台钓竿', 4.5, 1),
  ('汉鼎', '汉鼎1号', '37调', '台钓竿', 5.4, 1),
  ('汉鼎', '汉鼎1号', '37调', '台钓竿', 6.3, 1),
  ('汉鼎', '汉鼎1号', '37调', '台钓竿', 7.2, 1),
  -- 达亿瓦 波纹鲤 (28调 台钓竿)
  ('达亿瓦', '波纹鲤', '28调', '台钓竿', 3.6, 1),
  ('达亿瓦', '波纹鲤', '28调', '台钓竿', 4.5, 1),
  ('达亿瓦', '波纹鲤', '28调', '台钓竿', 5.4, 1),
  ('达亿瓦', '波纹鲤', '28调', '台钓竿', 6.3, 1),
  ('达亿瓦', '波纹鲤', '28调', '台钓竿', 7.2, 1),
  -- 达亿瓦 一击 (19调 台钓竿)
  ('达亿瓦', '一击', '19调', '台钓竿', 4.5, 1),
  ('达亿瓦', '一击', '19调', '台钓竿', 5.4, 1),
  ('达亿瓦', '一击', '19调', '台钓竿', 6.3, 1),
  ('达亿瓦', '一击', '19调', '台钓竿', 7.2, 1),
  -- 禧玛诺 爽风 (37调 台钓竿)
  ('禧玛诺', '爽风', '37调', '台钓竿', 3.6, 1),
  ('禧玛诺', '爽风', '37调', '台钓竿', 4.5, 1),
  ('禧玛诺', '爽风', '37调', '台钓竿', 5.4, 1),
  ('禧玛诺', '爽风', '37调', '台钓竿', 6.3, 1),
  -- 光威 竹山 (37调 台钓竿)
  ('光威', '竹山', '37调', '台钓竿', 2.7, 1),
  ('光威', '竹山', '37调', '台钓竿', 3.6, 1),
  ('光威', '竹山', '37调', '台钓竿', 4.5, 1),
  ('光威', '竹山', '37调', '台钓竿', 5.4, 1),
  ('光威', '竹山', '37调', '台钓竿', 6.3, 1);


-- -----------------------------------------------------------------------------
-- PART 7: Seed Data - 公共饵料品牌库 (public_baits)
-- -----------------------------------------------------------------------------
-- 来源: domain/baits.py BAIT_DATABASE 迁移 (补全 category 分类字段)
INSERT INTO `public_baits` (`category`, `brand`, `name`, `flavor`, `target_fish`, `is_verified`) VALUES
  -- 老鬼 (Lao Gui)
  ('商品饵', '老鬼', '九一八野战篇', '麸香', '鲫鱼/鲤鱼/草鱼/鳊鱼', 1),
  ('商品饵', '老鬼', '野战蓝鲫', '香腥', '鲫鱼/鲤鱼', 1),
  ('状态辅料', '老鬼', '速攻2号', '奶香/甜香', '鲫鱼/鲢鳙', 1),
  ('商品饵', '老鬼', '螺鲤 (1/2/3号)', '腥/香/酵', '鲤鱼/青鱼', 1),
  -- 化氏 (Hua Shi)
  ('商品饵', '化氏', '大板鲫', '谷物香', '鲫鱼', 1),
  ('商品饵', '化氏', '4号/6号鲫', '浓腥/腥香', '鲫鱼', 1),
  ('状态辅料', '化氏', '赤尾青', '极腥', '罗非鱼/鲫鱼/鲤鱼', 1),
  -- 天元 (Tian Yuan)
  ('商品饵', '天元', '红虫风暴', '浓腥', '鲫鱼/鲤鱼', 1),
  ('商品饵', '天元', '天元大板鲫', '甜香', '鲫鱼', 1),
  ('商品饵', '天元', '浮水鲢鳙(绝杀)', '酸臭/草莓', '鲢鳙', 1),
  -- 南北/广东特色
  ('商品饵', '南北', '南北钓鲮', '腥香', '土鲮/鲮鱼', 1),
  ('状态辅料', '基础料', '纯花生枯', '浓香', '土鲮/草鱼/鲤鱼', 1),
  ('自然饵', '特色', '冷冻活饵(肝/腥)', '腥臭/肝味', '罗非鱼/塘鲺', 1),
  -- 西部风 (Xi Bu Feng)
  ('商品饵', '西部风', '老坛发酵玉米', '酸甜发酵', '草鱼/鲤鱼/青鱼', 1),
  ('小药', '西部风', '牛B鲫', '麝香/甜香', '鲫鱼', 1),
  -- 基础状态饵 & 活饵
  ('自然饵', '基础活饵', '鲜活红虫/蚯蚓', '活体肉腥', '鲫鱼/塘鲺/黄颡鱼', 1),
  ('状态辅料', '状态辅料', '拉丝粉', '无味', '综合', 1),
  ('状态辅料', '状态辅料', '雪花粉', '薯香', '综合', 1);
