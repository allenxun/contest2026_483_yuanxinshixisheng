import os
import unittest
from unittest.mock import patch

from .backend_profile import configured_base_url, normalize_base_url


class BackendProfileTests(unittest.TestCase):
    def test_cloud_origin_is_normalized(self):
        self.assertEqual(normalize_base_url('https://eveaisia.com/openvela/'),
                         'https://eveaisia.com/openvela')

    def test_query_and_fragment_are_rejected(self):
        with self.assertRaises(ValueError):
            normalize_base_url('https://eveaisia.com/openvela?debug=1')

    def test_environment_override_wins_over_auth_file(self):
        with patch.dict(os.environ, {'VELAVISION_BACKEND_BASE_URL': 'https://eveaisia.com/openvela'}, clear=False):
            self.assertEqual(configured_base_url('http://10.3.3.170:18085'),
                             'https://eveaisia.com/openvela')

    def test_auth_origin_remains_default(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(configured_base_url('http://10.3.3.170:18085'),
                             'http://10.3.3.170:18085')
