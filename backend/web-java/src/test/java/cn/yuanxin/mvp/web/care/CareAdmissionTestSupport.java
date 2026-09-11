package cn.yuanxin.mvp.web.care;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;

import java.nio.charset.StandardCharsets;
import java.util.UUID;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;

/** M4-A03 / M4-A04 集成测试共用：合法 PNG 字节、multipart 提交与 metadata JSON 构造。 */
final class CareAdmissionTestSupport {

    /** 合法 PNG 头（参照 MediaFoundationIT.PNG）。 */
    static final byte[] PNG = new byte[]{(byte) 0x89, 'P', 'N', 'G', 0x0D, 0x0A, 0x1A, 0x0A,
            0, 0, 0, 9, 'I', 'H', 'D', 'R'};

    /** 非图片字节（触发 UNSUPPORTED_IMAGE）。 */
    static final byte[] NOT_IMAGE = new byte[]{1, 2, 3, 4, 5, 6, 7, 8};

    static final String CAPTURED_AT = "2026-09-10T04:00:00Z";

    private static final ObjectMapper M = new ObjectMapper();

    private CareAdmissionTestSupport() {
    }

    // ---------- metadata ----------

    static ObjectNode capture(String captureId, String capturedAt, String continuityId,
                              String purpose) {
        ObjectNode c = M.createObjectNode();
        c.put("captureId", captureId);
        c.put("capturedAt", capturedAt);
        c.put("clientContinuityId", continuityId);
        c.put("purpose", purpose);
        return c;
    }

    static String admissionMetadata(UUID microcrystalId, String connectionProof, UUID planId,
                                    UUID currentTaskId, String currentAssessmentRevision,
                                    ObjectNode capture, String consentEvidenceRef) {
        ObjectNode n = M.createObjectNode();
        n.put("microcrystalId", microcrystalId.toString());
        n.put("connectionProof", connectionProof);
        n.set("capture", capture);
        n.put("consentEvidenceRef", consentEvidenceRef);
        if (planId != null) {
            n.put("planId", planId.toString());
        }
        if (currentTaskId != null) {
            n.put("currentTaskId", currentTaskId.toString());
        }
        if (currentAssessmentRevision != null) {
            n.put("currentAssessmentRevision", currentAssessmentRevision);
        }
        return n.toString();
    }

    static String revalidationMetadata(String expectedRevision, ObjectNode capture,
                                       String consentEvidenceRef, JsonNode reportedState) {
        ObjectNode n = M.createObjectNode();
        n.put("expectedVerificationRevision", expectedRevision);
        n.set("capture", capture);
        n.put("consentEvidenceRef", consentEvidenceRef);
        if (reportedState != null) {
            n.set("reportedMicrocrystalState", reportedState);
        }
        return n.toString();
    }

    static JsonNode json(String raw) {
        try {
            return M.readTree(raw);
        } catch (Exception e) {
            throw new IllegalArgumentException(e);
        }
    }

    // ---------- M4-A05 / A06 JSON ----------

    static String observationJson(String epoch, String seq, String state, String occurredAt,
                                  String verificationRevision, Boolean continuityValid) {
        ObjectNode n = M.createObjectNode();
        n.put("epoch", epoch);
        n.put("seq", seq);
        n.put("state", state);
        n.put("occurredAt", occurredAt);
        if (verificationRevision != null) {
            n.put("verificationRevision", verificationRevision);
        }
        if (continuityValid != null) {
            n.put("continuityValid", continuityValid);
        }
        return n.toString();
    }

    static String recordJson(String recordId, String sourceEpoch, String sourceSeq, String countDelta,
                             String occurredAt) {
        ObjectNode n = M.createObjectNode();
        n.put("recordId", recordId);
        n.put("sourceEpoch", sourceEpoch);
        n.put("sourceSeq", sourceSeq);
        n.put("countDelta", countDelta);
        n.put("occurredAt", occurredAt);
        return n.toString();
    }

    static String syncBody(String observationJsonOrNull, java.util.List<String> recordJsons) {
        ObjectNode n = M.createObjectNode();
        if (observationJsonOrNull != null) {
            n.set("observation", json(observationJsonOrNull));
        } else {
            n.putNull("observation");
        }
        var records = n.putArray("records");
        for (String record : recordJsons) {
            records.add(json(record));
        }
        return n.toString();
    }

    static String closureBody(String stopObservationSeq, String reason, String recordStreamEpoch,
                              String finalRecordSeq, String finalCount) {
        ObjectNode n = M.createObjectNode();
        n.put("stopObservationSeq", stopObservationSeq);
        n.put("reason", reason);
        n.put("recordStreamEpoch", recordStreamEpoch);
        n.put("finalRecordSeq", finalRecordSeq);
        n.put("finalCount", finalCount);
        return n.toString();
    }

    static MvcResult postJson(MockMvc mvc, String token, String path, String key, String body)
            throws Exception {
        MockHttpServletRequestBuilder builder = org.springframework.test.web.servlet.request
                .MockMvcRequestBuilders.post(path)
                .contentType(org.springframework.http.MediaType.APPLICATION_JSON)
                .content(body.getBytes(StandardCharsets.UTF_8));
        return perform(mvc, builder, token, key);
    }

    // ---------- multipart ----------

    static MvcResult admit(MockMvc mvc, String token, String key, String metadataJson,
                           byte[] face) throws Exception {
        MockHttpServletRequestBuilder builder = multipart("/api/v1/care-executions")
                .file(metadataPart(metadataJson))
                .file(facePart(face));
        return perform(mvc, builder, token, key);
    }

    static MvcResult revalidate(MockMvc mvc, String token, UUID executionId, String key,
                                String metadataJson, byte[] face) throws Exception {
        MockHttpServletRequestBuilder builder =
                multipart("/api/v1/care-executions/" + executionId + "/revalidations")
                        .file(metadataPart(metadataJson))
                        .file(facePart(face));
        return perform(mvc, builder, token, key);
    }

    private static MvcResult perform(MockMvc mvc, MockHttpServletRequestBuilder builder,
                                     String token, String key) throws Exception {
        if (token != null) {
            builder.header("Authorization", "Bearer " + token);
        }
        if (key != null) {
            builder.header("Idempotency-Key", key);
        }
        return mvc.perform(builder).andReturn();
    }

    private static MockMultipartFile metadataPart(String json) {
        return new MockMultipartFile("metadata", null, "application/json",
                json.getBytes(StandardCharsets.UTF_8));
    }

    private static MockMultipartFile facePart(byte[] face) {
        return new MockMultipartFile("face", "face.png", "image/png", face);
    }

    static String newKey() {
        return "key-" + UUID.randomUUID();
    }
}
