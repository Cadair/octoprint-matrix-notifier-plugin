
from unittest.mock import MagicMock, call, mock_open, patch

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

    def test_generate_message_keys(self):
        # Create an instance of the plugin
        plugin = AsyncMatrixNotifierPlugin()

        current_data = {
            "progress": {
                "printTimeLeft": 3600,
                "printTime": 1800
            },
            "job": {
                "estimatedPrintTime": 7200,
                "user": "John Doe",
                "file": {
                    "name": "example.gcode"
                }
            }
        }

        mock_debug = MagicMock()
        mock_logger = MagicMock()
        mock_logger.debug = mock_debug
        mock_printer = MagicMock()
        mock_get_current_data = MagicMock(return_value=current_data)
        mock_printer.get_current_data = mock_get_current_data

        plugin._printer = mock_printer
        plugin._logger = mock_logger

        # Mock the _printer.get_current_data() method

        # with patch.object(plugin, '_printer', return_value=current_data):

        # Call the generate_message_keys method
        keys = plugin.generate_message_keys()

        # Assert the returned keys match the expected values
        assert "temperature" in keys
        assert keys["remaining_time"] == plugin._seconds_delta_to_string(3600)
        assert keys["total_estimated_time"] == plugin._seconds_delta_to_string(7200)
        assert keys["elapsed_time"] == plugin._seconds_delta_to_string(1800)
        assert "completion" in keys
        assert keys["user"] == "John Doe"
        assert keys["filename"] == "example.gcode"

        mock_get_current_data.assert_called_once()

        expected_log_message = "Available data: {'progress': {'printTimeLeft': 3600, 'printTime': 1800}, 'job': "
        expected_log_message += "{'estimatedPrintTime': 7200, 'user': 'John Doe', 'file': {'name': 'example.gcode'}}}"
        mock_debug.assert_called_once_with(expected_log_message)

    # @mock.patch("builtins.open", create=True)
    def test_upload_snapshot(self):
        """ Test the upload_snapshot function """

        mock_client = MagicMock()
        mock_upload_media = MagicMock(return_value={})
        mock_client.upload_media = mock_upload_media
        mock_logger = MagicMock()

        with patch.multiple('octoprint_async_matrix_notifier.plugin.AsyncMatrixNotifierPlugin',
                            client=mock_client):
            with patch('octoprint_async_matrix_notifier.plugin.open', mock_open(read_data='data')):
                amnp = self.get_instance()
                amnp._logger = mock_logger
                amnp.upload_snapshot(file_path="test.jpg")

                mock_upload_media.assert_called_once_with(media_data='data', filename='test.jpg', content_type='image/jpg')
                mock_logger.assert_has_calls(calls=[
                    call.info('Attempting to upload test.jpg'),
                    call.info('Getting mxc_url'),
                    call.warning('Unable to upload snapshot for test.jpg')])
