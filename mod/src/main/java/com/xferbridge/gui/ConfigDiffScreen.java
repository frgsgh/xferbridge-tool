package com.xferbridge.gui;

import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.xferbridge.transfer.TransferFlow;
import net.minecraft.client.gui.GuiGraphics;
import net.minecraft.client.gui.components.ObjectSelectionList;
import net.minecraft.network.chat.Component;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * 配置 Diff 页：仅列出「共存模组」的配置文件。
 * 每行可勾选「用源覆盖」（默认不勾选 = 保留目标存档配置）。
 */
public class ConfigDiffScreen extends XferScreen {
    private final JsonObject configDiff;
    private final List<Row> rows = new ArrayList<>();
    private DiffList list;

    public ConfigDiffScreen(TransferFlow flow, JsonObject configDiff) {
        super(Component.literal("配置文件对比"), flow);
        this.configDiff = configDiff;
        collectRows();
    }

    private void collectRows() {
        if (configDiff.has("coexist_diff")) {
            for (JsonElement el : configDiff.getAsJsonArray("coexist_diff")) {
                JsonObject o = el.getAsJsonObject();
                String file = o.has("file") ? o.get("file").getAsString() : "?";
                String mod = o.has("mod_id") ? o.get("mod_id").getAsString() : "?";
                String status = o.has("status") ? o.get("status").getAsString() : "?";
                String preview = o.has("diff_preview") ? o.getAsJsonArray("diff_preview").toString() : "";
                rows.add(new Row(mod, file, status, preview));
            }
        }
    }

    @Override
    protected void init() {
        int cx = this.width / 2;
        this.list = new DiffList(mc(), this, this.height - 92);
        this.list.setLeftPos(cx - 230);
        addRenderableWidget(this.list);
        for (Row r : rows) {
            this.list.addEntry(new DiffList.Entry(r));
        }
        addButton(cx - 120, this.height - 26, 240, 20, "确认选择（默认保留目标配置）",
                b -> flow.confirmConfig(mc(), collectChoices()));
        addButton(cx + 130, this.height - 26, 100, 20, "取消",
                b -> mc().setScreen(new XferMainScreen(flow)));
    }

    private JsonObject collectChoices() {
        JsonObject choices = new JsonObject();
        for (DiffList.Entry e : this.list.children()) {
            choices.addProperty(e.row.file,
                    e.overwrite.selected() ? "use_source" : "keep_target");
        }
        return choices;
    }

    @Override
    public void render(GuiGraphics gfx, int mouseX, int mouseY, float partialTick) {
        this.renderBackground(gfx);
        drawTitle(gfx, "配置文件对比 — 仅列共存模组（缺失模组配置将进隔离区）");
        drawWrapped(gfx, "默认建议保留目标存档的配置，除非你明确知道自己在做什么。"
                        + "替换前外部工具会自动打包备份目标 config 文件夹。",
                this.width / 2 - 230, this.height - 70, 460, 0x909090);
        super.render(gfx, mouseX, mouseY, partialTick);
    }

    record Row(String mod, String file, String status, String preview) {
    }

    static class DiffList extends ObjectSelectionList<DiffList.Entry> {
        public DiffList(net.minecraft.client.Minecraft mc, ConfigDiffScreen screen, int height) {
            super(mc, 460, height, 32, height - 28, 26);
        }

        @Override
        public int getRowWidth() {
            return 440;
        }

        @Override
        public int addEntry(Entry e) {
            return super.addEntry(e);
        }

        static class Entry extends ObjectSelectionList.Entry<Entry> {
            final Row row;
            final net.minecraft.client.gui.components.Checkbox overwrite;

            Entry(Row row) {
                this.row = row;
                // 1.20.1: Checkbox 无 builder，直接构造
                this.overwrite = new net.minecraft.client.gui.components.Checkbox(
                        0, 0, 66, 16, Component.literal("用源覆盖"), false);
            }

            @Override
            public void render(GuiGraphics gfx, int index, int top, int left, int width,
                               int height, int mouseX, int mouseY, boolean hovered, float partialTick) {
                String statusColor = switch (row.status()) {
                    case "identical" -> "0xFFFFFF";
                    case "changed" -> "0xFFD080";
                    default -> "0x80C0FF";
                };
                gfx.drawString(net.minecraft.client.Minecraft.getInstance().font,
                        row.file() + "  [" + row.mod() + "]  (" + row.status() + ")",
                        left + 6, top + 2, 0xE0E0E0);
                String note = switch (row.status()) {
                    case "identical" -> "内容一致";
                    case "changed" -> "两边不同，默认保留目标";
                    case "only_source" -> "仅源存档有";
                    case "only_target" -> "仅目标存档有";
                    default -> row.status();
                };
                gfx.drawString(net.minecraft.client.Minecraft.getInstance().font, note,
                        left + 6, top + 13, 0xA0A0A0);
                int bx = left + width - 70;
                this.overwrite.setPosition(bx, top + 2);
                this.overwrite.setWidth(66);
                this.overwrite.render(gfx, mouseX, mouseY, partialTick);
            }

            @Override
            public boolean mouseClicked(double mx, double my, int button) {
                if (this.overwrite.mouseClicked(mx, my, button)) {
                    return true;
                }
                return super.mouseClicked(mx, my, button);
            }

            @Override
            public Component getNarration() {
                return Component.literal(row.file());
            }
        }
    }
}
