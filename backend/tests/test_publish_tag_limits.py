import sys
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services import draft_merge as dm

class TagLimitTests(unittest.TestCase):
    def test_limits_and_payload(self):
        tags = [str(i) for i in range(12)]
        for platform, count in [('douyin', 5), ('kuaishou', 4), ('bilibili', 10), ('youtube', 10)]:
            account = SimpleNamespace(platform=platform, file_path='cookie')
            self.assertEqual(dm.build_platform_kwargs({'tags': tags}, {}, account)['tags'], tags[:count])
        self.assertEqual(len(tags), 12)

    def test_validation_uses_same_topic_budget(self):
        cfg = {'title': 'test', 'aiContent': '无需添加自主声明', 'tags': list('abcdefghij'),
               'description': '#topic text', 'activityId': ['activity']}
        self.assertEqual(dm.limit_platform_tags('douyin', cfg), list('abc'))
        draft = {'draft_data': {'commonConfig': {'videoLandscape': {'id': 'v'}, 'coverLandscape': {'id': 'c'}},
                'platformConfigs': {'douyin': cfg}, 'publishAccountIds': [3]}}
        with patch.object(dm, '_get_account_by_id', return_value=SimpleNamespace(platform='douyin')):
            self.assertEqual(dm.validate_draft_for_publish(draft), [])
        self.assertEqual(len(cfg['tags']), 10)

if __name__ == '__main__':
    unittest.main()
