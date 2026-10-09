from pathlib import Path # 路径处理工具，以后用Path表示路径
import hashlib # 哈希算法库，用于计算文件的哈希值

# --------------关键功能块：根据文件内容检测重复文件--------------

def calculate_hash(file_path):
    """
    hashlib.sha256() 不会自动读取文件，它只会创建一个“SHA-256 哈希计算器”。我们需要把文件内容交给它，它才会计算。
    """
    hash_object = hashlib.sha256() # 创建一个SHA-256哈希对象

    # rb：二进制模式读取文件，防止编码问题影响读取，所以文本、图片、视频等都可以
    with file_path.open("rb") as file: # 打开文件（with语句会自动关闭文件，避免资源泄漏，是一种安全写法）
        while True:
            chunk = file.read(8192) # 每次只读取8192字节，避免大文件一次性占用大量内存；chunk：变量名，“块”
            if not chunk: # 如果读取到文件末尾，跳出循环
                break
            hash_object.update(chunk) # 更新哈希对象

    return hash_object.hexdigest() # 返回最终的十六进制哈希字符串

# -------------------------------------------------------------

target=Path("test_data") # 创建路径对象，表示当前目录下的test_data文件夹
file_count=0 # 统计文件数
total_size=0 # 统计文件总大小
extension_count={} # 统计文件扩展名数量

hash_groups={} # 创建一个用于存储哈希值和对应文件路径的字典，键是哈希值，值是文件路径列表

# 遍历文件夹
for path in target.rglob("*"): # rglob表示递归遍历，*表示所有文件
    if path.is_file(): # 判断是否是文件(排除文件夹，因为本轮不管文件夹)
        file_count += 1

        total_size += path.stat().st_size
        print(path) 

        extension=path.suffix.lower() # 获取文件扩展名，并转换为小写(避免大小写不一致导致统计错误
        if extension in extension_count:
            extension_count[extension] += 1
        else:
            extension_count[extension] = 1

        file_hash=calculate_hash(path) # 递归问件时，同步计算文件哈希值
        if file_hash not in hash_groups:
            hash_groups[file_hash] = [] # 如果哈希值不存在，创建一个空列表
        hash_groups[file_hash].append(path)

print(f"Total files:{file_count}") # 输出文件总数
print(f"Total size:{total_size} bytes") # 输出文件总大小

print("File types:")
for extension, count in extension_count.items(): # .items()：同时取出字典中的扩展名和数量
    print(f"{extension}:{count}")

print("Duplicate files:")
duplicate_group_count=0 # 统计重复文件组数
# 遍历哈希分组
for file_hash, paths in hash_groups.items():
    if len(paths) > 1: # 如果哈希值对应的文件路径列表长度大于1，说明有重复文件
        duplicate_group_count += 1
        print(f"Group {duplicate_group_count}:") # 输出组号
        for path in paths:
            print(f" - {path}") # 输出重复文件路径
print(f"Duplicate groups: {duplicate_group_count}")
