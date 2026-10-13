"""用受控数据比较全量哈希与大小筛选；不操作业务数据库或真实目录。"""

import argparse
import csv
import hashlib
import json
import platform
import random
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
from src.filescope import calculate_hash, files_equal, file_snapshot, check_file_unchanged

DATA_ROOT = PROJECT_ROOT / 'benchmark_data' / 'size_filter_v1'
OUTPUT_ROOT = PROJECT_ROOT / 'docs' / 'experiments'
SCENARIOS = ('mostly_unique_sizes', 'same_size_different_content', 'many_duplicates')


def definitions(scenario):
    """固定种子保证重跑时生成同一份内容，yield 返回文件名与内容。"""
    rng = random.Random(20261013 + SCENARIOS.index(scenario))
    if scenario == 'mostly_unique_sizes':
        for index in range(54):
            yield f'unique_{index:02}.bin', rng.randbytes(65536 + index)
        for group in range(2):
            content = rng.randbytes(70000 + group)
            for copy in range(3):
                yield f'group_{group:02}_{copy}.bin', content
    elif scenario == 'same_size_different_content':
        for index in range(60):
            yield f'unique_{index:02}.bin', rng.randbytes(65536)
    else:
        for group in range(10):
            content = rng.randbytes(65536 + group)
            for copy in range(6):
                yield f'group_{group:02}_{copy}.bin', content


def prepare_data():
    """复用已生成的数据但必须逐个校验，绝不覆盖已有文件。"""
    if (PROJECT_ROOT / 'benchmark_data').is_symlink() or DATA_ROOT.is_symlink():
        raise ValueError('实验目录不能是符号链接')
    DATA_ROOT.mkdir(parents=True, exist_ok=True)
    manifest = {}
    for scenario in SCENARIOS:
        folder = DATA_ROOT / scenario
        if folder.is_symlink():
            raise ValueError('场景目录不能是符号链接')
        folder.mkdir(exist_ok=True)
        expected_names = set()
        hashes = {}
        for name, content in definitions(scenario):
            path = folder / name
            expected_names.add(name)
            if path.is_symlink():
                raise ValueError(f'不接受符号链接：{path}')
            if path.exists():
                if path.read_bytes() != content:
                    raise ValueError(f'实验文件已改变，不覆盖：{path}')
            else:
                with path.open('xb') as file:
                    file.write(content)
            hashes.setdefault(hashlib.sha256(content).hexdigest(), []).append(name)
        if {p.name for p in folder.iterdir()} != expected_names:
            raise ValueError(f'实验目录有额外文件，不继续：{folder}')
        manifest[scenario] = sorted(sorted(names) for names in hashes.values() if len(names) > 1)
    return manifest


def detect(folder, size_filter):
    """同一检测管线，只改变是否跳过唯一大小；不计生成和结果写盘时间。"""
    start = time.perf_counter()
    paths = sorted(folder.iterdir())
    size_groups = {}
    snapshots = {}
    total_bytes = 0
    for path in paths:
        info = path.stat()
        snapshots[path] = file_snapshot(info)
        total_bytes += info.st_size
        size_groups.setdefault(info.st_size, []).append(path)
    hashes = {}
    hashed_files = 0
    hashed_bytes = 0
    for size, members in size_groups.items():
        if size_filter and len(members) == 1:
            continue
        for path in members:
            check_file_unchanged(path, snapshots[path])
            digest = calculate_hash(path)
            check_file_unchanged(path, snapshots[path])
            hashes.setdefault(digest, []).append(path)
            hashed_files += 1
            hashed_bytes += size
    duplicates = []
    for members in hashes.values():
        if len(members) > 1:
            for path in members[1:]:
                if not files_equal(members[0], path):
                    raise ValueError('哈希候选内容不一致，实验中止')
            duplicates.append(sorted(path.name for path in members))
        for path in members:
            check_file_unchanged(path, snapshots[path])
    groups = sorted(duplicates)
    elapsed = time.perf_counter() - start
    return {'seconds': elapsed, 'file_count': len(paths), 'total_bytes': total_bytes,
            'hashed_files': hashed_files, 'hashed_bytes': hashed_bytes, 'groups': groups}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repeats', type=int, default=7)
    args = parser.parse_args()
    if args.repeats < 3:
        parser.error('至少重复 3 次')
    manifest = prepare_data()
    rows = []
    summaries = []
    for scenario in SCENARIOS:
        folder = DATA_ROOT / scenario
        for enabled in (False, True):
            if detect(folder, enabled)['groups'] != manifest[scenario]:
                raise ValueError(f'预热结果不符合预期：{scenario}')
        for repeat in range(args.repeats):
            order = (False, True) if repeat % 2 == 0 else (True, False)
            for position, enabled in enumerate(order, 1):
                result = detect(folder, enabled)
                if result.pop('groups') != manifest[scenario]:
                    raise ValueError(f'重复成员不符合预期：{scenario}')
                expected_hashed = 6 if enabled and scenario == 'mostly_unique_sizes' else 60
                if result['file_count'] != 60 or result['hashed_files'] != expected_hashed:
                    raise ValueError('文件数或哈希数不符合场景设计')
                rows.append({'scenario': scenario, 'strategy': 'size_filter' if enabled else 'full_hash',
                             'repeat': repeat + 1, 'position': position,
                             'duplicate_groups': len(manifest[scenario]), **result})
        selected = [r for r in rows if r['scenario'] == scenario]
        summary = {'scenario': scenario, 'duplicate_groups': len(manifest[scenario])}
        for strategy in ('full_hash', 'size_filter'):
            measured = [r for r in selected if r['strategy'] == strategy]
            times = [r['seconds'] for r in measured]
            summary[strategy] = {'median_seconds': statistics.median(times),
                                 'min_seconds': min(times), 'max_seconds': max(times),
                                 'hashed_files': measured[0]['hashed_files'],
                                 'hashed_bytes': measured[0]['hashed_bytes']}
        summary['speedup_ratio'] = summary['full_hash']['median_seconds'] / summary['size_filter']['median_seconds']
        summaries.append(summary)
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    stem = OUTPUT_ROOT / f'size-filter-{stamp}'
    environment = {'python': sys.version, 'platform': platform.platform(),
                   'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                   'scanner_sha256': hashlib.sha256((PROJECT_ROOT / 'src/filescope.py').read_bytes()).hexdigest(),
                   'data_root': str(DATA_ROOT), 'repeats': args.repeats, 'time_utc': stamp,
                   'cache': 'warm; generation, verification and warm-up precede timing'}
    with stem.with_suffix('.csv').open('x', newline='', encoding='utf-8') as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    with stem.with_suffix('.json').open('x', encoding='utf-8') as file:
        json.dump({'environment': environment, 'expected_groups': manifest,
                   'summaries': summaries, 'runs': rows}, file, ensure_ascii=False, indent=2)
    lines = ['# 大小筛选实验结果', '', f'UTC 时间：{stamp}',
             f'环境：{platform.platform()}；Python {platform.python_version()}',
             f'每方案每场景 {args.repeats} 次；各 60 文件；预热后交替运行。', '',
             '| 场景 | 数据字节数 | 重复组 | 全量/筛选哈希数 | 全量/筛选中位耗时(ms) | 加速比 |',
             '| --- | ---: | ---: | --- | --- | ---: |']
    for item in summaries:
        full, filtered = item['full_hash'], item['size_filter']
        total = next(r['total_bytes'] for r in rows if r['scenario'] == item['scenario'])
        lines.append(f"| {item['scenario']} | {total} | {item['duplicate_groups']} | "
                     f"{full['hashed_files']} / {filtered['hashed_files']} | "
                     f"{full['median_seconds'] * 1000:.3f} / {filtered['median_seconds'] * 1000:.3f} | "
                     f"{item['speedup_ratio']:.3f} |")
    lines += ['', '全部运行的重复成员与生成预期清单一致。加速比小于 1 表示筛选方案在本次测量中更慢。',
              '结果是本机小规模、热缓存、检测管线对照，不是整个应用或冷磁盘的加速结论。',
              '唯一差异为唯一大小组是否跳过哈希；哈希输入字节数不等于物理磁盘 I/O。',
              '同大小和大量副本场景无法节省哈希，耗时差异可能是系统噪声。',
              '逐次原始数据、最小/最大值、源文件摘要与预期成员见同名 CSV/JSON。',
              '', '重跑：`python scripts/benchmark_size_filter.py --repeats 7`。']
    with stem.with_suffix('.md').open('x', encoding='utf-8') as file:
        file.write('\n'.join(lines) + '\n')
    print('\n'.join(lines))
    print(f'结果文件：{stem}.csv / .json / .md')


if __name__ == '__main__':
    main()
