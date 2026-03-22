from setuptools import setup, find_packages

setup(
    name="comfyui-cli",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "click>=8.1,<9",
        "requests>=2.31,<3",
        "pyyaml>=6.0,<7",
    ],
    extras_require={
        "docs": ["qdrant-client>=1.9,<2", "openai>=1.30,<2"],
    },
    entry_points={
        "console_scripts": [
            "comfyui-cli=comfyui_cli.main:main",
        ],
    },
    python_requires=">=3.10",
)
