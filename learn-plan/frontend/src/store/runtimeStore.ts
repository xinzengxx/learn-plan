import { computed, reactive, ref } from 'vue'
import type {
  DemoQuestion,
  DifficultyLevel,
  DifficultySummary,
  DifficultySummaryBucket,
  FailedCaseSummary,
  ProblemPanelMode,
  QuestionProgress,
  RuntimeProgress,
  RuntimeQuestion,
  RuntimeQuestionsPayload,
  RuntimeTestCase,
  DisplayValue,
  RunCaseRecord,
  SubmitRecord,
  SubmitResult,
  TestCaseRecord,
} from '../types'

interface RuntimeState {
  questions: DemoQuestion[]
  rawQuestions: RuntimeQuestion[]
  progress: RuntimeProgress
  activeQuestionId: string
  panelMode: ProblemPanelMode
  sidebarCollapsed: boolean
  loading: boolean
  error: string
  title: string
  topic: string
}

const toastRecord = ref<SubmitRecord | null>(null)

const state = reactive<RuntimeState>({
  questions: [],
  rawQuestions: [],
  progress: { summary: { total: 0, attempted: 0, correct: 0 }, questions: {} },
  activeQuestionId: '',
  panelMode: 'description',
  sidebarCollapsed: false,
  loading: true,
  error: '',
  title: '',
  topic: '',
})

let loadStarted = false
let heartbeatTimer: number | undefined

function isDisplayValue(value: unknown): value is DisplayValue {
  return Boolean(value && typeof value === 'object' && 'kind' in value)
}

function stringifyValue(value: unknown): string {
  if (value === undefined || value === null) return ''
  if (typeof value === 'string') return value
  try {
    return JSON.stringify(value, null, 2)
  } catch {
    return String(value)
  }
}

function displayFallback(value: unknown): string {
  if (isDisplayValue(value)) return value.repr || ''
  return stringifyValue(value)
}

function formatTime(value?: string | null): string {
  if (!value) return new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
}

const DIFFICULTY_LEVELS: DifficultyLevel[] = ['basic', 'medium', 'upper_medium', 'hard']
const DIFFICULTY_LABELS: Record<DifficultyLevel, string> = {
  basic: '基础题',
  medium: '中等题',
  upper_medium: '中难题',
  hard: '难题',
}
const DIFFICULTY_SCORES: Record<DifficultyLevel, number> = {
  basic: 1,
  medium: 2,
  upper_medium: 3,
  hard: 4,
}

function normalizeDifficultyLevelValue(value: unknown): DifficultyLevel | undefined {
  const text = String(value || '').trim()
  const key = text.toLowerCase().replace(/[-\s]/g, '_')
  if (key === 'easy' || text === '基础' || text === '基础题') return 'basic'
  if (key === 'basic') return 'basic'
  if (key === 'medium' || text === '中等' || text === '中等题' || text === '进阶') return 'medium'
  if (key === 'upper_medium' || key === 'uppermedium' || text === '中难' || text === '中难题' || text === '中上') return 'upper_medium'
  if (key === 'hard' || text === '困难' || text === '难题' || text === '挑战') return 'hard'
  return undefined
}

function normalizeDifficultyLevel(question: RuntimeQuestion): DifficultyLevel {
  return normalizeDifficultyLevelValue(question.difficulty_level || question.difficulty) || 'basic'
}

function normalizeDifficultyLabel(question: RuntimeQuestion): string {
  const level = normalizeDifficultyLevel(question)
  const label = String(question.difficulty_label || '').trim()
  return label || DIFFICULTY_LABELS[level]
}

function normalizeDifficultyScore(question: RuntimeQuestion): number {
  const level = normalizeDifficultyLevel(question)
  const score = Number(question.difficulty_score)
  return Number.isFinite(score) ? score : DIFFICULTY_SCORES[level]
}

function normalizeConstraints(value: RuntimeQuestion['constraints']): string[] {
  if (Array.isArray(value)) return value.map((item) => String(item))
  if (typeof value === 'string' && value.trim()) return value.split('\n').map((item) => item.trim()).filter(Boolean)
  return []
}

function caseInput(testCase: RuntimeTestCase | FailedCaseSummary): unknown {
  if ('input' in testCase && testCase.input !== undefined) return testCase.input
  if ('args' in testCase && testCase.args !== undefined) return testCase.args
  if ('kwargs' in testCase && testCase.kwargs !== undefined) return testCase.kwargs
  return ''
}

function mapPublicTest(testCase: RuntimeTestCase, index: number): TestCaseRecord {
  return {
    name: `公开测试 ${index + 1}`,
    input: stringifyValue(caseInput(testCase)),
    expected: stringifyValue(testCase.expected),
    actual: '等待运行',
    passed: false,
  }
}

function mapFailedCase(testCase: FailedCaseSummary, index: number): TestCaseRecord {
  const inputValue = caseInput(testCase)
  return {
    name: `${testCase.category === 'hidden' ? '隐藏' : '公开'}测试 ${testCase.case || index + 1}`,
    input: displayFallback(testCase.inputDisplay || inputValue),
    expected: displayFallback(testCase.expectedDisplay || testCase.expected_repr || testCase.expected),
    actual: displayFallback(testCase.actualDisplay || testCase.actual_repr),
    inputDisplay: testCase.inputDisplay,
    expectedDisplay: testCase.expectedDisplay,
    actualDisplay: testCase.actualDisplay,
    passed: false,
    error: testCase.error,
    stdout: stringifyValue(testCase.stdout),
    stderr: stringifyValue(testCase.stderr),
    traceback: stringifyValue(testCase.traceback),
  }
}

function buildPassedCases(result: SubmitResult): TestCaseRecord[] {
  const failedCount = result.failed_case_summaries?.length || 0
  const total = result.total_count ?? (result.ok || result.is_correct ? 1 : failedCount)
  const passed = Math.max(0, (result.passed_count ?? (result.ok || result.is_correct ? total : 0)) - failedCount)
  return Array.from({ length: passed }, (_, index) => ({
    name: `通过测试 ${index + 1}`,
    input: '',
    expected: '',
    actual: '',
    passed: true,
  }))
}

function mapRunCases(result: SubmitResult, publicTests?: RuntimeTestCase[]): RunCaseRecord[] {
  return (result.run_cases || []).map((item, index) => {
    const expected = item.expectedDisplay || item.expected_repr || item.expected || publicTests?.[index]?.expected
    const inputValue = item.inputDisplay || item.input || item.input_repr
    return {
      name: `运行样例 ${index + 1}`,
      input: displayFallback(inputValue),
      expected: expected !== undefined ? displayFallback(expected) : undefined,
      actual: displayFallback(item.actualDisplay || item.actual_repr || item.actual),
      inputDisplay: item.inputDisplay,
      expectedDisplay: item.expectedDisplay,
      actualDisplay: item.actualDisplay,
      passed: item.passed,
      error: item.error,
      stdout: stringifyValue(item.stdout),
      stderr: stringifyValue(item.stderr),
      traceback: stringifyValue(item.traceback),
    }
  })
}

function buildTerminalOutput(record: Pick<SubmitRecord, 'action' | 'message' | 'testCases' | 'runCases' | 'failure_types'>): string {
  if (record.runCases?.length) {
    const hasStructuredCases = record.runCases.some((testCase) => Boolean(testCase.inputDisplay || testCase.expectedDisplay || testCase.actualDisplay))
    if (hasStructuredCases) {
      return record.runCases.map((testCase) => [
        testCase.stdout ? `stdout：${testCase.stdout}` : '',
        testCase.stderr ? `stderr：${testCase.stderr}` : '',
        testCase.error ? `错误：${testCase.error}` : '',
        testCase.traceback ? `traceback：${testCase.traceback}` : '',
      ].filter(Boolean).join('\n')).filter(Boolean).join('\n\n')
    }
    return record.runCases.map((testCase) => [
      `测试输入：${testCase.input}`,
      testCase.expected ? `预期输出：${testCase.expected}` : '',
      `实际返回值：${testCase.actual || '(无返回值)'}`,
      testCase.stdout ? `stdout：${testCase.stdout}` : '',
      testCase.stderr ? `stderr：${testCase.stderr}` : '',
      testCase.error ? `错误：${testCase.error}` : '',
    ].filter(Boolean).join('\n')).join('\n\n')
  }
  const failed = record.testCases.filter((testCase) => !testCase.passed)
  if (failed.length) {
    return failed.map((testCase) => [
      `测试输入：${testCase.input}`,
      `期望输出：${testCase.expected}`,
      `实际输出：${testCase.actual || '(无输出)'}`,
      testCase.error ? `错误：${testCase.error}` : '',
    ].filter(Boolean).join('\n')).join('\n\n')
  }
  return record.action === 'run' ? '运行完成，但没有可展示的样例输出。' : '本次提交没有失败样例输出。'
}

function resultToRecord(questionId: string, action: SubmitRecord['action'], result: SubmitResult, publicTests?: RuntimeTestCase[]): SubmitRecord {
  const failed = (result.failed_case_summaries || []).map(mapFailedCase)
  const passed = buildPassedCases(result)
  const runCases = mapRunCases(result, publicTests)
  const ok = result.all_passed ?? result.is_correct ?? (runCases.length ? runCases.every((item) => item.passed !== false && !item.error) : result.ok ?? !result.error)
  const totalPublic = result.total_public_count ?? 0
  const totalHidden = result.total_hidden_count ?? 0
  const publicText = totalPublic ? `公开 ${result.passed_public_count || 0}/${totalPublic}` : ''
  const hiddenText = totalHidden ? `隐藏 ${result.passed_hidden_count || 0}/${totalHidden}` : ''
  const failureText = result.failure_types?.length ? `失败类型：${result.failure_types.join('、')}` : ''
  const detail = [publicText, hiddenText, failureText].filter(Boolean).join('，')
  const record: Omit<SubmitRecord, 'terminalOutput'> = {
    id: `${Date.now()}-${action}`,
    questionId,
    action,
    status: ok ? 'passed' : 'failed',
    message: result.error || (detail ? `${ok ? '通过' : '未通过'}：${detail}` : ok ? '运行完成。' : '答案未通过。'),
    createdAt: formatTime(result.submitted_at),
    testCases: [...passed, ...failed],
    runCases,
    failure_types: result.failure_types,
  }
  return {
    ...record,
    terminalOutput: buildTerminalOutput(record),
  }
}

function questionProgress(questionId: string): QuestionProgress {
  if (!state.progress.questions) state.progress.questions = {}
  if (!state.progress.questions[questionId]) state.progress.questions[questionId] = { stats: {}, history: [] }
  const progress = state.progress.questions[questionId]
  if (!progress.stats) progress.stats = {}
  if (!progress.history) progress.history = []
  if (!progress.stats.submit_history) progress.stats.submit_history = []
  return progress
}

function statusFromProgress(questionId: string, draft: string): DemoQuestion['status'] {
  const stats = state.progress.questions?.[questionId]?.stats
  if (stats?.last_status === 'skipped') return 'skipped'
  if (stats?.last_status === 'passed' || stats?.last_status === 'correct') return 'passed'
  if (stats?.last_status === 'failed' || stats?.last_status === 'incorrect') return 'failed'
  if (draft.trim()) return 'draft'
  return 'not_started'
}

function emptyDifficultyBucket(): DifficultySummaryBucket {
  return { total: 0, attempted: 0, correct: 0 }
}

function emptyDifficultySummary(): DifficultySummary {
  return {
    by_level: Object.fromEntries(DIFFICULTY_LEVELS.map((level) => [level, emptyDifficultyBucket()])),
    by_category: {},
  }
}

function buildDifficultySummary(): DifficultySummary {
  const summary = emptyDifficultySummary()
  for (const question of state.rawQuestions) {
    const level = normalizeDifficultyLevel(question)
    const category = String(question.category || 'unknown')
    if (!summary.by_category[category]) {
      summary.by_category[category] = Object.fromEntries(DIFFICULTY_LEVELS.map((item) => [item, emptyDifficultyBucket()]))
    }
    const progress = state.progress.questions?.[question.id]
    const stats = progress?.stats || {}
    const attempted = (stats.attempts || 0) > 0 || ['passed', 'correct', 'failed', 'incorrect', 'skipped'].includes(String(stats.last_status || ''))
    const correct = stats.last_status === 'passed' || stats.last_status === 'correct'
    summary.by_level[level].total += 1
    summary.by_level[level].attempted += attempted ? 1 : 0
    summary.by_level[level].correct += correct ? 1 : 0
    summary.by_category[category][level].total += 1
    summary.by_category[category][level].attempted += attempted ? 1 : 0
    summary.by_category[category][level].correct += correct ? 1 : 0
  }
  return summary
}

function syncQuestionDifficultySnapshot(question: RuntimeQuestion) {
  const progress = questionProgress(question.id)
  progress.difficulty_level = normalizeDifficultyLevel(question)
  progress.difficulty_label = normalizeDifficultyLabel(question)
  progress.difficulty_score = normalizeDifficultyScore(question)
}

function mapQuestion(question: RuntimeQuestion, index: number): DemoQuestion {
  const progress = state.progress.questions?.[question.id]
  const selectedDraft = progress?.selected?.map((item) => question.options?.[item]).filter(Boolean).join('\n') || ''
  const draft = progress?.draft || selectedDraft || question.starter_code || question.starter_sql || ''
  const examples = (question.examples || []).map((example, exampleIndex) => ({
    title: `示例 ${exampleIndex + 1}`,
    inputCode: stringifyValue(example.input),
    outputCode: stringifyValue(example.output),
    explanation: example.explanation,
  }))
  syncQuestionDifficultySnapshot(question)
  return {
    id: question.id,
    order: index + 1,
    title: question.title || question.function_name || `题目 ${index + 1}`,
    type: question.type,
    difficulty: normalizeDifficultyLabel(question),
    difficultyLevel: normalizeDifficultyLevel(question),
    difficultyScore: normalizeDifficultyScore(question),
    status: statusFromProgress(question.id, draft),
    tags: question.capability_tags?.length ? question.capability_tags : [question.category || question.type],
    description: question.problem_statement || question.question || question.prompt || '',
    inputSpec: question.input_spec || question.function_signature,
    outputSpec: question.output_spec,
    constraints: normalizeConstraints(question.constraints),
    examples,
    exampleDisplays: question.example_displays || [],
    publicTests: (question.public_tests || []).map(mapPublicTest),
    functionName: question.function_name,
    functionSignature: question.function_signature,
    starterCode: question.starter_code || question.starter_sql,
    supportedRuntimes: question.supported_runtimes,
    defaultRuntime: question.default_runtime,
    datasetDescription: question.dataset_description,
    options: question.options,
    answerDraft: draft,
  }
}

function refreshQuestions() {
  state.questions = state.rawQuestions.map(mapQuestion)
  if (!state.activeQuestionId && state.questions[0]) state.activeQuestionId = state.questions[0].id
}

async function fetchJson<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(url, options)
  if (!response.ok) throw new Error(`${response.status} ${response.statusText}`)
  return response.json() as Promise<T>
}

async function load() {
  state.loading = true
  state.error = ''
  try {
    const [questionsPayload, progressPayload] = await Promise.all([
      fetchJson<RuntimeQuestionsPayload>('./questions.json'),
      fetchJson<RuntimeProgress>('./progress'),
    ])
    state.rawQuestions = questionsPayload.questions || []
    state.progress = progressPayload || { summary: {}, questions: {} }
    state.title = questionsPayload.title || ''
    state.topic = questionsPayload.topic || ''
    if (!state.progress.questions) state.progress.questions = {}
    refreshQuestions()
  } catch (error) {
    state.error = error instanceof Error ? error.message : String(error)
  } finally {
    state.loading = false
  }
}

async function persistProgress() {
  const questions = Object.values(state.progress.questions || {})
  const attempted = questions.filter((item) => (item.stats?.attempts || 0) > 0).length
  const correct = questions.filter((item) => item.stats?.last_status === 'passed' || item.stats?.last_status === 'correct').length
  state.progress.summary = {
    ...(state.progress.summary || {}),
    total: state.rawQuestions.length,
    attempted,
    correct,
  }
  for (const question of state.rawQuestions) syncQuestionDifficultySnapshot(question)
  state.progress.difficulty_summary = buildDifficultySummary()
  await fetchJson<{ ok: boolean }>('./progress', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(state.progress),
  })
}

const activeQuestion = computed(() => state.questions.find((question) => question.id === state.activeQuestionId) || state.questions[0])
const activeRawQuestion = computed(() => state.rawQuestions.find((question) => question.id === state.activeQuestionId) || state.rawQuestions[0])
const activeHistory = computed(() => (state.progress.questions?.[state.activeQuestionId]?.history || []).slice().reverse())
const latestRecord = computed(() => activeHistory.value[0])
const latestRecordsByQuestion = computed(() => {
  const records: Record<string, SubmitRecord> = {}
  for (const [questionId, progress] of Object.entries(state.progress.questions || {})) {
    const latest = progress.history?.[progress.history.length - 1]
    if (latest) records[questionId] = latest
  }
  return records
})

function selectQuestion(questionId: string) {
  state.activeQuestionId = questionId
  state.panelMode = 'description'
}

function toggleSidebar() {
  state.sidebarCollapsed = !state.sidebarCollapsed
}

function setPanelMode(mode: ProblemPanelMode) {
  state.panelMode = mode
}

function updateDraft(value: string) {
  const question = activeQuestion.value
  if (!question) return
  question.answerDraft = value
  const progress = questionProgress(question.id)
  progress.draft = value
  question.status = statusFromProgress(question.id, value)
}

function toggleChoice(value: string) {
  const question = activeQuestion.value
  if (!question || !question.options) return
  const selected = question.answerDraft.split('\n').filter(Boolean)
  const exists = selected.includes(value)
  const next = question.type === 'multiple_choice'
    ? exists ? selected.filter((item) => item !== value) : [...selected, value]
    : exists ? [] : [value]
  updateDraft(next.join('\n'))
  const progress = questionProgress(question.id)
  progress.selected = next.map((item) => question.options?.indexOf(item) ?? -1).filter((index) => index >= 0)
}

function toggleUnsure(index: number) {
  const question = activeQuestion.value
  if (!question) return
  const progress = questionProgress(question.id)
  if (!progress.unsure) progress.unsure = []
  const pos = progress.unsure.indexOf(index)
  if (pos >= 0) progress.unsure.splice(pos, 1)
  else progress.unsure.push(index)
  refreshQuestions()
}

function hasUnsure(): boolean {
  const question = activeQuestion.value
  if (!question) return false
  const progress = state.progress.questions?.[question.id]
  return (progress?.unsure?.length || 0) > 0
}

async function skipCurrentQuestion() {
  const question = activeQuestion.value
  if (!question) return
  const progress = questionProgress(question.id)
  const attemptCount = (progress.stats?.attempts || 0)
  const record: SubmitRecord = {
    id: `${Date.now()}-skip`,
    questionId: question.id,
    action: 'skip',
    status: 'skipped',
    message: `已跳过（尝试 ${attemptCount} 次后放弃）`,
    createdAt: new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }),
    testCases: [],
  }
  progress.stats = progress.stats || {}
  progress.stats.last_status = 'skipped'
  progress.stats.last_submitted_at = new Date().toISOString()
  progress.history = [...(progress.history || []), record]
  progress.draft = ''
  progress.selected = []
  progress.unsure = []
  refreshQuestions()
  await persistProgress()
  toastRecord.value = record
  // Navigate to next question
  const nextIndex = state.questions.findIndex(q => q.id === question.id) + 1
  if (nextIndex < state.questions.length) {
    state.activeQuestionId = state.questions[nextIndex].id
  }
  state.panelMode = 'status'
}

function selectedIndices(question: DemoQuestion): number[] {
  const selected = question.answerDraft.split('\n').filter(Boolean)
  return selected.map((item) => question.options?.indexOf(item) ?? -1).filter((index) => index >= 0)
}

function applyRecord(record: SubmitRecord, submitResult?: SubmitResult) {
  const progress = questionProgress(record.questionId)
  const stats = progress.stats || {}
  progress.stats = stats
  stats.attempts = (stats.attempts || 0) + 1
  stats.last_status = record.status
  stats.last_submitted_at = new Date().toISOString()
  if (record.status === 'passed') {
    stats.correct_count = (stats.correct_count || 0) + 1
    stats.pass_count = (stats.pass_count || 0) + 1
  }
  if (submitResult) {
    stats.last_submit_result = submitResult
    stats.submit_history = stats.submit_history || []
    stats.submit_history.push(submitResult)
  }
  progress.history = [...(progress.history || []), record]
  refreshQuestions()
  state.panelMode = 'status'
  if (record.action === 'submit') toastRecord.value = record
}

async function runCurrentQuestion() {
  const question = activeQuestion.value
  const rawQuestion = activeRawQuestion.value
  if (!question || !rawQuestion) return
  try {
    const result = question.type === 'code'
      ? await fetchJson<SubmitResult>('./run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          mode: 'function',
          question_id: question.id,
          code: question.answerDraft || question.starterCode || '',
          function_name: question.functionName,
        }),
      })
      : question.type === 'sql'
        ? await fetchJson<SubmitResult>('./run', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            mode: 'query',
            runtime: 'mysql',
            question_id: question.id,
            sql: question.answerDraft || question.starterCode || '',
          }),
        })
        : { ok: true, is_correct: selectedIndices(question).length > 0 }
    applyRecord(resultToRecord(question.id, 'run', result, rawQuestion.public_tests))
    await persistProgress()
  } catch (error) {
    applyRecord(resultToRecord(question.id, 'run', { ok: false, error: error instanceof Error ? error.message : String(error) }))
  }
}

async function submitCurrentQuestion() {
  const question = activeQuestion.value
  if (!question) return
  try {
    const payload = question.type === 'code'
      ? {
        mode: 'function',
        question_id: question.id,
        code: question.answerDraft || question.starterCode || '',
        function_name: question.functionName,
      }
      : question.type === 'sql'
        ? {
          mode: 'query',
          runtime: 'mysql',
          question_id: question.id,
          sql: question.answerDraft || question.starterCode || '',
          submitted_at: new Date().toISOString(),
        }
        : {
          mode: 'answer',
          question_id: question.id,
          selected: selectedIndices(question),
          unsure: (state.progress.questions?.[question.id]?.unsure) || [],
          submitted_at: new Date().toISOString(),
        }
    const submitResponse = await fetch('./submit', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
    if (!submitResponse.ok) throw new Error(`${submitResponse.status} ${submitResponse.statusText}`)
    const submitResult = await submitResponse.json() as SubmitResult
    const record = resultToRecord(question.id, 'submit', submitResult)
    applyRecord(record, submitResult)
    await persistProgress()
  } catch (error) {
    const submitResult = { ok: false, error: error instanceof Error ? error.message : String(error) }
    const record = resultToRecord(question.id, 'submit', submitResult)
    applyRecord(record, submitResult)
  }
}

async function finishSession() {
  return fetchJson('./finish', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(state.progress),
  })
}

function startHeartbeat() {
  if (heartbeatTimer !== undefined) return
  heartbeatTimer = window.setInterval(() => {
    fetch('./heartbeat', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ts: Date.now() }) }).catch(() => undefined)
  }, 15000)
}

export function useRuntimeStore() {
  if (!loadStarted) {
    loadStarted = true
    load()
    startHeartbeat()
  }
  return {
    state,
    activeQuestion,
    activeHistory,
    latestRecord,
    latestRecordsByQuestion,
    selectQuestion,
    toggleSidebar,
    setPanelMode,
    updateDraft,
    toggleChoice,
    toggleUnsure,
    hasUnsure,
    skipCurrentQuestion,
    runCurrentQuestion,
    submitCurrentQuestion,
    finishSession,
    toastRecord,
  }
}
