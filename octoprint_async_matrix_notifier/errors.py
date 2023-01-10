
class NetworkError(Exception):
    """ Exception for network based errors """

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class UploadError(Exception):
    """ Exception for file uploads """
    default_message: str = 'Unable to upload file'

    def __init__(self, filename: str, message: str = default_message):
        super().__init__(message.format(filename))
        self.message = message
        self.filename = filename
