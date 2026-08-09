import json
import logging

from openai import OpenAI

from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.schemas.ai import (
    CounterpartProfile,
    PreSpeechRequest,
    PreSpeechResult,
    SpeechFeedbackRequest,
    SpeechFeedbackResult,
)

logger = logging.getLogger(__name__)

# ---- 시스템 프롬프트 (고정) ----

NO_GENERALIZATION_PRINCIPLE = (
    '원칙: 특정 국가나 인종에 대한 일반화(예: "OO 국가 사람들은 ~하다", "OO 문화권은 ~를 선호한다")는 '
    "어떤 경우에도 사용하지 마십시오. 판단 근거는 오직 이번 요청에 주어진 상대방의 영어 숙련도, "
    "선호 소통 방식, 직무, 맥락 정보에만 두십시오."
)

PRE_SPEECH_SYSTEM_PROMPT = f"""당신은 글로벌 화상회의에서 한국인 사용자가 영어로 자연스럽게 발언할 수 있도록 돕는 어시스턴트입니다.

역할:
- 사용자가 입력한 한국어 문장의 "의도"를 파악하여, 직역이 아닌 자연스러운 업무용 영어 표현으로 재구성합니다.
- 반드시 아래 JSON 스키마로만 응답하십시오. 다른 설명, 마크다운, 코드블록을 포함하지 마십시오.

출력 스키마:
{{"expression": "<추천 영어 표현>", "reason": "<한국어 2문장 이내의 추천 이유>"}}

규칙:
1. expression은 실제 회의에서 바로 말할 수 있는 자연스러운 구어체 업무 영어여야 합니다. 단어 대 단어 직역은 금지하며, 화자의 의도와 뉘앙스는 유지하십시오.
2. 상대방의 영어 숙련도가 "초급"이면 쉬운 단어와 짧고 단순한 문장 구조를 사용하고, 관용어(idiom)는 사용하지 마십시오. "중급"이면 표준적인 업무 어휘를 사용하십시오. "고급"이면 보다 정교하고 자연스러운 표현을 사용해도 됩니다.
3. 상대방의 선호 소통 방식이 "직접적"이면 요점을 명확하고 간결하게, "완곡한"이면 쿠션어와 부드러운 표현을 더 사용하고, "균형적"이면 그 중간 톤을 사용하십시오.
4. 상대방의 직무, 회의 맥락, 추가 고려사항을 반영하여 전문 용어 사용 여부와 격식을 조정하십시오.
5. reason은 한국어 2문장 이내로 간결하게 작성하십시오.
6. {NO_GENERALIZATION_PRINCIPLE}
7. 반드시 유효한 JSON 객체 하나만 출력하십시오.

예시:
[예시 1] 숙련도=초급, 소통방식=완곡한, 직무=Sales, 맥락=일정 조율
입력 문장: "이 일정은 솔직히 어려울 것 같아요"
출력: {{"expression": "I think this timeline might be a bit tight for us.", "reason": "초급 숙련도에 맞춰 쉬운 단어를 쓰고, 완곡한 방식을 반영해 우려를 부드럽게 전달했습니다."}}

[예시 2] 숙련도=고급, 소통방식=직접적, 직무=Engineering Lead, 맥락=마감 논의
입력 문장: "이 부분은 반드시 이번 주 안에 끝내야 합니다"
출력: {{"expression": "We need to have this wrapped up by the end of this week.", "reason": "직접적 소통을 선호하는 상대에게 맞춰 요점을 명확하고 간결하게 전달했습니다."}}

[예시 3] 숙련도=중급, 소통방식=균형적, 직무=Product Manager, 맥락=의사결정 회의
입력 문장: "다른 팀 의견도 들어보면 좋을 것 같아요"
출력: {{"expression": "It might be worth getting input from the other team as well.", "reason": "중급 수준의 표준 어휘와 균형적인 톤으로 제안 형태로 부드럽게 전달했습니다."}}"""


SPEECH_FEEDBACK_SYSTEM_PROMPT = f"""당신은 글로벌 화상회의 중 한국인 사용자가 방금 한 영어 발언이 상대방에게 오해나 마찰을 일으킬 가능성이 있는지 점검하는 어시스턴트입니다.

역할:
- 사용자의 영어 발언, 최근 대화 맥락, 상대방 프로필을 바탕으로 오해나 불필요한 마찰을 일으킬 수 있는 표현이 있는지 분석합니다.
- 반드시 아래 JSON 스키마로만 응답하십시오. 다른 설명, 마크다운, 코드블록을 포함하지 마십시오.

출력 스키마:
{{"flagged": <true|false>, "original_text": "<입력된 영어 발언 그대로>", "type": "<5개 타입 중 하나 또는 null>", "reason": "<한국어 설명 또는 null>", "alternative": "<대안 영어 표현 또는 null>"}}

type은 반드시 다음 5개 중 하나여야 합니다:
- "직접적 거절"
- "공격적 표현"
- "모호한 표현"
- "관용어/속어"
- "고려사항 충돌"

규칙:
1. 대부분의 평범한 업무 발언은 문제가 없습니다. 억지로 지적하지 말고, 오해 가능성이 낮으면 flagged를 false로 하고 type/reason/alternative는 모두 null로 하십시오.
2. 오해 가능성이 있다고 판단될 때만 flagged를 true로 하고, 가장 적합한 type 하나만 선택하십시오.
3. reason은 "이 표현은 잘못되었다/틀렸다"처럼 단정하지 말고, "~로 들릴 수 있어요"처럼 가능성과 청자 관점 중심의 한국어로 작성하십시오.
4. alternative에는 같은 의도를 유지하면서 오해 가능성을 줄인 대안 영어 표현을 제시하십시오. flagged가 false이면 alternative는 반드시 null입니다.
5. original_text에는 입력된 영어 발언을 그대로 넣으십시오.
6. {NO_GENERALIZATION_PRINCIPLE}
7. 반드시 유효한 JSON 객체 하나만 출력하십시오.

예시:
[예시 1 - 걸림]
발언: "Let's table this for now."
출력: {{"flagged": true, "original_text": "Let's table this for now.", "type": "관용어/속어", "reason": "관용 표현이라 상대방이 문자 그대로의 뜻으로 오해하거나 의미를 파악하지 못할 수 있어요.", "alternative": "Let's put this on hold for now."}}

[예시 2 - 걸림] 상대방 소통방식=완곡한
발언: "That schedule is impossible."
출력: {{"flagged": true, "original_text": "That schedule is impossible.", "type": "직접적 거절", "reason": "완곡한 소통을 선호하는 상대에게는 다소 단정적이고 강하게 들릴 수 있어요.", "alternative": "I'm a little concerned this schedule might be hard to hit."}}

[예시 3 - 안 걸림]
발언: "Could you share the file when you get a chance?"
출력: {{"flagged": false, "original_text": "Could you share the file when you get a chance?", "type": null, "reason": null, "alternative": null}}"""


ALLOWED_FEEDBACK_TYPES = {
    "직접적 거절",
    "공격적 표현",
    "모호한 표현",
    "관용어/속어",
    "고려사항 충돌",
}


def _profile_block(profile: CounterpartProfile) -> str:
    lines = [
        "[상대방 프로필]",
        f"- 영어 숙련도: {profile.proficiency}",
        f"- 선호 소통 방식: {profile.communication_style}",
        f"- 직무: {profile.job_role}",
    ]
    if profile.additional_considerations:
        lines.append(f"- 추가 고려사항: {profile.additional_considerations}")
    return "\n".join(lines)


def _build_pre_speech_user_prompt(request: PreSpeechRequest) -> str:
    return (
        f"[한국어 문장]\n{request.korean_text}\n\n"
        f"{_profile_block(request.counterpart_profile)}\n\n"
        f"[회의 맥락]\n{request.meeting_context}\n\n"
        "위 정보를 반영하여 출력 스키마에 맞는 JSON으로만 응답하십시오."
    )


def _build_speech_feedback_user_prompt(request: SpeechFeedbackRequest) -> str:
    recent = "\n".join(f"- {message}" for message in request.recent_messages) or "(없음)"
    return (
        f"[분석할 영어 발언]\n{request.english_text}\n\n"
        f"[최근 대화 (시간순, 최대 5개)]\n{recent}\n\n"
        f"{_profile_block(request.counterpart_profile)}\n\n"
        "위 정보를 반영하여 출력 스키마에 맞는 JSON으로만 응답하십시오."
    )


def _sanitize_feedback(data: dict, original_text: str) -> SpeechFeedbackResult:
    flagged = bool(data.get("flagged"))
    type_ = data.get("type")
    reason = data.get("reason")
    alternative = data.get("alternative")

    if flagged and (type_ not in ALLOWED_FEEDBACK_TYPES or not reason):
        # type이 허용 목록 밖이거나 reason이 비어 있으면 신뢰할 수 없는 응답으로 보고 안전하게 통과 처리한다.
        flagged = False

    if not flagged:
        type_ = None
        reason = None
        alternative = None

    return SpeechFeedbackResult(
        flagged=flagged,
        original_text=original_text,
        type=type_,
        reason=reason,
        alternative=alternative,
    )


class AiService:
    """OpenAI 기반 발화 보조 기능을 제공하는 동기식 서비스입니다.

    DailyService와 동일하게 클라이언트 생성/오류 변환을 이 클래스 안에 캡슐화하고,
    실패는 항상 AppError(502)로 변환해 다른 서비스와 같은 오류 응답 규격을 따릅니다.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._client: OpenAI | None = None

    def _client_or_error(self, error_code: str) -> OpenAI:
        api_key = self.settings.openai_api_key.get_secret_value()
        if not api_key:
            raise AppError(
                status_code=502,
                code=error_code,
                message="AI 서비스 설정을 확인할 수 없습니다.",
            )
        if self._client is None:
            self._client = OpenAI(
                api_key=api_key,
                timeout=self.settings.openai_request_timeout_seconds,
            )
        return self._client

    def _create_json_completion(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        error_code: str,
    ) -> dict:
        client = self._client_or_error(error_code)
        try:
            completion = client.chat.completions.create(
                model=self.settings.openai_model,
                response_format={"type": "json_object"},
                temperature=0.3,
                max_tokens=400,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            )
        except Exception as exc:
            logger.warning(
                "OpenAI request failed operation=%s type=%s",
                error_code,
                type(exc).__name__,
            )
            raise AppError(status_code=502, code=error_code, message="AI 응답 생성에 실패했습니다.") from exc

        content = completion.choices[0].message.content
        try:
            return json.loads(content)
        except (TypeError, ValueError) as exc:
            logger.warning("OpenAI JSON parse failed operation=%s", error_code)
            raise AppError(status_code=502, code=error_code, message="AI 응답 형식을 확인하지 못했습니다.") from exc

    def generate_pre_speech(self, request: PreSpeechRequest) -> PreSpeechResult:
        data = self._create_json_completion(
            system_prompt=PRE_SPEECH_SYSTEM_PROMPT,
            user_prompt=_build_pre_speech_user_prompt(request),
            error_code="AI_PRE_SPEECH_FAILED",
        )
        try:
            return PreSpeechResult(expression=str(data["expression"]), reason=str(data["reason"]))
        except (KeyError, TypeError) as exc:
            raise AppError(
                status_code=502,
                code="AI_PRE_SPEECH_FAILED",
                message="AI 응답 형식을 확인하지 못했습니다.",
            ) from exc

    def generate_speech_feedback(self, request: SpeechFeedbackRequest) -> SpeechFeedbackResult:
        data = self._create_json_completion(
            system_prompt=SPEECH_FEEDBACK_SYSTEM_PROMPT,
            user_prompt=_build_speech_feedback_user_prompt(request),
            error_code="AI_SPEECH_FEEDBACK_FAILED",
        )
        return _sanitize_feedback(data, request.english_text)


def get_ai_service() -> AiService:
    return AiService()
