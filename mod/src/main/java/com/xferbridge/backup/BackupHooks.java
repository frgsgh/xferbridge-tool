package com.xferbridge.backup;

import com.google.gson.JsonObject;
import com.xferbridge.config.XferConfig;
import com.xferbridge.ipc.IpcChannel;
import com.xferbridge.transfer.TransferFlow;
import net.minecraft.client.Minecraft;
import net.minecraftforge.event.entity.player.PlayerEvent;
import net.minecraftforge.eventbus.api.SubscribeEvent;

/**
 * 备份触发器：
 * - 玩家退出世界（PlayerLoggedOutEvent）→ 增量备份
 * - 玩家保存/自动保存（PlayerEvent.SaveToFile）→ 增量备份（节流）
 * - 迁移执行前 → 由 TransferFlow 发起全量备份
 * 备份动作由外部工具执行（写 IPC 请求）。
 */
public final class BackupHooks {
    private final IpcChannel channel = new IpcChannel();
    private long lastSaveBackupMs = 0;

    @SubscribeEvent
    public void onPlayerLoggedOut(PlayerEvent.PlayerLoggedOutEvent event) {
        if (event.getEntity().level().isClientSide) {
            return;
        }
        if (!XferConfig.BACKUP_ON_LOGOUT.get()) {
            return;
        }
        requestBackup("trigger_logout", "incremental");
    }

    @SubscribeEvent
    public void onPlayerSaved(PlayerEvent.SaveToFile event) {
        if (event.getEntity().level().isClientSide) {
            return;
        }
        if (!XferConfig.BACKUP_ON_SAVE.get()) {
            return;
        }
        long now = System.currentTimeMillis();
        int throttle = XferConfig.BACKUP_THROTTLE_SEC.get() * 1000;
        if (now - lastSaveBackupMs < throttle) {
            return;
        }
        lastSaveBackupMs = now;
        requestBackup("trigger_save", "incremental");
    }

    private void requestBackup(String trigger, String kind) {
        Minecraft mc = Minecraft.getInstance();
        IpcChannel.WorldContext ctx = TransferFlow.worldContext(mc);
        JsonObject payload = new JsonObject();
        payload.addProperty("kind", kind);
        payload.addProperty("label", trigger);
        channel.writeRequestWithWorld("backup", payload, ctx);
    }
}
