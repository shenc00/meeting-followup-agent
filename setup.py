from setuptools import setup, find_packages

setup(
    name="meeting-followup-agent",
    version="0.1.0",
    description="AI-powered executive assistant for meeting follow-up automation",
    python_requires=">=3.11",
    packages=find_packages(exclude=["tests*"]),
    install_requires=[
        "pydantic>=2.7.0",
        "pydantic-settings>=2.3.0",
        "python-dateutil>=2.9.0",
        "pyyaml>=6.0.1",
        "jinja2>=3.1.4",
        "rich>=13.7.0",
        "typer>=0.12.3",
        "openai>=1.35.0",
        "tiktoken>=0.7.0",
        "msal>=1.29.0",
        "tinydb>=4.8.0",
        "tinydb-serialization>=2.1.0",
        "croniter>=2.0.5",
        "pytz>=2024.1",
    ],
    entry_points={
        "console_scripts": [
            "meeting-agent=meeting_agent.cli:app",
        ],
    },
    classifiers=[
        "Programming Language :: Python :: 3.11",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
)
