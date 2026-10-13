from pathlib import Path  # 路径处理工具，以后用 Path 表示路径
import hashlib  # 哈希算法库，用于计算文件的哈希值
import sys  # 系统相关库，用于获取命令行参数和退出程序
import os

QUARANTINE_ROOT = Path(__file__).resolve().parent.parent / 'quarantine'


def file_snapshot(info):
    """记录文件身份和属性，用于检测读取期间的变化。"""
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def check_file_unchanged(path, snapshot):
    """路径被替换、内容属性变化或变成符号链接时拒绝确认。"""
    if path.is_symlink() or file_snapshot(path.stat()) != snapshot:
        raise OSError(f"File changed during scan: {path}")


def opened_file_matches(file, snapshot):
    """比较身份、大小与修改时间；Windows 的 stat/fstat ctime 含义可能不同。"""
    return file_snapshot(os.fstat(file.fileno()))[:4] == snapshot[:4]


def files_equal(path_a, path_b):
    """借鉴 fdupes：摘要匹配之后，分块确认实际字节内容。"""
    snapshot_a = file_snapshot(path_a.stat())
    snapshot_b = file_snapshot(path_b.stat())
    equal = True

    with path_a.open('rb') as first, path_b.open('rb') as second:
        # 检查打开的文件是否仍然对应刚才观察到的路径。
        if (not opened_file_matches(first, snapshot_a)
                or not opened_file_matches(second, snapshot_b)):
            raise OSError('File replaced before content comparison')
        while True:
            chunk_a = first.read(8192)
            chunk_b = second.read(8192)
            if chunk_a != chunk_b:
                equal = False
                break
            if not chunk_a:
                break
        if (not opened_file_matches(first, snapshot_a)
                or not opened_file_matches(second, snapshot_b)):
            raise OSError('File changed during content comparison')

    check_file_unchanged(path_a, snapshot_a)
    check_file_unchanged(path_b, snapshot_b)
    return equal


# -------------------- 根据文件内容计算哈希值 --------------------
def calculate_hash(file_path):
    """
    hashlib.sha256() 不会自动读取文件，它只会创建一个 SHA-256 哈希计算器。
    我们需要读取文件内容，再把内容交给它计算。
    """
    hash_object = hashlib.sha256()  # 创建一个空的 SHA-256 哈希计算器
    snapshot = file_snapshot(file_path.stat())

    # rb 表示以二进制方式读取，可以处理文本、图片和视频等不同类型的文件。
    # with 会在代码块结束后自动关闭文件，避免文件一直被程序占用。
    with file_path.open("rb") as file:
        if not opened_file_matches(file, snapshot):
            raise OSError(f"File replaced before hashing: {file_path}")
        while True:
            # chunk 是我们自己定义的变量名，表示读取到的一“块”数据。
            # 每次最多读取 8192 字节，避免大文件一次性占用大量内存。
            chunk = file.read(8192)

            # 如果读到的内容为空，说明已经到达文件末尾，退出循环。
            if not chunk:
                break

            # 把本次读取的内容交给 SHA-256 计算器。
            hash_object.update(chunk)

        if not opened_file_matches(file, snapshot):
            raise OSError(f"File changed during hashing: {file_path}")

    check_file_unchanged(file_path, snapshot)

    # 返回最终的十六进制哈希字符串。
    return hash_object.hexdigest()


# -------------------- 扫描目录并收集数据 --------------------
def scan_directory(target):

    # 结构化记录
    file_records=[]  # 用于存储每个文件的路径、大小、扩展名和哈希值

    """扫描目标目录，返回文件统计信息和哈希分组。"""
    file_count = 0  # 统计文件数量
    total_size = 0  # 统计所有文件的总大小
    extension_count = {}  # 记录“扩展名 -> 文件数量”
    hash_groups = {}  # 记录“哈希值 -> 具有该哈希值的文件路径列表”
    size_groups = {}  # 记录“文件大小 -> 相同大小的文件记录列表”
    snapshots = {}  # 保存首次读取的属性，后续检查是否变化。
    seen_identities = set()  # 设备号和文件编号相同，代表同一物理文件。
    skipped_alias_count = 0

    # rglob("*") 会递归遍历目标目录中的所有文件和子目录。
    for path in target.rglob("*"):
        try:
            # 隔离区中的副本不再参与正常扫描。
            if path.resolve().is_relative_to(QUARANTINE_ROOT.resolve()):
                continue
            # 默认不跟随文件符号链接；rglob 默认也不递归目录符号链接。
            if path.is_symlink():
                skipped_alias_count += 1
                continue
            # 判断当前路径是否为文件，排除文件夹，因为当前版本只处理文件。
            if path.is_file():
                # 先读取并整理当前文件的所有信息。
                # 这一阶段只准备数据，暂时不修改数量、大小等统计结果。
                file_info = path.stat()
                file_size = file_info.st_size
                identity = (file_info.st_dev, file_info.st_ino)
                # 部分文件系统不提供有效 inode，此时不靠它判重。
                if file_info.st_ino and identity in seen_identities:
                    skipped_alias_count += 1
                    continue

                # 获取文件扩展名并转成小写，避免把 .TXT 和 .txt 当成两种类型。
                extension = path.suffix.lower()

                # 整理结构化文件属性记录（字典，键：值）。
                file_record = {
                    "path": str(path.resolve()),  # 文件绝对路径
                    "name": path.name,
                    "size": file_size,
                    "extension": extension,
                    "modified_time": file_info.st_mtime,  # 文件最后修改时间
                    # 第一阶段只读取元数据，暂时还没有计算内容哈希。
                    "hash": None,
                }

                # 上面的读取操作全部成功后，再正式更新统计结果。
                # 这样发生异常的文件不会留下不完整的统计数据。
                file_count += 1
                total_size += file_size

                # 如果扩展名已经出现过，数量加一；否则第一次创建记录。
                if extension in extension_count:
                    extension_count[extension] += 1
                else:
                    extension_count[extension] = 1

                # 如果这个文件大小第一次出现，先创建一个空列表。
                if file_size not in size_groups:
                    size_groups[file_size] = []

                # 将当前文件记录加入对应的大小分组。
                size_groups[file_size].append(file_record)
                file_records.append(file_record)  # 将文件记录添加到列表中
                snapshots[file_record['path']] = file_snapshot(file_info)
                if file_info.st_ino:
                    seen_identities.add(identity)

                print(path)
        
        except (PermissionError, OSError) as error:
            print(f"Skipped: {path}")
            print(f"Reason: {error}")
            continue

    # 第二阶段：只有相同大小的候选文件才需要读取内容并计算哈希。
    hashed_file_count = 0

    for file_size, records in size_groups.items():
        # 这个大小只有一个文件时，它不可能与其他文件内容完全相同。
        if len(records) <= 1:
            continue

        for file_record in records:
            path = Path(file_record["path"])

            try:
                check_file_unchanged(path, snapshots[file_record['path']])
                file_hash = calculate_hash(path)
                check_file_unchanged(path, snapshots[file_record['path']])
            except (PermissionError, OSError) as error:
                # 元数据已经读取成功，所以保留记录；但不参与重复文件判断。
                print(f"Hash skipped: {path}")
                print(f"Reason: {error}")
                continue

            hashed_file_count += 1
            file_record["hash"] = file_hash

            # 如果这个哈希值第一次出现，先创建一个空的路径列表。
            if file_hash not in hash_groups:
                hash_groups[file_hash] = []

            # 把当前文件加入对应的哈希分组。
            hash_groups[file_hash].append(path)

    # 第三阶段：哈希仅是候选条件，实际内容相同且属性稳定才保留分组。
    # 如果一个组确认失败，保守地撤销整组摘要，防止数据库再把它误分组。
    for file_hash, paths in list(hash_groups.items()):
        try:
            if len(paths) > 1:
                for path in paths[1:]:
                    if not files_equal(paths[0], path):
                        raise OSError('Hash matched but file contents differ')
            for path in paths:
                check_file_unchanged(path, snapshots[str(path)])
        except OSError as error:
            print(f"Confirmation skipped: {error}")
            del hash_groups[file_hash]
            for record in file_records:
                if record['hash'] == file_hash:
                    record['hash'] = None

    # 只显示包含两个或更多文件的大小候选组。
    print("Same-size candidate groups:")
    for file_size, records in size_groups.items():
        if len(records) > 1:
            print(f" - {file_size} bytes: {len(records)} files")

    print(f"Hashed files:{hashed_file_count}")
    print(f"Skipped link aliases:{skipped_alias_count}")

    return file_count, total_size, extension_count, hash_groups, file_records


# -------------------- 显示扫描报告 --------------------
def calculate_reclaimable_space(hash_groups, file_records):
    """计算重复文件理论上可以释放的空间。"""
    # 建立“哈希值 -> 文件大小”的对应关系。
    # 同一个哈希分组中的文件内容相同，因此大小也相同，只需记录一次大小。
    size_by_hash = {}
    for file_record in file_records:
        file_hash = file_record["hash"]
        if file_hash is not None:
            size_by_hash[file_hash] = file_record["size"]

    reclaimable_space = 0

    for file_hash, paths in hash_groups.items():
        if len(paths) > 1:
            # 每组保留一个文件，其余文件都视为可以删除的重复副本。
            extra_copy_count = len(paths) - 1
            file_size = size_by_hash[file_hash]
            reclaimable_space += file_size * extra_copy_count

    return reclaimable_space


def print_report(file_count, total_size, extension_count, hash_groups, file_records):
    """显示文件扫描结果和重复文件报告。"""
    print(f"Total files:{file_count}")  # 输出文件总数
    print(f"Total size:{total_size} bytes")  # 输出文件总大小

    print("File types:")

    # .items() 可以同时取出字典中的键和值，也就是扩展名和对应数量。
    for extension, count in extension_count.items():
        print(f"{extension}:{count}")

    print("Duplicate files:")
    duplicate_group_count = 0  # 统计重复文件组数

    # 逐个取出哈希值，以及这个哈希值对应的文件路径列表。
    for file_hash, paths in hash_groups.items():
        # 列表中有两个或更多路径，说明这些文件的内容相同。
        if len(paths) > 1:
            duplicate_group_count += 1
            print(f"Group {duplicate_group_count}:")  # 输出重复组编号

            for path in paths:
                print(f" - {path}")  # 输出当前重复组中的文件路径

    print(f"Duplicate groups: {duplicate_group_count}")

    reclaimable_space = calculate_reclaimable_space(hash_groups, file_records)
    print(f"Reclaimable space:{reclaimable_space} bytes")


# -------------------- 程序主流程 --------------------
def main():
    """设置扫描目标，并组织程序的执行流程。"""

    # 如果用户输入 history，就查询历史，不进行目录扫描。
    if len(sys.argv)>1 and sys.argv[1] == "history":
        from database import get_scan_history, print_scan_history

        scan_history=get_scan_history()
        print_scan_history(scan_history)
        return

    # show 后面需要一个扫描编号，例如：python src\filescope.py show 2
    if len(sys.argv) > 1 and sys.argv[1] == "show":
        if len(sys.argv) < 3:
            print("Usage: python src\\filescope.py show <scan_id>")
            return

        try:
            scan_id = int(sys.argv[2])
        except ValueError:
            print(f"Error: scan ID must be an integer: {sys.argv[2]}")
            return

        if scan_id <= 0:
            print("Error: scan ID must be greater than 0.")
            return

        from database import get_scan_files, get_scan_task, print_scan_details

        scan_task = get_scan_task(scan_id)
        file_records = get_scan_files(scan_id) if scan_task is not None else []
        print_scan_details(scan_task, file_records)
        return

    # largest 后面需要扫描编号，可选填写返回数量，默认显示 10 个文件。
    if len(sys.argv) > 1 and sys.argv[1] == "largest":
        if len(sys.argv) < 3:
            print("Usage: python src\\filescope.py largest <scan_id> [limit]")
            return

        try:
            scan_id = int(sys.argv[2])
            limit = int(sys.argv[3]) if len(sys.argv) > 3 else 10
        except ValueError:
            print("Error: scan ID and limit must be integers.")
            return

        if scan_id <= 0 or limit <= 0:
            print("Error: scan ID and limit must be greater than 0.")
            return

        from database import get_largest_files, get_scan_task, print_largest_files

        scan_task = get_scan_task(scan_id)
        if scan_task is None:
            print("Error: scan ID does not exist.")
            return

        largest_files = get_largest_files(scan_id, limit)
        print_largest_files(scan_id, largest_files)
        return

    # types 后面需要一个扫描编号，例如：python src\filescope.py types 2
    if len(sys.argv) > 1 and sys.argv[1] == "types":
        if len(sys.argv) < 3:
            print("Usage: python src\\filescope.py types <scan_id>")
            return

        try:
            scan_id = int(sys.argv[2])
        except ValueError:
            print(f"Error: scan ID must be an integer: {sys.argv[2]}")
            return

        if scan_id <= 0:
            print("Error: scan ID must be greater than 0.")
            return

        from database import get_file_type_stats, get_scan_task, print_file_type_stats

        scan_task = get_scan_task(scan_id)
        if scan_task is None:
            print("Error: scan ID does not exist.")
            return

        type_stats = get_file_type_stats(scan_id)
        print_file_type_stats(scan_id, type_stats)
        return

    # duplicate-dirs 统计某次扫描中重复文件来自哪些目录。
    if len(sys.argv) > 1 and sys.argv[1] == "duplicate-dirs":
        if len(sys.argv) < 3:
            print("Usage: python src\\filescope.py duplicate-dirs <scan_id>")
            return

        try:
            scan_id = int(sys.argv[2])
        except ValueError:
            print(f"Error: scan ID must be an integer: {sys.argv[2]}")
            return

        if scan_id <= 0:
            print("Error: scan ID must be greater than 0.")
            return

        from database import (
            count_duplicate_directories,
            get_duplicate_files,
            get_scan_task,
            print_duplicate_directories,
        )

        scan_task = get_scan_task(scan_id)
        if scan_task is None:
            print("Error: scan ID does not exist.")
            return

        duplicate_files = get_duplicate_files(scan_id)
        directory_counts = count_duplicate_directories(duplicate_files)
        print_duplicate_directories(scan_id, directory_counts)
        return

    # sys.argv[0] 是程序路径，sys.argv[1] 是用户提供的第一个参数。
    if len(sys.argv) > 1: # Python 用来接收终端命令后面附加内容的列表
        target = Path(sys.argv[1])  # 从命令行参数获取扫描目标
    else:
        target = Path("test_data")
    
    # 如果路径不存在，显示提示并结束 main()。
    if not target.exists():
        print(f"Error: path does not exist: {target}")
        return

    # 如果路径存在但不是文件夹，也不能进行目录扫描。
    if not target.is_dir():
        print(f"Error: path is not a directory: {target}")
        return

    # CLI 与 Flask 共用扫描保存服务，各自负责展示。
    # database.py 与当前文件都在 src 文件夹中；服务负责调用数据库。
    if __package__:
        from .services import scan_and_save
    else:
        from services import scan_and_save

    result = scan_and_save(target)

    print_report(
        result.file_count,
        result.total_size,
        result.extension_count,
        result.hash_groups,
        result.file_records
    )
    print(f"Records collected:{len(result.file_records)}")
    print(f"Saved scan ID:{result.scan_id}")
    print(f"Saved file records:{result.inserted_file_count}")


# 只有直接运行 filescope.py 时才调用 main()，从这里启动程序。
if __name__ == "__main__":
    main()
