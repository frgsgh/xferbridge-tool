package com.xferbridge.gui;

import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.xferbridge.transfer.TransferFlow;
import net.minecraft.client.gui.GuiGraphics;
import net.minecraft.network.chat.Component;

/** 缺失模组安装选择页：否 → 停止；是 → 备份后选择 引导/自动 安装。 */
public class MissingModsScreen extends XferScreen {
    private final JsonArray missing;
    private final boolean targetMissingXb;
    private boolean backupRequested = false;

    public MissingModsScreen(TransferFlow flow, JsonArray missing, boolean targetMissingXb) {
        super(Component.literal("缺失模组处理"), flow);
        this.missing = missing;
        this.targetMissingXb = targetMissingXb;
    }

    @Override
    protected void init() {
        int cx = this.width / 2;
        int y = this.height - 64;
        clearWidgets();
        if (!backupRequested) {
            addButton(cx - 210, y, 200, 22, "否，停止跨越并返回上一步",
                    b -> flow.cancelTransfer(mc()));
            addButton(cx + 10, y, 200, 22, "是，先备份目标存档再继续",
                    b -> {
                        backupRequested = true;
                        flow.onMissingInstallYes(mc());
                        init();
                    });
        } else {
            drawWrappedAt(y - 40, "目标存档已请求全量备份。请选择缺失模组的安装方式：", cx - 200, 400, 0xFFFFFF);
            addButton(cx - 210, y, 200, 22, "引导安装（列出缺失模组及下载链接）",
                    b -> flow.guidedInstall(mc()));
            addButton(cx + 10, y, 200, 22, "自动安装（免责声明+验证码后自动下载）",
                    b -> flow.autoInstall(mc()));
        }
    }

    private void drawWrappedAt(int y, String text, int x, int w, int color) {
        this.pendingText = text;
        this.pendingX = x;
        this.pendingW = w;
        this.pendingY = y;
        this.pendingColor = color;
    }

    private String pendingText = "";
    private int pendingX, pendingW, pendingY;
    private int pendingColor = 0xFFFFFF;

    @Override
    public void render(GuiGraphics gfx, int mouseX, int mouseY, float partialTick) {
        this.renderBackground(gfx);
        drawTitle(gfx, "检测到目标存档缺少模组");
        int y = 32;
        if (targetMissingXb) {
            gfx.drawString(this.font, "· 目标存档没有安装 XferBridge 模组本体", 24, y, 0xFFE0E0);
            y += 14;
        }
        gfx.drawString(this.font, "以下 " + missing.size() + " 个模组缺失（前置/依赖）：", 24, y, 0xE0E0E0);
        y += 16;
        for (int i = 0; i < Math.min(missing.size(), 8); i++) {
            JsonObject m = missing.get(i).getAsJsonObject();
            String name = strOr(m, "display_name", strOr(m, "mod_id", "?"));
            String ver = strOr(m, "version", "");
            gfx.drawString(this.font, "· " + name + (ver.isEmpty() ? "" : " v" + ver)
                            + "（被 " + strOr(m, "required_by", "-") + " 需要）",
                    40, y, 0xC0C0C0);
            y += 14;
        }
        if (missing.size() > 8) {
            gfx.drawString(this.font, "… 共 " + missing.size() + " 个", 40, y, 0x808080);
        }
        if (!pendingText.isEmpty()) {
            drawWrapped(gfx, pendingText, pendingX, pendingY, pendingW, pendingColor);
        }
        super.render(gfx, mouseX, mouseY, partialTick);
    }

    private static String strOr(JsonObject o, String key, String def) {
        return o != null && o.has(key) ? o.get(key).getAsString() : def;
    }
}
