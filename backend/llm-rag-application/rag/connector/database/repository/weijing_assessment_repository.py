from __future__ import annotations

import uuid

from sqlalchemy import select

from rag.connector.database.base import SessionLocal
from rag.connector.database.models.weijing_assessment_model import WeijingAssessmentModel
from rag.weijing.models import WeijingAssessment


class WeijingAssessmentNotFoundError(LookupError):
    pass


class WeijingAssessmentRepository:
    def save(self, assessment: WeijingAssessment) -> WeijingAssessment:
        record = WeijingAssessmentModel(
            record_id=str(uuid.uuid4()),
            assessment_id=assessment.assessment_id,
            user_id=assessment.user_id,
            organization_id=assessment.organization_id,
            report_id=assessment.report.report_id,
            report_sha256=assessment.report.file_sha256,
            revision=assessment.revision,
            report=assessment.report.model_dump(mode="json"),
            plan=assessment.plan.model_dump(mode="json"),
            rendered_markdown=assessment.rendered_markdown,
            created_at=assessment.created_at,
        )
        with SessionLocal.begin() as session:
            session.add(record)
        return assessment

    def get(self, assessment_id: str, user_id: str, organization_id: str | None) -> WeijingAssessment:
        organization_filter = (
            WeijingAssessmentModel.organization_id.is_(None)
            if organization_id is None
            else WeijingAssessmentModel.organization_id == organization_id
        )
        with SessionLocal() as session:
            record = session.scalar(
                select(WeijingAssessmentModel)
                .where(
                    WeijingAssessmentModel.assessment_id == assessment_id,
                    WeijingAssessmentModel.user_id == user_id,
                    organization_filter,
                )
                .order_by(WeijingAssessmentModel.revision.desc())
                .limit(1)
            )
            if record is None:
                raise WeijingAssessmentNotFoundError(assessment_id)
            return _to_assessment(record)

    def latest_for_user(self, user_id: str, organization_id: str | None) -> WeijingAssessment | None:
        organization_filter = (
            WeijingAssessmentModel.organization_id.is_(None)
            if organization_id is None
            else WeijingAssessmentModel.organization_id == organization_id
        )
        with SessionLocal() as session:
            record = session.scalar(
                select(WeijingAssessmentModel)
                .where(
                    WeijingAssessmentModel.user_id == user_id,
                    organization_filter,
                )
                .order_by(
                    WeijingAssessmentModel.created_at.desc(),
                    WeijingAssessmentModel.revision.desc(),
                )
                .limit(1)
            )
            return None if record is None else _to_assessment(record)


def _to_assessment(record: WeijingAssessmentModel) -> WeijingAssessment:
    return WeijingAssessment.model_validate({
        "assessment_id": record.assessment_id,
        "user_id": record.user_id,
        "organization_id": record.organization_id,
        "revision": record.revision,
        "report": record.report,
        "plan": record.plan,
        "rendered_markdown": record.rendered_markdown,
        "created_at": record.created_at,
    })
