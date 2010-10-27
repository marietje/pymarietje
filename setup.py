#!/usr/bin/env python

from setuptools import setup
from get_git_version import get_git_version

setup(name='pymarietje',
      version=get_git_version(),
      description='Curses client for MarietjeD music daemon',
      author='Bas Westerbaan',
      author_email='bas@westerbaan.name',
      url='http://github.com/bwesterb/pymarietje/',
      packages=['pymarietje'],
      package_dir={'pymarietje': 'src'},
      install_requires = ['docutils>=0.3',
	      		  'mutagen>=1.20',
			  'pyyaml>=3.00'],
      entry_points = {
	      'console_scripts': [
		      'upload-to-marietje = pymarietje.upload:main',
		      'marietje = pymarietje.cursesui:main',
	      ]}
      )
