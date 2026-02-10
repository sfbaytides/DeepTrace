"""Setup configuration for DeepTrace package."""

from setuptools import find_packages, setup

setup(
    name="deeptrace",
    version="0.1.0",
    description="Cold case investigation platform with AI analysis",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    python_requires=">=3.11",
    install_requires=[
        "Flask>=3.1.0",
        "Werkzeug>=3.1.3",
        "gunicorn>=23.0.0",
        "typer>=0.15.1",
        "click>=8.1.8",
        "requests>=2.32.3",
        "httpx>=0.28.1",
        "python-dotenv>=1.0.1",
    ],
    entry_points={
        "console_scripts": [
            "deeptrace=deeptrace.main:app",
        ],
    },
)
