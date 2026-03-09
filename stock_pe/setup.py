#!/usr/bin/env python2
# This file is part of Tryton.  The COPYRIGHT file at the top level of
# this repository contains the full copyright notices and license terms.

import io
import re
import os
import time
import sys
import unittest
import configparser
from setuptools import setup, Command


def read(fname):
    return open(os.path.join(os.path.dirname(__file__), fname)).read()


class SQLiteTest(Command):
    """
    Run the tests on SQLite
    """
    description = "Run tests on SQLite"

    user_options = []

    def initialize_options(self):
        pass

    def finalize_options(self):
        pass

    def run(self):
        if self.distribution.tests_require:
            self.distribution.fetch_build_eggs(self.distribution.tests_require)

        os.environ['TRYTOND_DATABASE_URI'] = 'sqlite://'
        os.environ['DB_NAME'] = ':memory:'

        from .tests import suite
        test_result = unittest.TextTestRunner(verbosity=3).run(suite())

        if test_result.wasSuccessful():
            sys.exit(0)
        sys.exit(-1)


class PostgresTest(Command):
    """
    Run the tests on Postgres.
    """
    description = "Run tests on Postgresql"

    user_options = []

    def initialize_options(self):
        pass

    def finalize_options(self):
        pass

    def run(self):
        if self.distribution.tests_require:
            self.distribution.fetch_build_eggs(self.distribution.tests_require)

        os.environ['TRYTOND_DATABASE_URI'] = 'postgresql://'
        os.environ['DB_NAME'] = 'test_' + str(int(time.time()))

        from .tests import suite
        test_result = unittest.TextTestRunner(verbosity=3).run(suite())

        if test_result.wasSuccessful():
            sys.exit(0)
        sys.exit(-1)


config = configparser.ConfigParser()
config.readfp(open('tryton.cfg'))
info = dict(config.items('tryton'))
for key in ('depends', 'extras_depend', 'xml'):
    if key in info:
        info[key] = info[key].strip().splitlines()
version = info.get('version', '0.0.1')
major_version, minor_version, _ = version.split('.', 2)
major_version = int(major_version)
minor_version = int(minor_version)
name = 'trytond_stock_pe'

download_url = 'https://pypi.org/project/trytond-party-pe/%s' % (version)
requires = []

MODULE = "stock_pe"
PREFIX = "trytond"
MODULE2PREFIX = {}
for dep in info.get('depends', []):
    if not re.match(r'(ir|res|webdav)(\W|$)', dep):
        requires.append(
            '%s_%s >= %s.%s, < %s.%s' % (
                MODULE2PREFIX.get(dep, 'trytond'), dep,
                major_version, minor_version, major_version,
                minor_version + 1
            )
        )
requires.append(
    'trytond >= %s.%s, < %s.%s' % (
        major_version, minor_version, major_version, minor_version + 1
    )
)

requires.append('python-sql >= 0.4')
requires.append('zeep==3.1.0')
requires.append('signxml==2.5.2')

setup(
    name=name,
    version=version,
    description='Peruvian localization for the stock module',
    long_description=read('README'),
    author='Connecttix',
    author_email='info@connecttix.pe',
    url='http://connecttix.pe/',
    download_url=download_url,
    keywords='stock peru almacen',
    package_dir={'trytond.modules.%s' % MODULE: '.'},
    packages=[
        'trytond.modules.%s' % MODULE,
        'trytond.modules.%s.tests' % MODULE,
        'trytond.modules.%s.sunat' % MODULE,
        ],
    package_data={
        'trytond.modules.%s' % MODULE: info.get('xml', [])
        + info.get('translation', []) + [
            'tryton.cfg', 'view/*.xml', '*.fodt', '*.odt',
            'icons/*.svg', 'tests/*.rst', 'sunat/maindoc/*.xsd',
            'sunat/template/*.xml'
            ]},
    classifiers=[
        'Development Status :: 4 - Production/Stable',
        'Environment :: Plugins',
        'Framework :: Tryton',
        'Intended Audience :: Developers',
        'Intended Audience :: Financial and Insurance Industry',
        'Intended Audience :: Legal Industry',
        'Intended Audience :: Manufacturing',
        'License :: OSI Approved :: GNU General Public License v3 or later (GPLv3+)',
        'Natural Language :: Spanish',
        'Operating System :: OS Independent',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: Implementation :: PyPy',
        'Topic :: Office/Business :: Financial :: Logistics',
        ],
    license='GPL-3',
    python_requires='>=2.7',
    install_requires=requires,
    zip_safe=False,
    entry_points="""
    [trytond.modules]
    {module_name} = trytond.modules.{module_name}
    """.format(module_name=MODULE),
    test_suite='tests',
    test_loader='trytond.test_loader:Loader',
    cmdclass={
        'test': SQLiteTest,
        'test_on_postgres': PostgresTest,
    })
