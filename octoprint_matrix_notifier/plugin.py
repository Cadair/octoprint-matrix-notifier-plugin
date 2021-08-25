import datetime
import io
import time
from pathlib import Path
from textwrap import dedent

import octoprint.plugin
import octoprint.util
from get_image_size import get_image_size_from_bytesio
from octoprint.timelapse import Timelapse

from .matrix import SimpleMatrixClient


class MatrixNotifierPlugin(octoprint.plugin.EventHandlerPlugin,
                           octoprint.plugin.ProgressPlugin,
                           octoprint.plugin.SettingsPlugin,
                           octoprint.plugin.TemplatePlugin,
                           octoprint.plugin.StartupPlugin):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._room = None
        self._room_alias = None

    def get_settings_defaults(self):
        return {
            "username": "@example:matrix.org",
            "homeserver": "https://matrix.org",
            "access_token": "",
            "room": "#myprinter:matrix.org",
            "send_snapshot": True,
            "events": {
                "PrintStarted": {
                    "template": dedent("""\
                    ## Print Started 🚀

                    **File**: {filename}
                    **User**: {user}
                    **Estimated Print Time**: {total_estimated_time}
                    {temperature}
                    """),
                    "enabled": True,
                },
                "PrintDone": {
                    "template": dedent("""\
                    ## Print Completed 🚀

                    **File**: {filename}
                    **User**: {user}
                    **Elapsed Time**: {elapsed_time}
                    {temperature}
                    """),
                    "enabled": True,
                },
                "PrintFailed": {
                    "template": dedent("""\
                    ## Print Failed 😞

                    **File**: {filename}
                    **User**: {user}
                    **Elapsed Time**: {elapsed_time}
                    {temperature}
                    """),
                    "enabled": True,
                },
                "PrintPaused": {
                    "template": dedent("""\
                    ## Print Paused ⏸️

                    **File**: {filename}
                    **User**: {user}
                    **Elapsed Time**: {elapsed_time}
                    **Remaining Time**: {remaining_time}
                    **Total Estimated Time**:{total_estimated_time}
                    {temperature}
                    """),
                    "enabled": True,
                },
                "progress": {
                    "template": dedent("""\
                    ## Print Progress {pct_completed}% 🏃

                    **File**: {filename}
                    **User**: {user}
                    **Elapsed Time**: {elapsed_time}
                    **Remaining Time**: {remaining_time}
                    **Total Estimated Time**:{total_estimated_time}
                    {temperature}
                    """),
                    "enabled": True,
                    "interval": 10,
                }
            }
        }

    @property
    def client(self):
        """
        The matrix client.

        This is a property to react to configuration changes without reloading the plugin.
        """
        return SimpleMatrixClient(self._settings.get(['homeserver']),
                                  access_token=self._settings.get(['access_token']),
                                  logger=self._logger)

    def on_after_startup(self):
        user_id = self.client.whoami()["user_id"]
        self._logger.info("Logged into matrix as user: %s", user_id)

    def get_template_configs(self):
        return [dict(type="settings", name="Matrix Notifier", custom_bindings=False)]

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
                "repo": "octoprint-matrix-notifier-plugin",
                "current": self._plugin_version,

                # update method: pip
                "pip": "https://github.com/Cadair/octoprint-matrix-notifier-plugin/archive/{target_version}.zip",
            }
        }

    @property
    def temperature_status_string(self):
        """
        A string representing the current temperatures of all nozzles and the bed.
        """
        tool_template = "{tool_name}: {current_temp}°C / {target_temp}°C"

        printer_temps = self._printer.get_current_temperatures()
        if "bed" not in printer_temps:
            return None

        tool_keys = [key for key in printer_temps if self._printer.valid_tool_regex.match(key)]

        # If we only have one nozzle then don't number it.
        first_key = "Nozzle" if len(tool_keys) == 1 else "Nozzle 0"

        tools_components = []
        for i, key in enumerate(tool_keys):
            if i == 0:
                tool_name = first_key
            else:
                tool_name = key.replace("tool", "Nozzle ")

            tools_components.append(
                tool_template.format(tool_name=tool_name,
                                     current_temp=printer_temps[key]["actual"],
                                     target_temp=printer_temps[key]["target"]))

        tool_string = " ".join(tools_components)

        return f"Bed: {printer_temps['bed']['actual']}°C / {printer_temps['bed']['target']}°C " + tool_string

    @staticmethod
    def _seconds_delta_to_string(seconds):
        if seconds is None:
            return
        delta = datetime.timedelta(seconds=seconds)
        return octoprint.util.get_formatted_timedelta(delta)

    def generate_message_keys(self):
        keys = {}
        keys["temperature"] = self.temperature_status_string
        printer_data = self._printer.get_current_data()
        keys["remaining_time"] = self._seconds_delta_to_string(printer_data["progress"]["printTimeLeft"])
        keys["total_estimated_time"] = self._seconds_delta_to_string(printer_data["job"]["estimatedPrintTime"])
        keys["elapsed_time"] = self._seconds_delta_to_string(printer_data["progress"]["printTime"])
        keys["user"] = printer_data["job"]["user"]
        keys["filename"] = printer_data["job"]["file"]["name"]

        return keys

    def on_event(self, event, payload):
        # see https://docs.octoprint.org/en/master/events/

        # If we don't support this event, exit
        if not self._settings.get(["events", event]):
            return

        payload = payload or dict()

        self._logger.info("Got event %s with payload %s", event, payload)

        if self._settings.get(["events", event, "enabled"]) or True:
            template = self._settings.get(["events", event, "template"])

        keys = self.generate_message_keys()
        keys = {
            "reason": payload.get("reason", None),
            "elapsed_time": None,
            **keys
        }
        if "time" in payload:
            keys["elapsed_time"] = octoprint.util.get_formatted_timedelta(datetime.timedelta(seconds=payload["time"]))

        message = template.format(**keys)

        self.client.room_send_markdown_message(self.room_id, message)
        if self._settings.get(["send_snapshot"]):
            self.send_snapshot()

    def on_print_progress(self, storage, path, progress):
        interval = int(self._settings.get(["events", "progress", "interval"])) or 1
        # Do not report if no progress, the progress isn't a multiple of
        # interval or the progress is 100% because we have PrintCompleted for
        # that.
        if not progress or not(progress / interval == progress // interval) or progress == 100:
            return

        if self._settings.get(["events", "progress", "enabled"]):
            template = self._settings.get(["events", "progress", "template"])

        keys = self.generate_message_keys()
        keys["pct_completed"] = progress
        message = template.format(**keys)

        self.client.room_send_markdown_message(self.room_id, message)
        if self._settings.get(["send_snapshot"]):
            self.send_snapshot()

    def capture_snapshot(self):
        if not self._settings.global_get(["webcam", "snapshot"]):
            self._logger.info(
                "Please configure the webcam snapshot settings "
                "before enabling sending snapshots!"
            )

        tl = Timelapse()
        tl._image_number = 0
        tl._capture_errors = 0
        tl._capture_success = 0
        tl._in_timelapse = True
        tl._file_prefix = time.strftime("%Y%m%d%H%M%S")
        file_path = Path(tl.capture_image())

        # Ensure the file has actually finished being written before we return
        # There appears to be a threading race condition or something going on here
        for i in range(10):
            if file_path.exists():
                break
            time.sleep(0.1)

        return file_path

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

    def send_snapshot(self):
        """
        Capture and then send a snapshot from the camera.
        """
        file_path = self.capture_snapshot()

        with open(file_path, "rb") as fobj:
            data = fobj.read()

        mxc_url = self.client.upload_media(data, "image/jpg")["content_uri"]

        img_w, img_h = get_image_size_from_bytesio(io.BytesIO(data), len(data))

        content = {
            "msgtype": "m.image",
            "body": file_path.name,
            "info": {"mimetype": "image/jpg", "w": img_w, "h": img_h},
            "url": mxc_url,
        }

        return self.client.room_send(self.room_id, "m.room.message", content)
