# LexUse
Scripts used to find and add usage examples to Wikidata Lexemes. All scripts here are licensed under GPL-v3

## swedish.py
Script used to semi-automatically import usage examples from the Riksdagen Open Data API (400.000 documents) and RAÄ K-samsök (10 mio. items). 

To get started install the following libraries with your package manager or python PIP:
* jellyfish
* requests
* LexData
* wikibaseintegrator

Please create a bot password for running the script for
safety reasons here: https://www.wikidata.org/wiki/Special:BotPasswords

Create a file named config.py yourself with the following content:
username = "username"
password= "password"
