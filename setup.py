# -*- coding: utf-8 -*-

from setuptools import setup, find_packages

with open('README.rst') as f:
    readme = f.read()

with open('LICENSE') as f:
    license = f.read()

setup(name='UEFI Firmware Parser',
      version='0.2',
      description='Various data structures and parsing tools for UEFI firmware.',
      long_description=readme,
      author='Teddy Reed',
      author_email='teddy@prosauce.org',
      license=license,
      packages=find_packages(exclude=('tests', 'docs'))
     )

