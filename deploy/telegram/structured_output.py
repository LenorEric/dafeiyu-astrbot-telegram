"""Scope JSON Output and presentation decoding to opted-in persona requests."""
import copy


def install():
    from astrbot import logger
    from astrbot.core.exceptions import EmptyModelOutputError
    from astrbot.core.pipeline.structured_reply import (
        PROTOCOL_MARKER, parse_reply, render_reply,
    )
    from astrbot.core.provider.entities import LLMResponse
    from astrbot.core.provider.sources.openai_source import ProviderOpenAIOfficial

    original = ProviderOpenAIOfficial._query
    if getattr(original, '_dafeiyu_json', False):
        return

    async def query(provider, payloads, tools, **kwargs):
        active = (
            payloads.get('model') == 'deepseek-flash'
            and provider.client.base_url.host == 'api.deepseek.com'
            and any(m.get('role') == 'system' and PROTOCOL_MARKER in str(m.get('content', ''))
                    for m in payloads.get('messages', []))
        )
        if not active:
            return await original(provider, payloads, tools, **kwargs)
        result = None
        for attempt in range(2):
            request = copy.deepcopy(payloads)
            request['response_format'] = {'type': 'json_object'}
            if attempt:
                request['messages'].append({
                    'role': 'system',
                    'content': '上次最终正文未满足 json 气泡协议。请重新输出完整的 v=1 json 对象，'
                               '包含 bubbles 数组及 voice 字段；不要输出空白、代码围栏或格式解释。'
                })
            try:
                result = await original(provider, request, tools, **kwargs)
                if result.tools_call_name:
                    # Keep native tool calls and IDs, hide intermediate presentation text.
                    result.completion_text = ''
                    return result
                plan = parse_reply(result.completion_text)
                result._dafeiyu_reply_plan = plan
                result.completion_text = '\n\n'.join(render_reply(plan)) if plan['bubbles'] else '[NO_REPLY]'
                logger.info('Structured reply decoded: bubbles=%d, voice=%s',
                            len(plan['bubbles']), plan['voice'])
                return result
            except (ValueError, EmptyModelOutputError) as exc:
                logger.warning('Structured reply rejected: attempt=%d, error=%s',
                               attempt + 1, type(exc).__name__)
                completion = getattr(result, 'raw_completion', None)
                choices = getattr(completion, 'choices', None)
                if choices and choices[0].finish_reason == 'length':
                    break
        if result is None:
            result = LLMResponse('assistant')
        plan = {'v': 1, 'bubbles': [{'text': '这次回复的格式没整理好，再发我一次试试',
                                   'emotion': 'neutral', 'ending': 'omit'}], 'voice': 'none'}
        result._dafeiyu_reply_plan = plan
        result.completion_text = render_reply(plan)[0]
        return result

    query._dafeiyu_json = True
    ProviderOpenAIOfficial._query = query
