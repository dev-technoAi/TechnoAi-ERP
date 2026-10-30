from . import models
from .models.res_config_settings import PAID_MENUS, PAID_VIEWS


def uninstall_hook(env):
    """ Give back what the module hid: the paid apps list and the archived screens and menus. """
    env.ref('base.open_module_tree').domain = False
    for xmlid in PAID_VIEWS + PAID_MENUS:
        record = env.ref(xmlid, raise_if_not_found=False)
        if record:
            record.active = True
