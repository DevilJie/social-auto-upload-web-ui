# Vue3 + Vite 项目

一个基于 Vue3、Vite、Element Plus、Pinia、Vue Router 和 Axios 的现代化前端项目模板。

## 🚀 特性

- ⚡️ **Vite** - 极速的构建工具
- 🖖 **Vue 3** - 渐进式 JavaScript 框架
- 🎨 **Element Plus** - 基于 Vue 3 的组件库
- 🗂 **Vue Router** - 官方路由管理器（WebHash 模式）
- 📦 **Pinia** - 新一代状态管理
- 🔗 **Axios** - HTTP 请求库（已封装）
- 🎯 **Sass** - CSS 预处理器
- 📁 **规范化目录结构** - views 存放页面，components 存放组件
- 🔧 **完整配置** - 包含开发和生产环境配置

## 📦 安装

```bash
# 安装依赖
npm install

# 启动开发服务器
npm run dev

# 构建生产版本
npm run build

# 预览生产构建
npm run preview
```

## 📁 项目结构

```
src/
├── api/                 # API 接口
│   ├── index.js        # API 统一导出
│   └── user.js         # 用户相关 API
├── components/          # 公共组件
│   └── HelloWorld.vue  # 示例组件
├── router/             # 路由配置
│   └── index.js        # 路由主文件
├── stores/             # 状态管理
│   ├── index.js        # Pinia 配置
│   └── user.js         # 用户状态
├── styles/             # 样式文件
│   ├── index.scss      # 主样式文件
│   ├── reset.scss      # 重置样式
│   └── variables.scss  # 样式变量
├── utils/              # 工具函数
│   └── request.js      # HTTP 请求封装
├── views/              # 页面组件
│   ├── Home.vue        # 首页
│   └── About.vue       # 关于页面
├── App.vue             # 根组件
└── main.js             # 入口文件
```

## 🔧 配置说明

### 环境变量

- `.env` - 通用环境变量
- `.env.development` - 开发环境变量
- `.env.production` - 生产环境变量

### 路由配置

项目使用 Vue Router 4，配置为 WebHash 模式，路由文件位于 `src/router/index.js`。

### 状态管理

使用 Pinia 进行状态管理，store 文件位于 `src/stores/` 目录。

### HTTP 请求

Axios 已经过封装，包含：
- 请求/响应拦截器
- 错误处理
- Token 自动添加
- 统一的响应格式处理

使用方式：
```javascript
import { http } from '@/utils/request'

// GET 请求
const data = await http.get('/api/users')

// POST 请求
const result = await http.post('/api/users', { name: 'John' })
```

### 样式系统

- 使用 Sass 作为 CSS 预处理器
- 已删除所有浏览器默认样式
- 提供了完整的样式变量和工具类
- 支持 Element Plus 主题定制

## 🎨 组件库

项目集成了 Element Plus，所有组件都可以直接使用：

```vue
<template>
  <el-button type="primary">按钮</el-button>
  <el-input v-model="input" placeholder="请输入内容"></el-input>
</template>
```

## 📝 开发规范

1. **页面组件** 放在 `src/views/` 目录
2. **公共组件** 放在 `src/components/` 目录
3. **使用 setup 语法糖** 编写组件
4. **样式使用 Sass** 并遵循 BEM 命名规范
5. **API 请求** 统一放在 `src/api/` 目录
6. **状态管理** 按模块划分，放在 `src/stores/` 目录

## 🚀 部署

```bash
# 构建生产版本
npm run build

# 构建完成后，dist 目录包含所有静态文件
# 可以部署到任何静态文件服务器
```

## 📄 许可证

Apache License 2.0
