package com.xferbridge.gui;

import com.xferbridge.transfer.TransferFlow;
import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.GuiGraphics;
import net.minecraft.network.chat.Component;

/** 自动下载完成后的重启确认页。 */
public class RestartPromptScreen extends XferScreen {
    public RestartPromptScreen(TransferFlow flow) {
        super(Component.literal("重启确认"), flow);
    }

    @Override
    protected void init() {
        int cx = this.width / 2;
        addButton(cx - 160, this.height - 34, 150, 22, "现在重启",
                b -> Minecraft.getInstance().stop());
        addButton(cx + 10, this.height - 34, 150, 22, "稍后（继续迁移）",
                b -> flow.toConfigDiff(mc()));
    }

    @Override
    public void render(GuiGraphics gfx, int mouseX, int mouseY, float partialTick) {
        this.renderBackground(gfx);
        drawTitle(gfx, "缺失模组已下载完毕");
        int y = this.height / 2 - 40;
        drawWrapped(gfx, "缺失模组已下载完毕，需要重启游戏才能生效，是否现在重启？",
                60, y, this.width - 120, 0xFFFFFF);
        drawWrapped(gfx, "模组已暂存于目标存档 mods/.staging，SHA1/MD5 校验通过。\n"
                        + "「稍后」将继续执行跨存档迁移，重启可在迁移完成后进行。",
                60, y + 60, this.width - 120, 0xA0A0A0);
        super.render(gfx, mouseX, mouseY, partialTick);
    }
}
