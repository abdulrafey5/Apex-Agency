# Chunked Generation - Supported Prompt Patterns

This document lists all the prompt patterns that will trigger chunked generation (Option B) to avoid truncation.

## ✅ Supported Patterns

### 1. **Social Media Content Combinations**

**Pattern:** Multiple social platforms mentioned

**Examples:**
- "Create a blog post about mindfulness, an X post, and a Facebook ad"
- "Prepare a blog post on nutrition, along with Instagram and LinkedIn posts"
- "Write a blog post, X post, and email newsletter about fitness"
- "Create blog + Twitter + Facebook + Instagram content for wellness"
- "Make a blog post, YouTube video script, and TikTok script about meditation"

**Supported Platforms:**
- Blog/Article
- X (Twitter)
- Facebook
- Instagram
- LinkedIn
- Email/Newsletter
- YouTube
- TikTok
- Pinterest
- Podcast

### 2. **Action Verbs + Multiple Items**

**Pattern:** Action verb + "and" or comma-separated items

**Examples:**
- "Create a marketing plan and social media strategy"
- "Write a blog post and press release about our launch"
- "Prepare a landing page and email campaign"
- "Develop a content calendar and ad campaign"
- "Make a blog post, newsletter, and podcast episode"

**Action Verbs:**
- create, make, write, prepare, generate, develop, build, design

### 3. **Numbered/Bulleted Lists**

**Pattern:** Explicit numbered or bulleted lists

**Examples:**
- "1. Blog post 2. X post 3. Facebook ad"
- "Create: 1. Blog post 2. Email newsletter 3. LinkedIn post"
- "• Blog post • X post • Facebook ad"
- "- Blog post - X post - Facebook ad"

### 4. **Business/Marketing Multi-Part**

**Pattern:** Business documents with multiple components

**Examples:**
- "Create a marketing plan with strategy, tactics, and budget"
- "Write a business plan including strategy, timeline, and metrics"
- "Develop a content calendar with strategy, tactics, and KPIs"
- "Create an email campaign with strategy, timeline, and metrics"

**Components Detected:**
- Strategy
- Tactics
- Budget
- Timeline
- Metrics/KPIs

### 5. **Multi-Part Indicators**

**Pattern:** Phrases indicating multiple parts

**Examples:**
- "Create a blog post along with social media posts"
- "Write content as well as ad copy"
- "Prepare a blog post plus email newsletter"
- "Create blog content and also social media posts"
- "Make a blog post in addition to press release"

**Indicators:**
- along with
- as well as
- plus
- also create
- and also
- in addition

### 6. **Complex Content Requests**

**Pattern:** Multiple content types in one request

**Examples:**
- "Create a blog post for the Mindfulness section, a post on X about the article, and a Facebook ad with static image"
- "Prepare blog content, social media posts, and email newsletter for product launch"
- "Write a comprehensive marketing package: blog post, social posts, email sequence, and landing page"

---

## 🎯 How It Works

1. **Detection:** System analyzes your prompt for multi-part indicators
2. **Splitting:** Request is split into separate chunks
3. **Generation:** Each chunk is generated independently (no truncation)
4. **Combination:** All chunks are combined into final response

---

## 📊 Content Types Supported

| Content Type | Token Limit | Description |
|-------------|-------------|-------------|
| Blog Post | 1200 | Comprehensive article (500-800 words) |
| X Post | 200 | Twitter/X post (280 chars) |
| Facebook Ad | 400 | Ad copy + image description |
| Instagram Post | 300 | Caption + image description |
| LinkedIn Post | 400 | Professional post |
| Email Newsletter | 500 | Email content |
| YouTube Video | 800 | Script + description |
| TikTok Video | 300 | Script + hashtags |
| Pinterest Pin | 200 | Pin description |
| Podcast Episode | 600 | Episode outline |
| Press Release | 700 | Press release |
| Landing Page | 1000 | Landing page copy |
| Ad Copy | 400 | Generic ad copy |

---

## ⚙️ Configuration

Enable/disable chunked generation via environment variable:

```bash
CEA_USE_CHUNKED_GENERATION=true  # Default: true
```

---

## 🔍 Detection Logic

The system checks for:
1. Multiple content type keywords (blog + X + Facebook)
2. Action verbs with multiple items
3. Numbered/bulleted lists
4. Business document components
5. Multi-part indicator phrases

If detected → Uses chunked generation
If not detected → Uses normal generation flow

---

## 💡 Tips

1. **Be explicit:** "Create blog post AND X post" works better than "create content"
2. **Use action verbs:** "create", "make", "write", "prepare" trigger detection
3. **List items:** Numbered or bulleted lists are easily detected
4. **Mention platforms:** Explicitly mention platforms (X, Facebook, Instagram, etc.)

---

## 🚫 What Won't Trigger Chunked Generation

- Single content type: "Create a blog post"
- Simple questions: "What is mindfulness?"
- Single-step requests: "Write an email"
- Vague requests: "Create some content"

These will use the normal generation flow (which is fine for single-part requests).

