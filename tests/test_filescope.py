from src.filescope import calculate_hash, calculate_reclaimable_space


def test_same_content_has_same_hash(tmp_path):
    """内容相同的文件应得到相同的哈希值。"""
    file_a = tmp_path / "a.txt" # pytest临时目录
    file_b = tmp_path / "b.txt"

    file_a.write_text("same content", encoding="utf-8")
    file_b.write_text("same content", encoding="utf-8")

    assert calculate_hash(file_a) == calculate_hash(file_b)
    # assert表示结果必须满足这个条件


def test_different_content_has_different_hash(tmp_path):
    """内容不同的文件应得到不同的哈希值。"""
    file_a = tmp_path / "a.txt"
    file_b = tmp_path / "b.txt"

    file_a.write_text("AAA", encoding="utf-8")
    file_b.write_text("BBB", encoding="utf-8")

    assert calculate_hash(file_a) != calculate_hash(file_b)


def test_calculate_reclaimable_space():
    """三个相同的10字节文件保留一个，应释放20字节。"""
    hash_groups = {
        "same_hash": ["a.txt", "b.txt", "c.txt"],
        "unique_hash": ["unique.txt"],
    }

    file_records = [
        {"hash": "same_hash", "size": 10},
        {"hash": "same_hash", "size": 10},
        {"hash": "same_hash", "size": 10},
        {"hash": "unique_hash", "size": 8},
    ]

    assert calculate_reclaimable_space(hash_groups, file_records) == 20