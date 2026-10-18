package com.xferbridge.gui;

import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.xferbridge.transfer.TransferFlow;
import net.minecraft.Util;
import net.minecraft.client.gui.GuiGraphics;
import net.minecraft.client.gui.components.ObjectSelectionList;
import net.minecraft.network.chat.Component;

import java.net.URI;
import java.util.ArrayList;
import java.util.List;

/** 引导安装页：缺失模组列表 + 下载链接（浏览器打开）。 */
public class GuidedInstallScreen extends XferScreen {
    private final JsonArray missing;
    private ModList list;

    public GuidedInstallScreen(TransferFlow flow, JsonArray missing) {
        super(Component.literal("引导安装 — 缺失模组清单"), flow);
        this.missing = missing;
    }

    @Override
    protected void init() {
        int cx = this.width / 2;
        this.list = new ModList(mc(), this, this.height - 92);
        this.list.setLeftPos(cx - 220);
        addRenderableWidget(this.list);
        for (JsonElement el : missing) {
            JsonObject m = el.getAsJsonObject();
            String name = m.has("display_name") ? m.get("display_name").getAsString()
                    : (m.has("mod_id") ? m.get("mod_id").getAsString() : "?");
            String ver = m.has("version") ? m.get("version").getAsString() : "";
            String links = collectLinks(m);
            this.list.addEntry(new ModList.Entry(name + " " + ver, links));
        }
        addButton(cx - 110, this.height - 26, 220, 20, "打开选中模组的下载链接",
                b -> openSelected());
        addButton(cx + 120, this.height - 26, 100, 20, "下一步",
                b -> flow.toConfigDiff(mc()));
    }

    private void openSelected() {
        ModList.Entry e = this.list.getSelected();
        if (e == null || e.links.isEmpty()) {
            return;
        }
        String link = e.links.split(" ")[0];
        try {
            Util.getPlatform().openUri(URI.create(link));
        } catch (Exception ex) {
            com.xferbridge.XferBridgeMod.LOGGER.info("打开链接失败: {}", ex.getMessage());
        }
    }

    private static String collectLinks(JsonObject m) {
        StringBuilder sb = new StringBuilder();
        if (m.has("downloads")) {
            for (JsonElement dl : m.getAsJsonArray("downloads")) {
                JsonObject d = dl.getAsJsonObject();
                if (d.has("url")) {
                    if (sb.length() > 0) {
                        sb.append(" ");
                    }
                    sb.append(d.get("url").getAsString());
                }
            }
        }
        return sb.toString();
    }

    @Override
    public void render(GuiGraphics gfx, int mouseX, int mouseY, float partialTick) {
        this.renderBackground(gfx);
        drawTitle(gfx, "引导安装 — 缺失模组（共 " + missing.size() + " 个）");
        drawWrapped(gfx, "提示：在浏览器中打开链接下载后，把 jar 放入目标存档 mods/ 目录即可。",
                this.width / 2 - 220, this.height - 70, 440, 0x909090);
        super.render(gfx, mouseX, mouseY, partialTick);
    }

    static class ModList extends ObjectSelectionList<ModList.Entry> {
        public ModList(net.minecraft.client.Minecraft mc, GuidedInstallScreen screen, int height) {
            super(mc, 440, height, 32, height - 28, 20);
        }

        @Override
        public int getRowWidth() {
            return 420;
        }

        @Override
        public int addEntry(Entry e) {
            return super.addEntry(e);
        }

        static class Entry extends ObjectSelectionList.Entry<Entry> {
            final String name;
            final String links;

            Entry(String name, String links) {
                this.name = name;
                this.links = links;
            }

            @Override
            public void render(GuiGraphics gfx, int index, int top, int left, int width,
                               int height, int mouseX, int mouseY, boolean hovered, float partialTick) {
                gfx.drawString(net.minecraft.client.Minecraft.getInstance().font, name,
                        left + 6, top + 3, 0xFFFFFF);
                gfx.drawString(net.minecraft.client.Minecraft.getInstance().font,
                        links.isEmpty() ? "（无自动下载源，请手动搜索）" : links,
                        left + 6, top + 13, 0x8AB8FF);
            }

            @Override
            public Component getNarration() {
                return Component.literal(name);
            }
        }
    }
}
