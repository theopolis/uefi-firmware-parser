'''UEFI Firmware parser utils.
'''

import uefi
import pfs
import me
import flash

from misc import checker
from base import FirmwareObject
from utils import search_firmware_volumes


class AutoParser(object):
    '''Automatically detect the file format type.

    The UEFI Firmware module supports several types of file formats:
      - UEFI Firmware Volumes
      - (U)EFI Capsule Updates
      - UEFI Firmware Files
      - Dell "PFS" Files
      - Intel ME Modules
      - Flash Descriptors and Regions

    If the input file format is unknown the AutoParser can attempt to discover
    the type by applying basic checks for known headers.
    '''

    def __init__(self, data, search=True):
        '''Create an AutoParser instance.

        Args:
            data (binary): The entire input file contents.
            search (Optional[bool]): Allow brute-force discovery of volumes.
        '''
        self.data = data
        self.data_type = 'unknown'
        self.constructor = None
        self.firmware = None

        header = data[:100]
        for tester in checker.TESTERS:
            if tester().match(header):
                self.data_type = tester().name
                self.constructor = tester().parser

    def type(self):
        '''Return the discovered file format type.

        If the type could not be matched, 'unknown' is returned.

        Return:
            string: Name of the file format type.
        '''
        return self.data_type

    def parse(self):
        '''Call the 'process' method for the discovered type using the input
        file contents. If the file type's parser returns False indicating a
        failure or exception while parsing this will return None.

        Return:
            object: The associated file object upon success, otherwise None.
        '''
        if self.constructor is None:
            return None
        if self.firmware is not None:
            return self.firmware

        # Instanciate an instance of the firmware object
        self.firmware = self.constructor(self.data)
        if not self.firmware.process():
            # Parsing failed, remove the object reference.
            self.firmware = None
            return None
        if self.constructor is uefi.FirmwareVolume:
            mfc = MultiVolumeContainer(self.data[self.firmware.size:])
            if mfc.has_indexes():
                # Headers were discovered, attempt to process.
                if mfc.process():
                    # Add the base (first) firmware volume
                    mfc.append_base(self.firmware)
                self.firmware = mfc
        return self.firmware


class MultiVolumeContainer(FirmwareObject):
    '''The AutoParser attempts to search for 'stacked' UEFIFirmwareVolumes.

    By default if a volume does not consist of the entire input content the
    AutoParser will attempt to search for additional volume headers. This can
    be disabled with the associated 'search' optional parameter.

    If additional volumes are discovered this MultiVolumeContainer is returned
    instead of a UEFIFirmwareVolume.
    '''

    def __init__(self, data):
        '''Initialize the container with the tail content from a volume.'''
        self.data = data
        self.indexes = search_firmware_volumes(data)
        self.volumes = []

    def has_indexes(self):
        '''Check if any indexes were discovered.'''
        return self.indexes > 0

    def append_base(self, volume):
        '''Set the base volume as the first within the list.'''
        self.volumes = [volume] + self.volumes

    def process(self):
        for index in self.indexes:
            volume = uefi.FirmwareVolume(self.data[index - 40:], index)
            if volume.process():
                self.volumes.append(volume)
        return len(self.volumes) > 0

    @property
    def objects(self):
        return self.volumes

    def showinfo(self, ts='', index=None):
        '''Write structure information to stdout.'''
        for volume in self.volumes:
            volume.showinfo(ts, index)

    def dump(self, parent, index=None):
        '''Allow a caller to dump the content of volumes.'''
        for i in range(self.volumes):
            path = os.path.join(parent, "volume-%d" % i)
            self.volumes[i].dump(path)


__title__ = "uefi_firmware"
__version__ = "1.6"
__author__ = "Teddy Reed"
__license__ = "BSD"
