const assert = require("node:assert/strict");
const test = require("node:test");

require("./web-speech-recognition.js");

class FakeSpeechRecognition {
  static instances = [];

  constructor() {
    this.lang = "";
    this.continuous = false;
    this.interimResults = false;
    this.maxAlternatives = 0;
    FakeSpeechRecognition.instances.push(this);
  }

  start() {
    this.onstart?.();
  }

  stop() {
    this.onend?.();
  }

  abort() {
    this.onend?.();
  }

  emitResult({ interim = "", final = "", confidence = Number.NaN }) {
    const results = [];
    if (interim) {
      const interimResult = [{ transcript: interim, confidence: Number.NaN }];
      interimResult.isFinal = false;
      results.push(interimResult);
    }
    if (final) {
      const finalResult = [{ transcript: final, confidence }];
      finalResult.isFinal = true;
      results.push(finalResult);
    }
    this.onresult?.({ resultIndex: 0, results });
  }
}

test("한국어와 영어 final payload 및 상태 전환 계약을 유지한다", () => {
  const states = [];
  const interim = [];
  const finals = [];
  const controller = globalThis.createWebSpeechController({
    Recognition: FakeSpeechRecognition,
    onStateChange: ({ status }) => states.push(status),
    onInterim: (text) => interim.push(text),
    onFinal: (payload) => finals.push(payload),
  });

  assert.equal(controller.supported, true);
  assert.equal(controller.start("ko-KR"), true);

  const recognition = FakeSpeechRecognition.instances.at(-1);
  assert.equal(recognition.lang, "ko-KR");
  assert.equal(recognition.continuous, true);
  assert.equal(recognition.interimResults, true);
  assert.equal(recognition.maxAlternatives, 1);

  recognition.emitResult({
    interim: "안녕",
    final: "안녕하세요",
    confidence: 0.91,
  });
  assert.equal(interim.at(-1), "안녕");
  assert.deepEqual(finals.at(-1), {
    transcript: "안녕하세요",
    stt_source: "WEB_SPEECH",
    stt_confidence: 0.91,
    language: "ko-KR",
  });

  controller.stop();
  assert.deepEqual(states, ["starting", "listening", "stopping", "idle"]);

  assert.equal(controller.start("en-US"), true);
  assert.equal(recognition.lang, "en-US");
  recognition.emitResult({ final: "Hello everyone" });
  assert.deepEqual(finals.at(-1), {
    transcript: "Hello everyone",
    stt_source: "WEB_SPEECH",
    stt_confidence: null,
    language: "en-US",
  });

  controller.stop();
});
