# XferBridge IPC 协议 v1

> 模组与外部工具之间的全部数据交换。协议版本号 `"protocol": "xferbridge.ipc.v1"`。
> 默认工作区：`%APPDATA%\XferBridge\`（模组与工具均可配置覆盖，但必须一致）。

## 1. 通用信封

### 请求（写入 `workspace/requests/req_<uuid>.json`）

```json
{
  "protocol": "xferbridge.ipc.v1",
  "request_id": "a1b2c3d4-e5f6-...",
  "action": "check_deps",
  "from": "mod",
  "created_at": "2026-10-17T10:00:00+08:00",
  "payload": { "...": "按 action 定义" }
}
```

### 响应（写入 `workspace/responses/resp_<uuid>.json`）

```json
{
  "protocol": "xferbridge.ipc.v1",
  "request_id": "a1b2c3d4-e5f6-...",
  "ok": true,
  "error": null,
  "result": { "...": "按 action 定义" },
  "completed_at": "2026-10-17T10:00:05+08:00"
}
```

### 事件（写入 `workspace/events/evt_<uuid>.json`，进度轮询）

```json
{
  "protocol": "xferbridge.ipc.v1",
  "request_id": "a1b2c3d4-e5f6-...",
  "stage": "downloading",
  "percent": 42,
  "message": "正在下载 jei-1.20.1-15.2.0.27.jar (3/7)",
  "at": "2026-10-17T10:00:03+08:00"
}
```

## 2. Action 清单

| action | 方向 | 说明 |
|---|---|---|
| `ping` | 双向 | 探活，返回 `{pong: true, version}` |
| `scan_saves` | 双向 | 全盘扫描存档，返回 `saves_index` |
| `check_deps` | mod→tool | 依赖树+冲突检测 |
| `plan_transfer` | mod→tool | 生成迁移计划（含配置 diff、隔离物品清单、缺失模组） |
| `apply_transfer` | mod→tool | 按决策执行迁移（备份→配置→模组→玩家数据→隔离写入） |
| `backup` | 双向 | `{save_id, kind: full|incremental, trigger}` |
| `rollback` | tool GUI | `{save_id, backup_id}` |
| `install_mods` | mod→tool | 缺失模组下载安装（auto 模式） |
| `install_guided` | tool GUI | 引导安装：仅输出下载链接清单 |
| `export_quarantine` | 双向 | 导出隔离区 `{save_id, format: zip|base64}` |
| `restart_prompt` | tool→mod | 通知下载完毕、请重启（mod 展示提示） |
| `status` | mod→tool | 查询进行中任务进度 |

## 3. 数据模型

### SaveEntry（存档条目，saves_index.json）

```json
{
  "id": "official|minecraft|world1",
  "name": "world1",
  "display_name": "world1 (1.20.1)",
  "launcher": "official",
  "instance": "minecraft",
  "path": "C:/Users/xx/AppData/Roaming/.minecraft/saves/world1",
  "version": "1.20.1",
  "mods_dir": "C:/Users/xx/AppData/Roaming/.minecraft/mods",
  "last_played": 1690000000000,
  "player_name": "Steve",
  "player_uuid": "8667ba71-b85a-4004-af54-457a9734eed7",
  "has_xferbridge": false,
  "mod_count": 37,
  "mods": [ "ModEntry...", "..." ]
}
```

`mods` 数组内嵌 `ModEntry`（见下），`saves_index.json` 顶层：

```json
{ "protocol": "xferbridge.ipc.v1", "kind": "saves_index",
  "scanned_at": "...", "saves": [SaveEntry...],
  "launchers": [{"launcher":"official","root":"...","found":true}],
  "custom_paths": [...] }
```

### ModEntry（模组条目，来自 modmeta.py）

```json
{
  "mod_id": "jei",
  "display_name": "Just Enough Items",
  "version": "15.2.0.27",
  "loader": "forge",
  "mc_version": "1.20.1",
  "file": "jei-1.20.1-15.2.0.27.jar",
  "path": ".../mods/jei-....jar",
  "sha1": "0123abcd...",
  "dependencies": [
    {"mod_id": "forge", "type": "required", "version_range": "[47.0,48)"}
  ],
  "conflicts": [
    {"mod_id": "optifine", "version_range": "*"}
  ],
  "breaks": [],
  "optional_dependencies": []
}
```

### DepReport（check_deps 结果）

```json
{
  "source_save": "...", "target_save": "...",
  "source_mods": [ModEntry...],
  "target_mods": [ModEntry...],
  "missing": [
    {"mod_id": "jei", "display_name": "JEI", "version": "15.2.0.27",
     "required_by": ["src_mod_a"], "version_range": "*",
     "downloads": [{"source":"modrinth","slug":"jei","url":"https://..."}],
     "can_auto_install": true}
  ],
  "version_mismatch": [ {"mod_id":"x","in_source":"1.0","in_target":"2.0","range":"[1.0,2.0)"} ],
  "conflicts": [ {"mod_id":"x","with":"y","reason":"mods.toml conflicts"} ],
  "duplicates": [ {"mod_id":"z","files":["a.jar","b.jar"]} ],
  "cycles": [ ["a","b","a"] ],
  "target_missing_xferbridge": true,
  "summary": {"missing":2,"mismatch":1,"conflicts":0,"duplicates":0,"cycles":0}
}
```

### TransferPlan（plan_transfer 结果）

```json
{
  "transfer_id": "uuid",
  "source_save": "...", "target_save": "...",
  "dep_report": {DepReport},
  "config_diff": {
    "coexist_diff": [
      {"mod_id":"jei","file":"config/jei.toml",
       "status":"changed",
       "source": ".../config/jei.toml", "target": ".../config/jei.toml",
       "diff_preview": ["- key=1", "+ key=2"]}
    ],
    "missing_mods_configs": [ "config/only_src.toml", "..." ],
    "target_config_backup_required": true
  },
  "item_preview": {
    "quarantine_candidates": [
      {"registry":"srcmod:sword","count":12,"mod_id":"srcmod",
       "reason":"target_missing_mod"}
    ],
    "same_name_diff_id": [
      {"registry_source":"srcmod:old","display":"铁剑",
       "candidates":["srcmod:new","vanilla:iron_sword"],"chosen":null}
    ],
    "total_quarantine_count": 12
  },
  "mods_to_install": [ModEntry...],
  "steps": ["backup","config","mods","playerdata","quarantine","report"]
}
```

### TransferDecision（决策文件，写入 `transfers/<id>/decision.json`）

```json
{
  "transfer_id": "uuid",
  "config_choices": {"config/jei.toml": "keep_target", "config/a.toml": "use_source"},
  "mapping_choices": {"srcmod:old": "srcmod:new"},
  "install_mode": "auto",
  "install_consent": {"disclaimer_read": true, "captcha_ok": true},
  "proceed": true
}
```

### ApplyResult（apply_transfer 结果）

```json
{
  "transfer_id": "uuid",
  "backup_id": "full_20261017_100000",
  "config_applied": 1,
  "config_kept": 3,
  "mods_installed": [{"mod_id":"jei","file":"jei-....jar","sha1_ok":true}],
  "playerdata_merged": true,
  "quarantine_written": {"count": 12, "path": "..."},
  "restart_required": true
}
```

## 4. 玩家数据载荷（transfers/<id>/payload.json）

```json
{
  "format": "xferbridge.payload.v1",
  "transfer_id": "uuid",
  "source_save": "...", "target_save": "...",
  "player": {"name": "Steve", "uuid": "8667ba71-..."},
  "nbt_base64": "<gzip 压缩 NBT 的 Base64>",
  "quarantine_nbt_base64": "<隔离物品 gzip NBT Base64>",
  "quarantine_meta": [{"registry":"srcmod:sword","count":12,"mod_id":"srcmod"}],
  "mapping_applied": {"srcmod:old": "srcmod:new"}
}
```

NBT 载荷结构（`nbt_base64` 解压后）：

```
Compound
├─ Attributes   Compound  (player.getAttributes().save())
├─ Inventory    List<Compound>  (ItemStack::save)
├─ EnderItems   List<Compound>
├─ XpLevel      Int
├─ XpTotal      Int
├─ XpProgress   Float
├─ Health       Float
├─ FoodLevel    Int
├─ GameMode     Int
└─ Dimension    String
```

工具侧 `nbt.py` 将该结构合并进目标存档 `playerdata/<uuid>.dat`：
- 目标无 playerdata → 以载荷新建；
- 存在 → `Inventory/EnderItems/Attributes/XpLevel/XpTotal/XpProgress/Health/FoodLevel` 覆盖，其余字段保留；
- 写入前先对该 .dat 做 `playerdata_backup_<ts>.dat` 副本。

## 5. 配置文件 Diff 约定

- 仅对比「源/目标共存模组」的 config 文件；缺失模组（源有目标无）的 config **不对比**，直接列入 `missing_mods_configs` 进隔离区。
- `coexist_diff` 按文件行级 `difflib.unified_diff` 生成 `diff_preview`（前 200 行）。
- 默认决策 `keep_target`（保留目标存档配置）。
- 无论任何文件被替换，工具先打包 `config` 文件夹为 `backups/<save_id>/config_backup_<ts>.zip`。

## 6. 下载与暂存约定

- 下载目标：目标实例 `mods\.staging\`（相对 mods 的隐藏暂存目录）；工具工作区 `staging\` 为镜像缓存。
- 校验：下载流式计算 SHA1 与 MD5，与 Modrinth 声明哈希比对；失败丢弃重试（最多 3 次，间隔 2s）。
- 安装：仅当 `apply_transfer` 决策 `install_mode=auto` 且全部校验通过后，将 `.staging` 文件原子移入 `mods/`（`os.replace`）。
- 完成事件：`restart_prompt` 事件 + 工作区 `events/` 提示「缺失模组已下载完毕，需要重启游戏才能生效」。

## 7. 隔离区导出格式

- `zip`：`quarantine/<save_id>/export_<ts>.zip`，内含 `manifest.json` + `items.json` + `payload_base64.txt`。
- `base64`：`{format:"xferbridge.quarantine.v1", items:[...], payload_base64:"..."}` 的 JSON 整体 Base64（单行字符串）。
