# WSL Ubuntu 运行与验证

## 验证结果

2026-10-13，用户在 WSL 2 Ubuntu、Python 3.14.4 中运行测试，连续两次均为 27 passed（2.10 秒与 1.27 秒）。随后确认 Flask 网页启动、扫描保存与详情展示成功。

项目位于 `/mnt/d/ChatGPT/项目/FileScope`，使用挂载的 Windows D 盘。这是本机跨环境验证，不是生产部署，也不代表已经验证所有 Linux 原生文件系统。

## 创建环境与运行

Windows CMD 中运行 `wsl -d Ubuntu`，进入 Linux 后执行：

```bash
cd /mnt/d/ChatGPT/项目/FileScope
python3 -m venv .venv-linux
source .venv-linux/bin/activate
python -m pip install -r requirements.txt -r requirements-dev.txt
python -m pytest -q
python app.py
```

已有 `.venv-linux` 时只需激活，不必重新创建。提示符出现 `(.venv-linux)` 表示激活成功。Windows 的 `.venv` 与 Linux 环境分开使用，两者均不提交 Git。

如果创建环境提示 `ensurepip is not available`，安装与 Python 版本匹配的 venv 包。本次环境使用：

```bash
sudo apt update
sudo apt install python3.14-venv
```

安装后重新创建并激活环境。其他 Python 版本需使用相应的软件包名称。

## 浏览器与数据注意事项

Windows 浏览器打开 http://127.0.0.1:5000/history。先停止 Windows 中的 Flask 服务，避免端口冲突或访问旧服务。Ctrl+C 停止当前 Linux 服务。

输入 `test_data` 创建新的 Linux 扫描记录。旧的 Windows 记录包含 Windows 绝对路径，不用于 Linux 文件隔离操作。两个环境共用当前目录的 SQLite 数据库，不要同时运行文件操作。

只操作测试数据。查看旧报告不会重新扫描；隔离前仍需重新检查文件。服务只监听本机地址，不开放公网访问。
