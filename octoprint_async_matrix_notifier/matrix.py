"""
A *really* barebones matrix client.
"""
import logging
from typing import Any, Dict
from uuid import uuid4

import markdown
import requests
from nio.api import Api
from requests.compat import urljoin

from .errors import NetworkError, UploadError


class SimpleMatrixClient:
    """
    A simple matrix client.
    """

    def __init__(self, homeserver, access_token=None, logger=None):
        self.homeserver = homeserver
        self.access_token = access_token
        self.logger = logger or logging.getLogger(__name__)

    def _send(self, method: str, path: str, data: str = None, content_type: str = None, content_length: str = None) -> Dict[str, Any]:
        """ Send data via http(s) """

        url = urljoin(base=self.homeserver, url=path)

        # Generate a log friendly URL without sensitive info
        log_friendly_url = url.replace(self.access_token, '<redacted>')

        # Default to application/json unless specified
        content_type = content_type if content_type else 'application/json'
        headers = {
            'Content-Type': content_type,
            'Accept': 'application/json'
        }

        if content_length is not None:
            headers['Content-Length'] = str(content_length)

        log_data = None if data is None else 'binary_data'
        if isinstance(data, str):
            data = data.encode('UTF-8')
            log_data = data

        self.logger.info(
            f'{method} {log_friendly_url} data={log_data} headers={headers}')
        response = requests.request(method=method, url=url, data=data, headers=headers)

        if not response.ok:
            raise NetworkError(
                message=f'Received error response {response.status_code} from {log_friendly_url}: {response.text}')
        return response.json()

    def room_resolve_alias(self, room_alias: str) -> Dict[str, Any]:
        """ Resolve a Matrix room alias """

        method, path = Api.room_resolve_alias(room_alias=room_alias)

        return self._send(method=method, path=path)

    def room_send(self, room_id: str, message_type: str, content: Dict[str, Any]) -> Dict[str, Any]:
        """
        Send a message to a room.
        """
        uuid = uuid4()
        method, path, data = Api.room_send(access_token=self.access_token, room_id=room_id, event_type=message_type, body=content, tx_id=uuid)

        return self._send(method=method, path=path, data=data)

    def whoami(self) -> Dict[str, Any]:
        if self.access_token is None:
            raise ValueError('No access_token is set.')

        method, path = Api.whoami(access_token=self.access_token)
        return self._send(method=method, path=path)

    def upload_media(self, media_data: bytes, filename: str, content_type: str) -> Dict[str, Any]:
        """ Upload some binary media (snapshots) and return the response JSON """

        url = urljoin(
            self.homeserver, f'/_matrix/media/r0/upload?filename={filename}&access_token={self.access_token}')
        headers = {
            'content-type': content_type,
            'content-length': str(len(media_data))
        }

        self.logger.info(f'Attempting to POST to {url} with headers {headers}')
        response = requests.post(url=url, data=media_data, headers=headers)

        if not response.ok:
            raise UploadError(filename=filename, message='Unable to upload')

        return response.json()

    def room_send_markdown_message(self, room_id: str, text: str) -> None:
        """ Send a markdown message to the specified room """

        content = {
            'msgtype': 'm.text',
            'body': text,
            'format': 'org.matrix.custom.html',
            'formatted_body': markdown.markdown(text=text, extensions=['nl2br'])
        }
        self.room_send(room_id=room_id, message_type='m.room.message', content=content)
