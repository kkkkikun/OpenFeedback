// openfeedback-core — the transport, the model, and the offline queue.
//
// This module has no Compose dependency, so a host app that only wants the
// REST client (or the Rust client, which mirrors this contract) can depend
// on it alone.

plugins {
    id("com.android.library")
    id("org.jetbrains.kotlin.android")
    id("maven-publish")
}

android {
    namespace = "com.kkkkikun.openfeedback.core"
    compileSdk = 35

    defaultConfig {
        // 26 covers OIT-Net-Portal; LocalPixt uses 28.
        minSdk = 26
        consumerProguardFiles("consumer-rules.pro")

        buildConfigField("String", "SDK_VERSION", "\"${project.version}\"")
    }

    buildFeatures {
        buildConfig = true
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = "17"
    }

    testOptions {
        unitTests.isReturnDefaultValues = true
    }
}

dependencies {
    implementation("androidx.core:core-ktx:1.15.0")
    implementation("androidx.work:work-runtime-ktx:2.9.1")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.9.0")

    testImplementation("junit:junit:4.13.2")
    testImplementation("org.jetbrains.kotlinx:kotlinx-coroutines-test:1.9.0")
}

publishing {
    publications {
        register<MavenPublication>("release") {
            groupId = "com.kkkkikun.openfeedback"
            artifactId = "openfeedback-core"
            version = project.version.toString()

            afterEvaluate {
                from(components["release"])
            }
        }
    }
}
