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
import sys
import time

from app.schemas.ai import CounterpartProfile, PreSpeechRequest, SpeechFeedbackRequest
from app.services.ai_service import AiService

# 콘솔/파일 리다이렉트 어디로 나가든 한글이 깨지지 않게 고정한다.
sys.stdout.reconfigure(encoding="utf-8")

REPEATS = 10
# 호출 사이 간격. 계정 RPM 한도에 걸려 실패가 몰리면 결과를 신뢰할 수 없으므로 넉넉히 둔다.
CALL_INTERVAL_SECONDS = 3

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
    failures = 0
    for i in range(REPEATS):
        try:
            result = service.generate_pre_speech(PRE_SPEECH_REQUEST)
            expressions.append(result.expression)
            print(f"[{i + 1}] {result.expression}")
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"[{i + 1}] 실패: {exc!r}")
        time.sleep(CALL_INTERVAL_SECONDS)

    unique = collections.Counter(expressions)
    print(f"\n성공 {len(expressions)}/{REPEATS} (실패 {failures}건)")
    print(f"고유 표현 수: {len(unique)} / {len(expressions)}")
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
        failures = 0
        for i in range(REPEATS):
            try:
                result = service.generate_speech_feedback(request)
                flagged_results.append((result.flagged, result.type))
            except Exception as exc:  # noqa: BLE001
                failures += 1
                print(f"    [{i + 1}] 호출 실패: {exc!r}")
            time.sleep(CALL_INTERVAL_SECONDS)

        succeeded = len(flagged_results)
        flagged_count = sum(1 for flagged, _ in flagged_results if flagged is True)
        types = collections.Counter(t for flagged, t in flagged_results if flagged)

        print(f"\n문장: {sentence!r}")
        print(f"  성공 {succeeded}/{REPEATS} (실패 {failures}건)")
        if succeeded == 0:
            print("  [주의] 전부 호출 실패라 판정 결과 없음 (재실행 필요)")
            continue
        print(f"  flagged=True 비율: {flagged_count}/{succeeded}")
        if types:
            print(f"  type 분포: {dict(types)}")
        if 0 < flagged_count < succeeded:
            print("  [주의] 판정이 반복 호출마다 흔들림 (감지 기준선 불안정 후보)")
        if failures:
            print("  [주의] 일부 호출이 실패해 성공분만으로 계산한 비율임 (참고용)")


def main() -> None:
    service = AiService()
    run_pre_speech_repeats(service)
    run_speech_feedback_repeats(service)


if __name__ == "__main__":
    main()
