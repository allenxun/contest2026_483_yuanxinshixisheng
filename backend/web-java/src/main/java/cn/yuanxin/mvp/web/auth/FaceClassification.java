package cn.yuanxin.mvp.web.auth;

/**
 * 人脸适配端口分类结果（DD 4.x；digest §6）：已匹配/可靠新人员/不确定/
 * 质量不合格/依赖失败。A 包只定义端口与替身，无业务调用点（B/D 接线）。
 */
public enum FaceClassification {
    MATCHED,
    RELIABLE_NEW,
    UNCERTAIN,
    QUALITY_REJECTED,
    /** 依赖失败 ≠ 匹配成功（fail closed：人脸超时/异常绝不按通过处理）。 */
    DEPENDENCY_FAILED
}
