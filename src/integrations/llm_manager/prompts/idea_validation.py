from src.integrations.llm_manager.schemas import VideoIdeaOutput
from src.models.channel import Channel

VALIDATION_SYSTEM_PROMPT = """You are a short-form video content quality reviewer.
Your output MUST be valid JSON only — no preamble, no markdown fences.
Follow the provided JSON schema exactly. Keep reason to a maximum of 2 sentences."""


def _summarize_system_prompt(system_prompt: str, max_length: int = 500) -> str:
    stripped = system_prompt.strip()
    if len(stripped) <= max_length:
        return stripped
    return f"{stripped[:max_length].rstrip()}..."


def build_idea_validation_prompt(
    channel: Channel,
    idea: VideoIdeaOutput,
) -> tuple[str, str]:
    key_points = "\n".join(f"- {point}" for point in idea.key_points)
    keywords = ", ".join(idea.suggested_keywords)
    system_prompt_summary = _summarize_system_prompt(channel.system_prompt)
    user_prompt = f"""
Evaluate whether this video idea is strong enough to produce for the channel.

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

Score the idea from 1 (poor) to 10 (excellent) on fit, originality, hook strength, and audience appeal.
Set is_acceptable to true only if the idea is good enough to move forward to scripting.
Return reason in at most 2 sentences.
"""
    return VALIDATION_SYSTEM_PROMPT, user_prompt.strip()
