#!/usr/bin/env python
# -*- coding: utf-8 -*-

from setuptools import setup, find_packages
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

with open(BASE_DIR / "requirements.txt") as f:
    requirements = [line.strip() for line in f if line.strip() and not line.startswith("#")]

with open(BASE_DIR / "README.md", encoding="utf-8") as f:
    long_description = f.read()

setup(
    name="Elyra",
    version="1.0.0",
    description="Assistente IA profissional multi-provedor com interface desktop",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="Seu Nome",
    author_email="seu@email.com",
    url="https://github.com/Eduxfuhd0909/Elyra",
    license="MIT",
    packages=find_packages(),
    include_package_data=True,
    install_requires=requirements,
    python_requires=">=3.8",
    entry_points={
        "console_scripts": [
            "elyra=app:main",
        ],
    },
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Intended Audience :: End Users/Desktop",
        "Topic :: Communications :: Chat",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
    ],
)
