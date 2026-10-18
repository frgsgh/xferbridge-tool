# XferBridge 外部工具（Python / Tkinter）

> 作者：bubble（跨存档迁移桥 XferBridge 的外部助手）

跨存档迁移的外部助手：扫描存档、依赖/冲突检测、下载缺失模组（.staging + SHA1/MD5 校验）、
全量/增量备份与一键回滚、隔离区导出（zip / Base64）、处理游戏内模组发来的 IPC 请求。

## 运行要求

- Windows + Python 3.11+（官方安装版自带 tkinter，无需安装任何第三方包）
- 与游戏内模组共用工作区 `%APPDATA%\XferBridge`

## 启动

```bat
python run.py             # 图形界面
python run.py --daemon    # 仅后台守护（处理游戏内请求，无界面）
python run.py --scan      # 仅扫描存档并写入索引
```

## 功能

| 界面按钮 | 作用 |
|---|---|
| 扫描存档 | 扫描官方启动器 / PCL / HMCL / CurseForge / Prism/MultiMC / 自定义路径 |
| 依赖检查 | 选源/目标存档 → 缺失/版本不匹配/冲突/重复/依赖环报告 |
| 自动安装缺失模组 | 免责声明+验证码 → 下载到目标 `mods\.staging`，SHA1/MD5 校验 |
| 备份 / 增量备份 | 全量 zip + 清单；增量按文件哈希对比 |
| 回滚 | 列出备份点，一键恢复到选定备份（回滚前自动保存当前状态） |
| 导出隔离区 | zip 包 / Base64 字符串（可复制分享） |
| 启动 IPC 守护 | 轮询工作区请求目录，处理游戏内模组的请求并回写响应/事件 |

## 目录约定（工作区 `%APPDATA%\XferBridge`）

见根目录 `docs\PROTOCOL.md` 第 4 节。

## 测试

```bat
python -m unittest discover -s tests -v   # 单元测试（解析/依赖/备份/NBT/扫描）
python -m tests.smoke_e2e                # 端到端冒烟（合成存档 + IPC 全链路）
```
