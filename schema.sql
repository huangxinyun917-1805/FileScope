PRAGMA foreign_keys = ON;
-- 让SQLite检查外键关系 --
-- PRAGMA 是 SQLite 用来调整数据库运行设置的命令 --
-- foreign_keys = ON 表示开启外键约束 --

CREATE TABLE IF NOT EXISTS scan_tasks(
    id INTEGER PRIMARY KEY AUTOINCREMENT, -- AUTOINCREMENT：插入新记录时自动生成递增编号 --
    target_path TEXT NOT NULL,
    scanned_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, -- 如果插入记录时没有提供时间，SQLite 自动填写当前时间 --
    file_count INTEGER NOT NULL CHECK(file_count>=0), -- 限定条件 --
    total_size INTEGER NOT NULL CHECK(total_size>=0)
);

-- 文件操作独立于历史快照：保存隔离位置、状态和错误，便于恢复。
CREATE TABLE IF NOT EXISTS quarantine_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_id INTEGER NOT NULL REFERENCES scan_tasks(id),
    original_path TEXT NOT NULL,
    quarantine_path TEXT NOT NULL UNIQUE,
    reference_path TEXT NOT NULL,
    hash TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('pending', 'isolated', 'restored', 'failed')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    restored_at TEXT,
    error TEXT
);

CREATE TABLE IF NOT EXISTS files(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_id INTEGER NOT NULL, -- 第几次扫描的编号 --
    path TEXT NOT NULL,
    name TEXT NOT NULL,
    size INTEGER NOT NULL CHECK(size>=0),
    extension TEXT NOT NULL,
    modified_time REAL NOT NULL,
    hash TEXT,

    -- 定义两张表之间的外键关系 --
    FOREIGN KEY (scan_id) REFERENCES scan_tasks(id) ON DELETE CASCADE,
    -- 在同一“次”扫描结果中，把同一个路径重复保存两遍 --
    UNIQUE (scan_id, path)

);
