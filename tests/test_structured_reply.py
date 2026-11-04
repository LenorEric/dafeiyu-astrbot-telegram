import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('structured_reply', ROOT / 'deploy/patches/structured_reply.py')
protocol = importlib.util.module_from_spec(spec)
spec.loader.exec_module(protocol)


def envelope(text='第一句。第二句。', emotion='neutral', ending='omit', voice='none'):
    return {'v': 1, 'bubbles': [{'text': text, 'emotion': emotion, 'ending': ending}], 'voice': voice}


class StructuredReplyTests(unittest.TestCase):
    def test_final_bubble_period_only(self):
        plan = protocol.parse_reply(json.dumps(envelope()))
        self.assertEqual(protocol.render_reply(plan), ['第一句。第二句'])

    def test_explicit_period_adds_one_before_quote(self):
        plan = protocol.parse_reply(json.dumps(envelope('“不理你了”', 'cold', 'period')))
        self.assertEqual(protocol.render_reply(plan), ['“不理你了。”'])
        plan = protocol.parse_reply(json.dumps(envelope('不理你了。。。', 'pouting', 'period')))
        self.assertEqual(protocol.render_reply(plan), ['不理你了。'])

    def test_serious_or_happy_cannot_force_period(self):
        for emotion in ('serious', 'happy'):
            plan = protocol.parse_reply(json.dumps(envelope('好呀。', emotion, 'period')))
            self.assertEqual(protocol.render_reply(plan), ['好呀'])

    def test_questions_exclamations_code_links_preserved(self):
        for text in ('好呀！', '怎么啦？', '嗯...', '```python\nprint("。")\n```', '`x.`', 'https://example.com/x.'):
            plan = protocol.parse_reply(json.dumps(envelope(text)))
            self.assertEqual(protocol.render_reply(plan), [text])

    def test_user_json_is_text_not_protocol(self):
        text = '```json\n{"bubbles": [1, 2]}\n```'
        self.assertEqual(protocol.render_reply(protocol.parse_reply(json.dumps(envelope(text)))), [text])

    def test_schema_validation_and_blank_content(self):
        for value in ('   ', '{}', '[]', '{', json.dumps(envelope(emotion=[])),
                      json.dumps({**envelope(), 'v': True}),
                      json.dumps({**envelope(), 'bubbles': [{'text': ' '}] } )):
            with self.subTest(value=value), self.assertRaises(ValueError):
                protocol.parse_reply(value)

    def test_overflow_merges_without_losing_content(self):
        value = envelope()
        value['bubbles'] = [{'text': str(i), 'emotion': 'neutral', 'ending': 'omit'} for i in range(8)]
        plan = protocol.parse_reply(json.dumps(value))
        self.assertEqual(len(plan['bubbles']), 6)
        self.assertEqual(plan['bubbles'][-1]['text'], '5\n\n6\n\n7')

    def test_silence_and_voice_fields(self):
        self.assertEqual(protocol.parse_reply('{"v":1,"bubbles":[],"voice":"none"}')['bubbles'], [])
        with self.assertRaises(ValueError):
            protocol.parse_reply('{"v":1,"bubbles":[],"voice":"requested"}')

    def test_no_reasoning_or_control_metadata_in_text(self):
        value = {**envelope('你好呀'), 'thinking': 'private', 'debug': 'secret'}
        self.assertEqual(protocol.render_reply(protocol.parse_reply(json.dumps(value))), ['你好呀'])


if __name__ == '__main__':
    unittest.main()
