<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import type { DemoQuestion } from '../types'

declare global {
  interface Window {
    require?: {
      config: (options: unknown) => void
      (dependencies: string[], onLoad: () => void, onError?: (error: unknown) => void): void
    }
    monaco?: MonacoApi
    MonacoEnvironment?: Record<string, unknown>
  }
}

interface MonacoEditorInstance {
  getValue: () => string
  setValue: (value: string) => void
  layout: () => void
  dispose: () => void
  onDidChangeModelContent: (listener: () => void) => { dispose: () => void }
  updateOptions: (options: Record<string, unknown>) => void
}

interface MonacoApi {
  editor: {
    create: (container: HTMLElement, options: Record<string, unknown>) => MonacoEditorInstance
    defineTheme: (themeName: string, themeData: Record<string, unknown>) => void
    setTheme: (theme: string) => void
  }
}

const props = defineProps<{
  question: DemoQuestion
  themeMode: 'paper' | 'ink'
  unsureIndices: number[]
  hasAttempts: boolean
}>()

const emit = defineEmits<{
  updateDraft: [value: string]
  toggleChoice: [value: string]
  toggleTheme: []
  run: []
  submit: []
  toggleUnsure: [index: number]
  skip: []
}>()

const monacoContainer = ref<HTMLElement | null>(null)
const monacoAvailable = ref(false)
const monacoFailed = ref(false)
let monacoLoadPromise: Promise<MonacoApi> | null = null
let monacoEditor: MonacoEditorInstance | null = null
let monacoChangeSubscription: { dispose: () => void } | null = null

const codeValue = computed(() => props.question.answerDraft || props.question.starterCode || '')
const editorLanguage = computed(() => props.question.type === 'sql' ? 'sql' : 'python')
const languageLabel = computed(() => props.question.type === 'sql' ? 'MySQL' : 'Python')
const lineNumbers = computed(() => {
  const count = Math.max(1, codeValue.value.split('\n').length)
  return Array.from({ length: count }, (_, index) => index + 1)
})
const selectedOptions = computed(() => props.question.answerDraft.split('\n').filter(Boolean))

function optionSelected(option: string) {
  return selectedOptions.value.includes(option)
}

function optionIsUnsure(index: number) {
  return props.unsureIndices.includes(index)
}

function handleChoiceDblClick(index: number) {
  emit('toggleUnsure', index)
}

const completionPairs: Record<string, string> = {
  '(': ')',
  '[': ']',
  '{': '}',
  '"': '"',
  "'": "'",
}

function insertTextAtCursor(textarea: HTMLTextAreaElement, text: string, cursorOffset = text.length) {
  const start = textarea.selectionStart
  const end = textarea.selectionEnd
  const nextValue = `${textarea.value.slice(0, start)}${text}${textarea.value.slice(end)}`
  textarea.value = nextValue
  emit('updateDraft', nextValue)
  requestAnimationFrame(() => {
    const cursor = start + cursorOffset
    textarea.setSelectionRange(cursor, cursor)
  })
}

function handleCodeKeydown(event: KeyboardEvent) {
  const textarea = event.target as HTMLTextAreaElement
  if (event.key === 'Tab') {
    event.preventDefault()
    insertTextAtCursor(textarea, '    ')
    return
  }
  if (event.key === 'Enter') {
    const lineStart = textarea.value.lastIndexOf('\n', textarea.selectionStart - 1) + 1
    const currentLine = textarea.value.slice(lineStart, textarea.selectionStart)
    const indent = currentLine.match(/^\s*/)?.[0] || ''
    const extraIndent = currentLine.trimEnd().endsWith(':') ? '    ' : ''
    event.preventDefault()
    insertTextAtCursor(textarea, `\n${indent}${extraIndent}`)
    return
  }
  const pair = completionPairs[event.key]
  if (pair) {
    event.preventDefault()
    const selectedText = textarea.value.slice(textarea.selectionStart, textarea.selectionEnd)
    insertTextAtCursor(textarea, `${event.key}${selectedText}${pair}`, 1 + selectedText.length)
  }
}

function registerLearnMonacoThemes(monaco: MonacoApi) {
  monaco.editor.defineTheme('learn-paper', {
    base: 'vs',
    inherit: true,
    rules: [
      { token: 'keyword', foreground: '9b4f2f', fontStyle: 'bold' },
      { token: 'number', foreground: '8a5a2f' },
      { token: 'string', foreground: '6f7f3f' },
      { token: 'comment', foreground: '8d8278', fontStyle: 'italic' },
    ],
    colors: {
      'editor.background': '#fffaf0',
      'editor.foreground': '#2d2926',
      'editorLineNumber.foreground': '#9a8e82',
      'editorLineNumber.activeForeground': '#b26a3d',
      'editorCursor.foreground': '#b26a3d',
      'editor.selectionBackground': '#ead6c5',
      'editor.lineHighlightBackground': '#f5eadc',
      'editorIndentGuide.background': '#e4d8c8',
    },
  })
  monaco.editor.defineTheme('learn-ink', {
    base: 'vs-dark',
    inherit: true,
    rules: [
      { token: 'keyword', foreground: 'd7a27c', fontStyle: 'bold' },
      { token: 'number', foreground: 'e4ba91' },
      { token: 'string', foreground: 'b9c98f' },
      { token: 'comment', foreground: '8b8178', fontStyle: 'italic' },
    ],
    colors: {
      'editor.background': '#14110f',
      'editor.foreground': '#f2e8dc',
      'editorLineNumber.foreground': '#6e6258',
      'editorLineNumber.activeForeground': '#d7a27c',
      'editorCursor.foreground': '#d7a27c',
      'editor.selectionBackground': '#4b372c',
      'editor.lineHighlightBackground': '#211c18',
      'editorIndentGuide.background': '#342d27',
    },
  })
}

function ensureMonaco(): Promise<MonacoApi> {
  if (window.monaco?.editor) return Promise.resolve(window.monaco)
  if (monacoLoadPromise) return monacoLoadPromise
  monacoLoadPromise = new Promise((resolve, reject) => {
    function loadEditor() {
      if (!window.require) {
        reject(new Error('Monaco loader unavailable'))
        return
      }
      window.require.config({ paths: { vs: './node_modules/monaco-editor/min/vs' } })
      window.MonacoEnvironment = {
        getWorker() {
          return new Worker(
            URL.createObjectURL(
              new Blob(['self.onmessage=function(){}'], { type: 'application/javascript' })
            )
          )
        },
      }
window.require(['vs/editor/editor.main'], () => {
        if (window.monaco) {
          registerLearnMonacoThemes(window.monaco)
          resolve(window.monaco)
        } else reject(new Error('Monaco editor unavailable'))
      }, reject)
    }
    if (window.require) {
      loadEditor()
      return
    }
    const script = document.createElement('script')
    script.src = './node_modules/monaco-editor/min/vs/loader.js'
    script.onload = loadEditor
    script.onerror = () => reject(new Error('Failed to load Monaco loader'))
    document.head.appendChild(script)
  })
  return monacoLoadPromise
}

function disposeMonaco() {
  monacoChangeSubscription?.dispose()
  monacoChangeSubscription = null
  monacoEditor?.dispose()
  monacoEditor = null
}

async function mountMonaco() {
  if (!['code', 'sql'].includes(props.question.type) || !monacoContainer.value) return
  try {
    const monaco = await ensureMonaco()
    if (!monacoContainer.value) return
    disposeMonaco()
    monacoEditor = monaco.editor.create(monacoContainer.value, {
      value: codeValue.value,
      language: editorLanguage.value,
      theme: props.themeMode === 'paper' ? 'learn-paper' : 'learn-ink',
      automaticLayout: true,
      tabSize: 4,
      insertSpaces: true,
      detectIndentation: false,
      minimap: { enabled: false },
      fontFamily: 'JetBrainsMono Nerd Font Mono, JetBrainsMono Nerd Font, JetBrains Mono, monospace',
      fontSize: 14,
      lineHeight: 24,
      scrollBeyondLastLine: false,
      wordWrap: 'off',
      bracketPairColorization: { enabled: true },
      autoClosingBrackets: 'always',
      autoClosingQuotes: 'always',
    })
    monacoChangeSubscription = monacoEditor.onDidChangeModelContent(() => {
      emit('updateDraft', monacoEditor?.getValue() || '')
    })
    monacoAvailable.value = true
    monacoFailed.value = false
  } catch {
    monacoFailed.value = true
    monacoAvailable.value = false
  }
}

watch(() => props.question.id, async () => {
  disposeMonaco()
  monacoAvailable.value = false
  monacoFailed.value = false
  await nextTick()
  mountMonaco()
}, { immediate: true })

watch(codeValue, (value) => {
  if (monacoEditor && monacoEditor.getValue() !== value) monacoEditor.setValue(value)
})

watch(() => props.themeMode, (themeMode) => {
  if (window.monaco?.editor) window.monaco.editor.setTheme(themeMode === 'paper' ? 'learn-paper' : 'learn-ink')
  monacoEditor?.layout()
})

onBeforeUnmount(disposeMonaco)
</script>

<template>
  <section class="workspace-card">
    <div class="workspace-header">
      <h2>作答</h2>
      <div class="workspace-header-actions">
        <button class="theme-toggle" type="button" :aria-label="props.themeMode === 'paper' ? '深色模式' : '浅色模式'" @click="emit('toggleTheme')">
          <svg v-if="props.themeMode === 'paper'" viewBox="0 0 24 24" aria-hidden="true">
            <title>深色模式</title>
            <path d="M20.4 14.7A8.2 8.2 0 0 1 9.3 3.6a8.4 8.4 0 1 0 11.1 11.1Z" />
          </svg>
          <svg v-else viewBox="0 0 48 48" aria-hidden="true" class="sun-icon">
            <title>浅色模式</title>
            <circle class="sun-orbit" cx="24" cy="24" r="19" />
            <circle class="sun-core" cx="24" cy="24" r="4.5" />
            <path class="sun-ray" d="M24 12v4M24 32v4M12 24h4M32 24h4M15.5 15.5l2.8 2.8M29.7 29.7l2.8 2.8M15.5 32.5l2.8-2.8M29.7 18.3l2.8-2.8" />
          </svg>
        </button>
      </div>
    </div>

    <div v-if="['code', 'sql'].includes(props.question.type)" class="code-editor-shell">
      <div class="editor-toolbar">
        <span>{{ languageLabel }}</span>
        <code>{{ props.question.functionSignature || props.question.functionName || props.question.inputSpec?.match(/`([^`]+)`/)?.[1] || '函数签名见题面' }}</code>
      </div>
      <div class="code-editor-frame monaco-editor-frame">
        <div ref="monacoContainer" class="editor-monaco" :class="{ ready: monacoAvailable }" />
        <textarea
          v-if="monacoFailed"
          class="answer-editor code monaco-fallback"
          :value="codeValue"
          spellcheck="false"
          @keydown="handleCodeKeydown"
          @input="emit('updateDraft', ($event.target as HTMLTextAreaElement).value)"
        />
      </div>
    </div>

    <div v-else class="choice-panel">
      <p class="choice-hint">
        {{ props.question.type === 'multiple_choice'
          ? `已选择 ${selectedOptions.length} 项${props.unsureIndices.length ? `，${props.unsureIndices.length} 项不确定` : ''}`
          : selectedOptions[0]
            ? `已选择 1 项${props.unsureIndices.length ? '，有选项标记为不确定' : ''}`
            : '请选择答案' }}
      </p>
      <button
        v-for="(option, idx) in props.question.options"
        :key="option"
        type="button"
        class="choice-card"
        :class="{
          selected: optionSelected(option),
          unsure: optionIsUnsure(idx),
        }"
        :title="optionIsUnsure(idx) ? '双击取消不确定' : '双击标记为不确定'"
        @click="emit('toggleChoice', option)"
        @dblclick="handleChoiceDblClick(idx)"
      >
        <span class="choice-marker">
          <template v-if="optionIsUnsure(idx)">?</template>
          <template v-else>{{ optionSelected(option) ? '✓' : '' }}</template>
        </span>
        <span class="choice-label">{{ option }}</span>
      </button>
    </div>

    <div class="workspace-actions">
      <button class="secondary-button" type="button" @click="emit('run')">运行</button>
      <button class="primary-button" type="button" @click="emit('submit')">
        {{ props.unsureIndices.length ? '提交（含不确定项）' : '提交' }}
      </button>
      <button v-if="props.hasAttempts" class="skip-button" type="button" @click="emit('skip')">跳过此题</button>
    </div>
  </section>
</template>
