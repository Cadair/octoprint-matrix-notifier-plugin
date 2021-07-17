import octoprint.plugin
from nio.client.async_client import AsyncClient


class MatrixNotifierPlugin(octoprint.plugin.SettingsPlugin,
                           octoprint.plugin.AssetPlugin,
                           octoprint.plugin.TemplatePlugin,
                           octoprint.plugin.EventHandlerPlugin,
                           octoprint.plugin.StartupPlugin):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._api = None

    def on_after_startup(self):
        self._logger.info("Logging into Matrix")

    def get_settings_defaults(self):
        self._settings_keys = ("username", "password", "homeserver", "room")
        return {key: "" for key in self._settings_keys}

    def get_template_configs(self):
        return [dict(type="settings", name="Matrix Notifier", custom_bindings=False)]

    def on_event(self, event, payload):
        self._logger.info("TESTING: event is %s: %s" % (event, payload))
        self._logger.info(", ".join([str(self._settings.get([k])) for k in self._settings_keys]))

    def get_assets(self):
        # Define your plugin's asset files to automatically include in the
        # core UI here.
        return {
            "js": ["js/matrix_notifier.js"],
            "css": ["css/matrix_notifier.css"],
            "less": ["less/matrix_notifier.less"]
        }

    def get_update_information(self):
        # Define the configuration for your plugin to use with the Software Update
        # Plugin here. See https://docs.octoprint.org/en/master/bundledplugins/softwareupdate.html
        # for details.
        return {
            "matrix_notifier": {
                "displayName": "Matrix Notifier Plugin",
                "displayVersion": self._plugin_version,

                # version check: github repository
                "type": "github_release",
                "user": "Cadair",
                "repo": "OctoPrint-Matrix_Notifier",
                "current": self._plugin_version,

                # update method: pip
                "pip": "https://github.com/Cadair/OctoPrint-Matrix_Notifier/archive/{target_version}.zip",
            }
        }
