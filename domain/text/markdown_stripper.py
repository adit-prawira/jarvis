import re

_FENCED_CODE = re.compile(r"```.*?```", re.DOTALL)
_IMAGE = re.compile(r"!\[([^\]]*)\]\([^)]*\)")
_LINK = re.compile(r"\[([^\]]+)\]\([^)]*\)")
_BOLD_ITALIC = re.compile(r"(\*\*\*|___)(.+?)\1")
_BOLD = re.compile(r"(\*\*|__)(.+?)\1")
_ITALIC_STAR = re.compile(r"\*([^*]+)\*")
_ITALIC_UNDERSCORE = re.compile(r"(?<!\w)_([^_]+)_(?!\w)")
_INLINE_CODE = re.compile(r"`([^`]+)`")
_HEADER = re.compile(r"^\s{0,3}#{1,6}[ \t]+", re.MULTILINE)
_BLOCKQUOTE = re.compile(r"^[ \t]*>[ \t]?", re.MULTILINE)
_HORIZONTAL_RULE = re.compile(r"^\s{0,3}([-*_])([ \t]*\1){2,}[ \t]*$", re.MULTILINE)
_NUMBERED_ITEM = re.compile(r"^[ \t]*\d+[.)][ \t]+", re.MULTILINE)
_BULLET_ITEM = re.compile(r"^[ \t]*[-*+][ \t]+", re.MULTILINE)


class MarkdownStripper:
    @staticmethod
    def strip(text: str) -> str:
        sanitised = _FENCED_CODE.sub("", text)
        sanitised = _IMAGE.sub(r"\1", sanitised)
        sanitised = _LINK.sub(r"\1", sanitised)
        sanitised = _BOLD_ITALIC.sub(r"\2", sanitised)
        sanitised = _BOLD.sub(r"\2", sanitised)
        sanitised = _ITALIC_STAR.sub(r"\1", sanitised)
        sanitised = _ITALIC_UNDERSCORE.sub(r"\1", sanitised)
        sanitised = _INLINE_CODE.sub(r"\1", sanitised)
        sanitised = _HEADER.sub("", sanitised)
        sanitised = _BLOCKQUOTE.sub("", sanitised)
        sanitised = _HORIZONTAL_RULE.sub("", sanitised)
        sanitised = _NUMBERED_ITEM.sub("", sanitised)
        sanitised = _BULLET_ITEM.sub("", sanitised)
        return sanitised.strip()
