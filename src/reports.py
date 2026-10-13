"""把数据库查询结果整理成报告数据；不查询数据库，也不修改文件。"""


def build_duplicate_report(file_records):
    """按已有哈希记录生成重复组及理论可释放空间。"""
    hash_groups = {}

    for name, path, size, extension, file_hash in file_records:
        # 未计算出哈希的记录不能用来判断重复。
        if file_hash is None:
            continue

        # 同哈希、同大小的文件放进同一组。
        key = (file_hash, size)
        if key not in hash_groups:
            hash_groups[key] = []
        hash_groups[key].append({"name": name, "path": path, "size": size})

    duplicate_groups = []
    reclaimable_space = 0

    for (file_hash, size), members in hash_groups.items():
        if len(members) <= 1:
            continue

        # 假设每组保留一份，其余为副本；这里只估算，不执行清理。
        group_space = size * (len(members) - 1)
        duplicate_groups.append({
            "members": members,
            "size": size,
            "reclaimable_space": group_space,
        })
        reclaimable_space += group_space

    return duplicate_groups, reclaimable_space
