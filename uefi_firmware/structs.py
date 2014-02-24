# -*- coding: utf-8 -*-

EFI_FILE_TYPES = {
    # http://wiki.phoenix.com/wiki/index.php/EFI_FV_FILETYPE
    0x00: ("unknown",                    "none",        "0x00"),
    0x01: ("raw",                        "raw",         "RAW"),
    0x02: ("freeform",                   "freeform",    "FREEFORM"),
    0x03: ("security core",              "sec",         "SEC"),
    0x04: ("pei core",                   "pei",         "PEI_CORE"),
    0x05: ("dxe core",                   "dxe",         "DXE_CORE"),
    0x06: ("pei module",                 "peim",        "PEIM"),
    0x07: ("driver",                     "driver",      "DRIVER"),
    0x08: ("combined pei module/driver", "peim.driver", "COMBO_PEIM_DRIVER"),
    0x09: ("application",                "app",         "APPLICATION"),
    0x0b: ("firmware volume image",      "vol",         "FV_IMAGE"),
    0xf0: ("ffs padding",                "pad",         "0xf0")
    ### SMM_CORE
    ### DXE_SMM_CORE
}

EFI_SECTION_TYPES = {
    0x01: ("Compression",               "compressed",   None),
    0x02: ("Guid Defined",              "guid",         None),
    0x03: ("Disposable",                "disposable",   None),
    0x10: ("PE32 image",                "pe",           "PE32"),
    0x11: ("PE32+ PIC image",           "pic.pe",       "PIC"),
    0x12: ("Terse executable (TE)",     "te",           "TE"),
    0x13: ("DXE dependency expression", "dxe.depex",    "DXE_DEPEX"),
    0x16: ("IA-32 16-bit image",        "ia32.16bit",   "COMPAT16"),
    0x17: ("Firmware volume image",     "fv",           "FV_IMAGE"),
    ### See FdfParser.py in EDKII's GenFds 
    0x18: ("Free-form GUID",            "freeform.guid", "SUBTYPE_GUID"),
    0x19: ("Raw",                       "raw",          "RAW"),
    0x1b: ("PEI dependency expression", "pie.depex",    "PEI_DEPEX"),
    
    # Added from previous code (not in Phoenix spec
    0x14: ("Version section",           "version",      "VERSION"),
    0x15: ("User interface name",       "ui",           "UI"),
    0x1b: ("SMM dependency expression", "smm.depex",    "SMM_DEPEX")
}

EFI_COMPRESSION_TYPES = {
    0x00: "",
    #0x01: "EFI_STANDARD_COMPRESSION",
    0x01: "PI_STD",
    #0x02: "EFI_CUSTOMIZED_COMPRESSION"
    0x02: "PI_STD"
}