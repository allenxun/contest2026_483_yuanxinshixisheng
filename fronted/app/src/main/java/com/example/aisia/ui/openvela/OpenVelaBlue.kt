package com.example.aisia.ui.openvela

import android.content.Context
import android.content.res.ColorStateList
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.graphics.drawable.RippleDrawable
import android.view.Gravity
import android.view.View
import android.widget.*
import com.example.aisia.R

internal object OpenVelaBlue {
    val ink = Color.rgb(19, 37, 68)
    val muted = Color.rgb(111, 129, 154)
    val blue = Color.rgb(47, 111, 245)
    val canvas = Color.rgb(243, 247, 252)
    val line = Color.rgb(231, 238, 247)
    fun dp(c: Context, n: Int) = (n * c.resources.displayMetrics.density).toInt()
    fun surface(c: Context, color: Int = Color.WHITE, radius: Int = 16, border: Boolean = false) =
        GradientDrawable().apply {
            setColor(color); cornerRadius = dp(c, radius).toFloat()
            if (border) setStroke(dp(c, 1), line)
        }
    fun text(c: Context, value: String, size: Int = 14, bold: Boolean = false, color: Int = ink) =
        TextView(c).apply {
            text = value; textSize = size.toFloat(); setTextColor(color)
            includeFontPadding = false
            if (bold) setTypeface(null, Typeface.BOLD)
            setLineSpacing(dp(c, 3).toFloat(), 1f)
        }
    fun icon(c: Context, resource: Int, size: Int = 24, tint: Int = ink) = ImageView(c).apply {
        setImageResource(resource); setColorFilter(tint)
        layoutParams = LinearLayout.LayoutParams(dp(c, size), dp(c, size))
        importantForAccessibility = View.IMPORTANT_FOR_ACCESSIBILITY_NO
    }
    fun divider(c: Context) = View(c).apply {
        setBackgroundColor(line)
        layoutParams = LinearLayout.LayoutParams(-1, dp(c, 1))
    }
    fun personRow(c: Context, person: OpenVelaData.Person, click: () -> Unit): View {
        return LinearLayout(c).apply {
            orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL
            setPadding(dp(c, 14), dp(c, 20), dp(c, 14), dp(c, 20))
            minimumHeight = dp(c, 102)
            background = RippleDrawable(ColorStateList.valueOf(0x153A6DF0), null, surface(c))
            addView(ImageView(c).apply {
                scaleType = ImageView.ScaleType.CENTER_CROP
                background = surface(c, Color.rgb(236, 244, 255), 40)
                clipToOutline = true
                contentDescription = "${person.name}的人脸头像"
                OpenVelaAvatars.bind(this, person)
            }, LinearLayout.LayoutParams(dp(c, 48), dp(c, 48)))
            addView(LinearLayout(c).apply {
                orientation = LinearLayout.VERTICAL
                addView(text(c, person.name, 17, true))
                addView(text(c, person.description, 12, color = muted).apply {
                    setPadding(0, dp(c, 9), 0, 0)
                })
            }, LinearLayout.LayoutParams(0, -2, 1f).apply { marginStart = dp(c, 15) })
            addView(icon(c, R.drawable.ic_arrow_right, 16, muted))
            isFocusable = true; setOnClickListener { click() }
        }
    }
    fun step(c: Context, number: Int, title: String, description: String): View =
        LinearLayout(c).apply {
            orientation = LinearLayout.HORIZONTAL; gravity = Gravity.TOP
            setPadding(0, dp(c, 18), 0, dp(c, 18))
            addView(text(c, number.toString(), 21, true, blue).apply {
                gravity = Gravity.CENTER
                background = surface(c, Color.rgb(226, 239, 255), 40)
            }, LinearLayout.LayoutParams(dp(c, 34), dp(c, 34)))
            addView(LinearLayout(c).apply {
                orientation = LinearLayout.VERTICAL
                addView(text(c, title, 17, true))
                addView(text(c, description, 14, color = muted).apply { setPadding(0, dp(c, 10), 0, 0) })
            }, LinearLayout.LayoutParams(0, -2, 1f).apply { marginStart = dp(c, 18) })
        }
}
