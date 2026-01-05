"""
Chunked Generation Service - Option B Implementation

Splits multi-part content requests into separate generation calls to avoid truncation.
Each chunk is generated independently and stored separately, then combined for the final response.
"""
import logging
import re
from typing import List, Dict, Any, Optional
from services.local_cea_client import call_local_cea
from services.grok_service import grok_chat


def detect_multi_part_request(user_message: str) -> List[Dict[str, str]]:
    """
    Detect if the user's request contains multiple parts.
    Handles various patterns: social media content, business plans, marketing campaigns, etc.
    Returns a list of chunk definitions with prompts.
    """
    msg_lower = user_message.lower()
    chunks = []
    
    # ============================================================================
    # Pattern 1: Multiple content types mentioned (social media, content marketing)
    # ============================================================================
    content_type_keywords = {
        "blog": ["blog", "article", "post", "blog post"],
        "x": ["x", "twitter", "tweet"],
        "facebook": ["facebook", "fb", "meta"],
        "instagram": ["instagram", "ig", "reel", "story"],
        "linkedin": ["linkedin", "li"],
        "email": ["email", "newsletter", "mail"],
        "youtube": ["youtube", "yt", "video"],
        "tiktok": ["tiktok", "tt"],
        "pinterest": ["pinterest", "pin"],
        "podcast": ["podcast", "episode"],
        "press_release": ["press release", "press", "announcement"],
        "landing_page": ["landing page", "landing", "sales page"],
        "ad_copy": ["ad", "advertisement", "ad copy", "advertising"],
        "social_media": ["social media", "social post", "social content"]
    }
    
    # Check for multiple content types
    detected_types = []
    for content_type, keywords in content_type_keywords.items():
        if any(keyword in msg_lower for keyword in keywords):
            detected_types.append(content_type)
    
    # If 2+ content types detected, create chunks
    if len(detected_types) >= 2:
        # Extract topic/theme
        topic_patterns = [
            r"(?:for|on|about|section|topic)\s+([^,]+?)(?:,|along|and|$)",
            r"(?:create|make|write|prepare|generate)\s+(?:a|an|the)?\s*(?:new|)?\s*(?:post|content|article|blog)?\s*(?:for|on|about)\s+([^,]+?)(?:,|along|and|$)",
            r"([^,]+?)\s+(?:section|topic|theme|subject)"
        ]
        topic = None
        for pattern in topic_patterns:
            match = re.search(pattern, msg_lower)
            if match:
                topic = match.group(1).strip() if match.lastindex else match.group(0).strip()
                break
        
        if not topic:
            # Try to extract from context
            topic_match = re.search(r"([^.!?]+?)(?:,|along|and)", msg_lower[:200])
            topic = topic_match.group(1).strip() if topic_match else "the specified topic"
        
        # Create chunks for each detected type
        for ct in detected_types:
            chunk = _create_content_chunk(ct, topic, user_message)
            if chunk:
                chunks.append(chunk)
        
        if chunks:
            return chunks
    
    # ============================================================================
    # Pattern 2: Action verbs + multiple items (create, make, write, prepare, generate)
    # ============================================================================
    action_verbs = ["create", "make", "write", "prepare", "generate", "develop", "build", "design"]
    has_action = any(verb in msg_lower for verb in action_verbs)
    
    if has_action:
        # Look for "and" or "," separating multiple items
        # Pattern: "create X and Y" or "create X, Y, and Z"
        and_pattern = r"(?:and|,)\s*([^,]+?)(?:,|and|$)"
        items = re.findall(and_pattern, msg_lower)
        
        # Also check for numbered lists
        numbered_items = re.findall(r"\d+\.\s*([^,]+?)(?:,|and|$)", msg_lower)
        
        # Combine both patterns
        all_items = items + numbered_items
        
        # If we have 2+ distinct items, treat as multi-part
        if len(all_items) >= 2:
            # Extract main topic
            topic_match = re.search(r"(?:for|on|about)\s+([^,]+?)(?:,|along|and|$)", msg_lower)
            topic = topic_match.group(1).strip() if topic_match else "the specified topic"
            
            # Map items to content types
            for item in all_items:
                item_lower = item.lower().strip()
                chunk = _map_item_to_chunk(item_lower, topic, user_message)
                if chunk:
                    chunks.append(chunk)
            
            if chunks:
                return chunks
    
    # ============================================================================
    # Pattern 3: Explicit numbered/bulleted lists
    # ============================================================================
    numbered_list = re.findall(r"\d+\.\s*([^,]+?)(?:,|and|$)", msg_lower)
    bulleted_list = re.findall(r"[•\-\*]\s*([^,]+?)(?:,|and|$)", msg_lower)
    
    if len(numbered_list) >= 2 or len(bulleted_list) >= 2:
        items = numbered_list if numbered_list else bulleted_list
        topic_match = re.search(r"(?:for|on|about)\s+([^,]+?)(?:,|along|and|$)", msg_lower)
        topic = topic_match.group(1).strip() if topic_match else "the specified topic"
        
        for item in items:
            item_lower = item.lower().strip()
            chunk = _map_item_to_chunk(item_lower, topic, user_message)
            if chunk:
                chunks.append(chunk)
        
        if chunks:
            return chunks
    
    # ============================================================================
    # Pattern 4: Business/marketing multi-part requests
    # ============================================================================
    business_keywords = {
        "marketing_plan": ["marketing plan", "marketing strategy", "marketing campaign"],
        "business_plan": ["business plan", "business strategy"],
        "content_calendar": ["content calendar", "content plan", "content schedule"],
        "social_media_strategy": ["social media strategy", "social media plan"],
        "email_campaign": ["email campaign", "email sequence", "email series"],
        "ad_campaign": ["ad campaign", "advertising campaign", "ad strategy"]
    }
    
    detected_business = []
    for business_type, keywords in business_keywords.items():
        if any(keyword in msg_lower for keyword in keywords):
            detected_business.append(business_type)
    
    # If business request mentions multiple components, split them
    if detected_business:
        # Common components: strategy, tactics, budget, timeline, metrics
        components = []
        if "strategy" in msg_lower or "strategic" in msg_lower:
            components.append("strategy")
        if "tactics" in msg_lower or "tactical" in msg_lower or "tactics" in msg_lower:
            components.append("tactics")
        if "budget" in msg_lower or "cost" in msg_lower or "pricing" in msg_lower:
            components.append("budget")
        if "timeline" in msg_lower or "schedule" in msg_lower or "calendar" in msg_lower:
            components.append("timeline")
        if "metrics" in msg_lower or "kpi" in msg_lower or "analytics" in msg_lower:
            components.append("metrics")
        
        if len(components) >= 2:
            topic_match = re.search(r"(?:for|on|about)\s+([^,]+?)(?:,|along|and|$)", msg_lower)
            topic = topic_match.group(1).strip() if topic_match else "the specified topic"
            
            for component in components:
                chunks.append({
                    "type": f"business_{component}",
                    "prompt": f"Create the {component} section for {topic}. Be specific, actionable, and comprehensive.",
                    "label": component.capitalize()
                })
            
            if chunks:
                return chunks
    
    # ============================================================================
    # Pattern 5: Generic multi-part indicators
    # ============================================================================
    multi_part_indicators = [
        r"along\s+with",
        r"as\s+well\s+as",
        r"plus",
        r"also\s+create",
        r"and\s+also",
        r"in\s+addition"
    ]
    
    indicator_count = sum(1 for pattern in multi_part_indicators if re.search(pattern, msg_lower))
    
    # If message is long and has multiple indicators, likely multi-part
    if indicator_count >= 1 and len(msg_lower.split()) > 15:
        # Use LLM-based detection as fallback (will be handled by normal flow)
        # For now, return empty to use normal generation
        pass
    
    return []  # Not a multi-part request (or too complex to detect)


def _create_content_chunk(content_type: str, topic: str, original_message: str) -> Optional[Dict[str, str]]:
    """Create a chunk definition for a specific content type."""
    prompts = {
        "blog": {
            "type": "blog_post",
            "prompt": f"Write a comprehensive blog post {topic}. Include: title, introduction, main content (3-5 key points), conclusion, and relevant tags. Keep it engaging and SEO-friendly. Word count: 500-800 words.",
            "label": "Blog Post"
        },
        "x": {
            "type": "x_post",
            "prompt": f"Create a concise X (Twitter) post promoting content about {topic}. Include: hook, key benefit, call-to-action, and relevant hashtags. Character limit: 280 characters.",
            "label": "X (Twitter) Post"
        },
        "facebook": {
            "type": "facebook_ad",
            "prompt": f"Create a Facebook ad copy with static image description for promoting content about {topic}. Include: headline, ad body (100-150 words), call-to-action button text, image description (dimensions, style, colors), and targeting suggestions.",
            "label": "Facebook Ad"
        },
        "instagram": {
            "type": "instagram_post",
            "prompt": f"Create an Instagram post (carousel or single) promoting content about {topic}. Include: caption (with hashtags), image description, and engagement hooks.",
            "label": "Instagram Post"
        },
        "linkedin": {
            "type": "linkedin_post",
            "prompt": f"Create a professional LinkedIn post promoting content about {topic}. Include: hook, value proposition, call-to-action, and relevant hashtags.",
            "label": "LinkedIn Post"
        },
        "email": {
            "type": "email_newsletter",
            "prompt": f"Create an email newsletter promoting content about {topic}. Include: subject line, opening, key points, call-to-action, and closing.",
            "label": "Email Newsletter"
        },
        "youtube": {
            "type": "youtube_video",
            "prompt": f"Create a YouTube video script and description for content about {topic}. Include: title, hook, main content outline, call-to-action, description, and tags.",
            "label": "YouTube Video"
        },
        "tiktok": {
            "type": "tiktok_video",
            "prompt": f"Create a TikTok video script for content about {topic}. Include: hook, main content (15-60 seconds), trending sounds/music suggestions, hashtags, and caption.",
            "label": "TikTok Video"
        },
        "pinterest": {
            "type": "pinterest_pin",
            "prompt": f"Create a Pinterest pin description for content about {topic}. Include: title, description, image suggestions, and relevant keywords.",
            "label": "Pinterest Pin"
        },
        "podcast": {
            "type": "podcast_episode",
            "prompt": f"Create a podcast episode outline for content about {topic}. Include: title, intro, main talking points, questions to discuss, and outro.",
            "label": "Podcast Episode"
        },
        "press_release": {
            "type": "press_release",
            "prompt": f"Write a press release about {topic}. Include: headline, dateline, lead paragraph, body paragraphs, boilerplate, and contact information.",
            "label": "Press Release"
        },
        "landing_page": {
            "type": "landing_page",
            "prompt": f"Create a landing page copy for {topic}. Include: headline, subheadline, value proposition, benefits, features, social proof, and call-to-action.",
            "label": "Landing Page"
        },
        "ad_copy": {
            "type": "ad_copy",
            "prompt": f"Create ad copy for {topic}. Include: headline, body copy, call-to-action, and targeting suggestions.",
            "label": "Ad Copy"
        }
    }
    
    return prompts.get(content_type)


def _map_item_to_chunk(item: str, topic: str, original_message: str) -> Optional[Dict[str, str]]:
    """Map a generic item description to a specific content chunk."""
    item_lower = item.lower()
    
    # Map keywords to content types
    if any(kw in item_lower for kw in ["blog", "article", "post"]):
        return _create_content_chunk("blog", topic, original_message)
    elif any(kw in item_lower for kw in ["x", "twitter", "tweet"]):
        return _create_content_chunk("x", topic, original_message)
    elif any(kw in item_lower for kw in ["facebook", "fb"]):
        return _create_content_chunk("facebook", topic, original_message)
    elif any(kw in item_lower for kw in ["instagram", "ig", "reel"]):
        return _create_content_chunk("instagram", topic, original_message)
    elif "linkedin" in item_lower:
        return _create_content_chunk("linkedin", topic, original_message)
    elif any(kw in item_lower for kw in ["email", "newsletter"]):
        return _create_content_chunk("email", topic, original_message)
    elif any(kw in item_lower for kw in ["youtube", "video"]):
        return _create_content_chunk("youtube", topic, original_message)
    elif "tiktok" in item_lower:
        return _create_content_chunk("tiktok", topic, original_message)
    elif "pinterest" in item_lower:
        return _create_content_chunk("pinterest", topic, original_message)
    elif any(kw in item_lower for kw in ["podcast", "episode"]):
        return _create_content_chunk("podcast", topic, original_message)
    elif any(kw in item_lower for kw in ["press release", "announcement"]):
        return _create_content_chunk("press_release", topic, original_message)
    elif any(kw in item_lower for kw in ["landing page", "sales page"]):
        return _create_content_chunk("landing_page", topic, original_message)
    elif any(kw in item_lower for kw in ["ad", "advertisement"]):
        return _create_content_chunk("ad_copy", topic, original_message)
    
    # If no specific match, create a generic chunk
    return {
        "type": "generic_content",
        "prompt": f"Create content about {item} for {topic}. Be comprehensive and detailed.",
        "label": item.capitalize()
    }


def generate_chunk(chunk: Dict[str, str], context: List[Dict[str, str]] = None, use_grok: bool = True) -> str:
    """
    Generate a single chunk of content.
    
    Args:
        chunk: Dict with 'type', 'prompt', 'label'
        context: Previous conversation context (optional)
        use_grok: Whether to use Grok (faster) or local CEA
    
    Returns:
        Generated content string
    """
    try:
        # Build prompt with context if available
        full_prompt = chunk["prompt"]
        if context:
            # Add relevant context (last 2-3 messages)
            context_str = "\n".join([
                f"{msg.get('role', 'user')}: {msg.get('content', '')[:200]}"
                for msg in context[-3:]
            ])
            full_prompt = f"Context from previous conversation:\n{context_str}\n\n{full_prompt}"
        
        # Add chunk-specific instructions
        full_prompt += f"\n\nIMPORTANT: Generate ONLY the {chunk['label']}. Do not include other content types. When finished, append [END]."
        
        if use_grok:
            logging.info(f"Generating {chunk['label']} using Grok")
            messages = [{"role": "user", "content": full_prompt}]
            result = grok_chat(messages, None)
        else:
            logging.info(f"Generating {chunk['label']} using local CEA")
            # Use reasonable token limit for each chunk
            max_tokens = {
                "blog_post": 1200,
                "x_post": 200,
                "facebook_ad": 400,
                "instagram_post": 300,
                "linkedin_post": 400,
                "email_newsletter": 500,
                "youtube_video": 800,
                "tiktok_video": 300,
                "pinterest_pin": 200,
                "podcast_episode": 600,
                "press_release": 700,
                "landing_page": 1000,
                "ad_copy": 400,
                "generic_content": 600
            }.get(chunk["type"], 600)
            
            result = call_local_cea(
                full_prompt,
                num_predict=max_tokens,
                temperature=0.7,
                stream=True
            )
        
        # Remove [END] marker if present
        result = result.strip().replace("[END]", "").strip()
        
        logging.info(f"Generated {chunk['label']}: {len(result)} characters")
        return result
        
    except Exception as e:
        logging.error(f"Error generating {chunk['label']}: {e}")
        return f"[Error generating {chunk['label']}: {str(e)}]"


def generate_chunked_content(user_message: str, context: List[Dict[str, str]] = None, use_grok: bool = True) -> str:
    """
    Main entry point: Detect multi-part request and generate chunks separately.
    
    Args:
        user_message: User's request
        context: Previous conversation context
        use_grok: Whether to use Grok for generation
    
    Returns:
        Combined response with all chunks
    """
    chunks = detect_multi_part_request(user_message)
    
    if not chunks:
        # Not a multi-part request - return None to use normal flow
        return None
    
    logging.info(f"Detected multi-part request with {len(chunks)} chunks: {[c['label'] for c in chunks]}")
    
    # Generate each chunk independently
    results = []
    for i, chunk in enumerate(chunks, 1):
        logging.info(f"Generating chunk {i}/{len(chunks)}: {chunk['label']}")
        content = generate_chunk(chunk, context, use_grok)
        
        # Format the chunk with a clear header
        formatted = f"### {chunk['label']}\n\n{content}\n"
        results.append(formatted)
    
    # Combine all chunks
    combined = "\n---\n\n".join(results)
    
    logging.info(f"Chunked generation complete: {len(combined)} total characters")
    return combined

