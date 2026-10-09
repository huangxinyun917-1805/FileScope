from pathlib import Path  # 路径处理工具，以后用 Path 表示路径
import hashlib  # 哈希算法库，用于计算文件的哈希值


# -------------------- 根据文件内容计算哈希值 --------------------
def calculate_hash(file_path):
    """
    hashlib.sha256() 不会自动读取文件，它只会创建一个 SHA-256 哈希计算器。
    我们需要读取文件内容，再把内容交给它计算。
    """
    hash_object = hashlib.sha256()  # 创建一个空的 SHA-256 哈希计算器

    # rb 表示以二进制方式读取，可以处理文本、图片和视频等不同类型的文件。
    # with 会在代码块结束后自动关闭文件，避免文件一直被程序占用。
    with file_path.open("rb") as file:
        while True:
            # chunk 是我们自己定义的变量名，表示读取到的一“块”数据。
            # 每次最多读取 8192 字节，避免大文件一次性占用大量内存。
            chunk = file.read(8192)

            # 如果读到的内容为空，说明已经到达文件末尾，退出循环。
            if not chunk:
                break

            # 把本次读取的内容交给 SHA-256 计算器。
            hash_object.update(chunk)

    # 返回最终的十六进制哈希字符串。
    return hash_object.hexdigest()


# -------------------- 扫描目录并收集数据 --------------------
def scan_directory(target):
    """扫描目标目录，返回文件统计信息和哈希分组。"""
    file_count = 0  # 统计文件数量
    total_size = 0  # 统计所有文件的总大小
    extension_count = {}  # 记录“扩展名 -> 文件数量”
    hash_groups = {}  # 记录“哈希值 -> 具有该哈希值的文件路径列表”

    # rglob("*") 会递归遍历目标目录中的所有文件和子目录。
    for path in target.rglob("*"):
        # 判断当前路径是否为文件，排除文件夹，因为当前版本只处理文件。
        if path.is_file():
            file_count += 1
            total_size += path.stat().st_size  # st_size 表示文件大小，单位是字节
            print(path)

            # 获取文件扩展名并转成小写，避免把 .TXT 和 .txt 当成两种类型。
            extension = path.suffix.lower()

            # 如果扩展名已经出现过，数量加一；否则第一次创建记录。
            if extension in extension_count:
                extension_count[extension] += 1
            else:
                extension_count[extension] = 1

            # 扫描当前文件时，同时计算它的内容哈希值。
            file_hash = calculate_hash(path)

            # 如果这个哈希值第一次出现，先创建一个空的路径列表。
            if file_hash not in hash_groups:
                hash_groups[file_hash] = []

            # 把当前文件加入对应的哈希分组。
            hash_groups[file_hash].append(path)

    # 把扫描得到的四项数据返回给 main()。
    return file_count, total_size, extension_count, hash_groups


# -------------------- 显示扫描报告 --------------------
def print_report(file_count, total_size, extension_count, hash_groups):
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


# -------------------- 程序主流程 --------------------
def main():
    """设置扫描目标，并组织程序的执行流程。"""
    target = Path("test_data")  # 表示当前项目目录下的 test_data 文件夹

    # scan_directory() 返回四项结果，左侧四个变量按照相同顺序分别接收。
    file_count, total_size, extension_count, hash_groups = scan_directory(target)

    # 把扫描结果交给报告函数显示。
    print_report(
        file_count,
        total_size,
        extension_count,
        hash_groups,
    )


# 只有直接运行 filescope.py 时才调用 main()，从这里启动程序。
if __name__ == "__main__":
    main()
