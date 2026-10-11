'''
    初始化数据库的结构

    打开或创建 filescope.db
        ↓
    读取 schema.sql
        ↓
    创建 scan_tasks 表
        ↓
    创建 files 表
        ↓
    提交修改并关闭连接

'''


from pathlib import Path
import sqlite3 # SQLite接口

PROJECT_ROOT=Path(__file__).resolve().parent.parent
# __file__ 是 Python 自动提供的变量，表示当前代码文件的位置
# Path(__file__) 把这个路径转换成方便处理的 Path 对象
# .resolve() 把路径转换成完整的绝对路径
# .parent.parent 上一级的上一级

SCHEMA_PATH = PROJECT_ROOT / "schema.sql"
DATABASE_PATH = PROJECT_ROOT / "filescope.db"

def initialize_database():
    # 调用SQLite接口
    connection = sqlite3.connect(DATABASE_PATH)

    try:
        # 每次建立 SQLite 连接后，都要开启外键检查。
        # Python 把 SQL 字符串交给 SQLite
        connection.execute("PRAGMA foreign_keys = ON")

        # 读取SQL文件
        schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")

        # 一次执行多条SQL语句（因为schema.sql这个文件中不只一条命令）
        connection.executescript(schema_sql)

        # 确认并保存本次数据库修改
        connection.commit()

    finally:
        # 无论成功还是失败，最后都关闭数据库连接
        connection.close()

if __name__=="__main__":
    initialize_database()
    print(f"Database initialized: {DATABASE_PATH}")



