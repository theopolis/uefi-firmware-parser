#!/usr/bin/env python

import os
import re
import sysconfig

from setuptools import Command, Extension, find_packages, setup


class LintCommand(Command):
    """Run pylint on implementation and test code"""

    description = "Run pylint on implementation and test code"
    user_options = []

    _pylint_options = ["--max-line-length 80", "--ignore-imports yes"]

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
        os.system(
            "pylint %s %s"
            % (
                " ".join(self._pylint_options),
                " ".join(self._lint_paths),
            )
        )


with open("README.rst") as f:
    README = f.read()

with open("uefi_firmware/__init__.py", "r") as f:
    __INIT__ = f.read()

AUTHOR = re.search(
    r'^__author__\s*=\s*[\'"]([^\'"]*)[\'"]', __INIT__, re.MULTILINE
).group(1)

COMPRESSION_SOURCES = []
COMPRESSION_HEADERS = []
for root, directory, paths in os.walk("uefi_firmware/compression"):
    for path in paths:
        if os.path.splitext(path)[1][1:] == "h":
            COMPRESSION_HEADERS.append(os.path.join(root, path))
        elif os.path.splitext(path)[1][1:] == "c":
            COMPRESSION_SOURCES.append(os.path.join(root, path))

IS_FREE_THREADED = sysconfig.get_config_var("Py_GIL_DISABLED") == 1
USE_LIMITED_API = not IS_FREE_THREADED

if USE_LIMITED_API:
    extension_options = {
        "define_macros": [("Py_LIMITED_API", "0x030A0000")],
        "py_limited_api": True,
    }
    options = {
        "bdist_wheel": {
            "py_limited_api": "cp310",
        }
    }
else:
    extension_options = {}
    options = {}


setup(
    name="uefi_firmware",
    use_scm_version={
        "write_to": "uefi_firmware/_version.py",
        "fallback_version": "0.1.0+unknown",
    },
    description="Various data structures and parsing tools for UEFI firmware.",
    long_description=README,
    author=AUTHOR,
    author_email="",
    url="https://github.com/theopolis/uefi-firmware-parser",
    license="BSD-3-Clause",
    packages=find_packages(exclude=("tests", "docs")),
    cmdclass={
        "lint": LintCommand,
    },
    headers=COMPRESSION_HEADERS,
    ext_modules=[
        Extension(
            "uefi_firmware.efi_compressor",
            sources=COMPRESSION_SOURCES,
            include_dirs=[os.path.join("uefi_firmware", "compression", "Include")],
            depends=COMPRESSION_HEADERS,
            **extension_options,
        )
    ],
    python_requires=">=3.10",
    options=options,
    scripts=[
        "bin/uefi-firmware-parser",
    ],
    install_requires=["future"],
    extras_require={
        "tests": ["dictdiffer"],
    },
    classifiers=[
        # https://pypi.python.org/pypi?%3Aaction=list_classifiers
        "Development Status :: 4 - Beta",
        "Intended Audience :: System Administrators",
        "Topic :: Security",
        "Programming Language :: Python :: 3",
    ],
    keywords="security uefi firmware parsing bios",
)
