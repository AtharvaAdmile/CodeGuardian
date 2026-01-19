"""
CodeGuardian CLI - Package setup for pip installation.
"""

from setuptools import setup, find_packages

setup(
    name="codeguardian",
    version="2.0.0",
    description="AI-powered institutional memory for codebases",
    author="CodeGuardian Team",
    python_requires=">=3.9",
    packages=find_packages(),
    install_requires=[
        "typer[all]>=0.9.0",
        "rich>=13.0.0",
        "supabase>=2.0.0",
        "python-dotenv>=1.0.0",
        "google-generativeai>=0.3.0",
        "langchain>=0.1.0",
        "langgraph>=0.0.20",
        "httpx>=0.25.0",
        "toml>=0.10.0",
        "gitpython>=3.1.0",
        "tree-sitter>=0.20.0",
    ],
    extras_require={
        "dev": [
            "pytest>=7.0.0",
            "pytest-asyncio>=0.21.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "cgctl=cgctl.main:app",
        ],
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Environment :: Console",
        "Intended Audience :: Developers",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
    ],
)
