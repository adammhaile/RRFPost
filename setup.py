# -*- coding: utf-8 -*-
from setuptools import setup, find_packages
import os

# with open('./requirements.txt') as f:
#     INSTALL_REQUIRES = f.read().splitlines()


def _get_version():
    from os.path import abspath, dirname, join
    filename = join(dirname(abspath(__file__)), 'rrfpost', 'version.py')
    line = open(filename).read()
    return line.replace('VERSION=', '').strip().strip("'")

setup(
    name="rrfpost",
    author="Adam Haile",
    author_email="adammhaile@gmail.com",
    version=_get_version(),
    description="CLI tool for post-processing RRF/Duet gcode files",
    long_description=open('README.md').read(),
    url="https://github.com/adammhaile/RRFPost",
    license="GNU Affero General Public License v3 or later (AGPLv3+)",
    packages=find_packages(exclude=[]),
    include_package_data=True,
    entry_points={
            'console_scripts': [
                'rrfpost = rrfpost:main',
                'rrp = rrfpost:main',
            ]
        },
    # install_requires=INSTALL_REQUIRES,
    dependency_links=[],
    classifiers=[
        "Development Status :: 4 - Beta",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Environment :: Console",
        "License :: OSI Approved :: GNU Affero General Public License v3 or later (AGPLv3+)",
        "Natural Language :: English",
    ]
)