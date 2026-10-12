from flask import Flask, render_template
from src.database import get_scan_history

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

@app.route('/api/status') # 浏览器访问http://127.0.0.1:5000/api/status
def status(): # 就调用这个函数，返回python字典；lask自动把它转换成 JSON，返回给浏览器
    return{
        'project':'FileScope',
        'message':'接口连接成功',
    }

if __name__ == '__main__':
    # 本机访问，Ctrl+C 停止。
    app.run(host='127.0.0.1', port=5000)
