UEFI Firmware Parser
====================

.. image:: https://travis-ci.org/theopolis/uefi-firmware-parser.svg?branch=master
    :target: https://travis-ci.org/theopolis/uefi-firmware-parser


The UEFI firmware parser is a simple module and set of scripts for parsing, extracting, 
and recreating UEFI firmware volumes.
This includes parsing modules for BIOS, OptionROM, Intel ME and other formats too. 
Please use the example scripts for parsing tutorials.

Installation
------------

This module is included within PyPy as `uefi_firmware <https://pypi.python.org/pypi/uefi_firmware>`_

::

  $ sudo pip install uefi_firmware

To install from Github, checkout this repo and use:

::

  $ sudo python ./setup.py install

**Requirements**

- Python development headers, usually found in the ``python-dev`` package.
- The compression/decompression features will use the python headers and ``gcc``.
- ``pefile`` is optional, and may be used for additional parsing.

Usage
-----

The simplest way to use the module to detect or parse firmware is through the ``AutoParser`` class.

::

  import uefi_firmware
  with open('/path/to/firmware.rom', 'r') as fh:
    file_content = fh.read()
  parser = uefi_firmware.AutoParser(file_content)
  if parser.type() != 'unknown':
    firmware = parser.parse()
    firmware.showinfo()

There are several classes within the **uefi**, **pfs**, **me**, and **flash** packages that
accept file contents in their constructor. In all cases there are abstract methods implemented:

- ``process()`` performs parsing work and returns a ``True`` or ``False``
- ``showinfo()`` print a hierarchy of information about the structure
- ``dump()`` walk the hierarchy and write each to a file

Scripts
-------

A Python script is installed ``uefi-firmware-parser``

::

  $ uefi-firmware-parser -h
  usage: uefi-firmware-parser [-h] [-b] [--superbrute] [-q] [-o OUTPUT] [-O]
                              [-c] [-e] [-g GENERATE] [--test]
                              file [file ...]

  Parse, and optionally output, details and data on UEFI-related firmware.

  positional arguments:
    file                  The file(s) to work on

  optional arguments:
    -h, --help            show this help message and exit
    -b, --brute           The input is a blob and may contain FV headers.
    --superbrute          The input is a blob and may contain any sort of
                          firmware object
    -q, --quiet           Do not show info.
    -o OUTPUT, --output OUTPUT
                          Dump firmware objects to this folder.
    -O, --outputfolder    Dump firmware objects to a folder based on filename
                          ${FILENAME}_output/
    -c, --echo            Echo the filename before parsing or extracting.
    -e, --extract         Extract all files/sections/volumes.
    -g GENERATE, --generate GENERATE
                          Generate a FDF, implies extraction (volumes only)
    --test                Test file parsing, output name/success.

To test a file or directory of files:

::

  $ uefi-firmware-parser --test ~/firmware/*
  ~/firmware/970E32_1.40: UEFIFirmwareVolume
  ~/firmware/CO5975P.BIO: EFICapsule
  ~/firmware/me-03.obj: IntelME
  ~/firmware/O990-A03.exe: None
  ~/firmware/O990-A03.exe.hdr: DellPFS

If you need to parse and extract a large number of firmware files check out the ``-O`` option to auto-generate an output folder per file. If parsing and searching for internals in a shell the ``--echo`` option will print the input filename before parsing.

The firmware-type checker will decide how to best parse the file. If the ``--test`` option fails to identify the type, or calls it ``unknown``, try to use the ``-b`` or ``--superbrute`` option. The later performs a byte-by-byte type checker.
::

  $ uefi-firmware-parser --type ~/firmware/970E32_1.40
  ~/firmware/970E32_1.40: unknown
  $ uefi-firmware-parser --superbrute ~/firmware/970E32_1.40
  [...]

**Features**

- UEFI Firmware Volumes, Capsules, FileSystems, Files, Sections parsing
- Intel PCH Flash Descriptors
- Intel ME modules parsing (ME, TXE, etc)
- Dell PFS (HDR) updates parsing
- Tiano/EFI, and native LZMA (7z) [de]compression

- Complete UEFI Firmware volume object hierarchy display
- Firmware descriptor [re]generation using the parsed input volumes
- Firmware File Section injection

**GUID Injection**

Injection or GUID replacement (no addition/subtraction yet) can be performed on sections within a UEFI firmware file, or on UEFI firmware files within a firmware filesystem.

:: 

  $ python ./scripts/fv_injector.py -h
  usage: fv_injector.py [-h] [-c] [-p] [-f] [--guid GUID] --injection INJECTION
                        [-o OUTPUT]
                        file

  Search a file for UEFI firmware volumes, parse and output.

  positional arguments:
    file                  The file to work on

  optional arguments:
    -h, --help            show this help message and exit
    -c, --capsule         The input file is a firmware capsule.
    -p, --pfs             The input file is a Dell PFS.
    -f, --ff              Inject payload into firmware file.
    --guid GUID           GUID to replace (inject).
    --injection INJECTION
                          Pre-generated EFI file to inject.
    -o OUTPUT, --output OUTPUT
                          Name of the output file.

Note: when injecting into a firmware file the user will be prompted for which section to replace. At the moment this is not-yet-scriptable. 

**IDA Python support**

There is an included script to generate additional GUID labels to import into IDA Python
using Snare's plugins. Using the ``-g LABEL`` the script will generate a Python dictionary-formatted output. This project will try to keep up-to-date with popular vendor GUIDs automatically.

::

  $ python ./scripts/uefi_guids.py -h
  usage: uefi_guids.py [-h] [-c] [-b] [-d] [-g GENERATE] [-u] file

  Output GUIDs for files, optionally write GUID structure file.

  positional arguments:
    file                  The file to work on

  optional arguments:
    -h, --help            show this help message and exit
    -c, --capsule         The input file is a firmware capsule, do not search.
    -b, --brute           The input file is a blob, search for firmware volume
                          headers.
    -d, --flash           The input file is a flash descriptor.
    -g GENERATE, --generate GENERATE
                          Generate a behemoth-style GUID output.
    -u, --unknowns        When generating also print unknowns.

**Supported Vendors**

This module has been tested on BIOS/UEFI/firmware updates from the following vendors.
Not every update for every product will parse, some may required a-priori decompression
or extraction from the distribution update mechanism (typically a PE). 

- ASRock
- Dell
- Gigabyte
- Intel
- Lenovo
- HP
- MSI
- VMware
- Apple
