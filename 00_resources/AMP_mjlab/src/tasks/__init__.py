import src.mjlab_compat  # noqa: F401  (mjlab 1.6 compat: update_assets + history_ordering)
from mjlab.utils.lab_api.tasks.importer import import_packages

_BLACKLIST_PKGS = ["utils", ".mdp"]

import_packages(__name__, _BLACKLIST_PKGS)
