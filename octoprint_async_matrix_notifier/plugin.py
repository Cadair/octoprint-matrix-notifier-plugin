import asyncio
import datetime
import io
import os
import time
from pathlib import Path
from textwrap import dedent
from typing import Any, Coroutine

import octoprint.plugin
import octoprint.util
from get_image_size import get_image_size_from_bytesio
from octoprint.timelapse import Timelapse
from octoprint.events import Events, eventManager

from .matrix import SimpleMatrixClient


class AsyncMatrixNotifierPlugin(octoprint.plugin.EventHandlerPlugin,
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
                    **Estimated Completion Time**:{completion}
                    """),
                    "enabled": True,
                    "interval": 10,
                },
                "progress_snapshot": {
                    "template": dedent("""\
                    ## Print Progress {pct_completed}% 🏃

                    **File**: {filename}
                    **User**: {user}
                    **Elapsed Time**: {elapsed_time}
                    **Remaining Time**: {remaining_time}
                    **Total Estimated Time**:{total_estimated_time}
                    {temperature}
                    **Estimated Completion Time**:{completion}
                    <img src="{mxc_url}">
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
        return [dict(type="settings", name="Async Matrix Notifier", custom_bindings=False)]

    def get_update_information(self):
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
        keys["completion"] = self._seconds_delta_to_string(printer_data["progress"]["completion"])
        keys["user"] = printer_data["job"]["user"]
        keys["filename"] = printer_data["job"]["file"]["name"]
        self._logger.info(f'Available data: {str(printer_data)}')

        return keys

    def on_event(self, event, payload):
        # see https://docs.octoprint.org/en/master/events/

        self._logger.info(f'Processing event {event}')

        # If we don't support this event, exit
        if not self._settings.get(["events", event]):
            return

        payload = payload or dict()

        self._logger.info("Got event %s with payload %s", event, payload)

        if self._settings.get(["events", event, "enabled"]) or True:
            if 'progress' == event and self._settings.get(["send_snapshot"]):
                template = self._settings.get(["events", "progress_snapshot", "template"])
            else:
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
        asyncio.run(self.process_event(message=message))
        
    
    async def process_event(self, message):
        """ Process events asynchronously """
        
        start_time = datetime.datetime.now()
        tasks: list[Coroutine[Any, Any, None]] = []
        tasks.append(self.send_message_async(message))
        if self._settings.get(["send_snapshot"]):
            self._logger.info('Generating snapshot...')
            eventManager().subscribe(Events.CAPTURE_DONE, self.snapshot_event)
            eventManager().subscribe(Events.CAPTURE_FAILED, self.snapshot_event)
            self.capture_snapshot()
            # tasks.append(self.send_snapshot_async())
        
        await asyncio.gather(*tasks)

        stop_time = datetime.datetime.now()
        self._logger.info(f'Processed event in {stop_time-start_time}')
    
    async def send_message_async(self, message) -> None:
        """ Async function to send a text message to Matrix """
        self.client.room_send_markdown_message(self.room_id, message)
    
    async def send_snapshot_async(self):
        """ Async function to send a snapshot to Matrix """
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
    
    def snapshot_event(self, event, payload):
        """ Called when an image snapshot is done capturing """
        
        eventManager().unsubscribe(Events.CAPTURE_DONE, self.snapshot_event)
        eventManager().unsubscribe(Events.CAPTURE_FAILED, self.snapshot_event)
        if Events.CAPTURE_DONE == event and payload.get('file', None) is not None:
            self._logger.info('Preparing to send snapshot')
            self.send_snapshot(file_path=payload.get('file'))
        else:
            self._logger.warning(f'Received {event} which is NOT {Events.CAPTURE_DONE} of type {type(event)} with {payload}')

    def send_snapshot(self, file_path):
        """
        Capture and then send a snapshot from the camera.
        """
        
        self._logger.info(f'Attempting to upload {file_path}')
        file_name = os.path.basename(file_path)
        # file_path = self.capture_snapshot()

        with open(file_path, "rb") as fobj:
            data = fobj.read()
        
        self._logger.info('Getting mxc_url')

        upload_response = self.client.upload_media(media_data=data, filename=file_name, content_type="image/jpg")
        if upload_response and upload_response.get('content_uri'):
            mxc_url = upload_response.get("content_uri")

            self._logger.info(f'Got mxc_url of {mxc_url}')

            img_w, img_h = get_image_size_from_bytesio(io.BytesIO(data), len(data))

            content = {
                "msgtype": "m.image",
                "body": file_name,
                "info": {"mimetype": "image/jpg", "w": img_w, "h": img_h},
                "url": mxc_url,
            }

            return self.client.room_send(self.room_id, "m.room.message", content)
        else:
            self._logger.warning(f'Unable to upload snapshot for {file_name}')
