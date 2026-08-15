const API_BASE = "http://127.0.0.1:8000/api/v1";

const state = {
  meetingId: null,
  participantId: null,
  token: null,
  role: null,
  shareUrl: null,
  callFrame: null,
  pollTimer: null,
  exiting: false,
  voiceAnalysisEnabled: false,
  speechController: null,
  speechFinals: [],
};

const elements = {
  apiStatus: document.querySelector("#api-status"),
  entryView: document.querySelector("#entry-view"),
  entryTitle: document.querySelector("#entry-title"),
  entryForm: document.querySelector("#entry-form"),
  entrySubmit: document.querySelector("#entry-submit"),
  createFields: document.querySelector("#create-fields"),
  meetingInfo: document.querySelector("#meeting-info"),
  roomView: document.querySelector("#room-view"),
  roomRole: document.querySelector("#room-role"),
  roomTitle: document.querySelector("#room-title"),
  copyLink: document.querySelector("#copy-link"),
  exitMeeting: document.querySelector("#exit-meeting"),
  videoContainer: document.querySelector("#video-container"),
  videoLoading: document.querySelector("#video-loading"),
  participantCount: document.querySelector("#participant-count"),
  participants: document.querySelector("#participants"),
  voiceAnalysisConsent: document.querySelector("#voice-analysis-consent"),
  speechLanguage: document.querySelector("#speech-language"),
  speechToggle: document.querySelector("#speech-toggle"),
  speechStatus: document.querySelector("#speech-status"),
  speechSupportNote: document.querySelector("#speech-support-note"),
  speechInterim: document.querySelector("#speech-interim"),
  speechFinals: document.querySelector("#speech-finals"),
  speechCopy: document.querySelector("#speech-copy"),
  speechClear: document.querySelector("#speech-clear"),
  message: document.querySelector("#message"),
  aiTargetParticipant: document.querySelector("#ai-target-participant"),
  aiKoreanText: document.querySelector("#ai-korean-text"),
  aiMeetingContext: document.querySelector("#ai-meeting-context"),
  aiPreSpeechBtn: document.querySelector("#ai-pre-speech-btn"),
  aiPreSpeechResult: document.querySelector("#ai-pre-speech-result"),
  aiSpeechFeedbackBtn: document.querySelector("#ai-speech-feedback-btn"),
  aiSpeechFeedbackResult: document.querySelector("#ai-speech-feedback-result"),
};

function meetingIdFromPath() {
  return window.location.pathname.match(/^\/(?:join|meetings)\/([0-9a-f-]{36})\/?$/i)?.[1] ?? null;
}

function tokenKey(meetingId) {
  return `video-check:${meetingId}:participant-token`;
}

function roleKey(meetingId) {
  return `video-check:${meetingId}:role`;
}

function showMessage(message) {
  elements.message.textContent = message;
  elements.message.classList.remove("hidden");
}

function clearMessage() {
  elements.message.classList.add("hidden");
  elements.message.textContent = "";
}

function setSpeechStatus(status, error = null) {
  const labels = {
    unsupported: "미지원",
    idle: "대기",
    starting: "시작 중",
    listening: "듣는 중",
    stopping: "정지 중",
    error: "오류",
  };
  elements.speechStatus.textContent = labels[status] || status;
  elements.speechStatus.classList.toggle("active", status === "listening");
  elements.speechStatus.classList.toggle("error", status === "error");

  const active = ["starting", "listening", "stopping"].includes(status);
  elements.speechLanguage.disabled = active;
  elements.speechToggle.textContent = active ? "음성 인식 중지" : "음성 인식 시작";
  if (error?.message) elements.speechSupportNote.textContent = error.message;
}

function renderSpeechFinals() {
  if (state.speechFinals.length === 0) {
    const empty = document.createElement("li");
    empty.className = "empty";
    empty.textContent = "아직 확정된 문장이 없습니다.";
    elements.speechFinals.replaceChildren(empty);
    elements.speechCopy.disabled = true;
    elements.speechClear.disabled = true;
    return;
  }

  elements.speechFinals.replaceChildren(
    ...state.speechFinals.map((item) => {
      const row = document.createElement("li");
      const text = document.createElement("span");
      const meta = document.createElement("small");
      const confidence = item.stt_confidence === null
        ? "신뢰도 미제공"
        : `신뢰도 ${Math.round(item.stt_confidence * 100)}%`;
      text.textContent = item.transcript;
      meta.textContent = `${item.language} · ${confidence}`;
      row.append(text, meta);
      return row;
    }),
  );
  elements.speechCopy.disabled = false;
  elements.speechClear.disabled = false;
}

function applySpeechAvailability() {
  const supported = Boolean(state.speechController?.supported);
  const enabled = supported && state.voiceAnalysisEnabled;
  elements.speechToggle.disabled = !enabled;

  if (!supported) {
    setSpeechStatus("unsupported");
    elements.speechSupportNote.textContent =
      "이 브라우저는 SpeechRecognition을 지원하지 않습니다. 데스크톱 Chrome으로 확인하세요.";
  } else if (!state.voiceAnalysisEnabled) {
    setSpeechStatus("idle");
    elements.speechSupportNote.textContent =
      "입장할 때 음성 인식에 동의하지 않아 비활성화되었습니다.";
  } else {
    setSpeechStatus("idle");
    elements.speechSupportNote.textContent =
      "원본 음성·텍스트는 서버로 보내지 않고 최근 확정 문장 3개만 탭 메모리에 둡니다.";
  }
}

function initializeSpeechPanel() {
  const browserLanguage = navigator.language?.toLowerCase() || "";
  elements.speechLanguage.value = browserLanguage.startsWith("ko") ? "ko-KR" : "en-US";

  if (typeof window.createWebSpeechController !== "function") {
    elements.speechToggle.disabled = true;
    setSpeechStatus("unsupported");
    elements.speechSupportNote.textContent = "Web Speech 컨트롤러를 불러오지 못했습니다.";
    return;
  }

  state.speechController = window.createWebSpeechController({
    onInterim(text) {
      elements.speechInterim.textContent = text || "—";
    },
    onFinal(payload) {
      state.speechFinals = [...state.speechFinals, payload].slice(-3);
      renderSpeechFinals();

      // AI 담당자는 이 이벤트의 detail을 F-03 API 요청에 연결하면 된다.
      window.dispatchEvent(
        new CustomEvent("webspeech-final-transcript", { detail: payload }),
      );
    },
    onStateChange({ status, error }) {
      setSpeechStatus(status, error);
    },
    onError(error) {
      elements.speechSupportNote.textContent = error.message;
    },
  });
  applySpeechAvailability();
  renderSpeechFinals();
}

async function api(path, options = {}) {
  const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
  if (state.token) headers["X-Participant-Token"] = state.token;

  let response;
  try {
    response = await fetch(`${API_BASE}${path}`, { ...options, headers });
  } catch (_) {
    throw new Error("백엔드에 연결할 수 없습니다. 8000번 포트에서 FastAPI가 실행 중인지 확인하세요.");
  }

  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    const error = body.error;
    const fields = error?.field_errors?.map((item) => `${item.field}: ${item.message}`).join("\n");
    throw new Error([error?.message || `요청 실패 (${response.status})`, fields].filter(Boolean).join("\n"));
  }

  if (response.status === 204) return null;
  return response.json();
}

function aiTargetParticipantId() {
  return elements.aiTargetParticipant.value || null;
}

function showAiResult(target, text, { error = false, flagged = false } = {}) {
  target.textContent = text;
  target.classList.remove("hidden", "error", "flagged");
  if (error) target.classList.add("error");
  if (flagged) target.classList.add("flagged");
}

elements.aiPreSpeechBtn.addEventListener("click", async () => {
  const koreanText = elements.aiKoreanText.value.trim();
  if (!koreanText) {
    showAiResult(elements.aiPreSpeechResult, "한국어 문장을 입력해주세요.", { error: true });
    return;
  }

  elements.aiPreSpeechBtn.disabled = true;
  try {
    const response = await api(`/meetings/${state.meetingId}/pre-speech`, {
      method: "POST",
      body: JSON.stringify({
        input_ko: koreanText,
        target_participant_id: aiTargetParticipantId(),
        meeting_context: elements.aiMeetingContext.value.trim() || null,
      }),
    });
    const { recommended_expression_en, recommendation_reason_ko } = response.data;
    showAiResult(
      elements.aiPreSpeechResult,
      `"${recommended_expression_en}"\n\n${recommendation_reason_ko}`,
    );
  } catch (error) {
    showAiResult(elements.aiPreSpeechResult, error.message, { error: true });
  } finally {
    elements.aiPreSpeechBtn.disabled = false;
  }
});

elements.aiSpeechFeedbackBtn.addEventListener("click", async () => {
  const latestEnglish = [...state.speechFinals].reverse().find((item) => item.language === "en-US");
  if (!latestEnglish) {
    showAiResult(
      elements.aiSpeechFeedbackResult,
      "먼저 왼쪽에서 English로 말해 확정 문장을 만들어주세요.",
      { error: true },
    );
    return;
  }

  elements.aiSpeechFeedbackBtn.disabled = true;
  try {
    const recentContext = state.speechFinals
      .filter((item) => item.language === "en-US" && item !== latestEnglish)
      .map((item) => item.transcript)
      .slice(-3)
      .join("\n");

    const response = await api(`/meetings/${state.meetingId}/speech-feedback/analyze`, {
      method: "POST",
      body: JSON.stringify({
        transcript: latestEnglish.transcript,
        stt_confidence: latestEnglish.stt_confidence ?? null,
        stt_source: latestEnglish.stt_source || "WEB_SPEECH",
        recent_context: recentContext || null,
        target_participant_id: aiTargetParticipantId(),
      }),
    });
    const result = response.data;
    if (!result.risk_detected) {
      showAiResult(elements.aiSpeechFeedbackResult, `"${latestEnglish.transcript}"\n\n문제 없음`);
    } else {
      const { feedback, suppressed_duplicate } = result;
      const suffix = suppressed_duplicate ? "\n\n(30초 내 동일 문장 재감지 — 새로 저장하지 않음)" : "";
      showAiResult(
        elements.aiSpeechFeedbackResult,
        `"${latestEnglish.transcript}"\n\n[${feedback.risk_type}] ${feedback.explanation_ko}\n\n대안: ${feedback.alternative_expression_en}${suffix}`,
        { flagged: true },
      );
    }
  } catch (error) {
    showAiResult(elements.aiSpeechFeedbackResult, error.message, { error: true });
  } finally {
    elements.aiSpeechFeedbackBtn.disabled = false;
  }
});

function profilePayload() {
  const languages = document.querySelector("#languages").value
    .split(",")
    .map((value) => value.trim())
    .filter(Boolean);

  return {
    display_name: document.querySelector("#display-name").value.trim(),
    country_code: document.querySelector("#country-code").value.trim().toUpperCase(),
    organization: document.querySelector("#organization").value.trim(),
    job_title: document.querySelector("#job-title").value.trim(),
    languages,
    english_proficiency: document.querySelector("#english-proficiency").value,
    communication_style: document.querySelector("#communication-style").value,
    timezone: document.querySelector("#timezone").value.trim(),
    additional_considerations: null,
  };
}

function saveSession(meetingId, token, role) {
  state.meetingId = meetingId;
  state.token = token;
  state.role = role;
  sessionStorage.setItem(tokenKey(meetingId), token);
  sessionStorage.setItem(roleKey(meetingId), role);
}

async function loadJoinView(meetingId) {
  elements.entryTitle.textContent = "프로필 입력 후 참가";
  elements.entrySubmit.textContent = "회의 입장";
  elements.createFields.classList.add("hidden");

  const response = await api(`/meetings/${meetingId}/public`);
  const meeting = response.data;
  elements.meetingInfo.textContent = `${meeting.title} · ${meeting.current_participants}/${meeting.max_participants}명`;
  elements.meetingInfo.classList.remove("hidden");
  if (!meeting.can_join) {
    elements.entrySubmit.disabled = true;
    showMessage(meeting.status === "ENDED" ? "이미 종료된 회의입니다." : "회의 정원이 가득 찼습니다.");
  }
}

async function enterRoom(meetingId) {
  clearMessage();
  const [contextResponse, mediaResponse] = await Promise.all([
    api(`/meetings/${meetingId}`),
    api(`/meetings/${meetingId}/media-session`, { method: "POST" }),
  ]);

  const context = contextResponse.data;
  const media = mediaResponse.data;
  state.participantId = context.me.id;
  state.voiceAnalysisEnabled = Boolean(context.me.voice_analysis_enabled);
  state.shareUrl = `${window.location.origin}/join/${meetingId}`;
  elements.roomRole.textContent = `${context.me.role} · ${context.me.profile.display_name}`;
  elements.roomTitle.textContent = context.meeting.title;
  elements.exitMeeting.textContent = state.role === "HOST" ? "회의 종료" : "나가기";
  elements.entryView.classList.add("hidden");
  elements.roomView.classList.remove("hidden");
  history.replaceState({}, "", `/meetings/${meetingId}`);
  applySpeechAvailability();

  await connectDaily(media.room_url, media.meeting_token);
  await refreshParticipants();
  state.pollTimer = window.setInterval(refreshParticipants, 3000);
}

async function connectDaily(roomUrl, meetingToken) {
  const joinUrl = new URL(roomUrl);
  joinUrl.searchParams.set("t", meetingToken);

  const iframe = document.createElement("iframe");
  iframe.title = "Daily 화상회의";
  iframe.src = joinUrl.toString();
  iframe.allow = "camera; microphone; fullscreen; display-capture; autoplay";
  iframe.setAttribute("allowfullscreen", "");
  iframe.style.cssText = "position:absolute;inset:0;width:100%;height:100%;border:0";
  iframe.addEventListener("load", () => elements.videoLoading.classList.add("hidden"), { once: true });
  elements.videoContainer.append(iframe);

  state.callFrame = {
    async leave() { iframe.src = "about:blank"; },
    async destroy() { iframe.remove(); },
  };
}

async function refreshParticipants() {
  if (state.exiting) return;
  try {
    const response = await api(`/meetings/${state.meetingId}/participants`);
    elements.participantCount.textContent = `${response.meta.count}명`;
    elements.participants.replaceChildren(
      ...response.data.map((participant) => {
        const item = document.createElement("li");
        const name = document.createElement("strong");
        const detail = document.createElement("small");
        name.textContent = `${participant.display_name} (${participant.role})`;
        detail.textContent = `${participant.organization} · ${participant.job_title}`;
        item.append(name, detail);
        return item;
      }),
    );
    updateAiTargetOptions(response.data);
  } catch (error) {
    if (!state.exiting) showMessage(error.message);
  }
}

function updateAiTargetOptions(participants) {
  const select = elements.aiTargetParticipant;
  const previous = select.value;
  const others = participants.filter((participant) => participant.id !== state.participantId);
  select.replaceChildren(
    new Option("지정 안 함", ""),
    ...others.map((participant) => new Option(`${participant.display_name} (${participant.job_title})`, participant.id)),
  );
  if (others.some((participant) => participant.id === previous)) {
    select.value = previous;
  }
}

async function exitMeeting() {
  if (state.exiting) return;
  if (state.role === "HOST" && !window.confirm("모든 참가자의 회의를 종료할까요?")) return;

  state.exiting = true;
  elements.exitMeeting.disabled = true;
  window.clearInterval(state.pollTimer);
  state.speechController?.stop();
  try {
    const action = state.role === "HOST" ? "end" : "leave";
    await api(`/meetings/${state.meetingId}/${action}`, { method: "POST" });
    await state.callFrame?.leave().catch(() => {});
    await state.callFrame?.destroy().catch(() => {});
    sessionStorage.removeItem(tokenKey(state.meetingId));
    sessionStorage.removeItem(roleKey(state.meetingId));
    alert(state.role === "HOST" ? "회의를 종료했습니다." : "회의에서 나왔습니다.");
    window.location.assign("/");
  } catch (error) {
    state.exiting = false;
    elements.exitMeeting.disabled = false;
    showMessage(error.message);
  }
}

elements.entryForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  clearMessage();
  elements.entrySubmit.disabled = true;
  const meetingId = meetingIdFromPath();

  try {
    if (meetingId && !state.token) {
      const response = await api(`/meetings/${meetingId}/participants`, {
        method: "POST",
        body: JSON.stringify({
          profile: profilePayload(),
          profile_sharing_consent: true,
          voice_analysis_consent: elements.voiceAnalysisConsent.checked,
        }),
      });
      saveSession(meetingId, response.data.participant_token, "MEMBER");
      await enterRoom(meetingId);
    } else {
      const response = await api("/meetings", {
        method: "POST",
        body: JSON.stringify({
          title: document.querySelector("#meeting-title").value.trim(),
          max_participants: Number(document.querySelector("#max-participants").value),
          host_profile: profilePayload(),
          profile_sharing_consent: true,
          voice_analysis_consent: elements.voiceAnalysisConsent.checked,
        }),
      });
      const data = response.data;
      saveSession(data.meeting.id, data.participant_token, "HOST");
      state.shareUrl = data.share_url;
      await enterRoom(data.meeting.id);
    }
  } catch (error) {
    showMessage(error.message);
  } finally {
    elements.entrySubmit.disabled = false;
  }
});

elements.copyLink.addEventListener("click", async () => {
  try {
    await navigator.clipboard.writeText(state.shareUrl);
    elements.copyLink.textContent = "복사됨";
    window.setTimeout(() => { elements.copyLink.textContent = "초대 링크 복사"; }, 1200);
  } catch (_) {
    window.prompt("아래 링크를 복사하세요.", state.shareUrl);
  }
});

elements.exitMeeting.addEventListener("click", exitMeeting);

elements.speechToggle.addEventListener("click", () => {
  if (!state.speechController?.supported || !state.voiceAnalysisEnabled) return;
  if (state.speechController.wantsListening) {
    state.speechController.stop();
  } else {
    state.speechController.start(elements.speechLanguage.value);
  }
});

elements.speechClear.addEventListener("click", () => {
  state.speechFinals = [];
  elements.speechInterim.textContent = "—";
  renderSpeechFinals();
});

elements.speechCopy.addEventListener("click", async () => {
  const text = state.speechFinals.map((item) => item.transcript).join("\n");
  if (!text) return;
  try {
    await navigator.clipboard.writeText(text);
    elements.speechCopy.textContent = "복사됨";
    window.setTimeout(() => { elements.speechCopy.textContent = "복사"; }, 1200);
  } catch (_) {
    window.prompt("아래 확정 문장을 복사하세요.", text);
  }
});

window.addEventListener("beforeunload", () => state.speechController?.abort());

async function initialize() {
  const meetingId = meetingIdFromPath();
  try {
    if (!meetingId) {
      elements.apiStatus.textContent = "백엔드: localhost:8000";
      elements.apiStatus.classList.add("ok");
      return;
    }

    const savedToken = sessionStorage.getItem(tokenKey(meetingId));
    const savedRole = sessionStorage.getItem(roleKey(meetingId));
    if (window.location.pathname.startsWith("/meetings/") && savedToken && savedRole) {
      saveSession(meetingId, savedToken, savedRole);
      await enterRoom(meetingId);
    } else {
      history.replaceState({}, "", `/join/${meetingId}`);
      await loadJoinView(meetingId);
    }
    elements.apiStatus.textContent = "백엔드 연결됨";
    elements.apiStatus.classList.add("ok");
  } catch (error) {
    showMessage(error.message);
    elements.apiStatus.textContent = "백엔드 연결 실패";
  }
}

initializeSpeechPanel();
initialize();
