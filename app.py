from flask import Flask, render_template, abort, request, redirect, url_for
import sqlite3
from src.database import get_scan_history, get_scan_task, get_scan_files
from src.reports import build_duplicate_report
from src.services import scan_and_save

# Flask 应用会在同级 templates 文件夹寻找 HTML 模板。
app = Flask(__name__)

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
    return render_template(
        'scan_detail.html',
        scan=scan_task,
        files=file_records,
        duplicate_groups=duplicate_groups,
        reclaimable_space=reclaimable_space,
    )


if __name__ == '__main__':
    # 本机访问，Ctrl+C 停止。
    app.run(host='127.0.0.1', port=5000)
