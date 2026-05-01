export type QuestionType = 'code' | 'sql' | 'single_choice' | 'multiple_choice' | 'true_false'
export type RuntimeName = 'python' | 'mysql'
export type QuestionStatus = 'not_started' | 'draft' | 'passed' | 'failed' | 'skipped'
export type ProblemPanelMode = 'description' | 'history' | 'status'
export type DifficultyLevel = 'basic' | 'medium' | 'upper_medium' | 'hard'

export interface DifficultySummaryBucket {
  total: number
  attempted: number
  correct: number
}

export interface DifficultySummary {
  by_level: Record<string, DifficultySummaryBucket>
  by_category: Record<string, Record<string, DifficultySummaryBucket>>
}

export interface RuntimeTestCase {
  input?: unknown
  args?: unknown[]
  kwargs?: Record<string, unknown>
  expected?: unknown
  category?: 'public' | 'hidden'
  note?: string
}

export interface DatasetColumnDescription {
  name: string
  type: string
  nullable?: boolean
  description?: string
}

export interface DatasetPublicPreview {
  columns: string[]
  rows: unknown[][]
  row_limit?: number
  truncated?: boolean
}

export interface DatasetTableDescription {
  name: string
  display_name?: string
  kind?: string
  columns: DatasetColumnDescription[]
  preview?: DatasetPublicPreview
}

export interface DatasetRelationshipDescription {
  kind?: string
  description?: string
  left_table: string
  left_key: string
  right_table: string
  right_key: string
}

export interface DatasetDescription {
  relationships?: DatasetRelationshipDescription[]
  tables: DatasetTableDescription[]
}

export type DisplayValue =
  | { kind: 'dataframe' | 'sql_result'; columns?: string[]; rows?: unknown[]; row_count?: number; truncated?: boolean; repr?: string }
  | { kind: 'series'; name?: string; values?: unknown[]; shape?: unknown[]; dtype?: string; truncated?: boolean; repr?: string }
  | { kind: 'ndarray' | 'tensor'; shape?: unknown[]; dtype?: string; device?: string; values?: unknown; repr?: string }
  | { kind: 'json'; value?: unknown; repr?: string }
  | { kind: 'scalar'; value?: unknown; repr?: string }
  | { kind: 'repr'; repr?: string }
  | { kind: 'error'; message?: string; repr?: string }

export interface RuntimeExample {
  input?: unknown
  output?: unknown
  explanation?: string
}

export interface RuntimeExampleParameter {
  name: string
  valueDisplay?: DisplayValue
}

export interface RuntimeExampleDisplay {
  title: string
  input_kind: 'parameters' | 'tables'
  input_parameters?: RuntimeExampleParameter[]
  input_tables?: DatasetTableDescription[]
  outputDisplay?: DisplayValue
  explanation?: string
}

export interface RuntimeQuestion {
  id: string
  type: QuestionType
  category?: string
  title?: string
  prompt?: string
  question?: string
  problem_statement?: string
  input_spec?: string
  output_spec?: string
  constraints?: string[] | string
  examples?: RuntimeExample[]
  public_tests?: RuntimeTestCase[]
  example_displays?: RuntimeExampleDisplay[]
  function_name?: string
  function_signature?: string
  starter_code?: string
  starter_sql?: string
  supported_runtimes?: RuntimeName[]
  default_runtime?: RuntimeName
  dataset_description?: DatasetDescription
  options?: string[]
  capability_tags?: string[]
  difficulty?: string
  difficulty_level?: DifficultyLevel | string
  difficulty_label?: string
  difficulty_score?: number
  difficulty_reason?: string
  expected_failure_mode?: string
}

export interface RuntimeQuestionsPayload {
  title?: string
  topic?: string
  questions: RuntimeQuestion[]
}

export interface FailedCaseSummary {
  case?: number
  category?: string
  passed?: boolean
  input?: unknown
  expected?: unknown
  expected_repr?: string
  actual_repr?: string
  expectedDisplay?: DisplayValue
  inputDisplay?: DisplayValue
  actualDisplay?: DisplayValue
  stdout?: string
  stderr?: string
  traceback?: string
  error?: string
  capability_tags?: string[]
}

export interface RunCaseResult {
  input?: unknown
  input_repr?: string
  expected?: unknown
  expected_repr?: string
  actual?: unknown
  actual_repr?: string
  inputDisplay?: DisplayValue
  expectedDisplay?: DisplayValue
  actualDisplay?: DisplayValue
  passed?: boolean
  stdout?: string
  stderr?: string
  traceback?: string
  error?: string
}

export interface SubmitResult {
  ok?: boolean
  all_passed?: boolean
  is_correct?: boolean
  passed_count?: number
  total_count?: number
  passed_public_count?: number
  total_public_count?: number
  passed_hidden_count?: number
  total_hidden_count?: number
  failed_case_summaries?: FailedCaseSummary[]
  run_cases?: RunCaseResult[]
  failure_types?: string[]
  submitted_at?: string
  error?: string
}

export interface QuestionProgressStats {
  attempts?: number
  correct_count?: number
  pass_count?: number
  last_status?: string | null
  last_submitted_at?: string | null
  last_submit_result?: SubmitResult
  submit_history?: SubmitResult[]
}

export interface QuestionProgress {
  difficulty_level?: DifficultyLevel | string
  difficulty_label?: string
  difficulty_score?: number
  stats?: QuestionProgressStats
  history?: SubmitRecord[]
  draft?: string
  selected?: number[]
  unsure?: number[]
}

export interface RuntimeProgress {
  summary?: {
    total?: number
    attempted?: number
    correct?: number
  }
  session?: Record<string, unknown>
  questions?: Record<string, QuestionProgress>
  difficulty_summary?: DifficultySummary
  [key: string]: unknown
}

export interface TestCaseRecord {
  name: string
  input: string
  expected: string
  actual: string
  passed: boolean
  inputDisplay?: DisplayValue
  expectedDisplay?: DisplayValue
  actualDisplay?: DisplayValue
  stdout?: string
  stderr?: string
  traceback?: string
  note?: string
  error?: string
}

export interface RunCaseRecord {
  name: string
  input: string
  expected?: string
  actual: string
  passed?: boolean
  inputDisplay?: DisplayValue
  expectedDisplay?: DisplayValue
  actualDisplay?: DisplayValue
  stdout?: string
  stderr?: string
  traceback?: string
  error?: string
}

export interface DemoExample {
  title: string
  inputCode: string
  outputCode: string
  explanation?: string
}

export interface DemoQuestion {
  id: string
  order: number
  title: string
  type: QuestionType
  difficulty: string
  difficultyLevel: DifficultyLevel | string
  difficultyScore?: number
  status: QuestionStatus
  tags: string[]
  description: string
  inputSpec?: string
  outputSpec?: string
  constraints?: string[]
  examples?: DemoExample[]
  exampleDisplays?: RuntimeExampleDisplay[]
  publicTests?: TestCaseRecord[]
  functionName?: string
  functionSignature?: string
  starterCode?: string
  supportedRuntimes?: RuntimeName[]
  defaultRuntime?: RuntimeName
  datasetDescription?: DatasetDescription
  options?: string[]
  answerDraft: string
}

export interface SubmitRecord {
  id: string
  questionId: string
  action: 'run' | 'submit' | 'skip'
  status: 'passed' | 'failed' | 'skipped'
  message: string
  createdAt: string
  testCases: TestCaseRecord[]
  runCases?: RunCaseRecord[]
  terminalOutput?: string
  failure_types?: string[]
  unsure?: number[]
}
