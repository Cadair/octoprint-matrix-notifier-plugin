import octoprint.plugin
from .matrix import SimpleMatrixClient


class MatrixNotifierPlugin(octoprint.plugin.SettingsPlugin,
                           octoprint.plugin.AssetPlugin,
                           octoprint.plugin.TemplatePlugin,
                           octoprint.plugin.StartupPlugin):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.client = None
        self._room = None
        self._room_alias = None

    def on_after_startup(self):
        self._logger.info("Logging into Matrix")
        self.client = SimpleMatrixClient(self._settings.get(['homeserver']),
                                         access_token=self._settings.get(['access_token']),
                                         logger=self._logger)

    def send_message(self, text):
        content = {"msgtype": "m.text", "body": text}
        self.client.room_send(self.room_id, "m.room.message", content)

    @property
    def room_id(self):
        """
        The room_id for the currently configured room.

        We cache this based on the config setting so we don't have to resolve
        the alias more than we need to.
        """
        room = self._settings.get(["room"])

        if room.startswith("!"):
            self._room = room
            return self._room

        if room.startswith("#"):
            if room == self._room_alias and self._room:
                return self._room

            room_id = self.client.room_resolve_alias(room)["room_id"]

            self._room = room_id
            self._room_alias = room

            return self._room

        raise ValueError("The room configuration option must start with ! or #")

    def get_settings_defaults(self):
        return {
            "username": "@example:matrix.org",
            "homeserver": "https://matrix.org",
            "access_token": "",
            "room": "#myprinter:matrix.org",
            "send_snapshot": True,
            "templates": {
                "done": "Print Completed after {elapsed_time}.",
                "failed": "Print Failed after {elapsed_time}.",
                "paused": "Print Paused at {elapsed_time}.",
                "progress": "Print progress: {pct_complete} - {print_name}, Elapsed: {elapsed_time}, Remaining: {remaining_time}."
            }
        }

    def get_template_configs(self):
        return [dict(type="settings", name="Matrix Notifier", custom_bindings=False)]

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
