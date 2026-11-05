// Root build file for the OpenFeedback Android SDK.
//
// The versions below are the lowest common denominator of the host apps:
//   OIT-Net-Portal : AGP 8.7.3, Kotlin 2.0.21, Compose BOM 2024.12.01
//   LocalPixt       : AGP 8.5.2, Kotlin 2.0.21, Compose BOM 2024.12.01
//   牵线 Android    : a Rust app; it uses the REST API, not this SDK
//
// A library built with AGP 8.5 is consumed by both, so 8.5.2 is the floor.

plugins {
    id("com.android.library") version "8.5.2" apply false
    id("org.jetbrains.kotlin.android") version "2.0.21" apply false
    id("org.jetbrains.kotlin.plugin.compose") version "2.0.21" apply false
    // `maven-publish` is a core Gradle plugin; the subprojects apply it
    // directly, so it is not declared here.
}

group = "com.kkkkikun.openfeedback"
version = "0.1.0"

// The SDK is published to a plain directory that the OpenFeedback server
// serves over HTTPS. A host app then declares one repository and pins an
// exact version:
//
//   maven { url = uri("https://<feedback-host>/maven/") }
//   implementation("com.kkkkikun.openfeedback:openfeedback-compose:0.1.0")
val mavenRepoDir: Directory = rootProject.layout.projectDirectory.dir("maven-repo")

subprojects {
    // The subprojects inherit the group and version, so every artifact
    // carries the same coordinates.
    group = rootProject.group
    version = rootProject.version

    plugins.withId("maven-publish") {
        extensions.configure<PublishingExtension> {
            repositories {
                maven {
                    name = "localMaven"
                    url = uri(mavenRepoDir)
                }
            }
        }
    }
}
