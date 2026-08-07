(function registerWebSpeechController(global) {
  "use strict";

  const ERROR_MESSAGES = Object.freeze({
    "not-allowed": "마이크 권한이 거부되었습니다. 브라우저 사이트 권한을 확인하세요.",
    "service-not-allowed": "브라우저 음성 인식 서비스 사용이 허용되지 않았습니다.",
    "audio-capture": "사용할 수 있는 마이크를 찾지 못했습니다.",
    network: "음성 인식 서비스의 네트워크 연결에 실패했습니다.",
    "no-speech": "음성이 감지되지 않았습니다.",
    aborted: "음성 인식이 중지되었습니다.",
    "language-not-supported": "선택한 언어를 이 브라우저가 지원하지 않습니다.",
    unknown: "음성 인식 중 알 수 없는 오류가 발생했습니다.",
  });
  const STOP_RESTART_ERRORS = new Set([
    "not-allowed",
    "service-not-allowed",
    "audio-capture",
    "network",
    "language-not-supported",
  ]);

  function createWebSpeechController(options = {}) {
    const Recognition =
      options.Recognition || global.SpeechRecognition || global.webkitSpeechRecognition;
    const onInterim = options.onInterim || (() => {});
    const onFinal = options.onFinal || (() => {});
    const onStateChange = options.onStateChange || (() => {});
    const onError = options.onError || (() => {});

    let recognition = null;
    let active = false;
    let starting = false;
    let shouldListen = false;
    let destroyed = false;
    let restartTimer = null;
    let currentLanguage = "en-US";

    function emitState(status, detail = {}) {
      onStateChange({ status, language: currentLanguage, ...detail });
    }

    function clearRestartTimer() {
      if (restartTimer !== null) {
        global.clearTimeout(restartTimer);
        restartTimer = null;
      }
    }

    function buildRecognition() {
      if (!Recognition) return null;

      const next = new Recognition();
      next.continuous = true;
      next.interimResults = true;
      next.maxAlternatives = 1;
      next.lang = currentLanguage;

      next.onstart = () => {
        active = true;
        starting = false;
        emitState("listening");
      };

      next.onresult = (event) => {
        let interimText = "";
        for (let index = event.resultIndex; index < event.results.length; index += 1) {
          const result = event.results[index];
          const alternative = result[0];
          const transcript = alternative?.transcript?.trim();
          if (!transcript) continue;

          if (result.isFinal) {
            const rawConfidence = alternative.confidence;
            onFinal({
              transcript,
              stt_source: "WEB_SPEECH",
              stt_confidence:
                typeof rawConfidence === "number" && Number.isFinite(rawConfidence)
                  ? rawConfidence
                  : null,
              language: currentLanguage,
            });
          } else {
            interimText = `${interimText} ${transcript}`.trim();
          }
        }
        onInterim(interimText);
      };

      next.onerror = (event) => {
        const code = event.error || "unknown";
        if (STOP_RESTART_ERRORS.has(code)) shouldListen = false;
        const error = {
          code,
          message: ERROR_MESSAGES[code] || ERROR_MESSAGES.unknown,
          language: currentLanguage,
        };
        onError(error);
        emitState("error", { error });
      };

      next.onend = () => {
        active = false;
        starting = false;
        onInterim("");
        if (!shouldListen || destroyed) {
          emitState("idle");
          return;
        }
        clearRestartTimer();
        restartTimer = global.setTimeout(() => start(currentLanguage), 400);
      };

      return next;
    }

    function start(language = "en-US") {
      if (!Recognition || destroyed) {
        emitState("unsupported");
        return false;
      }
      currentLanguage = language;
      shouldListen = true;
      clearRestartTimer();
      if (active || starting) return true;

      if (!recognition) recognition = buildRecognition();
      recognition.lang = currentLanguage;
      starting = true;
      emitState("starting");
      try {
        recognition.start();
        return true;
      } catch (error) {
        starting = false;
        if (error?.name === "InvalidStateError") return true;
        shouldListen = false;
        const detail = {
          code: "start-failed",
          message: "음성 인식을 시작하지 못했습니다.",
          language: currentLanguage,
        };
        onError(detail);
        emitState("error", { error: detail });
        return false;
      }
    }

    function stop() {
      shouldListen = false;
      clearRestartTimer();
      onInterim("");
      if (!recognition || (!active && !starting)) {
        emitState("idle");
        return;
      }
      emitState("stopping");
      try {
        recognition.stop();
      } catch (_) {
        emitState("idle");
      }
    }

    function abort() {
      shouldListen = false;
      clearRestartTimer();
      onInterim("");
      if (recognition) {
        try {
          recognition.abort();
        } catch (_) {
          // 이미 종료된 인식기는 추가 처리가 필요 없다.
        }
      }
      active = false;
      starting = false;
      emitState("idle");
    }

    function destroy() {
      destroyed = true;
      abort();
      if (recognition) {
        recognition.onstart = null;
        recognition.onresult = null;
        recognition.onerror = null;
        recognition.onend = null;
      }
      recognition = null;
    }

    return {
      supported: Boolean(Recognition),
      start,
      stop,
      abort,
      destroy,
      get isListening() {
        return active;
      },
      get wantsListening() {
        return shouldListen;
      },
      get language() {
        return currentLanguage;
      },
    };
  }

  global.createWebSpeechController = createWebSpeechController;
})(globalThis);
