package com.kkkkikun.openfeedback.compose

import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.net.Uri
import android.util.Log
import java.io.ByteArrayOutputStream
import java.io.InputStream
import kotlin.math.max
import kotlin.math.roundToInt

/**
 * Prepares a user-picked image for upload.
 *
 * The image is downscaled, re-encoded as JPEG, and stripped of EXIF data.
 * Re-encoding is what removes the metadata: the original bytes, which carry
 * the location and device information, never leave the device.
 */
internal object ImagePreparer {

    private const val TAG = "OpenFeedbackImage"
    private const val JPEG_QUALITY = 82

    /**
     * Reads [uri], scales it down, and returns JPEG bytes.
     *
     * Returns null when the image cannot be read or is not a real image.
     */
    fun prepare(
        context: Context,
        uri: Uri,
        maxEdge: Int,
        maxBytes: Int,
    ): PreparedImage? {
        return try {
            val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
            context.contentResolver.openInputStream(uri)?.use {
                BitmapFactory.decodeStream(it, null, bounds)
            } ?: return null

            if (bounds.outWidth <= 0 || bounds.outHeight <= 0) {
                Log.w(TAG, "the picked file is not a decodable image")
                return null
            }

            val sampleSize = calculateSampleSize(bounds.outWidth, bounds.outHeight, maxEdge)
            val options = BitmapFactory.Options().apply {
                inSampleSize = sampleSize
                inPreferredConfig = Bitmap.Config.ARGB_8888
            }

            val bitmap = context.contentResolver.openInputStream(uri)?.use { stream ->
                BitmapFactory.decodeStream(stream, null, options)
            } ?: return null

            val scaled = scaleToFit(bitmap, maxEdge)
            val bytes = compress(scaled, maxBytes)

            if (scaled !== bitmap) bitmap.recycle()
            scaled.recycle()

            if (bytes == null) {
                Log.w(TAG, "the image could not be compressed")
                null
            } else {
                PreparedImage(bytes = bytes, mimeType = "image/jpeg")
            }
        } catch (e: Exception) {
            Log.e(TAG, "could not prepare the image: ${e.message}")
            null
        }
    }

    /**
     * The power-of-two downscale factor that keeps the image under the edge
     * limit while decoding as little as possible.
     */
    private fun calculateSampleSize(width: Int, height: Int, maxEdge: Int): Int {
        var sampleSize = 1
        var longest = max(width, height)
        while (longest / 2 >= maxEdge) {
            longest /= 2
            sampleSize *= 2
        }
        return sampleSize
    }

    private fun scaleToFit(bitmap: Bitmap, maxEdge: Int): Bitmap {
        val longest = max(bitmap.width, bitmap.height)
        if (longest <= maxEdge) return bitmap
        val ratio = maxEdge.toFloat() / longest
        val width = (bitmap.width * ratio).roundToInt().coerceAtLeast(1)
        val height = (bitmap.height * ratio).roundToInt().coerceAtLeast(1)
        return Bitmap.createScaledBitmap(bitmap, width, height, true)
    }

    /**
     * Encodes as JPEG, lowering the quality until the result fits.
     *
     * Quality is reduced in steps rather than jumping to the minimum, so a
     * small image keeps its detail.
     */
    private fun compress(bitmap: Bitmap, maxBytes: Int): ByteArray? {
        var quality = JPEG_QUALITY
        var bytes = encode(bitmap, quality) ?: return null
        while (bytes.size > maxBytes && quality > 40) {
            quality -= 12
            bytes = encode(bitmap, quality) ?: break
        }
        return bytes
    }

    private fun encode(bitmap: Bitmap, quality: Int): ByteArray? {
        val stream = ByteArrayOutputStream()
        val ok = bitmap.compress(Bitmap.CompressFormat.JPEG, quality, stream)
        if (!ok) return null
        val bytes = stream.toByteArray()
        return if (bytes.isEmpty()) null else bytes
    }
}

/** An image that is ready to upload. */
internal data class PreparedImage(
    val bytes: ByteArray,
    val mimeType: String,
) {
    override fun equals(other: Any?): Boolean {
        if (this === other) return true
        if (other !is PreparedImage) return false
        return mimeType == other.mimeType && bytes.contentEquals(other.bytes)
    }

    override fun hashCode(): Int = 31 * bytes.contentHashCode() + mimeType.hashCode()
}
