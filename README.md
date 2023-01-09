# Async Matrix Notifier for OctoPrint

Send messages and snapshots to matrix rooms.

## Setup

Install via the bundled [Plugin Manager](https://docs.octoprint.org/en/master/bundledplugins/pluginmanager.html)
or manually using this URL:

    https://github.com/unomar/octoprint-async-matrix-notifier-plugin/archive/main.zip

## Configuration

The plugin can be configured via the octoprint UI. You will need the room alias or room id of the matrix room as well as your server address and an access token.

The easiest way to obtain an access token is to login with Element, copy the access token from the settings panel and then *do not logout*.

## Credits

This plugin is a fork of [Matrix Notifier Plugin](https://github.com/Cadair/octoprint-matrix-notifier-plugin/) intended to run on slower hardware such as the Raspberry Pi 3b where generating a snapshot can take a few cycles.  It has been optimized to generate a message and asyncronously request a snapshot.  When the snapshot is ready, then the message is sent to the Matrix server.  Performing this task asynchronously allows the plugin to return quickly which prevents stutters in printing (usually resulting in exterior blobs or zits) and ensures that the snapshot is completely written to disk before attempting to upload.

## Screenshots
![Configuration](https://github.com/unomar/octoprint-async-matrix-notifier-plugin/raw/main/screenshots/configuration.png)
![Progress](https://github.com/unomar/octoprint-async-matrix-notifier-plugin/raw/main/screenshots/progress.png)


## Developer Info

### Making a Release

1. Update the version number in `setup.py`, push to `main`.
1. Check the release draft on GitHub, make sure version number matches the
   `setup.py`.
1. Publish Release on GitHub.
