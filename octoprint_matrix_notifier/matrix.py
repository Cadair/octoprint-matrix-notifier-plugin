"""
A *really* barebones matrix client.
"""
from urllib.request import Request, urlopen
from urllib.parse import urljoin
from uuid import uuid4

from nio.api import Api
import logging
import json


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

        if isinstance(data, str):
            data = data.encode("UTF-8")

        req = Request(url, data=data, headers=headers, method=method)
        self.logger.info("%s %s data=%s headers=%s", method, url.replace(self.access_token, "..."), data, headers)

        resp = urlopen(req)
        # TODO: Detect matrix errors here
        return json.loads(resp.read())

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
