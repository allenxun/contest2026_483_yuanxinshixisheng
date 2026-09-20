package cn.yuanxin.mvp.web.assessments;

import cn.yuanxin.mvp.web.assessments.dto.SkinReportListItem;
import cn.yuanxin.mvp.web.assessments.dto.SkinReportView;
import cn.yuanxin.mvp.web.assessments.dto.SkinReportView.SkinReportImage;
import cn.yuanxin.mvp.web.auth.PrincipalContext;
import cn.yuanxin.mvp.web.auth.PrincipalType;
import cn.yuanxin.mvp.web.error.ApiException;
import cn.yuanxin.mvp.web.error.ErrorCode;
import cn.yuanxin.mvp.web.web.CursorCodec;
import cn.yuanxin.mvp.web.web.CursorException;
import cn.yuanxin.mvp.web.web.EnvelopeSupport;
import cn.yuanxin.mvp.web.web.ListData;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.stereotype.Service;

import java.time.Instant;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;

/**
 * M3-A04 报告列表 / M3-A05 报告受控投影（DD 5、6.1、8.6）。
 * 只从冻结 report_payload 白名单投影；model_info 与未知键绝不输出。
 */
@Service
public class SkinReportService {

    private final AssessmentRepository assessmentRepository;
    private final AssessmentGimbalRepository gimbalRepository;
    private final AssessmentAccessRepository accessRepository;
    private final CursorCodec cursorCodec;
    private final ObjectMapper objectMapper;

    public SkinReportService(AssessmentRepository assessmentRepository,
                             AssessmentGimbalRepository gimbalRepository,
                             AssessmentAccessRepository accessRepository,
                             CursorCodec cursorCodec,
                             ObjectMapper objectMapper) {
        this.assessmentRepository = assessmentRepository;
        this.gimbalRepository = gimbalRepository;
        this.accessRepository = accessRepository;
        this.cursorCodec = cursorCodec;
        this.objectMapper = objectMapper;
    }

    // ----------------------------------------------------------------- A04

    public ListData<SkinReportListItem> listReports(UUID memberId, Integer limit, String cursor,
                                                    PrincipalContext principal) {
        if (principal.principalType() == PrincipalType.GIMBAL) {
            throw new ApiException(ErrorCode.CALLER_NOT_ALLOWED,
                    "report history is not available to gimbals");
        }
        if (!accessRepository.hasActiveGrant(principal.accountUuid(), memberId)) {
            throw notVisible();
        }
        int fetchSize = cursorCodec.normalizeLimit(limit) + 1;
        Instant cursorTime = null;
        UUID cursorId = null;
        if (cursor != null && !cursor.isBlank()) {
            CursorCodec.Cursor decoded = cursorCodec.decode(cursor);
            if (!memberId.toString().equals(decoded.filterDigest())) {
                throw new CursorException("cursor does not match request filters");
            }
            try {
                cursorTime = Instant.parse(decoded.sortValue());
                cursorId = UUID.fromString(decoded.id());
            } catch (Exception e) {
                throw new CursorException("cursor is not a valid opaque token");
            }
        }
        List<AssessmentRepository.ReportListRow> rows = assessmentRepository.listReports(
                memberId, cursorTime, cursorId, fetchSize);

        boolean hasMore = rows.size() > fetchSize - 1;
        int size = hasMore ? fetchSize - 1 : rows.size();
        List<SkinReportListItem> items = new ArrayList<>(size);
        for (int i = 0; i < size; i++) {
            AssessmentRepository.ReportListRow row = rows.get(i);
            items.add(new SkinReportListItem(
                    row.reportId().toString(),
                    row.reportReadyAt() == null ? null : EnvelopeSupport.rfc3339(row.reportReadyAt()),
                    parseJson(row.reportSummary())));
        }
        String nextCursor = null;
        if (hasMore) {
            AssessmentRepository.ReportListRow last = rows.get(size - 1);
            nextCursor = cursorCodec.encode(last.reportReadyAt().toString(),
                    last.id().toString(), memberId.toString());
        }
        return new ListData<>(items, nextCursor);
    }

    // ----------------------------------------------------------------- A05

    public SkinReportView getReport(UUID reportId, String view, PrincipalContext principal) {
        boolean fullRequested = false;
        if (view != null) {
            if (!"full".equals(view) && !"brief".equals(view)) {
                throw new ApiException(ErrorCode.INVALID_INPUT, "view must be full or brief");
            }
            fullRequested = "full".equals(view);
        }
        AssessmentRepository.ReportRow row = assessmentRepository.findByReportId(reportId)
                .orElseThrow(SkinReportService::notVisible);
        if (!"report_ready".equals(row.status())) {
            throw notVisible();
        }

        String effectiveView;
        if (principal.principalType() == PrincipalType.APP) {
            if (row.memberId() == null
                    || !accessRepository.hasActiveGrant(principal.accountUuid(), row.memberId())) {
                throw notVisible();
            }
            effectiveView = view != null ? view : "full";
        } else {
            if (!principal.gimbalUuid().equals(row.gimbalId())) {
                throw notVisible();
            }
            AssessmentGimbalRepository.Pointer pointer = gimbalRepository
                    .findById(principal.gimbalUuid())
                    .orElseThrow(SkinReportService::notVisible);
            if (!row.id().equals(pointer.currentAssessmentId())) {
                throw new ApiException(ErrorCode.TASK_REPLACED,
                        "report belongs to a replaced task");
            }
            if (fullRequested) {
                throw new ApiException(ErrorCode.CALLER_NOT_ALLOWED,
                        "gimbal may only read the brief report view");
            }
            effectiveView = "brief";
        }

        return project(row, effectiveView, reportId);
    }

    private SkinReportView project(AssessmentRepository.ReportRow row, String effectiveView,
                                   UUID reportId) {
        boolean full = "full".equals(effectiveView);
        JsonNode payload = parsePayload(row.reportPayload());
        validateStructure(payload);
        String conclusion = textOrNull(payload.get("conclusion"));
        String description = full ? textOrNull(payload.get("description")) : null;
        List<Map<String, Object>> metrics = full ? projectMetrics(payload.get("metrics")) : null;
        List<SkinReportImage> images = projectImages(payload.get("images"));
        String memberId = full && row.memberId() != null ? row.memberId().toString() : null;
        String readyAt = row.reportReadyAt() == null ? null
                : EnvelopeSupport.rfc3339(row.reportReadyAt());
        String planStatus = accessRepository.planStatusByAssessmentId(row.id()).orElse(null);
        return new SkinReportView(reportId.toString(), effectiveView, memberId, readyAt,
                conclusion, metrics, description, images, planStatus);
    }

    private JsonNode parsePayload(String raw) {
        if (raw == null) {
            throw new ApiException(ErrorCode.INTERNAL, "report payload unavailable");
        }
        try {
            JsonNode node = objectMapper.readTree(raw);
            if (node != null && node.isObject()) {
                return node;
            }
        } catch (Exception e) {
            // fallthrough: 不泄露原始内容
        }
        throw new ApiException(ErrorCode.INTERNAL, "report payload unavailable");
    }

    /**
     * 冻结载荷内部结构类型校验：字段存在时类型必须匹配，否则视为损坏 →
     * 500 INTERNAL（绝不透传原始内容）。缺省/JSON null 合法。
     */
    private void validateStructure(JsonNode payload) {
        requireTextualOrNull(payload.get("conclusion"));
        requireTextualOrNull(payload.get("description"));
        requireArrayOrNull(payload.get("metrics"));
        requireArrayOrNull(payload.get("images"));
    }

    private void requireTextualOrNull(JsonNode node) {
        if (node != null && !node.isNull() && !node.isMissingNode() && !node.isTextual()) {
            throw new ApiException(ErrorCode.INTERNAL, "report payload malformed");
        }
    }

    private void requireArrayOrNull(JsonNode node) {
        if (node != null && !node.isNull() && !node.isMissingNode() && !node.isArray()) {
            throw new ApiException(ErrorCode.INTERNAL, "report payload malformed");
        }
    }

    private JsonNode parseJson(String raw) {
        if (raw == null) {
            return null;
        }
        try {
            return objectMapper.readTree(raw);
        } catch (Exception e) {
            return null;
        }
    }

    private List<Map<String, Object>> projectMetrics(JsonNode metricsNode) {
        List<Map<String, Object>> out = new ArrayList<>();
        if (metricsNode == null || !metricsNode.isArray()) {
            return out;
        }
        for (JsonNode item : metricsNode) {
            if (!item.isObject()) {
                continue;
            }
            Map<String, Object> metric = new LinkedHashMap<>();
            copy(metric, "name", item.get("name"));
            copy(metric, "value", item.get("value"));
            copy(metric, "unit", item.get("unit"));
            out.add(metric);
        }
        return out;
    }

    private void copy(Map<String, Object> target, String key, JsonNode value) {
        if (value == null || value.isMissingNode() || value.isNull()) {
            return;
        }
        target.put(key, objectMapper.convertValue(value, Object.class));
    }

    private List<SkinReportImage> projectImages(JsonNode imagesNode) {
        List<SkinReportImage> out = new ArrayList<>();
        if (imagesNode == null || !imagesNode.isArray()) {
            return out;
        }
        for (JsonNode item : imagesNode) {
            if (!item.isObject()) {
                continue;
            }
            JsonNode mediaId = item.get("media_id");
            if (mediaId != null && mediaId.isTextual()) {
                out.add(new SkinReportImage(mediaId.asText(),
                        "/api/v1/media/" + mediaId.asText() + "/content"));
            }
        }
        return out;
    }

    private static String textOrNull(JsonNode node) {
        return node != null && node.isTextual() ? node.asText() : null;
    }

    private static ApiException notVisible() {
        return new ApiException(ErrorCode.RESOURCE_NOT_VISIBLE, "report not visible");
    }
}
