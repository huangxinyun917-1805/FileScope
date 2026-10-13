# FileScope

FileScope 是一个本地文件扫描、重复文件检测与存储分析平台。

## 第一版目标

- 扫描指定目录
- 读取文件路径、大小、扩展名和修改时间
- 检测内容完全相同的文件
- 生成重复文件报告
- 不修改或删除任何文件

## 安全原则

第一版只读扫描。

所有开发和测试只使用 test_data，不使用真实重要文件。

## 本地网页运行

在项目根目录的 CMD 中：

```cmd
.venv\Scripts\activate
python -m pip install -r requirements.txt
python app.py
```

浏览器打开 http://127.0.0.1:5000/history，输入 `test_data`，点击“扫描并保存”。
扫描成功后自动打开本次详情，历史列表中新增记录。相对路径以项目根目录为起点。
当前同步执行扫描，等待完成后再进行下一次提交。Ctrl+C 停止服务；修改代码后需保存并重启。

## 代码调用关系

```text
CLI / Flask路由
    → services.scan_and_save（目录校验、组织扫描保存）
    → filescope.scan_directory（文件扫描与哈希）
    → database.save_scan_results（SQLite事务保存）
    → 扫描编号返回入口
    → reports / HTML模板（展示结果）
```

参考 dupeGuru 的核心与展示分离思路，逐步把已有逻辑接入服务层。
保留现有按大小筛选及SHA-256；fdupes的内容确认、链接策略与操作前变化检查待后续实现。
SQLite历史、统计、Flask网页为本项目扩展。当前报告基于扫描快照，仅供查看，尚未提供文件隔离或删除操作。
