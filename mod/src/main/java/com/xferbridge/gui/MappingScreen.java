package com.xferbridge.gui;

import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.xferbridge.mapping.ItemMappingTable;
import com.xferbridge.transfer.TransferFlow;
import net.minecraft.client.gui.GuiGraphics;
import net.minecraft.network.chat.Component;

import java.util.LinkedHashMap;
import java.util.Map;

/**
 * 物品映射页：
 * - 提示「有 X 件物品因目标存档缺少模组将暂存于隔离区/虚拟背包」；
 * - 对每个隔离候选提供「同名异 ID」手动替换输入框（预填映射表建议）。
 */
public class MappingScreen extends XferScreen {
    private final JsonObject itemPreview;
    private final ItemMappingTable mappingTable;
    private final Map<String, CandidateRow> rows = new LinkedHashMap<>();

    public MappingScreen(TransferFlow flow, JsonObject itemPreview, ItemMappingTable mappingTable) {
        super(Component.literal("物品映射确认"), flow);
        this.itemPreview = itemPreview;
        this.mappingTable = mappingTable;
    }

    @Override
    protected void init() {
        int cx = this.width / 2;
        int y = 60;
        if (itemPreview.has("quarantine_candidates")) {
            JsonArray arr = itemPreview.getAsJsonArray("quarantine_candidates");
            for (JsonElement el : arr) {
                JsonObject c = el.getAsJsonObject();
                String registry = c.get("registry").getAsString();
                int count = c.has("count") ? c.get("count").getAsInt() : 1;
                CandidateRow row = new CandidateRow(registry, count, y);
                row.init(this, cx - 220, y, 440);
                rows.put(registry, row);
                y += 24;
            }
        }
        int total = itemPreview.has("total_quarantine_count")
                ? itemPreview.get("total_quarantine_count").getAsInt() : 0;
        drawNotice("有 " + total + " 件物品因目标存档缺少模组将暂存于隔离区/虚拟背包，是否继续？\n"
                + "如果该物品在新版模组中改了 ID，可在输入框填写目标 registry（如 mod:item_new）。");
        addButton(cx - 120, this.height - 28, 240, 20, "继续（确认隔离与映射）",
                b -> flow.confirmAndApply(mc(), collectChoices()));
        addButton(cx + 130, this.height - 28, 100, 20, "取消",
                b -> mc().setScreen(new XferMainScreen(flow)));
    }

    private void drawNotice(String text) {
        this.notice = text;
    }

    private String notice = "";

    private Map<String, String> collectChoices() {
        Map<String, String> out = new LinkedHashMap<>();
        for (CandidateRow row : rows.values()) {
            String v = row.value();
            if (v != null && !v.isBlank() && !v.equals(row.registry)) {
                out.put(row.registry, v.trim());
                mappingTable.put(row.registry, v.trim());
            }
        }
        net.minecraft.client.Minecraft mc = mc();
        java.nio.file.Path cfgDir = com.xferbridge.transfer.TransferFlow.worldConfigDir(mc);
        mappingTable.saveLocal(cfgDir);
        return out;
    }

    @Override
    public void render(GuiGraphics gfx, int mouseX, int mouseY, float partialTick) {
        this.renderBackground(gfx);
        drawTitle(gfx, "物品映射确认 — 隔离区/虚拟背包");
        if (!notice.isEmpty()) {
            drawWrapped(gfx, notice, this.width / 2 - 220, 32, 440, 0xFFD0A0);
        }
        super.render(gfx, mouseX, mouseY, partialTick);
    }

    static class CandidateRow {
        final String registry;
        final int count;
        net.minecraft.client.gui.components.EditBox edit;

        CandidateRow(String registry, int count, int y) {
            this.registry = registry;
            this.count = count;
        }

        void init(MappingScreen screen, int x, int y, int width) {
            // 预填映射表建议（取第一个建议）
            String prefill = "";
            var sugg = screen.mappingTable.suggestions(registry);
            if (!sugg.isEmpty()) {
                prefill = sugg.get(0);
            }
            this.edit = new net.minecraft.client.gui.components.EditBox(
                    net.minecraft.client.Minecraft.getInstance().font, x + 190, y, 250, 16,
                    Component.literal("替换为"));
            this.edit.setMaxLength(128);
            this.edit.setValue(prefill);
            screen.addRenderableWidget(this.edit);
        }

        String value() {
            return this.edit == null ? "" : this.edit.getValue();
        }

        void render(MappingScreen screen, GuiGraphics gfx, int y) {
            gfx.drawString(net.minecraft.client.Minecraft.getInstance().font,
                    registry + "  x" + count, 30, y + 3, 0xE0E0E0);
            gfx.drawString(net.minecraft.client.Minecraft.getInstance().font,
                    "替换为(可选):", 30, y + 20, 0x808080);
        }
    }
}
