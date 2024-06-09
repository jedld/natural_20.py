from setuptools import setup, find_packages

setup(
    name="natural20.py",
    version="0.1",
    packages=find_packages(),
    install_requires=[
        "pyyaml",
        "dndice",
        "python-i18n"
    ]
)