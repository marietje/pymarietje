#!/usr/bin/env python

from setuptools import setup
from get_git_version import get_git_version

setup(name='pymarietje',
      version=get_git_version(),
      description='Curses client for MarietjeD music daemon',
      author='Bas Westerbaan',
      author_email='bas@westerbaan.name',
      url='http://github.com/marietje/pymarietje/',
      packages=['marietje'],
      package_dir={'marietje': 'src'},
      install_requires = ['docutils>=0.3',
                          'mutagen>=1.20',
                          'mirte>=0.1.5',
                          'sarah>=0.1.3',
                          'urwid>=1.0.0',
                          'py-joyce>=0.1.9']
      entry_points = {
              'console_scripts': [
                      'upload-to-marietje = marietje.upload:main',
                      'marietje = marietje.cursesui:main',
              ]}
      )

# vim: et:sta:bs=2:sw=4:
