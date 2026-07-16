from typing import Optional
from pydantic import BaseModel


class RFQBrief(BaseModel):
    rfq_id_and_org: Optional[str] = None
    quote_due_date: Optional[str] = None
    delivery_deadline: Optional[str] = None
    part_number_rev: Optional[str] = None
    material_and_grade: Optional[str] = None
    dimensions_raw: Optional[str] = None
    tolerances_stated: Optional[str] = None
    finishing_secondary: Optional[str] = None
    qty_tiers: Optional[list] = None
    incoterms_fob: Optional[str] = None
    target_price: Optional[str] = None
    legal_penalties: Optional[str] = None
    qa_certs_required: Optional[str] = None
    competing_vendors: Optional[str] = None
    missing_or_unclear: Optional[str] = None
    estimator_summary: Optional[str] = None


class RFQBriefV2(RFQBrief):
    """Extended brief returned by the Agno agent extractor.
    Backward compatible — adds new fields, does not remove existing ones."""
    document_type: str = "unknown"
    confidence_score: float = 0.0
    clarification_questions: list[str] = []
    ready_to_quote: bool = False
