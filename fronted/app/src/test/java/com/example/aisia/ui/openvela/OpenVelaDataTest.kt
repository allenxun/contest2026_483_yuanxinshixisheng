package com.example.aisia.ui.openvela
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class OpenVelaDataTest {
    @Test(expected=IllegalArgumentException::class) fun missingListIsNotEmptySuccess() {
        OpenVelaData.people(JSONObject("{}"))
    }
    @Test(expected=IllegalArgumentException::class) fun readyPlanRequiresBody() {
        OpenVelaData.plan(JSONObject("{\"planId\":\"p\",\"generationStatus\":\"ready\"}"))
    }
    @Test fun peopleUseServerNameAndMissingAvatarStaysNull() {
        val p = OpenVelaData.people(JSONObject("""{"items":[{"memberId":"m1","name":"测试姓名"}],"nextCursor":"opaque+/="}"""))
        assertEquals("测试姓名", p.items.single().name)
        assertNull(p.items.single().faceImageUrl)
        assertEquals("opaque+/=",p.next)
    }
    @Test fun nestedMemberAndAvatarAreRead() {
        val p=OpenVelaData.people(JSONObject("""{"items":[{"memberId":"m1","member":{"displayName":"服务端人员","avatarUrl":"/api/v1/media/a/content"}}]}"""))
        assertEquals("服务端人员",p.items.single().name)
        assertEquals("/api/v1/media/a/content",p.items.single().faceImageUrl)
    }
    @Test fun missingNameNeverInventsPerson() {
        assertEquals("未返回姓名",OpenVelaData.people(JSONObject("""{"items":[{"memberId":"m"}]}""")).items.single().name)
        assertTrue(OpenVelaData.people(JSONObject("""{"items":[]}""")).items.isEmpty())
    }
    @Test fun metricsUseServerValuesNotDemoScore() {
        val r=OpenVelaData.report(JSONObject("""{"reportId":"r","memberId":"m","metrics":[{"name":"水分","value":35.2,"unit":"%"}]}"""),"m")
        assertNull(r.score)
        assertEquals("35.2 %",r.metrics.single().second)
    }
    @Test(expected=IllegalArgumentException::class) fun wrongMemberRejected() {
        OpenVelaData.report(JSONObject("""{"reportId":"r","memberId":"other"}"""),"m")
    }
    @Test fun unlabelledImagesAreNotAssumedToBeFaceAngles() {
        val r=OpenVelaData.report(JSONObject("""{"reportId":"r","images":[{"contentUrl":"/one"},{"view":"left","contentUrl":"/left"}]}"""),"m")
        assertEquals("/left",r.leftFaceImageUrl);assertNull(r.frontFaceImageUrl)
        assertEquals(2,r.images.size)
    }
    @Test fun waitingPlanDoesNotInventSteps() {
        val p=OpenVelaData.plan(JSONObject("""{"planId":"p","generationStatus":"generating","plan":null}"""))
        assertEquals("generating",p.status);assertTrue(p.steps.isEmpty())
    }
    @Test fun readyPlanUsesApiParametersAndStringCounters() {
        val p=OpenVelaData.plan(JSONObject("""{"planId":"p","generationStatus":"ready","plan":{"title":"服务端方案","steps":[{"region":"face","parameters":{"strength":{"value":"3","unit":"level"}}}]},"progress":{"targetCount":"10","completedCount":"11","remainingCount":"0"}}"""))
        assertEquals("服务端方案",p.title)
        assertTrue(p.steps.single().second.contains("3 level"))
        assertTrue(p.progress.contains("已完成 11"))
    }
}
