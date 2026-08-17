from setuptools import setup

setup(
    name="esex",
    version="3.5.0",
    description="True Native PE Compiler for ES (Executable Script) DSL",
    py_modules=["esex"],
    entry_points={
        "console_scripts": [
            "esex=esex:main",
        ],
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "Operating System :: Microsoft :: Windows",
    ],
    python_requires=">=3.6",
)
