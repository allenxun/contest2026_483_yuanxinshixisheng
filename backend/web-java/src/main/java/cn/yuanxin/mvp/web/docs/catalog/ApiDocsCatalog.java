package cn.yuanxin.mvp.web.docs.catalog;

import io.swagger.v3.oas.models.tags.Tag;

import java.util.List;
import java.util.Map;

/**
 * 一个业务域的<strong>联调文档目录</strong>（集中式 springdoc 文档的按域切分单元）。
 *
 * <p>每个实现类是一个 Spring bean，由引擎收集后统一施加到<em>实际生成</em>的 OpenAPI 对象上。
 * 按域切分的目的：多条实施道可以并行编写<strong>互不相交的文件</strong>，且文档内容集中可审。</p>
 *
 * <p><b>权威来源与纪律</b>：{@code summary}/{@code description}/错误码清单应取自
 * {@code backend/contracts/openapi/openapi.yaml}（34/34 操作已有中文 summary+description 与
 * {@code x-error-codes}）与 {@code backend/doc/}（详细设计 DD 3.2 错误码与客户端动作表、
 * DD 6/7/8/9 字段与状态机、数据架构的列语义与 revision/epoch/seq 递增规则）。
 * <strong>不得自行发明语义</strong>；权威未冻结处（如微晶参数单位、云台连接状态编码、
 * 通知 registration 结构、真实会话 token 有效期）必须显式写明"未冻结/待定"及其依据。</p>
 *
 * <p><b>不得改动</b>：任何控制器、DTO、业务服务、{@code application.yml}、
 * {@code backend/contracts/**}、{@code backend/acceptance/**}。文档-only。</p>
 */
public interface ApiDocsCatalog {

    /** 域名（用于日志与稳定排序，如 {@code "foundation"}、{@code "identity-device"}）。 */
    String domain();

    /**
     * 该域负责的标签定义（中文 name + description）。name 必须与
     * {@link ApiDocEntry#tag()} 中使用的值一致。
     */
    List<Tag> tags();

    /**
     * 操作文档表，key = {@code "METHOD path"}（大写方法 + 真实路由模板）。
     *
     * <p>引擎会校验：①生成文档中<strong>每个</strong>操作都被某个目录覆盖（覆盖率门禁，
     * 未覆盖即测试失败）；②目录中不存在生成文档里没有的多余键（防止文档与真实路由漂移）；
     * ③{@link ApiDocEntry#params()} 与生成文档的参数集合完全一致（不漏不多）。</p>
     */
    Map<String, ApiDocEntry> entries();

    /**
     * schema 属性级文档：外层 key = 生成文档中的 schema 名（通常为 DTO 的简单类名，
     * 如 {@code MemberAccessGrantResult}、{@code Progress}、{@code HeartbeatAck}），
     * 内层 key = 属性名（<strong>JSON 字段名</strong>，注意 {@code @JsonProperty} 改名，
     * 例如 {@code DeviceDtos} 中的 {@code isStale}），value = 该属性的中文文档。
     *
     * <p>引擎把它施加到 {@code components.schemas}（含为响应 {@code data} 新注册的类型），
     * 并要求<strong>每个属性都有描述</strong>（覆盖率门禁）。基线为 80 个属性 0 个有描述。</p>
     */
    Map<String, Map<String, PropertyDoc>> propertyDocs();

    /**
     * <strong>属性级 required 修正</strong>：外层 key = 生成文档中的 schema 名，
     * 内层 = 该 schema 中<strong>应当标记为必填</strong>的属性名集合。
     *
     * <p>用途：当<strong>契约</strong>要求某属性必填、而 Java 代码未以校验注解强制时，
     * springdoc 生成的 {@code required} 会缺失该属性，文档因而与权威契约不一致
     * （实例：{@code EchoJobRequestBody.numbersAsStrings} 在契约
     * {@code SystemEchoJobRequest.required} 中，但代码未强制）。本方法让目录在
     * <strong>不改任何 DTO/业务代码</strong>的前提下修正生成文档的 {@code required}。</p>
     *
     * <p>纪律：①只在"契约要求必填"时使用，<strong>不得</strong>用它放宽或 invent 必填性；
     * ②被修正的属性必须在 {@link #propertyDocs()} 的 description 中写明
     * "契约要求必填、当前实现未强制（缺失会被容忍属实现偏差）"，使联调方同时看到两个口径；
     * ③覆盖率门禁会把本方法声明的集合与契约 {@code required} 交叉校验。</p>
     *
     * <p>默认空实现：大多数目录无需修正。</p>
     */
    default Map<String, java.util.Set<String>> requiredProperties() {
        return Map.of();
    }

    /**
     * 自由结构字段（Java 侧声明为 {@code Object}/{@code Map}/{@code JsonNode}，
     * springdoc 只能生成无结构 {@code object}）的<strong>显式结构</strong>文档。
     *
     * <p>key = {@code "SchemaName.propertyName"}（如 {@code "HeartbeatBody.incidents"}、
     * {@code "Request.registration"}、{@code "MicrocrystalObservationBody.capabilities"}、
     * {@code "SkinReportView.metrics"}、{@code "CarePlanFullView.plan"}）。</p>
     *
     * <p><b>总协调硬要求</b>：大 JSON 必须明确结构<strong>及可扩展边界</strong>——即写清
     * 哪些键是封闭枚举/白名单（服务端只认这些）、哪些键开放扩展（客户端必须容忍未来新增键）、
     * 是否含 {@code schema_version}、以及哪些内部诊断键<strong>绝不外发</strong>
     * （如 {@code failure_detail}/{@code last_error} 的原始内容）。结构必须来自写入方/投影方代码
     * 或权威文档取证，<strong>不得凭空发明键名</strong>；未冻结者显式标注。</p>
     *
     * @return key = {@code "SchemaName.propertyName"}，value = 该自由结构字段的文档
     */
    Map<String, FreeFormDoc> freeFormDocs();

    /**
     * 自由结构字段的显式结构与可扩展边界。
     *
     * @param description    中文说明：用途、写入方、是否含 schema_version、投影/脱敏规则
     * @param knownKeys      已知键的文档（键名 → 类型与含义）；<strong>只列经取证的键</strong>
     * @param extensible     可扩展边界：{@code true} = 客户端必须容忍未来新增键（开放扩展）；
     *                       {@code false} = 封闭白名单，服务端只认 {@link #knownKeys} 中的键
     * @param extensibilityNote 可扩展边界的中文说明（哪些键封闭、哪些开放、版本演进规则）
     * @param example        脱敏示例 JSON 字符串（可为 {@code null}）；不得含真实 token/手机号/
     *                       推送注册凭据/内部诊断内容
     */
    record FreeFormDoc(
            String description,
            Map<String, String> knownKeys,
            boolean extensible,
            String extensibilityNote,
            String example) {
    }

    /**
     * 单个 schema 属性的中文文档。
     *
     * @param description  含义（中文）
     * @param unit         单位（如 {@code "次"}、{@code "秒"}、{@code "MiB"}、{@code "毫秒"}）；无单位传 {@code null}
     * @param allowedValues 封闭枚举的全部合法值（顺序即文档展示顺序）；非枚举传 {@code null}
     * @param example      脱敏示例值（JSON 字面量字符串，如 {@code "1"}、{@code "2026-09-13T08:30:00Z"}、
     *                     {@code "needs_retake"}）；可为 {@code null}
     * @param format       需要覆盖/补充的 OpenAPI format（如 {@code "date-time"}、{@code "uuid"}）；
     *                     可为 {@code null}
     */
    record PropertyDoc(
            String description,
            String unit,
            List<String> allowedValues,
            String example,
            String format) {

        public static PropertyDoc of(String description) {
            return new PropertyDoc(description, null, null, null, null);
        }

        public static PropertyDoc of(String description, String example) {
            return new PropertyDoc(description, null, null, example, null);
        }

        public static PropertyDoc enumOf(String description, List<String> allowedValues, String example) {
            return new PropertyDoc(description, null, allowedValues, example, null);
        }

        public static PropertyDoc unitOf(String description, String unit, String example) {
            return new PropertyDoc(description, unit, null, example, null);
        }
    }
}
