import os

from setuptools import setup

here = os.path.dirname(os.path.abspath(__file__))
try:
    with open(os.path.join(here, "README.md"), encoding="utf-8") as f:
        long_description = f.read()
except OSError:
    long_description = ""

setup(
    name="esex",
    version="5.6.0",
    description="True Native PE Compiler for ES (Executable Script) DSL",
    long_description=long_description,
    long_description_content_type="text/markdown",
    py_modules=["esex"],
    entry_points={
        "console_scripts": [
            "esex=esex:main",
        ],
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "Operating System :: Microsoft :: Windows",
        "Topic :: Software Development :: Compilers",
    ],
    python_requires=">=3.7",
)
