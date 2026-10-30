// 会话信息读写：统一收口，避免各页面散落 localStorage 键名
const KEYS = {
  token: 'token',
  username: 'username',
  role: 'role',
  tenantId: 'tenantId',
  tenantName: 'tenantName',
  isSuper: 'isSuper',
  displayName: 'displayName',
  authSource: 'authSource',
}

export function saveSession(data = {}) {
  if (data.access_token) localStorage.setItem(KEYS.token, data.access_token)
  if (data.username) localStorage.setItem(KEYS.username, data.username)
  if (data.role) localStorage.setItem(KEYS.role, data.role)
  if (data.tenant_id) localStorage.setItem(KEYS.tenantId, data.tenant_id)
  if (data.tenant_name) localStorage.setItem(KEYS.tenantName, data.tenant_name)
  localStorage.setItem(KEYS.isSuper, data.is_super ? '1' : '0')
  if (data.display_name) localStorage.setItem(KEYS.displayName, data.display_name)
  if (data.auth_source) localStorage.setItem(KEYS.authSource, data.auth_source)
}

export function saveMe(me = {}) {
  saveSession({ username: me.username, role: me.role, tenant_id: me.tenant_id,
    tenant_name: me.tenant_name, is_super: me.is_super,
    display_name: me.display_name, auth_source: me.auth_source })
}

export function clearSession() {
  Object.values(KEYS).forEach((k) => localStorage.removeItem(k))
}

export const getToken = () => localStorage.getItem(KEYS.token) || ''
export const getUsername = () => localStorage.getItem(KEYS.username) || ''
export const getRole = () => localStorage.getItem(KEYS.role) || ''
export const getTenantName = () => localStorage.getItem(KEYS.tenantName) || ''
export const getDisplayName = () => localStorage.getItem(KEYS.displayName) || getUsername()
export const isSuper = () => localStorage.getItem(KEYS.isSuper) === '1'
export const getAuthSource = () => localStorage.getItem(KEYS.authSource) || 'local'
export const isLoggedIn = () => Boolean(getToken())
