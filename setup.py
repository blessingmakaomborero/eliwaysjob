from setuptools import setup, find_packages

setup(
    name="eliways_jobs",
    version="0.1.0",
    description="Eliways Jobs Portal — custom Frappe app for Job Portal integration",
    author="Eliways Solutions",
    author_email="dev@eliwayssolutions.co.zw",
    packages=find_packages(),
    zip_safe=False,
    include_package_data=True,
    install_requires=["frappe"],
)
