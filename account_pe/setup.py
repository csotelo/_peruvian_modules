#!/usr/bin/env python

import re
import os
import time
import sys
import unittest
import configparser
from setuptools import setup, Command
from io import open


def read(fname):
    return open(os.path.join(os.path.dirname(__file__), fname)).read()


class SQLiteTest(Command):
    """Run the tests on SQLite."""
    description = 'Run tests on SQLite'

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
    """Run the tests on Postgres."""
    description = 'Run tests on Postgresql'

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
major_version, minor_version, _ = info.get('version', '0.0.1').split('.', 2)
major_version = int(major_version)
minor_version = int(minor_version)

requires = ['configparser', 'pywebdav']

MODULE2PREFIX = {}

MODULE = 'account_pe'
PREFIX = 'trytond'
for dep in info.get('depends', []):
    if not re.match('(ir|res|webdav)(\W|$)', dep):
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

package_data = {
    'trytond.modules.%s' % MODULE: info.get('xml', [])
    + info.get('translation', [])
    + ['tryton.cfg', 'tests/*.rst']
    + ['view/*.xml', 'report/*.*']
}
setup(
    name='%s_%s' % (PREFIX, MODULE),
    version=info.get('version', '3.8.0'),
    description='Peruvian localization for account module',
    author='Grupo ConnectTix SAC',
    author_email='info@connecttix.pe',
    url='http://connecttix.pe',
    package_dir={'trytond.modules.%s' % MODULE: '.'},
    packages=[
        'trytond.modules.%s' % MODULE,
        'trytond.modules.%s.tests' % MODULE,
    ],
    package_data=package_data,
    classifiers=[
        'Development Status :: 4 - Beta',
        'Environment :: Plugins',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: GNU General Public License (GPL)',
        'Natural Language :: Spanish',
        'Operating System :: OS Independent',
        'Programming Language :: Python :: 2.7',
        'Framework :: Tryton',
        'Topic :: Office/Business',
        'Topic :: Office/Business :: Financial :: Accounting',
    ],
    long_description=open('README').read(),
    license='GPL-3',
    install_requires=requires,
    zip_safe=False,
    entry_points='''
    [trytond.modules]
    %s = trytond.modules.%s
    ''' % (MODULE, MODULE),
    test_suite='tests',
    test_loader='trytond.test_loader:Loader',
    cmdclass={
        'test': SQLiteTest,
        'test_on_postgres': PostgresTest,
    }
)
