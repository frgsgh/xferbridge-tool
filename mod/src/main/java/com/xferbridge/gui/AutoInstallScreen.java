package com.xferbridge.gui;

import com.google.gson.JsonArray;
import com.google.gson.JsonObject;
import com.xferbridge.transfer.TransferFlow;
import net.minecraft.client.gui.GuiGraphics;
import net.minecraft.client.gui.components.Checkbox;
import net.minecraft.client.gui.components.EditBox;
import net.minecraft.network.chat.Component;

import java.security.SecureRandom;

/**
 * 自动安装页：免责声明 + 「我已阅读并同意」勾选 + 随机验证码 + [开始自动下载]。
 * 勾选并输入正确验证码后按钮才可用。
 */
public class AutoInstallScreen extends XferScreen {
    private static final String DISCLAIMER =
            "自动安装免责声明\n"
            + "1. 本工具将从 Modrinth 官方 API 下载第三方模组文件。\n"
            + "2. 模组由第三方作者发布，工具仅负责下载与 SHA1/MD5 校验，\n"
            + "   不对模组内容、安全性及兼容性负责。\n"
            + "3. 安装缺失模组可能导致存档损坏、崩溃或数据丢失。\n"
            + "4. 执行前工具会自动备份目标存档与 config 文件夹。\n"
            + "5. 下载文件先进入 .staging 暂存区，校验通过后才生效。\n"
            + "6. 继续操作视为你已理解并接受以上风险。";

    private final JsonArray missing;
    private Checkbox agreeBox;
    private EditBox captchaInput;
    private String captcha;
    private net.minecraft.client.gui.components.Button startButton;

    public AutoInstallScreen(TransferFlow flow, JsonArray missing) {
        super(Component.literal("自动安装前置确认"), flow);
        this.missing = missing;
        this.captcha = randomCaptcha();
    }

    private static final char[] CHARS = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789".toCharArray();
    private static final SecureRandom RNG = new SecureRandom();

    private static String randomCaptcha() {
        StringBuilder sb = new StringBuilder(6);
        for (int i = 0; i < 6; i++) {
            sb.append(CHARS[RNG.nextInt(CHARS.length)]);
        }
        return sb.toString();
    }

    @Override
    protected void init() {
        int cx = this.width / 2;
        this.agreeBox = new Checkbox(cx - 160, this.height / 2 + 40, 340, 20,
                Component.literal("我已阅读并同意上述免责声明"), false, true);
        addRenderableWidget(this.agreeBox);

        drawText(cx - 160, this.height / 2 + 66,
                "请输入验证码:  " + captcha + "      （6 位字符，区分大小写）");
        this.captchaInput = new EditBox(this.font, cx - 160, this.height / 2 + 86, 200, 18,
                Component.literal("验证码"));
        this.captchaInput.setMaxLength(16);
        this.captchaInput.setResponder(s -> sync());
        addRenderableWidget(this.captchaInput);

        this.startButton = addButton(cx - 110, this.height - 30, 220, 22, "开始自动下载", b -> {
            if (validate()) {
                flow.startAutoDownload(mc());
            }
        });
        this.startButton.active = false;
        addButton(cx + 120, this.height - 30, 100, 22, "取消",
                b -> mc().setScreen(new XferMainScreen(flow)));
    }

    private void drawText(int x, int y, String text) {
        this.pendingLine = text;
        this.pendingX = x;
        this.pendingY = y;
    }

    private String pendingLine = "";
    private int pendingX, pendingY;

    private void sync() {
        this.startButton.active = this.agreeBox.selected()
                && captchaInput.getValue().trim().equalsIgnoreCase(this.captcha);
    }

    private boolean validate() {
        if (!this.agreeBox.selected()) {
            return false;
        }
        String in = this.captchaInput.getValue().trim();
        if (!in.equalsIgnoreCase(this.captcha)) {
            this.captcha = randomCaptcha();
            this.captchaInput.setValue("");
            this.pendingLine = "验证码错误，已刷新，请重新输入:  " + captcha;
            this.startButton.active = false;
            return false;
        }
        return true;
    }

    @Override
    public void render(GuiGraphics gfx, int mouseX, int mouseY, float partialTick) {
        this.renderBackground(gfx);
        drawTitle(gfx, "自动安装 — 请先阅读并确认（缺失 " + missing.size() + " 个模组）");
        int y = 32;
        for (String line : DISCLAIMER.split("\n")) {
            gfx.drawString(this.font, line, 24, y, 0xE0E0E0);
            y += this.font.lineHeight + 2;
        }
        if (!pendingLine.isEmpty()) {
            gfx.drawString(this.font, pendingLine, pendingX, pendingY, 0xFFD0A0);
        }
        super.render(gfx, mouseX, mouseY, partialTick);
    }
}
