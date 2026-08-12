"""수동 QA 스크립트: 같은 입력을 여러 번 호출했을 때 F-02/F-03 결과가 얼마나 일관되는지 확인한다.

pytest가 아니라 실제 OpenAI API를 호출하는 수동 점검용 스크립트다.
자동 CI에서 실행하지 않는다 (비용·비결정성 때문).

AiService는 temperature=0.3으로 호출하므로 완전한 결정성은 기대하지 않는다.
이 스크립트의 목적은 다음 두 가지를 눈으로 확인하는 것이다.
- F-02: 같은 입력에 대해 expression 표현이 매번 크게 달라지지 않는지
- F-03: 같은 문장에 대해 flagged/type 판정이 흔들리지 않는지 (감지 기준선 안정성 점검)

실행:
    .venv\\Scripts\\python.exe tests\\manual_qa\\consistency_check.py
"""

import collections

from app.schemas.ai import CounterpartProfile, PreSpeechRequest, SpeechFeedbackRequest
from app.services.ai_service import AiService

REPEATS = 10

PROFILE = CounterpartProfile(
    proficiency="중급",
    communication_style="균형적",
    job_role="Product Manager",
)

PRE_SPEECH_REQUEST = PreSpeechRequest(
    korean_text="이 일정은 솔직히 어려울 것 같아요",
    counterpart_profile=PROFILE,
    meeting_context="다음 주 마감인 프로젝트 일정 조율 회의",
)

# 명확히 걸리는 문장 / 명확히 안 걸리는 문장 / 애매한 경계 문장을 섞어서 확인한다.
FEEDBACK_SENTENCES = [
    "That schedule is impossible.",
    "Let's table this for now.",
    "Could you share the file when you get a chance?",
    "Honestly, that idea doesn't make sense.",
]


def run_pre_speech_repeats(service: AiService) -> None:
    print("=" * 100)
    print(f"F-02 pre-speech: 같은 입력 x{REPEATS} 반복 (profile/context 고정)")
    print(f"입력 문장: {PRE_SPEECH_REQUEST.korean_text!r}")
    print("=" * 100)

    expressions = []
    for i in range(REPEATS):
        try:
            result = service.generate_pre_speech(PRE_SPEECH_REQUEST)
            expressions.append(result.expression)
            print(f"[{i + 1}] {result.expression}")
        except Exception as exc:  # noqa: BLE001
            print(f"[{i + 1}] 실패: {exc!r}")

    unique = collections.Counter(expressions)
    print(f"\n고유 표현 수: {len(unique)} / {len(expressions)}")
    for expression, count in unique.most_common():
        print(f"  x{count}: {expression}")


def run_speech_feedback_repeats(service: AiService) -> None:
    print("\n" + "=" * 100)
    print(f"F-03 speech-feedback: 같은 문장 x{REPEATS} 반복 (profile 고정)")
    print("=" * 100)

    for sentence in FEEDBACK_SENTENCES:
        request = SpeechFeedbackRequest(
            english_text=sentence,
            recent_messages=[],
            counterpart_profile=PROFILE,
        )
        flagged_results = []
        for i in range(REPEATS):
            try:
                result = service.generate_speech_feedback(request)
                flagged_results.append((result.flagged, result.type))
            except Exception as exc:  # noqa: BLE001
                flagged_results.append((None, f"실패: {exc!r}"))

        flagged_count = sum(1 for flagged, _ in flagged_results if flagged is True)
        types = collections.Counter(t for flagged, t in flagged_results if flagged)

        print(f"\n문장: {sentence!r}")
        print(f"  flagged=True 비율: {flagged_count}/{REPEATS}")
        if types:
            print(f"  type 분포: {dict(types)}")
        if 0 < flagged_count < REPEATS:
            print("  [주의] 판정이 반복 호출마다 흔들림 (감지 기준선 불안정 후보)")


def main() -> None:
    service = AiService()
    run_pre_speech_repeats(service)
    run_speech_feedback_repeats(service)


if __name__ == "__main__":
    main()
