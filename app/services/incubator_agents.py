# /data/inception/app/services/incubator_agents.py
"""
General-purpose AI Agent System for the AI Incubator.
Agents are dynamically configured from vectorized documents (RAG) rather than hardcoded.
"""

import logging
from typing import Dict, List, Optional
from dataclasses import dataclass


@dataclass
class AgentConfig:
    """General-purpose agent configuration loaded from documents."""
    name: str
    role: str
    department: Optional[str] = None
    responsibilities: List[str] = None
    tools: List[str] = None
    communication_protocol: Optional[str] = None
    metadata: Dict = None
    
    def __post_init__(self):
        if self.responsibilities is None:
            self.responsibilities = []
        if self.tools is None:
            self.tools = []
        if self.metadata is None:
            self.metadata = {}


def build_general_agent_prompt(
    agent_name: Optional[str] = None,
    agent_role: Optional[str] = None,
    agent_context: Optional[str] = None,
    task_description: str = "",
    previous_work: Optional[Dict[str, str]] = None,
    time_remaining_minutes: Optional[int] = None
) -> str:
    """
    Build a prompt for a general-purpose agent.
    Agent details can come from RAG lookup if agent_name/role is provided.
    
    Args:
        agent_name: Name of the agent (e.g., "Sophie", "Colby")
        agent_role: Role of the agent (e.g., "Social Media Specialist")
        agent_context: Additional context about the agent (from RAG)
        task_description: The task to perform
        previous_work: Optional dict of previous agent outputs
        time_remaining_minutes: Optional time remaining for graceful wrap-up
        
    Returns:
        Formatted prompt string
    """
    prompt_parts = []
    
    # Add agent identity if available
    if agent_name or agent_role:
        prompt_parts.append("# Agent Identity")
        if agent_name:
            prompt_parts.append(f"Name: {agent_name}")
        if agent_role:
            prompt_parts.append(f"Role: {agent_role}")
        if agent_context:
            prompt_parts.append(f"\nContext:\n{agent_context}")
        prompt_parts.append("")
    
    # Add task
    prompt_parts.extend([
        "## Your Task:",
        task_description,
        ""
    ])
    
    # Add collaboration context if available
    if previous_work:
        prompt_parts.extend([
            "## Previous Work from Other Agents:",
            "Review the following outputs and build upon them:",
            ""
        ])
        for agent, output in previous_work.items():
            output_preview = output[:800] + "..." if len(output) > 800 else output
            prompt_parts.append(f"### {agent}:")
            prompt_parts.append(f"{output_preview}")
            prompt_parts.append("")
    
    # Add time awareness
    if time_remaining_minutes is not None and time_remaining_minutes <= 5:
        prompt_parts.extend([
            "## Time Remaining:",
            f"⚠️ You have approximately {time_remaining_minutes} minutes remaining. Please provide your final output now.",
            ""
        ])
    
    prompt_parts.extend([
        "## Instructions:",
        "1. Be thorough and actionable.",
        "2. Use data-driven reasoning where possible.",
        "3. If collaborating with other agents, reference their work and build upon it.",
        "4. Provide specific, implementable recommendations.",
        "5. When finished, append [AGENT_COMPLETE] at the end.",
        "",
        "Begin your work:"
    ])
    
    return "\n".join(prompt_parts)


def build_synthesis_prompt(
    master_task: str,
    all_work: Dict[str, str],
    time_elapsed_minutes: int
) -> str:
    """
    Build prompt for synthesizing all agent work into final output.
    
    Args:
        master_task: Original master task/project
        all_work: Dict of all agent outputs (agent_name -> output)
        time_elapsed_minutes: Time elapsed in the session
        
    Returns:
        Formatted synthesis prompt
    """
    prompt_parts = [
        "# Synthesis Task",
        "",
        "## Original Master Task:",
        master_task,
        "",
        "## Work Completed by Agents:",
        ""
    ]
    
    # Add all agent outputs
    for agent_name, output in all_work.items():
        output_truncated = output[:1200] + "\n[... content truncated for synthesis ...]" if len(output) > 1200 else output
        prompt_parts.extend([
            f"### {agent_name}:",
            f"{output_truncated}",
            ""
        ])
    
    prompt_parts.extend([
        "## Your Task:",
        "Synthesize all the work above into a comprehensive, cohesive final output.",
        "Ensure all sections are well-integrated and actionable.",
        "",
        "## Instructions:",
        "1. Synthesize all agent outputs into a cohesive whole.",
        "2. Ensure consistency across sections.",
        "3. Prioritize recommendations based on impact and feasibility.",
        "4. Use clear, professional language.",
        "5. When complete, append [SYNTHESIS_COMPLETE] at the end.",
        "",
        f"## Session Context:",
        f"Session duration: {time_elapsed_minutes} minutes",
        "",
        "Begin synthesis:"
    ])
    
    return "\n".join(prompt_parts)
