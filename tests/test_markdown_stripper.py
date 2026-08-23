"""Unit tests for MarkdownStripper.strip — given/then format.

The stripper removes markdown formatting (bold/italic, headers, lists, links,
code, blockquotes, rules) but preserves meaningful symbols so spoken prose
still reads naturally.
"""

from domain.text.markdown_stripper import MarkdownStripper


# — boundary: bold, italic, and inline code are stripped to plain text —
def test_given_bold_italic_code_then_stripped():
    text = "**bold** *italic* `code` ***both***"
    assert MarkdownStripper.strip(text) == "bold italic code both"


# — boundary: underscore emphasis is stripped —
def test_given_underscore_emphasis_then_stripped():
    text = "__bold__ and _italic_"
    assert MarkdownStripper.strip(text) == "bold and italic"


# — false-positive guard: snake_case is NOT eaten by underscore-italic —
def test_given_snake_case_then_preserved():
    text = "open main_file.py"
    assert MarkdownStripper.strip(text) == "open main_file.py"


# — boundary: headers, bullets, numbering, blockquotes are flattened —
def test_given_list_markup_then_flattened():
    text = "# Title\n- one\n- two\n1. three\n> quote"
    assert MarkdownStripper.strip(text) == "Title\none\ntwo\nthree\nquote"


# — boundary: a link keeps its label —
def test_given_link_then_keeps_label():
    text = "see [the docs](https://example.com) sir"
    assert MarkdownStripper.strip(text) == "see the docs sir"


# — boundary: an image keeps its alt text —
def test_given_image_then_keeps_alt_text():
    text = "![diagram](img.png) here"
    assert MarkdownStripper.strip(text) == "diagram here"


# — boundary: a horizontal rule vanishes —
def test_given_horizontal_rule_then_empty():
    text = "---"
    assert MarkdownStripper.strip(text) == ""


# — false-positive guard: meaningful symbols are preserved —
def test_given_symbols_then_preserved():
    text = "That's $100, 50% off, C# and 3 + 4."
    assert MarkdownStripper.strip(text) == "That's $100, 50% off, C# and 3 + 4."


# — boundary: plain prose is untouched —
def test_given_plain_text_then_unchanged():
    text = "The time is two thirty, sir."
    assert MarkdownStripper.strip(text) == text


# — boundary: a fenced code block is removed outright —
def test_given_fenced_code_block_then_removed():
    text = "Run this:\n```\npytest tests\n```\nnow."
    assert MarkdownStripper.strip(text) == "Run this:\n\nnow."


# — boundary: empty input stays empty —
def test_given_empty_then_empty():
    text = ""
    assert MarkdownStripper.strip(text) == ""
