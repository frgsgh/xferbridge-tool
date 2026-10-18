package com.xferbridge.mapping;

import com.google.gson.Gson;
import com.google.gson.GsonBuilder;
import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.xferbridge.ipc.IpcChannel;

import java.io.IOException;
import java.io.Reader;
import java.io.Writer;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * 物品 ID 映射表：源 registry → 候选目标 registry 列表。
 * 全局映射（工作区 mappings.json，可被外部工具编辑）与存档本地映射合并。
 */
public final class ItemMappingTable {
    private static final Gson GSON = new GsonBuilder().setPrettyPrinting().create();
    private final Map<String, List<String>> entries = new LinkedHashMap<>();

    /** 从全局 + 存档本地加载映射表。 */
    public static ItemMappingTable load(IpcChannel channel, Path worldConfigDir) {
        ItemMappingTable t = new ItemMappingTable();
        t.merge(loadFile(channel.root().resolve("mappings.json")));
        t.merge(loadFile(worldConfigDir.resolve("xferbridge_mappings.json")));
        return t;
    }

    private static JsonObject loadFile(Path p) {
        if (!Files.isRegularFile(p)) {
            return null;
        }
        try (Reader r = Files.newBufferedReader(p, StandardCharsets.UTF_8)) {
            JsonElement el = com.google.gson.JsonParser.parseReader(r);
            return el.isJsonObject() ? el.getAsJsonObject() : null;
        } catch (Exception e) {
            return null;
        }
    }

    private void merge(JsonObject obj) {
        if (obj == null) {
            return;
        }
        JsonObject mappings = obj.has("mappings") ? obj.getAsJsonObject("mappings") : obj;
        for (Map.Entry<String, JsonElement> e : mappings.entrySet()) {
            List<String> cands = new ArrayList<>();
            if (e.getValue().isJsonArray()) {
                for (JsonElement el : e.getValue().getAsJsonArray()) {
                    cands.add(el.getAsString());
                }
            } else {
                cands.add(e.getValue().getAsString());
            }
            entries.put(e.getKey(), cands);
        }
    }

    /** 写入存档本地映射（不覆盖全局）。 */
    public void saveLocal(Path worldConfigDir) {
        try {
            Files.createDirectories(worldConfigDir);
            JsonObject root = new JsonObject();
            JsonObject mappings = new JsonObject();
            for (Map.Entry<String, List<String>> e : entries.entrySet()) {
                JsonArray arr = new JsonArray();
                for (String s : e.getValue()) {
                    arr.add(s);
                }
                mappings.add(e.getKey(), arr);
            }
            root.add("mappings", mappings);
            try (Writer w = Files.newBufferedWriter(
                    worldConfigDir.resolve("xferbridge_mappings.json"), StandardCharsets.UTF_8)) {
                w.write(GSON.toJson(root));
            }
        } catch (IOException ignored) {
        }
    }

    public List<String> suggestions(String registry) {
        return entries.getOrDefault(registry, List.of());
    }

    public void put(String source, String target) {
        entries.computeIfAbsent(source, k -> new ArrayList<>()).add(target);
    }

    public boolean isEmpty() {
        return entries.isEmpty();
    }

    public Map<String, List<String>> all() {
        return entries;
    }
}
