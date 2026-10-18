package com.xferbridge.config;

import com.xferbridge.XferConstants;
import net.minecraftforge.common.ForgeConfigSpec;

/** 客户端配置：工作区路径、备份触发开关、节流秒数。 */
public final class XferConfig {
    public static final ForgeConfigSpec SPEC;
    public static final ForgeConfigSpec.ConfigValue<String> WORKSPACE;
    public static final ForgeConfigSpec.BooleanValue BACKUP_ON_LOGOUT;
    public static final ForgeConfigSpec.BooleanValue BACKUP_ON_SAVE;
    public static final ForgeConfigSpec.IntValue BACKUP_THROTTLE_SEC;
    public static final ForgeConfigSpec.ConfigValue<String> GLOBAL_MAPPINGS;

    static {
        ForgeConfigSpec.Builder b = new ForgeConfigSpec.Builder();
        b.push("xferbridge");
        WORKSPACE = b.comment("外部工具工作区目录（必须与 XferTool 设置一致）")
                .define("workspace", defaultWorkspace());
        BACKUP_ON_LOGOUT = b.comment("退出世界时触发增量备份")
                .define("backup_on_logout", true);
        BACKUP_ON_SAVE = b.comment("玩家保存/自动保存时触发增量备份（带节流）")
                .define("backup_on_save", true);
        BACKUP_THROTTLE_SEC = b.comment("保存类备份的最小间隔（秒）")
                .defineInRange("backup_throttle_sec", 60, 5, 3600);
        GLOBAL_MAPPINGS = b.comment("全局物品映射表路径（可选，覆盖工作区默认）")
                .define("global_mappings", "");
        b.pop();
        SPEC = b.build();
    }

    private static String defaultWorkspace() {
        String appdata = System.getenv("APPDATA");
        if (appdata == null || appdata.isEmpty()) {
            appdata = System.getProperty("user.home");
        }
        return appdata + "\\" + XferConstants.WORKSPACE_DIR_NAME;
    }

    private XferConfig() {
    }
}
