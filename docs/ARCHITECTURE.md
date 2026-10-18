# XferBridge —— 跨存档迁移桥（架构设计）

> Forge 1.20.1 模组 + Python 桌面外部工具，实现「角色属性与物品跨存档迁移」的完整链路。

## 1. 总体架构

```
┌────────────────────────────────────────────────────────────┐
│ Minecraft 客户端 (Forge 1.20.1)   ——  mods/xferbridge-*.jar  │
│                                                              │
│  游戏内 GUI 层                                                │
│   ├ 主菜单/暂停菜单按钮 + F9 快捷键                            │
│   ├ 存档选择页（列出工具扫描出的所有存档）                       │
│   ├ 依赖检查结果页（缺失/冲突/隔离预览）                        │
│   ├ 缺失模组安装页（引导安装 / 自动安装）                       │
│   ├ 自动安装页（免责声明 + 勾选 + 随机验证码 + 开始下载）         │
│   ├ 配置 Diff 页（源值/目标值对比 + 勾选）                      │
│   ├ 物品映射页（隔离提示 + 同名异 ID 手动替换）                  │
│   └ 隔离背包页（虚拟背包，查看/释放/导出）                      │
│                                                              │
│  核心逻辑层                                                   │
│  ├ PlayerDataExtractor  提取玩家属性+物品 → NBT 载荷           │
│  ├ ItemMappingTable     物品 ID 映射表（持久化 JSON）           │
│  ├ QuarantineStore      隔离区/虚拟背包（CustomSavedData）      │
│  ├ TransferFlow         跨存档流程编排                          │
│  └ BackupHooks          备份触发器（退出世界/保存/迁移前）       │
│                                                              │
│  IPC 客户端（读写 workspace 下的 JSON 请求/响应/事件）           │
└──────────────────────────┬───────────────────────────────────┘
                           │ 文件 IPC：%APPDATA%\XferBridge\
                           │ 请求 request_*.json / 响应 resp_*.json
                           │ 事件 evt_*.json / 计划 plan_*.json
┌──────────────────────────┴───────────────────────────────────┐
│ Python 外部工具 XferTool（Tkinter 桌面程序）                    │
│  ├ launchers   多启动器存档/实例扫描（官方、PCL、HMCL、CurseForge、 │
│  │             Prism/MultiMC、自定义路径）                      │
│  ├ modmeta     模组元数据解析（META-INF/mods.toml、fabric.mod.json│
│  │             MANIFEST.MF），jar 内 zipfile 读取              │
│  ├ dependency  依赖树构建 + 缺失/版本不匹配/冲突/重复检测          │
│  ├ downloader  Modrinth v2 API 搜索+下载，SHA1/MD5 哈希校验       │
│  ├ staging     .staging 暂存区（下载不直写 mods/）               │
│  ├ backup      全量/增量备份（zip + 清单），一键回滚              │
│  ├ quarantine  隔离区管理 + 导出（zip / Base64）                 │
│  ├ nbt         最小 NBT 读写器（合并玩家数据到目标存档）          │
│  ├ transfer    迁移执行器（配置合并、玩家数据写入、收尾）          │
│  ├ ipc         请求处理（mod→tool 双向）                         │
│  └ ui          Tkinter 界面（存档列表/详情/操作/日志/设置）        │
└────────────────────────────────────────────────────────────┘
```

## 2. 设计原则

1. **重量级任务在外部工具**：打包压缩、下载、备份、回滚、扫描全部在 Python 工具内完成；游戏内只做选择与物品级逻辑。
2. **文件 IPC 为唯一通信方式**：无需网络端口、无需模组与工具同机常驻，天然跨进程、可审计。
3. **一切破坏性操作先备份**：任何覆盖目标存档前，先对目标存档做全量备份、对 config 文件夹做独立打包备份。
4. **下载不直写**：所有下载先进入 `.staging` 暂存区并校验哈希，确认后才移入 `mods/`。
5. **可回滚**：外部工具保留备份链，任何一步可一键回滚。

## 3. 目录结构

```
├── README.md                    总览
├── docs\
│   ├── ARCHITECTURE.md          本文档
│   ├── PROTOCOL.md              IPC 协议与数据格式
│   └── USER_GUIDE.md            使用手册
├── mod\                         Forge 1.20.1 模组工程
│   ├── build.gradle / settings.gradle / gradle.properties
│   ├── gradlew(.bat) + gradle\wrapper\
│   └── src\main\
│       ├── java\com\xferbridge\...
│       └── resources\META-INF\mods.toml, pack.mcmeta, assets\...
└── tool\                        Python 外部工具
    ├── run.py                   启动入口
    ├── xfer_tool\               （模块见上）
    └── tests\                   测试与冒烟脚本
```

## 4. 工作区（%APPDATA%\XferBridge\）布局

| 路径 | 内容 |
|---|---|
| `saves_index.json` | 扫描出的全部实例与存档索引 |
| `requests\req_*.json` | 请求（mod→tool 或 GUI 操作） |
| `responses\resp_*.json` | 响应（tool→mod） |
| `events\evt_*.json` | 进度事件（tool→mod 轮询） |
| `plans\plan_*.json` | 迁移计划 |
| `transfers\<id>\` | 玩家数据载荷、决策文件、执行结果 |
| `staging\` | 下载暂存区（.staging） |
| `backups\<save_id>\` | 全量/增量备份与回滚点 |
| `quarantine\<save_id>\` | 隔离数据与导出物 |
| `moddb\` | 模组元数据缓存 |
| `logs\` | 运行日志 |

## 5. 跨存档迁移主流程

```
[游戏内 源存档 A]
  1. 玩家打开 XferBridge（F9 / 暂停菜单按钮）
  2. 存档选择页 ← 读 saves_index.json，选出目标存档 B
  3. 请求 check_deps(A, B) → 工具分析模组依赖 → 返回报告
  4. 依赖检查结果页：
     - 缺失模组/冲突/隔离物品预览
     - 目标缺 xferbridge 本体或其他模组 → 缺失模组安装页：
         [否] → 停止，返回上一步
         [是] → 工具先全量备份 B
               ├ 引导安装：列出缺失模组 + 下载链接（浏览器打开）
               └ 自动安装：免责声明+勾选+验证码 → 开始自动下载
                    下载到 B 的 mods\.staging → SHA1/MD5 校验
                    → 提示「需要重启游戏才能生效，是否现在重启？」
  5. 玩家数据提取：属性+背包+末影箱+经验+生命/饥饿 → NBT 载荷
     - 目标缺模组的物品 → 进入隔离区（暂不写入载荷）
     - 同名异 ID → 按映射表/手动选择替换
  6. 配置 Diff 页：仅列「共存模组」的 config；缺失模组 config 直接进隔离区
     默认保留目标配置；替换前自动打包备份目标 config 文件夹
  7. 确认 → 工具执行：
     a. 备份 B（全量）
     b. 应用配置决策（含备份）
     c. 安装暂存区内已校验模组（.staging → mods）
     d. 将玩家载荷合并写入 B 的 playerdata
     e. 隔离物品写入 B 的 xfer_quarantine（+ 工作区镜像）
     f. 返回执行报告
  8. 玩家进入 B：隔离背包页查看/释放隔离物品；工具侧可随时回滚
```

## 6. 模组与工具的功能映射（对应 11 项需求）

| # | 需求 | 实现位置 |
|---|---|---|
| 1 | 角色属性与物品跨存档 | mod `PlayerDataExtractor` + tool `transfer.py`（NBT 合并） |
| 2 | 检测电脑上所有 Microsoft 存档 | tool `launchers.py`（官方启动器 + 各第三方启动器） |
| 3 | 游戏内选择页列出全部存档 | mod `gui/SaveSelectScreen`（读 saves_index.json） |
| 4 | 依赖树与冲突检测、缺失前置判断 | tool `modmeta.py` + `dependency.py`，mod 展示 |
| 5 | 缺失模组安装（引导/自动+免责+验证码+暂存+重启+哈希） | mod `gui/MissingModsScreen`、`AutoInstallScreen` + tool `downloader.py`、`staging.py` |
| 6 | 配置分类/对比/默认保留目标/自动备份 config | tool `transfer.py` + mod `gui/ConfigDiffScreen` |
| 7 | 物品 ID 映射表、预扫描拦截、隔离区/虚拟背包、手动替换 | mod `ItemMappingTable`、`QuarantineStore` + tool `quarantine.py` |
| 8 | 隔离区导出 zip / Base64 | tool `quarantine.py`（GUI/IPC 触发） |
| 9 | 增量备份触发器（退出世界/迁移前/手动保存） | mod `BackupHooks` + tool `backup.py` |
| 10 | 外部工具接管打包压缩 | tool `backup.py`（所有 zip 在工具侧） |
| 11 | 一键回滚 | tool `backup.py restore()` + GUI 按钮 |

## 7. 备份策略

- **全量备份**：`backups/<save_id>/full_<ts>.zip`，包含存档全部文件 + `manifest.json`（文件→SHA1）。
- **增量备份**：基于上次备份清单，仅打包变更/新增文件（按 mtime+size+SHA1 判定），删除记录写入清单；`incr_<ts>_from_<base>.zip`。
- **回滚**：`full` 直接还原；`incr` 按链式顺序应用。回滚前先把当前状态保存为 `pre_rollback_<ts>.zip`。
- **触发**：`PlayerLoggedOutEvent`（退出世界）、`PlayerEvent.SaveToFile`（手动/周期保存，节流）、迁移执行前（双存档全量）、GUI 手动。

## 8. 隔离区/虚拟背包

- 游戏内：`CustomSavedData`（键 `xferbridge_quarantine`），条目 = `{transfer_id, 物品registry, 数量, NBT(压缩), 来源存档, 来源模组, 状态}`。
- 磁盘：目标存档 `xfer_quarantine\items_<ts>.json`（工具写入），mod 在世界加载时幂等导入 CustomSavedData。
- 释放：目标存档已装对应模组 → 虚拟背包页一键放回玩家背包（NBT 还原 ItemStack）。
- 导出：`quarantine.py` 打包为 zip，或把载荷 Base64 编码为字符串（可复制保存/分享）。

## 9. 安全与免责

- 自动安装下载第三方模组：仅从 Modrinth 官方 API 获取，校验 SHA1；下载前强制展示免责声明 + 勾选 + 随机验证码。
- 所有写入目标存档的操作均有备份前置；对存档目录的修改以「复制/移动 + 清单」方式记录，可审计。
