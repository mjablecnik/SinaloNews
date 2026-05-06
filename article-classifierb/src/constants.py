from enum import Enum


TAG_TAXONOMY: dict[str, list[str]] = {
    "Politics": ["Czech", "European", "Global", "USA", "Diplomacy"],
    "Economy": ["Finance", "Markets", "Business", "Law", "Crypto", "Jobs"],
    "Technology": ["Software", "Hardware", "AI", "Cybersecurity", "Cloud", "Startups"],
    "Science": ["Research", "Space", "Medicine", "Energy", "Environment"],
    "Security": ["Military", "Conflict", "Terrorism", "Crime", "Defense"],
    "Society": ["Culture", "Education", "Health", "Sports", "Media"],
    "World": ["Disasters", "Migration", "Humanitarian", "Climate"],
}


class ContentType(str, Enum):
    CONSPIRACY_THEORY = "CONSPIRACY_THEORY"
    CLICKBAIT = "CLICKBAIT"
    NO_USEFUL_CONTENT = "NO_USEFUL_CONTENT"
    OPINION_EDITORIAL = "OPINION_EDITORIAL"
    BREAKING_NEWS = "BREAKING_NEWS"
    GENERAL_VALUABLE_CONTENT = "GENERAL_VALUABLE_CONTENT"
    UNIVERSAL_RELEVANT_CONTENT = "UNIVERSAL_RELEVANT_CONTENT"


def validate_content_type(value: str) -> str:
    try:
        return ContentType(value).value
    except ValueError:
        return ContentType.GENERAL_VALUABLE_CONTENT.value


def clamp_score(value: int) -> int:
    return max(0, min(10, value))
