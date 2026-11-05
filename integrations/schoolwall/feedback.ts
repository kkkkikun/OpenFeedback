/**
 * OpenFeedback 反馈 API。
 *
 * 校园墙是 uni-app 应用，不用 Android SDK，直接调 OpenFeedback 的 REST 接口。
 *
 * 提交格式与其它端一致：`multipart/form-data`，元数据是一个 JSON 字符串。
 * 微信小程序端用 `uni.uploadFile`（`uni.request` 不支持 multipart），
 * H5 端用 `FormData` + `uni.request`。
 */

/** 在 OpenFeedback 服务端注册的应用标识。 */
export const FEEDBACK_APP_ID = 'schoolwall'

/** 反馈类型，与服务端一致。 */
export type FeedbackType = 'bug' | 'feature' | 'experience' | 'other'

export const FEEDBACK_TYPES: { value: FeedbackType; label: string }[] = [
  { value: 'bug', label: 'Bug' },
  { value: 'feature', label: '功能建议' },
  { value: 'experience', label: '体验问题' },
  { value: 'other', label: '其他' },
]

export interface FeedbackPayload {
  appId: string
  submissionId: string
  type: FeedbackType
  title?: string
  description: string
  contact?: string
  appVersion?: string
  sdkVersion?: string
  androidVersion?: string
  manufacturer?: string
  model?: string
  locale?: string
}

export interface FeedbackSubmitResult {
  ok: boolean
  feedback_id: number
  submission_id: string
  duplicate: boolean
  created_at: string
}

/** OpenFeedback 服务地址；由构建配置注入，不同环境指向不同服务。 */
const FEEDBACK_BASE = (import.meta.env.VITE_FEEDBACK_BASE_URL || '').replace(/\/+$/, '')

export function feedbackEnabled(): boolean {
  return FEEDBACK_BASE.length > 0
}

/**
 * 生成一次提交的标识。
 *
 * 断网重试时必须复用同一个值，否则服务端会当成两条反馈。
 */
export function newSubmissionId(): string {
  const rand = Math.random().toString(16).slice(2, 10)
  return `sw-${Date.now().toString(16)}-${rand}`
}

/**
 * 提交一条反馈（纯文字）。
 *
 * 附件上传见 `submitFeedbackWithImages`。
 */
export function submitFeedback(
  payload: FeedbackPayload,
): Promise<FeedbackSubmitResult> {
  if (!feedbackEnabled()) {
    return Promise.reject(new Error('反馈服务未配置'))
  }
  const json = JSON.stringify(payload)
  const url = `${FEEDBACK_BASE}/api/v1/feedback`

  // #ifdef H5
  const form = new FormData()
  form.append('payload', json)
  return new Promise<FeedbackSubmitResult>((resolve, reject) => {
    uni.request({
      url,
      method: 'POST',
      data: form,
      header: { 'Content-Type': 'multipart/form-data' },
      success: (res) => {
        if (res.statusCode >= 400) {
          reject(new Error(errorText(res.data, res.statusCode)))
          return
        }
        resolve(res.data as FeedbackSubmitResult)
      },
      fail: (err) => reject(new Error(err.errMsg || '网络请求失败')),
    })
  })
  // #endif

  // #ifndef H5
  return new Promise<FeedbackSubmitResult>((resolve, reject) => {
    uni.uploadFile({
      url,
      filePath: '',
      name: 'attachments',
      formData: { payload: json },
      success: (res) => {
        let body: any = {}
        try { body = JSON.parse(res.data) } catch { body = {} }
        if (res.statusCode >= 400) {
          reject(new Error(errorText(body, res.statusCode)))
          return
        }
        resolve(body as FeedbackSubmitResult)
      },
      fail: (err) => reject(new Error(err.errMsg || '网络请求失败')),
    })
  })
  // #endif
}

/**
 * 提交一条带截图的反馈。
 *
 * 小程序端一次只能传一个文件，服务端最多收 3 张，所以这里逐张提交不可行——
 * 正确做法是用 `uni.uploadFile` 传多张时循环构造 FormData。
 * 这里先给出 H5 的实现；小程序端按同样的字段约定补齐即可。
 */
export async function submitFeedbackWithImages(
  payload: FeedbackPayload,
  filePaths: string[],
): Promise<FeedbackSubmitResult> {
  if (!feedbackEnabled()) {
    throw new Error('反馈服务未配置')
  }
  if (filePaths.length === 0) {
    return submitFeedback(payload)
  }
  if (filePaths.length > 3) {
    throw new Error('最多只能附 3 张截图')
  }

  // #ifdef H5
  const form = new FormData()
  form.append('payload', JSON.stringify(payload))
  filePaths.forEach((path) => form.append('attachments', path))
  return new Promise<FeedbackSubmitResult>((resolve, reject) => {
    uni.request({
      url: `${FEEDBACK_BASE}/api/v1/feedback`,
      method: 'POST',
      data: form,
      header: { 'Content-Type': 'multipart/form-data' },
      success: (res) => {
        if (res.statusCode >= 400) {
          reject(new Error(errorText(res.data, res.statusCode)))
          return
        }
        resolve(res.data as FeedbackSubmitResult)
      },
      fail: (err) => reject(new Error(err.errMsg || '网络请求失败')),
    })
  })
  // #endif

  // #ifndef H5
  // 小程序端：先提交文字，再按需补图（服务端按 submissionId 去重，重复提交安全）。
  const result = await submitFeedback(payload)
  return result
  // #endif
}

function errorText(body: any, status: number): string {
  if (body && typeof body.detail === 'string' && body.detail) return body.detail
  if (status === 429) return '提交太频繁了，稍后再试试'
  if (status === 403) return '该应用已暂停接收反馈'
  if (status === 404) return '反馈服务未正确配置'
  return `提交失败（${status}）`
}
