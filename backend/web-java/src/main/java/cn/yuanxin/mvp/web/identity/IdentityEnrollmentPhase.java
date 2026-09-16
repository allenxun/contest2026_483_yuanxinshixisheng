package cn.yuanxin.mvp.web.identity;

/**
 * 身份登记结果的<b>状态机</b>（Java→Worker 身份结果合同的一部分）。
 *
 * <p>本轮裁定（2026-09-16，总协调已接受跨包阻塞并协调 D 移除 Worker 人脸调用与
 * {@code face_subject_ref} 双写）：<b>Java 是 T01 身份结果的唯一写入方</b>，Worker 只读消费。
 *
 * <p><b>持久化位置与归属（必须严格区分，两个载体不是同一列）</b>：
 * <ul>
 *   <li>{@link #ENROLLED} / {@link #ENROLLED_RECONCILED} —— 由 <b>Java</b> 写入
 *       <b>T01 {@code members.identity_summary.enrollment.phase}</b>。只有这两个值是
 *       "成员行已提交、身份已可靠建立"的终态。</li>
 *   <li>{@link #ENROLL_PENDING} / {@link #ENROLL_STARTED} —— 仍由 <b>D 的 Worker</b> 写入
 *       <b>T05 {@code skin_assessments.identity_result.phase}</b>（既有语义，见
 *       {@code identity_enroll.py:87} 的 {@code phase IN ('enroll_pending','enroll_started')} 守卫）。
 *       <b>Java 绝不写 T05 {@code identity_result}</b>——该列是 Worker 独占列
 *       （{@code AssessmentRepository.java:14,99}、{@code PhotoVersions.java:21} 逐字记载）。</li>
 * </ul>
 *
 * <p><b>为什么 Java 侧不持久化 in-flight 标记</b>：{@code face_subject_ref} 由
 * {@link IdentityResultContract#candidateEntityId} <b>确定性派生</b>（UUIDv5，跨重试稳定），
 * 因此"远端登记成功但本地事务失败/进程崩溃"可以用同一 ref 调 {@code FaceIdentityPort.get}
 * 对账后安全重试，<b>不需要</b>先写一个待决成员行。刻意不采用"先插行再翻状态"的方案，
 * 因为 {@code members.status} 的取值域只有 {@code active|disabled}，而
 * {@code 数据架构设计-V1-五模块-MVP.md:160} 明确「disabled 是运维状态，不代替授权撤销」
 * ——把它当作待决标记会污染既有语义。依据 {@code 后端详细设计-V1-MVP.md:659}
 * 「网络超时先按同 EntityId 查询对账，不生成另一 ID 盲目重试」与 {@code :661}
 * 「外部成功但业务取消的人员资源保留受控对账，确认无业务引用后再清理」。
 */
public enum IdentityEnrollmentPhase {

    /** D 的 Worker 侧：已判定需要登记、任务已入队（写 T05 {@code identity_result}）。 */
    ENROLL_PENDING("enroll_pending"),

    /** D 的 Worker 侧：登记已开始、外部结果未知（写 T05 {@code identity_result}）。 */
    ENROLL_STARTED("enroll_started"),

    /**
     * Java 侧终态：远端登记本次确认成功，且成员行已在同一业务事务提交
     * （写 T01 {@code members.identity_summary}）。
     */
    ENROLLED("enrolled"),

    /**
     * Java 侧终态：远端登记在<b>此前</b>某次尝试已成功（超时/崩溃后按同一确定性
     * {@code face_subject_ref} 查询对账命中），本次只补写本地成员行
     * （写 T01 {@code members.identity_summary}）。
     *
     * <p>该值使"远端成功 + 本地失败"可恢复且<b>不产生第二个 subject</b>。
     */
    ENROLLED_RECONCILED("enrolled_reconciled");

    private final String wireValue;

    IdentityEnrollmentPhase(String wireValue) {
        this.wireValue = wireValue;
    }

    /** 落库/跨语言传输使用的字面值（与 D 既有取值逐字一致，不得改名）。 */
    public String wireValue() {
        return wireValue;
    }

    /** 是否为 Java 写入 T01 的终态（Worker 不得自行产出这两个值）。 */
    public boolean isJavaTerminal() {
        return this == ENROLLED || this == ENROLLED_RECONCILED;
    }

    /**
     * 严格解析：未知取值一律失败，绝不静默降级为某个默认相位。
     *
     * @throws IllegalArgumentException 取值不属于本状态机
     */
    public static IdentityEnrollmentPhase fromWireValue(String value) {
        for (IdentityEnrollmentPhase phase : values()) {
            if (phase.wireValue.equals(value)) {
                return phase;
            }
        }
        throw new IllegalArgumentException("unknown identity enrollment phase");
    }
}
