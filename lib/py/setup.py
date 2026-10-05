# scribe-next modification: use the existing setuptools backend and current IDL output.
from setuptools import setup

setup(name='scribe',
      version='2.0',
      packages=['scribe'],
      package_dir={'scribe': '../../src/gen-py/scribe'},
      )
