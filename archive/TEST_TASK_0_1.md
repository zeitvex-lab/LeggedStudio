# Electron 与资产后端验收

## 自动化检查

要求 Python 3.12.x 和 Node.js 20+。从工作区根目录执行：

```powershell
python -m unittest discover -s legged_studio\backend -p "test_*.py" -v
python -m legged_studio.contracts.selfcheck
node --check legged_studio\web\app.js
node --check legged_studio\electron\main.js
```

预期 backend 5/5 通过，Contract 加载 107 条记录且 JS 无语法错误。

## HTTP smoke

```powershell
python -m uvicorn legged_studio.backend.app:app --port 8000
```

验证 `/`、`/api/health`、`/api/summary`、`/api/assets?size=M&limit=3` 和 `/api/assets/unitree_go2` 均返回成功；未知 family 应返回 JSON 404。

## Electron 人工验收

```powershell
cd C:\Users\31560\Documents\00_open\legged_studio
npm start
```

验收窗口显示资产工作台、筛选与搜索可用、退出后 Python 子进程被回收、端口被占用时有明确失败日志。GUI 验收完成前，不把 Electron 打包标为完成。
