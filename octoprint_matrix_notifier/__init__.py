import octoprint.plugin

from .plugin import MatrixNotifierPlugin

__plugin_pythoncompat__ = ">=3,<4" # only python 3

def __plugin_load__():
    global __plugin_implementation__
    __plugin_implementation__ = MatrixNotifierPlugin()

    global __plugin_hooks__
    __plugin_hooks__ = {
        "octoprint.plugin.softwareupdate.check_config": __plugin_implementation__.get_update_information
    }
