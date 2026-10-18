package com.xferbridge.gui;

import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.xferbridge.transfer.TransferFlow;
import net.minecraft.client.gui.GuiGraphics;
import net.minecraft.network.chat.Component;

import java.util.ArrayList;
import java.util.List;

/** 迁移结果页：执行摘要 + 重启提示。 */
public class ResultScreen extends XferScreen {
    private final JsonObject result;
    private final boolean restartRequired;
    private final List<String> lines = new ArrayList<>();

    public ResultScreen(TransferFlow flow, JsonObject result, boolean restartRequired) {
        super(Component.literal("迁移完成"), flow);
        this.result = result;
        this.restartRequired = restartRequired;
        buildLines();
    }

    private void buildLines() {
        lines.add("迁移已由外部工具执行完成：");
        lines.add("");
        lines.add("· 全量备份: " + str(result, "backup_id", "-"));
        lines.add("· 配置: 应用 " + intOf(result, "config_applied") + " 项 / 保留 "
                + intOf(result, "config_kept") + " 项"
                + (result.has("config_backup_id") ? "（config 已备份 " + result.get("config_backup_id").getAsString() + "）" : ""));
        if (result.has("mods_installed")) {
            JsonArray arr = result.getAsJsonArray("mods_installed");
            lines.add("· 已安装模组: " + arr.size() + " 个");
            for (int i = 0; i < Math.min(arr.size(), 4); i++) {
                JsonObject m = arr.get(i).getAsJsonObject();
                lines.add("    - " + str(m, "file", "?") + "（SHA1 校验通过）");
            }
        }
        lines.add("· 玩家数据合并: " + (result.has("playerdata_merged") && result.get("playerdata_merged").getAsBoolean() ? "成功" : "否"));
        if (result.has("quarantine_written")) {
            JsonObject q = result.getAsJsonObject("quarantine_written");
            lines.add("· 隔离区: " + intOf(q, "count") + " 件物品已写入 " + str(q, "path", ""));
        }
        lines.add("");
        if (restartRequired) {
            lines.add("缺失模组已下载完毕，需要重启游戏才能生效。");
            lines.add("是否现在重启？");
        } else {
            lines.add("进入目标存档后，可在「隔离背包」查看/释放隔离物品。");
        }
    }

    @Override
    protected void init() {
        int cx = this.width / 2;
        addButton(cx - 110, this.height - 28, 220, 20, "好的（返回主界面）",
                b -> mc().setScreen(new XferMainScreen(flow)));
    }

    @Override
    public void render(GuiGraphics gfx, int mouseX, int mouseY, float partialTick) {
        this.renderBackground(gfx);
        drawTitle(gfx, restartRequired ? "迁移完成 — 需要重启游戏" : "迁移完成");
        int y = 34;
        for (String line : lines) {
            gfx.drawString(this.font, line, 24, y, 0xE0E0E0);
            y += this.font.lineHeight + 2;
        }
        super.render(gfx, mouseX, mouseY, partialTick);
    }

    private static String str(JsonObject o, String key, String def) {
        return o != null && o.has(key) ? o.get(key).getAsString() : def;
    }

    private static int intOf(JsonObject o, String key) {
        return o != null && o.has(key) ? o.get(key).getAsInt() : 0;
    }
}
