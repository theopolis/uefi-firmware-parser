import efiguids
import efiguids_ami
import efiguids_dell

from ..utils import rguid

GUID_TABLES = [
    efiguids.GUIDs,
    efiguids_ami.GUIDs,
    efiguids_dell.GUIDs
]

def get_guid_name(guid):
    raw_guid = rguid(guid) if type(guid) is str else guid

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
    pass