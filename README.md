# XferBridge — 跨存档角色属性与物品迁移（Forge 1.20.1 模组 + Python 外部工具）

把「角色属性 + 背包/末影箱物品」从一个存档迁移到另一个存档（Java 版），
带完整的模组依赖/冲突检测、缺失模组引导或自动安装、配置对比、物品 ID 映射、
隔离区（虚拟背包）与增量备份回滚。

## 工程结构

```
├─ mod\       Forge 1.20.1 模组（Java 17，游戏内 GUI + IPC 客户端）
│  └─ src\main\java\com\xferbridge\...
├─ tool\      Python 外部工具（Tkinter，零第三方依赖）
│  └─ xfer_tool\...   + tests\（12 单测 + e2e 冒烟）
└─ docs\      ARCHITECTURE.md / PROTOCOL.md / USER_GUIDE.md
```

## 构建模组

```bat
cd mod
gradlew.bat build        # 产物：mod\build\libs\xferbridge-1.0.0.jar
```

前置：JDK 17（如 `winget install EclipseAdoptium.Temurin.17.JDK --source winget`）。
首次构建需从 maven.minecraftforge.net 拉取依赖，网络慢时可参考 seed_localm2.ps1
（本地镜像仓库绕过限速，配合 build.gradle 里的 file:// localm2 仓库）。

## 使用（快速上手）

1. 启动外部工具：`python tool\run.py`（或双击 `tool\启动外部工具.bat`）。
2. 点「扫描存档」→ 在列表中选中**源存档**与**目标存档**。
3. 点「依赖检查」→ 查看缺失/冲突报告；有缺失模组时选择「引导安装」或「自动安装」。
4. 自动安装：同意免责声明 → 输入随机验证码 → 下载进入目标存档 `mods\.staging`，
   完成 SHA1/MD5 校验后提示重启游戏。
5. 游戏内：将模组 jar 放入 `mods\`，进源存档 → 按 **F9**（或主菜单/暂停菜单按钮）→
   选择目标存档 → 按流程走：依赖检查 → 缺失模组处理 → 配置对比 → 物品映射 → 迁移。
6. 隔离物品：进目标存档后 F9 →「隔离背包」，安装对应模组后放回，或导出 zip/Base64。

完整说明见 `docs\USER_GUIDE.md`，通信协议见 `docs\PROTOCOL.md`。

## 功能清单（对应 11 项需求）

1. 角色属性与物品跨存档 — 模组抽取玩家数据 → 工具按映射写入目标存档
2. 检测所有 Microsoft/Java 版存档 — 官方/PCL/HMCL/CurseForge/Prism/MultiMC 扫描
3. 游戏内存档选择页 — F9 打开，列出全部检测存档
4. 依赖树与冲突检测 — mods.toml/fabric.mod.json 元数据 + 版本范围 + 依赖环检测
5. 缺失模组安装 — 引导（清单+链接）/ 自动（免责声明+验证码 → .staging → 哈希校验 → 重启提示）
6. 配置分类处理 — 只比共存模组；diff 视图默认保留目标；替换前整包备份 config
7. 物品 ID 映射表 — 预扫描隔离预览、同名异 ID 手动替换、隔离区/虚拟背包
8. 隔离区导出 — zip 压缩包 / Base64 字符串
9. 增量备份 — 退出世界/跨越前/手动保存三触发器
10. 外部工具接管 — 打包/压缩/下载全部由 Python 工具执行
11. 一键回滚 — 工具按备份点恢复（含独立 config 备份与链式回滚）

## 许可

MIT — © 2026 bubble
