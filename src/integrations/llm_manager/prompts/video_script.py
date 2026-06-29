from src.integrations.llm_manager.schemas import VideoIdeaOutput
from src.models.channel import Channel

SCRIPT_SYSTEM_PROMPT = """You are a short-form video scriptwriter.
Output ONLY valid JSON — no markdown fences, no preamble, no wrapper objects.
The JSON root must contain exactly: title, script_segments, voiceover_text, hashtags, thumbnail_description."""


def _summarize_system_prompt(system_prompt: str, max_length: int = 500) -> str:
    stripped = system_prompt.strip()
    if len(stripped) <= max_length:
        return stripped
    return f"{stripped[:max_length].rstrip()}..."


def build_video_script_prompt(
    channel: Channel,
    idea: VideoIdeaOutput,
) -> tuple[str, str]:
    key_points = "\n".join(f"- {point}" for point in idea.key_points)
    keywords = ", ".join(idea.suggested_keywords)
    system_prompt_summary = _summarize_system_prompt(channel.system_prompt)
    user_prompt = f"""
Write a complete short-form video script based on this idea.

Channel Info:
- Name: {channel.name}
- Niche: {channel.niche}
- Target Audience: {channel.target_audience}
- Language: {channel.language}
- Tone of Voice: {channel.tone_of_voice}

Video Idea:
- Title: {idea.title}
- Hook: {idea.hook}
- Mood: {idea.mood}
- Estimated Duration (seconds): {idea.estimated_duration_seconds}
- Key Points:
{key_points}
- Suggested Keywords: {keywords}

Channel Editorial Style (summary):
{system_prompt_summary}

Return a single flat JSON object with EXACTLY these top-level keys:
- title (string)
- script_segments (array of strings, 3-6 items)
- voiceover_text (string, 50-2000 characters, full narration)
- hashtags (array of strings, include #)
- thumbnail_description (string)

Do NOT wrap the response in video_metadata, script, data, or any other parent key.
Do NOT add extra top-level keys.

Return ONLY this flat JSON shape:
{{
  "title": "...",
  "script_segments": ["Hook line", "Point 1", "CTA"],
  "voiceover_text": "Full spoken script here...",
  "hashtags": ["#tag1", "#tag2"],
  "thumbnail_description": "Short visual description"
}}
"""
    return SCRIPT_SYSTEM_PROMPT, user_prompt.strip()
