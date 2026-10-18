package com.xferbridge.quarantine;

import com.google.gson.JsonObject;
import com.xferbridge.ipc.Protocol;
import net.minecraft.nbt.CompoundTag;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.item.ItemStack;

/**
 * 隔离物品条目：来源存档、来源模组、registry、数量、NBT 载荷。
 * 支持 JSON（工具写入）与 NBT（CustomSavedData 持久化）两种形态。
 */
public class QuarantineItem {
    private String registry;
    private String modId;
    private String displayName;
    private int count;
    private String nbtBase64;
    private String sourceSave;
    private String transferId;

    public QuarantineItem() {
    }

    public QuarantineItem(String registry, String modId, String displayName, int count,
                          String nbtBase64, String sourceSave, String transferId) {
        this.registry = registry;
        this.modId = modId;
        this.displayName = displayName;
        this.count = count;
        this.nbtBase64 = nbtBase64;
        this.sourceSave = sourceSave;
        this.transferId = transferId;
    }

    public static QuarantineItem fromJson(JsonObject o) {
        QuarantineItem item = new QuarantineItem();
        item.registry = str(o, "registry");
        item.modId = str(o, "mod_id");
        item.displayName = str(o, "display_name");
        item.count = o.has("count") ? o.get("count").getAsInt() : 1;
        item.nbtBase64 = str(o, "nbt_base64");
        item.sourceSave = str(o, "source_save");
        item.transferId = str(o, "transfer_id");
        return item;
    }

    public JsonObject toJson() {
        JsonObject o = new JsonObject();
        o.addProperty("registry", registry);
        o.addProperty("mod_id", modId);
        o.addProperty("display_name", displayName);
        o.addProperty("count", count);
        o.addProperty("nbt_base64", nbtBase64);
        o.addProperty("source_save", sourceSave);
        o.addProperty("transfer_id", transferId);
        return o;
    }

    public static QuarantineItem fromNbt(CompoundTag tag) {
        QuarantineItem item = new QuarantineItem();
        item.registry = tag.getString("registry");
        item.modId = tag.getString("mod_id");
        item.displayName = tag.getString("display_name");
        item.count = tag.getInt("count");
        item.nbtBase64 = tag.getString("nbt_base64");
        item.sourceSave = tag.getString("source_save");
        item.transferId = tag.getString("transfer_id");
        return item;
    }

    public CompoundTag toNbt() {
        CompoundTag tag = new CompoundTag();
        tag.putString("registry", registry == null ? "" : registry);
        tag.putString("mod_id", modId == null ? "" : modId);
        tag.putString("display_name", displayName == null ? registry : displayName);
        tag.putInt("count", count);
        tag.putString("nbt_base64", nbtBase64 == null ? "" : nbtBase64);
        tag.putString("source_save", sourceSave == null ? "" : sourceSave);
        tag.putString("transfer_id", transferId == null ? "" : transferId);
        return tag;
    }

    /** 还原为 ItemStack（按当前存档 registry 解析；缺失物品时返回空栈）。 */
    public ItemStack toStack(Player player) {
        if (nbtBase64 == null || nbtBase64.isEmpty()) {
            return ItemStack.EMPTY;
        }
        try {
            CompoundTag tag = Protocol.fromGzipBase64(nbtBase64);
            ItemStack stack = Protocol.loadStack(player, tag);
            return stack.isEmpty() ? ItemStack.EMPTY : stack;
        } catch (Exception e) {
            return ItemStack.EMPTY;
        }
    }

    private static String str(JsonObject o, String key) {
        return o.has(key) ? o.get(key).getAsString() : "";
    }

    public String registry() {
        return registry;
    }

    public String modId() {
        return modId;
    }

    public String displayName() {
        return displayName;
    }

    public int count() {
        return count;
    }

    public String sourceSave() {
        return sourceSave;
    }

    public String transferId() {
        return transferId;
    }

    @Override
    public String toString() {
        return displayName + " x" + count + " (" + registry + ")";
    }
}
