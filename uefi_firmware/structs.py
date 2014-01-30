# -*- coding: utf-8 -*-

EFI_FILE_TYPES = {
    # http://wiki.phoenix.com/wiki/index.php/EFI_FV_FILETYPE
    0x00: ("unknown", "none"),
    0x01: ("raw", "raw"),
    0x02: ("freeform", "freeform"),
    0x03: ("security core", "sec"),
    0x04: ("pei core", "pei"),
    0x05: ("dxe core", "dxe"),
    0x06: ("pei module", "peim"),
    0x07: ("driver", "driver"),
    0x08: ("combined pei module/driver", "peim.driver"),
    0x09: ("application", "app"),
    0x0b: ("firmware volume image", "vol"),
    0xf0: ("ffs padding", "pad")
}

EFI_SECTION_TYPES = {
    0x01: ("Compression", "compressed"),
    0x02: ("GUID defined", "guiddef"),
    0x03: ("Disposable", "disposable"),
    0x10: ("PE32 image", "pe"),
    0x11: ("PE32+ PIC image", "pic.pe"),
    0x12: ("Terse executable (TE)", "te"),
    0x13: ("DXE dependency expression", "dxe.depex"),
    0x16: ("IA-32 16-bit image", "ia32.16bit"),
    0x17: ("Firmware volume image", "fv"),
    0x18: ("Free-form GUID", "freeform.guidsec"),
    0x19: ("Raw", "raw"),
    0x1b: ("PEI dependency expression", "pie.depex"),
    
    # Added from previous code (not in Phoenix spec
    0x14: ("Version section", "version"),
    0x15: ("User interface name", "name"),
    0x1b: ("SMM dependency expression", "smm.depex")
}
