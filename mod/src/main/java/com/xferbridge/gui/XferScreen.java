package com.xferbridge.gui;

import com.xferbridge.transfer.TransferFlow;
import net.minecraft.client.gui.GuiGraphics;
import net.minecraft.network.chat.Component;

/** 所有 XferBridge 界面的基类：统一标题渲染与按钮辅助。 */
public abstract class XferScreen extends Screen {
    protected final TransferFlow flow;

    protected XferScreen(Component title, TransferFlow flow) {
        super(title);
        this.flow = flow;
    }

    protected Button addButton(int x, int y, int w, int h, String label, Button.OnPress onPress) {
        return addRenderableWidget(Button.builder(Component.literal(label), onPress)
                .bounds(x, y, w, h).build());
    }

    protected void drawTitle(GuiGraphics gfx, String text) {
        gfx.drawCenteredString(this.font, text, this.width / 2, 12, 0xFFFFFF);
    }

    protected void drawWrapped(GuiGraphics gfx, String text, int x, int y, int maxWidth, int color) {
        for (var line : this.font.split(Component.literal(text), maxWidth)) {
            gfx.drawString(this.font, line, x, y, color);
            y += this.font.lineHeight + 2;
        }
    }

    protected static Minecraft mc() {
        return Minecraft.getInstance();
    }

    @Override
    public boolean isPauseScreen() {
        return false;
    }
}
