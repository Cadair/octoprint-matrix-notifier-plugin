import datetime
import os
import time
from textwrap import dedent
from typing import Any, Dict, List

import octoprint.plugin
import octoprint.util
from octoprint.events import Events, eventManager
from octoprint.timelapse import Timelapse

from .errors import NetworkError
from .matrix import SimpleMatrixClient


class AsyncMatrixNotifierPlugin(octoprint.plugin.EventHandlerPlugin,
                                octoprint.plugin.ProgressPlugin,
                                octoprint.plugin.SettingsPlugin,
                                octoprint.plugin.TemplatePlugin,
                                octoprint.plugin.StartupPlugin):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._room: str = None
        self._room_alias: str = None
        self.queued_message: str = None

    def get_settings_defaults(self) -> Dict[str, Any]:
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
                    **Total Estimated Time**: {total_estimated_time}
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
                    **Total Estimated Time**: {total_estimated_time}
                    **Estimated Completion Time**: {completion}
                    {temperature}
                    """),
                    "enabled": True,
                    "interval": 10,
                }
            }
        }

    @property
    def client(self) -> SimpleMatrixClient:
        """
        The matrix client.

        This is a property to react to configuration changes without reloading the plugin.
        """
        return SimpleMatrixClient(self._settings.get(['homeserver']),
                                  access_token=self._settings.get(
                                      ['access_token']),
                                  logger=self._logger)

    def on_after_startup(self) -> None:
        """ Initialize the plugin after system startup """

        user_id = self.client.whoami().get("user_id", None)
        self._logger.info("Logged into matrix as user: %s", user_id)
        monitored_events = self._settings.get(['events'])
        if monitored_events:
            self._logger.info(
                f'The following additional events are monitored: {monitored_events}')

    def get_template_configs(self) -> List[Dict[str, Any]]:
        """ Retrieve the configurable templates for this plugin """
        return [dict(type="settings", name="Async Matrix Notifier", custom_bindings=False)]

    def get_update_information(self) -> Dict[str, Dict[str, Any]]:
        # Define the configuration for your plugin to use with the Software Update
        # Plugin here. See https://docs.octoprint.org/en/master/bundledplugins/softwareupdate.html
        # for details.
        return {
            "async_matrix_notifier": {
                "displayName": "Async Matrix Notifier Plugin",
                "displayVersion": self._plugin_version,

                # version check: github repository
                "type": "github_release",
                "user": "unomar",
                "repo": "octoprint-async_matrix-notifier-plugin",
                "current": self._plugin_version,

                # update method: pip
                "pip": "https://github.com/unomar/octoprint-matrix-notifier-plugin/archive/{target_version}.zip",
            }
        }

    @property
    def temperature_status_string(self) -> str:
        """
        A string representing the current temperatures of all nozzles and the bed.
        """

        tool_template = "{tool_name}: {current_temp}°C / {target_temp}°C"

        printer_temps = self._printer.get_current_temperatures()
        if "bed" not in printer_temps:
            return None

        tool_keys = [
            key for key in printer_temps if self._printer.valid_tool_regex.match(key)]

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
    def _seconds_delta_to_string(seconds: float) -> str:
        """ Convert delta seconds into a formatted string """

        if seconds is None:
            return
        delta = datetime.timedelta(seconds=seconds)
        return octoprint.util.get_formatted_timedelta(d=delta)

    def generate_message_keys(self) -> Dict[str, Any]:
        """ Generate a dictionary of values used for status messages """

        keys = {}
        keys["temperature"] = self.temperature_status_string
        printer_data = self._printer.get_current_data()
        remaining_time_seconds = printer_data["progress"]["printTimeLeft"]
        keys["remaining_time"] = self._seconds_delta_to_string(seconds=remaining_time_seconds)
        keys["total_estimated_time"] = self._seconds_delta_to_string(seconds=printer_data["job"]["estimatedPrintTime"])
        keys["elapsed_time"] = self._seconds_delta_to_string(seconds=printer_data["progress"]["printTime"])
        if remaining_time_seconds and remaining_time_seconds > 0:
            keys["completion"] = (datetime.datetime.now() + datetime.timedelta(seconds=remaining_time_seconds)).ctime()
        keys["user"] = printer_data["job"]["user"]
        keys["filename"] = printer_data["job"]["file"]["name"]
        self._logger.debug(f'Available data: {str(printer_data)}')

        return keys

    def on_event(self, event: str, payload: Dict[str, Any]) -> None:
        """ Handle the receipt of a new event """

        # see https://docs.octoprint.org/en/master/events/

        # If we don't support this event, exit
        if not self._settings.get(["events", event]):
            self._logger.debug(f'Ignoring received event {event}')
            return

        self.snapshot_enabled = self._settings.get(["send_snapshot"])
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

        self.queued_message = template.format(**keys)

        if self.snapshot_enabled:
            # Generate the snapshot first.  The message will be sent upon receipt of Events.CAPTURE_DONE
            self.generate_snapshot()
        else:
            # No snapshot so we can send the message immediately
            self.send_message()

    def on_print_progress(self, storage: str, path: str, progress: int):
        """ Print Progress comes as a separate event.  Handle it here. """

        interval = int(self._settings.get(
            ["events", "progress", "interval"])) or 10

        if not progress or not (progress / interval == progress // interval) or progress == 100:
            return

        if self._settings.get(["events", "progress", "enabled"]):
            template = self._settings.get(["events", "progress", "template"])

        keys = self.generate_message_keys()
        keys["pct_completed"] = progress
        self.queued_message = template.format(**keys)

        if self.snapshot_enabled:
            # Generate the snapshot first.  The message will be sent upon receipt of Events.CAPTURE_DONE
            self.generate_snapshot()
        else:
            # No snapshot so we can send the message immediately
            self.send_message()

    def generate_snapshot(self) -> None:
        """ Request a snapshot and provide callbacks """

        self._logger.info('Generating snapshot...')
        eventManager().subscribe(Events.CAPTURE_DONE, self.snapshot_event)
        eventManager().subscribe(Events.CAPTURE_FAILED, self.snapshot_event)
        self.capture_snapshot()

    def send_message(self) -> None:
        """ Send a message """
        try:
            self.client.room_send_markdown_message(room_id=self.room_id, text=self.queued_message)
        except NetworkError as e:
            self._logger.warning(f'Unable to send message: {self.queued_message} due to {e.message}')

    def capture_snapshot(self) -> None:
        """ Request a snapshot """

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
        tl._file_prefix = time.strftime(format="%Y%m%d%H%M%S")
        tl.capture_image()

    @property
    def room_id(self) -> str:
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

            room_id = self.client.room_resolve_alias(room_alias=room)["room_id"]

            self._room = room_id
            self._room_alias = room

            return self._room

        raise ValueError(
            "The room configuration option must start with ! or #")

    def snapshot_event(self, event: str, payload: Dict[str, Any]) -> None:
        """ Called when an image snapshot is done capturing """

        eventManager().unsubscribe(Events.CAPTURE_DONE, self.snapshot_event)
        eventManager().unsubscribe(Events.CAPTURE_FAILED, self.snapshot_event)
        if Events.CAPTURE_DONE == event and payload.get('file', None) is not None:
            self._logger.info('Preparing to send snapshot')
            mxc_url = self.upload_snapshot(file_path=payload.get('file'))
            if mxc_url:
                self.queued_message = self.queued_message + \
                    f'\n<img src="{mxc_url}">\n'
                self.send_message()
            else:
                self._logger.warning(
                    'Image upload failed.  Sending message without snapshot.')
                self.send_message()
        else:
            self._logger.warning(
                f'Received {event} which is NOT {Events.CAPTURE_DONE} of type {type(event)} with {payload}')
        self.queued_message = None

    def upload_snapshot(self, file_path: str) -> str:
        """
        Upload a snapshot and return a mxc_url when complete.
        """

        mxc_url: str = None
        self._logger.info(f'Attempting to upload {file_path}')
        file_name = os.path.basename(file_path)

        with open(file_path, "rb") as fobj:
            data = fobj.read()

        self._logger.info('Getting mxc_url')

        upload_response = self.client.upload_media(
            media_data=data, filename=file_name, content_type="image/jpg")
        if upload_response and upload_response.get('content_uri'):
            mxc_url = upload_response.get("content_uri")

            self._logger.info(f'Got mxc_url of {mxc_url}')
            return mxc_url

        else:
            self._logger.warning(f'Unable to upload snapshot for {file_name}')
