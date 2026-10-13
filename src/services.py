"""CLI 与网页共用的业务流程，连接扫描逻辑和数据库。"""

from dataclasses import dataclass
from pathlib import Path


@dataclass
class ScanResult:
    """把一次扫描的结果与数据库生成的编号一起返回。"""

    scan_id: int
    inserted_file_count: int
    file_count: int
    total_size: int
    extension_count: dict
    hash_groups: dict
    file_records: list


def scan_and_save(target_path):
    """校验目录、调用已有扫描器、保存结果；不生成网页。"""
    # 同时支持 python app.py 和 python src/filescope.py 两种入口。
    if __package__:
        from .database import PROJECT_ROOT, save_scan_results
        from .filescope import scan_directory
    else:
        from database import PROJECT_ROOT, save_scan_results
        from filescope import scan_directory

    if not str(target_path).strip():
        raise ValueError("请输入扫描目录。")

    target = Path(target_path) # target 是我们自己起名的变量，不是 Python函数。它保存“这次要扫描的目录”。
    # 相对路径统一相对于项目根目录，不受启动位置影响。
    if not target.is_absolute():
        target = PROJECT_ROOT / target
    target = target.resolve()

    if not target.exists():
        raise ValueError(f"目录不存在：{target}")
    if not target.is_dir():
        raise ValueError(f"请选择目录而不是文件：{target}")

    # 核心数据流：目录 → 扫描记录 → 数据库 → 新扫描编号。
    file_count, total_size, extension_count, hash_groups, file_records = scan_directory(target)
    scan_id, inserted_file_count = save_scan_results(
        target, file_count, total_size, file_records,
    )

    return ScanResult(
        scan_id, inserted_file_count, file_count, total_size,
        extension_count, hash_groups, file_records,
    )
