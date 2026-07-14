"""Voice command parsing, dictionary, and tone selection (all deterministic)."""

from dictate import commands as commands_mod
from dictate.commands import (
    add_to_dictionary,
    apply_dictionary_casing,
    extract_list_request,
    extract_style_request,
    load_dictionary,
    parse_command,
    tone_for_bundle,
)


# ---- command parsing ----

def test_scratch_variants():
    for phrase in ("Scratch that.", "scratch that", "Undo that!", "Delete that."):
        assert parse_command(phrase) == ("scratch", "")


def test_rewrite_known_styles():
    kind, style = parse_command("Make it formal.")
    assert kind == "rewrite" and "formal" in style
    kind, style = parse_command("make that shorter")
    assert kind == "rewrite" and "concise" in style
    kind, style = parse_command("Rewrite it as bullet points.")
    assert kind == "rewrite" and "bulleted" in style


def test_rewrite_natural_variants():
    """Regression: 'make it formal isn't working' — spoken variants must parse."""
    for phrase in (
        "Make it more formal.",
        "Can you make it formal?"[:-1] + ".",  # "Can you make it formal."
        "Please make it shorter.",
        "Make this casual.",
        "Make it a bit more polite.",
        "Make it formal, please.",
        "Could you make it more professional.",
    ):
        cmd = parse_command(phrase)
        assert cmd is not None and cmd[0] == "rewrite", phrase


def test_rewrite_tolerates_asr_commas():
    """Regression: Parakeet punctuates pauses — 'Make it, formal.' must parse."""
    for phrase in (
        "Make it, formal.",
        "Make it, more formal.",
        "Can you, make it formal.",
        "Scratch, that.",
    ):
        assert parse_command(phrase) is not None, phrase


def test_list_prefix_extraction():
    assert extract_list_request(
        "Bullet points: buy milk, call mom, and email the professor."
    ) == "buy milk, call mom, and email the professor."
    assert extract_list_request("In bullet points buy milk and call mom") == (
        "buy milk and call mom"
    )
    assert extract_list_request("As a list, first do X then do Y") == (
        "first do X then do Y"
    )


def test_list_prefix_not_triggered_by_normal_speech():
    for phrase in (
        "The bullet points in that slide were great.",
        "I made a list of groceries yesterday.",
        "He points at the board a lot.",
    ):
        assert extract_list_request(phrase) is None, phrase


SIDDHARTH_UTTERANCE = (
    "Make it formal. Can you send an email to Siddharth saying, "
    '"Hey, what\'s up? Are you in San Francisco?"'
)


def test_inline_style_prefix_real_user_utterance():
    """Regression: command + content in one breath must style the content."""
    assert parse_command(SIDDHARTH_UTTERANCE) is None  # not a bare command
    result = extract_style_request(SIDDHARTH_UTTERANCE)
    assert result is not None
    style, rest = result
    assert "formal" in style
    assert rest.startswith("Can you send an email to Siddharth")


def test_inline_style_prefix_variants():
    assert extract_style_request("Make it casual. hey are you around")
    assert extract_style_request("Make it more formal: send me the report")
    assert extract_style_request("make it shorter, we need the numbers today")


def test_inline_style_prefix_not_triggered_by_normal_speech():
    # no punctuation separator, or unknown style → normal dictation
    assert extract_style_request("Make it formal enough to impress them.") is None
    assert extract_style_request("Make it work. We ship on Friday.") is None
    assert extract_style_request("Make it formal.") is None  # bare command, no content


def test_scratch_natural_variants():
    for phrase in ("Please undo that.", "Can you scratch that.", "Scratch that, please."):
        assert parse_command(phrase) == ("scratch", ""), phrase


def test_unknown_rewrite_style_is_dictation():
    # "make it work by Friday" must be inserted as text, not eaten as a command
    assert parse_command("Make it work by Friday.") is None
    assert parse_command("Make it more fun for the kids next week.") is None


def test_overlong_dictionary_word_rejected():
    long_word = "x" * 60
    assert parse_command(f"Add {long_word} to my dictionary.") is None


def test_dict_add():
    assert parse_command("Add Siddharth to my dictionary.") == ("dict_add", "Siddharth")
    assert parse_command("add MLX to the dictionary") == ("dict_add", "MLX")


def test_normal_dictation_is_not_a_command():
    for phrase in (
        "Hello world, this is a test.",
        "I need to scratch that itch later.",
        "Can you make it to dinner?",
        "The dictionary definition of add.",
    ):
        assert parse_command(phrase) is None


# ---- personal dictionary ----

def test_dictionary_roundtrip_and_dedupe(tmp_path, monkeypatch):
    monkeypatch.setattr(commands_mod, "DICTIONARY_PATH", tmp_path / "dict.txt")
    assert load_dictionary() == []
    add_to_dictionary("Siddharth")
    add_to_dictionary("MLX")
    add_to_dictionary("siddharth")  # dupe, different case → ignored
    assert load_dictionary() == ["Siddharth", "MLX"]


def test_dictionary_casing_enforced():
    words = ["Siddharth", "MLX", "Wispr Flow"]
    out = apply_dictionary_casing(
        "siddharth built this with mlx, inspired by wispr flow.", words
    )
    assert out == "Siddharth built this with MLX, inspired by Wispr Flow."


def test_dictionary_casing_respects_word_boundaries():
    # "mlx" inside another word must not be touched
    assert apply_dictionary_casing("htmlx is not mlx", ["MLX"]) == "htmlx is not MLX"


def test_dictionary_casing_symbol_edged_words():
    assert apply_dictionary_casing("i love c++ a lot", ["C++"]) == "i love C++ a lot"
    assert apply_dictionary_casing("using node.js here", ["Node.js"]) == (
        "using Node.js here"
    )


def test_dictionary_casing_backslash_safe():
    # a backslash in a dictionary word must never be treated as a group ref
    weird = r"foo\1bar"
    assert apply_dictionary_casing(r"say foo\1bar again", [weird]) == (
        r"say foo\1bar again"
    )


# ---- tone selection ----

def test_tone_mapping():
    assert tone_for_bundle("com.apple.MobileSMS") == "casual"
    assert tone_for_bundle("com.tinyspeck.slackmacgap") == "casual"
    assert tone_for_bundle("com.apple.mail") == "formal"
    assert tone_for_bundle("com.apple.Notes") == "neutral"
    assert tone_for_bundle(None) == "neutral"
