'use strict';
// Developer page for the voice + Anam avatar interview (M5 S4, D90). Not a service screen: it logs in as a synthetic seeker,
// shows the transcript consent, creates a session (or joins an existing one), takes the microphone-only token from POST /join,
// opens a local-only muted camera preview, restricts mic subscribers to the interviewer agent, joins the room and shows masked text.
// It publishes the MICROPHONE only (the token allows nothing else), sends no data, and uses textContent for everything it renders.

const { Room, RoomEvent, ParticipantKind } = LivekitClient;

const READY_ATTRIBUTE = 'cs_ready'; // page -> agent: attached and able to hear the interviewer
const AVATAR_IDENTITY = 'anam-avatar-agent';
const PUBLISH_ON_BEHALF = 'lk.publish_on_behalf';
const OPEN_SUBSCRIBERS = new URLSearchParams(window.location.search).get('open') === '1';
const AGENT_JOIN_TIMEOUT_MS = 20000;
const POLL_MS = 2000;

const $ = (id) => document.getElementById(id);
const dom = {
  email: $('email'), password: $('password'), login: $('login'), startBox: $('start-box'), consentTitle: $('consent-title'),
  consentItems: $('consent-items'), agree: $('agree'), jobId: $('job-id'), depth: $('depth'), sessionId: $('session-id'), start: $('start'), end: $('end'),
  feedback: $('feedback'), status: $('status'), error: $('error'), transcript: $('transcript'), metrics: $('metrics'),
  feedbackBox: $('feedback-box'), feedbackText: $('feedback-text'), remoteAudio: $('remote-audio'),
  avatarVideo: $('avatar-video'), avatarPlaceholder: $('avatar-placeholder'), previewVideo: $('preview-video'),
};
const state = {
  token: null, consentVersion: null, sessionId: null, room: null, previewStream: null,
  poll: null, agentTimer: null, allowedAgents: new Set(), marks: {}, over: false,
};

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
    `joined the room -> first avatar video track: ${seconds('connected', 'agentVideo')}`,
  ].join('\n');
}

function isAvatarWorker(participant) {
  return participant.identity === AVATAR_IDENTITY || Boolean(participant.attributes && participant.attributes[PUBLISH_ON_BEHALF]);
}

function restrictMicrophoneSubscribers(room) {
  if (OPEN_SUBSCRIBERS) return;
  room.localParticipant.setTrackSubscriptionPermissions(false, []);
}

function allowAgent(room, participant) {
  if (OPEN_SUBSCRIBERS) return;
  if (participant.kind !== ParticipantKind.AGENT || isAvatarWorker(participant)) return;
  state.allowedAgents.add(participant.identity);
  room.localParticipant.setTrackSubscriptionPermissions(
    false,
    [...state.allowedAgents].map((participantIdentity) => ({ participantIdentity, allowAll: true })),
  );
}

async function openPreview() {
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) return;
  let stream = null;
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: true, video: true });
  } catch {
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      dom.avatarPlaceholder.textContent = '카메라를 사용할 수 없어 미리보기 없이 진행합니다. (음성·아바타 수신은 계속됩니다.)';
    } catch {
      return; // LiveKit setMicrophoneEnabled will surface a missing microphone cleanly
    }
  }
  stream.getAudioTracks().forEach((track) => track.stop()); // only local video is kept; LiveKit opens its own mic track
  const video = stream.getVideoTracks();
  if (video.length) {
    state.previewStream = new MediaStream(video);
    dom.previewVideo.srcObject = state.previewStream; // local only: never published or uploaded
  }
}

function stopPreview() {
  if (state.previewStream) {
    state.previewStream.getTracks().forEach((track) => track.stop());
    state.previewStream = null;
  }
  dom.previewVideo.srcObject = null;
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
  stopPreview();
  state.allowedAgents.clear();
  dom.avatarPlaceholder.hidden = false;
  dom.end.disabled = true;
  dom.feedback.disabled = false;
  showMetrics();
}

function onParticipantConnected(participant) {
  if (state.room) allowAgent(state.room, participant);
  if (isAvatarWorker(participant)) {
    setStatus('아바타가 입장했습니다. 음성·영상을 준비하는 중...');
    return;
  }
  if (participant.kind === ParticipantKind.AGENT || !participant.identity.startsWith('candidate-')) {
    state.marks.agentJoined = state.marks.agentJoined ?? performance.now();
    clearTimeout(state.agentTimer);
    setError(''); // a late join (a pending dispatch delivered after the 20 s message) must not leave the red error up
    setStatus('면접관(AI)이 입장했습니다. 첫 질문을 기다리세요.');
    showMetrics();
  }
}

function onTrackSubscribed(track, _publication, participant) {
  if (participant.kind !== ParticipantKind.AGENT) return;
  if (track.kind === 'video') {
    state.marks.agentVideo = state.marks.agentVideo ?? performance.now();
    track.attach(dom.avatarVideo);
    dom.avatarPlaceholder.hidden = true;
    showMetrics();
  } else if (track.kind === 'audio') {
    state.marks.agentAudio = state.marks.agentAudio ?? performance.now();
    dom.remoteAudio.append(track.attach());
    showMetrics();
  }
}

function onTrackUnsubscribed(track) {
  if (track.kind === 'video') {
    track.detach(dom.avatarVideo);
    dom.avatarPlaceholder.textContent = '아바타 영상이 종료되었습니다. (음성 전용 모드)';
    dom.avatarPlaceholder.hidden = false;
  }
}

async function connect(join) {
  const room = new Room({ adaptiveStream: true });
  state.room = room;
  room.on(RoomEvent.TrackSubscribed, onTrackSubscribed);
  room.on(RoomEvent.TrackUnsubscribed, onTrackUnsubscribed);
  room.on(RoomEvent.ParticipantConnected, onParticipantConnected);
  room.on(RoomEvent.Disconnected, () => {
    stopPreview();
    state.allowedAgents.clear();
    dom.avatarPlaceholder.hidden = false;
    setStatus('방에서 나왔습니다.');
  });
  await room.connect(join.url, join.token);
  state.marks.connected = performance.now();
  restrictMicrophoneSubscribers(room);
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
  dom.avatarPlaceholder.textContent = '면접을 시작하면 AI 면접관 아바타(또는 음성 전용 모드)가 연결됩니다.';
  dom.avatarPlaceholder.hidden = false;
  try {
    await openPreview();
    let sessionId = Number(dom.sessionId.value) || null;
    if (!sessionId) {
      const depth = Number(dom.depth ? dom.depth.value : 2) || 2;
      const created = await api(`/jobs/${Number(dom.jobId.value)}/interview-sessions`, {
        method: 'POST',
        body: { consent_transcript: true, consent_version: state.consentVersion, depth },
      });
      sessionId = created.session.id;
    }
    state.sessionId = sessionId;
    state.over = false;
    state.marks = {};
    state.allowedAgents.clear();
    const join = await api(`/interview-sessions/${sessionId}/join`, { method: 'POST' });
    await connect(join);
    dom.end.disabled = false;
    state.poll = setInterval(pollOnce, POLL_MS);
  } catch (error) {
    stopPreview();
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
window.addEventListener('beforeunload', () => { stopPreview(); if (state.room) state.room.disconnect(); });
