"""수동 QA 스크립트: 프로필 조합에 따라 F-02/F-03 결과가 실제로 달라지는지 눈으로 확인한다.

pytest가 아니라 실제 OpenAI API를 호출하는 수동 점검용 스크립트다.
자동 CI에서 실행하지 않는다 (비용·비결정성 때문).

실행:
    .venv\\Scripts\\python.exe tests\\manual_qa\\profile_variation_check.py
"""

import itertools

from app.schemas.ai import (
    CounterpartProfile,
    PreSpeechRequest,
    SpeechFeedbackRequest,
)
from app.services.ai_service import AiService

PROFICIENCIES = ["초급", "중급", "고급"]
STYLES = ["직접적", "완곡한", "균형적"]

FIXED_KOREAN_TEXT = "이 일정은 솔직히 어려울 것 같아요"
FIXED_MEETING_CONTEXT = "다음 주 마감인 프로젝트 일정 조율 회의"
FIXED_JOB_ROLE = "Product Manager"

FEEDBACK_SENTENCES = [
    "That schedule is impossible.",
    "Let's table this for now.",
    "Could you share the file when you get a chance?",
]


def run_pre_speech_matrix(service: AiService) -> None:
    print("=" * 100)
    print("F-02 pre-speech: 숙련도 x 소통방식 매트릭스 (문장/맥락 고정)")
    print(f"입력 문장: {FIXED_KOREAN_TEXT!r}")
    print("=" * 100)

    for proficiency, style in itertools.product(PROFICIENCIES, STYLES):
        profile = CounterpartProfile(
            proficiency=proficiency,
            communication_style=style,
            job_role=FIXED_JOB_ROLE,
        )
        request = PreSpeechRequest(
            korean_text=FIXED_KOREAN_TEXT,
            counterpart_profile=profile,
            meeting_context=FIXED_MEETING_CONTEXT,
        )
        try:
            result = service.generate_pre_speech(request)
            print(f"\n[숙련도={proficiency}, 소통방식={style}]")
            print(f"  expression: {result.expression}")
            print(f"  reason    : {result.reason}")
        except Exception as exc:  # noqa: BLE001
            print(f"\n[숙련도={proficiency}, 소통방식={style}] 실패: {exc!r}")


def run_speech_feedback_matrix(service: AiService) -> None:
    print("\n" + "=" * 100)
    print("F-03 speech-feedback: 소통방식별 동일 문장 판정 비교")
    print("=" * 100)

    for sentence in FEEDBACK_SENTENCES:
        print(f"\n문장: {sentence!r}")
        for style in STYLES:
            profile = CounterpartProfile(
                proficiency="중급",
                communication_style=style,
                job_role=FIXED_JOB_ROLE,
            )
            request = SpeechFeedbackRequest(
                english_text=sentence,
                recent_messages=[],
                counterpart_profile=profile,
            )
            try:
                result = service.generate_speech_feedback(request)
                print(
                    f"  [소통방식={style}] flagged={result.flagged} "
                    f"type={result.type} alt={result.alternative}"
                )
            except Exception as exc:  # noqa: BLE001
                print(f"  [소통방식={style}] 실패: {exc!r}")


def main() -> None:
    service = AiService()
    run_pre_speech_matrix(service)
    run_speech_feedback_matrix(service)


if __name__ == "__main__":
    main()
