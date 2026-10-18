package com.xferbridge;

/** 全局常量：模组 id、协议版本、工作区默认路径等。 */
public final class XferConstants {
    public static final String MOD_ID = "xferbridge";
    public static final String MOD_NAME = "XferBridge";
    public static final String PROTOCOL = "xferbridge.ipc.v1";
    /** 工作区默认目录：%APPDATA%/XferBridge（与外部工具一致）。 */
    public static final String WORKSPACE_DIR_NAME = "XferBridge";

    /** IPC 子目录。 */
    public static final String DIR_REQUESTS = "requests";
    public static final String DIR_RESPONSES = "responses";
    public static final String DIR_EVENTS = "events";
    public static final String DIR_PLANS = "plans";
    public static final String DIR_TRANSFERS = "transfers";

    /** 玩家载荷字段。 */
    public static final String KEY_FORMAT = "format";
    public static final String FORMAT_PAYLOAD = "xferbridge.payload.v1";
    public static final String KEY_NBT = "nbt_base64";
    public static final String KEY_Q_NBT = "quarantine_nbt_base64";
    public static final String KEY_Q_META = "quarantine_meta";
    public static final String KEY_MAPPING_APPLIED = "mapping_applied";

    public static final String QUARANTINE_FOLDER = "xfer_quarantine";

    private XferConstants() {
    }
}
