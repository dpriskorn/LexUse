#!/usr/bin/env python3
import argparse
import logging

import util

# This script enables finding example sentences via the Riksdagen API where
# everything is out of copyright

#
# Functions
#


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-l",
        "--log",
        help="Loglevel",
    )
    args = parser.parse_args()
    loglevel = args.log
    if loglevel:
        numeric_level = getattr(logging, loglevel.upper(), None)
        if not isinstance(numeric_level, int):
            raise ValueError('Invalid log level: %s' % loglevel)
        logging.basicConfig(level=numeric_level)
    else:
        logging.basicConfig()
    logging.captureWarnings(True)
    # async_fetch_from_riksdagen("test")
    # exit(0)

    begin = util.introduction()
    if begin:
        #
        # Instantiation
        #
        print("Fetching lexeme forms to work on")
        results = util.fetch_lexeme_forms()
        util.process_lexeme_data(results)


if __name__ == "__main__":
    main()
