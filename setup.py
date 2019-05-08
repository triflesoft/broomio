#!/usr/bin/env python3

from datetime import datetime
from setuptools import find_packages
from setuptools import setup
from subprocess import run

with open('README.rst', 'r') as readme_file:
    readme_text = readme_file.read()

with open('LICENSE') as license_file:
    license_text = license_file.read()

commit_datetime = datetime.min

git = run(['git', 'log', '--max-count=1', '--format=%ct'], capture_output=True)

if git.returncode == 0:
    commit_timestamp = int(git.stdout.strip(b'\n'))
    commit_datetime = datetime.utcfromtimestamp(commit_timestamp)

version = f'0.2.{commit_datetime:%y%m%d}'

setup(
    name='broomio',
    version=version,
    author='Roman Akopov',
    author_email='adontz@gmail.com',
    # maintainer='',
    # maintainer_email='',
    url='https://github.com/triflesoft/broomio',
    license=license_text,
    description='Broomio',
    long_description=readme_text,
    long_description_content_type='text/markdown',
    # keywords='',
    # platforms='',
    # fullname='',
    # contact='',
    # contact_email='',
    classifiers=[
        'Development Status :: 4 - Beta',
        'Environment :: Console',
        'Environment :: Web Environment',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: GNU Lesser General Public License v3 (LGPLv3)',
        'Operating System :: OS Independent',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
    ],
    # download_url='',
    # provides='',
    # requires='',
    # obsoletes='',
    packages=find_packages(exclude=('docs', 'examples', 'tests')),
)
