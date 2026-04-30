import importlib.util
import os
import subprocess
import sys

from plugin import *


REQUIRED_PACKAGES = [
    ("cloudscraper", "cloudscraper"),
    ("beautifulsoup4", "bs4"),
    ("lxml", "lxml"),
]


def _ensure_requirements():
    missing = [
        package
        for package, module_name in REQUIRED_PACKAGES
        if importlib.util.find_spec(module_name) is None
    ]
    if not missing:
        return
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", *missing])
    except Exception as e:
        print(f"Failed to install requirements: {e}")


def _get_runtime_package_name():
    return os.path.basename(os.path.dirname(__file__))


runtime_package_name = _get_runtime_package_name()

_ensure_requirements()

setting = {
    "filepath": __file__,
    "use_db": True,
    "use_default_setting": True,
    "home_module": "main",
    "menu": {
        "uri": runtime_package_name,
        "name": "MissKon",
        "list": [
            {"uri": "main", "name": "Latest"},
            {"uri": "top3", "name": "Top 3 days"},
            {"uri": "top7", "name": "Top 7 days"},
            {"uri": "top30", "name": "Top 30 days"},
            {"uri": "top60", "name": "Top 60 days"},
            {"uri": "search", "name": "Search"},
            {"uri": "setting", "name": "Setting"},
            {"uri": "log", "name": "Log"},
        ],
    },
    "default_route": "single",
}

P = create_plugin_instance(setting)

try:
    from .mod_main import ModuleMain

    P.set_module_list([ModuleMain])
except Exception as e:
    P.logger.error(f"Exception:{str(e)}")
