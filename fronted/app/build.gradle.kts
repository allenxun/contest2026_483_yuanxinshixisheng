plugins {
    alias(libs.plugins.android.application)
}

android {
    namespace = "com.example.aisia"
    compileSdk {
        version = release(36) {
            minorApiLevel = 1
        }
    }

    defaultConfig {
        applicationId = "com.example.aisia"
        minSdk = 24
        targetSdk = 36
        versionCode = 1
        versionName = "1.0"

        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
    }

    buildFeatures {
        buildConfig = true
    }

    sourceSets {
        getByName("main") {
            jniLibs.srcDirs("../filament-extract/jni")
        }
    }

    buildTypes {
        debug {
            // 开发环境
            buildConfigField("String", "BASE_URL", "\"https://eveaisia.com/\"")
        }
        release {
            // 正式环境
            buildConfigField("String", "BASE_URL", "\"https://eveaisia.com/\"")
            optimization {
                enable = false
            }
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_11
        targetCompatibility = JavaVersion.VERSION_11
    }
}

// The 3D model renderer uses the Filament JNI libraries in `filament-extract/jni`.

dependencies {
    implementation(libs.androidx.activity.ktx)
    implementation(libs.androidx.appcompat)
    implementation(libs.androidx.constraintlayout)
    implementation(libs.androidx.core.ktx)
    implementation(libs.material)
    implementation(libs.androidx.viewpager2)
    implementation(libs.androidx.fragment.ktx)
    implementation(libs.coil)
    implementation(libs.okhttp)
    implementation(libs.androidx.recyclerview)
    implementation(libs.androidx.camera.core)
    implementation(libs.androidx.camera.camera2)
    implementation(libs.androidx.camera.lifecycle)
    implementation(libs.androidx.camera.view)
    implementation(libs.filament.android)
    implementation(libs.filament.utils.android)
    implementation(libs.filament.gltfio.android)
    implementation(libs.mediapipe.vision)
    implementation(libs.mlkit.face.detection)
    implementation(libs.kotlinx.coroutines.android)
    testImplementation(libs.junit)
    testImplementation("org.json:json:20240303")
    androidTestImplementation(libs.androidx.espresso.core)
    androidTestImplementation(libs.androidx.junit)
}
