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
     * <p>springdoc 只从 Bean Validation 注解（{@code @NotNull} 等）推导 {@code required}，
     * 本项目的 DTO 多为 record 且以<strong>手工校验</strong>为主，故生成结果与权威契约不一致。
     * 本方法让目录在<strong>不改任何 DTO/业务代码</strong>的前提下，把 {@code required}
     * 修正为与契约一致。覆盖率门禁会把它与契约 {@code required} 交叉校验
     * （<strong>少于</strong>契约 = 未修正；<strong>多于</strong>契约 = invent，两者皆构建失败）。</p>
     *
     * <p><b>两种方向的语义不同，描述口径必须区分（不得混为一谈）</b>：</p>
     * <ol>
     *   <li><strong>请求体 schema</strong>：契约要求必填。此时须进一步区分——
     *     <ul>
     *       <li>服务端<strong>确实强制</strong>（如 multipart 解析器/控制器手工校验，缺失即
     *           400 {@code INVALID_INPUT} + {@code details.fields}）⇒ 在 {@link #propertyDocs()}
     *           的描述中写明"服务端强制、只是未用注解声明，<strong>这不是实现偏差</strong>"；</li>
     *       <li>服务端<strong>并不强制</strong>（如 {@code EchoJobRequestBody.numbersAsStrings}）
     *           ⇒ 必须写明"契约要求必填、当前实现未强制（缺失会被容忍）属<strong>实现偏差</strong>，
     *           不得据此改写契约"。</li>
     *     </ul>
     *   </li>
     *   <li><strong>响应 schema</strong>：契约的 {@code required} 表达的是<strong>服务端保证该键必然存在</strong>。
     *       record 组件恒被序列化，故未列入 {@code required} 的字段意为"可能为 {@code null}
     *       或在某些视图下省略，客户端<strong>不得依赖</strong>"（例如 {@code AssessmentTaskView}
     *       的 {@code failureCode}/{@code reportId} 仅在对应状态下有值、{@code VerificationDto.validUntil}
     *       当前恒为 null）。这<strong>不是</strong>实现偏差，描述中不得如此表述。</li>
     * </ol>
     *
     * <p>纪律：①声明集合必须<strong>逐字等于</strong>契约对应 schema 的 {@code required}
     * （请用 snakeyaml 实读契约核实，<strong>不得</strong>凭 DTO 字段推断）；
     * ②不得用它放宽或 invent 必填性；③契约未声明 {@code required} 的 schema 不要声明。</p>
     *
     * <p>默认空实现。</p>
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
     * <strong>递归的</strong>结构化已知键定义，用于自由结构字段<strong>内部</strong>的嵌套类型。
     *
     * <p><b>为何需要它</b>：{@link FreeFormDoc#knownKeys()} 的值是"类型前缀 + 中文说明"的一层 DSL，
     * 引擎对 {@code array} 只能生成 {@code array<string>}。而真实结构常是嵌套的，例如
     * {@code CarePlanFullView.plan.steps} 实为 {@code array<object{region, parameters}>}
     * （权威源 {@code CarePlanProjection.projectStep/projectParameters/projectParameter}）、
     * {@code ErrorBody.details.missingRanges} 实为 {@code array<object{from,to}>}
     * （权威源契约 {@code components.schemas.MissingRange}，两键均必填、封闭）。
     * 若文档写成 {@code array<string>}，Swagger UI 与代码生成器会产出<strong>与真实响应冲突</strong>的
     * 客户端模型——这比缺少描述更有害。</p>
     *
     * <p><b>纪律</b>：结构必须来自<strong>写入方/投影方代码</strong>或<strong>权威契约</strong>取证，
     * 不得发明键名；未冻结的层级用 {@link #opaqueObject(String)}（显式开放、无已知键）表达，
     * 而不是猜测其内部结构。</p>
     *
     * @param type                       {@code object}/{@code array}/{@code string}/{@code integer}/
     *                                   {@code number}/{@code boolean}；另支持 {@code any} =
     *                                   <strong>不写 type 关键字</strong>、仅给 description，
     *                                   用于"标量或对象"这类真实存在的联合形态
     *                                   （例：{@code CarePlanProjection.projectParameter} 允许参数值
     *                                   直接是标量，也允许 {@code {value, unit}} 对象；而 {@code value}
     *                                   本身可为 string/number/boolean）。
     *                                   <strong>不得</strong>用 {@code any} 规避取证——
     *                                   凡能确定单一类型者必须写明具体类型
     * @param description                中文说明（含义、来源、单位、未冻结状态）
     * @param properties                 {@code type=object} 时的已知键（递归）；否则为 {@code null}/空
     * @param items                      {@code type=array} 时的元素结构（递归）；否则为 {@code null}
     * @param additionalProperties       {@code type=object} 时的可扩展边界：{@code TRUE} = 开放扩展
     *                                   （客户端必须容忍未来新增键）、{@code FALSE} = 封闭白名单
     *                                   （服务端只认 {@link #properties} 中的键）、{@code null} = 不设置该关键字
     * @param additionalPropertiesSchema {@code type=object} 且键名<strong>不固定</strong>（动态映射，
     *                                   如 {@code {参数名: 参数定义}}）时，给出<strong>值</strong>的递归结构，
     *                                   引擎据此生成 {@code additionalProperties: <该结构>}；
     *                                   非动态映射传 {@code null}
     * @param example                    脱敏示例（JSON 字面量字符串），可为 {@code null}
     */
    record KnownKeyDoc(
            String type,
            String description,
            Map<String, KnownKeyDoc> properties,
            KnownKeyDoc items,
            Boolean additionalProperties,
            KnownKeyDoc additionalPropertiesSchema,
            String example) {

        public static KnownKeyDoc str(String description) {
            return new KnownKeyDoc("string", description, null, null, null, null, null);
        }

        public static KnownKeyDoc str(String description, String example) {
            return new KnownKeyDoc("string", description, null, null, null, null, example);
        }

        public static KnownKeyDoc integer(String description) {
            return new KnownKeyDoc("integer", description, null, null, null, null, null);
        }

        public static KnownKeyDoc number(String description) {
            return new KnownKeyDoc("number", description, null, null, null, null, null);
        }

        public static KnownKeyDoc bool(String description) {
            return new KnownKeyDoc("boolean", description, null, null, null, null, null);
        }

        /** 数组；{@code items} 必须是完整的递归定义（不得为 {@code null}）。 */
        public static KnownKeyDoc array(KnownKeyDoc items, String description) {
            return new KnownKeyDoc("array", description, null, items, null, null, null);
        }

        /** 封闭白名单对象：{@code additionalProperties=false}，服务端只认列出的键。 */
        public static KnownKeyDoc closedObject(Map<String, KnownKeyDoc> properties, String description) {
            return new KnownKeyDoc("object", description, properties, null, Boolean.FALSE, null, null);
        }

        /** 开放扩展对象：{@code additionalProperties=true}，已知键之外的未来键客户端必须容忍。 */
        public static KnownKeyDoc openObject(Map<String, KnownKeyDoc> properties, String description) {
            return new KnownKeyDoc("object", description, properties, null, Boolean.TRUE, null, null);
        }

        /**
         * 动态映射：键名不固定（如 {@code {参数名: 参数定义}}），值结构由 {@code valueSchema} 给出，
         * 引擎生成 {@code type=object} + {@code additionalProperties: <valueSchema>}。
         */
        public static KnownKeyDoc mapOf(KnownKeyDoc valueSchema, String description) {
            return new KnownKeyDoc("object", description, Map.of(), null, Boolean.TRUE, valueSchema, null);
        }

        /**
         * 显式不透明的嵌套对象：无已知键、{@code additionalProperties=true}。
         * 用于"结构未冻结"的层级——<strong>诚实标注而非猜测</strong>。
         */
        public static KnownKeyDoc opaqueObject(String description) {
            return new KnownKeyDoc("object", description, Map.of(), null, Boolean.TRUE, null, null);
        }
    }

    /**
     * <strong>嵌套结构化键</strong>：为自由结构字段内部的键给出<strong>递归</strong>类型定义。
     *
     * <p>外层 key 与 {@link #freeFormDocs()} 同键空间（{@code "SchemaName.propertyName"}）；
     * 内层 key = 该自由结构字段的<strong>顶层已知键名</strong>，value = 其递归结构。</p>
     *
     * <p><b>与 {@link FreeFormDoc#knownKeys()} 的关系</b>：两者按<strong>并集</strong>施加，
     * 同名键以本方法（结构化定义）为准。只需为<strong>真正嵌套</strong>的键使用本方法
     * （数组元素为对象、对象内部还有对象/映射）；一层标量键继续用 {@code knownKeys} 即可。</p>
     *
     * <p>覆盖率门禁会<strong>递归</strong>检查生成结果：任何 {@code object} 必须有 {@code properties}
     * 或显式 {@code additionalProperties}（或属经核准的显式不透明声明）；任何 {@code array} 必须有
     * 带 {@code type} 的 {@code items}。把对象数组写成 {@code array<string>} 会直接构建失败。</p>
     *
     * <p>默认空实现：只有存在嵌套结构的目录需要覆写。</p>
     */
    default Map<String, Map<String, KnownKeyDoc>> structuredKeys() {
        return Map.of();
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
