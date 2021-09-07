import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name='jqed',
    version='0.1.4',
    entry_points={
        'console_scripts': 'jqed=jqed.jqed:cli'
    },
    author="David Shlemayev",
    author_email="david.shlemayev@gmail.com",
    description="Process JSON data interactively using JQ",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/Wazzaps/jqed",
    packages=setuptools.find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "Environment :: Console",
        "License :: OSI Approved :: GNU General Public License v3 (GPLv3)",
        "Operating System :: POSIX :: Linux",
        "Intended Audience :: End Users/Desktop",
        "Intended Audience :: Developers",
        "Intended Audience :: Science/Research",
        "Intended Audience :: System Administrators",
        "Topic :: Utilities",
        "Topic :: Scientific/Engineering :: Information Analysis",
        "Topic :: Text Processing",
    ],
    install_requires=[
        'urwid >= 2.1',
        'urwid-readline >= 0.13',
    ],
)
