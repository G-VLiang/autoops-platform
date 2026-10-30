import axios from 'axios'

const api = axios.create({ baseURL: '/api/v1' })

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

api.interceptors.response.use(
  (res) => res,
  (err) => {
    // 401：token 失效或过期，清理后带来源地址跳登录（登录后回到原页面）
    if (err.response?.status === 401 && !err.config?.url?.includes('/auth/login')) {
      const onLoginPage = window.location.pathname.startsWith('/login')
      localStorage.removeItem('token')
      localStorage.removeItem('username')
      if (!onLoginPage) {
        const redirect = encodeURIComponent(window.location.pathname + window.location.search)
        window.location.replace(`/login?redirect=${redirect}`)
      }
    }
    return Promise.reject(err)
  },
)

/** 带鉴权下载文件（导出 PDF/Excel/CSV 用）。 */
export async function download(path, fallbackName = 'download') {
  const res = await api.get(path, { responseType: 'blob' })
  const disposition = res.headers?.['content-disposition'] || ''
  let name = fallbackName
  const utf8 = /filename\*=UTF-8''([^;]+)/i.exec(disposition)
  const plain = /filename="?([^";]+)"?/i.exec(disposition)
  if (utf8) name = decodeURIComponent(utf8[1])
  else if (plain) name = plain[1]
  const url = URL.createObjectURL(res.data)
  const a = document.createElement('a')
  a.href = url
  a.download = name
  document.body.appendChild(a)
  a.click()
  a.remove()
  setTimeout(() => URL.revokeObjectURL(url), 1500)
}

export default api
