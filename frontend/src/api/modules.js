import api from './index'

// 认证
export const login = (username, password) => api.post('/auth/login', { username, password })

// 主机组
export const listGroups = () => api.get('/hosts/groups')
export const createGroup = (data) => api.post('/hosts/groups', data)

// 主机
export const listHosts = (groupId) => api.get('/hosts', { params: { group_id: groupId } })
export const createHost = (data) => api.post('/hosts', data)
export const deleteHost = (id) => api.delete(`/hosts/${id}`)

// 任务
export const listTasks = () => api.get('/tasks')
export const createTask = (data) => api.post('/tasks', data)
export const getTask = (id) => api.get(`/tasks/${id}`)
export const getTaskLogs = (id) => api.get(`/tasks/${id}/logs`)

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

// 巡检报告
export const listReports = (planId) => api.get('/plans/reports', { params: { plan_id: planId } })

// 告警配置
export const listAlerts = () => api.get('/plans/alerts')
export const createAlert = (data) => api.post('/plans/alerts', data)
export const deleteAlert = (id) => api.delete(`/plans/alerts/${id}`)
export const testAlert = (id) => api.post(`/plans/alerts/${id}/test`)

// 凭据管理
export const listCredentials = () => api.get('/credentials')
export const createCredential = (data) => api.post('/credentials', data)
export const deleteCredential = (id) => api.delete(`/credentials/${id}`)

// 审计日志
export const listAudit = () => api.get('/audit')
