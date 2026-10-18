package com.xferbridge.ipc;

import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import com.xferbridge.XferConstants;
import com.xferbridge.config.XferConfig;

import java.io.IOException;
import java.io.Reader;
import java.io.Writer;
import java.nio.charset.StandardCharsets;
import java.nio.file.DirectoryStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.time.ZoneOffset;
import java.time.ZonedDateTime;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;

/**
 * 文件 IPC 客户端：向外部工具工作区写入请求、读取响应与事件。
 * 工作区默认 %APPDATA%/XferBridge，可在配置中覆盖。
 */
public final class IpcChannel {
    private static final DateTimeFormatter ISO = DateTimeFormatter.ISO_OFFSET_DATE_TIME;

    private final Path root;

    public IpcChannel() {
        String cfg = XferConfig.WORKSPACE.get();
        this.root = cfg == null || cfg.isBlank()
                ? defaultWorkspace()
                : Paths.get(cfg).toAbsolutePath();
    }

    public static Path defaultWorkspace() {
        String appdata = System.getenv("APPDATA");
        if (appdata == null || appdata.isEmpty()) {
            appdata = System.getProperty("user.home");
        }
        return Paths.get(appdata, XferConstants.WORKSPACE_DIR_NAME);
    }

    public Path root() {
        return root;
    }

    private Path sub(String name) {
        Path p = root.resolve(name);
        try {
            Files.createDirectories(p);
        } catch (IOException ignored) {
        }
        return p;
    }

    // ---------------------------------------------------------------- 写入
    /** 发送请求，返回 request_id。payload 可为 null。 */
    public String writeRequest(String action, JsonObject payload) {
        JsonObject req = new JsonObject();
        String id = UUID.randomUUID().toString();
        req.addProperty("protocol", XferConstants.PROTOCOL);
        req.addProperty("request_id", id);
        req.addProperty("action", action);
        req.addProperty("from", "mod");
        req.addProperty("created_at", ZonedDateTime.now(ZoneOffset.UTC).format(ISO));
        if (payload != null) {
            req.add("payload", payload);
        }
        writeJson(sub(XferConstants.DIR_REQUESTS).resolve("req_" + id + ".json"), req);
        return id;
    }

    /** 便捷：附带当前世界信息（world_folder / world_path）的请求。 */
    public String writeRequestWithWorld(String action, JsonObject payload, WorldContext world) {
        if (payload == null) {
            payload = new JsonObject();
        }
        if (world != null) {
            if (world.folder() != null) {
                payload.addProperty("world_folder", world.folder());
            }
            if (world.path() != null) {
                payload.addProperty("world_path", world.path().toString());
            }
        }
        return writeRequest(action, payload);
    }

    /** 写入迁移任务文件（payload.json / decision.json）到工作区 transfers/<id>/。 */
    public void writeTransferFile(String transferId, String name, JsonObject obj) {
        Path dir = sub(XferConstants.DIR_TRANSFERS).resolve(transferId);
        writeJson(dir.resolve(name), obj);
    }

    /** 读取迁移任务文件。 */
    public JsonObject readTransferFile(String transferId, String name) {
        Path p = sub(XferConstants.DIR_TRANSFERS).resolve(transferId).resolve(name);
        return Files.isRegularFile(p) ? readJson(p) : null;
    }

    public boolean hasTransferFile(String transferId, String name) {
        return Files.isRegularFile(sub(XferConstants.DIR_TRANSFERS).resolve(transferId).resolve(name));
    }

    // ---------------------------------------------------------------- 读取
    public JsonObject pollResponse(String requestId) {
        Path p = sub(XferConstants.DIR_RESPONSES).resolve("resp_" + requestId + ".json");
        if (!Files.isRegularFile(p)) {
            return null;
        }
        JsonObject resp = readJson(p);
        if (resp == null) {
            return null;
        }
        try {
            Files.deleteIfExists(p);
        } catch (IOException ignored) {
        }
        return resp;
    }

    /** 读取某请求的最新事件（进度）。 */
    public JsonObject latestEvent(String requestId) {
        List<JsonObject> evts = eventsFor(requestId);
        return evts.isEmpty() ? null : evts.get(evts.size() - 1);
    }

    public List<JsonObject> eventsFor(String requestId) {
        List<JsonObject> out = new ArrayList<>();
        Path dir = sub(XferConstants.DIR_EVENTS);
        try (DirectoryStream<Path> ds = Files.newDirectoryStream(dir, "evt_" + requestId + "_*.json")) {
            for (Path p : ds) {
                JsonObject evt = readJson(p);
                if (evt != null) {
                    out.add(evt);
                }
            }
        } catch (IOException ignored) {
        }
        out.sort((a, b) -> Long.compare(
                a.get("at") == null ? 0 : a.get("at").getAsString().hashCode(),
                b.get("at") == null ? 0 : b.get("at").getAsString().hashCode()));
        return out;
    }

    /** 读取外部工具生成的存档索引。 */
    public JsonObject readSavesIndex() {
        Path p = root.resolve("saves_index.json");
        if (!Files.isRegularFile(p)) {
            return null;
        }
        JsonObject idx = readJson(p);
        if (idx == null || !idx.has("saves")) {
            return null;
        }
        return idx;
    }

    public JsonArray savesArray() {
        JsonObject idx = readSavesIndex();
        return idx == null ? new JsonArray() : idx.getAsJsonArray("saves");
    }

    /** 请求外部工具重新扫描。 */
    public String requestScan() {
        return writeRequest("scan_saves", new JsonObject());
    }

    // ---------------------------------------------------------------- 内部
    private static JsonObject readJson(Path p) {
        try (Reader r = Files.newBufferedReader(p, StandardCharsets.UTF_8)) {
            JsonElement el = JsonParser.parseReader(r);
            return el.isJsonObject() ? el.getAsJsonObject() : null;
        } catch (Exception e) {
            return null;
        }
    }

    private static void writeJson(Path p, JsonObject obj) {
        try {
            Files.createDirectories(p.getParent());
            try (Writer w = Files.newBufferedWriter(p, StandardCharsets.UTF_8)) {
                w.write(obj.toString());
            }
        } catch (IOException ignored) {
        }
    }

    /** 当前世界上下文（文件夹名与绝对路径）。 */
    public record WorldContext(String folder, Path path) {
    }
}
