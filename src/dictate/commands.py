"""Voice command parsing, personal dictionary, and per-app tone selection.

Command detection is deliberately deterministic (regex, not LLM): commands
must never misfire because a model felt creative, and dictated text must
never be executed as a command unless it exactly matches a known phrase.
"""

import re
from pathlib import Path

DICTIONARY_PATH = Path.home() / ".config" / "dictate" / "dictionary.txt"

# spoken style → instruction handed to the rewrite prompt
REWRITE_STYLES = {
    "formal": "formal and professional",
    "professional": "formal and professional",
    "casual": "casual and friendly",
    "friendly": "casual and friendly",
    "polite": "polite and warm",
    "shorter": "much more concise, keeping every key point",
    "more concise": "much more concise, keeping every key point",
    "longer": "more detailed and explicit",
    "bullet points": "a bulleted list (start each line with '- ')",
    "a bullet list": "a bulleted list (start each line with '- ')",
    "a list": "a bulleted list (start each line with '- ')",
}

# ASR often inserts commas at speech pauses ("Make it, formal."), so every
# junction tolerates an optional comma.
_POLITE = r"(?:(?:can|could|would) you,? |please,? )?"
_SCRATCH_RE = re.compile(
    rf"^\s*{_POLITE}(?:scratch|undo|delete),? that(?:,? please)?[.!]?\s*$",
    re.IGNORECASE,
)
_REWRITE_RE = re.compile(
    rf"^\s*{_POLITE}(?:make (?:it|this|that)|rewrite (?:it|this|that)(?: as)?),?\s+"
    r"(?:way |a bit |a little )?(.+?)(?:,? please)?[.!]?\s*$",
    re.IGNORECASE,
)
_DICT_ADD_RE = re.compile(
    rf"^\s*{_POLITE}add (.+?) to (?:my |the )?dictionary(?:,? please)?[.!]?\s*$",
    re.IGNORECASE,
)

# dictation-time list trigger: "bullet points: buy milk, call mom, ..."
_LIST_PREFIX_RE = re.compile(
    r"^\s*(?:in |as |make )?(?:bullet points?|a bullet list|a list|list form)[:,.]?\s+(.+)$",
    re.IGNORECASE | re.DOTALL,
)


def extract_list_request(text: str) -> str | None:
    """If the dictation starts with a list trigger ("bullet points: ..."),
    return the remainder to be formatted as bullets; else None."""
    m = _LIST_PREFIX_RE.match(text)
    return m.group(1).strip() if m else None


# inline style: "Make it formal. Can you send me the report" — command and
# content in one utterance. Requires punctuation after the style so partial
# matches inside normal sentences ("make it formal enough to...") don't fire.
_STYLE_PREFIX_RE = re.compile(
    r"^\s*make (?:it|this|that),?\s+(?:way |a bit |a little )?"
    r"(?P<style>[A-Za-z ]+?)[.,:]\s+(?P<rest>.+)$",
    re.IGNORECASE | re.DOTALL,
)


def extract_style_request(text: str) -> tuple[str, str] | None:
    """If the dictation starts with "make it <style>." followed by content,
    return (style_instruction, content); else None. Unknown styles → None."""
    m = _STYLE_PREFIX_RE.match(text)
    if not m:
        return None
    style = _normalize_style(m.group("style"))
    if style is None:
        return None
    return style, m.group("rest").strip()

MAX_DICTIONARY_WORD_LEN = 40


def _normalize_style(style: str) -> str | None:
    style = style.strip().lower()
    if style in REWRITE_STYLES:
        return REWRITE_STYLES[style]
    if style.startswith("more ") and style[5:] in REWRITE_STYLES:
        return REWRITE_STYLES[style[5:]]
    return None


def parse_command(text: str) -> tuple[str, str] | None:
    """Return ("scratch", ""), ("rewrite", style), ("dict_add", word), or None.

    Unknown rewrite styles return None so e.g. "make it work by Friday" is
    inserted as normal dictation instead of being swallowed as a command.
    """
    if _SCRATCH_RE.match(text):
        return ("scratch", "")
    m = _REWRITE_RE.match(text)
    if m:
        style = _normalize_style(m.group(1))
        if style is not None:
            return ("rewrite", style)
        return None
    m = _DICT_ADD_RE.match(text)
    if m:
        word = m.group(1).strip().strip(".")
        if word and len(word) <= MAX_DICTIONARY_WORD_LEN and "\n" not in word:
            return ("dict_add", word)
    return None


# ---- personal dictionary ----


def load_dictionary() -> list[str]:
    try:
        words = [w.strip() for w in DICTIONARY_PATH.read_text().splitlines()]
        return [w for w in words if w]
    except OSError:
        return []


def add_to_dictionary(word: str) -> None:
    words = load_dictionary()
    if word.lower() in {w.lower() for w in words}:
        return
    DICTIONARY_PATH.parent.mkdir(parents=True, exist_ok=True)
    DICTIONARY_PATH.write_text("\n".join([*words, word]) + "\n")


def apply_dictionary_casing(text: str, words: list[str]) -> str:
    """Deterministically enforce the user's spelling/casing for known words.

    Lookaround boundaries (not \\b) so words edged with symbols ("C++",
    "Node.js") still match; lambda replacement so backslashes in a word can
    never be interpreted as regex group references.
    """
    for word in words:
        pattern = rf"(?<!\w){re.escape(word)}(?!\w)"
        text = re.sub(pattern, lambda _m: word, text, flags=re.IGNORECASE)
    return text


# ---- per-app tone ----

CASUAL_BUNDLES = {
    "com.apple.MobileSMS",  # Messages
    "com.tinyspeck.slackmacgap",  # Slack
    "com.hnc.Discord",
    "net.whatsapp.WhatsApp",
    "ru.keepcoder.Telegram",
}
FORMAL_BUNDLES = {
    "com.apple.mail",
    "com.microsoft.Outlook",
    "com.microsoft.Word",
    "com.apple.Pages",
}

TONE_INSTRUCTIONS = {
    "casual": (
        "The user is writing a casual chat message: keep contractions and a "
        "relaxed, friendly voice; lowercase-style informality is fine if the "
        "speaker used it."
    ),
    "formal": (
        "The user is writing in a professional context: use complete "
        "sentences, professional wording, and proper punctuation."
    ),
    "neutral": "",
}


def tone_for_bundle(bundle_id: str | None) -> str:
    if bundle_id in CASUAL_BUNDLES:
        return "casual"
    if bundle_id in FORMAL_BUNDLES:
        return "formal"
    return "neutral"
