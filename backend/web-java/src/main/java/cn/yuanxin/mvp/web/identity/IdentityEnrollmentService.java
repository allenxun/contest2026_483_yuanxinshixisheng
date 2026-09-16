package cn.yuanxin.mvp.web.identity;

/**
 * <b>身份登记生产端的冻结调用面</b>（Java→Worker 身份结果合同的一部分）。
 *
 * <p>本轮交付的是<b>合同 + 生产端实现 + 消费端只读边界</b>；<b>业务流程的触发点尚未接线</b>，
 * 因为触发它的"测肤分析判定为新人候选"这一步位于 D 的写域
 * （{@code assessment_analyze.py:377-397,459-529} 与 D 独占的 {@code web/assessments/**}）。
 * 冻结本接口的目的正是让 D 与总协调<b>不必猜测未提交的实现</b>：数据面（写什么、写到哪、
 * 什么形状、何时可见）与调用面（方法签名、输入输出、失败语义）都已固定并有测试锁定。
 *
 * <p><b>实现必须满足的不变量</b>（逐条都有测试；违反任一条即为缺陷）：
 * <ol>
 *   <li><b>围栏</b>：在业务事务内以 {@code SELECT ... FOR UPDATE} 重读 T05，校验
 *       {@code processing_revision} 与 {@code current_photo_version} 仍等于命令值且
 *       {@code status='analyzing'}；不符则<b>不写成员行</b>并抛出可区分的围栏异常
 *       （依据 {@code 后端详细设计-V1-MVP.md:661}「如果任务输入已被补拍替换，
 *       不能把旧登记结果归给新照片」；对齐 D 既有 {@code _LINK_MEMBER} 的围栏
 *       {@code identity_enroll.py:80-87}，并<b>补上</b>既有 {@code _PERSIST_ENROLL_STARTED}
 *       只校验 revision 的缺口）。</li>
 *   <li><b>远端调用在事务外</b>：绝不在持有行锁时调用人脸服务
 *       （依据 {@code 后端详细设计-V1-MVP.md:659}「再锁外调用」）。</li>
 *   <li><b>幂等与对账</b>：{@code faceSubjectRef} 由 {@link IdentityEnrollmentCommand#faceSubjectRef()}
 *       确定性派生；先 {@code FaceIdentityPort.get(subjectRef)} 对账，命中即走
 *       {@link IdentityEnrollmentPhase#ENROLLED_RECONCILED} 且<b>不重复登记</b>；
 *       未命中才 {@code register}。本地插入用
 *       {@code INSERT ... ON CONFLICT (identity_namespace, face_subject_ref) DO NOTHING} + 回查
 *       （与 D 既有 {@code identity_enroll.py:63-66,393-398} 同范式），
 *       由 {@code uq_members_identity} 兜底唯一性，<b>绝不</b>用应用层 check-then-insert。</li>
 *   <li><b>失败语义</b>：依赖故障（超时/网络/5xx/畸形响应）⇒ 抛
 *       {@code ApiException(ErrorCode.DEPENDENCY_UNAVAILABLE)}（503、可重试），
 *       <b>绝不</b>写成员行、<b>绝不</b>回退测试替身、<b>绝不</b>返回看似成功的结果；
 *       配置错误 ⇒ 不可重试的失败。远端已登记但本地未能提交时，<b>保留</b>该 subject
 *       供受控对账，<b>绝不</b>自动删除（依据 {@code :661}）。</li>
 *   <li><b>写域</b>：只写 T01 {@code members}；<b>绝不</b>写 T05 {@code identity_result} 或
 *       {@code member_id}（Worker 独占列），<b>绝不</b>新增迁移、<b>绝不</b>改契约。</li>
 *   <li><b>脱敏</b>：日志与异常消息不得含 {@code faceSubjectRef}、{@code memberId}、
 *       namespace 取值、media id、图片字节、embedding 或任何凭据。</li>
 * </ol>
 */
public interface IdentityEnrollmentService {

    /**
     * 执行一次受控身份登记并产出冻结的身份结果。
     *
     * @param command 冻结输入；{@code correlationId}/{@code providerRequestId} 必须是确定性派生值
     * @return 已提交的成员行与终态相位；<b>只在成员行提交后返回</b>（见
     *         {@link IdentityEnrollmentResult} 的可见性时点）
     * @throws cn.yuanxin.mvp.web.error.ApiException 依赖故障（503 可重试）、围栏不符、
     *         或输入非法；绝不静默降级
     */
    IdentityEnrollmentResult enroll(IdentityEnrollmentCommand command);
}
