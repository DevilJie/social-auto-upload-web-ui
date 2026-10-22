"""YouTube's explicit 'no' must survive merging and required-field validation."""
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services import draft_merge


class YouTubeDeclarationTests(unittest.TestCase):
    def validate(self, config, account_override=None):
        draft = {'draft_data': {
            'commonConfig': {'videoLandscape': {'id': 'video'}, 'coverLandscape': {'id': 'cover'}},
            'platformConfigs': {'youtube': {'title': 'Test', 'audience': 'not_kids', **config}},
            'accountOverrides': {'7': account_override or {}},
            'publishAccountIds': [7],
        }}
        with patch.object(draft_merge, '_get_account_by_id', return_value=SimpleNamespace(platform='youtube')):
            return draft_merge.validate_draft_for_publish(draft)

    def test_explicit_yes_and_no_are_valid(self):
        for value in (True, False):
            with self.subTest(value=value):
                self.assertEqual(self.validate({'alteredContent': value}), [])

    def test_unset_or_non_boolean_is_rejected(self):
        for config in ({}, {'alteredContent': None}, {'alteredContent': ''},
                       {'alteredContent': 'false'}, {'alteredContent': 0}):
            with self.subTest(config=config):
                self.assertTrue(any('alteredContent' in e for e in self.validate(config)))

    def test_account_no_overrides_platform_yes(self):
        self.assertEqual(self.validate({'alteredContent': True}, {'alteredContent': False}), [])
        merged = draft_merge.merge_config({}, {'alteredContent': True}, {}, {'alteredContent': False})
        self.assertIs(merged['alteredContent'], False)

    def test_missing_audience_remains_invalid(self):
        errors = self.validate({'alteredContent': False, 'audience': ''})
        self.assertTrue(any('audience' in e for e in errors))
        self.assertFalse(any('alteredContent' in e for e in errors))


if __name__ == '__main__':
    unittest.main()
