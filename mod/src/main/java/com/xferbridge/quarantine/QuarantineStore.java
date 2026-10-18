package com.xferbridge.quarantine;

import com.google.gson.Gson;
import com.google.gson.GsonBuilder;
import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import net.minecraft.nbt.CompoundTag;
import net.minecraft.server.MinecraftServer;
import net.minecraft.world.level.saveddata.SavedData;

import java.io.IOException;
import java.io.Reader;
import java.nio.charset.StandardCharsets;
import java.nio.file.DirectoryStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;

/**
 * 隔离区/虚拟背包存储：以 CustomSavedData 挂载到主世界，
 * 条目为「因目标存档缺失模组而被拦截的物品」（NBT 压缩存储）。
 * 世界加载时从存档目录 xfer_quarantine/items_*.json 幂等导入。
 */
public class QuarantineStore extends SavedData {
    public static final String DATA_KEY = "xferbridge_quarantine";

    private final List<QuarantineItem> items = new ArrayList<>();
    private final List<String> importedBatches = new ArrayList<>();

    public static QuarantineStore of(MinecraftServer server) {
        if (server == null || server.overworld() == null) {
            return null;
        }
        // 1.20.1 无 SavedData.Factory，使用 3 参 computeIfAbsent
        return server.overworld().getDataStorage().computeIfAbsent(
                QuarantineStore::load, QuarantineStore::new, DATA_KEY);
    }

    public static QuarantineStore load(CompoundTag tag) {
        QuarantineStore store = new QuarantineStore();
        ListTagReader list = ListTagReader.of(tag.getList("items", 10));
        for (CompoundTag item : list.compounds()) {
            store.items.add(QuarantineItem.fromNbt(item));
        }
        ListTagReader batches = ListTagReader.of(tag.getList("imported_batches", 8));
        for (String b : batches.strings()) {
            store.importedBatches.add(b);
        }
        return store;
    }

    @Override
    public CompoundTag save(CompoundTag tag) {
        net.minecraft.nbt.ListTag list = new net.minecraft.nbt.ListTag();
        for (QuarantineItem item : items) {
            list.add(item.toNbt());
        }
        tag.put("items", list);
        net.minecraft.nbt.ListTag batches = new net.minecraft.nbt.ListTag();
        for (String b : importedBatches) {
            batches.add(net.minecraft.nbt.StringTag.valueOf(b));
        }
        tag.put("imported_batches", batches);
        return tag;
    }

    /** 从世界目录 xfer_quarantine/items_*.json 导入（幂等，按 transfer_id 去重）。 */
    public int importFromWorldFolder(Path worldDir) {
        Path qdir = worldDir.resolve("xfer_quarantine");
        if (!Files.isDirectory(qdir)) {
            return 0;
        }
        int added = 0;
        try (DirectoryStream<Path> ds = Files.newDirectoryStream(qdir, "items_*.json")) {
            for (Path p : ds) {
                String batchId = batchIdOf(p);
                if (batchId == null || importedBatches.contains(batchId)) {
                    continue;
                }
                JsonObject doc = parse(p);
                if (doc == null) {
                    continue;
                }
                JsonArray arr = doc.has("items") ? doc.getAsJsonArray("items") : new JsonArray();
                for (JsonElement el : arr) {
                    if (el.isJsonObject()) {
                        items.add(QuarantineItem.fromJson(el.getAsJsonObject()));
                        added++;
                    }
                }
                importedBatches.add(batchId);
                setDirty();
            }
        } catch (IOException ignored) {
        }
        return added;
    }

    private static String batchIdOf(Path p) {
        try (Reader r = Files.newBufferedReader(p, StandardCharsets.UTF_8)) {
            JsonObject doc = JsonParser.parseReader(r).getAsJsonObject();
            return doc.has("transfer_id") ? doc.get("transfer_id").getAsString() : null;
        } catch (Exception e) {
            return null;
        }
    }

    private static JsonObject parse(Path p) {
        try (Reader r = Files.newBufferedReader(p, StandardCharsets.UTF_8)) {
            JsonElement el = JsonParser.parseReader(r);
            return el.isJsonObject() ? el.getAsJsonObject() : null;
        } catch (Exception e) {
            return null;
        }
    }

    // ------------------------------------------------------------ 操作
    public List<QuarantineItem> items() {
        return items;
    }

    public int size() {
        return items.size();
    }

    public void add(QuarantineItem item) {
        items.add(item);
        setDirty();
    }

    /** 释放指定条目（从隔离区移除）。 */
    public QuarantineItem release(int index) {
        if (index < 0 || index >= items.size()) {
            return null;
        }
        QuarantineItem item = items.remove(index);
        setDirty();
        return item;
    }

    /** 释放全部。 */
    public List<QuarantineItem> releaseAll() {
        List<QuarantineItem> out = new ArrayList<>(items);
        items.clear();
        setDirty();
        return out;
    }

    // ------------------------------------------------------------ 辅助
    private static final class ListTagReader {
        private final net.minecraft.nbt.ListTag tag;

        private ListTagReader(net.minecraft.nbt.ListTag tag) {
            this.tag = tag;
        }

        static ListTagReader of(net.minecraft.nbt.ListTag tag) {
            return new ListTagReader(tag);
        }

        List<CompoundTag> compounds() {
            List<CompoundTag> out = new ArrayList<>();
            for (int i = 0; i < tag.size(); i++) {
                out.add(tag.getCompound(i));
            }
            return out;
        }

        List<String> strings() {
            List<String> out = new ArrayList<>();
            for (int i = 0; i < tag.size(); i++) {
                out.add(tag.getString(i));
            }
            return out;
        }
    }
}
