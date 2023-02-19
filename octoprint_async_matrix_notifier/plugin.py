import os
from datetime import datetime, timedelta
from textwrap import dedent
from typing import Any, Dict, List, Optional

import octoprint.util
import requests
from octoprint.events import Events, eventManager
from octoprint.plugin import (EventHandlerPlugin, ProgressPlugin,
                              SettingsPlugin, StartupPlugin, TemplatePlugin)
from octoprint.settings import settings

from .errors import NetworkError
from .matrix import SimpleMatrixClient


class AsyncMatrixNotifierEvents(Events):
    CAPTURE_IMAGE = 'AsyncCaptureImage'
    CAPTURE_DONE = 'AsyncCaptureDone'
    CAPTURE_ERROR = 'AsyncCaptureError'


class AsyncMatrixNotifierPlugin(EventHandlerPlugin,
                                ProgressPlugin,
                                SettingsPlugin,
                                TemplatePlugin,
                                StartupPlugin):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._room: Optional[str] = None
        self._room_alias: Optional[str] = None
        self.queued_message: Optional[str] = None
        self._capture_dir = settings().getBaseFolder("timelapse_tmp")
        self._snapshot_url = settings().get(["webcam", "snapshot"])
        self._snapshot_timeout = settings().getInt(["webcam", "snapshotTimeout"])
        self._snapshot_validate_ssl = settings().getBoolean(["webcam", "snapshotSslValidation"])

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

        # Subscribe to the potential responses
        eventManager().subscribe(AsyncMatrixNotifierEvents.CAPTURE_IMAGE, self._capture_snapshot)
        eventManager().subscribe(AsyncMatrixNotifierEvents.CAPTURE_DONE, self._snapshot_event)
        eventManager().subscribe(AsyncMatrixNotifierEvents.CAPTURE_ERROR, self._snapshot_event)

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
    def temperature_status_string(self) -> Optional[str]:
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
    def _seconds_delta_to_string(seconds: float) -> Optional[str]:
        """ Convert delta seconds into a formatted string """

        if seconds is None:
            return
        delta = timedelta(seconds=seconds)
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
            keys["completion"] = (datetime.now() + timedelta(seconds=remaining_time_seconds)).ctime()
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
            keys["elapsed_time"] = octoprint.util.get_formatted_timedelta(timedelta(seconds=payload["time"]))

        self.queued_message = template.format(**keys)

        if self.snapshot_enabled:
            # Generate the snapshot first.  The message will be sent upon receipt of Events.CAPTURE_DONE
            eventManager().fire(AsyncMatrixNotifierEvents.CAPTURE_IMAGE)
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
            # Generate the snapshot first.  The message will be sent upon receipt of AsyncMatrixNotifierEvents.CAPTURE_DONE
            self._logger.info('Generating snapshot...')
            # Fire off an event to asynchronously capture the image
            eventManager().fire(AsyncMatrixNotifierEvents.CAPTURE_IMAGE)
        else:
            # No snapshot so we can send the message immediately
            self.send_message()

    def send_message(self) -> None:
        """ Send a message """
        self._logger.info(f'Sending message: {self.queued_message}')
        try:
            self.client.room_send_markdown_message(room_id=self.room_id, text=self.queued_message)
        except NetworkError as e:
            self._logger.warning(f'Unable to send message: {self.queued_message} due to {e.message}')

    def _capture_snapshot(self, event: str, payload: Dict[str, Any]) -> None:
        """ Private function to request a snapshot """

        self._logger.info('Capturing snapshot!')

        if not self._settings.global_get(["webcam", "snapshot"]):
            self._logger.info(
                "Please configure the webcam snapshot settings "
                "before enabling sending snapshots!"
            )

        filename = datetime.now().strftime("%Y%m%dT%H:%M:%S") + '.jpg'
        filepath = os.path.join(
            self._capture_dir,
            filename
        )

        error: Optional[str] = None

        try:
            self._logger.debug(f"Going to capture {filepath} from {self._snapshot_url}")
            r = requests.get(
                self._snapshot_url,
                stream=True,
                timeout=self._snapshot_timeout,
                verify=self._snapshot_validate_ssl,
            )
            self._logger.info('Retrieved snapshot')
            r.raise_for_status()

            with open(filepath, "wb") as f:
                for chunk in r.iter_content(chunk_size=1024):
                    if chunk:
                        f.write(chunk)
                        f.flush()

            self._logger.info(f"Image {filename} captured from {self._snapshot_url}")
        except Exception:
            error_msg = f'Could not capture image {filename} from {self._snapshot_url}'
            self._logger.exception(error_msg, exc_info=True)
            error = error_msg

        if error:
            self._logger.info(f'Reporting error: {error}')
            eventManager().fire(
                AsyncMatrixNotifierEvents.CAPTURE_ERROR,
                {"file": filename, "error": str(error), "url": self._snapshot_url},
            )
        else:
            self._logger.info('Reporting capture is done')
            eventManager().fire(AsyncMatrixNotifierEvents.CAPTURE_DONE, {"file": filepath})

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

    def _snapshot_event(self, event: str, payload: Dict[str, Any]) -> None:
        """ Called when an image snapshot is done capturing """

        self._logger.info(f'Received snapshot event: {event} with payload {payload}')

        if AsyncMatrixNotifierEvents.CAPTURE_DONE == event and payload.get('file', None) is not None:
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
                f'Received {event} which is NOT {AsyncMatrixNotifierEvents.CAPTURE_DONE} of type {type(event)} with {payload}')
        self.queued_message = None

    def upload_snapshot(self, file_path: str) -> str:
        """
        Upload a snapshot and return a mxc_url when complete.
        """

        mxc_url: str = ''
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
