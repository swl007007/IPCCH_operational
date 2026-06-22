from __future__ import print_function

import os
import ntpath

try:
    import configparser
except ImportError:
    import ConfigParser as configparser


ROOT_DIR = os.path.dirname(os.path.abspath(__file__))


def default_config_path():
    env_path = os.environ.get("IPCCH_CONFIG")
    if env_path:
        return env_path
    return os.path.join(ROOT_DIR, "config", "paths.ini")


def load_config(path=None):
    config_path = path or default_config_path()
    parser = configparser.RawConfigParser()
    read_files = parser.read(config_path)
    if not read_files:
        template = os.path.join(ROOT_DIR, "config", "paths_template.ini")
        raise RuntimeError(
            "Could not read config file: {0}. Copy {1} to config/paths.ini "
            "or set IPCCH_CONFIG.".format(config_path, template)
        )
    return parser


def get_value(config, section, option, default=None):
    if config.has_section(section) and config.has_option(section, option):
        return config.get(section, option)
    if default is not None:
        return default
    raise RuntimeError("Missing config value [{0}] {1}".format(section, option))


def _expanded(value, project_root_hint=None):
    if project_root_hint is None:
        project_root_hint = get_project_root_hint()
    value = value.replace("${PROJECT_ROOT}", project_root_hint)
    return os.path.expandvars(value)


def get_project_root_hint():
    return os.environ.get("PROJECT_ROOT", ROOT_DIR)


def _project_root_from_config(config):
    if config.has_section("paths") and config.has_option("paths", "project_root"):
        project_root = config.get("paths", "project_root")
        return _expanded(project_root, get_project_root_hint())
    return get_project_root_hint()


def resolve_path(config, section, option, default=None):
    project_root = _project_root_from_config(config)
    raw_value = get_value(config, section, option, default)
    expanded = _expanded(raw_value, project_root)
    if os.path.isabs(expanded) or ntpath.isabs(expanded):
        return os.path.normpath(expanded)
    return os.path.normpath(os.path.join(project_root, expanded))


def require_file(path, label):
    if not os.path.isfile(path):
        raise RuntimeError("Missing required file for {0}: {1}".format(label, path))
    return path


def require_dir(path, label):
    if not os.path.isdir(path):
        raise RuntimeError("Missing required folder for {0}: {1}".format(label, path))
    return path


def ensure_dir(path):
    if not os.path.isdir(path):
        os.makedirs(path)
    return path
