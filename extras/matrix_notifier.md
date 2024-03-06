---
layout: plugin

id: matrix_notifier
title: Matrix Notifier
description: Sends matrix notifications and snapshots of your print.
authors:
- Stuart Mumford
license: AGPLv3

date: 2021-07-18

homepage: https://github.com/Cadair/octoprint-matrix-notifier-plugin
source: https://github.com/Cadair/octoprint-matrix-notifier-plugin
archive: https://github.com/Cadair/octoprint-matrix-notifier-plugin/archive/main.zip

tags:
- notifications
- notification
- matrix
- shapshots

screenshots:
- url: /assets/img/plugins/printstarted.png
  alt: A print started message
  caption: A matrix notification showing a print started message and a snapshot image.
- ...

featuredimage: /assets/img/plugins/printstarted.png

compatibility:
  # List of compatible versions
  #
  # A single version number will be interpretated as a minimum version requirement,
  # e.g. "1.3.1" will show the plugin as compatible to OctoPrint versions 1.3.1 and up.
  # More sophisticated version requirements can be modelled too by using PEP440
  # compatible version specifiers.
  #
  # You can also remove the whole "octoprint" block. Removing it will default to all
  # OctoPrint versions being supported.
  octoprint:
  - 1.2.0
  # Compatible Python version
  #
  # Plugins should aim for compatibility for Python 2 and 3 for now, in which case the value should be ">=2.7,<4".
  #
  # Plugins that only wish to support Python 3 should set it to ">=3,<4".
  #
  # If your plugin only supports Python 2 (worst case, not recommended for newly developed plugins since Python 2
  # is EOL), leave at ">=2.7,<3" - be aware that your plugin will not be allowed to register on the
  # plugin repository if it only support Python 2.
  python: ">=3,<4"

---

Matrix notifier sends messages to a configured matrix room with information about your print and snapshots of your camera.

The following events are configurable through the web UI:

  - PrintStarted
  - PrintPaused
  - PrintFailed
  - PrintDone
  - Print Progress

The message templates support markdown which are converted to HTML to send as formatted matrix messages.

In addition to this any other event should be configurable directly in the `config.yaml` file.

Take the event name from https://docs.octoprint.org/en/master/events/ and add a section under the `plugins:` section which looks like this:

```
  matrix_notifier:
    events:
      Connected:
        enabled: true
        template: |
          ## Printer Connected
```

This would send messages on the "Connected" event. Find the existing section of the config and edit it where appropriate rather than adding new sections.
Note that not all events have been tested, please [open an issue](https://github.com/Cadair/octoprint-matrix-notifier-plugin/issues/new) if you encounter an issue with a specific event.
