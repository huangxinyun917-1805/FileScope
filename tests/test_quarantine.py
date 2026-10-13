"""文件操作闭环与失败补偿，所有文件和数据库都位于临时目录。"""

from pathlib import Path
import sqlite3

import pytest

import src.database as database
import src.filescope as scanner
import src.quarantine as quarantine
from src.reports import build_duplicate_report
from src.services import scan_and_save
from app import app


@pytest.fixture
def sample(tmp_path, monkeypatch):
    monkeypatch.setattr(database, 'DATABASE_PATH', tmp_path / 'operations.db')
    monkeypatch.setattr(quarantine, 'QUARANTINE_ROOT', tmp_path / 'quarantine')
    monkeypatch.setattr(scanner, 'QUARANTINE_ROOT', tmp_path / 'quarantine')
    target = tmp_path / 'documents'
    target.mkdir()
    (target / 'a.txt').write_bytes(b'same contents')
    (target / 'b.txt').write_bytes(b'same contents')
    result = scan_and_save(target)
    groups, _ = build_duplicate_report(database.get_scan_files(result.scan_id))
    reference, candidate = (Path(m['path']) for m in groups[0]['members'])
    return result.scan_id, reference, candidate


def test_isolate_and_restore_preserve_contents(sample):
    scan_id, reference, candidate = sample
    operation_id = quarantine.isolate_file(scan_id, str(candidate), str(reference))
    row = quarantine.get_quarantine_records()[0]
    isolated = Path(row['quarantine_path'])
    assert row['status'] == 'isolated'
    assert reference.read_bytes() == isolated.read_bytes() == b'same contents'
    assert not candidate.exists()
    quarantine.restore_file(operation_id)
    assert candidate.read_bytes() == reference.read_bytes()
    assert not isolated.exists()
    assert quarantine.get_quarantine_records()[0]['status'] == 'restored'


def test_reference_cannot_be_submitted_as_candidate(sample):
    scan_id, reference, candidate = sample
    with pytest.raises(ValueError):
        quarantine.isolate_file(scan_id, str(reference), str(candidate))
    assert reference.exists() and candidate.exists()
    assert quarantine.get_quarantine_records() == []


def test_changed_candidate_is_rejected(sample):
    scan_id, reference, candidate = sample
    candidate.write_bytes(b'changed')
    with pytest.raises(ValueError):
        quarantine.isolate_file(scan_id, str(candidate), str(reference))
    assert candidate.read_bytes() == b'changed'
    assert reference.read_bytes() == b'same contents'


def test_restore_conflict_does_not_overwrite(sample):
    scan_id, reference, candidate = sample
    operation_id = quarantine.isolate_file(scan_id, str(candidate), str(reference))
    candidate.write_bytes(b'new file at original path')
    with pytest.raises(ValueError):
        quarantine.restore_file(operation_id)
    assert candidate.read_bytes() == b'new file at original path'
    row = quarantine.get_quarantine_records()[0]
    assert row['status'] == 'isolated'
    assert Path(row['quarantine_path']).read_bytes() == b'same contents'


def install_failure_trigger(status):
    connection = sqlite3.connect(database.DATABASE_PATH)
    try:
        connection.execute(f"""CREATE TRIGGER fail_update BEFORE UPDATE ON quarantine_records
            WHEN NEW.status = '{status}' BEGIN SELECT RAISE(ABORT, 'simulated database failure'); END""")
        connection.commit()
    finally:
        connection.close()


def test_database_failure_compensates_isolation(sample):
    scan_id, reference, candidate = sample
    install_failure_trigger('isolated')
    with pytest.raises(sqlite3.Error):
        quarantine.isolate_file(scan_id, str(candidate), str(reference))
    row = quarantine.get_quarantine_records()[0]
    assert candidate.read_bytes() == reference.read_bytes()
    assert row['status'] == 'failed'
    assert not Path(row['quarantine_path']).exists()


def test_database_failure_compensates_restore(sample):
    scan_id, reference, candidate = sample
    operation_id = quarantine.isolate_file(scan_id, str(candidate), str(reference))
    install_failure_trigger('restored')
    with pytest.raises(sqlite3.Error):
        quarantine.restore_file(operation_id)
    row = quarantine.get_quarantine_records()[0]
    assert row['status'] == 'isolated'
    assert Path(row['quarantine_path']).read_bytes() == reference.read_bytes()
    assert not candidate.exists()


def test_quarantine_directory_is_excluded(sample):
    scan_id, reference, candidate = sample
    quarantine.isolate_file(scan_id, str(candidate), str(reference))
    # 根目录还包含临时数据库，因此只检查隔离文件不在返回记录中。
    _, _, _, _, records = scanner.scan_directory(reference.parent.parent)
    assert all(not Path(r['path']).is_relative_to(quarantine.QUARANTINE_ROOT)
               for r in records)


def test_web_operation_requires_token_and_runs_round_trip(sample):
    scan_id, reference, candidate = sample
    app.config['TESTING'] = True
    client = app.test_client()
    submitted = {'candidate_path': str(candidate), 'reference_path': str(reference)}
    assert client.post(f'/scan/{scan_id}/isolate', data=submitted).status_code == 400
    assert candidate.exists()
    client.get(f'/scan/{scan_id}')
    with client.session_transaction() as session:
        submitted['operation_token'] = session['operation_token']
    response = client.post(f'/scan/{scan_id}/isolate', data=submitted)
    assert response.status_code == 303 and response.headers['Location'] == '/quarantine'
    assert not candidate.exists()
    row = quarantine.get_quarantine_records()[0]
    restore = client.post(f"/quarantine/{row['id']}/restore", data=submitted)
    assert restore.status_code == 303
    assert candidate.read_bytes() == reference.read_bytes()


def test_same_file_cannot_be_isolated_twice(sample):
    scan_id, reference, candidate = sample
    quarantine.isolate_file(scan_id, str(candidate), str(reference))
    with pytest.raises(ValueError):
        quarantine.isolate_file(scan_id, str(candidate), str(reference))
    assert len(quarantine.get_quarantine_records()) == 1
    assert reference.exists()


def test_changed_reference_is_rejected(sample):
    scan_id, reference, candidate = sample
    reference.write_bytes(b'changed reference')
    with pytest.raises(ValueError):
        quarantine.isolate_file(scan_id, str(candidate), str(reference))
    assert candidate.read_bytes() == b'same contents'


def test_cross_device_failure_keeps_original(sample, monkeypatch):
    scan_id, reference, candidate = sample

    def unsupported_link(*args, **kwargs):
        raise OSError('Cross-device link unavailable')

    monkeypatch.setattr(quarantine.os, 'link', unsupported_link)
    with pytest.raises(OSError):
        quarantine.isolate_file(scan_id, str(candidate), str(reference))
    assert candidate.read_bytes() == reference.read_bytes()
    assert quarantine.get_quarantine_records()[0]['status'] == 'failed'
