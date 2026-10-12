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

def insert_scan_task(connection, target_path, file_count, total_size):
    # 向 scan_tasks 表插入一次扫描任务，并返回新任务的 id
    cursor=connection.execute(

        # SQL字符串开始
        """
        INSERT INTO scan_tasks(
            target_path,
            file_count,
            total_size
        )
        VALUES(?,?,?)
        """, # SQL字符串结束
        (
            str(target_path),
            file_count,
            total_size,
        ),
    )
    return cursor.lastrowid

def insert_files(connection, scan_id, file_records):
    """把一次扫描得到的文件记录批量插入 files 表。"""
    file_rows = []

    for file_record in file_records:
        file_row = (
            scan_id,
            file_record["path"],
            file_record["name"],
            file_record["size"],
            file_record["extension"],
            file_record["modified_time"],
            file_record["hash"],
        )

        file_rows.append(file_row)

    connection.executemany(
        """
        INSERT INTO files (
            scan_id,
            path,
            name,
            size,
            extension,
            modified_time,
            hash
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        file_rows,
    )

    return len(file_rows)


def save_scan_results(target_path, file_count, total_size, file_records):
    """把一次完整的扫描结果保存到数据库。"""
    initialize_database()
    connection = sqlite3.connect(DATABASE_PATH)

    try:
        # 每次建立 SQLite 连接后，都要重新开启外键检查。
        connection.execute("PRAGMA foreign_keys = ON")

        # 先插入扫描任务，取得数据库自动生成的 scan_id。
        scan_id = insert_scan_task(
            connection,
            target_path,
            file_count,
            total_size,
        )

        # 再使用相同的 scan_id，批量插入这次扫描发现的文件。
        inserted_file_count = insert_files(
            connection,
            scan_id,
            file_records,
        )

        # 扫描任务和文件记录都写入成功后，才正式保存。
        connection.commit()

        return scan_id, inserted_file_count

    except Exception:
        # 中途任何一步失败，就撤销本次尚未提交的数据库修改。
        connection.rollback()
        raise

    finally:
        # 无论成功还是失败，最后都关闭数据库连接。
        connection.close()

def get_scan_history():
    # 查询扫描记录
    initialize_database()
    connection=sqlite3.connect(DATABASE_PATH)

    try:
        cursor=connection.execute(
            """

            SELECT
                id,
                target_path,
                scanned_at,
                file_count,
                total_size
            FROM scan_tasks
            ORDER BY id DESC

            """
        )

        scan_history=cursor.fetchall()
        return scan_history

    finally:
        connection.close()


def get_scan_task(scan_id):
    """根据扫描编号查询一条扫描任务。"""
    initialize_database()
    connection = sqlite3.connect(DATABASE_PATH)

    try:
        cursor = connection.execute(
            """
            SELECT
                id,
                target_path,
                scanned_at,
                file_count,
                total_size
            FROM scan_tasks
            WHERE id = ?
            """,
            (scan_id,),
        )

        return cursor.fetchone()

    finally:
        connection.close()


def get_scan_files(scan_id):
    # 查询某一次扫描包含的文件，并按照文件大小从大到小返回
    initialize_database()
    connection=sqlite3.connect(DATABASE_PATH)

    try:
        cursor=connection.execute(
            """
            SELECT
                name,
                path,
                size,
                extension,
                hash
            FROM files
            WHERE scan_id=?
            ORDER BY size DESC

            """,
            (scan_id,), # 是只有一个元素的元组，末尾逗号不能省略。它负责为 SQL 中唯一的 ? 提供值
        )
        file_records = cursor.fetchall()
        return file_records

    finally:
        connection.close()


def get_largest_files(scan_id, limit):
    """查询某次扫描中最大的若干文件。"""
    initialize_database()
    connection = sqlite3.connect(DATABASE_PATH)

    try:
        cursor = connection.execute(
            """
            SELECT
                name,
                path,
                size,
                extension
            FROM files
            WHERE scan_id = ?
            ORDER BY size DESC
            LIMIT ?
            """,
            (scan_id, limit),
        )

        return cursor.fetchall()

    finally:
        connection.close()


def get_file_type_stats(scan_id):
    """按扩展名统计某次扫描的文件数量和总大小。"""
    initialize_database()
    connection = sqlite3.connect(DATABASE_PATH)

    try:
        cursor = connection.execute(
            """
            SELECT
                extension,
                COUNT(*) AS file_count,
                SUM(size) AS total_size
            FROM files
            WHERE scan_id = ?
            GROUP BY extension
            ORDER BY total_size DESC, extension ASC
            """,
            (scan_id,),
        )

        return cursor.fetchall()

    finally:
        connection.close()


def print_scan_history(scan_history):
    """以便于阅读的格式显示扫描历史。"""
    print("Scan history:")

    if not scan_history:
        print("No scan history.")
        return

    for scan in scan_history:
        scan_id, target_path, scanned_at, file_count, total_size = scan

        print(
            f"ID:{scan_id} | "
            f"Path:{target_path} | "
            f"Time:{scanned_at} | "
            f"Files:{file_count} | "
            f"Size:{total_size} bytes"
        )


def print_scan_details(scan_task, file_records):
    """显示一次扫描的概况和文件记录。"""
    if scan_task is None:
        print("Error: scan ID does not exist.")
        return

    scan_id, target_path, scanned_at, file_count, total_size = scan_task

    print(f"Scan ID:{scan_id}")
    print(f"Path:{target_path}")
    print(f"Time:{scanned_at}")
    print(f"Files:{file_count}")
    print(f"Size:{total_size} bytes")
    print("File records:")

    if not file_records:
        print("No file records.")
        return

    for name, path, size, extension, file_hash in file_records:
        hash_text = file_hash if file_hash is not None else "Not calculated"

        print(f"- {name} | {size} bytes | {extension}")
        print(f"  Path:{path}")
        print(f"  SHA-256:{hash_text}")


def print_largest_files(scan_id, file_records):
    """显示某次扫描中最大的文件。"""
    print(f"Largest files in scan {scan_id}:")

    if not file_records:
        print("No file records.")
        return

    for rank, file_record in enumerate(file_records, start=1):
        name, path, size, extension = file_record
        print(f"{rank}. {name} | {size} bytes | {extension}")
        print(f"   Path:{path}")


def print_file_type_stats(scan_id, type_stats):
    """显示某次扫描中各类文件的数量和总大小。"""
    print(f"File type statistics for scan {scan_id}:")

    if not type_stats:
        print("No file records.")
        return

    for extension, file_count, total_size in type_stats:
        # 没有扩展名的文件在数据库中保存为空字符串，这里给它一个易读名称。
        extension_text = extension if extension else "[no extension]"
        print(f"{extension_text} | {file_count} files | {total_size} bytes")


if __name__ == "__main__":
    scan_history = get_scan_history()
    print_scan_history(scan_history)
