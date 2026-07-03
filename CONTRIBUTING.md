# 贡献说明

感谢关注叩舷。这个项目的核心原则是：本地优先、少打扰、少解释，把用户自己的数字手感还给用户。

## 开发前先确认

- 不记录具体键盘内容。
- 不记录鼠标坐标。
- 不上传本地记录。
- 不把用户行为写成道德评价或效率评分。
- 新功能优先增加可回看的趣味和可理解的线索，而不是堆更多图表。

## 本地开发

```powershell
pip install -r requirements.txt
python main.py
```

打包：

```powershell
.\build.ps1
```

## 提交建议

提交前至少运行：

```powershell
python -m py_compile config.py db.py icons.py main.py monitor.py settings.py stats.py tray.py update_manager.py window.py
```

如果修改了界面，请实际打开应用检查：

- 启动是否白屏
- 窗口拖动是否跟手
- 托盘打开、刷新、退出是否正常
- 弹窗是否能完整显示
- 热力图和应用强度榜是否没有挤压或遮挡

## 产品口径

叩舷不是监控软件，也不是生产力打分器。它更像一只贴着船舷听响的耳朵：帮用户看见自己和应用之间的数字手感。

手感回放输出时应遵守：

- 先给结论。
- 只挑少量重要发现。
- 建议要能执行。
- 不假装知道用户真实意图。
- 不输出冗长报告。
