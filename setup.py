from pathlib import Path
import setuptools

# The text of the README file
README = Path("README.md").read_text()

version = "0.6.0"
assert "." in version

setuptools.setup(
    name="doe-dap-dl",
    version=version,
    description="Packages for Jupyter Notebook users to interact with data from A2e, Livewire, and the SPP data platform.",
    long_description=README,
    long_description_content_type="text/markdown",
    url="https://github.com/DAP-platform/dap-py",
    author="DAP-Platform",
    author_email="dapteam@pnnl.gov",
    license="MIT",
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Natural Language :: English",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Topic :: Scientific/Engineering",
        "Intended Audience :: Science/Research",
        "Operating System :: OS Independent",
    ],
    packages=setuptools.find_packages(exclude=["docs", "tests", "examples"]),
    include_package_data=True,
    zip_safe=False,
    install_requires=[
        "requests",
        "matplotlib",
        "numpy",
        "netcdf4"
    ],
    scripts=[],
)
