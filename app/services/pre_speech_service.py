from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models.participant import Participant
from app.models.pre_speech_request import PreSpeechRequest as PreSpeechRequestModel
from app.schemas.ai import CounterpartProfile
from app.schemas.ai import PreSpeechRequest as AiPreSpeechRequest
from app.schemas.meeting import ParticipantStatus
from app.schemas.pre_speech import PreSpeechCreateRequest, PreSpeechResult
from app.services.ai_service import (
    COMMUNICATION_STYLE_TO_KOREAN,
    PROFICIENCY_TO_KOREAN,
    AiService,
)

NEUTRAL_JOB_ROLE = "회의 참가자"


class PreSpeechService:
    def __init__(self, db: Session, ai: AiService) -> None:
        self.db = db
        self.ai = ai

    def _resolve_target(
        self, meeting_id: UUID, requester_id: UUID, target_participant_id: UUID | None
    ) -> Participant | None:
        if target_participant_id is None:
            return None
        if target_participant_id == requester_id:
            raise AppError(422, "SELF_TARGET_NOT_ALLOWED", "본인을 대상으로 선택할 수 없습니다.")
        target = self.db.scalar(
            select(Participant).where(
                Participant.id == target_participant_id,
                Participant.meeting_id == meeting_id,
                Participant.status == ParticipantStatus.JOINED.value,
            )
        )
        if target is None:
            raise AppError(
                404, "TARGET_PARTICIPANT_NOT_FOUND", "같은 회의의 참가자만 선택할 수 있습니다."
            )
        return target

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
    def _to_result(row: PreSpeechRequestModel) -> PreSpeechResult:
        return PreSpeechResult(
            id=row.id,
            input_ko=row.input_ko,
            target_participant_id=row.target_participant_id,
            meeting_context=row.meeting_context,
            recommended_expression_en=row.recommended_expression_en,
            recommendation_reason_ko=row.recommendation_reason_ko,
            parent_request_id=row.parent_request_id,
            created_at=row.created_at,
        )

    def _generate_and_save(
        self,
        *,
        meeting_id: UUID,
        requester_id: UUID,
        input_ko: str,
        target_participant_id: UUID | None,
        meeting_context: str | None,
        parent_request_id: UUID | None,
    ) -> PreSpeechResult:
        target = self._resolve_target(meeting_id, requester_id, target_participant_id)
        ai_result = self.ai.generate_pre_speech(
            AiPreSpeechRequest(
                korean_text=input_ko,
                counterpart_profile=self._counterpart_profile(target),
                meeting_context=meeting_context or "일반 업무 회의",
            )
        )
        row = PreSpeechRequestModel(
            meeting_id=meeting_id,
            requester_participant_id=requester_id,
            target_participant_id=target_participant_id,
            parent_request_id=parent_request_id,
            input_ko=input_ko,
            meeting_context=meeting_context,
            recommended_expression_en=ai_result.expression,
            recommendation_reason_ko=ai_result.reason,
        )
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return self._to_result(row)

    def create(
        self, meeting_id: UUID, requester_id: UUID, request: PreSpeechCreateRequest
    ) -> PreSpeechResult:
        return self._generate_and_save(
            meeting_id=meeting_id,
            requester_id=requester_id,
            input_ko=request.input_ko,
            target_participant_id=request.target_participant_id,
            meeting_context=request.meeting_context,
            parent_request_id=None,
        )

    def get(
        self, meeting_id: UUID, requester_id: UUID, request_id: UUID
    ) -> PreSpeechResult:
        row = self.db.scalar(
            select(PreSpeechRequestModel).where(
                PreSpeechRequestModel.id == request_id,
                PreSpeechRequestModel.meeting_id == meeting_id,
                PreSpeechRequestModel.requester_participant_id == requester_id,
            )
        )
        if row is None:
            raise AppError(404, "PRE_SPEECH_NOT_FOUND", "요청을 찾을 수 없습니다.")
        return self._to_result(row)

    def regenerate(
        self, meeting_id: UUID, requester_id: UUID, request_id: UUID
    ) -> PreSpeechResult:
        original = self.db.scalar(
            select(PreSpeechRequestModel).where(
                PreSpeechRequestModel.id == request_id,
                PreSpeechRequestModel.meeting_id == meeting_id,
                PreSpeechRequestModel.requester_participant_id == requester_id,
            )
        )
        if original is None:
            raise AppError(404, "PRE_SPEECH_NOT_FOUND", "요청을 찾을 수 없습니다.")
        return self._generate_and_save(
            meeting_id=meeting_id,
            requester_id=requester_id,
            input_ko=original.input_ko,
            target_participant_id=original.target_participant_id,
            meeting_context=original.meeting_context,
            parent_request_id=original.id,
        )
