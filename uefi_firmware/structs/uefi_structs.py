# -*- coding: utf-8 -*-
import ctypes

uint8_t  = ctypes.c_ubyte
char     = ctypes.c_char
uint32_t = ctypes.c_uint
uint64_t = ctypes.c_uint64
uint16_t = ctypes.c_ushort

FIRMWARE_VOLUME_GUIDS = [
    '7a9354d9-0468-444a-ce81-0bf617d890df', # FFS1
    '8c8ce578-8a3d-4f1c-3599-896185c32dd3', # FFS2
    'fff12b8d-7696-4c8b-85a9-2747075b4f50', # NVRAM
    '04adeead-61ff-4d31-bab6-64f8bf901f5a', # Apple Boot Volume

    'cef5b9a3-476d-497f-dc9f-e98143e0422c', # NVRAM
]

FIRMWARE_CAPSULE_GUIDS = [
    '3b6686bd-0d76-4030-0eb7-b5519e2fc5a0', # EFI Capsule
    '4a3ca68b-7723-48fb-803d-578cc1fec44d', # EFI Capsule v2
    '539182b9-abb5-4391-9ab6-e3a943f72fcc', # UEFI Capsule
    '6dcbd5ed-e82d-4c44-a1bd-7194199ad92a', # Firmware Management Capsule
]

FIRMWARE_GUIDED_GUIDS = {
    "LZMA_COMPRESSED": "ee4e5898-3914-4259-6e9d-dc7bd79403cf",
    "FIRMWARE_VOLUME": "24400798-3807-4a42-13b4-a1ecee205dd8",
    #"VOLUME_SECTION":  "367ae684-335d-4671-6da1-899dbfea6b88",
    "STATIC_GUID":     "fc1bcdb0-7d31-49aa-6a93-a4600d9dd083"
}

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

class FirmwareVolumeType(ctypes.LittleEndianStructure):
    _fields_ = [
        ("Reserved",   char*16),  # Zeros
        ("Guid",       char*16),  #
        ("Size",       uint64_t), 
        ("Magic",      char*4),
        ("Attributes", uint8_t),
        ("HeaderSize", uint32_t),
        ("Checksum",   uint16_t),
        ("Reserved2",  uint8_t),
        ("Revision",   uint8_t)
    ]
