# /data/inception/app/services/incubator_agents.py
"""
Specialized AI Agent Definitions for the AI Incubator System.
Each agent embodies a specific domain expert with unique perspective and expertise.
"""

import logging
from typing import Dict, List, Optional
from dataclasses import dataclass
from enum import Enum


class AgentRole(Enum):
    """Enumeration of available agent roles."""
    MARKETING_EXPERT = "marketing_expert"
    FINANCIAL_ADVISOR = "financial_advisor"
    MARKET_ANALYST = "market_analyst"
    TECHNICAL_ARCHITECT = "technical_architect"
    RISK_ANALYST = "risk_analyst"
    CEA_COORDINATOR = "cea_coordinator"


@dataclass
class AgentDefinition:
    """Definition of a specialized agent with its persona and expertise."""
    role: AgentRole
    name: str
    expertise: str
    persona: str
    focus_areas: List[str]
    output_format: str


# Agent Definitions - Professional personas with clear expertise
AGENT_DEFINITIONS: Dict[AgentRole, AgentDefinition] = {
    AgentRole.MARKETING_EXPERT: AgentDefinition(
        role=AgentRole.MARKETING_EXPERT,
        name="Marketing Strategist",
        expertise="Digital marketing, brand positioning, customer acquisition, growth strategies",
        persona="You are a senior marketing strategist with 15+ years of experience in digital marketing and brand development. You think like a CMO at a Fortune 500 company, focusing on market positioning, customer personas, go-to-market strategies, and scalable growth tactics.",
        focus_areas=[
            "Target audience identification and segmentation",
            "Brand positioning and messaging strategy",
            "Marketing channel selection and budget allocation",
            "Customer acquisition cost (CAC) and lifetime value (LTV) analysis",
            "Go-to-market (GTM) strategy and launch tactics"
        ],
        output_format="Provide structured analysis with: Target Audience, Positioning Strategy, Marketing Channels, Budget Recommendations, GTM Timeline"
    ),
    
    AgentRole.FINANCIAL_ADVISOR: AgentDefinition(
        role=AgentRole.FINANCIAL_ADVISOR,
        name="Financial Advisor",
        expertise="Financial modeling, startup economics, funding strategies, unit economics",
        persona="You are a seasoned financial advisor specializing in startups and early-stage businesses. You think like a CFO or venture capital analyst, focusing on financial viability, unit economics, funding requirements, and sustainable business models.",
        focus_areas=[
            "Startup costs and capital requirements",
            "Revenue projections and financial modeling",
            "Unit economics (CAC, LTV, gross margins)",
            "Funding strategies and investor readiness",
            "Break-even analysis and cash flow projections"
        ],
        output_format="Provide structured analysis with: Startup Costs, Revenue Projections, Unit Economics, Funding Requirements, Financial Milestones"
    ),
    
    AgentRole.MARKET_ANALYST: AgentDefinition(
        role=AgentRole.MARKET_ANALYST,
        name="Market Research Analyst",
        expertise="Market sizing, competitive analysis, industry trends, opportunity assessment",
        persona="You are a market research analyst with deep expertise in market sizing, competitive intelligence, and industry trend analysis. You think like a McKinsey or BCG consultant, focusing on market opportunity, competitive landscape, and strategic positioning.",
        focus_areas=[
            "Total Addressable Market (TAM), Serviceable Addressable Market (SAM), Serviceable Obtainable Market (SOM)",
            "Competitive landscape and differentiation opportunities",
            "Industry trends and market dynamics",
            "Customer pain points and unmet needs",
            "Market entry barriers and opportunities"
        ],
        output_format="Provide structured analysis with: Market Size (TAM/SAM/SOM), Competitive Landscape, Market Trends, Opportunities, Market Entry Strategy"
    ),
    
    AgentRole.TECHNICAL_ARCHITECT: AgentDefinition(
        role=AgentRole.TECHNICAL_ARCHITECT,
        name="Technical Architect",
        expertise="Technology stack, product development, scalability, technical feasibility",
        persona="You are a senior technical architect with expertise in building scalable products and platforms. You think like a CTO at a tech startup, focusing on technical feasibility, architecture decisions, development timelines, and scalability considerations.",
        focus_areas=[
            "Technology stack recommendations",
            "Product development roadmap and milestones",
            "Technical feasibility and complexity assessment",
            "Scalability and infrastructure requirements",
            "Development cost and timeline estimates"
        ],
        output_format="Provide structured analysis with: Technology Stack, Development Roadmap, Technical Feasibility, Infrastructure Requirements, Development Timeline"
    ),
    
    AgentRole.RISK_ANALYST: AgentDefinition(
        role=AgentRole.RISK_ANALYST,
        name="Risk & Strategy Analyst",
        expertise="Risk assessment, mitigation strategies, business model validation, strategic planning",
        persona="You are a risk and strategy analyst with expertise in identifying business risks and developing mitigation strategies. You think like a management consultant, focusing on potential pitfalls, risk mitigation, and strategic planning.",
        focus_areas=[
            "Business model risks and challenges",
            "Market and competitive risks",
            "Operational and execution risks",
            "Regulatory and compliance considerations",
            "Risk mitigation strategies and contingency plans"
        ],
        output_format="Provide structured analysis with: Key Risks, Risk Severity Assessment, Mitigation Strategies, Contingency Plans, Risk Monitoring Framework"
    ),
    
    AgentRole.CEA_COORDINATOR: AgentDefinition(
        role=AgentRole.CEA_COORDINATOR,
        name="Chief Executive Agent (CEA)",
        expertise="Strategic synthesis, executive decision-making, business plan compilation",
        persona="You are the Chief Executive Agent (CEA), responsible for synthesizing insights from all specialized agents into a comprehensive, actionable business plan. You think like a CEO, focusing on strategic alignment, prioritization, and execution readiness.",
        focus_areas=[
            "Synthesizing multi-agent insights into cohesive strategy",
            "Prioritizing recommendations and action items",
            "Creating executive summary and business plan structure",
            "Identifying strategic gaps and opportunities",
            "Ensuring plan is actionable and implementation-ready"
        ],
        output_format="Provide comprehensive business plan with: Executive Summary, Strategic Overview, Integrated Recommendations, Implementation Roadmap, Success Metrics"
    )
}


def get_agent_definition(role: AgentRole) -> Optional[AgentDefinition]:
    """Get agent definition by role."""
    return AGENT_DEFINITIONS.get(role)


def get_all_agent_roles() -> List[AgentRole]:
    """Get list of all available agent roles (excluding CEA coordinator)."""
    return [role for role in AgentRole if role != AgentRole.CEA_COORDINATOR]


def build_agent_prompt(
    agent_def: AgentDefinition,
    business_idea: str,
    previous_insights: Optional[Dict[AgentRole, str]] = None,
    time_remaining_minutes: Optional[int] = None
) -> str:
    """
    Build a comprehensive prompt for an agent to analyze the business idea.
    
    Args:
        agent_def: Agent definition
        business_idea: The business idea to analyze
        previous_insights: Optional dict of previous agent outputs for collaboration
        time_remaining_minutes: Optional time remaining for graceful wrap-up
        
    Returns:
        Formatted prompt string
    """
    prompt_parts = [
        f"# Role: {agent_def.name}",
        f"# Expertise: {agent_def.expertise}",
        "",
        f"{agent_def.persona}",
        "",
        "## Your Task:",
        f"Analyze the following business idea from your specialized perspective and provide comprehensive insights.",
        "",
        "## Business Idea:",
        f"{business_idea}",
        ""
    ]
    
    # Add collaboration context if available
    if previous_insights:
        prompt_parts.extend([
            "## Insights from Other Specialists:",
            "The following insights have been provided by other domain experts. Use these to inform your analysis and identify synergies or gaps:",
            ""
        ])
        for role, insight in previous_insights.items():
            if role != agent_def.role:
                agent_name = AGENT_DEFINITIONS[role].name
                # Truncate insight to avoid context overflow
                insight_preview = insight[:800] + "..." if len(insight) > 800 else insight
                prompt_parts.append(f"### {agent_name}:")
                prompt_parts.append(f"{insight_preview}")
                prompt_parts.append("")
    
    # Add time awareness for graceful wrap-up
    if time_remaining_minutes is not None and time_remaining_minutes <= 5:
        prompt_parts.extend([
            "## Time Remaining:",
            f"⚠️ You have approximately {time_remaining_minutes} minutes remaining. Please provide your final, comprehensive analysis now. Focus on key insights and actionable recommendations.",
            ""
        ])
    
    prompt_parts.extend([
        "## Your Analysis Should Cover:",
        *[f"- {area}" for area in agent_def.focus_areas],
        "",
        "## Output Format:",
        f"{agent_def.output_format}",
        "",
        "## Instructions:",
        "1. Be thorough but concise. Focus on actionable insights.",
        "2. Use data-driven reasoning where possible.",
        "3. If collaborating with other agents, reference their insights and build upon them.",
        "4. Provide specific, implementable recommendations.",
        "5. When finished, append [AGENT_COMPLETE] at the end.",
        "",
        "Begin your analysis:"
    ])
    
    return "\n".join(prompt_parts)


def build_synthesis_prompt(
    business_idea: str,
    all_insights: Dict[AgentRole, str],
    time_elapsed_minutes: int
) -> str:
    """
    Build prompt for CEA to synthesize all agent insights into final business plan.
    
    Args:
        business_idea: Original business idea
        all_insights: Dict of all agent outputs
        time_elapsed_minutes: Time elapsed in the incubator session
        
    Returns:
        Formatted synthesis prompt
    """
    cea_def = AGENT_DEFINITIONS[AgentRole.CEA_COORDINATOR]
    
    prompt_parts = [
        f"# Role: {cea_def.name}",
        f"# Expertise: {cea_def.expertise}",
        "",
        f"{cea_def.persona}",
        "",
        "## Your Task:",
        "Synthesize insights from all specialized agents into a comprehensive, executive-ready business plan.",
        "",
        "## Original Business Idea:",
        f"{business_idea}",
        "",
        "## Insights from Specialized Agents:",
        ""
    ]
    
    # Add all agent insights
    for role, insight in all_insights.items():
        agent_name = AGENT_DEFINITIONS[role].name
        # Truncate if too long to fit in context
        insight_truncated = insight[:1200] + "\n[... content truncated for synthesis ...]" if len(insight) > 1200 else insight
        prompt_parts.extend([
            f"### {agent_name} Analysis:",
            f"{insight_truncated}",
            ""
        ])
    
    prompt_parts.extend([
        "## Business Plan Structure:",
        "Create a comprehensive business plan with the following sections:",
        "",
        "1. **Executive Summary** (2-3 paragraphs)",
        "   - Business concept overview",
        "   - Key value proposition",
        "   - Primary objectives and success metrics",
        "",
        "2. **Market Opportunity**",
        "   - Market size and opportunity",
        "   - Target audience and customer personas",
        "   - Competitive landscape and differentiation",
        "",
        "3. **Business Model & Strategy**",
        "   - Revenue model and pricing strategy",
        "   - Go-to-market strategy",
        "   - Marketing and customer acquisition plan",
        "",
        "4. **Financial Projections**",
        "   - Startup costs and capital requirements",
        "   - Revenue projections (Year 1-3)",
        "   - Unit economics and profitability analysis",
        "   - Funding requirements (if applicable)",
        "",
        "5. **Product & Technology**",
        "   - Product/service description",
        "   - Technology stack and development roadmap",
        "   - Scalability considerations",
        "",
        "6. **Risk Analysis & Mitigation**",
        "   - Key risks and challenges",
        "   - Risk mitigation strategies",
        "   - Contingency plans",
        "",
        "7. **Implementation Roadmap**",
        "   - Phase 1: Launch (Months 1-3)",
        "   - Phase 2: Growth (Months 4-6)",
        "   - Phase 3: Scale (Months 7-12)",
        "   - Key milestones and success metrics",
        "",
        "8. **Conclusion & Next Steps**",
        "   - Summary of key recommendations",
        "   - Immediate action items",
        "   - Success criteria and KPIs",
        "",
        "## Instructions:",
        "1. Synthesize all agent insights into a cohesive, professional business plan.",
        "2. Ensure all sections are comprehensive and actionable.",
        "3. Maintain consistency across sections (e.g., financial projections align with market analysis).",
        "4. Prioritize recommendations based on impact and feasibility.",
        "5. Use clear, executive-level language suitable for stakeholders.",
        "6. When complete, append [SYNTHESIS_COMPLETE] at the end.",
        "",
        f"## Session Context:",
        f"Incubator session duration: {time_elapsed_minutes} minutes",
        "",
        "Begin synthesis:"
    ])
    
    return "\n".join(prompt_parts)

