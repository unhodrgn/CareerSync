'use strict';
/*
 * Meeting page of the standalone AI avatar interview PoC (a seeker practice interview, not a hiring tool).
 *
 * Privacy rules kept here:
 *  - The camera is opened ONLY for a local preview (getUserMedia, attached to a muted <video>). It is never handed to
 *    LiveKit: this page never publishes a camera track, and the token only allows a microphone track.
 *  - Only the microphone is published, and only the interviewer agent may subscribe to it (not the avatar worker).
 *  - The transcript on the page arrives from the agent already masked; nothing is stored in the browser.
 * All user-facing text of this page is in the STRINGS object below.
 */

const { Room, RoomEvent, ParticipantKind, DisconnectReason } = window.LivekitClient;

const EVENT_TOPIC = 'poc.event'; // agent -> page: masked transcript lines, status, end, error
const READY_ATTRIBUTE = 'poc_ready'; // page -> agent: attached and able to hear the avatar
const AVATAR_IDENTITY = 'anam-avatar-agent'; // the Anam plugin's default avatar participant identity (a second guard)
const PUBLISH_ON_BEHALF = 'lk.publish_on_behalf'; // documented marker: an avatar worker is kind "agent" with this attribute
const AVATAR_WAIT_MS = 35000;
const AUDIBLE_RMS = 0.02;
// ?open=1 skips the subscription restriction (debugging only: any participant could then subscribe to the microphone)
const OPEN_SUBSCRIBERS = new URLSearchParams(window.location.search).get('open') === '1';

const STRINGS = {
  idle: '대기 중',
  checkingMedia: '마이크와 카메라 권한을 확인하는 중…',
  noCamera: '카메라를 사용할 수 없어 미리보기 없이 진행합니다. (마이크만 사용)',
  noMic: '마이크를 사용할 수 없습니다. 브라우저의 마이크 권한을 허용한 뒤 다시 시도해 주세요.',
  connecting: 'AI 면접관에 연결하는 중…',
  waitingAvatar: '아바타가 입장하기를 기다리는 중…',
  avatarTimeout: '아바타 영상이 연결되지 않았습니다. 잠시 후 다시 시도해 주세요.',
  live: '진행 중',
  who: { agent: 'AI 면접관', candidate: '나' },
  stages: {
    opening: 'AI 면접관이 안내하는 중…',
    wait_answer_1: '마이크가 켜져 있습니다. 답변을 말씀해 주세요.',
    responding_1: 'AI가 답변을 확인하는 중…',
    wait_answer_2: '마이크가 켜져 있습니다. 후속 질문에 답변해 주세요.',
    responding_2: 'AI가 마무리하는 중…',
  },
  ended: {
    completed: '면접 연습이 끝났습니다. 수고하셨습니다.',
    time_limit: '시간이 다 되어 면접 연습이 끝났습니다.',
    hard_stop: '시간이 다 되어 면접 연습이 끝났습니다.',
    no_answer: '답변이 확인되지 않아 면접 연습이 끝났습니다.',
    default: '면접 연습이 끝났습니다.',
  },
  llmError: '지금은 AI가 질문을 이어갈 수 없어 연습이 끝났습니다.',
  avatarError: '아바타를 시작하지 못했습니다. (계정, 사용 한도 또는 연결을 확인해 주세요.)',
  busy: '다른 연습 세션이 진행 중입니다. 잠시 후 다시 시도해 주세요.',
  disconnected: '연결이 종료되었습니다.',
  genericError: '문제가 생겨 시작하지 못했습니다. 콘솔 메시지를 확인해 주세요.',
  metricsNone: '아직 없음',
};

const el = (id) => document.getElementById(id);
const dom = {
  agree: el('agree'),
  start: el('start'),
  end: el('end'),
  status: el('status'),
  timer: el('timer'),
  error: el('error'),
  transcript: el('transcript'),
  metrics: el('metrics'),
  avatarVideo: el('avatar-video'),
  avatarPlaceholder: el('avatar-placeholder'),
  previewVideo: el('preview-video'),
  remoteAudio: el('remote-audio'),
};

const session = {
  room: null,
  data: null, // { url, token, room, identity, max_seconds, avatar }
  previewStream: null,
  timerHandle: null,
  connectedAt: 0,
  allowedAgents: new Set(),
  avatarTimeout: null,
  ended: false,
  lastCandidateLineAt: 0,
  lastAgentLineAt: 0,
  agentLines: 0,
  waitingForAudible: false,
  analyser: null,
  analyserTimer: null,
  figures: {},
};

function setStatus(text) {
  dom.status.textContent = text;
}

function showError(text) {
  dom.error.textContent = text;
  dom.error.hidden = !text;
}

function formatClock(seconds) {
  const s = Math.max(0, Math.floor(seconds));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
}

// ── Measurements (this browser's view; the agent writes its own report in interview_poc/.runs/) ──

function renderFigures() {
  const rows = Object.entries(session.figures);
  dom.metrics.textContent = rows.length ? rows.map(([k, v]) => `${k}: ${v}`).join('\n') : STRINGS.metricsNone;
}

function noteFigure(name, value) {
  session.figures[name] = value;
  console.info('[measure]', name, value);
  renderFigures();
}

function startAudibleWatch(track) {
  // Watches the loudness of the avatar's (or agent's) audio track to time the first audible sound after a line is announced
  try {
    const ctx = new AudioContext();
    const source = ctx.createMediaStreamSource(new MediaStream([track.mediaStreamTrack]));
    const analyser = ctx.createAnalyser();
    analyser.fftSize = 1024;
    source.connect(analyser);
    const buf = new Float32Array(analyser.fftSize);
    session.analyser = analyser;
    session.analyserTimer = window.setInterval(() => {
      analyser.getFloatTimeDomainData(buf);
      let sum = 0;
      for (const v of buf) sum += v * v;
      const rms = Math.sqrt(sum / buf.length);
      if (session.waitingForAudible && rms > AUDIBLE_RMS) {
        session.waitingForAudible = false;
        const now = performance.now();
        const since = Math.round(now - session.lastAgentLineAt);
        noteFigure(`AI 음성 #${session.agentLines}: 첫 소리 (AI 줄 알림 후)`, `${since} ms`);
        if (session.lastCandidateLineAt && session.lastAgentLineAt > session.lastCandidateLineAt) {
          noteFigure(`AI 음성 #${session.agentLines}: 응답 지연 (내 발화 확정 → AI 소리)`, `${Math.round(now - session.lastCandidateLineAt)} ms`);
        }
      }
    }, 40);
  } catch (e) {
    console.warn('audible watch unavailable', e);
  }
}

// ── Events from the agent ──

function appendLine(role, text) {
  const li = document.createElement('li');
  li.className = role;
  const who = document.createElement('span');
  who.className = 'who';
  who.textContent = STRINGS.who[role] || role;
  const body = document.createElement('span');
  body.textContent = text; // textContent only: transcript text is never parsed as HTML
  li.append(who, body);
  dom.transcript.append(li);
}

function handleAgentEvent(event) {
  switch (event.type) {
    case 'line': {
      appendLine(event.role, event.text);
      const now = performance.now();
      if (event.role === 'agent') {
        session.lastAgentLineAt = now;
        session.waitingForAudible = true;
        session.agentLines += 1;
      } else {
        session.lastCandidateLineAt = now;
      }
      break;
    }
    case 'status':
      setStatus(STRINGS.stages[event.stage] || STRINGS.live);
      break;
    case 'end':
      session.ended = true;
      setStatus(event.reason && event.reason.startsWith('llm_error') ? STRINGS.llmError : STRINGS.ended[event.reason] || STRINGS.ended.default);
      break;
    case 'error':
      showError(STRINGS.avatarError);
      break;
    default:
      break;
  }
}

// ── Subscription permissions: only the interviewer agent may subscribe to the microphone ──

function restrictMicrophoneSubscribers(room) {
  if (OPEN_SUBSCRIBERS) return;
  room.localParticipant.setTrackSubscriptionPermissions(false, []);
}

function isAvatarWorker(participant) {
  return participant.identity === AVATAR_IDENTITY || Boolean(participant.attributes && participant.attributes[PUBLISH_ON_BEHALF]);
}

function allowAgent(room, participant) {
  if (OPEN_SUBSCRIBERS) return;
  if (participant.kind !== ParticipantKind.AGENT || isAvatarWorker(participant)) return;
  session.allowedAgents.add(participant.identity);
  room.localParticipant.setTrackSubscriptionPermissions(
    false,
    [...session.allowedAgents].map((participantIdentity) => ({ participantIdentity, allowAll: true })),
  );
  console.info('[privacy] microphone subscription allowed for the interviewer agent only');
}

// ── Media and room ──

async function openPreview() {
  // Permission for the microphone is required; the camera is optional and used for the local preview only
  let stream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: true, video: true });
  } catch (first) {
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      showError(STRINGS.noCamera);
    } catch (second) {
      throw new Error(STRINGS.noMic);
    }
  }
  stream.getAudioTracks().forEach((t) => t.stop()); // only the permission was needed; LiveKit opens its own microphone track
  const video = stream.getVideoTracks();
  if (video.length) {
    session.previewStream = new MediaStream(video);
    dom.previewVideo.srcObject = session.previewStream; // local only: never published, never uploaded
  }
}

function stopPreview() {
  if (session.previewStream) {
    session.previewStream.getTracks().forEach((t) => t.stop());
    session.previewStream = null;
  }
  dom.previewVideo.srcObject = null;
}

async function markReady() {
  try {
    await session.room.localParticipant.setAttributes({ [READY_ATTRIBUTE]: '1' });
  } catch (e) {
    console.warn('could not set the ready attribute', e);
  }
}

function onTrackSubscribed(track, _publication, participant) {
  if (participant.kind !== ParticipantKind.AGENT) return; // the agent and the avatar worker are both kind "agent"
  if (track.kind === 'video') {
    track.attach(dom.avatarVideo);
    dom.avatarPlaceholder.hidden = true;
    window.clearTimeout(session.avatarTimeout);
    noteFigure('아바타 영상 연결 (연결 후)', `${Math.round(performance.now() - session.connectedAt)} ms`);
    setStatus(STRINGS.live);
    if (session.data.avatar) markReady();
  } else if (track.kind === 'audio') {
    dom.remoteAudio.append(track.attach());
    startAudibleWatch(track);
    if (!session.data.avatar) markReady();
  }
}

async function startSession() {
  showError('');
  dom.start.disabled = true;
  dom.agree.disabled = true;
  dom.transcript.replaceChildren();
  session.ended = false;
  session.figures = {};
  session.agentLines = 0;
  session.lastAgentLineAt = 0;
  session.lastCandidateLineAt = 0;
  renderFigures();
  try {
    setStatus(STRINGS.checkingMedia);
    await openPreview();

    setStatus(STRINGS.connecting);
    const response = await fetch('/api/token', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' });
    if (response.status === 409) throw new Error(STRINGS.busy);
    if (!response.ok) throw new Error(STRINGS.genericError);
    session.data = await response.json();

    const room = new Room({ adaptiveStream: true });
    session.room = room;
    room.on(RoomEvent.TrackSubscribed, onTrackSubscribed);
    room.on(RoomEvent.ParticipantConnected, (participant) => allowAgent(room, participant));
    room.on(RoomEvent.Disconnected, (reason) => onDisconnected(reason));
    room.registerTextStreamHandler(EVENT_TOPIC, async (reader) => {
      try {
        handleAgentEvent(JSON.parse(await reader.readAll()));
      } catch (e) {
        console.warn('unreadable agent event', e);
      }
    });

    await room.connect(session.data.url, session.data.token);
    session.connectedAt = performance.now();
    restrictMicrophoneSubscribers(room);
    room.remoteParticipants.forEach((p) => allowAgent(room, p));

    await room.localParticipant.setMicrophoneEnabled(true); // the only track this page publishes
    await room.startAudio();
    dom.end.disabled = false;
    startTimer(session.data.max_seconds);
    setStatus(session.data.avatar ? STRINGS.waitingAvatar : STRINGS.live);
    if (session.data.avatar) {
      session.avatarTimeout = window.setTimeout(() => {
        showError(STRINGS.avatarTimeout);
        endSession();
      }, AVATAR_WAIT_MS);
    }
  } catch (e) {
    console.error(e);
    showError(e && e.message ? e.message : STRINGS.genericError);
    await endSession();
  }
}

function startTimer(maxSeconds) {
  const began = performance.now();
  const total = formatClock(maxSeconds <= 180 ? 180 : maxSeconds);
  session.timerHandle = window.setInterval(() => {
    dom.timer.textContent = `${formatClock((performance.now() - began) / 1000)} / ${total}`;
  }, 500);
}

function releaseSlot() {
  // Tells the local server the session is over (it frees the one-session slot and deletes the room if it still exists)
  const roomName = session.data && session.data.room;
  session.data = null;
  if (roomName) {
    fetch('/api/end', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ room: roomName }), keepalive: true }).catch(() => {});
  }
}

function onDisconnected(reason) {
  if (!session.ended) setStatus(STRINGS.disconnected);
  const label = DisconnectReason && reason !== undefined ? DisconnectReason[reason] : '';
  console.info('[room] disconnected', label || reason);
  releaseSlot();
  cleanup();
}

function cleanup() {
  window.clearInterval(session.timerHandle);
  window.clearInterval(session.analyserTimer);
  window.clearTimeout(session.avatarTimeout);
  stopPreview();
  dom.avatarPlaceholder.hidden = false;
  dom.end.disabled = true;
  dom.agree.disabled = false;
  dom.start.disabled = !dom.agree.checked;
  session.room = null;
  session.allowedAgents.clear();
}

async function endSession() {
  const room = session.room;
  if (room) {
    try {
      await room.disconnect(); // graceful: stops the microphone track and leaves; the agent then closes the session
    } catch (e) {
      console.warn('disconnect failed', e);
    }
  }
  releaseSlot();
  cleanup();
}

dom.agree.addEventListener('change', () => {
  dom.start.disabled = !dom.agree.checked;
});
dom.start.addEventListener('click', startSession);
dom.end.addEventListener('click', endSession);
window.addEventListener('pagehide', () => {
  if (session.data && session.data.room) {
    navigator.sendBeacon('/api/end', new Blob([JSON.stringify({ room: session.data.room })], { type: 'application/json' }));
  }
  if (session.room) session.room.disconnect();
});

setStatus(STRINGS.idle);
renderFigures();
