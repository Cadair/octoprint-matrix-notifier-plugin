"""
A *really* barebones matrix client.
"""
import json
import logging
import requests
from urllib.parse import urljoin
from urllib.request import Request, urlopen
from urllib.error import URLError
from uuid import uuid4

import markdown
from nio.api import Api


class SimpleMatrixClient:
    """
    A simple matrix client.
    """

    def __init__(self, homeserver, access_token=None, logger=None):
        self.homeserver = homeserver
        self.access_token = access_token
        self.logger = logger or logging.getLogger(__name__)

    def _send(self, method, path, data=None, content_type=None, content_length=None):
        url = urljoin(self.homeserver, path)

        headers = (
            {"Content-Type": content_type}
            if content_type
            else {"Content-Type": "application/json"}
        )

        if content_length is not None:
            headers["Content-Length"] = str(content_length)

        log_data = None if data is None else "binary_data"
        if isinstance(data, str):
            data = data.encode("UTF-8")
            log_data = data

        req = Request(url, data=data, headers=headers, method=method)
        self.logger.info("%s %s data=%s headers=%s", method, url.replace(self.access_token, "..."), log_data, headers)

        try:
            self.logger.debug(f'Attempting to open URL {req}')
            with urlopen(req) as resp:
                return json.loads(resp.read())
        except URLError as e:
            self.logger.warn(f'Caught URLError attempting to {method} to {path}: {e.code}, {e.read()}')
        # TODO: Detect matrix errors here
        

    def room_resolve_alias(self, room_alias):
        method, path = Api.room_resolve_alias(room_alias)

        return self._send(method, path)

    def room_send(self, room_id, message_type, content):
        """
        Send a message to a room.
        """
        uuid = uuid4()
        method, path, data = Api.room_send(
            self.access_token, room_id, message_type, content, uuid
        )

        return self._send(method, path, data)

    def whoami(self):
        if self.access_token is None:
            raise ValueError("No access_token is set.")

        method, path = Api.whoami(self.access_token)
        return self._send(method, path)

    def upload_media(self, media_data, filename, content_type):
        # return self._send(
        #     method="POST",
        #     path=f"/_matrix/media/r0/upload?access_token={self.access_token}",
        #     data=media_data,
        #     content_type=content_type,
        #     # content_length=len(media_data),
        # )
        rlog = logging.getLogger('urllib3')
        rlog.setLevel(logging.DEBUG)
        ch = logging.StreamHandler()
        ch.setLevel(logging.DEBUG)
        rlog.addHandler(ch)

        url = urljoin(self.homeserver, f'/_matrix/media/r0/upload?filename={filename}&access_token={self.access_token}')
        headers = {
            'content-type': content_type,
            'content-length': str(len(media_data))
        }
        self.logger.info(f'Attempting to POST to {url} with headers {headers}')
        response = requests.post(url=url, data=media_data, headers=headers)
        # response = requests.post(url=url, data=media_data)
        if response.ok:
            return response.json()
        else:
            self.logger.warning(f'Received error status from image upload: {response.status_code} {response.content}')

    def room_send_markdown_message(self, room_id, text):
        content = {
            "msgtype": "m.text",
            "body": text,
            "format": "org.matrix.custom.html",
            "formatted_body": markdown.markdown(text, extensions=['nl2br'])
        }
        self.room_send(room_id, "m.room.message", content)
