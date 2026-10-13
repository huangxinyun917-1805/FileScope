"""验证网页扫描闭环；使用临时目录和数据库，不写用户的扫描历史。"""

import pytest

import src.database as database
from app import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(database, 'DATABASE_PATH', tmp_path / 'test.db')
    monkeypatch.setitem(app.config, 'TESTING', True)
    return app.test_client()


def test_scan_saves_and_redirects_to_detail(client, tmp_path):
    target = tmp_path / 'sample'
    target.mkdir()
    (target / 'first.txt').write_bytes(b'same')
    (target / 'copy.txt').write_bytes(b'same')
    (target / 'unique.txt').write_bytes(b'only this file')

    response = client.post('/scan', data={'target_path': str(target)})
    assert response.status_code == 303
    assert response.headers['Location'] == '/scan/1'

    task = database.get_scan_task(1)
    assert task[1] == str(target.resolve())
    assert task[3:] == (3, 22)
    assert len(database.get_scan_files(1)) == 3

    detail = client.get(response.headers['Location'])
    html = detail.get_data(as_text=True)
    assert detail.status_code == 200
    assert 'first.txt' in html and 'copy.txt' in html and 'unique.txt' in html
    assert '理论可释放空间 4 字节' in html
    # 刷新详情只是 GET，不重复创建扫描任务。
    client.get(response.headers['Location'])
    assert len(database.get_scan_history()) == 1


@pytest.mark.parametrize('kind', ['empty', 'missing', 'file'])
def test_invalid_directory_does_not_create_scan(client, tmp_path, kind):
    target = tmp_path / 'not-a-directory.txt'
    if kind == 'file':
        target.write_text('example', encoding='utf-8')
    value = '' if kind == 'empty' else str(target)

    response = client.post('/scan', data={'target_path': value})
    assert response.status_code == 400
    assert 'role="alert"' in response.get_data(as_text=True)
    assert database.get_scan_history() == []
