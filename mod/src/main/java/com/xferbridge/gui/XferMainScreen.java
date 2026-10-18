package com.xferbridge.gui;

import com.xferbridge.transfer.TransferFlow;
import net.minecraft.client.gui.GuiGraphics;
import net.minecraft.network.chat.Component;

/** 主界面：入口按钮与帮助信息。 */
public class XferMainScreen extends XferScreen {
    public XferMainScreen(TransferFlow flow) {
        super(Component.literal("XferBridge 跨存档迁移"), flow);
    }

    @Override
    protected void init() {
        int cx = this.width / 2;
        int y = this.height / 4;
        addButton(cx - 110, y, 220, 24, "开始跨存档迁移",
                b -> flow.startSelect(mc()));
        addButton(cx - 110, y + 34, 220, 24, "隔离背包（虚拟背包）",
                b -> flow.openQuarantine(mc()));
        addButton(cx - 110, y + 68, 220, 24, "关闭", b -> mc().setScreen(null));
    }

    @Override
    public void render(GuiGraphics gfx, int mouseX, int mouseY, float partialTick) {
        this.renderBackground(gfx);
        drawTitle(gfx, "XferBridge — 角色属性与物品跨存档迁移");
        String help = "1. 请确保外部工具 XferTool 已启动（或开启 IPC 守护）\n"
                + "2. 选择目标存档后，工具会进行模组依赖树与冲突检测\n"
                + "3. 缺失模组可引导/自动安装（.staging + 哈希校验）\n"
                + "4. 配置文件可逐项选择，默认保留目标存档配置\n"
                + "5. 缺失模组的物品进入隔离区/虚拟背包，可导出/释放\n"
                + "6. 所有操作前自动备份，可在外部工具一键回滚";
        drawWrapped(gfx, help, this.width / 2 - 160, this.height / 4 + 110, 320, 0xA0A0A0);
        super.render(gfx, mouseX, mouseY, partialTick);
    }
}
