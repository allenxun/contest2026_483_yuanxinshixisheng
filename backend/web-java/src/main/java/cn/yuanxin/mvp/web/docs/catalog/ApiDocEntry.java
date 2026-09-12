package cn.yuanxin.mvp.web.docs.catalog;

import cn.yuanxin.mvp.web.error.ErrorCode;

import java.util.List;

/**
 * 单个 HTTP 操作的<strong>联调文档条目</strong>（集中式 springdoc 文档目录的数据形状）。
 *
 * <p>本类型是"文档目录道"与"文档施加引擎"之间的<strong>冻结契约</strong>：目录道只负责按
 * 权威来源（{@code backend/contracts/openapi/openapi.yaml} 的 summary/description/x-error-codes、
 * {@code backend/doc/} 的详细设计与数据架构）填写内容；引擎负责把这些内容施加到
 * <em>由实际 Controller/DTO 生成</em>的 OpenAPI 对象上。<strong>不修改任何控制器、DTO
 * 或业务代码</strong>，因此序列化与业务行为零变更。</p>
 *
 * <p>键约定：目录 {@code Map} 的 key 一律为 {@code "METHOD path"}（大写方法 + 真实路由模板，
 * 如 {@code "POST /api/v1/auth/sessions"}、{@code "PUT /api/v1/me/gimbal-bindings/{gimbalId}"}）。
 * <strong>不得使用 operationId 作键</strong>——生成文档中存在 {@code create}/{@code create_1}/
 * {@code create_2}/{@code get}/{@code list}/{@code task} 等歧义名。</p>
 *
 * @param tag                 所属业务域标签名（须与 {@link ApiDocsCatalog#tags()} 中声明的一致）
 * @param summary             一句话中文用途（建议 ≤ 40 字，Swagger UI 列表标题）
 * @param description         中文详细说明：用途、调用方主体、前置条件与顺序、关键规则、
 *                            幂等语义、字段单位/枚举要点、错误处理与客户端动作。可多行。
 *                            <strong>语义须取自权威来源，不得自行发明</strong>；权威缺失处
 *                            必须显式写"待定/未冻结"并说明依据。
 * @param params              该操作<strong>全部</strong>参数（path/query/header）的文档；
 *                            引擎据此补 description/example，并校验无遗漏、无多余
 * @param multipartParts      multipart 请求体各 part 的文档；非 multipart 端点传 {@code List.of()}。
 *                            用于 M1-A01、M3-A01、M3-A02 这三个用 raw request 手工解析、
 *                            springdoc 完全看不到 part 的端点
 * @param requestBodyClass    JSON 请求体的文档化类型；{@code null} 表示沿用 springdoc 自动推导。
 *                            当自动推导错误时（例如把鉴权主体 {@code PrincipalContext} 当成请求体）
 *                            用本字段<strong>覆盖</strong>为真实请求体类型
 * @param requestBodyDescription 请求体整体说明（含 JCS payload_hash 与幂等键关系等）；可为 {@code null}
 * @param successes           成功响应（可多个：如 201 新建 / 200 重放，或 202 受理）
 * @param errorCodes          该操作适用的业务错误码，<strong>必须与契约 {@code x-error-codes} 一致</strong>
 *                            （由一致性测试强制校验）；HTTP 状态与 retryable 取自 {@link ErrorCode}
 */
public record ApiDocEntry(
        String tag,
        String summary,
        String description,
        List<ParamDoc> params,
        List<MultipartPartDoc> multipartParts,
        Class<?> requestBodyClass,
        String requestBodyDescription,
        List<SuccessDoc> successes,
        List<ErrorCode> errorCodes) {

    /**
     * 单个参数的文档。
     *
     * @param name        参数名（与生成文档中的 {@code name} 完全一致，如 {@code taskId}、
     *                    {@code Idempotency-Key}、{@code If-Match}、{@code X-Pairing-Proof}）
     * @param in          位置：{@code path} / {@code query} / {@code header}
     * @param description 中文含义，<strong>必须含类型、必填性、单位或取值格式</strong>
     *                    （如"无符号 bigint 十进制字符串，从 1 开始，补拍须为当前版本+1"）
     * @param example     脱敏示例值（不得含真实手机号、真实 token、真实 UUID 之外的敏感数据）；
     *                    可为 {@code null}
     * @param requiredOverride 若非 {@code null}，覆盖生成文档中的 required（用于契约要求必填但
     *                    代码层未强制、或反之的情形；须在 description 中说明依据）
     */
    public record ParamDoc(
            String name,
            String in,
            String description,
            String example,
            Boolean requiredOverride) {

        public static ParamDoc of(String name, String in, String description) {
            return new ParamDoc(name, in, description, null, null);
        }

        public static ParamDoc of(String name, String in, String description, String example) {
            return new ParamDoc(name, in, description, example, null);
        }
    }

    /**
     * multipart 请求体中单个 part 的文档。
     *
     * @param name        part 名（如 {@code metadata}、{@code face}、{@code front}、{@code left}、{@code right}）
     * @param contentType 该 part 的 Content-Type（JSON part 用 {@code application/json}；
     *                    图片用 {@code image/jpeg} 等）
     * @param description 中文说明（含必填性、大小上限、校验规则）
     * @param jsonSchema  若该 part 是 JSON，给出其结构化类型（引擎据此生成可展开的 schema）；
     *                    二进制 part 传 {@code null}
     * @param binaryFormat 二进制 part 的 OpenAPI format（通常为 {@code "binary"}）；JSON part 传 {@code null}
     */
    public record MultipartPartDoc(
            String name,
            String contentType,
            String description,
            Class<?> jsonSchema,
            String binaryFormat) {

        public static MultipartPartDoc json(String name, String description, Class<?> jsonSchema) {
            return new MultipartPartDoc(name, "application/json", description, jsonSchema, null);
        }

        public static MultipartPartDoc binary(String name, String contentType, String description) {
            return new MultipartPartDoc(name, contentType, description, null, "binary");
        }
    }

    /**
     * 单个成功响应的文档。
     *
     * <p><strong>状态码必须是该端点的真实状态码</strong>，不得沿用 springdoc 默认生成的 200：
     * 基线生成文档把全部 34 个操作都标为 200，而实际存在 201（新建授权）、202（任务受理/补拍受理）、
     * 204（撤销授权、解绑、登出，无响应体）。错误地写成 200 会直接误导联调方的响应解析。</p>
     *
     * <p><b>四种形态（互斥，按下列优先级判定）</b>：</p>
     * <ol>
     *   <li>{@code listItemClass != null} → 列表响应：{@code data} 为
     *       {@code {items: [ <该条目类型> ], nextCursor: string|null}}
     *       （即 {@code cn.yuanxin.mvp.web.web.ListData<T>} 的形状）。
     *       <strong>列表端点必须用 {@link #jsonList}，不得用 {@code json(…, ListData.class)}</strong>——
     *       {@code ListData} 是 record 且泛型在运行时被擦除，裸类会让 {@code items} 退化为无类型
     *       object，条目 DTO 也不会注册进 components，从而导致条目字段无法文档化。</li>
     *   <li>{@code contentType != null} → 非 JSON（媒体二进制下载），无信封；</li>
     *   <li>{@code dataClass != null} → 标准信封 {@code {requestId, data:<该类型>, meta}}；</li>
     *   <li>三者皆 null → 无响应体（204）。</li>
     * </ol>
     *
     * @param code          HTTP 状态码字符串（{@code "200"}/{@code "201"}/{@code "202"}/{@code "204"}）
     * @param description   中文说明（含"重放时 meta.replayed=true"等语义差异）
     * @param dataClass     统一信封中 {@code data} 的真实类型；引擎据此生成
     *                      {@code {requestId, data:<该类型>, meta}} 的<strong>可展开</strong>响应 schema。
     *                      {@code null} 表示无 {@code data}（204）、非 JSON（二进制下载）或列表响应
     * @param contentType   响应 Content-Type；{@code null} 表示 {@code application/json}；
     *                      二进制下载填媒体自身类型（如 {@code "image/jpeg"}）并令 {@code dataClass=null}
     * @param listItemClass 列表响应中 {@code data.items} 的<strong>条目类型</strong>；非列表端点传 {@code null}。
     *                      引擎会把它注册进 {@code components.schemas}（因此其字段可由
     *                      {@link ApiDocsCatalog#propertyDocs()} 文档化），并生成
     *                      {@code items: {type: array, items: {$ref 条目类型}}} 与
     *                      {@code nextCursor: {type: string, nullable: true}}（含中文说明：
     *                      为 null 表示无后续页，字段保留不省略）
     */
    public record SuccessDoc(
            String code,
            String description,
            Class<?> dataClass,
            String contentType,
            Class<?> listItemClass) {

        public static SuccessDoc json(String code, String description, Class<?> dataClass) {
            return new SuccessDoc(code, description, dataClass, null, null);
        }

        /**
         * 列表响应（{@code data = {items, nextCursor}}）。
         *
         * @param itemClass {@code items} 数组的条目类型（如 {@code SkinReportListItem}）
         */
        public static SuccessDoc jsonList(String code, String description, Class<?> itemClass) {
            return new SuccessDoc(code, description, null, null, itemClass);
        }

        public static SuccessDoc noContent(String code, String description) {
            return new SuccessDoc(code, description, null, null, null);
        }

        public static SuccessDoc binary(String code, String description, String contentType) {
            return new SuccessDoc(code, description, null, contentType, null);
        }
    }
}
