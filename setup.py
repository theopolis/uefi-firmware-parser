#!/usr/bin/env python

import os
import re
from setuptools import setup, find_packages, Extension, Command


class LintCommand(Command):
    """Run pylint on implementation and test code"""

    description = "Run pylint on implementation and test code"
    user_options = []

    _pylint_options = [
        "--max-line-length 80",
        "--ignore-imports yes"
    ]

    _lint_paths = [
        "uefi_firmware/*.py",
        "uefi_firmware/*/*.py",
        "tests/*.py",
        "scripts/*.py",
        "scripts/contrib/*.py",
    ]

    def initialize_options(self):
        """Set default values for options."""
        pass

    def finalize_options(self):
        """Post-process options."""
        pass

    def run(self):
        """Run the command"""
        os.system("pylint %s %s" % (
            " ".join(self._pylint_options),
            " ".join(self._lint_paths),
        ))

with open('README.rst') as f:
    README = f.read()

with open("uefi_firmware/__init__.py", "r") as f:
    __INIT__ = f.read()

VERSION = re.search(r'^__version__\s*=\s*[\'"]([^\'"]*)[\'"]',
                    __INIT__, re.MULTILINE).group(1)
AUTHOR = re.search(r'^__author__\s*=\s*[\'"]([^\'"]*)[\'"]',
                   __INIT__, re.MULTILINE).group(1)

COMPRESSION_SOURCES = []
COMPRESSION_HEADERS = []
for root, directory, paths in os.walk('uefi_firmware/compression'):
    for path in paths:
        if os.path.splitext(path)[1][1:] == 'h':
            COMPRESSION_HEADERS.append(os.path.join(root, path))
        else:
            COMPRESSION_SOURCES.append(os.path.join(root, path))

setup(
    name='uefi_firmware',
    version=VERSION,
    description='Various data structures and parsing tools for UEFI firmware.',
    long_description=README,
    author=AUTHOR,
    author_email='teddy@prosauce.org',
    url='https://github.com/theopolis/uefi-firmware-parser',
    license='BSD',
    packages=find_packages(exclude=('tests', 'docs')),
    test_suite="tests",
    cmdclass={
        "lint": LintCommand,
    },
    headers=COMPRESSION_HEADERS,
    ext_modules=[
        Extension(
            'uefi_firmware.efi_compressor',
            sources=COMPRESSION_SOURCES,
            include_dirs=[
                os.path.join("uefi_firmware", 'compression', 'Include')
            ],
            depends=COMPRESSION_HEADERS,
        )
    ],
    scripts=[
        'bin/uefi-firmware-parser',
    ],

    classifiers=[
        # https://pypi.python.org/pypi?%3Aaction=list_classifiers
        'Development Status :: 4 - Beta',
        'Intended Audience :: System Administrators',
        'Topic :: Security',
        'License :: OSI Approved :: BSD License',
        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 2.6',
        'Programming Language :: Python :: 2.7',
    ],
    keywords="security uefi firmware parsing bios",
)
