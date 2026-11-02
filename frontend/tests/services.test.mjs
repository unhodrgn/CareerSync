import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import vm from 'node:vm'
import ts from 'typescript'

// Runs the TypeScript services without adding a test library to the project. One loader = one module cache, so
// modules loaded through it share their imports (e.g. errors.ts and httpClient.ts see the same ApiError).
function loader(globals = {}) {
  const cache = new Map()
  function load(filename) {
    if (cache.has(filename)) return cache.get(filename).exports
    const source = fs.readFileSync(filename, 'utf8').replaceAll('import.meta.env', 'testEnv')
    const { outputText } = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2023 } })
    const module = { exports: {} }
    cache.set(filename, module)
    const context = vm.createContext({ module, exports: module.exports, FormData, URLSearchParams, Event, testEnv: {}, ...globals,
      require: name => load(path.resolve(path.dirname(filename), `${name}.ts`)),
    })
    new vm.Script(outputText, { filename }).runInContext(context)
    return module.exports
  }
  return file => load(path.resolve(file))
}

/** sessionStorage and window.dispatchEvent stand-ins; `events` collects dispatched event types. */
function browser() {
  const values = new Map()
  const events = []
  return {
    events,
    sessionStorage: { getItem: key => values.get(key) ?? null, setItem: (key, value) => values.set(key, value), removeItem: key => values.delete(key) },
    window: { dispatchEvent: event => events.push(event.type) },
  }
}

const reply = (status, body) => ({ ok: status < 400, status, statusText: '', json: async () => body })

test('API: same-origin /api paths, Bearer token, no cookies, JSON body and multipart upload', async () => {
  const calls = []
  const env = browser()
  const fetch = async (url, options) => { calls.push({ url, ...options }); return reply(200, { items: [], total: 0, limit: 20, offset: 0 }) }
  const load = loader({ ...env, fetch })
  load('src/services/tokenStorage.ts').setToken('abc')
  const { api } = load('src/services/apiService.ts')
  await api.jobs({ q: '백엔드', category: 'data_ai', region: '경기', offset: 20 })
  assert.equal(calls[0].url, `/api/jobs?q=${encodeURIComponent('백엔드')}&category=data_ai&region=${encodeURIComponent('경기')}&offset=20`)
  assert.equal(calls[0].method, 'GET')
  assert.equal(calls[0].headers.Authorization, 'Bearer abc')
  assert.equal(calls[0].credentials, undefined)
  await api.login({ email: 'a@b.test', password: 'pw123456' })
  assert.equal(calls[1].url, '/api/auth/login')
  assert.equal(calls[1].body, '{"email":"a@b.test","password":"pw123456"}')
  assert.equal(calls[1].headers['Content-Type'], 'application/json')
  await load('src/services/httpClient.ts').request('POST', '/cv', new FormData())
  assert.ok(calls[2].body instanceof FormData)
  assert.equal(calls[2].headers['Content-Type'], undefined)
})

test('HTTP: the three backend error shapes become one ApiError and one Korean sentence', async () => {
  const cases = [
    // AppError {code, message}: a known code gets the UI's text
    [reply(409, { code: 'EMAIL_TAKEN', message: 'x' }), 'EMAIL_TAKEN', '이미 가입된 이메일입니다.'],
    // AppError with a code the UI does not know: the backend's own (Korean) message
    [reply(409, { code: 'NEW_CODE', message: '서버가 보낸 문장' }), 'NEW_CODE', '서버가 보낸 문장'],
    // HTTPException {detail: "..."}
    [reply(403, { detail: '기업 회원만 사용할 수 있습니다.' }), 'HTTP_403', '기업 회원만 사용할 수 있습니다.'],
    // 422 {detail: [...]}: the first issue, without Pydantic's "Value error, " prefix
    [reply(422, { detail: [{ type: 'value_error', loc: ['body'], msg: 'Value error, 회사명을 입력해야 합니다.' }] }), 'VALIDATION', '회사명을 입력해야 합니다.'],
    // No JSON body
    [reply(502, null), 'SERVER', '일시적인 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.'],
  ]
  for (const [response, code, text] of cases) {
    const load = loader({ ...browser(), fetch: async () => response })
    const { request } = load('src/services/httpClient.ts')
    const { errorText } = load('src/services/errors.ts')
    const error = await request('GET', '/x').then(() => null, e => e)
    assert.equal(error.code, code)
    assert.equal(error.status, response.status)
    assert.equal(errorText(error), text)
  }
})

test('HTTP: a 401 on an authenticated call clears the token and announces it; a guest 401 does not', async () => {
  const env = browser()
  const load = loader({ ...env, fetch: async () => reply(401, { detail: '인증이 필요합니다.' }) })
  load('src/services/tokenStorage.ts').setToken('old')
  const { request } = load('src/services/httpClient.ts')
  await assert.rejects(request('GET', '/users/me'), e => e.code === 'HTTP_401')
  assert.equal(env.sessionStorage.getItem('careersync.token'), null)
  assert.deepEqual(env.events, ['careersync:session-expired'])
  await assert.rejects(request('POST', '/auth/login', {}))
  assert.deepEqual(env.events, ['careersync:session-expired'])
})

test('jobView: labels, D-day and tags come from the backend fields; nothing is invented', () => {
  const { toJob, dDayLabel } = loader()('src/services/jobView.ts')
  const item = { id: 7, company_id: 3, company_name: '넥스트코드', title: '백엔드 개발자', employment_type: 'contract', min_experience_years: 3, location: '서울 강남구', deadline: null, status: 'published', expired: false, criteria_count: 4, published_at: null, category: 'dev', tags: ['Java', 'Spring'] }
  const job = toJob(item)
  assert.equal(job.company, '넥스트코드')
  assert.equal(job.logo, '넥')
  assert.equal(job.employment, '계약직')
  assert.equal(job.experience, '경력 3년 이상')
  assert.equal(toJob({ ...item, min_experience_years: null }).experience, '신입 가능')
  assert.equal(job.dDay, '상시 채용')
  assert.deepEqual([...job.tags], ['Java', 'Spring'])
  assert.equal('score' in job, false)
  const today = new Date(2026, 9, 26)
  assert.equal(dDayLabel('2026-10-26', false, today), 'D-day')
  assert.equal(dDayLabel('2026-10-29', false, today), 'D-3')
  assert.equal(dDayLabel('2026-10-25', false, today), '마감')
  assert.equal(dDayLabel('2026-12-01', true, today), '마감')
})

test('API: saved jobs use PUT/DELETE /api/jobs/{id}/save (204, no body) and GET /api/saved-jobs/mine', async () => {
  const calls = []
  const fetch = async (url, options) => { calls.push({ url, method: options.method }); return options.method === 'GET' ? reply(200, []) : { ok: true, status: 204, json: async () => { throw new Error('no body') } } }
  const load = loader({ ...browser(), fetch })
  load('src/services/tokenStorage.ts').setToken('t')
  const { api } = load('src/services/apiService.ts')
  assert.equal(await api.saveJob(5), undefined)
  assert.equal(await api.unsaveJob(5), undefined)
  assert.deepEqual([...await api.savedJobs()], [])
  assert.deepEqual(calls, [
    { url: '/api/jobs/5/save', method: 'PUT' },
    { url: '/api/jobs/5/save', method: 'DELETE' },
    { url: '/api/saved-jobs/mine', method: 'GET' },
  ])
})

test('API: CV upload is multipart `file`; confirm, review and apply use the backend paths and bodies', async () => {
  const calls = []
  const fetch = async (url, options) => { calls.push({ url, ...options }); return reply(200, {}) }
  const load = loader({ ...browser(), fetch })
  load('src/services/tokenStorage.ts').setToken('t')
  const { api } = load('src/services/apiService.ts')
  const pdf = new File(['%PDF-1.4'], 'cv.pdf', { type: 'application/pdf' })
  await api.myCv()
  await api.uploadCv(pdf)
  const profile = { skills: ['Java'], experiences: [], projects: [], education: [], certificates: [], summary: '' }
  await api.updateCv(12, { profile, confirm: true })
  await api.reviewCv(13)
  await api.apply(7)
  await api.myApplications()
  assert.deepEqual(calls.map(c => `${c.method} ${c.url}`), [
    'GET /api/cv/me', 'POST /api/cv', 'PUT /api/cv/12', 'POST /api/cv/13/review', 'POST /api/jobs/7/applications', 'GET /api/applications/mine',
  ])
  assert.ok(calls[1].body instanceof FormData)
  assert.equal(calls[1].body.get('file').name, 'cv.pdf')
  assert.equal(calls[1].headers['Content-Type'], undefined)
  assert.deepEqual(JSON.parse(calls[2].body), { profile, confirm: true })
  for (const i of [3, 4]) assert.equal(calls[i].body, undefined) // review and apply send no body
})

test('HTTP: the apply 409s become their Korean sentences', async () => {
  const cases = {
    CV_NOT_CONFIRMED: /이력서에서 내용을 확인하고 저장/,
    AI_CONSENT_REQUIRED: /AI 분석 동의/,
    ALREADY_APPLIED: /이미 지원한 공고/,
    JOB_EXPIRED: /마감된 공고/,
  }
  for (const [code, text] of Object.entries(cases)) {
    const load = loader({ ...browser(), fetch: async () => reply(409, { code, message: 'x' }) })
    const error = await load('src/services/apiService.ts').api.apply(1).then(() => null, e => e)
    assert.equal(error.code, code)
    assert.match(load('src/services/errors.ts').errorText(error), text)
  }
})

test('API: rename is PATCH /api/users/me with the name only; preferences use GET/PUT /api/preferences/me', async () => {
  const calls = []
  const fetch = async (url, options) => { calls.push({ url, ...options }); return reply(200, {}) }
  const load = loader({ ...browser(), fetch })
  load('src/services/tokenStorage.ts').setToken('t')
  const { api } = load('src/services/apiService.ts')
  await api.updateMe({ display_name: '김지원' })
  await api.myPreferences()
  await api.savePreferences({ locations: ['서울'], employment_types: ['full_time'], job_keywords: [], profile_public: true, experience_level: 'junior', skills: ['React'] })
  assert.deepEqual(calls.map(c => `${c.method} ${c.url}`), ['PATCH /api/users/me', 'GET /api/preferences/me', 'PUT /api/preferences/me'])
  assert.equal(calls[0].body, '{"display_name":"김지원"}')
  assert.deepEqual(JSON.parse(calls[2].body).skills, ['React'])
})

test('preferenceView: the form maps to the API lists; the talent opt-in is sent back as stored', () => {
  const { toPreferenceForm, toPreferenceIn } = loader()('src/services/preferenceView.ts')
  const empty = toPreferenceForm(null)
  assert.equal(empty.experienceLevel, '')
  assert.deepEqual([...empty.skills], [])
  const stored = { locations: ['서울'], employment_types: ['contract'], job_keywords: ['백엔드'], profile_public: true, profile_public_at: null, updated_at: null, experience_level: 'mid', skills: ['Java'] }
  const form = toPreferenceForm(stored)
  assert.equal(form.experienceLevel, 'mid')
  const body = toPreferenceIn({ ...form, locations: [' 서울 ', ''], experienceLevel: '', skills: ['React', ' '] }, stored)
  assert.deepEqual(JSON.parse(JSON.stringify(body)), {
    locations: ['서울'], employment_types: ['contract'], job_keywords: ['백엔드'], profile_public: true, experience_level: null, skills: ['React'],
  })
  assert.equal(toPreferenceIn(form, null).profile_public, false) // nothing stored yet: the opt-in stays off
})

test('HTTP: the name-lock codes become Korean sentences', async () => {
  for (const [code, text] of [['NAME_LOCKED', /이력서를 올린 뒤에는 이름을 바꿀 수 없습니다/], ['NAME_CHANGED', /다시 올려 주세요/]]) {
    const load = loader({ ...browser(), fetch: async () => reply(409, { code, message: 'x' }) })
    const error = await load('src/services/apiService.ts').api.updateMe({ display_name: 'x' }).then(() => null, e => e)
    assert.match(load('src/services/errors.ts').errorText(error), text)
  }
})

test('labels: every application status and masked kind has a Korean label', () => {
  const { applicationStatusLabel, maskedKindLabel } = loader()('src/data/labels.ts')
  assert.deepEqual(Object.keys(applicationStatusLabel).sort(), ['interview', 'on_hold', 'passed', 'rejected', 'reviewing', 'submitted'])
  assert.deepEqual(Object.keys(maskedKindLabel).sort(), ['address', 'birth', 'email', 'name', 'phone', 'rrn', 'url'])
})

test('jobView: a closed job reads as 마감 (saved jobs keep closed ones)', () => {
  const { toJob } = loader()('src/services/jobView.ts')
  const item = { id: 1, company_id: 1, company_name: 'A', title: 'x', employment_type: 'full_time', min_experience_years: null, location: '', deadline: null, status: 'closed', expired: false, criteria_count: 1, published_at: null, category: 'dev', tags: [] }
  assert.equal(toJob(item).dDay, '마감')
  assert.equal(toJob({ ...item, status: 'published' }).dDay, '상시 채용')
})

test('HTTP: an unreachable server is a NETWORK error with a Korean sentence', async () => {
  const load = loader({ ...browser(), fetch: async () => { throw new TypeError('fetch failed') } })
  const error = await load('src/services/httpClient.ts').request('GET', '/jobs').then(() => null, e => e)
  assert.equal(error.code, 'NETWORK')
  assert.equal(error.status, 0)
  assert.match(load('src/services/errors.ts').errorText(error), /서버에 연결할 수 없습니다/)
})

test('API: recommendations are GET /api/recommendations/jobs?limit=20; the job match is GET /api/jobs/{id}/match', async () => {
  const calls = []
  const fetch = async (url, options) => { calls.push({ url, ...options }); return reply(200, {}) }
  const load = loader({ ...browser(), fetch })
  load('src/services/tokenStorage.ts').setToken('t')
  const { api } = load('src/services/apiService.ts')
  await api.recommendations()
  await api.recommendations(5)
  await api.jobMatch(7)
  assert.deepEqual(calls.map(c => `${c.method} ${c.url}`), ['GET /api/recommendations/jobs?limit=20', 'GET /api/recommendations/jobs?limit=5', 'GET /api/jobs/7/match'])
  for (const call of calls) {
    assert.equal(call.body, undefined)
    assert.equal(call.headers.Authorization, 'Bearer t')
  }
})

test('HTTP: refused recommendations become Korean sentences with a next step to the CV or consent page', async () => {
  const cases = { CV_NOT_CONFIRMED: [/이력서에서 내용을 확인하고 저장/, 'resume'], AI_CONSENT_REQUIRED: [/AI 분석 동의/, 'consent'] }
  for (const [code, [text, page]] of Object.entries(cases)) {
    const load = loader({ ...browser(), fetch: async () => reply(409, { code, message: 'x' }) })
    const error = await load('src/services/apiService.ts').api.recommendations().then(() => null, e => e)
    assert.equal(error.code, code)
    assert.match(load('src/services/errors.ts').errorText(error), text)
    assert.equal(load('src/services/matchView.ts').RECOMMENDATION_NEXT[code].page, page)
  }
})

test('matchView: only seekers see a score, never on applied jobs; pending and none show no number', () => {
  const { detailMatchState, MATCH_DISCLAIMER } = loader()('src/services/matchView.ts')
  const match = (status, score = null) => ({ job_id: 1, match_score: score, match_level: score === null ? null : '적합', status, notice: 'AI' })
  assert.equal(detailMatchState(null, false, match('done', 70)), 'hidden') // guest
  assert.equal(detailMatchState('company', false, match('done', 70)), 'hidden')
  assert.equal(detailMatchState('seeker', true, match('done', 70)), 'hidden') // applied (D44)
  assert.equal(detailMatchState('seeker', false, null), 'hidden') // still loading or the call failed
  assert.equal(detailMatchState('seeker', false, match('done', 70)), 'done')
  assert.equal(detailMatchState('seeker', false, match('pending')), 'pending')
  assert.equal(detailMatchState('seeker', false, match('none')), 'none')
  assert.equal(detailMatchState('seeker', false, match('done')), 'none') // a done status without a number shows none
  assert.equal(MATCH_DISCLAIMER, '점수는 합격 가능성을 뜻하지 않습니다.') // D42
})

test('API: company jobs and criteria use the backend paths, methods and bodies', async () => {
  const calls = []
  const fetch = async (url, options) => { calls.push({ url, ...options }); return options.method === 'DELETE' ? { ok: true, status: 204, json: async () => { throw new Error('no body') } } : reply(200, {}) }
  const load = loader({ ...browser(), fetch })
  load('src/services/tokenStorage.ts').setToken('t')
  const { api } = load('src/services/apiService.ts')
  const job = { title: '백엔드', description: 'x', employment_type: 'full_time', min_experience_years: null, location: '', salary_note: '', deadline: null, category: 'dev', headcount: 3 }
  const items = [{ id: null, name: 'Java', description: '', category: 'skill', weight: 100 }]
  await api.myJobs()
  await api.createJob(job)
  await api.updateJob(4, { headcount: null })
  assert.equal(await api.deleteJob(4), undefined)
  await api.publishJob(5)
  await api.closeJob(5)
  await api.ownerCriteria(5)
  await api.saveCriteria(5, items)
  await api.checkCriterion('나이 30세 이하', '')
  assert.deepEqual(calls.map(c => `${c.method} ${c.url}`), [
    'GET /api/jobs/mine', 'POST /api/jobs', 'PATCH /api/jobs/4', 'DELETE /api/jobs/4', 'POST /api/jobs/5/publish', 'POST /api/jobs/5/close',
    'GET /api/jobs/5/criteria', 'PUT /api/jobs/5/criteria', 'POST /api/criteria/check',
  ])
  assert.deepEqual(JSON.parse(calls[1].body), job)
  assert.equal(calls[2].body, '{"headcount":null}')
  for (const i of [3, 4, 5, 6]) assert.equal(calls[i].body, undefined)
  assert.deepEqual(JSON.parse(calls[7].body), { items })
  assert.deepEqual(JSON.parse(calls[8].body), { name: '나이 30세 이하', description: '' })
})

test('jobForm: two text areas become one JD with headings and come back; numbers and empty fields map to the API', () => {
  const f = loader()('src/services/jobForm.ts')
  const form = { ...f.emptyJobForm, title: ' 백엔드 개발자 ', minExperience: '', headcount: '3', deadline: '', category: '', duties: 'API 개발', requirements: 'Java 필수\nKafka 우대' }
  const body = f.toJobCreate(form)
  assert.equal(body.description, '[주요 업무]\nAPI 개발\n\n[자격 요건 및 우대 사항]\nJava 필수\nKafka 우대')
  assert.deepEqual({ ...body, description: undefined }, { title: '백엔드 개발자', description: undefined, employment_type: 'full_time', min_experience_years: null, location: '', salary_note: '', deadline: null, category: null, headcount: 3 })
  assert.deepEqual({ ...f.splitDescription(body.description) }, { duties: 'API 개발', requirements: 'Java 필수\nKafka 우대' })
  assert.deepEqual({ ...f.splitDescription('[자격 요건 및 우대 사항]\nJava') }, { duties: '', requirements: 'Java' })
  assert.deepEqual({ ...f.splitDescription('직접 쓴 공고') }, { duties: '직접 쓴 공고', requirements: '' }) // text from elsewhere stays whole
  assert.equal(f.joinDescription('업무', ' '), '[주요 업무]\n업무')
  const back = f.toJobForm({ ...body, id: 1, min_experience_years: 2, headcount: null, deadline: '2026-12-31' })
  assert.equal(back.minExperience, '2')
  assert.equal(back.headcount, '')
  assert.equal(back.deadline, '2026-12-31')
  assert.equal(back.duties, 'API 개발')
  assert.equal(f.jobFormProblem({ ...form, headcount: '0' }), '모집 인원은 1~999명 사이의 정수로 입력해 주세요.')
  assert.equal(f.jobFormProblem({ ...form, headcount: '1000' }), '모집 인원은 1~999명 사이의 정수로 입력해 주세요.')
  assert.equal(f.jobFormProblem({ ...form, title: ' ' }), '채용 직무명을 입력해 주세요.')
  assert.equal(f.jobFormProblem(form), null)
  assert.deepEqual(['draft', 'published', 'closed'].map(status => f.jobStatusLabel({ status, expired: false })), ['작성 중', '게시 중', '마감'])
  assert.equal(f.jobStatusLabel({ status: 'published', expired: true }), '기간 만료')
})

test('jobForm: criteria rows are checked like the server (count, names, weights, total 100)', () => {
  const f = loader()('src/services/jobForm.ts')
  const row = (name, weight) => ({ key: name, id: null, name, description: '', category: 'skill', weight: String(weight) })
  assert.deepEqual(JSON.parse(JSON.stringify(f.criteriaProblems([row('Java', 60), row('Spring', 40)]))), { form: [], rows: {} })
  const bad = JSON.parse(JSON.stringify(f.criteriaProblems([row('Java', 60), row('java ', 30), row('', 5), row('DB', 0)])))
  assert.deepEqual(bad.rows, { 1: '같은 이름의 항목이 이미 있습니다.', 2: '항목 이름을 입력해 주세요.', 3: '가중치는 1~100 사이의 정수로 입력해 주세요.' })
  assert.deepEqual(bad.form, ['가중치 합계는 100이어야 합니다. (현재 95)'])
  assert.match(f.criteriaProblems([]).form[0], /1개 이상 10개 이하/)
  assert.deepEqual([...f.toCriteriaIn([{ ...row(' Java ', '100'), id: 7 }])].map(c => ({ ...c })), [{ id: 7, name: 'Java', description: '', category: 'skill', weight: 100 }])
})

test('jobForm: refused saves and publishes become Korean sentences that point to the row or the page to fix', async () => {
  const fail = async (status, body) => {
    const load = loader({ ...browser(), fetch: async () => reply(status, body) })
    const error = await load('src/services/apiService.ts').api.publishJob(1).then(() => null, e => e)
    return { error, f: load('src/services/jobForm.ts') }
  }
  let { error, f } = await fail(422, { code: 'FIELD_REQUIRED', message: '직무 분야를 선택해야 게시할 수 있습니다.', fields: ['category'] })
  assert.deepEqual({ ...f.publishIssue(error) }, { message: '직무 분야를 선택해야 게시할 수 있어요. 공고 수정에서 직무 분야를 골라 주세요.', fix: 'edit' });
  ({ error, f } = await fail(422, { code: 'JOB_INCOMPLETE', message: 'x', fields: ['description'] }))
  assert.equal(f.publishIssue(error).fix, 'edit');
  ({ error, f } = await fail(422, { code: 'CRITERIA_COUNT_INVALID', message: 'x', count: 0 }))
  assert.deepEqual({ ...f.publishIssue(error) }, { message: '평가 기준을 먼저 설정해야 게시할 수 있어요.', fix: 'criteria' });
  ({ error, f } = await fail(422, { code: 'WEIGHT_SUM_INVALID', message: '가중치 합계는 100이어야 합니다. (현재 90)', total: 90 }))
  assert.deepEqual({ ...f.publishIssue(error) }, { message: '평가 기준을 고쳐야 게시할 수 있어요. 가중치 합계는 100이어야 합니다. (현재 90)', fix: 'criteria' });
  ({ error, f } = await fail(409, { code: 'JOB_NOT_DRAFT', message: '작성 중인 공고만 게시할 수 있습니다.' }))
  assert.equal(f.publishIssue(error).fix, null);

  const hit = { index: 1, field: 'name', rule_id: 'age', category: 'age', matched: '30세 이하', reason: '나이 제한', law_ref: '고용정책 기본법 제7조' };
  ({ error, f } = await fail(422, { code: 'CRITERIA_BLOCKED', message: '사용할 수 없는 평가 기준이 포함되어 있습니다.', items: [hit] }))
  let issue = f.criteriaIssue(error)
  assert.deepEqual([...issue.form], ['사용할 수 없는 평가 기준이 포함되어 있습니다.'])
  assert.equal(issue.rows[1], '‘30세 이하’ — 나이 제한 (고용정책 기본법 제7조)');
  ({ error, f } = await fail(422, { code: 'CRITERIA_MAJOR_REQUIRED', message: 'x', items: [{ index: 0, name: '전공' }] }))
  assert.match(f.criteriaIssue(error).rows[0], /전공을 적어 주세요/);
  ({ error, f } = await fail(422, { detail: [{ type: 'string_too_long', loc: ['body', 'items', 2, 'name'], msg: 'String should have at most 50 characters' }] }))
  issue = f.criteriaIssue(error)
  assert.equal(issue.rows[2], 'String should have at most 50 characters')
})
