"""实验脚本也需要独立核对预期，避免把错误结果写成优化证据。"""

import hashlib

import pytest

from scripts.benchmark_size_filter import definitions, detect, SCENARIOS


@pytest.mark.parametrize('scenario, group_count, filtered_count', [
    (SCENARIOS[0], 2, 6), (SCENARIOS[1], 0, 60), (SCENARIOS[2], 10, 60),
])
def test_benchmark_strategies_match_expected(tmp_path, scenario, group_count, filtered_count):
    expected_hashes = {}
    for name, content in definitions(scenario):
        (tmp_path / name).write_bytes(content)
        expected_hashes.setdefault(hashlib.sha256(content).hexdigest(), []).append(name)
    expected = sorted(sorted(names) for names in expected_hashes.values() if len(names) > 1)
    full = detect(tmp_path, False)
    filtered = detect(tmp_path, True)
    assert full['groups'] == filtered['groups'] == expected
    assert len(expected) == group_count
    assert full['file_count'] == filtered['file_count'] == 60
    assert full['total_bytes'] == filtered['total_bytes']
    assert full['hashed_files'] == 60
    assert filtered['hashed_files'] == filtered_count
