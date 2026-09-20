package com.example.aisia.ui.report

import android.util.Log
import org.json.JSONArray
import org.json.JSONObject

/**
 * 报告数据解析工具类
 * 从 SkinReportActivity 抽取的公共解析逻辑，供报告详情/对比页复用
 */
object ReportParser {

    private const val TAG = "ReportParser"

    // ────── 数据模型 ──────

    data class RadarItem(val name: String, val value: Int)

    data class DetectTableRow(
        val zone: String,
        val score: String,
        val count: String,
        val pixelLength: String,
        val avgLength: String,
        val maxLength: String,
        val density: String,
        val ratio: String,
        val area: String,
        val regionImageUrl: String = ""
    )

    data class DetectData(
        val name: String,
        val description: String,
        val suggestion: String,
        val faceImage: String,
        val hasData: Boolean,
        val table: List<DetectTableRow>
    )

    /** 报告级改善建议（improvement_suggestions / summary.suggestions） */
    data class SuggestionItem(val title: String, val description: String)

    data class ReportDetail(
        val overallScore: Int = 0,
        val skinType: String = "",
        val moistureLevel: Int = 0,
        val skinAge: Int? = null,
        val skinAgeScore: Int? = null,
        val elasticityScore: Int = 0,
        val elasticityX: List<Number> = emptyList(),
        val elasticityY: List<Number> = emptyList(),
        val referenceScore: Int = 0,
        val radarItems: List<RadarItem> = emptyList(),
        val redness: DetectData = emptyDetect("红区"),
        val spots: DetectData = emptyDetect("色斑"),
        val brown: DetectData = emptyDetect("棕区"),
        val purple: DetectData = emptyDetect("紫区"),
        val pores: DetectData = emptyDetect("毛孔"),
        val texture: DetectData = emptyDetect("纹理"),
        val wrinkle: DetectData = emptyDetect("皱纹"),
        val acne: DetectData = emptyDetect("痘痘"),
        val createdAt: String = "",
        val reportImageUrl: String = "",
        val suggestions: List<SuggestionItem> = emptyList()
    )

    // ────── 入口方法 ──────

    fun parseReportJson(json: JSONObject): ReportDetail {
        // 新版后端结构（报告详情接口）：根级 overall_score/radar/summary + raw_result 检测项对象
        if (json.has("summary") || json.has("radar") || json.has("overall_score")) {
            try {
                return parseApiSchema(json)
            } catch (e: Exception) {
                Log.w(TAG, "parseApiSchema failed, fallback to legacy parse", e)
            }
        }
        val rawResultStr = json.optString("raw_result", "")
        if (rawResultStr.isNotBlank()) {
            try {
                val rawResult = JSONObject(rawResultStr)
                return parseRawResult(rawResult).copy(
                    createdAt = json.optString("created_at", json.optString("create_time", "")),
                    reportImageUrl = json.optString("report_image_url", "")
                )
            } catch (e: Exception) {
                Log.w(TAG, "parse raw_result failed, fallback to direct parse", e)
            }
        }
        return parseDirectJson(json)
    }

    // ────── 新版后端结构解析 ──────
    // 实际返回结构（GET /faces/{faceId}/reports/{reportId}）：
    //   根级: overall_score / radar[{name,value}] / summary{skin_type,skin_score,moisture_level,
    //         elasticity{score,skin_age,reference_curve{x[],y[]}},suggestions}
    //         / improvement_suggestions[{title,description}] / created_at(秒级时间戳)
    //   raw_result: {wrinkle, acne, redness, spots, brown, texture, pores, purple}
    private fun parseApiSchema(json: JSONObject): ReportDetail {
        val summary = json.optJSONObject("summary")

        val skinType = summary?.optString("skin_type", "") ?: ""

        // 总得分：优先 summary.skin_score（与列表页一致），兜底根级 overall_score
        var score = if (summary != null && summary.has("skin_score")) summary.optInt("skin_score", 0) else 0
        if (score <= 0) score = json.optInt("overall_score", 0)

        // 水分档位（兼容数字/字符串）
        val moistureLevel = summary?.optString("moisture_level", "")?.toIntOrNull()
            ?: summary?.optInt("moisture_level", 0) ?: 0

        // 弹性
        val elasticity = summary?.optJSONObject("elasticity")
        val elasticityScore = elasticity?.optInt("score", 0) ?: 0
        val skinAge = if (elasticity != null && elasticity.has("skin_age")) elasticity.optInt("skin_age") else null
        val refCurve = elasticity?.optJSONObject("reference_curve")
        val elasticityX = parseNumberList(refCurve?.optJSONArray("x"))
        val elasticityY = parseNumberList(refCurve?.optJSONArray("y"))

        // 雷达图
        val radarItems = parseRadarItems(json.optJSONArray("radar"))

        // 检测项
        val rawResult = optJSONObjectFlexible(json, "raw_result")
        val wrinkle = parseWrinkleDetect(rawResult?.optJSONObject("wrinkle"))
        val acne = parseAcneDetect(rawResult?.optJSONObject("acne"))
        val redness = parseRednessDetect(rawResult?.optJSONObject("redness"))
        val spots = parseSpotsDetect(rawResult?.optJSONObject("spots"))
        val brown = parseMetricsDetect(rawResult?.optJSONObject("brown"), "brown", "棕区")
        val purple = parseMetricsDetect(rawResult?.optJSONObject("purple"), "purple", "紫区")
        val texture = parseMetricsDetect(rawResult?.optJSONObject("texture"), "texture", "纹理")
        val pores = parseMetricsDetect(rawResult?.optJSONObject("pores"), "pores", "毛孔")

        // 报告级改善建议
        val suggestions = mutableListOf<SuggestionItem>()
        json.optJSONArray("improvement_suggestions")?.let { arr ->
            for (i in 0 until arr.length()) {
                val o = arr.optJSONObject(i) ?: continue
                val title = o.optString("title", "")
                val desc = o.optString("description", "")
                if (title.isNotBlank() || desc.isNotBlank()) suggestions.add(SuggestionItem(title, desc))
            }
        }
        val sumSug = summary?.optString("suggestions", "") ?: ""
        if (sumSug.isNotBlank()) suggestions.add(SuggestionItem("综合建议", sumSug))

        return ReportDetail(
            overallScore = score, skinType = skinType, moistureLevel = moistureLevel,
            skinAge = skinAge, elasticityScore = elasticityScore,
            elasticityX = elasticityX, elasticityY = elasticityY,
            radarItems = radarItems,
            redness = redness, spots = spots, brown = brown, purple = purple, pores = pores,
            texture = texture, wrinkle = wrinkle, acne = acne,
            createdAt = json.optString("created_at", json.optString("create_time", "")),
            reportImageUrl = json.optString("image_url", json.optString("report_image_url", "")),
            suggestions = suggestions
        )
    }

    /** 皱纹：raw_result.wrinkle.region_metrics 数组 */
    private fun parseWrinkleDetect(obj: JSONObject?): DetectData {
        if (obj == null) return emptyDetect("皱纹")
        if (!optBooleanFlexible(obj, "detected")) return emptyDetect("皱纹")
        val arr = obj.optJSONArray("region_metrics")
            ?: return DetectData("皱纹", "", "", "", true, emptyList())
        val table = mutableListOf<DetectTableRow>()
        for (i in 0 until arr.length()) {
            val m = arr.optJSONObject(i) ?: continue
            table.add(DetectTableRow(
                zone = m.optString("region_name", "").ifEmpty { m.optString("region_key", "") },
                score = formatNum(m.opt("relative_score")),
                count = formatNum(m.opt("segment_count")),
                pixelLength = formatNum(m.opt("wrinkle_pixels")),
                avgLength = formatNum(m.opt("mean_segment_length")),
                maxLength = formatNum(m.opt("max_segment_length")),
                density = formatNum(m.opt("density_per_10k")),
                ratio = formatNum(m.opt("share_pct")),
                area = formatNum(m.opt("area_px")),
                regionImageUrl = m.optString("region_image_url", "")
            ))
        }
        return DetectData("皱纹", "", "", "", true, table)
    }

    /** 痘痘：raw_result.acne（severity/region_counts/circle_count） */
    private fun parseAcneDetect(obj: JSONObject?): DetectData {
        if (obj == null) return emptyDetect("痘痘")
        if (!optBooleanFlexible(obj, "detected")) return emptyDetect("痘痘")
        val level = obj.optString("severity_level", "")
        val note = obj.optString("severity_note", "")
        val desc = listOf(level, note).filter { it.isNotBlank() }.joinToString("：")
        val table = mutableListOf<DetectTableRow>()
        if (obj.has("circle_count")) {
            table.add(DetectTableRow("检测数量", formatNum(obj.opt("circle_count")), "", "", "", "", "", "", ""))
        }
        val rc = obj.optJSONObject("region_counts")
        if (rc != null) {
            val keys = rc.keys()
            while (keys.hasNext()) {
                val k = keys.next()
                table.add(DetectTableRow(rednessRegionToChinese(k), formatNum(rc.opt(k)), "", "", "", "", "", "", ""))
            }
        }
        return DetectData("痘痘", desc, "", "", true, table)
    }

    /** 红区：raw_result.redness.redness_metrics（优先 red_feature_region_distribution 数组，兜底 region_statistics 对象） */
    private fun parseRednessDetect(obj: JSONObject?): DetectData {
        if (obj == null) return emptyDetect("红区")
        if (!optBooleanFlexible(obj, "detected")) return emptyDetect("红区")
        val metrics = obj.optJSONObject("redness_metrics")
        val table = mutableListOf<DetectTableRow>()

        // 优先 red_feature_region_distribution 数组格式（与小程序一致）
        val distributionArray = metrics?.optJSONArray("red_feature_region_distribution")
        if (distributionArray != null && distributionArray.length() > 0) {
            for (i in 0 until distributionArray.length()) {
                val region = distributionArray.optJSONObject(i) ?: continue
                table.add(DetectTableRow(
                    zone = rednessRegionToChinese(region.optString("region", "")),
                    score = formatNum(region.opt("count")),
                    count = formatNum(region.opt("count")),
                    pixelLength = "", avgLength = "", maxLength = "",
                    density = "", ratio = "", area = ""
                ))
            }
        }

        // 兜底 region_statistics 对象格式
        if (table.isEmpty()) {
            val regions = metrics?.optJSONObject("region_statistics")
            if (regions != null) {
                val keys = regions.keys()
                while (keys.hasNext()) {
                    val k = keys.next()
                    val r = regions.optJSONObject(k) ?: continue
                    table.add(DetectTableRow(
                        zone = rednessRegionToChinese(k),
                        score = formatPercent(r.opt("red_area_ratio")),
                        count = "", pixelLength = "", avgLength = "", maxLength = "",
                        density = "", ratio = "", area = formatNum(r.opt("area"))
                    ))
                }
            }
        }

        val desc = if (metrics != null && metrics.has("red_area_ratio"))
            "红区面积占比 ${formatPercent(metrics.opt("red_area_ratio"))}" else ""
        return DetectData("红区", desc, "", "", true, table)
    }

    /** 色斑：raw_result.spots.spots_metrics（对象，取计数字段） */
    private fun parseSpotsDetect(obj: JSONObject?): DetectData {
        if (obj == null) return emptyDetect("色斑")
        if (!optBooleanFlexible(obj, "detected")) return emptyDetect("色斑")
        val m = obj.optJSONObject("spots_metrics")
        val table = mutableListOf<DetectTableRow>()
        if (m != null) {
            if (m.has("spot_count")) table.add(DetectTableRow("斑点总数", formatNum(m.opt("spot_count")), "", "", "", "", "", "", ""))
            if (m.has("small_spot_count")) table.add(DetectTableRow("小斑点", formatNum(m.opt("small_spot_count")), "", "", "", "", "", "", ""))
            if (m.has("large_spot_count")) table.add(DetectTableRow("大斑点", formatNum(m.opt("large_spot_count")), "", "", "", "", "", "", ""))
        }
        return DetectData("色斑", "", "", "", true, table)
    }

    /** 棕区/纹理/毛孔：raw_result.<key>.<key>_metrics [{name,value}] 数组 */
    private fun parseMetricsDetect(obj: JSONObject?, key: String, displayName: String): DetectData {
        if (obj == null) return emptyDetect(displayName)
        if (!optBooleanFlexible(obj, "detected")) return emptyDetect(displayName)
        val arr = obj.optJSONArray("${key}_metrics")
        val table = mutableListOf<DetectTableRow>()
        if (arr != null) {
            for (i in 0 until arr.length()) {
                val m = arr.optJSONObject(i) ?: continue
                table.add(DetectTableRow(
                    zone = m.optString("name", ""),
                    score = formatNum(m.opt("value")),
                    count = "", pixelLength = "", avgLength = "", maxLength = "",
                    density = "", ratio = "", area = ""
                ))
            }
        }
        return DetectData(displayName, "", "", "", true, table)
    }

    /** 数字格式化：整数去小数点，小数保留一位 */
    private fun formatNum(v: Any?): String = when (v) {
        null, JSONObject.NULL -> ""
        is Number -> {
            val d = v.toDouble()
            if (d == Math.floor(d) && !d.isInfinite()) d.toLong().toString()
            else String.format(java.util.Locale.US, "%.1f", d)
        }
        else -> v.toString()
    }

    /** 比例(0~1)转百分比字符串 */
    private fun formatPercent(v: Any?): String {
        val d = (v as? Number)?.toDouble() ?: return ""
        return "${(d * 100).toInt()}%"
    }

    // ────── 直接解析 ──────

    private fun parseDirectJson(json: JSONObject): ReportDetail {
        val overallScore = json.optInt("overall_score", 0)
        val skinType = json.optString("skin_type", "")
        val moistureLevel = json.optInt("moisture_level", 0)
        val createdAt = json.optString("created_at", json.optString("create_time", ""))
        val reportImageUrl = json.optString("report_image_url", "")

        val elasticityObj = json.optJSONObject("elasticity")
        val elasticityScore = elasticityObj?.optInt("score", 0) ?: 0
        val refCurve = elasticityObj?.optJSONObject("reference_curve")
        val elasticityX = parseNumberList(refCurve?.optJSONArray("x"))
        val elasticityY = parseNumberList(refCurve?.optJSONArray("y"))
        val referenceScore = elasticityObj?.optInt("reference_score", 0) ?: 0

        val skinAge = if (json.has("skin_age")) json.optInt("skin_age", 0) else null
        val skinAgeScore = if (json.has("skin_age_score")) json.optInt("skin_age_score", 0) else null

        val radarItems = parseRadarItems(json.optJSONArray("radar_items"))

        val redness = parseRednessResponse(json)
        val spots = parseSpotsResponse(json)
        val brown = parseBrownPoresTextureResponse(json, "brown", "棕区")
        val purple = parseBrownPoresTextureResponse(json, "purple", "紫区")
        val pores = parseBrownPoresTextureResponse(json, "pores", "毛孔")
        val texture = parseBrownPoresTextureResponse(json, "texture", "纹理")
        val wrinkle = parseBrownPoresTextureResponse(json, "wrinkle", "皱纹")
        val acne = parseBrownPoresTextureResponse(json, "acne", "痘痘")

        return ReportDetail(
            overallScore = overallScore, skinType = skinType, moistureLevel = moistureLevel,
            skinAge = skinAge, skinAgeScore = skinAgeScore, elasticityScore = elasticityScore,
            elasticityX = elasticityX, elasticityY = elasticityY, referenceScore = referenceScore,
            radarItems = radarItems, redness = redness, spots = spots, brown = brown, purple = purple,
            pores = pores, texture = texture, wrinkle = wrinkle, acne = acne,
            createdAt = createdAt, reportImageUrl = reportImageUrl
        )
    }

    // ────── raw_result 解析 ──────

    fun parseRawResult(rawResult: JSONObject): ReportDetail {
        val overallScore = pickInt(rawResult, "overall_score")
        val skinType = pickStr(rawResult, "skin_type")
        val moistureLevel = pickInt(rawResult, "moisture_level")
        val referenceScore = pickInt(rawResult, "reference_score")
        val elasticityScore = pickInt(rawResult, "elasticity_score")

        val skinAge = if (rawResult.has("skin_age")) rawResult.optInt("skin_age") else null
        val skinAgeScore = if (rawResult.has("skin_age_score")) rawResult.optInt("skin_age_score") else null

        val elasticityX: List<Number>
        val elasticityY: List<Number>
        val elasticityObj = rawResult.optJSONObject("elasticity")
        if (elasticityObj != null) {
            elasticityX = parseNumberList(elasticityObj.optJSONArray("reference_x"))
            elasticityY = parseNumberList(elasticityObj.optJSONArray("reference_y"))
        } else {
            elasticityX = parseNumberList(rawResult.optJSONArray("elasticity_reference_x"))
            elasticityY = parseNumberList(rawResult.optJSONArray("elasticity_reference_y"))
        }

        val items = rawResult.optJSONObject("items")
        val redness = parseRedness(items)
        val spots = parseSpots(items)
        val brown = parseBrownPoresTexture(items, "brown", "棕区")
        val purple = parseBrownPoresTexture(items, "purple", "紫区")
        val pores = parseBrownPoresTexture(items, "pores", "毛孔")
        val texture = parseBrownPoresTexture(items, "texture", "纹理")
        val wrinkle = parseBrownPoresTexture(items, "wrinkle", "皱纹")
        val acne = parseBrownPoresTexture(items, "acne", "痘痘")

        val radarItems = rawResult.optJSONArray("radar_items")?.let { parseRadarItems(it) } ?: run {
            val arr = JSONArray()
            if (moistureLevel > 0) arr.put(JSONObject().apply { put("name", "水油"); put("value", moistureLevel) })
            if (referenceScore > 0) arr.put(JSONObject().apply { put("name", "毛孔"); put("value", referenceScore) })
            if (elasticityScore > 0) arr.put(JSONObject().apply { put("name", "弹性"); put("value", elasticityScore) })
            parseRadarItems(arr)
        }

        return ReportDetail(
            overallScore = overallScore, skinType = skinType, moistureLevel = moistureLevel,
            skinAge = skinAge, skinAgeScore = skinAgeScore, elasticityScore = elasticityScore,
            elasticityX = elasticityX, elasticityY = elasticityY, referenceScore = referenceScore,
            radarItems = radarItems, redness = redness, spots = spots, brown = brown, purple = purple,
            pores = pores, texture = texture, wrinkle = wrinkle, acne = acne
        )
    }

    // ────── 红区解析 ──────

    private fun parseRednessResponse(json: JSONObject): DetectData {
        val rednessObj = json.optJSONObject("redness") ?: return emptyDetect("红区")
        if (!optBooleanFlexible(rednessObj, "has_redness")) return emptyDetect("红区")
        val faceImage = rednessObj.optString("face_image", "")
        val desc = rednessObj.optString("description", "")
        val suggestion = rednessObj.optString("suggestion", "")
        val regions = rednessObj.optJSONObject("regions")
            ?: return emptyDetect("红区", faceImage, true, desc, suggestion)
        return DetectData("红区", desc, suggestion, faceImage, true, parseRegionTable(regions))
    }

    private fun parseRedness(items: JSONObject?): DetectData {
        if (items == null) return emptyDetect("红区")
        val redness = optJSONObjectFlexible(items, "redness") ?: return emptyDetect("红区")
        if (!optBooleanFlexible(redness, "has_redness")) return emptyDetect("红区")
        val desc = redness.optString("description", "")
        val suggestion = redness.optString("suggestion", "")
        val faceImage = redness.optString("face_image", "")
        val regions = redness.optJSONObject("regions")
            ?: return DetectData("红区", desc, suggestion, faceImage, true, emptyList())
        return DetectData("红区", desc, suggestion, faceImage, true, parseRegionTable(regions))
    }

    // ────── 色斑解析 ──────

    private fun parseSpotsResponse(json: JSONObject): DetectData {
        val spotsObj = json.optJSONObject("spots") ?: return emptyDetect("色斑")
        if (!optBooleanFlexible(spotsObj, "has_spots")) return emptyDetect("色斑")
        val faceImage = spotsObj.optString("face_image", "")
        val desc = spotsObj.optString("description", "")
        val suggestion = spotsObj.optString("suggestion", "")
        val regions = spotsObj.optJSONObject("regions")
            ?: return emptyDetect("色斑", faceImage, true, desc, suggestion)
        return DetectData("色斑", desc, suggestion, faceImage, true, parseRegionTable(regions))
    }

    private fun parseSpots(items: JSONObject?): DetectData {
        if (items == null) return emptyDetect("色斑")
        val spots = optJSONObjectFlexible(items, "spots") ?: return emptyDetect("色斑")
        if (!optBooleanFlexible(spots, "has_spots")) return emptyDetect("色斑")
        val desc = spots.optString("description", "")
        val suggestion = spots.optString("suggestion", "")
        val faceImage = spots.optString("face_image", "")
        val regions = spots.optJSONObject("regions")
            ?: return DetectData("色斑", desc, suggestion, faceImage, true, emptyList())
        return DetectData("色斑", desc, suggestion, faceImage, true, parseRegionTable(regions))
    }

    // ────── 棕区/毛孔/纹理/皱纹/痘痘 通用解析 ──────

    private fun parseBrownPoresTextureResponse(json: JSONObject, key: String, displayName: String): DetectData {
        val obj = json.optJSONObject(key) ?: return emptyDetect(displayName)
        if (!optBooleanFlexible(obj, "has_$key")) return emptyDetect(displayName)
        val faceImage = obj.optString("face_image", "")
        val desc = obj.optString("description", "")
        val suggestion = obj.optString("suggestion", "")
        val regions = obj.optJSONObject("regions")
            ?: return emptyDetect(displayName, faceImage, true, desc, suggestion)
        return DetectData(displayName, desc, suggestion, faceImage, true, parseRegionTable(regions))
    }

    private fun parseBrownPoresTexture(items: JSONObject?, key: String, displayName: String): DetectData {
        if (items == null) return emptyDetect(displayName)
        val obj = optJSONObjectFlexible(items, key) ?: return emptyDetect(displayName)
        if (!optBooleanFlexible(obj, "has_$key")) return emptyDetect(displayName)
        val desc = obj.optString("description", "")
        val suggestion = obj.optString("suggestion", "")
        val faceImage = obj.optString("face_image", "")
        val regions = obj.optJSONObject("regions")
            ?: return DetectData(displayName, desc, suggestion, faceImage, true, emptyList())
        return DetectData(displayName, desc, suggestion, faceImage, true, parseRegionTable(regions))
    }

    private fun parseRegionTable(regions: JSONObject): List<DetectTableRow> {
        val table = mutableListOf<DetectTableRow>()
        val keys = regions.keys()
        while (keys.hasNext()) {
            val key = keys.next()
            val region = regions.optJSONObject(key) ?: continue
            table.add(DetectTableRow(
                zone = rednessRegionToChinese(key),
                score = region.optInt("relative_score", 0).toString(),
                count = region.optInt("count", 0).toString(),
                pixelLength = region.optInt("pixel_length", 0).toString(),
                avgLength = region.optInt("avg_segment_length", 0).toString(),
                maxLength = region.optInt("max_segment_length", 0).toString(),
                density = region.optDouble("density", 0.0).toString(),
                ratio = region.optDouble("ratio", 0.0).toString(),
                area = region.optInt("area_pixels", 0).toString(),
                regionImageUrl = region.optString("region_image", "")
            ))
        }
        return table
    }

    // ────── 辅助方法 ──────

    private fun parseRadarItems(jsonArray: JSONArray?): List<RadarItem> {
        if (jsonArray == null) return emptyList()
        val items = mutableListOf<RadarItem>()
        for (i in 0 until jsonArray.length()) {
            val obj = jsonArray.optJSONObject(i) ?: continue
            items.add(RadarItem(obj.optString("name", ""), obj.optInt("value", 0)))
        }
        return items
    }

    private fun parseNumberList(jsonArray: JSONArray?): List<Number> {
        if (jsonArray == null) return emptyList()
        val list = mutableListOf<Number>()
        for (i in 0 until jsonArray.length()) {
            list.add(jsonArray.optDouble(i))
        }
        return list
    }

    fun optJSONObjectFlexible(json: JSONObject, key: String): JSONObject? {
        json.optJSONObject(key)?.let { return it }
        val str = json.optString(key, "")
        return if (str.isNotBlank()) try { JSONObject(str) } catch (_: Exception) { null } else null
    }

    fun optBooleanFlexible(json: JSONObject, key: String): Boolean {
        if (json.has(key)) {
            when (val v = json.opt(key)) {
                is Boolean -> return v
                is String -> return v.equals("true", ignoreCase = true)
                is Int -> return v != 0
                is Number -> return v.toInt() != 0
            }
        }
        return false
    }

    private fun pickStr(json: JSONObject, key: String): String {
        json.optString(key, "").takeIf { it.isNotBlank() }?.let { return it }
        json.optJSONObject("items")?.optString(key, "")?.takeIf { it.isNotBlank() }?.let { return it }
        return ""
    }

    private fun pickInt(json: JSONObject, key: String): Int {
        if (json.has(key)) {
            val v = json.optInt(key, 0)
            if (v != 0) return v
        }
        json.optJSONObject("items")?.let { items ->
            if (items.has(key)) return items.optInt(key, 0)
        }
        return 0
    }

    fun rednessRegionToChinese(key: String): String = when (key) {
        "left_cheek" -> "左脸"
        "right_cheek" -> "右脸"
        "forehead" -> "额头"
        "nose" -> "鼻子"
        "chin" -> "下巴"
        else -> key
    }

    fun emptyDetect(name: String, faceImage: String = "", hasData: Boolean = false,
                    desc: String = "", suggestion: String = ""): DetectData =
        DetectData(name, desc, suggestion, faceImage, hasData, emptyList())
}