package com.xferbridge.transfer;

import com.google.gson.JsonArray;
import com.google.gson.JsonObject;
import com.xferbridge.XferConstants;
import com.xferbridge.ipc.Protocol;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.nbt.CompoundTag;
import net.minecraft.nbt.ListTag;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.world.entity.ai.attributes.AttributeMap;
import net.minecraft.world.entity.player.Inventory;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.item.ItemStack;

import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Set;

/**
 * 玩家数据提取器：把属性 + 背包 + 末影箱 + 经验 + 生命/饥饿序列化为 NBT 载荷。
 * - 目标缺失模组的物品 → 进入隔离区（quarantine_meta + quarantine_nbt）；
 * - 玩家在映射页指定的「同名异 ID」替换 → 写入 payload 并记录 mapping_applied。
 */
public final class PlayerDataExtractor {

    private PlayerDataExtractor() {
    }

    /** 提取结果。 */
    public record Result(JsonObject payload, int quarantinedCount) {
    }

    public static Result extract(Player player, String transferId, String sourceSave,
                                 String targetSave, Set<String> quarantineRegistries,
                                 Map<String, String> mappingChoices) {
        JsonObject ctx = Protocol.transferContext(transferId, player, sourceSave, targetSave);

        CompoundTag root = new CompoundTag();
        ListTag inventory = new ListTag();
        ListTag ender = new ListTag();

        JsonArray quarantineMeta = new JsonArray();
        ListTag quarantineNbt = new ListTag();
        JsonObject mappingApplied = new JsonObject();

        Inventory inv = player.getInventory();
        // 主背包 + 护甲 + 副手 → payload 或隔离
        for (ItemStack stack : inv.items) {
            handleStack(player, stack, inventory, quarantineMeta, quarantineNbt,
                    quarantineRegistries, mappingChoices, mappingApplied);
        }
        for (ItemStack stack : inv.armor) {
            handleStack(player, stack, inventory, quarantineMeta, quarantineNbt,
                    quarantineRegistries, mappingChoices, mappingApplied);
        }
        for (ItemStack stack : inv.offhand) {
            handleStack(player, stack, inventory, quarantineMeta, quarantineNbt,
                    quarantineRegistries, mappingChoices, mappingApplied);
        }
        for (int i = 0; i < player.getEnderChestInventory().getContainerSize(); i++) {
            handleStack(player, player.getEnderChestInventory().getItem(i), ender,
                    quarantineMeta, quarantineNbt, quarantineRegistries,
                    mappingChoices, mappingApplied);
        }

        // 属性（1.20.1: AttributeMap.save() 返回 ListTag）
        AttributeMap attributes = player.getAttributes();
        ListTag attrTag = attributes.save();
        root.put("Attributes", attrTag);
        root.put("Inventory", inventory);
        root.put("EnderItems", ender);
        root.putInt("XpLevel", player.experienceLevel);
        root.putInt("XpTotal", player.totalExperience);
        root.putFloat("XpProgress", player.experienceProgress);
        root.putFloat("Health", player.getHealth());
        root.putInt("FoodLevel", player.getFoodData().getFoodLevel());

        ctx.addProperty(XferConstants.KEY_NBT, Protocol.toGzipBase64(root));

        // 隔离载荷
        CompoundTag qRoot = new CompoundTag();
        qRoot.put("Items", quarantineNbt);
        ctx.addProperty(XferConstants.KEY_Q_NBT, Protocol.toGzipBase64(qRoot));
        ctx.add(XferConstants.KEY_Q_META, quarantineMeta);
        ctx.add(XferConstants.KEY_MAPPING_APPLIED, mappingApplied);

        return new Result(ctx, quarantineMeta.size());
    }

    private static void handleStack(Player player, ItemStack stack, ListTag payload,
                                    JsonArray qMeta, ListTag qNbt,
                                    Set<String> quarantineRegistries,
                                    Map<String, String> mappingChoices,
                                    JsonObject mappingApplied) {
        if (stack == null || stack.isEmpty()) {
            return;
        }
        ResourceLocation key = BuiltInRegistries.ITEM.getKey(stack.getItem());
        String registry = key.toString();
        String modId = key.getNamespace();

        // 1) 玩家指定的「同名异 ID」映射
        String mapped = mappingChoices.get(registry);
        if (mapped != null && !mapped.equals(registry)) {
            ResourceLocation target = ResourceLocation.tryParse(mapped);
            if (target != null && BuiltInRegistries.ITEM.containsKey(target)) {
                ItemStack replaced = new ItemStack(BuiltInRegistries.ITEM.get(target), stack.getCount());
                if (stack.getTag() != null) {
                    replaced.setTag(stack.getTag().copy());
                }
                payload.add(Protocol.saveStack(player, replaced));
                mappingApplied.addProperty(registry, mapped);
                return;
            }
        }

        // 2) 目标缺失模组 → 隔离区
        if (quarantineRegistries.contains(registry)) {
            JsonObject meta = new JsonObject();
            meta.addProperty("registry", registry);
            meta.addProperty("mod_id", modId);
            meta.addProperty("display_name", stack.getHoverName().getString());
            meta.addProperty("count", stack.getCount());
            meta.addProperty("nbt_base64", Protocol.toGzipBase64(Protocol.saveStack(player, stack)));
            meta.addProperty("source_save", player.level().getServer() == null
                    ? "" : player.level().getServer().getWorldData().getLevelName());
            qMeta.add(meta);
            qNbt.add(Protocol.saveStack(player, stack));
            return;
        }

        // 3) 正常可迁移物品
        payload.add(Protocol.saveStack(player, stack));
    }

    public static Map<String, String> choicesFrom(JsonObject decision) {
        Map<String, String> out = new LinkedHashMap<>();
        if (decision == null || !decision.has("mapping_choices")) {
            return out;
        }
        JsonObject mc = decision.getAsJsonObject("mapping_choices");
        for (Map.Entry<String, com.google.gson.JsonElement> e : mc.entrySet()) {
            out.put(e.getKey(), e.getValue().getAsString());
        }
        return out;
    }
}
