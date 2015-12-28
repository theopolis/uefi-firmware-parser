import efiguids
import efiguids_ami
import efiguids_dell
import efiguids_lenovo
import efiguids_asrock

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
        for name, match_guid in guid_table.iteritems():
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
