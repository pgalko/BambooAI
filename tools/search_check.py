#!/usr/bin/env python3
"""The Web Search seat run once on a hosted box: bambooai/web_search.py's check, with the app's environment. It says
the searches run, the sources that came back, the tokens and the cost, and shows what the analyst would read. Run it
from the web app's folder, as the app's user; nothing is written to the usage table and nothing is charged to an
account - the provider is paid as for any search.

    python3 ../tools/search_check.py "average wheat yield per hectare, world, latest year"
    python3 ../tools/search_check.py --raw "..."                    # with OpenRouter's reply as it came
    python3 ../tools/search_check.py --engine parallel "..."        # for this run, another of the configuration's engines
    python3 ../tools/search_check.py --model gemini-flash-latest --provider gemini "..."
                                                                    # ... the seat on Gemini: it says which model the alias answered as
    python3 ../tools/search_check.py --level max "..."              # the seat of another level of the template

In the self-hosted edition's working folder, whose .env it reads: python -m bambooai.web_search "..."
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.dirname(HERE), HERE]


def main(argv=None):
    from memory_ask import environment
    environment()               # the box's files in the order its gunicorn loads them, then the .env
    from bambooai import web_search
    return web_search.main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
