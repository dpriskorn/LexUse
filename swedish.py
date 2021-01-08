#!/usr/bin/env python3
import logging

import config
import loglevel
import util

# This script enables finding example sentences via the Riksdagen API where
# everything is out of copyright

#
# Functions
#


# def setup_logging():
#     parser = argparse.ArgumentParser()
#     parser.add_argument(
#         "-l",
#         "--log",
#         help="Loglevel",
#     )
#     args = parser.parse_args()
#     loglevel = args.log
#     if loglevel:
#         numeric_level = getattr(logging, loglevel.upper(), None)
#         if not isinstance(numeric_level, int):
#             raise ValueError('Invalid log level: %s' % loglevel)
#         config.loglevel = numeric_level
#         print(f"Setting loglevel {numeric_level}")
#         reload(logging)
#         logging.basicConfig(level=numeric_level)
#     else:
#         logging.basicConfig()
#     logging.captureWarnings(True)


def main():
    # async_fetch_from_riksdagen("test")
    # exit(0)
    logger = logging.getLogger(__name__)
    if config.loglevel is None:
        # Set loglevel
        loglevel.set_loglevel()
    logger.setLevel(config.loglevel)
    logger.level = logger.getEffectiveLevel()
    # file_handler = logging.FileHandler("europarl.log")
    # logger.addHandler(file_handler)
    begin = util.introduction()
    if begin:
        print("Fetching lexeme forms to work on")
        results = util.fetch_lexeme_forms()
        util.process_lexeme_data(results)


if __name__ == "__main__":
    main()
