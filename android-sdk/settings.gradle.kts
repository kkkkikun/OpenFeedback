// OpenFeedback Android SDK — build configuration.
//
// The SDK is built as an Android library and published to a Maven
// repository, so every host app pins an exact version.

pluginManagement {
    repositories {
        google {
            content {
                includeGroupByRegex("com\\.android.*")
                includeGroupByRegex("com\\.google.*")
                includeGroupByRegex("androidx.*")
            }
        }
        mavenCentral()
        gradlePluginPortal()
    }
}

dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.PREFER_SETTINGS)
    repositories {
        google()
        mavenCentral()
    }
}

rootProject.name = "openfeedback-android"
include(":openfeedback-core")
include(":openfeedback-compose")
include(":openfeedback-testing")
