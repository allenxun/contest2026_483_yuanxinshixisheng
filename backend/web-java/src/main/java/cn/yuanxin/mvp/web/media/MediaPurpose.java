package cn.yuanxin.mvp.web.media;

/**
 * T11 media_objects.purpose 枚举（V1 迁移 CHECK 取值；digest §2 T11）。
 */
public enum MediaPurpose {
    ASSESSMENT_SOURCE("assessment_source"),
    ASSESSMENT_RESULT("assessment_result"),
    GRANT_FACE("grant_face"),
    EXECUTION_FACE("execution_face"),
    REVALIDATION_FACE("revalidation_face");

    private final String dbValue;

    MediaPurpose(String dbValue) {
        this.dbValue = dbValue;
    }

    public String dbValue() {
        return dbValue;
    }

    public static MediaPurpose fromDbValue(String v) {
        for (MediaPurpose p : values()) {
            if (p.dbValue.equals(v)) return p;
        }
        throw new IllegalArgumentException("unknown media purpose: " + v);
    }
}
