<!--
  意见反馈弹窗（uni-app）。

  用法（在设置页里）：

    <feedback-sheet v-model:show="showFeedback" @done="onFeedbackDone" />
-->
<template>
  <view v-if="show" class="fb-mask" @tap="onMaskTap">
    <view class="fb-panel" @tap.stop>
      <view class="fb-head">
        <text class="fb-title">意见反馈</text>
        <text class="fb-close" @tap="close">✕</text>
      </view>

      <view class="fb-body">
        <text class="fb-label">反馈类型</text>
        <view class="fb-types">
          <view
            v-for="option in types"
            :key="option.value"
            class="fb-type"
            :class="{ 'is-active': type === option.value }"
            @tap="type = option.value"
          >
            <text class="fb-type-text">{{ option.label }}</text>
          </view>
        </view>

        <text class="fb-label">详细描述</text>
        <textarea
          v-model="description"
          class="fb-textarea"
          placeholder="具体发生了什么？"
          :maxlength="2000"
          auto-height
        />
        <text v-if="!description.trim()" class="fb-hint">描述不能为空</text>

        <text class="fb-label">联系方式（选填）</text>
        <input v-model="contact" class="fb-input" placeholder="邮箱或其他联系方式" />

        <view class="fb-notice">
          <text class="fb-notice-text">
            反馈会发到作者的 OpenFeedback 后台，作者会集中处理。不含账号、位置或设备标识。
          </text>
        </view>

        <text v-if="error" class="fb-error">{{ error }}</text>
      </view>

      <view class="fb-actions">
        <view class="fb-btn fb-btn-ghost" @tap="close">
          <text class="fb-btn-text">取消</text>
        </view>
        <view class="fb-btn fb-btn-primary" :class="{ 'is-disabled': submitting }" @tap="submit">
          <text class="fb-btn-text">{{ submitting ? '提交中…' : '提交' }}</text>
        </view>
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import {
  FEEDBACK_APP_ID,
  FEEDBACK_TYPES,
  feedbackEnabled,
  newSubmissionId,
  submitFeedback,
  type FeedbackType,
} from './feedback'

const props = defineProps<{ show: boolean }>()
const emit = defineEmits<{ (e: 'update:show', value: boolean): void; (e: 'done', ok: boolean): void }>()

const types = FEEDBACK_TYPES
const type = ref<FeedbackType>('bug')
const description = ref('')
const contact = ref('')
const submitting = ref(false)
const error = ref('')

const enabled = computed(() => feedbackEnabled())

watch(
  () => props.show,
  (visible) => {
    if (visible) {
      type.value = 'bug'
      description.value = ''
      contact.value = ''
      error.value = ''
    }
  },
)

function close() {
  if (submitting.value) return
  emit('update:show', false)
}

function onMaskTap() {
  close()
}

async function submit() {
  if (submitting.value) return
  if (!description.value.trim()) {
    error.value = '请描述一下遇到的问题'
    return
  }
  if (!enabled.value) {
    error.value = '反馈服务未配置'
    return
  }

  submitting.value = true
  error.value = ''
  const submissionId = newSubmissionId()
  try {
    await submitFeedback({
      appId: FEEDBACK_APP_ID,
      submissionId,
      type: type.value,
      description: description.value.trim(),
      contact: contact.value.trim() || undefined,
      appVersion: __uniConfig?.version?.name,
      locale: '',
    })
    emit('update:show', false)
    emit('done', true)
    uni.showToast({ title: '反馈已收到', icon: 'none' })
  } catch (err: any) {
    error.value = err?.message || '提交失败，请稍后再试'
    emit('done', false)
  } finally {
    submitting.value = false
  }
}
</script>

<style scoped>
.fb-mask {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.45);
  z-index: 999;
  display: flex;
  align-items: center;
  justify-content: center;
}
.fb-panel {
  width: 84vw;
  max-width: 420px;
  max-height: 82vh;
  background: #fff;
  border-radius: 14px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}
.fb-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 18px 10px;
}
.fb-title {
  font-size: 17px;
  font-weight: 600;
  color: #1b1f24;
}
.fb-close {
  font-size: 18px;
  color: #8a919b;
  padding: 0 4px;
}
.fb-body {
  padding: 4px 18px 12px;
  overflow-y: auto;
}
.fb-label {
  display: block;
  font-size: 13px;
  color: #6b7480;
  margin: 12px 0 6px;
}
.fb-types {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.fb-type {
  padding: 6px 14px;
  border-radius: 999px;
  border: 1px solid #e3e6ea;
  background: #f7f8fa;
}
.fb-type.is-active {
  background: #c2455c;
  border-color: #c2455c;
}
.fb-type-text {
  font-size: 13px;
  color: #4b5563;
}
.fb-type.is-active .fb-type-text {
  color: #fff;
}
.fb-textarea {
  width: 100%;
  min-height: 110px;
  box-sizing: border-box;
  background: #f7f8fa;
  border-radius: 10px;
  padding: 10px 12px;
  font-size: 14px;
  color: #1b1f24;
}
.fb-input {
  width: 100%;
  height: 40px;
  box-sizing: border-box;
  background: #f7f8fa;
  border-radius: 10px;
  padding: 0 12px;
  font-size: 14px;
  color: #1b1f24;
}
.fb-hint,
.fb-error {
  display: block;
  font-size: 12px;
  margin-top: 6px;
}
.fb-hint {
  color: #8a919b;
}
.fb-error {
  color: #c0392b;
}
.fb-notice {
  margin-top: 14px;
  padding: 10px 12px;
  background: #f7f8fa;
  border-radius: 8px;
}
.fb-notice-text {
  font-size: 12px;
  color: #6b7480;
  line-height: 1.5;
}
.fb-actions {
  display: flex;
  gap: 10px;
  padding: 12px 18px 18px;
  border-top: 1px solid #eef0f2;
}
.fb-btn {
  flex: 1;
  height: 42px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
}
.fb-btn-ghost {
  background: #f7f8fa;
}
.fb-btn-primary {
  background: #c2455c;
}
.fb-btn-primary.is-disabled {
  opacity: 0.6;
}
.fb-btn-text {
  font-size: 15px;
  color: #4b5563;
}
.fb-btn-primary .fb-btn-text {
  color: #fff;
}
</style>
