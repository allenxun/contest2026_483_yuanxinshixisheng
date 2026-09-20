package com.example.aisia.ui.openvela
import android.widget.ImageView
import coil.transform.CircleCropTransformation
internal object OpenVelaAvatars {
    fun bind(view: ImageView, person: OpenVelaData.Person) {
        OpenVelaImages.bind(view, person.faceImageUrl, listOf(CircleCropTransformation()))
    }
}
