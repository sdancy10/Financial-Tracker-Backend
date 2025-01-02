from setuptools import setup, find_packages

setup(
    name="financial-tracker",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        'functions-framework',
        'google-cloud-secret-manager',
        'google-cloud-firestore',
        'google-cloud-pubsub',
        'google-cloud-logging',
        'google-cloud-scheduler',
        'google-cloud-functions',
        'requests',
        'pyyaml'
    ],
    python_requires='>=3.10',
) 