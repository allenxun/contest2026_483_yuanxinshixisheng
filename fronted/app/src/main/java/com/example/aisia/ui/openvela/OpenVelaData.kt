package com.example.aisia.ui.openvela

import org.json.JSONObject

/** Real API projections. Missing data never creates demonstration records. */
object OpenVelaData {
    data class Person(val id: String, val name: String, val description: String,
        val faceImageUrl: String? = null, val demoAvatarIndex: Int? = null)
    data class Report(val id: String, val personId: String, val date: String, val score: Int? = null,
        val leftFaceImageUrl: String? = null, val frontFaceImageUrl: String? = null,
        val rightFaceImageUrl: String? = null, val conclusion: String = "",
        val description: String = "", val metrics: List<Pair<String, String>> = emptyList(),
        val images: List<Pair<String, String>> = emptyList())
    data class Plan(val id: String, val status: String, val title: String, val description: String,
        val steps: List<Pair<String, String>>, val progress: String)
    data class Page<T>(val items: List<T>, val next: String?)
    fun text(o: JSONObject, vararg keys: String): String? =
        keys.asSequence().mapNotNull { k -> (o.opt(k) as? String)?.trim()?.takeIf { it.isNotEmpty() && it != "null" } }.firstOrNull()
    fun objects(o: JSONObject, key: String): List<JSONObject> {
        val a = o.optJSONArray(key) ?: return emptyList()
        return (0 until a.length()).mapNotNull { a.optJSONObject(it) }
    }
    private fun id(o: JSONObject, key: String) = text(o, key) ?: error("接口缺少 " + key)
    private fun rows(o: JSONObject): List<JSONObject> {
        require(o.optJSONArray("items") != null) { "列表字段缺失" }
        return objects(o, "items")
    }
    fun people(o: JSONObject) = Page(rows(o).map {
        val member = it.optJSONObject("member") ?: it
        Person(id(it, "memberId"), text(member, "name", "memberName", "displayName") ?: text(it, "name", "memberName") ?: "未返回姓名",
            text(member, "description") ?: "查看测肤记录",
            text(member, "avatarUrl", "avatar", "faceImageUrl") ?: text(it, "avatarUrl", "avatar", "faceImageUrl"))
    }.distinctBy { it.id }, text(o, "nextCursor"))
    fun report(o: JSONObject, memberId: String): Report {
        val owner = text(o, "memberId")
        require(owner == null || owner == memberId) { "报告与当前人员不匹配" }
        val imgs = objects(o, "images")
        fun angle(view: String) = imgs.firstOrNull { text(it, "view", "angle") == view }?.let { text(it, "contentUrl") }
        return Report(id(o, "reportId"), memberId, text(o, "reportReadyAt") ?: "时间未返回",
            leftFaceImageUrl = angle("left"), frontFaceImageUrl = angle("front"), rightFaceImageUrl = angle("right"),
            conclusion = text(o, "conclusion") ?: o.optJSONObject("reportSummary")?.let { text(it, "conclusion") }.orEmpty(),
            description = text(o, "description").orEmpty(),
            metrics = objects(o, "metrics").mapNotNull {
                val name = text(it, "name") ?: return@mapNotNull null
                val v = it.opt("value") as? Number ?: return@mapNotNull null
                name to (v.toString() + " " + text(it, "unit").orEmpty()).trim()
            }, images = imgs.mapIndexedNotNull { i, img -> text(img, "contentUrl")?.let { (text(img, "view", "angle") ?: ("结果图片 " + (i + 1))) to it } })
    }
    fun reports(o: JSONObject, memberId: String) = Page(rows(o).map { report(it, memberId) }.distinctBy { it.id }, text(o, "nextCursor"))
    fun plan(o: JSONObject): Plan {
        val state = id(o, "generationStatus")
        val p = o.optJSONObject("plan")
        require(state != "ready" || p != null) { "就绪方案缺少正文" }
        val progress = o.optJSONObject("progress")
        fun params(j: JSONObject?): String = j?.keys()?.asSequence()?.map { key ->
            val v = j.opt(key)
            if (v is JSONObject) key + "：" + (v.opt("value") ?: "") + " " + text(v, "unit").orEmpty() else key + "：" + v
        }?.joinToString("\n").orEmpty()
        return Plan(id(o, "planId"), state, p?.let { text(it, "title") } ?: "护肤方案",
            p?.let { text(it, "description") }.orEmpty(), p?.let { objects(it, "steps").mapIndexed { i, step ->
                (text(step, "region") ?: ("护理步骤 " + (i + 1))) to params(step.optJSONObject("parameters"))
            } }.orEmpty(),
            progress?.let { "目标 " + (text(it, "targetCount") ?: "—") + " 次 · 已完成 " + (text(it, "completedCount") ?: "—") + " 次 · 剩余 " + (text(it, "remainingCount") ?: "—") + " 次" }.orEmpty())
    }
}
object OpenVelaCommands {
    const val INITIALIZE = 'a'
    const val START = 'b'
    const val STOP = 'c'
    const val QUERY = 'd'
}
