# AISIA Android 前端

本目录是从 `D:/work/appforandroid` 独立复制的 Android 工程快照。这里的后续修改不会自动同步回原目录，原目录的后续修改也不会自动同步到这里。比赛仓其他目录（`app/`、`board/`、`quickapp/`、`logs/`）不属于本工程。

## 工程结构

- `app/src/`：Android 主代码、资源及测试。
- `gradle/`、`*.gradle.kts`、`gradlew*`：Gradle 配置与 Wrapper。
- `app/src/main/jniLibs/`、`filament-extract/jni/`：原生运行库，Gradle 配置会引用。
- `libs/`：原项目保留的原生库文件。
- `docs/`：流程、接口及 K7 配网说明。

## 本机构建

使用 JDK 21 和带 Android SDK Platform 36.1 的 SDK。首次打开工程时由 Android Studio 生成本机 `local.properties`，不要把它提交到仓库。执行 `./gradlew :app:assembleDebug`（Windows 使用 `gradlew.bat`）。本次复制只验证文件完整性，未把此前隔离类型检查当作 APK 构建成功。

`outputs/`、`tmp/`、`.gradle/`、`app/build/`、`app/release/`、`local.properties` 和原仓 `.git/` 均未复制。提交前请再次检查是否有新生成的缓存、安装包或凭据。
