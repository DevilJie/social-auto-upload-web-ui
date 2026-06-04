import axios from 'axios'
import { ElMessage } from 'element-plus'

// 创建axios实例
const request = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '',
  headers: {
    'Content-Type': 'application/json'
  }
})

// 请求拦截器
request.interceptors.request.use(
  (config) => {
    // 可以在这里添加token等认证信息
    const token = localStorage.getItem('token')
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  (error) => {
    console.error('请求错误:', error)
    return Promise.reject(error)
  }
)

/**
 * 从后端错误信息中提取用户可读的消息（去掉 Python 堆栈）
 * 规则：只取第一行；如果包含 "Error:" 或 "错误:" 则取其后面的部分
 */
function extractUserMessage(raw) {
  if (!raw) return ''
  const text = String(raw)
  // 取第一行
  const firstLine = text.split('\n')[0].trim()
  // 如果包含典型错误前缀，取冒号后面的内容
  const match = firstLine.match(/(?:Error|错误|失败|异常|Exception)[:：]\s*(.+)/)
  return match ? match[1].trim() : firstLine
}

// 响应拦截器
request.interceptors.response.use(
  (response) => {
    const { data } = response

    // 根据后端接口规范处理响应
    if (data.code === 200 || data.success) {
      return data
    } else {
      const msg = extractUserMessage(data.msg || data.message) || '请求失败'
      ElMessage.error(msg)
      return Promise.reject(new Error(msg))
    }
  },
  (error) => {
    console.error('响应错误:', error)

    // 处理HTTP错误状态码
    if (error.response) {
      const { status } = error.response
      const rawMsg = error.response?.data?.msg || error.response?.data?.message || ''
      const msg = extractUserMessage(rawMsg)

      switch (status) {
        case 400:
          ElMessage.error(msg || '请求参数错误')
          break
        case 401:
          ElMessage.error('未授权，请重新登录')
          break
        case 403:
          ElMessage.error('拒绝访问')
          break
        case 404:
          ElMessage.error('请求地址不存在')
          break
        case 500:
          ElMessage.error(msg || '服务器内部错误')
          break
        default:
          ElMessage.error(msg || '网络错误')
      }
    } else {
      ElMessage.error('网络连接失败')
    }

    return Promise.reject(error)
  }
)

// 封装常用的请求方法
export const http = {
  get(url, params) {
    return request.get(url, { params })
  },
  
  post(url, data, config = {}) {
    return request.post(url, data, config)
  },
  
  put(url, data, config = {}) {
    return request.put(url, data, config)
  },
  
  delete(url, params) {
    return request.delete(url, { params })
  },
  
  upload(url, formData, onUploadProgress) {
    return request.post(url, formData, {
      headers: {
        'Content-Type': 'multipart/form-data'
      },
      onUploadProgress
    })
  }
}

export default request