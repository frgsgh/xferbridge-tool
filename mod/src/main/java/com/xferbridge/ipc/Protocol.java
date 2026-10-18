package com.xferbridge.ipc;

import com.google.gson.JsonArray;
import com.google.gson.JsonObject;
import com.xferbridge.XferConstants;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.nbt.CompoundTag;
import net.minecraft.nbt.ListTag;
import net.minecraft.nbt.NbtIo;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.world.entity.player.Inventory;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.item.ItemStack;

import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.util.Base64;
import java.util.zip.GZIPInputStream;
import java.util.zip.GZIPOutputStream;

/** 协议工具：载荷构建、NBT<->Base64、玩家清单。 */
public final class Protocol {

    private Protocol() {
    }

    // ------------------------------------------------------------ NBT
    public static String toGzipBase64(CompoundTag tag) {
        try {
            ByteArrayOutputStream bos = new ByteArrayOutputStream();
            try (GZIPOutputStream gz = new GZIPOutputStream(bos)) {
                NbtIo.writeCompressed(tag, gz);
            }
            return Base64.getEncoder().encodeToString(bos.toByteArray());
        } catch (IOException e) {
            throw new IllegalStateException("NBT 压缩失败", e);
        }
    }

    public static CompoundTag fromGzipBase64(String b64) {
        try {
            byte[] raw = Base64.getDecoder().decode(b64);
            try (GZIPInputStream gz = new GZIPInputStream(new ByteArrayInputStream(raw))) {
                return NbtIo.readCompressed(gz);
            }
        } catch (IOException e) {
            throw new IllegalStateException("NBT 解压失败", e);
        }
    }

    // ------------------------------------------------------------ 玩家清单
    /** 生成玩家物品清单（registry/count/mod_id），供外部工具预扫描。 */
    public static JsonArray playerItemManifest(Player player) {
        JsonArray arr = new JsonArray();
        Inventory inv = player.getInventory();
        for (ItemStack stack : inv.items) {
            addManifestItem(arr, stack);
        }
        for (ItemStack stack : inv.armor) {
            addManifestItem(arr, stack);
        }
        for (ItemStack stack : inv.offhand) {
            addManifestItem(arr, stack);
        }
        for (int i = 0; i < player.getEnderChestInventory().getContainerSize(); i++) {
            addManifestItem(arr, player.getEnderChestInventory().getItem(i));
        }
        return arr;
    }

    private static void addManifestItem(JsonArray arr, ItemStack stack) {
        if (stack == null || stack.isEmpty()) {
            return;
        }
        ResourceLocation key = BuiltInRegistries.ITEM.getKey(stack.getItem());
        JsonObject o = new JsonObject();
        o.addProperty("registry", key.toString());
        o.addProperty("count", stack.getCount());
        o.addProperty("mod_id", key.getNamespace());
        o.addProperty("display_name", stack.getHoverName().getString());
        arr.add(o);
    }

    // ------------------------------------------------------------ 物品序列化
    public static CompoundTag saveStack(Player player, ItemStack stack) {
        // 1.20.1: ItemStack.save 仅接受 CompoundTag（RegistryAccess 版是 1.20.2+）
        return stack.save(new CompoundTag());
    }

    public static ItemStack loadStack(Player player, CompoundTag tag) {
        return ItemStack.of(tag);
    }

    public static ListTag saveStacks(Player player, Iterable<ItemStack> stacks) {
        ListTag list = new ListTag();
        for (ItemStack s : stacks) {
            if (s != null && !s.isEmpty()) {
                list.add(saveStack(player, s));
            }
        }
        return list;
    }

    /** 写决策文件所需的基础信息。 */
    public static JsonObject transferContext(String transferId, Player player,
                                             String sourceSave, String targetSave) {
        JsonObject ctx = new JsonObject();
        ctx.addProperty("transfer_id", transferId);
        JsonObject p = new JsonObject();
        p.addProperty("name", player.getGameProfile().getName());
        p.addProperty("uuid", player.getGameProfile().getId().toString());
        ctx.add("player", p);
        ctx.addProperty("source_save", sourceSave);
        ctx.addProperty("target_save", targetSave);
        ctx.addProperty(XferConstants.KEY_FORMAT, XferConstants.FORMAT_PAYLOAD);
        return ctx;
    }
}
