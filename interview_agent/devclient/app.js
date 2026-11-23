'use strict';
// Developer page for the voice interview (M5 S4). Not a service screen: it logs in as a synthetic seeker, shows the transcript consent, creates a
// session (or joins an existing one), takes the microphone-only token from POST /join, joins the room and shows the stored, masked transcript.
// It publishes the MICROPHONE only (the token allows nothing else), sends no data, and uses textContent for everything it renders.

const { Room, RoomEvent, ParticipantKind } = LivekitClient;

const READY_ATTRIBUTE = 'cs_ready'; // page -> agent: attached and able to hear the interviewer
const AGENT_JOIN_TIMEOUT_MS = 20000;
const POLL_MS = 2000;

const $ = (id) => document.getElementById(id);
const dom = {
  email: $('email'), password: $('password'), login: $('login'), startBox: $('start-box'), consentTitle: $('consent-title'),
  consentItems: $('consent-items'), agree: $('agree'), jobId: $('job-id'), sessionId: $('session-id'), start: $('start'), end: $('end'),
  feedback: $('feedback'), status: $('status'), error: $('error'), transcript: $('transcript'), metrics: $('metrics'),
  feedbackBox: $('feedback-box'), feedbackText: $('feedback-text'), remoteAudio: $('remote-audio'),
};
const state = { token: null, consentVersion: null, sessionId: null, room: null, poll: null, agentTimer: null, connectedAt: null, marks: {}, over: false };

function setStatus(text) { dom.status.textContent = text; }
function setError(text) { dom.error.hidden = !text; dom.error.textContent = text || ''; }
function describe(error) {
  const data = error.data || {};
  return [data.code || error.message, data.message].filter(Boolean).join(' - ');
}

async function api(path, { method = 'GET', body } = {}) {
  const headers = { Accept: 'application/json' };
  if (state.token) headers.Authorization = `Bearer ${state.token}`;
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  const response = await fetch(`/api${path}`, { method, headers, body: body === undefined ? undefined : JSON.stringify(body), cache: 'no-store' });
  const text = await response.text();
  let data = null;
  try { data = text ? JSON.parse(text) : null; } catch { data = null; }
  if (!response.ok) {
    const error = new Error(`HTTP ${response.status}`);
    error.data = data;
    throw error;
  }
  return data;
}

function showMetrics() {
  const m = state.marks;
  const seconds = (a, b) => (m[a] !== undefined && m[b] !== undefined ? ((m[b] - m[a]) / 1000).toFixed(2) + ' s' : '-');
  dom.metrics.textContent = [
    `joined the room -> the interviewer (agent) joined: ${seconds('connected', 'agentJoined')}`,
    `joined the room -> first interviewer audio track: ${seconds('connected', 'agentAudio')}`,
  ].join('\n');
}

async function login() {
  setError('');
  try {
    const token = await api('/auth/login', { method: 'POST', body: { email: dom.email.value.trim(), password: dom.password.value } });
    state.token = token.access_token;
    dom.password.value = '';
    const consent = await api('/interview-consent');
    state.consentVersion = consent.version;
    dom.consentTitle.textContent = `${consent.title} (${consent.version})`;
    dom.consentItems.replaceChildren(...consent.items.map((item) => Object.assign(document.createElement('li'), { textContent: item.text })));
    dom.startBox.hidden = false;
    setStatus('로그인했습니다. 동의 내용을 확인하세요.');
  } catch (error) {
    setError(describe(error));
  }
}

function renderTranscript(detail) {
  dom.transcript.replaceChildren(
    ...detail.turns.map((turn) => {
      const li = document.createElement('li');
      li.className = turn.role;
      li.textContent = `${turn.role === 'agent' ? '면접관' : '나'}: ${turn.text}`;
      return li;
    }),
  );
}

async function pollOnce() {
  if (!state.sessionId || state.over) return;
  try {
    const detail = await api(`/interview-sessions/${state.sessionId}`);
    renderTranscript(detail);
    setStatus(`세션 ${detail.id}: ${detail.status}${detail.end_reason ? ` (${detail.end_reason})` : ''}`);
    if (detail.status === 'completed' || detail.status === 'aborted') finish();
  } catch (error) {
    setError(describe(error));
    if (error.data && error.data.code === 'INTERVIEW_NOT_FOUND') finish();
  }
}

function finish() {
  state.over = true;
  clearInterval(state.poll);
  clearTimeout(state.agentTimer);
  if (state.room) state.room.disconnect();
  dom.end.disabled = true;
  dom.feedback.disabled = false;
  showMetrics();
}

function onParticipantConnected(participant) {
  if (participant.kind === ParticipantKind.AGENT || !participant.identity.startsWith('candidate-')) {
    state.marks.agentJoined = performance.now();
    clearTimeout(state.agentTimer);
    setError(''); // a late join (a pending dispatch delivered after the 20 s message) must not leave the red error up
    setStatus('면접관(AI)이 입장했습니다. 첫 질문을 기다리세요.');
    showMetrics();
  }
}

function onTrackSubscribed(track) {
  if (track.kind === 'audio') {
    state.marks.agentAudio = state.marks.agentAudio ?? performance.now();
    dom.remoteAudio.append(track.attach());
    showMetrics();
  }
}

async function connect(join) {
  const room = new Room();
  state.room = room;
  room.on(RoomEvent.TrackSubscribed, onTrackSubscribed);
  room.on(RoomEvent.ParticipantConnected, onParticipantConnected);
  room.on(RoomEvent.Disconnected, () => setStatus('방에서 나왔습니다.'));
  await room.connect(join.url, join.token);
  state.marks.connected = performance.now();
  room.remoteParticipants.forEach(onParticipantConnected);
  setStatus('방에 들어왔습니다. 면접관(AI)을 기다리는 중...');
  state.agentTimer = setTimeout(() => {
    if (state.marks.agentJoined === undefined) {
      setError('면접관이 20초 안에 입장하지 않았습니다. 에이전트가 꺼져 있었다면 켜질 때 이 방으로 입장하니 잠시 더 기다리세요. 켜져 있었다면 에이전트 이름과 LiveKit 프로젝트가 같은지, 이 방이 이미 있었는지(이미 있는 방에는 새로 배정되지 않습니다) 확인하세요.');
    }
  }, AGENT_JOIN_TIMEOUT_MS);
  await room.localParticipant.setMicrophoneEnabled(true); // the only track this page publishes
  await room.startAudio();
  await room.localParticipant.setAttributes({ [READY_ATTRIBUTE]: '1' });
}

async function start() {
  setError('');
  dom.start.disabled = true;
  try {
    let sessionId = Number(dom.sessionId.value) || null;
    if (!sessionId) {
      const created = await api(`/jobs/${Number(dom.jobId.value)}/interview-sessions`, {
        method: 'POST',
        body: { consent_transcript: true, consent_version: state.consentVersion },
      });
      sessionId = created.session.id;
    }
    state.sessionId = sessionId;
    state.over = false;
    state.marks = {};
    const join = await api(`/interview-sessions/${sessionId}/join`, { method: 'POST' });
    await connect(join);
    dom.end.disabled = false;
    state.poll = setInterval(pollOnce, POLL_MS);
  } catch (error) {
    setError(describe(error));
    dom.start.disabled = !dom.agree.checked;
  }
}

async function end() {
  dom.end.disabled = true;
  try {
    await api(`/interview-sessions/${state.sessionId}/end`, { method: 'POST' });
  } catch (error) {
    setError(describe(error));
  }
  finish();
  pollOnce();
}

async function showFeedback() {
  setError('');
  try {
    const result = await api(`/interview-sessions/${state.sessionId}/feedback`, { method: 'POST' });
    dom.feedbackText.textContent = JSON.stringify(result.report, null, 2);
    dom.feedbackBox.hidden = false;
  } catch (error) {
    setError(describe(error));
  }
}

dom.login.addEventListener('click', login);
dom.agree.addEventListener('change', () => { dom.start.disabled = !dom.agree.checked || state.room !== null && !state.over; });
dom.start.addEventListener('click', start);
dom.end.addEventListener('click', end);
dom.feedback.addEventListener('click', showFeedback);
window.addEventListener('beforeunload', () => { if (state.room) state.room.disconnect(); });
