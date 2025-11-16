# /data/inception/app/services/incubator_orchestrator.py
"""
AI Incubator Orchestrator - Coordinates multi-agent collaboration for business idea evaluation.
Manages time-based execution (1 hour) with graceful wrap-up and final synthesis.
"""

import logging
import time
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from services.incubator_agents import (
    AgentRole, get_agent_definition, get_all_agent_roles,
    build_agent_prompt, build_synthesis_prompt
)
from services.local_cea_client import call_local_cea
from services.grok_service import grok_chat
from utils.yaml_utils import load_yaml, save_yaml


# Configuration
INCUBATOR_DURATION_MINUTES = int(os.getenv("INCUBATOR_DURATION_MINUTES", "60"))
INCUBATOR_WRAP_UP_MINUTES = int(os.getenv("INCUBATOR_WRAP_UP_MINUTES", "5"))  # Start wrap-up 5 min before end
INCUBATOR_AGENT_TIMEOUT_SECONDS = int(os.getenv("INCUBATOR_AGENT_TIMEOUT_SECONDS", "300"))  # 5 min per agent
INCUBATOR_USE_GROK_FOR_AGENTS = os.getenv("INCUBATOR_USE_GROK_FOR_AGENTS", "false").lower() in ("1", "true", "yes")
INCUBATOR_USE_GROK_FOR_SYNTHESIS = os.getenv("INCUBATOR_USE_GROK_FOR_SYNTHESIS", "false").lower() in ("1", "true", "yes")


# === Memory Management Functions ===

def get_memory_path():
    """Return the YAML file path for shared/global memory."""
    base_dir = Path(__file__).resolve().parent.parent.parent / "storage" / "instructions"
    return base_dir / "memory.yaml"


def load_incubator_memory() -> Dict:
    """Load incubator-related memory from memory.yaml."""
    path = get_memory_path()
    if not path.exists():
        return {"incubator_sessions": [], "agent_insights_history": []}
    
    data = load_yaml(path)
    if "incubator_sessions" not in data:
        data["incubator_sessions"] = []
    if "agent_insights_history" not in data:
        data["agent_insights_history"] = []
    
    return {
        "incubator_sessions": data.get("incubator_sessions", []),
        "agent_insights_history": data.get("agent_insights_history", []),
        "shared_context": data.get("shared_context", {}),
        "conversation": data.get("conversation", [])
    }


def save_incubator_memory(incubator_data: Dict):
    """Save incubator session data to memory.yaml."""
    path = get_memory_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    
    # Load existing memory
    if path.exists():
        data = load_yaml(path)
    else:
        data = {"shared_context": {}, "conversation": []}
    
    # Update incubator sections
    data["incubator_sessions"] = incubator_data.get("incubator_sessions", [])
    data["agent_insights_history"] = incubator_data.get("agent_insights_history", [])
    
    # Preserve other sections
    if "shared_context" not in data:
        data["shared_context"] = {}
    if "conversation" not in data:
        data["conversation"] = []
    
    save_yaml(path, data)
    logging.info(f"Saved incubator memory to {path}")


def get_relevant_memory_context(business_idea: str, agent_role: AgentRole, max_sessions: int = 3) -> str:
    """Get relevant memory context from previous incubator sessions for an agent."""
    memory = load_incubator_memory()
    sessions = memory.get("incubator_sessions", [])
    
    if not sessions:
        return ""
    
    # Get most recent sessions (limit to max_sessions)
    recent_sessions = sessions[-max_sessions:]
    
    context_parts = []
    for session in recent_sessions:
        idea = session.get("business_idea", "")
        insights = session.get("agent_insights", {})
        agent_insight = insights.get(agent_role.value, "")
        
        if agent_insight:
            context_parts.append(f"Previous session - Business Idea: {idea[:100]}...")
            context_parts.append(f"{agent_role.value.replace('_', ' ').title()} Insight: {agent_insight[:300]}...")
            context_parts.append("---")
    
    if context_parts:
        return "\n".join(context_parts)
    return ""


def _save_session_to_memory(session: IncubatorSession):
    """Save incubator session data to memory.yaml."""
    try:
        memory = load_incubator_memory()
        sessions = memory.get("incubator_sessions", [])
        
        # Convert agent insights to serializable format
        agent_insights_dict = {}
        for role, insight in session.agent_insights.items():
            agent_insights_dict[role.value] = insight
        
        # Create session record
        session_record = {
            "session_id": session.session_id,
            "business_idea": session.business_idea,
            "start_time": session.start_time.isoformat(),
            "end_time": session.end_time.isoformat(),
            "status": session.status,
            "agent_insights": agent_insights_dict,
            "agent_status": {role.value: status for role, status in session.agent_status.items()},
            "final_business_plan": session.final_business_plan[:5000] if session.final_business_plan else None,  # Truncate for storage
            "progress_log": session.progress_log[-50:]  # Keep last 50 progress messages
        }
        
        # Add to sessions list (keep last 20 sessions)
        sessions.append(session_record)
        if len(sessions) > 20:
            sessions = sessions[-20:]
        
        memory["incubator_sessions"] = sessions
        
        # Also add to agent insights history for quick lookup
        insights_history = memory.get("agent_insights_history", [])
        for role, insight in session.agent_insights.items():
            insights_history.append({
                "session_id": session.session_id,
                "agent_role": role.value,
                "business_idea": session.business_idea[:200],
                "insight": insight[:1000],  # Truncate for storage
                "timestamp": session.start_time.isoformat()
            })
        
        # Keep last 100 insights
        if len(insights_history) > 100:
            insights_history = insights_history[-100:]
        
        memory["agent_insights_history"] = insights_history
        
        # Save to memory.yaml
        save_incubator_memory(memory)
        logging.info(f"Saved incubator session {session.session_id} to memory")
        
    except Exception as e:
        logging.error(f"Failed to save session to memory: {e}")


class IncubatorSession:
    """Represents an active incubator session with state tracking."""
    
    def __init__(self, business_idea: str, session_id: str):
        self.business_idea = business_idea
        self.session_id = session_id
        self.start_time = datetime.now()
        self.end_time = self.start_time + timedelta(minutes=INCUBATOR_DURATION_MINUTES)
        self.agent_insights: Dict[AgentRole, str] = {}
        self.agent_status: Dict[AgentRole, str] = {}  # "pending", "processing", "completed", "failed"
        self.final_business_plan: Optional[str] = None
        self.status: str = "initialized"  # "initialized", "running", "wrapping_up", "synthesizing", "completed", "failed"
        self.progress_log: List[str] = []
        
    def add_progress(self, message: str):
        """Add progress message to log."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.progress_log.append(f"[{timestamp}] {message}")
        logging.info(f"Incubator {self.session_id}: {message}")
    
    def get_time_remaining_minutes(self) -> int:
        """Get remaining time in minutes."""
        remaining = (self.end_time - datetime.now()).total_seconds() / 60
        return max(0, int(remaining))
    
    def is_wrap_up_time(self) -> bool:
        """Check if it's time to start wrap-up phase."""
        return self.get_time_remaining_minutes() <= INCUBATOR_WRAP_UP_MINUTES
    
    def is_time_expired(self) -> bool:
        """Check if session time has expired."""
        return datetime.now() >= self.end_time


def run_agent_analysis(
    agent_role: AgentRole,
    business_idea: str,
    previous_insights: Dict[AgentRole, str],
    time_remaining_minutes: Optional[int] = None,
    max_retries: int = 2
) -> Tuple[str, bool]:
    """
    Run analysis for a single agent with retry logic and memory context.
    
    Returns:
        Tuple of (insight_text, success_flag)
    """
    agent_def = get_agent_definition(agent_role)
    if not agent_def:
        return f"Error: Agent definition not found for {agent_role}", False
    
    # Get relevant memory context from previous sessions
    memory_context = get_relevant_memory_context(business_idea, agent_role, max_sessions=3)
    
    for attempt in range(max_retries + 1):
        try:
            # Build agent prompt with memory context
            prompt = build_agent_prompt(
                agent_def=agent_def,
                business_idea=business_idea,
                previous_insights=previous_insights if previous_insights else None,
                time_remaining_minutes=time_remaining_minutes
            )
            
            # Add memory context to prompt if available
            if memory_context:
                prompt = f"{prompt}\n\n## Relevant Context from Previous Sessions\n{memory_context}\n\nPlease consider this context when providing your analysis."
            
            # Determine which model to use
            if INCUBATOR_USE_GROK_FOR_AGENTS:
                # Use Grok for faster agent responses
                logging.info(f"Running {agent_def.name} analysis using Grok (attempt {attempt + 1}/{max_retries + 1})")
                messages = [{"role": "user", "content": prompt}]
                insight = grok_chat(messages, None)
            else:
                # Use local CEA model
                logging.info(f"Running {agent_def.name} analysis using local CEA (attempt {attempt + 1}/{max_retries + 1})")
                agent_tokens = int(os.getenv("CEA_MAX_TOKENS", "600"))
                # Cap tokens for local model context window
                agent_tokens = min(agent_tokens, 500)
                insight = call_local_cea(
                    prompt=prompt,
                    num_predict=agent_tokens,
                    timeout=INCUBATOR_AGENT_TIMEOUT_SECONDS,
                    stream=True,
                    context=None
                )
            
            # Check if response is empty or too short
            if not insight or len(insight.strip()) < 50:
                if attempt < max_retries:
                    logging.warning(f"{agent_def.name} returned empty/short response (attempt {attempt + 1}), retrying...")
                    time.sleep(2)  # Brief delay before retry
                    continue
                else:
                    # Final fallback: Try Grok if local CEA failed
                    if not INCUBATOR_USE_GROK_FOR_AGENTS:
                        logging.warning(f"{agent_def.name} failed with local CEA, trying Grok as fallback...")
                        try:
                            prompt = build_agent_prompt(
                                agent_def=agent_def,
                                business_idea=business_idea,
                                previous_insights=previous_insights if previous_insights else None,
                                time_remaining_minutes=time_remaining_minutes
                            )
                            messages = [{"role": "user", "content": prompt}]
                            insight = grok_chat(messages, None)
                            if insight and len(insight.strip()) >= 50:
                                logging.info(f"{agent_def.name} succeeded with Grok fallback")
                                insight = insight.replace("[AGENT_COMPLETE]", "").strip()
                                return insight, True
                        except Exception as e:
                            logging.error(f"Grok fallback also failed for {agent_def.name}: {e}")
                    
                    return f"Error: {agent_def.name} returned empty or insufficient response after {max_retries + 1} attempts", False
            
            # Remove completion markers if present
            insight = insight.replace("[AGENT_COMPLETE]", "").strip()
            
            return insight, True
            
        except Exception as e:
            error_msg = f"Error running {agent_def.name} (attempt {attempt + 1}): {str(e)}"
            logging.exception(error_msg)
            if attempt < max_retries:
                logging.warning(f"Retrying {agent_def.name} after error...")
                time.sleep(2)
                continue
            else:
                return error_msg, False
    
    return f"Error: {agent_def.name} failed after {max_retries + 1} attempts", False


def run_incubator_session(business_idea: str, session_id: str) -> Dict:
    """
    Main orchestrator function - runs the full incubator session.
    
    Args:
        business_idea: The business idea to evaluate
        session_id: Unique session identifier
        
    Returns:
        Dict with session results
    """
    session = IncubatorSession(business_idea, session_id)
    session.add_progress(f"Starting incubator session for business idea evaluation")
    session.status = "running"
    
    try:
        # Get list of agents to run (excluding CEA coordinator)
        agent_roles = get_all_agent_roles()
        session.add_progress(f"Initialized {len(agent_roles)} specialized agents")
        
        # Phase 1: Run agents in parallel (or sequential if needed for resource constraints)
        # For now, run sequentially to avoid overwhelming the local model
        # In production, could run in parallel with proper resource management
        
        for agent_role in agent_roles:
            if session.is_time_expired():
                session.add_progress("⚠️ Time expired before all agents completed")
                break
            
            agent_def = get_agent_definition(agent_role)
            session.agent_status[agent_role] = "processing"
            session.add_progress(f"Running {agent_def.name} analysis...")
            
            # Check time remaining for wrap-up signal
            time_remaining = session.get_time_remaining_minutes()
            if session.is_wrap_up_time():
                session.add_progress(f"⚠️ Wrap-up phase: {time_remaining} minutes remaining")
            
            # Run agent analysis
            insight, success = run_agent_analysis(
                agent_role=agent_role,
                business_idea=business_idea,
                previous_insights=session.agent_insights,
                time_remaining_minutes=time_remaining if session.is_wrap_up_time() else None
            )
            
            if success:
                session.agent_insights[agent_role] = insight
                session.agent_status[agent_role] = "completed"
                session.add_progress(f"✅ {agent_def.name} analysis completed ({len(insight)} chars)")
            else:
                session.agent_status[agent_role] = "failed"
                session.agent_insights[agent_role] = insight  # Store error message
                session.add_progress(f"❌ {agent_def.name} analysis failed: {insight[:100]}")
        
        # Phase 2: Synthesis - CEA coordinator compiles final business plan
        if len(session.agent_insights) == 0:
            session.status = "failed"
            session.add_progress("❌ No agent insights collected - cannot synthesize")
            return {
                "status": "failed",
                "error": "No agent insights collected",
                "session_id": session_id,
                "progress_log": session.progress_log
            }
        
        session.status = "synthesizing"
        time_elapsed = int((datetime.now() - session.start_time).total_seconds() / 60)
        session.add_progress(f"Starting synthesis phase ({time_elapsed} minutes elapsed)")
        
        # Build synthesis prompt - truncate agent insights if too long
        # Limit each insight to 800 chars to avoid prompt overflow
        truncated_insights = {}
        for role, insight in session.agent_insights.items():
            if isinstance(insight, str) and len(insight) > 800:
                truncated_insights[role] = insight[:800] + "\n[... content truncated for synthesis ...]"
            else:
                truncated_insights[role] = insight
        
        synthesis_prompt = build_synthesis_prompt(
            business_idea=business_idea,
            all_insights=truncated_insights,
            time_elapsed_minutes=time_elapsed
        )
        
        # Truncate prompt itself if too long (for local CEA context window)
        max_prompt_chars = 2500  # Leave room for response
        if len(synthesis_prompt) > max_prompt_chars:
            logging.warning(f"Synthesis prompt too long ({len(synthesis_prompt)} chars), truncating to {max_prompt_chars}")
            # Keep beginning and end, truncate middle
            keep_start = max_prompt_chars // 2 - 200
            keep_end = max_prompt_chars // 2 - 200
            synthesis_prompt = synthesis_prompt[:keep_start] + "\n\n[... agent insights truncated for context ...]\n\n" + synthesis_prompt[-keep_end:]
        
        # Run synthesis with retry logic and fallback
        business_plan = None
        synthesis_attempts = 2
        
        try:
            for attempt in range(synthesis_attempts):
                try:
                    if INCUBATOR_USE_GROK_FOR_SYNTHESIS:
                        logging.info(f"Running synthesis using Grok (attempt {attempt + 1}/{synthesis_attempts})")
                        messages = [{"role": "user", "content": synthesis_prompt}]
                        business_plan = grok_chat(messages, None)
                    else:
                        logging.info(f"Running synthesis using local CEA (attempt {attempt + 1}/{synthesis_attempts})")
                        synthesis_tokens = int(os.getenv("CEA_MAX_TOKENS", "700"))
                        synthesis_tokens = min(synthesis_tokens, 500)  # Cap for context window
                        business_plan = call_local_cea(
                            prompt=synthesis_prompt,
                            num_predict=synthesis_tokens,
                            timeout=INCUBATOR_AGENT_TIMEOUT_SECONDS * 2,  # Give synthesis more time
                            stream=True,
                            context=None
                        )
                    
                    if business_plan and len(business_plan.strip()) > 0:
                        break  # Success, exit retry loop
                    else:
                        logging.warning(f"Synthesis attempt {attempt + 1} returned empty response")
                        if attempt < synthesis_attempts - 1:
                            session.add_progress(f"⚠️ Synthesis returned empty, retrying... (attempt {attempt + 2}/{synthesis_attempts})")
                            time.sleep(2)
                        
                except Exception as e:
                    logging.error(f"Synthesis attempt {attempt + 1} failed: {e}")
                    if attempt < synthesis_attempts - 1:
                        session.add_progress(f"⚠️ Synthesis failed, retrying... (attempt {attempt + 2}/{synthesis_attempts})")
                        time.sleep(2)
                    else:
                        # Final attempt failed, try Grok as fallback if we were using local CEA
                        if not INCUBATOR_USE_GROK_FOR_SYNTHESIS:
                            logging.warning("Local CEA synthesis failed, trying Grok as fallback...")
                            session.add_progress("⚠️ Local CEA synthesis failed, trying Grok as fallback...")
                            try:
                                messages = [{"role": "user", "content": synthesis_prompt}]
                                business_plan = grok_chat(messages, None)
                                if business_plan and len(business_plan.strip()) > 0:
                                    logging.info("Grok fallback succeeded for synthesis")
                                    session.add_progress("✅ Grok fallback succeeded for synthesis")
                            except Exception as e2:
                                logging.error(f"Grok fallback also failed: {e2}")
            
            if business_plan and len(business_plan.strip()) > 0:
                # Remove completion markers
                business_plan = business_plan.replace("[SYNTHESIS_COMPLETE]", "").strip()
                
                # Check for truncation and complete if needed (using same logic as CEA delegation)
                from services.cea_delegation_service import _looks_truncated, _ensure_complete
                
                # Use iterative completion to ensure full completion
                max_completion_iterations = 3
                for completion_iter in range(max_completion_iterations):
                    if not _looks_truncated(business_plan, business_idea):
                        break  # Plan is complete
                    
                    if completion_iter == 0:
                        session.add_progress("⚠️ Business plan appears truncated, attempting completion...")
                    else:
                        session.add_progress(f"⚠️ Still truncated after iteration {completion_iter}, continuing...")
                    
                    try:
                        # Use Grok for continuation if available, otherwise local CEA
                        use_grok_cont = os.getenv("CEA_USE_GROK_FOR_CONTINUATION", "true").lower() in ("1", "true", "yes")
                        if use_grok_cont:
                            # Build continuation prompt with more context
                            cont_prompt = f"""The following business plan is incomplete. Please complete it from where it left off. Do not repeat any content. Ensure you complete the current section and any remaining sections.

Incomplete business plan (last 1000 chars):
{business_plan[-1000:]}

Continue and complete the business plan. Make sure to finish the current section and include any remaining sections (e.g., Financial Projections, Risk Analysis, Implementation Roadmap, Conclusion)."""
                            messages = [{"role": "user", "content": cont_prompt}]
                            continuation = grok_chat(messages, None)
                            if continuation and len(continuation.strip()) > 50:
                                # Check if continuation itself is truncated
                                if _looks_truncated(continuation, business_idea):
                                    logging.warning(f"Continuation itself appears truncated, may need another iteration")
                                
                                # Check for duplication before appending
                                last_100_chars = business_plan.rstrip()[-100:].lower()
                                first_100_chars = continuation.strip()[:100].lower()
                                
                                # Avoid duplication
                                if last_100_chars not in first_100_chars and first_100_chars not in last_100_chars:
                                    business_plan = business_plan.rstrip() + "\n\n" + continuation.strip()
                                else:
                                    # If there's overlap, find the unique part
                                    overlap_found = False
                                    for i in range(50, min(len(continuation), 200)):
                                        if business_plan.rstrip()[-i:].lower() == continuation.strip()[:i].lower():
                                            business_plan = business_plan.rstrip() + continuation.strip()[i:]
                                            overlap_found = True
                                            break
                                    if not overlap_found:
                                        business_plan = business_plan + continuation.strip()
                        else:
                            # Use local completion logic with more iterations
                            business_plan = _ensure_complete(business_idea, business_plan, max_iters=3)
                    except Exception as e:
                        logging.warning(f"Failed to complete truncated business plan (iteration {completion_iter + 1}): {e}")
                        if completion_iter == max_completion_iterations - 1:
                            session.add_progress("⚠️ Could not complete truncated plan after multiple attempts, using partial result")
                        continue
                    
                # Final check - if still truncated, add a note
                if _looks_truncated(business_plan, business_idea):
                    session.add_progress("⚠️ Business plan may still be incomplete after completion attempts")
                    business_plan = business_plan + "\n\n[Note: Business plan generation was limited by token constraints. Some sections may be abbreviated.]"
                
                session.final_business_plan = business_plan
                session.status = "completed"
                session.add_progress(f"✅ Synthesis completed - Business plan generated ({len(business_plan)} chars)")
                
                # Save session to memory
                _save_session_to_memory(session)
            else:
                session.status = "failed"
                session.add_progress("❌ Synthesis returned empty response")
                # Still save partial session to memory
                _save_session_to_memory(session)
                return {
                    "status": "failed",
                    "error": "Synthesis returned empty response",
                    "session_id": session_id,
                    "agent_insights": {role.value: insight for role, insight in session.agent_insights.items()},
                    "progress_log": session.progress_log
                }
                
        except Exception as e:
            session.status = "failed"
            error_msg = f"Synthesis failed: {str(e)}"
            session.add_progress(f"❌ {error_msg}")
            logging.exception(error_msg)
            return {
                "status": "failed",
                "error": error_msg,
                "session_id": session_id,
                "agent_insights": {role.value: insight for role, insight in session.agent_insights.items()},
                "progress_log": session.progress_log
            }
        
        # Success - return complete results
        total_time = int((datetime.now() - session.start_time).total_seconds() / 60)
        session.add_progress(f"🎉 Incubator session completed successfully in {total_time} minutes")
        
        # Ensure session is saved to memory (should already be saved, but ensure it)
        if session.status == "completed":
            _save_session_to_memory(session)
        
        return {
            "status": "completed",
            "session_id": session_id,
            "business_idea": business_idea,
            "agent_insights": {
                role.value: {
                    "agent_name": get_agent_definition(role).name,
                    "status": session.agent_status.get(role, "unknown"),
                    "insight": insight
                }
                for role, insight in session.agent_insights.items()
            },
            "business_plan": session.final_business_plan,
            "progress_log": session.progress_log,
            "duration_minutes": total_time,
            "completed_agents": len([s for s in session.agent_status.values() if s == "completed"])
        }
        
    except Exception as e:
        session.status = "failed"
        error_msg = f"Incubator session failed: {str(e)}"
        session.add_progress(f"❌ {error_msg}")
        logging.exception(error_msg)
        # Save failed session to memory
        _save_session_to_memory(session)
        return {
            "status": "failed",
            "error": error_msg,
            "session_id": session_id,
            "progress_log": session.progress_log
        }

