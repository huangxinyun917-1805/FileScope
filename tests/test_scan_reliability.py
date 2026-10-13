"""扫描可靠性：真实硬链接、内容确认、读取失败和扫描期间变化。"""

import os

import pytest

import src.filescope as scanner
from src.reports import build_duplicate_report


def report_rows(records):
    return [(r['name'], r['path'], r['size'], r['extension'], r['hash']) for r in records]


def test_three_copies_and_empty_files_are_confirmed(tmp_path):
    for name in ['a.txt', 'b.txt', 'c.txt']:
        (tmp_path / name).write_bytes(b'copy')
    for name in ['empty-a', 'empty-b']:
        (tmp_path / name).write_bytes(b'')
    result = scanner.scan_directory(tmp_path)
    count, size, _, groups, records = result
    assert (count, size) == (5, 12)
    assert sorted(len(paths) for paths in groups.values()) == [2, 3]
    assert scanner.calculate_reclaimable_space(groups, records) == 8
    web_groups, web_space = build_duplicate_report(report_rows(records))
    assert len(web_groups) == 2 and web_space == 8


@pytest.mark.parametrize('with_actual_copy', [False, True])
def test_hardlink_alias_does_not_add_reclaimable_space(tmp_path, with_actual_copy):
    source = tmp_path / 'original.txt'
    source.write_bytes(b'copy')
    try:
        os.link(source, tmp_path / 'alias.txt')
    except OSError as error:
        pytest.skip(f'Hard links unavailable: {error}')
    # 一个硬链接别名和一个真正的副本：只算两个物理文件。
    if with_actual_copy:
        (tmp_path / 'actual-copy.txt').write_bytes(b'copy')
    count, size, _, groups, records = scanner.scan_directory(tmp_path)
    expected_count = 2 if with_actual_copy else 1
    expected_space = 4 if with_actual_copy else 0
    assert (count, size) == (expected_count, expected_count * 4)
    assert scanner.calculate_reclaimable_space(groups, records) == expected_space
    assert build_duplicate_report(report_rows(records))[1] == expected_space


def test_forced_hash_match_does_not_report_different_contents(tmp_path, monkeypatch):
    (tmp_path / 'a').write_bytes(b'ABC')
    (tmp_path / 'b').write_bytes(b'XYZ')
    # 人为让哈希总是相同，确认扫描器没有只凭哈希下结论。
    monkeypatch.setattr(scanner, 'calculate_hash', lambda path: 'forced-match')
    _, _, _, groups, records = scanner.scan_directory(tmp_path)
    assert groups == {}
    assert all(r['hash'] is None for r in records)
    assert build_duplicate_report(report_rows(records)) == ([], 0)


def test_changed_during_hash_is_excluded(tmp_path, monkeypatch):
    (tmp_path / 'a').write_bytes(b'copy')
    (tmp_path / 'b').write_bytes(b'copy')
    original_hash = scanner.calculate_hash

    def hash_then_change(path):
        digest = original_hash(path)
        path.write_bytes(b'changed content')
        return digest

    monkeypatch.setattr(scanner, 'calculate_hash', hash_then_change)
    _, _, _, groups, records = scanner.scan_directory(tmp_path)
    assert groups == {}
    assert all(r['hash'] is None for r in records)


def test_confirmation_read_error_invalidates_group(tmp_path, monkeypatch):
    (tmp_path / 'a').write_bytes(b'copy')
    (tmp_path / 'b').write_bytes(b'copy')

    def fail_comparison(first, second):
        raise PermissionError('File became unreadable')

    monkeypatch.setattr(scanner, 'files_equal', fail_comparison)
    _, _, _, groups, records = scanner.scan_directory(tmp_path)
    assert groups == {}
    assert build_duplicate_report(report_rows(records)) == ([], 0)


def test_files_equal_compares_beyond_first_chunk(tmp_path):
    first, second = tmp_path / 'a', tmp_path / 'b'
    first.write_bytes(b'x' * 8192 + b'A')
    second.write_bytes(b'x' * 8192 + b'B')
    assert scanner.files_equal(first, second) is False
    second.write_bytes(first.read_bytes())
    assert scanner.files_equal(first, second) is True


def test_changed_during_confirmation_invalidates_saved_hashes(tmp_path, monkeypatch):
    (tmp_path / 'a').write_bytes(b'copy')
    (tmp_path / 'b').write_bytes(b'copy')
    original_equal = scanner.files_equal

    def compare_then_change(first, second):
        equal = original_equal(first, second)
        second.write_bytes(b'changed after reading')
        return equal

    monkeypatch.setattr(scanner, 'files_equal', compare_then_change)
    _, _, _, groups, records = scanner.scan_directory(tmp_path)
    assert groups == {}
    assert build_duplicate_report(report_rows(records)) == ([], 0)


def test_different_sizes_do_not_need_hashing(tmp_path, monkeypatch):
    (tmp_path / 'a').write_bytes(b'a')
    (tmp_path / 'b').write_bytes(b'bb')

    def unexpected_hash(path):
        pytest.fail('Unique sizes should not be hashed')

    monkeypatch.setattr(scanner, 'calculate_hash', unexpected_hash)
    _, _, _, groups, records = scanner.scan_directory(tmp_path)
    assert groups == {}
    assert all(r['hash'] is None for r in records)
