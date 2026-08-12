"""수동 QA 스크립트: F-02/F-03 실제 응답 시간을 측정한다.

pytest가 아니라 실제 OpenAI API를 호출하는 수동 점검용 스크립트다.

실행:
    .venv\\Scripts\\python.exe tests\\manual_qa\\latency_check.py
"""

import statistics
import time

from app.schemas.ai import CounterpartProfile, PreSpeechRequest, SpeechFeedbackRequest
from app.services.ai_service import AiService

REPEATS = 5

PROFILE = CounterpartProfile(
    proficiency="중급",
    communication_style="균형적",
    job_role="Product Manager",
)


def timed(label: str, fn) -> float:
    start = time.perf_counter()
    fn()
    elapsed = time.perf_counter() - start
    print(f"  {label}: {elapsed:.2f}s")
    return elapsed


def main() -> None:
    service = AiService()

    pre_speech_request = PreSpeechRequest(
        korean_text="이 일정은 솔직히 어려울 것 같아요",
        counterpart_profile=PROFILE,
        meeting_context="다음 주 마감인 프로젝트 일정 조율 회의",
    )
    feedback_request = SpeechFeedbackRequest(
        english_text="That schedule is impossible.",
        recent_messages=[],
        counterpart_profile=PROFILE,
    )

    print(f"F-02 pre-speech x{REPEATS}")
    pre_speech_times = [
        timed(f"run {i + 1}", lambda: service.generate_pre_speech(pre_speech_request))
        for i in range(REPEATS)
    ]

    print(f"\nF-03 speech-feedback x{REPEATS}")
    feedback_times = [
        timed(f"run {i + 1}", lambda: service.generate_speech_feedback(feedback_request))
        for i in range(REPEATS)
    ]

    print("\n" + "=" * 60)
    print(
        f"F-02 평균: {statistics.mean(pre_speech_times):.2f}s "
        f"(최소 {min(pre_speech_times):.2f}s / 최대 {max(pre_speech_times):.2f}s)"
    )
    print(
        f"F-03 평균: {statistics.mean(feedback_times):.2f}s "
        f"(최소 {min(feedback_times):.2f}s / 최대 {max(feedback_times):.2f}s)"
    )


if __name__ == "__main__":
    main()
