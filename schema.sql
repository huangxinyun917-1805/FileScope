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