
from unittest.mock import MagicMock
from octoprint_async_matrix_notifier.plugin import AsyncMatrixNotifierPlugin

class TestAsyncMatrixNotifierPlugin():
    """ Class to test the AsyncMatrixNotifierPlugin """

    def get_instance(self) -> AsyncMatrixNotifierPlugin:
        """ Get an instance of the AsyncMatrixNotifierPlugin """

        amnp = AsyncMatrixNotifierPlugin()

        return amnp

    def test_get_settings_defaults(self):
        """ Test the get_settings_defaults function """

        amnp = self.get_instance()
        assert amnp.get_settings_defaults() is not None

    def test_get_update_information(self):
        """ Test the get_update_information function """

        amnp = self.get_instance()
        amnp._plugin_version = "0.0.0"
        update_info = amnp.get_update_information()
        assert update_info is not None
        assert update_info == {
            'async_matrix_notifier': {'current': '0.0.0',
            'displayName': 'Async Matrix Notifier Plugin',
            'displayVersion': '0.0.0',
            'pip': 'https://github.com/unomar/octoprint-matrix-notifier-plugin/archive/{target_version}.zip',
            'repo': 'octoprint-async_matrix-notifier-plugin',
            'type': 'github_release',
            'user': 'unomar'},
        }

