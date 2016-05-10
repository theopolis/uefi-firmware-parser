from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

from . import efiguids
from . import efiguids_ami
from . import efiguids_dell
from . import efiguids_lenovo
from . import efiguids_asrock

from ..utils import aguid

GUID_TABLES = [
    efiguids.GUIDs,
    efiguids_ami.GUIDs,
    efiguids_dell.GUIDs,
    efiguids_lenovo.GUIDs,
    efiguids_asrock.GUIDs,
]


def get_guid_name(guid):
    raw_guid = aguid(guid) if isinstance(guid, str) else guid

    for guid_table in GUID_TABLES:
        for name, match_guid in guid_table.items():
            match = True
            for i, k in enumerate(raw_guid):
                if match_guid[i] != k:
                    match = False
                    break
            if match:
                return name
    return None


def get_tables():
    return GUID_TABLES
