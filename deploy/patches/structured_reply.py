"""Versioned chat presentation protocol, independent of AstrBot imports."""
import json
import re

PROTOCOL_MARKER = '【大肥鱼 JSON 气泡协议 v1】'
EMOTIONS = {
    'neutral', 'happy', 'excited', 'surprised', 'pouting', 'shy', 'touched',
    'cold', 'displeased', 'tsundere', 'serious', 'sad',
}
PERIOD_EMOTIONS = {'cold', 'displeased', 'pouting', 'tsundere'}
VOICE_EMOTIONS = {'excited', 'surprised', 'pouting', 'shy', 'touched'}
MAX_BUBBLES = 6

JSON_REPLY_PROMPT = PROTOCOL_MARKER + '''
最终聊天正文必须是一个 json 对象，不套 Markdown 代码围栏，不输出对象外的文字。
这是发给程序的呈现格式，人格决定内容和口吻；用户只会看到 bubbles 的 text。
json 示例：
{"v":1,"bubbles":[{"text":"你总算来啦","emotion":"happy","ending":"omit"},{"text":"哼，刚才才没有在等你","emotion":"tsundere","ending":"period"}],"voice":"none"}
严格使用这些字段：
- v 固定为整数 1。
- bubbles 按发送顺序排列，每个对象就是一个最终气泡。通常 1～3 个，必要时最多 6 个。
  不按每个句号机械拆分；同一段解释、代码、表格或连贯论证可放进一个气泡。
  text 是最终给用户看的字符串，可用换行、Markdown、代码、公式或用户要求的 JSON；
  这些都作为 text 的内容，正确转义引号和换行。不要把内部草稿、推理字段或控制说明放入正文。
- emotion 只能是 neutral/happy/excited/surprised/pouting/shy/touched/cold/displeased/tsundere/serious/sad，
  表达该气泡当下的情绪，不要求每泡都表现情绪，也不向用户输出情绪标签或表演旁白。
- ending 只能是 omit 或 period。默认 omit：程序只去掉气泡结尾的句号，中间句号保持不变；
  问号、叹号、省略号、代码和 URL 不受影响。只有本泡确实在表达不满、刻意冷淡或傲娇闹脾气，
  才选 period，并搭配 cold/displeased/pouting/tsundere；程序负责收尾一个句号。
  普通亲近玩笑、认真讲解均为 omit，serious 不等于冷淡。不要再输出 [[KEEP_PERIOD]]。
- voice 只能是 none/auto/requested。平时 none；只有台词情绪强烈丰富、适合自然朗读，
  且至少一个气泡 emotion 为 excited/surprised/pouting/shy/touched 时才候选 auto。
  本轮用户明确或语境中明确点播语音、想听声音、朗读或唱歌时用 requested；不要把背景引用、
  代码或语音功能讨论当点播。用户只要文字时为 none。不要再输出 [[VOICE:...]]。
  程序决定是否发送语音，自动语音有十分钟冷却，用户点播不受该冷却限制；
  成功时只发语音，失败时发 bubbles 的文字，不能承诺已经发送。
只有确实无需回复且会话允许静默时，可用 {"v":1,"bubbles":[],"voice":"none"}。
使用工具仍走 API 的 tool_calls，遵守工具参数协议，不把工具调用伪装成气泡文本。
无论历史助手消息采用何种格式，本轮最终正文都必须遵守这个 json 对象格式。
'''


def parse_reply(text):
    """Validate the entire envelope; malformed plans must never be displayed."""
    if not isinstance(text, str) or not text.strip() or len(text) > 262144:
        raise ValueError('empty_or_oversized_reply')
    # Accept a single accidental JSON fence, without extracting arbitrary braces.
    text = text.strip()
    if text.startswith('```json\n') and text.endswith('\n```'):
        text = text[8:-4]
    value = json.loads(text)
    if not isinstance(value, dict) or type(value.get('v')) is not int or value['v'] != 1:
        raise ValueError('unsupported_reply_version')
    bubbles = value.get('bubbles')
    voice = value.get('voice')
    if not isinstance(bubbles, list) or voice not in ('none', 'auto', 'requested'):
        raise ValueError('invalid_reply_envelope')
    result = []
    total = 0
    for bubble in bubbles:
        if not isinstance(bubble, dict):
            raise ValueError('invalid_bubble')
        text, emotion, ending = (bubble.get(k) for k in ('text', 'emotion', 'ending'))
        if (not isinstance(text, str) or not text.strip() or not isinstance(emotion, str)
                or emotion not in EMOTIONS
                or ending not in ('omit', 'period')):
            raise ValueError('invalid_bubble_fields')
        text = text.strip()
        total += len(text)
        if total > 64000:
            raise ValueError('reply_text_too_large')
        if ending == 'period' and emotion not in PERIOD_EMOTIONS:
            ending = 'omit'
        item = {'text': text, 'emotion': emotion, 'ending': ending}
        if len(result) < MAX_BUBBLES:
            result.append(item)
        else:
            # Preserve every word and the final bubble's closing intent.
            result[-1] = {**item, 'text': result[-1]['text'] + '\n\n' + text}
    if not result and voice != 'none':
        raise ValueError('silent_reply_cannot_request_voice')
    return {'v': 1, 'bubbles': result, 'voice': voice}


def render_bubble(bubble):
    """Apply closing punctuation after boundaries are known, preserving code."""
    text = bubble['text'].strip()
    ending = re.search(r'([。.]*)(["\'”’）)】」》〉]*\s*)$', text)
    cut = ending.start(1)
    prefix = text[:cut]
    # Do not edit the contents of fenced/inline code, URLs or ASCII ellipses.
    if (prefix.count('`') % 2 or text.endswith('```') or text.endswith('`')
            or re.search(r'https?://\S+$', text)
            or ending.group(1).startswith('..')):
        return text
    period = bubble['ending'] == 'period' and bubble['emotion'] in PERIOD_EMOTIONS
    if period and prefix and prefix[-1] not in '!?！？…~～':
        return prefix + '。' + ending.group(2)
    return prefix + ending.group(2)


def render_reply(plan):
    return [render_bubble(bubble) for bubble in plan['bubbles']]
