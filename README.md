# Matrix Notifier for OctoPrint

Send messages and snapshots to matrix rooms.

## Setup

Install via the bundled [Plugin Manager](https://docs.octoprint.org/en/master/bundledplugins/pluginmanager.html)
or manually using this URL:

    https://github.com/Cadair/octoprint-matrix-notifier-plugin/archive/main.zip

## Configuration

The plugin can be configured via the octoprint UI. You will need the room alias or room id of the matrix room as well as your server address and an access token.

The easiest way to obtain an access token is to login with Element, copy the access token from the settings panel and then *do not logout*.

## Credits

This plugin is heavily inspired by [OctoSlack](https://github.com/fraschetti/Octoslack) and I used [Octoprint Signal Notifier](https://github.com/aerickson/OctoPrint_Signal-Notifier) to understand how to write an octoprint plugin and how to capture a snapshot from the camera.
