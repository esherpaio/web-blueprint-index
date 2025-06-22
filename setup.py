from setuptools import find_packages, setup

from version import __version__

DATA = [
    "*.md",
    "static/*.css",
    "static/*.js",
    "templates/*.txt",
    "templates/*.xml",
]


def find_requirements() -> list[str]:
    with open("requirements.txt") as f:
        lines = f.read().splitlines()
    filtered = [x for x in lines if x and not x.startswith(("#", "git+"))]
    return filtered


setup(
    name="web-blueprint-index",
    url="https://github.com/esherpaio/web-blueprint-index",
    version=__version__,
    author="H.P. Mertens",
    python_requires=">=3.11",
    install_requires=find_requirements(),
    include_package_data=True,
    package_data={"": DATA},
    packages=find_packages(include=["web_bp_index", "web_bp_index.*"]),
)
