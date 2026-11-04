"""Shared layout helpers for the chat pipeline patches.

This file is bind-mounted as ``astrbot/core/pipeline/chat_layout.py``.  It has
no AstrBot imports on purpose: the repo's regression tests load it directly,
and the two patched stages import only these pure functions.

Keeping the rules here means the display bubbles and the TTS text are derived
from the same semantic source instead of being re-split independently.
"""

from __future__ import annotations

import os
import re
from copy import copy
import json
import tempfile
import time
from pathlib import Path

# A bubble should end only at a real sentence boundary.  Tilde / ellipsis are
# included because the bot's persona uses them as sentence enders.
SENTENCE_END = "。！？!?…~～"
_TRAILING_CLOSERS = "\"'”’）)】」》〉"

_EMOJI_MARK = re.compile(r"\[[A-Za-z一-鿿]{1,6}\]")
_NO_REPLY_MARK = re.compile(r"[\[【]\s*NO[_ -]?REPLY\s*[\]】]", re.IGNORECASE)
_FENCED_CODE = re.compile(r"```.*?```", re.DOTALL)
_INLINE_CODE = re.compile(r"`[^`\n]+`")
_URL = re.compile(r"https?://\S+")
_MARKDOWN_MARKS = re.compile(r"(\*\*|__|~~|^#{1,6}\s+|^>\s*)", re.MULTILINE)
_SPACES = re.compile(r"[ \t　]{2,}")
_KEEP_PERIOD = "[[KEEP_PERIOD]]"
VOICE_EMOTIONS = {'excited', 'surprised', 'pouting', 'shy', 'touched'}


def user_voice_request(text: str) -> str | None:
    """Recognize current-user delivery requests, excluding quoted examples."""
    text = _FENCED_CODE.sub('', text or '')
    text = _INLINE_CODE.sub('', text)
    text = re.sub(r'“[^”]*”|「[^」]*」|"[^"\n]*"', '', text)
    negative = re.compile(
        r'(?:不要|别|不用|不想|不需要|停止|禁止)[^，。；;\n!?！？]{0,8}(?:语音|唱|朗读|读给我听)'
        r'|(?:只发|只用|用)文字(?:回复|回答)?|(?:文字|打字)就好'
    )
    positive = re.compile(
        r'(?:发|来|回复)(?:一条|一段|一个|一则|条|段|个)?语音'
        r'|用语音(?:来)?(?:回复|回答|说|讲|读)'
        r'|(?:想听|听听|听一下)你(?:的声音|说话|说|唱)'
        r'|唱(?:一)?(?:首|段|个)|唱歌|来一首歌|朗读|读给我听|念给我听'
    )
    denied = list(negative.finditer(text))
    choices = [(m.start(), 'text') for m in denied]
    # Asking how to implement voice is not asking the bot to speak now.
    informational = re.search(r'(?:如何|怎么|怎样|为什么|原理|代码|配置).{0,25}(?:语音|唱歌|朗读)', text)
    if not informational:
        choices += [(m.start(), 'voice') for m in positive.finditer(text)
                    if not any(n.start() <= m.start() < n.end() for n in denied)]
    return max(choices)[1] if choices else None


def extract_voice_intent(text: str) -> tuple[str, str | None]:
    """Only a trailing, allowlisted control token nominates emotional speech."""
    match = re.search(r'\s*\[\[VOICE:([a-z]+)\]\]\s*$', text)
    if not match:
        return text, None
    if text[:match.start()].count('```') % 2:
        return text, None
    return text[:match.start()].rstrip(), match.group(1) if match.group(1) in VOICE_EMOTIONS | {'requested'} else None


class RareVoiceGate:
    """One global, persistent reservation per ten minutes; no other quotas."""
    def __init__(self, state_path):
        self.state_path = Path(state_path)

    def reserve(self, emotion, now=None):
        if emotion not in VOICE_EMOTIONS:
            return False
        now = time.time() if now is None else now
        try:
            state = json.loads(self.state_path.read_text()) if self.state_path.exists() else {}
            last = state.get('last_voice_at')
            if last is not None and now - float(last) < 600:
                return False
            self.state_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            fd, name = tempfile.mkstemp(prefix='.voice-', dir=self.state_path.parent)
            try:
                with os.fdopen(fd, 'w') as output:
                    json.dump({'last_voice_at': now}, output)
                    output.flush();os.fsync(output.fileno())
                os.replace(name, self.state_path)
            finally:
                if os.path.exists(name):
                    os.unlink(name)
            return True
        except (OSError, ValueError, TypeError, AttributeError):
            return False


def extract_period_intent(text: str) -> tuple[str, list[str]]:
    """Consume explicit period intent before history, segmentation and TTS."""
    kept = []
    chunks = re.split(r"(```.*?```|`[^`\n]+`)", text, flags=re.DOTALL)
    for i in range(0, len(chunks), 2):
        def capture(match):
            kept.append(match.group(1).strip())
            return match.group(1)
        chunks[i] = re.sub(r"([^。！？!?\n]+[。.]+)[ \t]*\[\[KEEP_PERIOD\]\]", capture, chunks[i])
        chunks[i] = chunks[i].replace(_KEEP_PERIOD, '')
    return ''.join(chunks), kept


def _period_key(text: str) -> str:
    return re.sub(r'\s+', '', text.replace('「', '“').replace('」', '”'))


def format_bubble_period(bubble, plain_type, keep_sentences=()):
    """Remove only a bubble's closing period unless its final clause is marked."""
    text = ''.join(c.text for c in bubble if isinstance(c, plain_type))
    ending = re.search(r'([。.]+)(["\'”’）)】」》〉]*\s*)$', text)
    if not ending:
        return bubble
    periods = ending.group(1)
    # An ASCII ellipsis is a separate punctuation mark, not a full stop.
    if periods == '.' * len(periods) and len(periods) > 1:
        return bubble
    if text[:ending.start()].count('`') % 2:
        return bubble
    if periods == '.' and any(m.start() <= ending.start() < m.end() for m in _URL.finditer(text)):
        return bubble
    final_text = text[:ending.end(1)]
    intentional = any(_period_key(final_text).endswith(_period_key(s)) for s in keep_sentences)
    replacement = ('。' if '。' in periods else '.') if intentional else ''
    # Replace by character offsets across Plain components; middle punctuation,
    # quotes, attachments and the original model chain remain untouched.
    result = list(bubble)
    offset = 0
    inserted = False
    for i, comp in enumerate(result):
        if isinstance(comp, plain_type):
            start, end = offset, offset + len(comp.text)
            offset = end
            left, right = max(start, ending.start(1)), min(end, ending.end(1))
            if left >= right:
                continue
            result[i] = copy(comp)
            result[i].text = comp.text[:left-start] + (replacement if not inserted else '') + comp.text[right-start:]
            inserted = True
    return result


def text_ends_sentence(text: str) -> bool:
    """Return True when *text* ends with a sentence boundary.

    Trailing quotes/brackets are ignored so ``好呀。”`` still counts as an
    ending.  Newlines are handled by the caller as hard boundaries.
    """
    if text and text.rstrip(" \t　").endswith("\n"):
        return True
    s = (text or "").rstrip()
    if not s:
        return False
    while s and s[-1] in _TRAILING_CLOSERS:
        s = s[:-1].rstrip()
    return bool(s) and (s[-1] in SENTENCE_END or s.endswith("\n"))


def _is_record(comp, record_type) -> bool:
    return record_type is not None and isinstance(comp, record_type)


def group_bubbles(
    chain,
    plain_type,
    record_type=None,
    max_bubbles: int = 3,
):
    """Group a decorated message chain into chat bubbles.

    ``ResultDecorateStage`` emits one ``Plain`` per semantic sentence.  Face
    conversion may later split a single ``Plain`` into ``Plain / Face /
    Plain`` around an inline emoji.  A bubble is therefore continued when the
    next ``Plain`` follows a non-``Plain`` component and the previous text did
    not end a sentence; otherwise a new bubble starts.

    Records are always isolated: Telegram delivers a voice segment as its own
    message.  Text bubbles are capped at *max_bubbles*; extra sentences are
    merged into the last text bubble instead of producing a wall of messages.
    """
    if max_bubbles is None or max_bubbles <= 0:
        max_bubbles = 0

    bubbles: list[list] = []

    def text_bubble_count() -> int:
        return sum(1 for b in bubbles if not any(_is_record(c, record_type) for c in b))

    def merge_into_last_text_bubble(comp) -> bool:
        for bubble in reversed(bubbles):
            if not any(_is_record(c, record_type) for c in bubble):
                bubble.append(comp)
                return True
        return False

    for comp in chain:
        if not bubbles:
            bubbles.append([comp])
            continue

        current = bubbles[-1]

        # Structured replies carry explicit boundaries, including through emoji conversion.
        bubble_id = getattr(comp, '_fy_bubble_id', None)
        if bubble_id is not None and not _is_record(comp, record_type):
            previous_id = next((getattr(c, '_fy_bubble_id', None)
                                for c in reversed(current)
                                if getattr(c, '_fy_bubble_id', None) is not None), None)
            if previous_id != bubble_id or _is_record(current[-1], record_type):
                bubbles.append([comp])
            else:
                current.append(comp)
            continue

        if isinstance(comp, plain_type):
            # Text after a voice segment always starts a new bubble.
            if _is_record(current[-1], record_type):
                bubbles.append([comp])
                continue

            previous_plain = next(
                (c for c in reversed(current) if isinstance(c, plain_type)),
                None,
            )
            starts_new = previous_plain is not None and text_ends_sentence(
                getattr(previous_plain, "text", "")
            )
            if starts_new and max_bubbles and text_bubble_count() >= max_bubbles:
                # Cap reached: keep the remaining sentences together instead
                # of turning the tail into a pile of short messages.
                merge_into_last_text_bubble(comp)
            elif starts_new:
                bubbles.append([comp])
            else:
                current.append(comp)
        elif _is_record(comp, record_type):
            bubbles.append([comp])
        else:
            current.append(comp)

    return bubbles


def make_tts_text(text: str) -> str:
    """Turn display text into text that is pleasant to read aloud.

    Code, URLs and emoji markers are not useful speech.  Punctuation is kept
    so the synthesizer can phrase the whole reply as one coherent utterance.
    """
    s = text or ""
    s = _FENCED_CODE.sub("（代码部分看文字）", s)
    s = _INLINE_CODE.sub("（代码）", s)
    s = _URL.sub("链接", s)
    s = _NO_REPLY_MARK.sub("", s)
    s = _EMOJI_MARK.sub("", s)
    s = _MARKDOWN_MARKS.sub("", s)
    s = _SPACES.sub(" ", s)
    s = "\n".join(line.strip() for line in s.splitlines())
    s = re.sub(r"\n{3,}", "\n\n", s).strip()
    if not s.strip("…。.，,!！?？~～、：:;； \n\t　"):
        return ""
    return s


def is_valid_audio_file(path: str) -> bool:
    """Cheap decode sanity check before handing a file to the Telegram adapter.

    DashScope occasionally returns an HTML/JSON error body with HTTP 200.
    Writing that to ``.wav`` and sending it makes Telegram 适配器 fail silently, so the
    caller must fall back to text instead.
    """
    try:
        path = str(path or "")
        if not path or not os.path.isfile(path):
            return False
        size = os.path.getsize(path)
        if size < 512:
            return False
        with open(path, "rb") as f:
            head = f.read(16)
        if head.lstrip()[:1] in (b"<", b"{"):
            return False
        lower = path.lower()
        if lower.endswith(".wav"):
            return head[:4] == b"RIFF" and head[8:12] == b"WAVE"
        if lower.endswith(".mp3"):
            return head[:3] == b"ID3" or head[:1] == b"\xff"
        # Other containers (ogg/opus/silk/...) are accepted as long as the
        # body does not look like a text error page.
        return True
    except OSError:
        return False
