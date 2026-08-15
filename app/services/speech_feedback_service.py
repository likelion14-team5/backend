import hashlib
import re
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models.participant import Participant
from app.models.speech_feedback import SpeechFeedback as SpeechFeedbackModel
from app.schemas.ai import CounterpartProfile
from app.schemas.ai import SpeechFeedbackRequest as AiSpeechFeedbackRequest
from app.schemas.meeting import ParticipantStatus
from app.schemas.speech_feedback import (
    SpeechFeedbackAnalyzeRequest,
    SpeechFeedbackAnalyzeResult,
    SpeechFeedbackDetail,
    SpeechFeedbackListItem,
)
from app.services.ai_service import (
    COMMUNICATION_STYLE_TO_KOREAN,
    PROFICIENCY_TO_KOREAN,
    AiService,
    map_risk_type,
)

NEUTRAL_JOB_ROLE = "회의 참가자"
DUPLICATE_WINDOW = timedelta(seconds=30)
LOW_CONFIDENCE_THRESHOLD = 0.70


def _normalize_transcript(transcript: str) -> str:
    lowered = transcript.strip().lower()
    stripped_punctuation = re.sub(r"[^\w\s]", "", lowered)
    return re.sub(r"\s+", " ", stripped_punctuation).strip()


def _hash_transcript(normalized: str) -> str:
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


class SpeechFeedbackService:
    def __init__(self, db: Session, ai: AiService) -> None:
        self.db = db
        self.ai = ai

    def _resolve_target(
        self, meeting_id: UUID, requester_id: UUID, target_participant_id: UUID | None
    ) -> Participant | None:
        if target_participant_id is not None:
            if target_participant_id == requester_id:
                raise AppError(400, "TARGET_NOT_IN_MEETING", "본인을 대상으로 선택할 수 없습니다.")
            target = self.db.scalar(
                select(Participant).where(
                    Participant.id == target_participant_id,
                    Participant.meeting_id == meeting_id,
                    Participant.status == ParticipantStatus.JOINED.value,
                )
            )
            if target is None:
                raise AppError(
                    400, "TARGET_NOT_IN_MEETING", "같은 회의의 참가자만 선택할 수 있습니다."
                )
            return target
        # 대상을 지정하지 않으면 같은 회의에서 가장 먼저 입장한 다른 참가자를 사용한다 (기존 동작).
        return self.db.scalar(
            select(Participant)
            .where(
                Participant.meeting_id == meeting_id,
                Participant.id != requester_id,
                Participant.status == ParticipantStatus.JOINED.value,
            )
            .order_by(Participant.joined_at, Participant.id)
        )

    @staticmethod
    def _counterpart_profile(target: Participant | None) -> CounterpartProfile:
        if target is None:
            return CounterpartProfile(
                proficiency="중급",
                communication_style="균형적",
                job_role=NEUTRAL_JOB_ROLE,
            )
        return CounterpartProfile(
            proficiency=PROFICIENCY_TO_KOREAN[target.english_proficiency],
            communication_style=COMMUNICATION_STYLE_TO_KOREAN[target.communication_style],
            job_role=target.job_title,
            additional_considerations=target.additional_considerations,
        )

    @staticmethod
    def _to_detail(row: SpeechFeedbackModel) -> SpeechFeedbackDetail:
        return SpeechFeedbackDetail(
            id=row.id,
            detected_text=row.detected_text,
            risk_type=row.risk_type,
            explanation_ko=row.explanation_ko,
            alternative_expression_en=row.alternative_expression_en,
            transcript_may_be_inaccurate=row.transcript_may_be_inaccurate,
            display_state=row.display_state,
        )

    @staticmethod
    def _to_list_item(row: SpeechFeedbackModel) -> SpeechFeedbackListItem:
        return SpeechFeedbackListItem(
            id=row.id,
            detected_text=row.detected_text,
            risk_type=row.risk_type,
            explanation_ko=row.explanation_ko,
            alternative_expression_en=row.alternative_expression_en,
            transcript_may_be_inaccurate=row.transcript_may_be_inaccurate,
            display_state=row.display_state,
            created_at=row.created_at,
            dismissed_at=row.dismissed_at,
        )

    def analyze(
        self,
        meeting_id: UUID,
        participant: Participant,
        request: SpeechFeedbackAnalyzeRequest,
    ) -> SpeechFeedbackAnalyzeResult:
        if not participant.voice_analysis_consent or not participant.voice_analysis_enabled:
            raise AppError(
                403, "VOICE_CONSENT_REQUIRED", "음성 분석 동의 또는 활성화가 필요합니다."
            )

        target = self._resolve_target(meeting_id, participant.id, request.target_participant_id)
        ai_result = self.ai.generate_speech_feedback(
            AiSpeechFeedbackRequest(
                english_text=request.transcript,
                recent_messages=[request.recent_context] if request.recent_context else [],
                counterpart_profile=self._counterpart_profile(target),
            )
        )
        if not ai_result.flagged or not ai_result.alternative:
            # alternative가 비어 있으면 DB NOT NULL 제약을 만족할 수 없는 신뢰할 수 없는 응답이므로
            # 기존 정책("애매하면 관대하게")에 맞춰 위험 없음으로 처리한다.
            return SpeechFeedbackAnalyzeResult(
                risk_detected=False, feedback=None, suppressed_duplicate=False
            )

        risk_type = map_risk_type(ai_result.type)
        normalized = _normalize_transcript(request.transcript)
        text_hash = _hash_transcript(normalized)
        cutoff = datetime.now(UTC) - DUPLICATE_WINDOW

        duplicate = self.db.scalar(
            select(SpeechFeedbackModel)
            .where(
                SpeechFeedbackModel.participant_id == participant.id,
                SpeechFeedbackModel.normalized_text_hash == text_hash,
                SpeechFeedbackModel.risk_type == risk_type,
                SpeechFeedbackModel.created_at >= cutoff,
            )
            .order_by(SpeechFeedbackModel.created_at.desc())
        )
        if duplicate is not None:
            return SpeechFeedbackAnalyzeResult(
                risk_detected=True,
                feedback=self._to_detail(duplicate),
                suppressed_duplicate=True,
            )

        row = SpeechFeedbackModel(
            meeting_id=meeting_id,
            participant_id=participant.id,
            detected_text=request.transcript,
            normalized_text_hash=text_hash,
            stt_confidence=request.stt_confidence,
            transcript_may_be_inaccurate=(
                request.stt_confidence is not None
                and request.stt_confidence < LOW_CONFIDENCE_THRESHOLD
            ),
            risk_type=risk_type,
            explanation_ko=ai_result.reason,
            alternative_expression_en=ai_result.alternative,
            display_state="VISIBLE",
        )
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return SpeechFeedbackAnalyzeResult(
            risk_detected=True,
            feedback=self._to_detail(row),
            suppressed_duplicate=False,
        )

    def list(self, meeting_id: UUID, participant_id: UUID) -> list[SpeechFeedbackListItem]:
        rows = self.db.scalars(
            select(SpeechFeedbackModel)
            .where(
                SpeechFeedbackModel.meeting_id == meeting_id,
                SpeechFeedbackModel.participant_id == participant_id,
            )
            .order_by(SpeechFeedbackModel.created_at.desc())
        )
        return [self._to_list_item(row) for row in rows]

    def dismiss(
        self, meeting_id: UUID, participant_id: UUID, feedback_id: UUID
    ) -> SpeechFeedbackListItem:
        row = self.db.scalar(
            select(SpeechFeedbackModel).where(
                SpeechFeedbackModel.id == feedback_id,
                SpeechFeedbackModel.meeting_id == meeting_id,
                SpeechFeedbackModel.participant_id == participant_id,
            )
        )
        if row is None:
            raise AppError(404, "FEEDBACK_NOT_FOUND", "피드백을 찾을 수 없습니다.")
        row.display_state = "DISMISSED"
        row.dismissed_at = datetime.now(UTC)
        self.db.commit()
        self.db.refresh(row)
        return self._to_list_item(row)
