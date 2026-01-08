from setuptools import find_packages, setup


setup(
    name="sceptre-zip-code-s3",
    version="2.1.0",
    description="Sceptre hook and resolver to package code and fetch S3 object versions.",
    author="Cloudreach / WCS (updated for Sceptre v4)",
    packages=find_packages(exclude=["src", "templates", "example", "examples", "tests"]),
    install_requires=[
        "sceptre>=4,<5",
        "boto3",
    ],
    python_requires=">=3.8",
    entry_points={
        "sceptre.resolvers": [
            "s3_version = resolvers.s3_version:S3Version",
        ],
        "sceptre.hooks": [
            "s3_package = hooks.s3_package:S3Package",
        ],
    },
)
