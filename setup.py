try:
    from setuptools import setup, find_packages
except ImportError:
    from ez_setup import use_setuptools
    use_setuptools()
    from setuptools import setup, find_packages

from fetcher import VERSION

setup(
    name='django_fetcher',
    version=VERSION,
    description='Fetcher',
    author='Maximiliano Mendez',
    author_email='',
    url='',
    install_requires=[
        "Django==1.2.3",
        "psycopg2==2.3.2",
        "Fabric==1.2.2",
        "pika==0.9.5",
        "boto==2.0b4",
    ],
    packages=find_packages(),
    include_package_data=True,
)
