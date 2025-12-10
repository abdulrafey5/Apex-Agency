#!/usr/bin/env python3
"""
Script to vectorize the Marketing Department document.
Run this to populate the vector store with agent/role information.
"""

# CRITICAL: Load .env BEFORE any other imports
import os
import sys
from pathlib import Path

# Add parent directory to path FIRST
script_dir = os.path.dirname(os.path.abspath(__file__))
app_dir = os.path.dirname(script_dir)
sys.path.insert(0, app_dir)

# Load .env using python-dotenv (standard library approach)
from dotenv import load_dotenv

# Load .env from app directory
env_path = Path(app_dir) / ".env"
print(f"[DEBUG] Script starting - looking for .env at: {env_path}")
print(f"[DEBUG] Script dir: {script_dir}, App dir: {app_dir}")
print(f"[DEBUG] Current working directory: {os.getcwd()}")

if env_path.exists():
    print(f"[DEBUG] Found .env file, loading with load_dotenv()...")
    load_dotenv(env_path)
    print(f"[DEBUG] Loaded .env - DB_HOST={os.getenv('DB_HOST', 'NOT_SET')}")
    print(f"[DEBUG] DB_USER={os.getenv('DB_USER', 'NOT_SET')}")
    print(f"[DEBUG] DB_PASSWORD={'***' if os.getenv('DB_PASSWORD') else 'NOT_SET'}")
else:
    print(f"[ERROR] .env file NOT FOUND at {env_path}")
    sys.exit(1)

# NOW configure logging and import services
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Final verification
db_host = os.getenv("DB_HOST")
db_user = os.getenv("DB_USER")
db_password = os.getenv("DB_PASSWORD")

if not db_host or not db_user or not db_password:
    print(f"[ERROR] Missing required database credentials after .env load!")
    print(f"[ERROR] DB_HOST={db_host}, DB_USER={db_user}, DB_PASSWORD={'***' if db_password else 'NOT_SET'}")
    print(f"[ERROR] Cannot proceed - database will fail to connect")
    sys.exit(1)

print(f"[DEBUG] Environment ready - DB_HOST={db_host}, DB_USER={db_user}")

# NOW import services (after .env is loaded)
from services.document_ingestion_service import get_ingestion_service

# Marketing Department document (from client)
MARKETING_DEPARTMENT_DOC = """department:
  name: Marketing Department
  manager:
    name: Maria
    title: Director of Marketing
    responsibilities:
      - Oversee all marketing activities and strategy execution
      - Review and approve all outbound creative and communications
      - Provide feedback before final publication or automation
      - Maintain alignment with brand standards and company goals
    communication_protocol:
      - All agents must submit drafts, campaigns, or creative concepts to Maria for review
      - Maria provides feedback or revisions within the same workflow thread
      - No agent may activate, post, or publish content until Maria has approved the final version
      - Approved deliverables should be documented in shared storage (e.g., Notion or Drive)

  general_guidelines:
    purpose: >
      The Marketing Department manages awareness, engagement, and brand growth across all channels.
      Agents work collaboratively under the direction of the Marketing Manager (Maria).
    tone_of_voice: >
      Consistent with brand values: clear, positive, and credible.
    review_policy: >
      All outward-facing materials (ads, posts, emails, videos, influencer collaborations)
      must be approved by Maria before launch.
    tool_usage_rules:
      - Tools that directly publish, post, or spend budget require prior approval from Maria.
      - Logging of communication and approvals is required. 

  communication:
    internal_channels:
      - [insert communication method]
    reporting:
      - Agents send summaries of progress and feedback requests to Maria at the end of each task cycle.
      - Maria consolidates updates from its Agents, responds to requests for feedback, and when the work product is deemed sufficient then gives the results the CEA. 

  agents:
    - name: Sofie
      role: Social Media Specialist
      responsibilities:
        - Plan and schedule posts across social platforms
        - Monitor engagement and audience feedback
        - Coordinate post timing with Adria (Advertising)
        - Submit weekly content calendars to Maria for approval
      tools:
        - Write to Storage and Memory
        - [Insert Tools Later]

    - name: Adria
      role: Advertising Specialist
      responsibilities:
        - Manage paid ad campaigns (Google, Meta, TikTok, Outbrain)
        - Analyze performance and optimize creative sets
        - Align targeting with Sofie (Social Media) and Colby (Copywriting)
        - Submit ad copy, visuals, and budgets to Maria before activation
      tools:
        - Google Ads API
        - Meta Ads Manager
        - Outbrain API

    - name: Colby
      role: Copywriting Specialist
      responsibilities:
        - Write ad copy, email content, and headlines
        - Ensure consistency in tone and clarity
        - Collaborate with Coco and Neomi on messaging
        - Submit all copy to Maria for review before handoff
      Tools:
        - Write to Storage and Memory

    - name: Coco
      role: Content Creation Specialist
      responsibilities:
        - Produce images, blog visuals, and graphics
        - Maintain consistency with style guide and tone
        - Work with Colby on layout and phrasing alignment
        - Submit visuals to Maria before upload or publication
      tools:
        - Write to Storage and Memory
        - Native Image Gen
        - [Insert Tools Later]

    - name: Vienna
      role: Video Production Specialist
      responsibilities:
        - Create short-form and long-form video content
        - Edit, caption, and format for platform delivery
        - Submit drafts to Maria before publishing
        - Coordinate with Sofie for post scheduling
        - Coordinate with Adriana to supply videos for ads
      tools:
        - Write to Storage and Memory
        - Veo 3
        - Creatify
        - CapCut

    - name: Neomi
      role: Newsletter Specialist
      responsibilities:
        - Build, segment, and schedule newsletter sends
        - Collaborate with Colby for copy and Coco for design
        - Submit all newsletter drafts to Maria for final review
        - Maintain deliverability and list hygiene
      tools:
        - Write to Storage and Memory
        - AWS SES
        - DynamoDB

    - name: Inaya
      role: Influencer Relations Specialist
      responsibilities:
        - Identify and vet influencer partners
        - Coordinate deliverables and content timing
        - Submit all collaboration proposals and content to Maria before outreach
        - Track influencer performance and ROI
      tools:
        - Write to Storage and Memory
        - FB/IG API 

  quality_standards:
    output_format:
      - Include filename convention: dept_role_date_task
"""


def main():
    """Vectorize the Marketing Department document."""
    logging.info("Starting Marketing Department document vectorization...")
    
    ingestion_service = get_ingestion_service()
    
    # Vectorize the document
    chunks, vectors = ingestion_service.vectorize_document(
        document_text=MARKETING_DEPARTMENT_DOC,
        document_id="marketing_department_v1",
        document_type="agent_library",
        metadata={
            "department": "Marketing Department",
            "version": "1.0",
            "source": "client_provided"
        },
        parse_structure=True
    )
    
    if chunks > 0 and vectors > 0:
        logging.info(f"✅ Successfully vectorized Marketing Department document!")
        logging.info(f"   - Created {chunks} chunks")
        logging.info(f"   - Stored {vectors} vectors in database")
        logging.info("")
        logging.info("You can now test queries like:")
        logging.info('   - "who is Sophie?"')
        logging.info('   - "what does Colby do?"')
        logging.info('   - "who is the Marketing Department manager?"')
    else:
        logging.error("❌ Failed to vectorize document")
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

