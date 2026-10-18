package com.xferbridge.gui;

import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.xferbridge.transfer.TransferFlow;
import net.minecraft.client.gui.GuiGraphics;
import net.minecraft.client.gui.components.ObjectSelectionList;
import net.minecraft.network.chat.Component;

import java.util.ArrayList;
import java.util.List;

/** 存档选择页：列出外部工具扫描出的全部存档。 */
public class SaveSelectScreen extends XferScreen {
    private SaveList list;

    public SaveSelectScreen(TransferFlow flow) {
        super(Component.literal("选择目标存档"), flow);
    }

    @Override
    protected void init() {
        int cx = this.width / 2;
        int top = 32;
        this.list = new SaveList(mc(), this, this.height - top - 60);
        this.list.setLeftPos(cx - 220);
        addRenderableWidget(this.list);
        loadSaves();
        addButton(cx - 220, this.height - 26, 140, 20, "重新扫描（读取索引）",
                b -> loadSaves());
        addButton(cx - 70, this.height - 26, 140, 20, "迁移到选中的存档",
                b -> {
                    SaveList.Entry e = this.list.getSelected();
                    if (e != null) {
                        flow.onTargetSelected(mc(), e.saveId);
                    }
                });
        addButton(cx + 80, this.height - 26, 140, 20, "取消",
                b -> mc().setScreen(new XferMainScreen(flow)));
    }

    private void loadSaves() {
        this.list.clear();
        JsonArray saves = flow.channel().savesArray();
        for (JsonElement el : saves) {
            JsonObject s = el.getAsJsonObject();
            String name = s.has("display_name") ? s.get("display_name").getAsString() : s.get("name").getAsString();
            String version = s.has("version") ? s.get("version").getAsString() : "?";
            String launcher = s.has("launcher") ? s.get("launcher").getAsString() : "?";
            String mods = s.has("mod_count") ? String.valueOf(s.get("mod_count").getAsInt()) : "0";
            String xb = s.has("has_xferbridge") && s.get("has_xferbridge").getAsBoolean() ? "是" : "否";
            String path = s.has("path") ? s.get("path").getAsString() : "";
            this.list.addEntry(new SaveList.Entry(s.get("id").getAsString(), name, version, launcher, mods, xb, path, mc().font));
        }
    }

    @Override
    public void render(GuiGraphics gfx, int mouseX, int mouseY, float partialTick) {
        this.renderBackground(gfx);
        drawTitle(gfx, "选择目标存档（源存档 = 当前世界）");
        super.render(gfx, mouseX, mouseY, partialTick);
    }

    static class SaveList extends ObjectSelectionList<SaveList.Entry> {
        private final SaveSelectScreen screen;

        public SaveList(net.minecraft.client.Minecraft mc, SaveSelectScreen screen, int height) {
            super(mc, 440, height, 32, height - 28, 20);
            this.screen = screen;
        }

        public void clear() {
            this.clearEntries();
        }

        @Override
        public int getRowWidth() {
            return 420;
        }

        /** 公开入口（基类 addEntry 为 protected，且需从外部类调用）。 */
        @Override
        public int addEntry(Entry e) {
            return super.addEntry(e);
        }

        @Override
        public boolean mouseClicked(double mx, double my, int button) {
            if (super.mouseClicked(mx, my, button)) {
                SaveList.Entry e = getSelected();
                if (e != null && button == 0) {
                    screen.flow.onTargetSelected(screen.mc(), e.saveId);
                }
                return true;
            }
            return false;
        }

        static class Entry extends ObjectSelectionList.Entry<Entry> {
            final String saveId;
            final String name;
            final String version;
            final String launcher;
            final String mods;
            final String xb;
            final String path;

            Entry(String saveId, String name, String version, String launcher,
                  String mods, String xb, String path, net.minecraft.client.gui.Font font) {
                this.saveId = saveId;
                this.name = name;
                this.version = version;
                this.launcher = launcher;
                this.mods = mods;
                this.xb = xb;
                this.path = path;
                this.font = font;
            }

            final net.minecraft.client.gui.Font font;

            @Override
            public void render(GuiGraphics gfx, int index, int top, int left, int width,
                               int height, int mouseX, int mouseY, boolean hovered, float partialTick) {
                gfx.drawString(this.font, name + "  [" + launcher + "]", left + 6, top + 2, 0xFFFFFF);
                gfx.drawString(this.font, "版本 " + version + " · 模组 " + mods
                                + " · XferBridge:" + xb,
                        left + 6, top + 12, 0xA0A0A0);
            }

            @Override
            public Component getNarration() {
                return Component.literal(name);
            }
        }
    }
}
