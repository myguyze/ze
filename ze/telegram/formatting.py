import html as _html
import re

# ── Pattern definitions ───────────────────────────────────────────────────────

_FENCE = re.compile(r'```([^\n`]*)?\n?([\s\S]*?)```')
_INLINE_CODE = re.compile(r'`([^`\n]+)`')

# Inline emphasis — applied after bold+italic to avoid partial matches
_BOLD_ITALIC = re.compile(r'\*\*\*(.+?)\*\*\*')
_BOLD = re.compile(r'\*\*(.+?)\*\*')
# Italic: must not be preceded/followed by another *, and content must be non-empty
_ITALIC_STAR = re.compile(r'(?<!\*)\*(?!\s)([^*\n]+?)(?<!\s)\*(?!\*)')
# Underscores: only when flanked by word boundaries to avoid matching snake_case
_ITALIC_UNDER = re.compile(r'(?<!\w)_(?!\s)([^_\n]+?)(?<!\s)_(?!\w)')
_STRIKE = re.compile(r'~~(.+?)~~')

# Block-level — only match at line start
_H3 = re.compile(r'^###[ \t](.+)$', re.MULTILINE)
_H2 = re.compile(r'^##[ \t](.+)$', re.MULTILINE)
_H1 = re.compile(r'^#[ \t](.+)$', re.MULTILINE)

_LINK = re.compile(r'\[([^\]\n]+)\]\((https?://[^)\n]+)\)')

_UL = re.compile(r'^[ \t]*[-*+][ \t](.+)$', re.MULTILINE)
_OL = re.compile(r'^[ \t]*(\d+)\.[ \t](.+)$', re.MULTILINE)

# Separator lines (---, ***, ___) → em-dash line
_HR = re.compile(r'^[ \t]*[-*_]{3,}[ \t]*$', re.MULTILINE)

# Blockquotes — matched after HTML escaping, so > becomes &gt;
_BLOCKQUOTE = re.compile(r'^&gt;[ \t]?(.+)$', re.MULTILINE)

_PLACEHOLDER_BLOCK = '\x00B{}\x00'
_PLACEHOLDER_INLINE = '\x00I{}\x00'


def md_to_html(text: str) -> str:
    """Convert LLM markdown to Telegram-compatible HTML.

    Handles: code blocks, inline code, bold, italic, strikethrough, headers,
    bullet/numbered lists, blockquotes, links, and horizontal rules.
    Safe: HTML-escapes all prose before applying tag patterns.
    """
    code_blocks: list[str] = []
    inline_codes: list[str] = []

    def stash_fence(m: re.Match) -> str:
        content = _html.escape(m.group(2).strip())
        idx = len(code_blocks)
        code_blocks.append(f'<pre><code>{content}</code></pre>')
        return _PLACEHOLDER_BLOCK.format(idx)

    def stash_inline(m: re.Match) -> str:
        content = _html.escape(m.group(1))
        idx = len(inline_codes)
        inline_codes.append(f'<code>{content}</code>')
        return _PLACEHOLDER_INLINE.format(idx)

    text = _FENCE.sub(stash_fence, text)
    text = _INLINE_CODE.sub(stash_inline, text)

    # Escape HTML special chars in all remaining prose
    text = _html.escape(text)

    # Inline formatting (precedence: bold+italic > bold > italic > strike)
    text = _BOLD_ITALIC.sub(lambda m: f'<b><i>{m.group(1)}</i></b>', text)
    text = _BOLD.sub(lambda m: f'<b>{m.group(1)}</b>', text)
    text = _ITALIC_STAR.sub(lambda m: f'<i>{m.group(1)}</i>', text)
    text = _ITALIC_UNDER.sub(lambda m: f'<i>{m.group(1)}</i>', text)
    text = _STRIKE.sub(lambda m: f'<s>{m.group(1)}</s>', text)

    # Links — URL already HTML-escaped by the step above (& → &amp;), which is
    # correct inside href attributes
    text = _LINK.sub(lambda m: f'<a href="{m.group(2)}">{m.group(1)}</a>', text)

    # Block-level: headers, lists, blockquotes, HRs
    text = _H3.sub(lambda m: f'<b>{m.group(1)}</b>', text)
    text = _H2.sub(lambda m: f'<b>{m.group(1)}</b>', text)
    text = _H1.sub(lambda m: f'<b><u>{m.group(1)}</u></b>', text)

    text = _BLOCKQUOTE.sub(lambda m: f'<blockquote>{m.group(1)}</blockquote>', text)
    text = _UL.sub(lambda m: f'• {m.group(1)}', text)
    text = _OL.sub(lambda m: f'{m.group(1)}. {m.group(2)}', text)

    text = _HR.sub('──────────', text)

    # Restore stashed spans and blocks
    for i, span in enumerate(inline_codes):
        text = text.replace(_PLACEHOLDER_INLINE.format(i), span)
    for i, block in enumerate(code_blocks):
        text = text.replace(_PLACEHOLDER_BLOCK.format(i), block)

    return text.strip()


def split_html(text: str, limit: int = 4096) -> list[str]:
    """Split HTML text into Telegram-safe chunks without breaking paragraphs."""
    if len(text) <= limit:
        return [text]

    chunks: list[str] = []
    current = ''

    for para in text.split('\n\n'):
        candidate = f'{current}\n\n{para}' if current else para
        if len(candidate) <= limit:
            current = candidate
        else:
            if current:
                chunks.append(current)
            # para itself may exceed limit — split at newlines
            if len(para) <= limit:
                current = para
            else:
                lines, current = para.split('\n'), ''
                for line in lines:
                    candidate = f'{current}\n{line}' if current else line
                    if len(candidate) <= limit:
                        current = candidate
                    else:
                        if current:
                            chunks.append(current)
                        # hard cut if a single line still exceeds limit
                        while len(line) > limit:
                            chunks.append(line[:limit])
                            line = line[limit:]
                        current = line

    if current:
        chunks.append(current)

    return [c for c in chunks if c.strip()]
