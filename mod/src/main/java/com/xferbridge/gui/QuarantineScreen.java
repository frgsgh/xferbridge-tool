package com.xferbridge.gui;

import com.google.gson.JsonObject;
import com.xferbridge.quarantine.QuarantineItem;
import com.xferbridge.quarantine.QuarantineStore;
import com.xferbridge.transfer.TransferFlow;
import net.minecraft.client.gui.GuiGraphics;
import net.minecraft.client.gui.components.ObjectSelectionList;
import net.minecraft.network.chat.Component;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.item.ItemStack;

import java.util.List;

/** 隔离背包（虚拟背包）：查看/放回/导出隔离物品。 */
public class QuarantineScreen extends XferScreen {
    private final QuarantineStore store;
    private ItemList list;

    public QuarantineScreen(TransferFlow flow, QuarantineStore store) {
        super(Component.literal("隔离背包 / 虚拟背包"), flow);
        this.store = store;
    }

    @Override
    protected void init() {
        int cx = this.width / 2;
        this.list = new ItemList(mc(), this, this.height - 92);
        this.list.setLeftPos(cx - 230);
        addRenderableWidget(this.list);
        refresh();
        addButton(cx - 230, this.height - 26, 148, 20, "放回选中物品",
                b -> giveBack(getSelected()));
        addButton(cx - 76, this.height - 26, 148, 20, "全部放回",
                b -> giveBackAll());
        addButton(cx + 78, this.height - 26, 150, 20, "导出（zip / Base64）",
                b -> requestExport());
        addButton(cx + 234, this.height - 26, 100, 20, "关闭",
                b -> mc().setScreen(new XferMainScreen(flow)));
    }

    private void refresh() {
        this.list.reset();
        List<QuarantineItem> items = store == null ? List.of() : store.items();
        for (QuarantineItem item : items) {
            this.list.addEntry(new ItemList.Entry(item));
        }
    }

    private QuarantineItem getSelected() {
        ItemList.Entry e = this.list.getSelected();
        return e == null ? null : e.item;
    }

    private void giveBack(QuarantineItem item) {
        if (item == null || store == null) {
            return;
        }
        Player player = mc().player;
        if (player == null) {
            return;
        }
        ItemStack stack = item.toStack(player);
        int idx = store.items().indexOf(item);
        if (!stack.isEmpty() && idx >= 0) {
            if (!player.getInventory().add(stack)) {
                player.drop(stack, false);
            }
            store.release(idx);
            mc().player.displayClientMessage(
                    Component.literal("已放回 " + item.displayName() + " x" + item.count()), true);
        } else {
            mc().player.displayClientMessage(
                    Component.literal("物品无法还原（对应模组可能仍未安装）"), true);
        }
        refresh();
    }

    private void giveBackAll() {
        if (store == null) {
            return;
        }
        List<QuarantineItem> all = store.releaseAll();
        Player player = mc().player;
        int ok = 0;
        for (QuarantineItem item : all) {
            if (player == null) {
                break;
            }
            ItemStack stack = item.toStack(player);
            if (!stack.isEmpty()) {
                if (!player.getInventory().add(stack)) {
                    player.drop(stack, false);
                }
                ok++;
            }
        }
        if (player != null) {
            player.displayClientMessage(Component.literal("已尝试放回 " + ok + " / " + all.size() + " 件"), true);
        }
        refresh();
    }

    /** 导出请求交给外部工具（zip 或 Base64 两种格式）。 */
    private void requestExport() {
        JsonObject payload = new JsonObject();
        payload.addProperty("save_id", flow.currentSaveId(mc()));
        payload.addProperty("format", "zip");
        flow.channel().writeRequestWithWorld("export_quarantine", payload,
                TransferFlow.worldContext(mc()));
        if (mc().player != null) {
            mc().player.displayClientMessage(
                    Component.literal("已请求外部工具导出隔离区（zip），也可在工具中导出 Base64"), true);
        }
    }

    @Override
    public void render(GuiGraphics gfx, int mouseX, int mouseY, float partialTick) {
        this.renderBackground(gfx);
        drawTitle(gfx, "隔离背包（虚拟背包）— 共 " + (store == null ? 0 : store.size()) + " 件");
        drawWrapped(gfx, "这些物品因目标存档当时缺少对应模组而被暂存。安装模组后可放回。",
                this.width / 2 - 230, this.height - 68, 460, 0x909090);
        super.render(gfx, mouseX, mouseY, partialTick);
    }

    static class ItemList extends ObjectSelectionList<ItemList.Entry> {
        public ItemList(net.minecraft.client.Minecraft mc, QuarantineScreen screen, int height) {
            super(mc, 460, height, 32, height - 28, 20);
        }

        @Override
        public int getRowWidth() {
            return 440;
        }

        /** 清空列表（基类 clearEntries 为 protected，需对外暴露）。 */
        public void reset() {
            super.clearEntries();
        }

        @Override
        public int addEntry(Entry e) {
            return super.addEntry(e);
        }

        static class Entry extends ObjectSelectionList.Entry<Entry> {
            final QuarantineItem item;

            Entry(QuarantineItem item) {
                this.item = item;
            }

            @Override
            public void render(GuiGraphics gfx, int index, int top, int left, int width,
                               int height, int mouseX, int mouseY, boolean hovered, float partialTick) {
                gfx.drawString(net.minecraft.client.Minecraft.getInstance().font,
                        item.displayName() + " x" + item.count(),
                        left + 6, top + 2, 0xFFFFFF);
                gfx.drawString(net.minecraft.client.Minecraft.getInstance().font,
                        item.registry() + "  来自 " + item.sourceSave() + "（" + item.transferId() + "）",
                        left + 6, top + 12, 0xA0A0A0);
            }

            @Override
            public Component getNarration() {
                return Component.literal(item.displayName());
            }
        }
    }
}
