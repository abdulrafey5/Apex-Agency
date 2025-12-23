#!/usr/bin/env python3
"""
Seed core knowledge base content (agent library + SOPs) into Postgres semantic_memory.
Uses existing embedding pipeline (OpenAI first, Ollama fallback).

Run:
    PYTHONPATH=./app python -m scripts.seed_kb
"""
import os
import logging
from pathlib import Path
from typing import Dict, Any

from dotenv import load_dotenv

from services.embedding_service import generate_embedding
from services.db_service import get_db_service


# ---------------------------------------------------------------------------
# Seed content
# ---------------------------------------------------------------------------

AGENT_LIBRARY_DOC = """Title: Core Departments, Leaders, and Specialized Agents

Marketing Department
- Department Lead: Maria (Director of Marketing)
- Agents:
  - Sofie (Social Media Specialist)
  - Adria (Advertising Specialist)
  - Colby (Copywriting Specialist)
  - Coco (Content Creation Specialist)
  - Vienna (Video Production Specialist)
  - Neomi (Newsletter Specialist)
  - Inaya (Influencer Relations Specialist)

Sales Department
- Teams: Scrapers, Dialers, Cold Outreach (text/email), Appointment Setters, Closers

Product/Service Department
- Fulfillment
- Research & Development
- Product/Service Strategy

Customer Service Department
- Inbound call, Inbound text, Inbound email

Technology Department
- Web team, System Integrations, Custom Coding & Development

Partnerships Department
- Strategic Outreach

Finance Department
- Reporting & Analysis, Forecasting, Budgeting

Human Resources (HR) Department
- Recruitment & Onboarding, Compliance & Labor Law, Performance Management, Learning & Development, Culture & Engagement

Legal & Compliance Department
- Contract Management, Regulatory Compliance, Risk Management, Corporate Governance, Data Privacy

Business Intelligence Department
- KPI Monitoring & Data Analysis, Dashboarding, Market Intelligence, Customer Insights, Competitive Analysis, Funnel Analysis

Board & C-Suite
- Board of Directors: oversight, governance, strategic approvals.
- C-Suite: CEO, COO, CFO, CMO, CTO responsible for company-wide strategy and execution.
"""


SOP_IDEA_VETTING = """Title: SOP — Vetting Business Ideas

1) Intake & Clarify
   - Gather problem statement, audience, pain points, constraints, success criteria.
2) Market & Competitor Scan
   - TAM/SAM/SOM sketch, competitor list, differentiation summary.
3) Customer & Channel Fit
   - ICP definition, expected channels (paid, organic, partnerships), CAC/LTV assumptions.
4) Feasibility & Ops
   - Tech feasibility, delivery/fulfillment risks, regulatory flags, data/privacy considerations.
5) Financial Quickview
   - Pricing hypothesis, unit economics sketch, budget envelope, timeline/milestones.
6) Risk & Mitigation
   - Top 3–5 risks with mitigations; go/no-go flags.
7) Decision & Next Steps
   - Recommendation (go / revise / no-go), info gaps, next experiments.

Meta:
- Revisit quarterly or when major market shifts occur.
- Keep a log of accepted/rejected ideas with rationale.
"""


SOP_ASYNC_COMMS = """Title: SOP — Asynchronous Inter-Agent Communication

Principles:
- Default async; keep context in shared threads; link artifacts; avoid blocking.

Workflow:
- Create a thread per task with: objective, owner, due date, status, links.
- Post updates with: what changed, blockers, decisions, next step + due date.
- Use tags: [BLOCKED], [REVIEW], [DONE], [RISK], [DECISION].

Handoffs:
- Summarize state + links; note pending decisions; tag the receiver.
- Escalate if blocked >24h or risks to timeline/quality.

Cadence:
- Daily async standup: yesterday/today/blockers.
- Weekly summary per department; monthly rollup for leadership.
"""


SOP_SELF_REVIEW = """Title: SOP — Self-Review

Checklist before marking tasks done:
- Requirements met? Scope creep noted?
- Quality: clarity, accuracy, tone/brand, compliance.
- Evidence: links to data, drafts, code, assets.
- Tests/checks run? Peer review needed?
- Risks noted? Follow-ups created?

Output pattern:
- Summary (3-5 bullets), Evidence links, Risks/Issues, Next steps.
"""


SOP_AUTONOMY = """Title: SOP — Autonomy & New Tasks

Principles:
- Bias to action with guardrails; escalate when uncertain.
- Stay within role/authority; log new tasks with owner/due date.

When to self-create a task:
- Clear dependency or follow-up required.
- Detected risk that needs mitigation.
- Small improvement with clear benefit and low risk.

When to escalate/ask:
- Ambiguous goals, high-risk changes, budget/brand/legal implications.

Logging:
- Each new task: objective, owner, due date, status, links; tag [NEW] until acknowledged.
"""


SOP_STAGE_0_TO_4 = """Title: SOP — Stage 0–4 Content & Promo

Stage 0–3 Example Task:
- "Prepare a new post on the Mindfulness section of my blog, along with a post on X about the new article, and a Facebook ad with a static image to promote it."
- Deliverables: Blog post draft + image guidance; X post (<200 chars + hashtags); FB ad copy + static image spec; suggested targeting/budget; links to assets; QA checklist.
- Review: Maria (Marketing lead) approves before publish/launch.
- Handoffs: Sofie (Social), Adria (Ads), Colby (Copy), Coco/Vienna (Creative) as needed.

Stage 4 Recurring Task (Daily 9am):
- "Create a new post for the Sleep section of the blog every day at 9am and send word about it through all free channels."
- Cadence: Daily 09:00 local time; queue posts 3 days ahead.
- Channels: Blog publish + X + LinkedIn + Instagram (organic) + Newsletter blurb when relevant.
- Steps:
  1) Draft: Topic selection (Sleep), outline, write, light SEO, CTA.
  2) Creative: Static image guidance; optional short clip.
  3) Social: Schedule X/LinkedIn/Instagram posts aligned to publish time; add UTM links.
  4) QA: Links, images, tags/hashtags, accessibility (alt text), approvals.
  5) Publish & Monitor: Confirm publish; check early metrics; log performance.
- Owners: Content (Coco/Colby), Social (Sofie), QA/Approval (Maria).
"""


SEED_DOCS = [
    ("agent_library_v1", "agent_library", AGENT_LIBRARY_DOC, {"category": "agent_library", "version": "1.0"}),
    ("sop_idea_vetting_v1", "sop", SOP_IDEA_VETTING, {"category": "sop", "topic": "idea_vetting", "version": "1.0"}),
    ("sop_async_comms_v1", "sop", SOP_ASYNC_COMMS, {"category": "sop", "topic": "async_comms", "version": "1.0"}),
    ("sop_self_review_v1", "sop", SOP_SELF_REVIEW, {"category": "sop", "topic": "self_review", "version": "1.0"}),
    ("sop_autonomy_v1", "sop", SOP_AUTONOMY, {"category": "sop", "topic": "autonomy", "version": "1.0"}),
    ("sop_stage_0_4_v1", "sop", SOP_STAGE_0_TO_4, {"category": "sop", "topic": "stage_0_4", "version": "1.0"}),
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def index_doc(db, doc_id: str, source_type: str, text: str, metadata: Dict[str, Any]) -> None:
    emb = generate_embedding(text)
    if not emb:
        logging.error(f"Embedding failed for {doc_id}")
        return
    db.upsert_semantic_memory(
        content=text,
        embedding=emb,
        metadata=metadata,
        source_type=source_type,
        source_id=doc_id,
    )
    logging.info(f"Seeded {doc_id} ({source_type})")


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    # Load .env
    root = Path(__file__).resolve().parent.parent
    env_path = root / ".env"
    if env_path.exists():
        load_dotenv(env_path)
    else:
        logging.warning(f".env not found at {env_path} (continuing if env vars set)")

    db = get_db_service()

    for doc_id, source_type, text, metadata in SEED_DOCS:
        index_doc(db, doc_id, source_type, text, metadata)

    logging.info("✅ Seeding complete")


if __name__ == "__main__":
    main()

