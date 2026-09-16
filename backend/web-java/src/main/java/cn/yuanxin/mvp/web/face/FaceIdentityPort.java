package cn.yuanxin.mvp.web.face;

import java.util.Optional;

/**
 * 供应商无关的<b>人脸身份端口</b>（B 自有）。业务层只依赖本端口与其保守结果类型
 * （{@link FaceSearchDecision}/{@link FaceSearchResult}/{@link PhotoComparisonMatch}/
 * {@link LivenessVerifiedMatch}），<b>不</b>依赖任何供应商 SDK、HTTP 形状或错误码字面量。
 *
 * <p>当前唯一实现是 InsightFace 适配器；将来切换阿里云时<b>只</b>新增一个实现，
 * 业务层、HTTP 契约、DTO 与数据库身份语义都不改（用户最终决策，2026-09-16）。
 * 阿里云实现尚不存在：{@code app.face.provider=aliyun} 在<b>启动期</b>即被
 * {@code AliyunFaceBoundaryConfig} 拒绝（沿用既有 static {@code @Bean} 的
 * {@code BeanFactoryPostProcessor} 范式），绝不返回假结果。
 *
 * <p><b>失败语义（fail-closed）</b>：任何依赖故障（超时、网络、5xx、畸形/不完整 2xx 响应）
 * 都<b>抛</b> {@link FaceServiceException}，<b>绝不</b>返回"未匹配"或任何看似成功的结果，
 * 也<b>绝不</b>回退到测试替身。调用方负责把异常映射为 503 {@code DEPENDENCY_UNAVAILABLE}。
 *
 * <p><b>日志纪律</b>：实现类不得记录 token、图片字节、embedding、namespace 取值、
 * {@code subjectRef} 取值或候选明细；只允许记录操作名、请求标识、HTTP 状态与错误分类。
 */
public interface FaceIdentityPort {

    /** 当前配置的身份命名空间（人脸库隔离边界）；绝不返回给外部客户端。 */
    String identityNamespace();

    /**
     * namespace 限定的<b>只读</b> 1:N 搜索。
     *
     * <p>保守性由服务端固定策略保证（调用方<b>不可</b>指定阈值）；返回值的
     * {@link FaceSearchDecision#NO_MATCH} <b>不得</b>被解释为可靠新人。
     *
     * @param purpose 业务用途（例如 {@code grant}），仅用于审计与日志分类，绝不作为身份信息
     * @param image   候选照片字节；实现不得持久化、不得记录其内容
     * @throws FaceServiceException 依赖/配置故障，或响应形状不符合冻结契约
     */
    FaceSearchResult search(String purpose, byte[] image);

    /**
     * <b>普通无活体 1:1</b>（照片比对）：只与指定 {@code subjectRef} 比对，不做全库检索、不写库。
     *
     * <p>请求<b>不</b>携带 {@code require_liveness}，因此不会触发服务端 501；
     * 结果<b>无防翻拍能力</b>，只能用于不要求现场性的身份场景，<b>绝不</b>用于护理准入。
     *
     * @throws FaceServiceException 依赖/配置故障、{@code SUBJECT_NOT_FOUND}、
     *                              {@code NAMESPACE_NOT_FOUND} 或响应形状不符
     */
    PhotoComparisonMatch verifyPhotoOnly(String purpose, String subjectRef, byte[] image);

    /**
     * <b>要求活体</b>的 1:1：恒发送 {@code require_liveness=true}，<b>无关闭开关</b>。
     *
     * <p>当前真实服务无活体能力 ⇒ 恒抛 {@link FaceServiceException}
     * （{@code LIVENESS_UNSUPPORTED} 或 {@code LIVENESS_NOT_PASSED}），
     * 由护理路径映射为 {@code CAPABILITY_UNAVAILABLE}（对外 503）。这是刻意 fail-closed，不是缺陷。
     *
     * @throws FaceServiceException 活体不支持/未通过，或任何依赖、配置、形状故障
     */
    LivenessVerifiedMatch verifyWithLiveness(String purpose, String subjectRef, byte[] image);

    /**
     * 只读自省：进程/模型/库状态。用于运维与就绪判断，不参与任何身份判定。
     *
     * @throws FaceServiceException 依赖故障或响应形状不符
     */
    FaceHealthView health();

    /**
     * 零写入的人脸检测与特征提取（不查库、不登记）。
     *
     * @throws FaceServiceException 依赖故障或响应形状不符
     */
    FaceExtractView extract(String purpose, byte[] image);

    /**
     * 零写入的质量评估。质量信号必须<b>诚实</b>：服务端不具备的信号（如活体、姿态、遮挡）
     * 必须显式标为不支持，绝不用检测分数或相似度冒充。
     *
     * @throws FaceServiceException 依赖故障或响应形状不符
     */
    FaceQualityView quality(String purpose, byte[] image);

    /**
     * 登记（<b>写</b>操作）：在受控 namespace 内登记主体与参考特征。
     *
     * <p><b>幂等与对账要求</b>：{@code subjectRef} 必须由调用方<b>预先确定</b>
     * （不得由本端口生成随机值），使"远端登记成功但本地事务失败"可以用同一
     * {@code subjectRef} 查询对账后安全重试，而不是盲目重试产生第二个主体
     * （依据 {@code backend/doc/后端详细设计-V1-MVP.md:659}）。
     *
     * <p><b>当前状态（如实披露）</b>：本方法属"Java 是人脸库唯一写入方"的能力实现，
     * 但<b>尚无业务流程调用它</b>——成员建档（T01 {@code members}）当前唯一生产写入方是
     * D 包的 Python {@code identity.enroll}，属跨包写域，须先由总协调裁定移交。
     * 详见 {@code backend/handoffs/B-face-java.md} 的跨包 blocker 一节。
     *
     * @throws FaceServiceException 依赖/配置故障、{@code SUBJECT_ALREADY_EXISTS} 或响应形状不符
     */
    FaceSubjectRegistration register(String purpose, String subjectRef, byte[] referenceImage);

    /**
     * 只读查询某主体是否已登记（用于登记超时后的<b>对账</b>，不做全库搜索）。
     *
     * @return 存在则返回登记视图，不存在返回 {@link Optional#empty()}（<b>不</b>抛异常）
     * @throws FaceServiceException 依赖/配置故障或响应形状不符
     */
    Optional<FaceSubjectView> get(String subjectRef);

    /**
     * 删除（<b>写</b>操作）：删除算法侧主体与特征。重复删除必须有明确、幂等的结果。
     *
     * <p>删除算法主体<b>不</b>隐式撤销账号授权、也<b>不</b>删除业务成员行——三者是不同的事
     * （依据 {@code backend/doc/人脸服务调研与推荐方案-V1-MVP.md:151}）。
     *
     * <p><b>当前状态</b>：与 {@link #register} 同——能力已实现，尚无业务流程调用，
     * 待跨包写域裁定后接入。
     *
     * @throws FaceServiceException 依赖/配置故障或响应形状不符
     */
    FaceSubjectDeletion delete(String subjectRef);
}
