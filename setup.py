from setuptools import setup, find_packages
import os

with open("README.md", "r") as fh:
    long_description = fh.read()

setup(
    name='bambooai',
    version='0.4.03',
    description='A lightweight library for working with pandas dataframes using natural language queries',
    long_description=long_description,
    long_description_content_type="text/markdown",
    author='Palo Galko',
    packages=find_packages(),
    install_requires=[
        'openai',
        'tiktoken',
        'pandas',
        'numpy',
        'pyarrow',
        'matplotlib',
        'seaborn',
        'plotly',
        'termcolor',
        'newspaper3k',
        'pinecone',
        'selenium',
        'google-generativeai',
        'google-genai',
        'groq',
        'ollama',
        'anthropic',
        'mistralai',
        'flask',
        'ipython',
        'nbformat',
        'python-dotenv',
        'lxml[html_clean]',
        'gunicorn',
        'google-cloud-storage',
        'statsmodels',
        'scipy',
        'scikit-learn',
        'geopandas',
        'yfinance'
    ],
    classifiers=[
        'Development Status :: 3 - Alpha',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 3',
    ],
)