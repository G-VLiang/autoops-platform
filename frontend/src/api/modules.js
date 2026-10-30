import api from './index'

// 认证
export const login = (username, password) => api.post('/auth/login', { username, password })
export const getProviders = () => api.get('/auth/providers')
export const getMe = () => api.get('/auth/me')
export const oidcLoginUrl = () => '/api/v1/auth/oidc/login'

// 主机组
export const listGroups = () => api.get('/hosts/groups')
export const createGroup = (data) => api.post('/hosts/groups', data)

// 主机
export const listHosts = (groupId) => api.get('/hosts', { params: { group_id: groupId } })
export const createHost = (data) => api.post('/hosts', data)
export const deleteHost = (id) => api.delete(`/hosts/${id}`)
export const probeHosts = (data = {}) => api.post('/hosts/probe', data)
export const probeHost = (id) => api.post(`/hosts/${id}/probe`)

// 任务
export const listTasks = () => api.get('/tasks')
export const createTask = (data) => api.post('/tasks', data)
export const getTask = (id) => api.get(`/tasks/${id}`)
export const getTaskLogs = (id) => api.get(`/tasks/${id}/logs`)
export const listLibrary = (params) => api.get('/tasks/library', { params })
export const listLibraryCategories = () => api.get('/tasks/library/categories')
export const createTaskFromLibrary = (data) => api.post('/tasks/from-library', data)

// 巡检
export const listTemplates = () => api.get('/inspections/templates')
export const createTemplate = (data) => api.post('/inspections/templates', data)
export const updateTemplate = (id, data) => api.put(`/inspections/templates/${id}`, data)
export const deleteTemplate = (id) => api.delete(`/inspections/templates/${id}`)
export const generatePlaybook = (data) => api.post('/inspections/generate', data)

// 巡检计划
export const listPlans = () => api.get('/plans')
export const createPlan = (data) => api.post('/plans', data)
export const updatePlan = (id, data) => api.put(`/plans/${id}`, data)
export const deletePlan = (id) => api.delete(`/plans/${id}`)
export const runPlan = (id) => api.post(`/plans/${id}/run`)
export const previewCron = (cron, count = 5) => api.post('/plans/cron/preview', { cron, count })

// 巡检报告
export const listReports = (planId) => api.get('/plans/reports', { params: { plan_id: planId } })
export const reportExportUrl = (id, format = 'pdf') =>
  `/plans/reports/${id}/export?format=${format}`
export const reportsExportAllUrl = (days = 30) =>
  `/plans/reports/export-all?format=xlsx&days=${days}`

// 告警中心
export const listAlertConfigs = () => api.get('/alerts/configs')
export const createAlertConfig = (data) => api.post('/alerts/configs', data)
export const updateAlertConfig = (id, data) => api.put(`/alerts/configs/${id}`, data)
export const deleteAlertConfig = (id) => api.delete(`/alerts/configs/${id}`)
export const testAlertConfig = (id, severity = 'warning') =>
  api.post(`/alerts/configs/${id}/test`, null, { params: { severity } })
export const listAlertEvents = (params) => api.get('/alerts/events', { params })
export const resolveAlertEvent = (id) => api.post(`/alerts/events/${id}/resolve`)
export const getAlertSummary = () => api.get('/alerts/summary')
export const listSilences = () => api.get('/alerts/silences')
export const createSilence = (data) => api.post('/alerts/silences', data)
export const deleteSilence = (id) => api.delete(`/alerts/silences/${id}`)

// 凭据管理
export const listCredentials = () => api.get('/credentials')
export const createCredential = (data) => api.post('/credentials', data)
export const deleteCredential = (id) => api.delete(`/credentials/${id}`)

// 审计日志
export const listAudit = (params) => api.get('/audit', { params })
export const auditFacets = () => api.get('/audit/facets')
export const auditExportPath = (params = {}) => {
  const qs = new URLSearchParams(
    Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== ''),
  ).toString()
  return `/audit/export${qs ? '?' + qs : ''}`
}

// 统计看板
export const getDashboard = (days = 14) => api.get('/stats/dashboard', { params: { days } })
export const getOverview = () => api.get('/stats/overview')
export const getTrend = (days = 14) => api.get('/stats/trend', { params: { days } })
export const getHotspots = (days = 30, limit = 5) =>
  api.get('/stats/hotspots', { params: { days, limit } })

// 租户
export const listTenants = () => api.get('/tenants')
export const createTenant = (data) => api.post('/tenants', data)
export const updateTenant = (id, data) => api.put(`/tenants/${id}`, data)

// 系统
export const getSystemStatus = () => api.get('/system/status')
export const reloadScheduler = () => api.post('/system/scheduler/reload')
