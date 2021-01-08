#!/usr/bin/env python3
import logging

import config
import loglevel
import riksdagen
import util

# This script enables finding example sentences via the Riksdagen API where
# everything is out of copyright

#
# Functions
#


def main():
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
