from src.models.channel import Channel

IDEA_SYSTEM_PROMPT = """You are a viral short-form video strategist.
Your output MUST be valid JSON only — no preamble, no markdown fences.
Follow the provided JSON schema exactly."""


def _format_recent_context_block(recent_context: list[dict]) -> str:
    lines: list[str] = []
    for index, entry in enumerate(recent_context, start=1):
        title = entry.get("title", "")
        hook = entry.get("hook", "")
        hashtags = entry.get("hashtags", [])
        hashtag_text = (
            ", ".join(hashtags) if isinstance(hashtags, list) else str(hashtags)
        )
        lines.append(
            f"{index}. Title: {title}\n   Hook: {hook}\n   Hashtags: {hashtag_text}"
        )
    return "\n".join(lines)


def build_video_idea_prompt(
    channel: Channel,
    recent_context: list[dict] | None = None,
    news_item: dict | None = None,
) -> tuple[str, str]:
    base_hashtags = ", ".join(channel.base_hashtags)
    recent_context_block = ""
    if recent_context:
        recent_context_block = f"""
Recent Videos (avoid repeating these hooks and hashtags):
{_format_recent_context_block(recent_context)}

Generate a fresh idea that does not reuse the hooks or hashtags listed above.
"""
    news_block = ""
    if news_item:
        news_block = f"""
REQUIRED NEWS SOURCE — your video idea MUST be based on this news story:
- Title: {news_item.get("title", "")}
- Summary: {news_item.get("summary", "")}
- Source URL: {news_item.get("link", "")}
- Author: {news_item.get("author", "")}

Create a short-form video idea that explains or reacts to this specific news story.
Do not invent a different topic — anchor the hook and key points to this article.
"""
    user_prompt = f"""
Generate a compelling video idea for this channel.

Channel Info:
- Name: {channel.name}
- Niche: {channel.niche}
- Target Audience: {channel.target_audience}
- Language: {channel.language}
- Tone of Voice: {channel.tone_of_voice}
- Base Hashtags: {base_hashtags}

Channel System Prompt (editorial style):
{channel.system_prompt}
{recent_context_block}{news_block}
Target video duration: 30-50 seconds.
"""
    return IDEA_SYSTEM_PROMPT, user_prompt.strip()
