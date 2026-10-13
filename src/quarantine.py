"""单文件隔离与恢复；参考保留对象/候选副本模型，操作前重新确认内容。"""

import os
from pathlib import Path
import sqlite3
import stat
from uuid import uuid4

from . import database
from .filescope import calculate_hash, check_file_unchanged, file_snapshot, files_equal
from .reports import build_duplicate_report


QUARANTINE_ROOT = database.PROJECT_ROOT / 'quarantine'


def connect_operations():
    database.initialize_database()
    connection = sqlite3.connect(database.DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute('PRAGMA foreign_keys = ON')
    return connection


def get_quarantine_records():
    connection = connect_operations()
    try:
        return [dict(row) for row in connection.execute(
            'SELECT * FROM quarantine_records ORDER BY id DESC'
        ).fetchall()]
    finally:
        connection.close()


def move_without_overwrite(source, destination):
    """同文件系统内用链接再解除原路径，目标存在时由系统拒绝覆盖。"""
    # os.link 不复制内容，必须支持硬链接；跨文件系统时失败并保留原文件。
    before = source.lstat()
    if not stat.S_ISREG(before.st_mode):
        raise ValueError('只能移动普通文件。')
    os.link(source, destination, follow_symlinks=False)
    try:
        # 创建链接会改变 ctime，因此这里比较身份、大小与修改时间。
        if (file_snapshot(destination.stat())[:4] != file_snapshot(before)[:4]
                or file_snapshot(source.lstat())[:4] != file_snapshot(before)[:4]):
            raise OSError('移动期间源文件发生变化。')
        source.unlink()
    except OSError:
        # 原文件无法移走时，撤销刚建立的目标路径。
        destination.unlink()
        raise


def verify_candidate(scan_id, candidate_path, reference_path):
    records = database.get_scan_files(scan_id)
    groups, _ = build_duplicate_report(records)
    # 服务器也检查角色，不能通过修改表单把保留文件当成副本。
    group = next((g for g in groups
                  if g['members'][0]['path'] == reference_path
                  and any(m['path'] == candidate_path for m in g['members'][1:])), None)
    if group is None:
        raise ValueError('选择无效：只能隔离该组保留文件以外的候选副本。')

    source, reference = Path(candidate_path), Path(reference_path)
    stored = {row[1]: row for row in records}
    attributes_connection = connect_operations()
    try:
        modified_times = dict(attributes_connection.execute(
            'SELECT path, modified_time FROM files WHERE scan_id=?', (scan_id,),
        ).fetchall())
    finally:
        attributes_connection.close()
    snapshots = {}
    for path in (source, reference):
        if path.is_symlink() or not path.is_file():
            raise ValueError('文件不存在或已变成链接，请重新扫描。')
        if path.resolve().is_relative_to(QUARANTINE_ROOT.resolve()):
            raise ValueError('隔离区中的文件不能再次隔离。')
        info = path.stat()
        row = stored[str(path)]
        if info.st_nlink > 1:
            raise ValueError('文件有硬链接别名，暂不执行隔离。')
        if info.st_size != row[2] or info.st_mtime != modified_times[str(path)]:
            raise ValueError('文件属性已变化，请重新扫描。')
        snapshots[str(path)] = file_snapshot(info)
        if calculate_hash(path) != group_hash(records, candidate_path):
            raise ValueError('文件内容已变化，请重新扫描。')

    if os.path.samefile(source, reference) or not files_equal(source, reference):
        raise ValueError('副本与保留文件不是两个内容相同的独立文件。')
    for path in (source, reference):
        check_file_unchanged(path, snapshots[str(path)])
    return source, reference, snapshots, group_hash(records, candidate_path)


def group_hash(records, candidate_path):
    return next(row[4] for row in records if row[1] == candidate_path)


def isolate_file(scan_id, candidate_path, reference_path):
    connection = connect_operations()
    operation_id = None
    destination = QUARANTINE_ROOT / (uuid4().hex + '.file')
    moved = False
    try:
        # 串行化本应用的文件操作，防止两个请求同时处理同一副本。
        connection.execute('BEGIN IMMEDIATE')
        source, reference, snapshots, digest = verify_candidate(
            scan_id, candidate_path, reference_path,
        )
        QUARANTINE_ROOT.mkdir(parents=True, exist_ok=True)
        if QUARANTINE_ROOT.is_symlink():
            raise ValueError('隔离区不能是符号链接。')
        cursor = connection.execute(
            '''INSERT INTO quarantine_records
               (scan_id, original_path, quarantine_path, reference_path, hash, status)
               VALUES (?, ?, ?, ?, ?, 'pending')''',
            (scan_id, str(source), str(destination), str(reference), digest),
        )
        operation_id = cursor.lastrowid
        # 先保存意图，异常退出后仍有恢复位置记录。
        connection.commit()
        connection.execute('BEGIN IMMEDIATE')
        check_file_unchanged(source, snapshots[str(source)])
        check_file_unchanged(reference, snapshots[str(reference)])
        move_without_overwrite(source, destination)
        moved = True
        if calculate_hash(destination) != digest or not files_equal(destination, reference):
            raise ValueError('移动期间内容发生变化，撤销隔离。')
        check_file_unchanged(reference, snapshots[str(reference)])
        connection.execute(
            "UPDATE quarantine_records SET status='isolated', error=NULL WHERE id=?",
            (operation_id,),
        )
        connection.commit()
        return operation_id
    except Exception as error:
        connection.rollback()
        # SQLite 回滚不会恢复磁盘文件，所以显式补偿移动。
        compensation_error = None
        if moved:
            try:
                move_without_overwrite(destination, Path(candidate_path))
            except (OSError, ValueError) as recovery_error:
                compensation_error = str(recovery_error)
        if operation_id is not None:
            try:
                connection.execute(
                    'UPDATE quarantine_records SET status=?, error=? WHERE id=?',
                    ('pending' if compensation_error or destination.exists() else 'failed',
                     str(error) + (f'; 补偿失败：{compensation_error}' if compensation_error else ''),
                     operation_id),
                )
                connection.commit()
            except sqlite3.Error:
                connection.rollback()  # 已提交的 pending 仍保留定位信息。
        raise
    finally:
        connection.close()


def restore_file(operation_id):
    connection = connect_operations()
    moved = False
    try:
        connection.execute('BEGIN IMMEDIATE')
        row = connection.execute(
            'SELECT * FROM quarantine_records WHERE id=?', (operation_id,),
        ).fetchone()
        if row is None or row['status'] not in ('isolated', 'pending'):
            raise ValueError('记录不存在或已经恢复。')
        source, destination = Path(row['quarantine_path']), Path(row['original_path'])
        if source.parent.resolve() != QUARANTINE_ROOT.resolve() or source.is_symlink():
            raise ValueError('隔离路径无效。')
        if os.path.lexists(destination):
            raise ValueError('原位置已存在文件或链接，拒绝覆盖。')
        if not destination.parent.is_dir():
            raise ValueError('原目录不存在，请先恢复目录。')
        if calculate_hash(source) != row['hash']:
            raise ValueError('隔离文件内容已变化，拒绝恢复。')
        move_without_overwrite(source, destination)
        moved = True
        if calculate_hash(destination) != row['hash']:
            raise ValueError('恢复期间内容发生变化，撤销恢复。')
        connection.execute(
            "UPDATE quarantine_records SET status='restored', restored_at=CURRENT_TIMESTAMP, error=NULL WHERE id=?",
            (operation_id,),
        )
        connection.commit()
    except Exception as error:
        connection.rollback()
        compensation_message = ''
        if moved:
            try:
                move_without_overwrite(destination, source)
            except (OSError, ValueError) as recovery_error:
                compensation_message = f'; 补偿失败，请核对已记录的两个路径：{recovery_error}'
        try:
            connection.execute(
                "UPDATE quarantine_records SET error=?, status=CASE WHEN ? THEN 'pending' ELSE status END WHERE id=?",
                (str(error) + compensation_message, bool(compensation_message), operation_id),
            )
            connection.commit()
        except sqlite3.Error:
            connection.rollback()
        raise
    finally:
        connection.close()
