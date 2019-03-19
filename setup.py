#!/usr/bin/env python3

from setuptools import find_packages
from setuptools import setup

with open('README.rst', 'r') as readme_file:
    readme_text = readme_file.read()

with open('LICENSE') as license_file:
    license_text = license_file.read()

setup(
    name='broomio',
    version='0.0.1',
    author='Roman Akopov',
    author_email='adontz@gmail.com',
    description='Broomio',
    license=license_text,
    long_description=readme_text,
    long_description_content_type='text/markdown',
    url='https://github.com/triflesoft/broomio',
    packages=find_packages(exclude=('tests', 'docs')),
    classifiers=[
        'Development Status :: 4 - Beta',
        'Environment :: Console',
        'Environment :: Web Environment',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: GNU Lesser General Public License v3 (LGPLv3)',
        # 'Operating System :: OS Independent',
        'Operating System :: POSIX :: Linux',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
    ],
)

