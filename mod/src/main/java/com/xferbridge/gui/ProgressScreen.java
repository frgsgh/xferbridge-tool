package com.xferbridge.gui;

import com.google.gson.JsonObject;
import com.xferbridge.transfer.TransferFlow;
import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.GuiGraphics;
import net.minecraft.network.chat.Component;

/** 进度页：显示阶段与百分比（由 IPC 事件驱动更新）。 */
public class ProgressScreen extends XferScreen {
    private String message;
    private int percent = -1;

    public ProgressScreen(TransferFlow flow, String message) {
        super(Component.literal("XferBridge 处理中…"), flow);
        this.message = message;
    }

    public static void show(Minecraft mc, TransferFlow flow, String title, String message) {
        mc.setScreen(new ProgressScreen(flow, message + "\n\n" + title));
    }

    /** 用事件更新进度。 */
    public void update(JsonObject evt) {
        if (evt == null) {
            return;
        }
        if (evt.has("message")) {
            this.message = evt.get("message").getAsString();
        }
        if (evt.has("percent")) {
            this.percent = evt.get("percent").getAsInt();
        }
    }

    @Override
    public void render(GuiGraphics gfx, int mouseX, int mouseY, float partialTick) {
        this.renderBackground(gfx);
        drawTitle(gfx, "XferBridge — 处理中");
        int cx = this.width / 2;
        int y = this.height / 3;
        drawWrapped(gfx, message, cx - 180, y, 360, 0xFFFFFF);
        if (percent >= 0) {
            int w = 320;
            gfx.fill(cx - w / 2, y + 90, cx + w / 2, y + 100, 0xFF555555);
            gfx.fill(cx - w / 2, y + 90, cx - w / 2 + (int) (w * percent / 100.0), y + 100, 0xFF3FA34D);
            gfx.drawCenteredString(this.font, percent + "%", cx, y + 106, 0xA0A0A0);
        } else {
            drawWrapped(gfx, "（等待外部工具响应…请确认 XferTool 已启动或已开启 IPC 守护）",
                    cx - 180, y + 90, 360, 0xA0A0A0);
        }
        super.render(gfx, mouseX, mouseY, partialTick);
    }
}
