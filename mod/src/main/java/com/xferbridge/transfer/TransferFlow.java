package com.xferbridge.transfer;

import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.xferbridge.XferConstants;
import com.xferbridge.gui.AutoInstallScreen;
import com.xferbridge.gui.ConfigDiffScreen;
import com.xferbridge.gui.GuidedInstallScreen;
import com.xferbridge.gui.MappingScreen;
import com.xferbridge.gui.MissingModsScreen;
import com.xferbridge.gui.PlanReviewScreen;
import com.xferbridge.gui.ProgressScreen;
import com.xferbridge.gui.QuarantineScreen;
import com.xferbridge.gui.ResultScreen;
import com.xferbridge.gui.SaveSelectScreen;
import com.xferbridge.gui.XferMainScreen;
import com.xferbridge.ipc.IpcChannel;
import com.xferbridge.ipc.Protocol;
import com.xferbridge.mapping.ItemMappingTable;
import net.minecraft.client.Minecraft;
import net.minecraft.server.MinecraftServer;
import net.minecraft.world.entity.player.Player;

import java.nio.file.Path;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;

/**
 * 跨存档迁移流程编排（客户端状态机）。
 *
 * SELECTING → PLANNING → PLAN_REVIEW → MISSING_INSTALL → CONFIG → MAPPING
 *            → EXTRACTING → APPLYING → DONE
 *
 * 所有与外部工具的交互通过文件 IPC；进度/响应在客户端 tick 中轮询。
 */
public final class TransferFlow {
    public static final TransferFlow INSTANCE = new TransferFlow();

    public enum Phase {
        IDLE, SELECTING, PLANNING, PLAN_REVIEW, INSTALLING, CONFIG, MAPPING,
        EXTRACTING, APPLYING, DONE
    }

    private Phase phase = Phase.IDLE;
    private final IpcChannel channel = new IpcChannel();
    private String sourceSaveId = "";
    private String targetSaveId = "";
    private String planRequestId = "";
    private String installRequestId = "";
    private String applyRequestId = "";
    private String transferId = "";
    private JsonObject plan = new JsonObject();
    private JsonObject decision = new JsonObject();
    private ItemMappingTable mappingTable = new ItemMappingTable();
    private JsonObject pendingConfigChoices = new JsonObject();
    private String lastError = "";

    private TransferFlow() {
    }

    public Phase phase() {
        return phase;
    }

    public IpcChannel channel() {
        return channel;
    }

    public JsonObject plan() {
        return plan;
    }

    public String transferId() {
        return transferId;
    }

    public String targetSaveId() {
        return targetSaveId;
    }

    public void reset() {
        phase = Phase.IDLE;
        planRequestId = installRequestId = applyRequestId = "";
        transferId = "";
        plan = new JsonObject();
        decision = new JsonObject();
        lastError = "";
    }

    // ------------------------------------------------------------ 入口
    public void openMain(Minecraft mc) {
        if (mc.player == null) {
            return;
        }
        mc.setScreen(new XferMainScreen(this));
    }

    public void openQuarantine(Minecraft mc) {
        com.xferbridge.quarantine.QuarantineStore store =
                com.xferbridge.quarantine.QuarantineStore.of(mc.getSingleplayerServer());
        mc.setScreen(new QuarantineScreen(this, store));
    }

    /** 1) 进入存档选择页。 */
    public void startSelect(Minecraft mc) {
        phase = Phase.SELECTING;
        mc.setScreen(new SaveSelectScreen(this));
    }

    /** 2) 玩家选中目标存档 → 请求生成迁移计划。 */
    public void onTargetSelected(Minecraft mc, String targetId) {
        sourceSaveId = currentSaveId(mc);
        targetSaveId = targetId;
        Player player = mc.player;
        if (player == null) {
            fail("当前没有玩家实体");
            return;
        }
        JsonObject payload = new JsonObject();
        payload.addProperty("source_save", sourceSaveId);
        payload.addProperty("target_save", targetSaveId);
        payload.add("player_manifest", Protocol.playerItemManifest(player));
        planRequestId = channel.writeRequestWithWorld("plan_transfer", payload, worldContext(mc));
        phase = Phase.PLANNING;
        ProgressScreen.show(mc, this, "正在生成迁移计划",
                "请确保 XferBridge 外部工具已启动（或已开启 IPC 守护）…");
    }

    /** 3) 计划已生成 → 依赖检查结果页。 */
    public void onPlanReady(Minecraft mc) {
        phase = Phase.PLAN_REVIEW;
        mc.setScreen(new PlanReviewScreen(this, plan));
    }

    /** 4a) 玩家选择「否」→ 停止跨越，返回存档选择页。 */
    public void cancelTransfer(Minecraft mc) {
        phase = Phase.SELECTING;
        mc.setScreen(new SaveSelectScreen(this));
    }

    /** 4c) 计划审查通过 → 有缺失则进入安装选择页，否则直接配置 Diff。 */
    public void toInstallChoice(Minecraft mc) {
        JsonObject dep = plan.has("dep_report") ? plan.getAsJsonObject("dep_report") : new JsonObject();
        boolean targetMissingXb = dep.has("target_missing_xferbridge")
                && dep.get("target_missing_xferbridge").getAsBoolean();
        if (!missingMods().isEmpty() || targetMissingXb) {
            mc.setScreen(new MissingModsScreen(this, missingMods(), targetMissingXb));
        } else {
            toConfigDiff(mc);
        }
    }

    /** 5) 配置 Diff 页。 */
    public void toConfigDiff(Minecraft mc) {
        phase = Phase.CONFIG;
        JsonObject cfg = plan.has("config_diff") ? plan.getAsJsonObject("config_diff") : new JsonObject();
        mc.setScreen(new ConfigDiffScreen(this, cfg));
    }

    /** 配置选择确认 → 进入物品映射页。 */
    public void confirmConfig(Minecraft mc, JsonObject configChoices) {
        pendingConfigChoices = configChoices == null ? new JsonObject() : configChoices;
        toMapping(mc);
    }

    /** 6) 物品映射页（隔离预览 + 同名异 ID 手动替换）。 */
    public void toMapping(Minecraft mc) {
        phase = Phase.MAPPING;
        JsonObject itemPreview = plan.has("item_preview") ? plan.getAsJsonObject("item_preview") : new JsonObject();
        mappingTable = ItemMappingTable.load(channel, worldConfigDir(mc));
        mc.setScreen(new MappingScreen(this, itemPreview, mappingTable));
    }

    /** 7) 提取玩家数据 + 写决策 + 请求执行。 */
    public void confirmAndApply(Minecraft mc, Map<String, String> mappingChoices) {
        confirmAndApply(mc, mappingChoices, pendingConfigChoices);
    }

    /** 4b) 玩家选择「是」→ 先请求备份目标存档，再选择安装方式。 */
    public void onMissingInstallYes(Minecraft mc) {
        JsonObject payload = new JsonObject();
        payload.addProperty("save_id", targetSaveId);
        payload.addProperty("kind", "full");
        payload.addProperty("label", "pre_install");
        channel.writeRequestWithWorld("backup", payload, worldContext(mc));
        ProgressScreen.show(mc, this, "已请求备份目标存档",
                "外部工具正在全量备份目标存档…备份完成后请选择安装方式。");
    }

    /** 引导安装：打开缺失模组列表 + 下载链接。 */
    public void guidedInstall(Minecraft mc) {
        decision.addProperty("install_mode", "guided");
        mc.setScreen(new GuidedInstallScreen(this, missingMods()));
    }

    /** 自动安装：免责声明 + 验证码。 */
    public void autoInstall(Minecraft mc) {
        decision.addProperty("install_mode", "auto");
        mc.setScreen(new AutoInstallScreen(this, missingMods()));
    }

    /** 自动安装确认后：请求外部工具下载到 .staging。 */
    public void startAutoDownload(Minecraft mc) {
        JsonObject payload = new JsonObject();
        payload.addProperty("target_save", targetSaveId);
        payload.add("mods", missingMods());
        installRequestId = channel.writeRequestWithWorld("install_mods", payload, worldContext(mc));
        phase = Phase.INSTALLING;
        ProgressScreen.show(mc, this, "正在自动下载缺失模组",
                "文件将下载到目标存档 mods/.staging 并校验 SHA1/MD5…");
    }

    /** 7) 提取玩家数据 + 写决策 + 请求执行。 */
    public void confirmAndApply(Minecraft mc, Map<String, String> mappingChoices,
                                JsonObject configChoices) {
        Player player = mc.player;
        if (player == null) {
            fail("当前没有玩家实体");
            return;
        }
        JsonObject cfgChoices = configChoices == null ? new JsonObject() : configChoices;
        decision.add("config_choices", cfgChoices);
        JsonObject mcJson = new JsonObject();
        for (Map.Entry<String, String> e : mappingChoices.entrySet()) {
            mcJson.addProperty(e.getKey(), e.getValue());
        }
        decision.add("mapping_choices", mcJson);
        JsonArray missingCfg = new JsonArray();
        if (plan.has("config_diff") && plan.getAsJsonObject("config_diff").has("missing_mods_configs")) {
            missingCfg = plan.getAsJsonObject("config_diff").getAsJsonArray("missing_mods_configs");
        }
        decision.add("missing_configs_quarantine", missingCfg);
        decision.addProperty("proceed", true);

        // 隔离 registry 集合
        Set<String> quarantineRegistries = new HashSet<>();
        if (plan.has("item_preview")) {
            JsonObject ip = plan.getAsJsonObject("item_preview");
            if (ip.has("quarantine_candidates")) {
                for (JsonElement el : ip.getAsJsonArray("quarantine_candidates")) {
                    quarantineRegistries.add(el.getAsJsonObject().get("registry").getAsString());
                }
            }
        }

        phase = Phase.EXTRACTING;
        ProgressScreen.show(mc, this, "正在提取玩家数据…", "属性、背包、末影箱、经验、生命/饥饿…");

        PlayerDataExtractor.Result result = PlayerDataExtractor.extract(
                player, transferId, sourceSaveId, targetSaveId,
                quarantineRegistries, mappingChoices);

        JsonObject payload = result.payload();
        channel.writeTransferFile(transferId, "payload.json", payload);
        channel.writeTransferFile(transferId, "decision.json", decision);

        JsonObject apply = new JsonObject();
        apply.addProperty("transfer_id", transferId);
        applyRequestId = channel.writeRequestWithWorld("apply_transfer", apply, worldContext(mc));
        phase = Phase.APPLYING;
        ProgressScreen.show(mc, this, "正在执行迁移…",
                "外部工具将依次执行：备份 → 配置 → 模组 → 玩家数据合并 → 隔离写入");
    }

    // ------------------------------------------------------------ tick
    /** 客户端 tick 轮询：必须在客户端线程调用。 */
    public void tick(Minecraft mc) {
        if (phase == Phase.PLANNING) {
            JsonObject resp = channel.pollResponse(planRequestId);
            if (resp != null) {
                if (resp.has("ok") && resp.get("ok").getAsBoolean()) {
                    JsonObject result = resp.getAsJsonObject("result");
                    plan = result.getAsJsonObject("plan");
                    transferId = plan.get("transfer_id").getAsString();
                    decision = new JsonObject();
                    decision.addProperty("transfer_id", transferId);
                    onPlanReady(mc);
                } else {
                    fail(resp.has("error") ? resp.get("error").getAsString() : "计划生成失败");
                }
            }
        } else if (phase == Phase.INSTALLING) {
            JsonObject evt = channel.latestEvent(installRequestId);
            if (evt != null && mc.screen instanceof ProgressScreen ps) {
                ps.update(evt);
            }
            JsonObject resp = channel.pollResponse(installRequestId);
            if (resp != null) {
                if (resp.has("ok") && resp.get("ok").getAsBoolean()) {
                    JsonObject r = resp.has("result") ? resp.getAsJsonObject("result") : new JsonObject();
                    if (r.has("restart_required") && r.get("restart_required").getAsBoolean()) {
                        phase = Phase.PLAN_REVIEW;
                        mc.setScreen(new com.xferbridge.gui.RestartPromptScreen(this));
                    } else {
                        toConfigDiff(mc);
                    }
                } else {
                    fail(resp.has("error") ? resp.get("error").getAsString() : "自动下载失败");
                }
            }
        } else if (phase == Phase.APPLYING) {
            JsonObject evt = channel.latestEvent(applyRequestId);
            if (evt != null && mc.screen instanceof ProgressScreen ps) {
                ps.update(evt);
            }
            JsonObject resp = channel.pollResponse(applyRequestId);
            if (resp != null) {
                if (resp.has("ok") && resp.get("ok").getAsBoolean()) {
                    JsonObject result = resp.getAsJsonObject("result");
                    phase = Phase.DONE;
                    boolean restart = result.has("restart_required")
                            && result.get("restart_required").getAsBoolean();
                    mc.setScreen(new ResultScreen(this, result, restart));
                } else {
                    fail(resp.has("error") ? resp.get("error").getAsString() : "迁移执行失败");
                }
            }
        }
    }

    // ------------------------------------------------------------ 工具
    public JsonArray missingMods() {
        JsonArray arr = new JsonArray();
        if (plan.has("mods_to_install")) {
            arr = plan.getAsJsonArray("mods_to_install");
        }
        return arr;
    }

    public void fail(String message) {
        lastError = message;
        phase = Phase.IDLE;
    }

    public String lastError() {
        return lastError;
    }

    /** 当前世界上下文（文件夹名 + 绝对路径）。 */
    public static IpcChannel.WorldContext worldContext(Minecraft mc) {
        MinecraftServer server = mc.getSingleplayerServer();
        if (server == null) {
            return null;
        }
        try {
            Path p = server.getWorldPath(net.minecraft.world.level.storage.LevelResource.ROOT);
            return new IpcChannel.WorldContext(p.getFileName().toString(), p);
        } catch (Exception e) {
            return null;
        }
    }

    public static Path worldConfigDir(Minecraft mc) {
        IpcChannel.WorldContext ctx = worldContext(mc);
        if (ctx != null && ctx.path() != null) {
            return ctx.path().resolve("config").resolve("xferbridge");
        }
        return Path.of(".");
    }

    /** 从存档索引解析当前世界对应的 save id。 */
    public String currentSaveId(Minecraft mc) {
        IpcChannel.WorldContext ctx = worldContext(mc);
        if (ctx == null) {
            return "current_world";
        }
        JsonArray saves = channel.savesArray();
        String path = ctx.path() == null ? null : ctx.path().toString();
        String folder = ctx.folder();
        for (JsonElement el : saves) {
            JsonObject s = el.getAsJsonObject();
            if (path != null && s.has("path") && path.equalsIgnoreCase(s.get("path").getAsString())) {
                return s.get("id").getAsString();
            }
        }
        for (JsonElement el : saves) {
            JsonObject s = el.getAsJsonObject();
            if (folder != null && s.has("path")) {
                try {
                    String name = Path.of(s.get("path").getAsString()).getFileName().toString();
                    if (folder.equalsIgnoreCase(name)) {
                        return s.get("id").getAsString();
                    }
                } catch (Exception ignored) {
                }
            }
        }
        return folder != null ? folder : "current_world";
    }
}
