from flask import Flask, render_template, abort, request, redirect, url_for, session, flash
import sqlite3
import secrets
from src.database import get_scan_history, get_scan_task, get_scan_files, get_largest_files
from src.reports import build_duplicate_report
from src.services import scan_and_save
from src.quarantine import isolate_file, restore_file, get_quarantine_records

# Flask 应用会在同级 templates 文件夹寻找 HTML 模板。
app = Flask(__name__)
app.secret_key = secrets.token_bytes(32)


@app.context_processor
def operation_token():
    # 文件操作表单必须来自当前浏览器会话。
    if 'operation_token' not in session:
        session['operation_token'] = secrets.token_hex(32)
    return {'operation_token': session['operation_token']}


def check_operation_token():
    expected = session.get('operation_token', '')
    submitted = request.form.get('operation_token', '')
    if not expected or not secrets.compare_digest(expected, submitted):
        abort(400)

# 浏览器访问这些网址时，Flask 调用 history 函数。
@app.route('/')
@app.route('/history')
def history():
    # 查询 SQLite，得到已有扫描记录。
    scan_history = get_scan_history()
    # 把列表传给模板中的 scans 变量，生成 HTML 返回浏览器。
    return render_template('history.html', scans=scan_history)


@app.route('/scan', methods=['POST'])
def start_scan():
    # POST 接收表单提交；路由只负责输入、错误反馈和跳转。
    target_path = request.form.get('target_path', '').strip()
    try:
        result = scan_and_save(target_path)
    except ValueError as error:
        return render_template(
            'history.html', scans=get_scan_history(),
            error=str(error), target_path=target_path,
        ), 400
    except (OSError, sqlite3.Error):
        app.logger.exception('扫描或保存失败')
        return render_template(
            'history.html', scans=get_scan_history(),
            error='扫描或保存失败，请查看终端错误信息。', target_path=target_path,
        ), 500

    # 保存成功后跳转到已有详情页，刷新详情不会再次提交扫描。
    return redirect(url_for('scan_detail', scan_id=result.scan_id), code=303)

@app.route('/api/status') # 浏览器访问http://127.0.0.1:5000/api/status
def status(): # 就调用这个函数，返回python字典；lask自动把它转换成 JSON，返回给浏览器
    return{
        'project':'FileScope',
        'message':'接口连接成功',
    }

@app.route('/scan/<int:scan_id>') # @ 这个网址
def scan_detail(scan_id):
    scan_task=get_scan_task(scan_id)
    if scan_task is None:
        abort(404) # 中止当前请求，并返回指定的 HTTP错误状态
    file_records=get_scan_files(scan_id)
    # 查询一次文件记录，再整理出网页需要的重复组和空间统计。
    duplicate_groups, reclaimable_space = build_duplicate_report(file_records)
    # 查询本次扫描中最大的三个文件，供详情页展示。
    largest_files = get_largest_files(scan_id, 3)

    return render_template(
        'scan_detail.html',
        scan=scan_task,
        files=file_records,
        largest_files=largest_files,
        duplicate_groups=duplicate_groups,
        reclaimable_space=reclaimable_space,
        isolated_paths={r['original_path'] for r in get_quarantine_records()
                        if r['status'] in ('isolated', 'pending')},
    )


@app.route('/scan/<int:scan_id>/isolate', methods=['POST'])
def isolate(scan_id):
    check_operation_token()
    try:
        operation_id = isolate_file(
            scan_id, request.form.get('candidate_path', ''),
            request.form.get('reference_path', ''),
        )
        flash(f'副本已隔离，操作编号 {operation_id}。可在隔离区恢复。')
        return redirect(url_for('quarantine_page'), code=303)
    except (ValueError, OSError, sqlite3.Error) as error:
        flash(f'未完成隔离：{error}')
        return redirect(url_for('scan_detail', scan_id=scan_id), code=303)


@app.route('/quarantine')
def quarantine_page():
    return render_template('quarantine.html', records=get_quarantine_records())


@app.route('/quarantine/<int:operation_id>/restore', methods=['POST'])
def restore(operation_id):
    check_operation_token()
    try:
        restore_file(operation_id)
        flash('文件已恢复到原位置。')
    except (ValueError, OSError, sqlite3.Error) as error:
        flash(f'未完成恢复：{error}')
    return redirect(url_for('quarantine_page'), code=303)


if __name__ == '__main__':
    # 本机访问，Ctrl+C 停止。
    app.run(host='127.0.0.1', port=5000)
