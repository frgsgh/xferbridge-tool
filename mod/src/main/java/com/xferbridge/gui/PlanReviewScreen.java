package com.xferbridge.gui;

import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.xferbridge.transfer.TransferFlow;
import net.minecraft.client.gui.GuiGraphics;
import net.minecraft.network.chat.Component;

import java.util.ArrayList;
import java.util.List;

/** 依赖检查结果页：缺失/冲突/版本不匹配/隔离预览 → 继续或取消。 */
public class PlanReviewScreen extends XferScreen {
    private final JsonObject plan;
    private final List<String> lines = new ArrayList<>();

    public PlanReviewScreen(TransferFlow flow, JsonObject plan) {
        super(Component.literal("依赖检查结果"), flow);
        this.plan = plan;
        buildLines();
    }

    private void buildLines() {
        JsonObject dep = plan.has("dep_report") ? plan.getAsJsonObject("dep_report") : new JsonObject();
        JsonObject summary = dep.has("summary") ? dep.getAsJsonObject("summary") : new JsonObject();
        int missing = intOf(summary, "missing");
        int mismatch = intOf(summary, "mismatch");
        int conflicts = intOf(summary, "conflicts");
        int duplicates = intOf(summary, "duplicates");
        int cycles = intOf(summary, "cycles");
        boolean targetMissingXb = dep.has("target_missing_xferbridge")
                && dep.get("target_missing_xferbridge").getAsBoolean();

        lines.add("源存档 → 目标存档 依赖分析");
        lines.add("");
        lines.add(String.format("缺失前置模组: %d    版本不匹配: %d    冲突: %d    重复: %d    依赖环: %d",
                missing, mismatch, conflicts, duplicates, cycles));
        lines.add("目标存档缺少 XferBridge 本体: " + (targetMissingXb ? "是" : "否"));
        lines.add("");
        if (missing > 0) {
            lines.add("== 缺失模组（将决定是否可跨越）==");
            for (JsonElement el : dep.getAsJsonArray("missing")) {
                JsonObject m = el.getAsJsonObject();
                lines.add("· " + m.get("mod_id").getAsString() + " v" + strOr(m, "version", "?")
                        + "（被 " + strOr(m, "required_by", "-") + " 需要）");
            }
        }
        if (mismatch > 0) {
            lines.add("== 版本不匹配 ==");
            for (JsonElement el : dep.getAsJsonArray("version_mismatch")) {
                JsonObject m = el.getAsJsonObject();
                lines.add("· " + m.get("mod_id").getAsString() + " 源 "
                        + strOr(m, "in_source", "?") + " / 目标 " + strOr(m, "in_target", "?")
                        + "（要求 " + strOr(m, "range", "*") + "）");
            }
        }
        if (conflicts > 0) {
            lines.add("== 冲突 ==");
            for (JsonElement el : dep.getAsJsonArray("conflicts")) {
                JsonObject m = el.getAsJsonObject();
                lines.add("· " + strOr(m, "mod_id", "?") + " ↔ " + strOr(m, "with", "?")
                        + "：" + strOr(m, "reason", ""));
            }
        }
        if (duplicates > 0) {
            lines.add("== 重复模组 ==");
            for (JsonElement el : dep.getAsJsonArray("duplicates")) {
                JsonObject m = el.getAsJsonObject();
                lines.add("· " + m.get("mod_id").getAsString() + "：" + strOr(m, "files", ""));
            }
        }
        if (plan.has("item_preview")) {
            JsonObject ip = plan.getAsJsonObject("item_preview");
            int total = intOf(ip, "total_quarantine_count");
            lines.add("");
            lines.add("== 物品预扫描 ==");
            lines.add("因目标存档缺少模组将被隔离的物品数量: " + total);
            if (ip.has("quarantine_candidates") && ip.getAsJsonArray("quarantine_candidates").size() > 0) {
                JsonArray arr = ip.getAsJsonArray("quarantine_candidates");
                for (int i = 0; i < Math.min(arr.size(), 6); i++) {
                    JsonObject c = arr.get(i).getAsJsonObject();
                    lines.add("· " + c.get("registry").getAsString() + " x" + c.get("count").getAsInt());
                }
                if (arr.size() > 6) {
                    lines.add("… 等共 " + arr.size() + " 类");
                }
            }
        }
    }

    @Override
    protected void init() {
        int cx = this.width / 2;
        addButton(cx - 150, this.height - 28, 140, 20, "继续",
                b -> flow.toInstallChoice(mc()));
        addButton(cx + 10, this.height - 28, 140, 20, "取消",
                b -> mc().setScreen(new XferMainScreen(flow)));
    }

    @Override
    public void render(GuiGraphics gfx, int mouseX, int mouseY, float partialTick) {
        this.renderBackground(gfx);
        drawTitle(gfx, "依赖树与冲突检测结果");
        int y = 30;
        for (String line : lines) {
            gfx.drawString(this.font, line, 20, y, 0xE0E0E0);
            y += this.font.lineHeight + 2;
            if (y > this.height - 60) {
                gfx.drawString(this.font, "…（继续显示省略）", 20, y, 0x808080);
                break;
            }
        }
        super.render(gfx, mouseX, mouseY, partialTick);
    }

    private static int intOf(JsonObject o, String key) {
        return o != null && o.has(key) ? o.get(key).getAsInt() : 0;
    }

    private static String strOr(JsonObject o, String key, String def) {
        if (o == null || !o.has(key)) {
            return def;
        }
        JsonElement el = o.get(key);
        if (el.isJsonArray()) {
            StringBuilder sb = new StringBuilder();
            for (JsonElement e : el.getAsJsonArray()) {
                if (sb.length() > 0) {
                    sb.append(", ");
                }
                sb.append(e.isJsonPrimitive() ? e.getAsString() : e.toString());
            }
            return sb.toString();
        }
        return el.getAsString();
    }
}
