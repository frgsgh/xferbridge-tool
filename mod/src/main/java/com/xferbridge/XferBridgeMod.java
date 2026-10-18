package com.xferbridge;

import com.mojang.blaze3d.platform.InputConstants;
import com.xferbridge.backup.BackupHooks;
import com.xferbridge.config.XferConfig;
import com.xferbridge.transfer.TransferFlow;
import net.minecraft.client.KeyMapping;
import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.screens.PauseScreen;
import net.minecraft.client.gui.screens.TitleScreen;
import net.minecraft.network.chat.Component;
import net.minecraftforge.client.event.RegisterKeyMappingsEvent;
import net.minecraftforge.client.event.ScreenEvent;
import net.minecraftforge.common.MinecraftForge;
import net.minecraftforge.common.ForgeConfigSpec;
import net.minecraftforge.event.TickEvent;
import net.minecraftforge.eventbus.api.SubscribeEvent;
import net.minecraftforge.fml.ModLoadingContext;
import net.minecraftforge.fml.common.Mod;
import net.minecraftforge.fml.config.ModConfig;
import net.minecraftforge.fml.event.lifecycle.FMLClientSetupEvent;
import net.minecraftforge.fml.javafmlmod.FMLJavaModLoadingContext;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/** XferBridge 模组主入口：注册配置、快捷键、事件与备份钩子。 */
@Mod(XferConstants.MOD_ID)
public final class XferBridgeMod {
    public static final Logger LOGGER = LoggerFactory.getLogger(XferConstants.MOD_ID);

    public static final KeyMapping OPEN_KEY = new KeyMapping(
            "key.xferbridge.open", InputConstants.Type.KEYSYM, InputConstants.KEY_F9,
            "key.categories.xferbridge");

    public XferBridgeMod() {
        ModLoadingContext.get().registerConfig(ModConfig.Type.CLIENT, XferConfig.SPEC);
        MinecraftForge.EVENT_BUS.register(this);
        MinecraftForge.EVENT_BUS.register(new BackupHooks());
        FMLJavaModLoadingContext.get().getModEventBus().addListener(this::clientSetup);
        FMLJavaModLoadingContext.get().getModEventBus().addListener(this::registerKeys);
        LOGGER.info("XferBridge 已加载");
    }

    private void clientSetup(FMLClientSetupEvent event) {
        // 1.20.1: 键位注册走 RegisterKeyMappingsEvent（ClientRegistry 已移除）
    }

    private void registerKeys(RegisterKeyMappingsEvent event) {
        event.register(OPEN_KEY);
    }

    private static String lastImportedWorld = "";

    /** 快捷键 + 流程轮询（每 tick）。 */
    @SubscribeEvent
    public void onClientTick(TickEvent.ClientTickEvent event) {
        if (event.phase != TickEvent.Phase.END) {
            return;
        }
        Minecraft mc = Minecraft.getInstance();
        if (mc.player == null || mc.level == null) {
            return;
        }
        while (OPEN_KEY.consumeClick()) {
            TransferFlow.INSTANCE.openMain(mc);
        }
        TransferFlow.INSTANCE.tick(mc);
        importQuarantineOnce(mc);
    }

    /** 进入世界时，把存档目录 xfer_quarantine/items_*.json 幂等导入隔离背包。 */
    private void importQuarantineOnce(Minecraft mc) {
        if (mc.getSingleplayerServer() == null) {
            return;
        }
        com.xferbridge.ipc.IpcChannel.WorldContext ctx = TransferFlow.worldContext(mc);
        if (ctx == null || ctx.path() == null) {
            return;
        }
        String key = ctx.path().toString();
        if (key.equals(lastImportedWorld)) {
            return;
        }
        lastImportedWorld = key;
        com.xferbridge.quarantine.QuarantineStore store =
                com.xferbridge.quarantine.QuarantineStore.of(mc.getSingleplayerServer());
        if (store != null) {
            int n = store.importFromWorldFolder(ctx.path());
            if (n > 0) {
                LOGGER.info("已从存档目录导入 {} 件隔离物品", n);
                if (mc.player != null) {
                    mc.player.displayClientMessage(
                            net.minecraft.network.chat.Component.literal(
                                    "XferBridge: 已导入 " + n + " 件隔离物品到虚拟背包"), false);
                }
            }
        }
    }

    /** 在主菜单与暂停菜单添加入口按钮。 */
    @SubscribeEvent
    public void onScreenInit(ScreenEvent.Init.Post event) {
        if (event.getScreen() instanceof TitleScreen) {
            event.addListener(net.minecraft.client.gui.components.Button.builder(
                            Component.translatable("screen.xferbridge.open"),
                            btn -> TransferFlow.INSTANCE.openMain(Minecraft.getInstance()))
                    .bounds(6, event.getScreen().height / 4 + 96, 150, 20)
                    .build());
        } else if (event.getScreen() instanceof PauseScreen) {
            event.addListener(net.minecraft.client.gui.components.Button.builder(
                            Component.translatable("screen.xferbridge.open"),
                            btn -> TransferFlow.INSTANCE.openMain(Minecraft.getInstance()))
                    .bounds(event.getScreen().width / 2 - 102, event.getScreen().height / 4 + 72, 204, 20)
                    .build());
        }
    }
}
