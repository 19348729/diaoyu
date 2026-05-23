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
