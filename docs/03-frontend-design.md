# AI资讯早报监控面板 - 前端详细设计方案

> 版本：v1.0 | 日期：2026-04-10
> 目标读者：AI Agent（拿到此文档即可独立实现前端）

---

## 一、项目初始化

### 1.1 创建项目

```bash
cd ~/.openclaw/workspace/skills/ai-news-v10/scripts

# 使用 Vite 创建 Vue3 + TypeScript 项目
npm create vite@latest frontend -- --template vue-ts

cd frontend
pnpm install
```

### 1.2 安装依赖

```bash
pnpm add vue-router@4 pinia element-plus echarts vue-echarts axios
```

### 1.3 安装开发依赖

```bash
pnpm add -D @vitejs/plugin-vue
```

### 1.4 vite.config.ts 配置

```typescript
// scripts/frontend/vite.config.ts
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src')
    }
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true
      }
    }
  }
})
```

### 1.5 main.ts 入口

```typescript
// scripts/frontend/src/main.ts
import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import 'element-plus/theme-chalk/dark/css-vars.css'
import App from './App.vue'
import router from './router'

const app = createApp(App)

app.use(createPinia())
app.use(router)
app.use(ElementPlus)

app.mount('#app')
```

---

## 二、目录结构

```
scripts/frontend/src/
├── api/
│   └── index.ts              # Axios API 调用封装
├── components/
│   ├── FunnelChart.vue        # 漏斗图（ECharts）
│   ├── MetricCard.vue         # 指标卡片
│   ├── TrendChart.vue         # 趋势折线图
│   ├── NewsTable.vue          # 新闻列表（可展开行）
│   └── LogViewer.vue          # 日志查看器
├── views/
│   ├── Dashboard.vue           # 概览页 /
│   ├── RawNews.vue            # 原始数据页 /raw-news
│   ├── Filtered.vue           # 过滤明细页 /filtered
│   ├── Config.vue             # 配置管理页 /config
│   └── Logs.vue              # 日志中心页 /logs
├── router/
│   └── index.ts              # 路由配置
├── stores/
│   └── app.ts                # 全局状态（Pinia）
├── App.vue
├── main.ts
└── env.d.ts
```

---

## 三、API 调用层（api/index.ts）

```typescript
// scripts/frontend/src/api/index.ts
import axios from 'axios'
import type {
  Run, FunnelData, RemovedItem, RawNewsItem, ConfigHistory
} from './types'

const api = axios.create({
  baseURL: '/api',
  timeout: 10000,
  headers: { 'Content-Type': 'application/json' }
})

// ---------- runs ----------

export async function getRuns(params: {
  days?: number
  page?: number
  page_size?: number
}) {
  const { data } = await api.get<{
    runs: Run[]
    total: number
    page: number
    page_size: number
    pages: number
  }>('/runs', { params })
  return data
}

export async function getRunDetail(date: string) {
  const { data } = await api.get(`/runs/${date}`)
  return data as {
    run: Run
    steps: StepDetail[]
  }
}

export async function getFunnel(date: string) {
  const { data } = await api.get<FunnelData>(`/runs/${date}/funnel`)
  return data
}

// ---------- raw_news ----------

export async function getRawNews(params: {
  date?: string
  source?: string
  page?: number
  page_size?: number
}) {
  const { data } = await api.get<{
    items: RawNewsItem[]
    total: number
    page: number
    page_size: number
    pages: number
  }>('/raw-news', { params })
  return data
}

// ---------- removed ----------

export async function getRemoved(params: {
  date?: string
  step?: string
  source?: string
  page?: number
  page_size?: number
}) {
  const { data } = await api.get<{
    items: RemovedItem[]
    total: number
    page: number
    page_size: number
    pages: number
  }>('/removed', { params })
  return data
}

// ---------- config ----------

export async function getCurrentConfig() {
  const { data } = await api.get<{ config: any; date: string | null }>('/config/current')
  return data
}

export async function getConfigHistory(limit = 30) {
  const { data } = await api.get<ConfigHistory[]>(`/config/history?limit=${limit}`)
  return data
}

export async function updateConfig(config: any) {
  const { data } = await api.post('/config', { config })
  return data
}
```

### types.ts（类型定义）

```typescript
// scripts/frontend/src/api/types.ts

export interface Run {
  id: number
  date: string
  started_at: string
  finished_at: string | null
  status: 'running' | 'success' | 'failed'
  duration_seconds: number | null
  total_collected: number
  total_output: number
  error_message: string | null
}

export interface FunnelStep {
  step: string
  input: number
  output: number
  removed: number
}

export interface FunnelData {
  run: Run
  steps: FunnelStep[]
}

export interface StepDetail {
  step: string
  input_count: number
  output_count: number
  removed_count: number
  duration_seconds: number | null
  removed: RemovedItem[]
}

export interface RemovedItem {
  id: number
  title: string
  source: string
  reason: string
  reason_detail: string
  category: string
  step: string
  date: string
}

export interface RawNewsItem {
  id: number
  source: string
  title: string
  link: string
  time_ago: string
  desc: string
  raw_extra: string
  collected_at: string
  filtered_by: string | null
}

export interface ConfigHistory {
  id: number
  date: string
  created_at: string
}
```

---

## 四、路由配置（router/index.ts）

```typescript
// scripts/frontend/src/router/index.ts
import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      name: 'dashboard',
      component: () => import('@/views/Dashboard.vue'),
      meta: { title: '概览' }
    },
    {
      path: '/raw-news',
      name: 'raw-news',
      component: () => import('@/views/RawNews.vue'),
      meta: { title: '原始数据' }
    },
    {
      path: '/filtered',
      name: 'filtered',
      component: () => import('@/views/Filtered.vue'),
      meta: { title: '过滤明细' }
    },
    {
      path: '/config',
      name: 'config',
      component: () => import('@/views/Config.vue'),
      meta: { title: '配置管理' }
    },
    {
      path: '/logs',
      name: 'logs',
      component: () => import('@/views/Logs.vue'),
      meta: { title: '日志中心' }
    }
  ]
})

router.beforeEach((to) => {
  document.title = `${to.meta.title || '监控'} - AI资讯早报`
})

export default router
```

---

## 五、全局状态（stores/app.ts）

```typescript
// scripts/frontend/src/stores/app.ts
import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useAppStore = defineStore('app', () => {
  // 当前选中的日期
  const currentDate = ref(new Date().toISOString().slice(0, 10).replace(/-/g, ''))

  // 数据源列表（静态配置）
  const sources = [
    { value: 'huxiu', label: '虎嗅' },
    { value: 'infoq', label: 'InfoQ' },
    { value: '量子位', label: '量子位' },
    { value: 'huggingface', label: 'HuggingFace' },
    { value: 'github', label: 'GitHub' },
    { value: 'openrouter', label: 'OpenRouter' }
  ]

  // 拦截器列表（静态配置）
  const interceptors = [
    { value: 'time_filter', label: '时间过滤' },
    { value: 'keyword_filter', label: '关键词过滤' },
    { value: 'bge_dedup', label: '语义去重' },
    { value: 'llm_classify', label: 'LLM分类' },
    { value: 'llm_summary', label: 'LLM摘要' }
  ]

  function setCurrentDate(date: string) {
    currentDate.value = date
  }

  return { currentDate, sources, interceptors, setCurrentDate }
})
```

---

## 六、页面组件详解

### 6.1 App.vue（根组件 + 布局）

```vue
<!-- scripts/frontend/src/App.vue -->
<template>
  <el-config-provider :locale="zhCn">
    <el-container class="app-container">
      <!-- 侧边栏 -->
      <el-aside width="220px" class="sidebar">
        <div class="logo">
          <span class="logo-icon">📡</span>
          <span class="logo-text">AI资讯监控</span>
        </div>
        <el-menu
          :default-active="route.path"
          :router="true"
          class="sidebar-menu"
          background-color="#1a1a2e"
          text-color="#a0a0b0"
          active-text-color="#409eff"
        >
          <el-menu-item index="/">
            <span>📊</span><span>概览</span>
          </el-menu-item>
          <el-menu-item index="/raw-news">
            <span>📥</span><span>原始数据</span>
          </el-menu-item>
          <el-menu-item index="/filtered">
            <span>🗑️</span><span>过滤明细</span>
          </el-menu-item>
          <el-menu-item index="/config">
            <span>⚙️</span><span>配置管理</span>
          </el-menu-item>
          <el-menu-item index="/logs">
            <span>📋</span><span>日志中心</span>
          </el-menu-item>
        </el-menu>
      </el-aside>

      <!-- 主内容 -->
      <el-container>
        <el-header class="header">
          <div class="header-left">
            <el-date-picker
              v-model="selectedDate"
              type="date"
              placeholder="选择日期"
              format="YYYY-MM-DD"
              value-format="YYYYMMDD"
              size="default"
              style="width: 160px"
              @change="onDateChange"
            />
          </div>
          <div class="header-right">
            <el-tag :type="runStatusType" effect="dark">
              {{ runStatusText }}
            </el-tag>
            <span class="header-time">{{ currentTime }}</span>
          </div>
        </el-header>

        <el-main class="main-content">
          <router-view />
        </el-main>
      </el-container>
    </el-container>
  </el-config-provider>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRoute } from 'vue-router'
import zhCn from 'element-plus/dist/locale/zh-cn.mjs'
import { useAppStore } from '@/stores/app'

const route = useRoute()
const store = useAppStore()

const selectedDate = ref(store.currentDate)
const currentTime = ref('')
const runStatus = ref<'running' | 'success' | 'failed' | 'none'>('none')

const runStatusType = computed(() => ({
  running: 'warning',
  success: 'success',
  failed: 'danger',
  none: 'info'
}[runStatus.value]))

const runStatusText = computed(() => ({
  running: '运行中',
  success: '已完成',
  failed: '失败',
  none: '无数据'
}[runStatus.value]))

function onDateChange(date: string) {
  store.setCurrentDate(date)
}

let timer: number
onMounted(() => {
  timer = window.setInterval(() => {
    currentTime.value = new Date().toLocaleString('zh-CN')
  }, 1000)
})
onUnmounted(() => clearInterval(timer))
</script>

<style>
* { margin: 0; padding: 0; box-sizing: border-box; }

body {
  background: #0f0f1a;
  color: #e0e0e0;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
}

.app-container {
  height: 100vh;
}

.sidebar {
  background: #1a1a2e;
  border-right: 1px solid #2a2a3e;
}

.logo {
  padding: 20px 16px;
  border-bottom: 1px solid #2a2a3e;
  display: flex;
  align-items: center;
  gap: 10px;
}

.logo-icon { font-size: 22px; }
.logo-text { font-size: 15px; font-weight: 600; color: #fff; }

.sidebar-menu {
  border-right: none !important;
}

.sidebar-menu .el-menu-item {
  height: 48px;
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 14px;
}

.sidebar-menu .el-menu-item.is-active {
  background: #1f2d3d !important;
}

.header {
  background: #1a1a2e;
  border-bottom: 1px solid #2a2a3e;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 20px;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 16px;
}

.header-time {
  font-size: 13px;
  color: #888;
}

.main-content {
  padding: 20px;
  overflow-y: auto;
  background: #0f0f1a;
}

/* Element Plus 暗黑适配 */
.el-table { background: #1a1a2e !important; }
.el-table th { background: #252536 !important; }
.el-card { background: #1a1a2e; border: 1px solid #2a2a3e; }
.el-input__wrapper { background: #252536 !important; border-color: #2a2a3e !important; }
</style>
```

### 6.2 Dashboard.vue（概览页）

```vue
<!-- scripts/frontend/src/views/Dashboard.vue -->
<template>
  <div class="dashboard">
    <!-- 顶部指标卡 -->
    <el-row :gutter="16" class="metric-row">
      <el-col :span="6" v-for="card in metricCards" :key="card.label">
        <MetricCard v-bind="card" />
      </el-col>
    </el-row>

    <!-- 漏斗图 + 趋势图 -->
    <el-row :gutter="16" class="chart-row">
      <el-col :span="14">
        <el-card class="chart-card">
          <template #header>
            <div class="card-header">
              <span>📊 数据流转漏斗</span>
              <span class="date-label">{{ store.currentDate }}</span>
            </div>
          </template>
          <FunnelChart :data="funnelData" @click-step="onFunnelClick" />
        </el-card>
      </el-col>

      <el-col :span="10">
        <el-card class="chart-card">
          <template #header>
            <span>📈 近7天过滤趋势</span>
          </template>
          <TrendChart :data="trendData" />
        </el-card>
      </el-col>
    </el-row>

    <!-- 拦截器耗时排行 -->
    <el-card class="step-card">
      <template #header>
        <span>⚡ 各拦截器耗时排行</span>
      </template>
      <el-table :data="stepDurations" stripe>
        <el-table-column prop="step" label="拦截器" width="180">
          <template #default="{ row }">
            <el-tag size="small">{{ row.step }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="input" label="输入" width="100" align="center" />
        <el-table-column prop="output" label="输出" width="100" align="center" />
        <el-table-column prop="removed" label="过滤" width="100" align="center">
          <template #default="{ row }">
            <span style="color: #ff6b6b">{{ row.removed }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="duration" label="耗时" align="center">
          <template #default="{ row }">
            <span :style="{ color: row.duration > 30 ? '#ff6b6b' : '#67c23a' }">
              {{ row.duration.toFixed(1) }}s
            </span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { getRunDetail, getRuns } from '@/api'
import { useAppStore } from '@/stores/app'
import MetricCard from '@/components/MetricCard.vue'
import FunnelChart from '@/components/FunnelChart.vue'
import TrendChart from '@/components/TrendChart.vue'

const store = useAppStore()
const router = useRouter()

const runDetail = ref<any>(null)
const runsList = ref<any[]>([])
const trendData = ref<any[]>([])

const funnelData = computed(() => {
  if (!runDetail.value?.steps) return []
  return runDetail.value.steps.map((s: any) => ({
    step: s.step,
    input: s.input_count,
    output: s.output_count,
    removed: s.removed_count
  }))
})

const metricCards = computed(() => {
  const run = runDetail.value?.run
  if (!run) return []
  const collected = run.total_collected || 0
  const output = run.total_output || 0
  const filtered = collected - output
  const filterRate = collected > 0 ? ((filtered / collected) * 100).toFixed(1) : '0.0'
  return [
    { label: '总采集', value: collected, icon: '📥', color: '#409eff' },
    { label: '最终输出', value: output, icon: '✅', color: '#67c23a' },
    { label: '过滤率', value: `${filterRate}%`, icon: '🗑️', color: '#e6a23c' },
    { label: '总耗时', value: `${(run.duration_seconds || 0).toFixed(1)}s`, icon: '⏱️', color: '#909399' }
  ]
})

const stepDurations = computed(() => {
  if (!runDetail.value?.steps) return []
  return runDetail.value.steps
    .filter((s: any) => s.duration_seconds !== null)
    .sort((a: any, b: any) => (b.duration_seconds || 0) - (a.duration_seconds || 0))
})

function onFunnelClick(step: string) {
  router.push({ path: '/filtered', query: { step } })
}

async function loadData() {
  const date = store.currentDate
  try {
    runDetail.value = await getRunDetail(date)
  } catch (e) {
    runDetail.value = null
  }

  // 加载近7天趋势
  try {
    const { runs } = await getRuns({ days: 7 })
    runsList.value = runs
    trendData.value = runs.slice().reverse().map((r: any) => ({
      date: r.date,
      collected: r.total_collected,
      output: r.total_output,
      removed: r.total_collected - r.total_output
    }))
  } catch (e) {
    trendData.value = []
  }
}

watch(() => store.currentDate, loadData)
onMounted(loadData)
</script>

<style scoped>
.dashboard { }
.metric-row { margin-bottom: 16px; }
.chart-row { margin-bottom: 16px; }
.chart-card .card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.date-label { font-size: 13px; color: #888; }
.step-card { }
</style>
```

### 6.3 Filtered.vue（过滤明细页）

```vue
<!-- scripts/frontend/src/views/Filtered.vue -->
<template>
  <div class="filtered-page">
    <!-- 筛选栏 -->
    <el-card class="filter-card">
      <el-form inline>
        <el-form-item label="拦截器">
          <el-select v-model="filterStep" clearable placeholder="全部" style="width: 140px">
            <el-option
              v-for="it in store.interceptors"
              :key="it.value"
              :label="it.label"
              :value="it.value"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="来源">
          <el-select v-model="filterSource" clearable placeholder="全部" style="width: 120px">
            <el-option
              v-for="src in store.sources"
              :key="src.value"
              :label="src.label"
              :value="src.value"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="关键词">
          <el-input v-model="filterKeyword" placeholder="搜索标题" clearable style="width: 200px" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="loadData">查询</el-button>
        </el-form-item>
      </el-form>

      <!-- 统计 -->
      <div class="filter-stats">
        <el-tag type="info">共 {{ total }} 条</el-tag>
        <el-tag
          v-for="st in store.interceptors"
          :key="st.value"
          :type="filterStep === st.value ? 'primary' : 'info'"
          style="cursor: pointer"
          @click="filterStep = filterStep === st.value ? '' : st.value; loadData()"
        >
          {{ st.label }}
        </el-tag>
      </div>
    </el-card>

    <!-- 数据表格 -->
    <el-card class="table-card">
      <el-table :data="tableData" stripe :expand-row-keys="expandedRows" @expand-change="onExpand">
        <el-table-column type="expand">
          <template #default="{ row }">
            <div class="expanded-content">
              <p><strong>标题：</strong>{{ row.title }}</p>
              <p><strong>原因详情：</strong>{{ row.reason_detail || row.reason || '无' }}</p>
              <p><strong>分类：</strong>{{ row.category || '无' }}</p>
              <p><strong>日期：</strong>{{ row.date }}</p>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="source" label="来源" width="80">
          <template #default="{ row }">
            <el-tag size="small">{{ sourceLabel(row.source) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="step" label="拦截器" width="120">
          <template #default="{ row }">
            <el-tag type="danger" size="small">{{ interceptorLabel(row.step) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="title" label="标题" min-width="300" show-overflow-tooltip />
        <el-table-column prop="reason" label="过滤原因" min-width="150" show-overflow-tooltip />
        <el-table-column prop="date" label="日期" width="100" />
      </el-table>

      <el-pagination
        v-model:current-page="page"
        :page-size="pageSize"
        :total="total"
        layout="prev, pager, next"
        style="margin-top: 16px; justify-content: flex-end"
        @current-change="loadData"
      />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { getRemoved } from '@/api'
import { useAppStore } from '@/stores/app'

const store = useAppStore()
const tableData = ref<any[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(50)
const filterStep = ref('')
const filterSource = ref('')
const filterKeyword = ref('')
const expandedRows = ref<string[]>([])

function sourceLabel(src: string) {
  return store.sources.find(s => s.value === src)?.label || src
}

function interceptorLabel(step: string) {
  return store.interceptors.find(s => s.value === step)?.label || step
}

function onExpand(row: any) {
  const idx = expandedRows.value.indexOf(row.id)
  if (idx >= 0) {
    expandedRows.value.splice(idx, 1)
  } else {
    expandedRows.value.push(row.id)
  }
}

async function loadData() {
  const result = await getRemoved({
    date: store.currentDate,
    step: filterStep.value || undefined,
    source: filterSource.value || undefined,
    page: page.value,
    page_size: pageSize.value
  })

  let items = result.items
  if (filterKeyword.value) {
    items = items.filter(i =>
      i.title.toLowerCase().includes(filterKeyword.value.toLowerCase())
    )
  }

  tableData.value = items
  total.value = result.total
}

onMounted(loadData)
</script>

<style scoped>
.filter-card { margin-bottom: 16px; }
.filter-stats { display: flex; gap: 8px; align-items: center; margin-top: 12px; }
.expanded-content { padding: 8px 16px; }
.expanded-content p { margin: 4px 0; font-size: 13px; color: #aaa; }
.expanded-content strong { color: #e0e0e0; }
</style>
```

### 6.4 RawNews.vue（原始数据页）

```vue
<!-- scripts/frontend/src/views/RawNews.vue -->
<template>
  <div class="raw-news">
    <!-- 筛选栏 -->
    <el-card class="filter-card">
      <el-form inline>
        <el-form-item label="数据源">
          <el-select v-model="filterSource" clearable placeholder="全部" style="width: 140px">
            <el-option
              v-for="src in store.sources"
              :key="src.value"
              :label="src.label"
              :value="src.value"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="filterStatus" clearable placeholder="全部" style="width: 140px">
            <el-option label="全部" value="" />
            <el-option label="保留" value="kept" />
            <el-option label="被过滤" value="filtered" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="loadData">查询</el-button>
        </el-form-item>
      </el-form>

      <!-- 来源统计 -->
      <div class="source-stats">
        <span class="stat-label">各来源采集量：</span>
        <el-tag v-for="st in sourceStats" :key="st.source" type="info" style="margin-right: 8px">
          {{ sourceLabel(st.source) }}: {{ st.total }} / 保留: {{ st.kept }} / 过滤: {{ st.filtered }}
        </el-tag>
      </div>
    </el-card>

    <!-- 数据表格 -->
    <el-card class="table-card">
      <el-table :data="tableData" stripe>
        <el-table-column prop="source" label="来源" width="100">
          <template #default="{ row }">
            <el-tag size="small">{{ sourceLabel(row.source) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="title" label="标题" min-width="300" show-overflow-tooltip />
        <el-table-column prop="time_ago" label="时间" width="100" />
        <el-table-column prop="desc" label="描述" min-width="200" show-overflow-tooltip />
        <el-table-column prop="filtered_by" label="状态" width="100" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.filtered_by" type="danger" size="small">
              🗑️ {{ interceptorLabel(row.filtered_by) }}
            </el-tag>
            <el-tag v-else type="success" size="small">✅ 保留</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="80" align="center">
          <template #default="{ row }">
            <el-link :href="row.link" target="_blank" type="primary" size="small">原文</el-link>
          </template>
        </el-table-column>
      </el-table>

      <el-pagination
        v-model:current-page="page"
        :page-size="pageSize"
        :total="total"
        layout="prev, pager, next"
        style="margin-top: 16px; justify-content: flex-end"
        @current-change="loadData"
      />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { getRawNews } from '@/api'
import { useAppStore } from '@/stores/app'

const store = useAppStore()
const tableData = ref<any[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(50)
const filterSource = ref('')
const filterStatus = ref('')

const sourceStats = computed(() => {
  const stats: Record<string, { total: number; kept: number; filtered: number }> = {}
  for (const item of tableData.value) {
    if (!stats[item.source]) {
      stats[item.source] = { total: 0, kept: 0, filtered: 0 }
    }
    stats[item.source].total++
    if (item.filtered_by) {
      stats[item.source].filtered++
    } else {
      stats[item.source].kept++
    }
  }
  return Object.entries(stats).map(([source, data]) => ({ source, ...data }))
})

function sourceLabel(src: string) {
  return store.sources.find(s => s.value === src)?.label || src
}

function interceptorLabel(step: string) {
  return store.interceptors.find(s => s.value === step)?.label || step
}

async function loadData() {
  const result = await getRawNews({
    date: store.currentDate,
    source: filterSource.value || undefined,
    page: page.value,
    page_size: pageSize.value
  })

  let items = result.items
  if (filterStatus.value) {
    items = items.filter(i => {
      if (filterStatus.value === 'kept') return !i.filtered_by
      if (filterStatus.value === 'filtered') return !!i.filtered_by
      return true
    })
  }

  tableData.value = items
  total.value = result.total
}

onMounted(loadData)
</script>

<style scoped>
.filter-card { margin-bottom: 16px; }
.source-stats { display: flex; gap: 8px; align-items: center; margin-top: 12px; flex-wrap: wrap; }
.stat-label { font-size: 13px; color: #888; }
</style>
```

### 6.5 Config.vue（配置管理页）

```vue
<!-- scripts/frontend/src/views/Config.vue -->
<template>
  <div class="config-page">
    <el-card>
      <template #header>
        <div class="card-header">
          <span>⚙️ 拦截器配置</span>
          <el-button type="primary" size="small" @click="saveConfig">💾 保存配置</el-button>
        </div>
      </template>

      <el-form :model="config" label-width="120px">
        <!-- 分类数量上限 -->
        <el-divider content-position="left">分类数量上限</el-divider>
        <el-row :gutter="16">
          <el-col :span="6" v-for="(limit, cat) in config.limits" :key="cat">
            <el-form-item :label="cat">
              <el-input-number v-model="config.limits[cat]" :min="1" :max="100" />
            </el-form-item>
          </el-col>
        </el-row>

        <!-- keyword_filter -->
        <el-divider content-position="left">关键词过滤</el-divider>
        <el-form-item label="过滤关键词">
          <el-select
            v-model="keywordFilterList"
            multiple
            filterable
            allow-create
            default-first-option
            placeholder="输入关键词后回车添加"
            style="width: 100%"
          >
            <el-option
              v-for="kw in keywordFilterList"
              :key="kw"
              :label="kw"
              :value="kw"
            />
          </el-select>
        </el-form-item>

        <!-- bge_dedup -->
        <el-divider content-position="left">语义去重</el-divider>
        <el-form-item label="相似度阈值">
          <el-slider
            v-model="bgeThreshold"
            :min="0.5"
            :max="0.99"
            :step="0.01"
            show-stops
            :format-tooltip="(v: number) => v.toFixed(2)"
          />
          <span style="margin-left: 12px; color: #888">{{ bgeThreshold.toFixed(2) }}</span>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 配置历史 -->
    <el-card style="margin-top: 16px">
      <template #header>
        <span>📋 配置变更历史</span>
      </template>
      <el-table :data="configHistory" stripe>
        <el-table-column prop="date" label="日期" width="120" />
        <el-table-column prop="created_at" label="保存时间" />
        <el-table-column label="操作" width="100">
          <template #default="{ row }">
            <el-button size="small" text type="primary" @click="viewSnapshot(row.id)">查看</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="dialogVisible" title="配置快照" width="600px">
      <pre>{{ snapshotContent }}</pre>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { getCurrentConfig, getConfigHistory, updateConfig } from '@/api'

const config = ref<any>({
  limits: { '国内AI资讯': 15, '国外AI资讯': 15, '智能硬件': 5, '其它科技资讯': 5 }
})
const keywordFilterList = ref<string[]>([])
const bgeThreshold = ref(0.8)
const configHistory = ref<any[]>([])
const dialogVisible = ref(false)
const snapshotContent = ref('')

async function loadConfig() {
  const result = await getCurrentConfig()
  if (result.config) {
    config.value = result.config
    if (result.config.keyword_filter) {
      keywordFilterList.value = result.config.keyword_filter
    }
  }
  configHistory.value = await getConfigHistory()
}

async function saveConfig() {
  try {
    await updateConfig({
      ...config.value,
      keyword_filter: keywordFilterList.value
    })
    ElMessage.success('配置已保存，下次任务生效')
  } catch (e) {
    ElMessage.error('保存失败')
  }
}

function viewSnapshot(id: number) {
  const item = configHistory.value.find(i => i.id === id)
  if (item) {
    snapshotContent.value = JSON.stringify(JSON.parse(item.config_json || '{}'), null, 2)
    dialogVisible.value = true
  }
}

onMounted(loadConfig)
</script>

<style scoped>
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
pre {
  background: #0f0f1a;
  padding: 16px;
  border-radius: 4px;
  font-size: 12px;
  overflow: auto;
  max-height: 400px;
  color: #67c23a;
}
</style>
```

### 6.6 Logs.vue（日志中心页）

```vue
<!-- scripts/frontend/src/views/Logs.vue -->
<template>
  <div class="logs-page">
    <LogViewer :date="store.currentDate" />
  </div>
</template>

<script setup lang="ts">
import { useAppStore } from '@/stores/app'
import LogViewer from '@/components/LogViewer.vue'

const store = useAppStore()
</script>
```

---

## 七、公共组件

### 7.1 MetricCard.vue（指标卡片）

```vue
<template>
  <el-card class="metric-card" shadow="hover">
    <div class="metric-inner">
      <div class="metric-icon" :style="{ background: color + '20', color }">
        {{ icon }}
      </div>
      <div class="metric-content">
        <div class="metric-value">{{ value }}</div>
        <div class="metric-label">{{ label }}</div>
      </div>
    </div>
  </el-card>
</template>

<script setup lang="ts">
defineProps<{
  label: string
  value: string | number
  icon: string
  color?: string
}>()
</script>

<style scoped>
.metric-card { cursor: default; }
.metric-inner {
  display: flex;
  align-items: center;
  gap: 16px;
}
.metric-icon {
  width: 48px;
  height: 48px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 22px;
  flex-shrink: 0;
}
.metric-value {
  font-size: 24px;
  font-weight: 700;
  color: #fff;
  line-height: 1.2;
}
.metric-label {
  font-size: 13px;
  color: #888;
  margin-top: 4px;
}
</style>
```

### 7.2 FunnelChart.vue（漏斗图）

```vue
<!-- 使用 ECharts 漏斗图 -->
<template>
  <div ref="chartRef" class="funnel-chart" />
</template>

<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import * as echarts from 'echarts'
import type { FunnelStep } from '@/api/types'

const props = defineProps<{
  data: FunnelStep[]
}>()

const emit = defineEmits<{
  (e: 'click-step', step: string): void
}>()

const chartRef = ref<HTMLDivElement>()

function buildChart() {
  if (!chartRef.value || !props.data.length) return

  const chart = echarts.init(chartRef.value)

  const steps = [
    { name: '原始采集', ...props.data[0] },
    ...props.data.map(s => ({
      name: stepLabel(s.step),
      ...s
    }))
  ]

  // 人工添加"最终输出"步骤（最后一项 output）
  const finalStep = {
    name: '最终输出',
    input: props.data[props.data.length - 1]?.output || 0,
    output: props.data[props.data.length - 1]?.output || 0,
    removed: 0
  }
  steps.push(finalStep)

  const option = {
    tooltip: {
      trigger: 'item',
      formatter: (p: any) => `${p.name}<br/>输入: ${p.data.value} → 输出: ${p.data.value2 || p.data.value}`
    },
    series: [{
      name: '数据漏斗',
      type: 'funnel',
      left: '5%',
      top: 20,
      bottom: 20,
      width: '60%',
      min: 0,
      max: props.data[0]?.input || 100,
      minSize: '15%',
      maxSize: '100%',
      sort: 'none',
      gap: 4,
      label: {
        show: true,
        position: 'inside',
        formatter: (p: any) => `${p.name}\n${p.data.value}`,
        color: '#fff',
        fontSize: 13
      },
      itemStyle: {
        borderColor: '#0f0f1a',
        borderWidth: 2
      },
      emphasis: {
        label: { fontSize: 15 }
      },
      data: steps.map((s, i) => ({
        name: s.name,
        value: s.input,
        value2: s.output,
        itemStyle: {
          color: [
            '#409eff', '#67c23a', '#e6a23c', '#f56c6c', '#909399', '#50a5d4'
          ][i % 6]
        }
      }))
    }]
  }

  chart.setOption(option)

  chart.on('click', (p: any) => {
    const stepName = props.data.find((_, i) => stepLabel(_.step) === p.name)?.step || p.name
    emit('click-step', stepName)
  })
}

function stepLabel(step: string) {
  const map: Record<string, string> = {
    time_filter: '时间过滤',
    keyword_filter: '关键词过滤',
    bge_dedup: '语义去重',
    llm_classify: 'LLM分类',
    llm_summary: 'LLM摘要'
  }
  return map[step] || step
}

onMounted(buildChart)
watch(() => props.data, buildChart)
</script>

<style scoped>
.funnel-chart { height: 320px; }
</style>
```

### 7.3 TrendChart.vue（趋势折线图）

```vue
<template>
  <div ref="chartRef" class="trend-chart" />
</template>

<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import * as echarts from 'echarts'

const props = defineProps<{
  data: Array<{ date: string; collected: number; output: number; removed: number }>
}>()

const chartRef = ref<HTMLDivElement>()

function buildChart() {
  if (!chartRef.value || !props.data.length) return

  const chart = echarts.init(chartRef.value)

  const option = {
    tooltip: { trigger: 'axis' },
    legend: {
      data: ['总采集', '最终输出', '过滤'],
      textStyle: { color: '#aaa' }
    },
    grid: { left: 40, right: 20, top: 30, bottom: 30 },
    xAxis: {
      type: 'category',
      data: props.data.map(d => `${d.date.slice(4, 6)}-${d.date.slice(6, 8)}`),
      axisLabel: { color: '#888' }
    },
    yAxis: {
      type: 'value',
      axisLabel: { color: '#888' },
      splitLine: { lineStyle: { color: '#2a2a3e' } }
    },
    series: [
      {
        name: '总采集', type: 'line',
        data: props.data.map(d => d.collected),
        smooth: true, itemStyle: { color: '#409eff' }
      },
      {
        name: '最终输出', type: 'line',
        data: props.data.map(d => d.output),
        smooth: true, itemStyle: { color: '#67c23a' }
      },
      {
        name: '过滤', type: 'line',
        data: props.data.map(d => d.removed),
        smooth: true, itemStyle: { color: '#f56c6c' }
      }
    ]
  }

  chart.setOption(option)
}

onMounted(buildChart)
watch(() => props.data, buildChart)
</script>

<style scoped>
.trend-chart { height: 260px; }
</style>
```

### 7.4 LogViewer.vue（日志查看器）

```vue
<template>
  <el-card>
    <template #header>
      <div class="card-header">
        <span>📋 运行日志</span>
        <el-button size="small" @click="loadLogs">🔄 刷新</el-button>
      </div>
    </template>

    <div class="log-container" ref="logContainerRef">
      <div
        v-for="(line, i) in logLines"
        :key="i"
        class="log-line"
        :class="getLineClass(line)"
      >
        <span class="log-time">{{ extractTime(line) }}</span>
        <span class="log-content">{{ line }}</span>
      </div>
      <div v-if="!logLines.length" class="log-empty">
        暂无日志数据
      </div>
    </div>
  </el-card>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useAppStore } from '@/stores/app'

const props = defineProps<{ date: string }>()
const store = useAppStore()
const logLines = ref<string[]>([])
const logContainerRef = ref<HTMLDivElement>()

function extractTime(line: string) {
  const match = line.match(/\[\d{2}:\d{2}:\d{2}\]/)
  return match ? match[0] : ''
}

function getLineClass(line: string) {
  if (line.includes('ERROR') || line.includes('失败')) return 'log-error'
  if (line.includes('WARN') || line.includes('⚠️')) return 'log-warn'
  if (line.includes('✅')) return 'log-success'
  return 'log-info'
}

async function loadLogs() {
  const logDir = `${Deno.build.os === 'windows' ? 'C:' : ''}/Users/${require('os').userInfo().username()}/.openclaw/workspace/skills/ai-news-v10/scripts/output/logs`
  // 注：此为演示，实际前端通过 /api/logs/{date} 获取
  // 这里直接请求 FastAPI 接口
  try {
    const resp = await fetch(`/api/logs/${props.date}`)
    const data = await resp.json()
    logLines.value = data.logs || []
  } catch (e) {
    logLines.value = ['日志加载失败']
  }
}

onMounted(loadLogs)
</script>

<style scoped>
.log-container {
  background: #0a0a14;
  padding: 12px;
  border-radius: 4px;
  max-height: 500px;
  overflow-y: auto;
  font-family: 'JetBrains Mono', 'Fira Code', monospace;
  font-size: 12px;
}
.log-line {
  display: flex;
  gap: 12px;
  padding: 2px 0;
  line-height: 1.6;
}
.log-time { color: #555; flex-shrink: 0; }
.log-info .log-content { color: #aaa; }
.log-warn .log-content { color: #e6a23c; }
.log-error .log-content { color: #f56c6c; }
.log-success .log-content { color: #67c23a; }
.log-empty { color: #555; text-align: center; padding: 20px; }
.card-header { display: flex; justify-content: space-between; align-items: center; }
</style>
```

---

## 八、构建和部署

### 构建

```bash
cd ~/.openclaw/workspace/skills/ai-news-v10/scripts/frontend
pnpm build
# 输出到 dist/ 目录
```

### 启动服务

```bash
cd ~/.openclaw/workspace/skills/ai-news-v10/scripts
uvicorn monitor.api:app --reload --port 8000 --host 127.0.0.1
```

### 访问

```
http://localhost:8000
```
