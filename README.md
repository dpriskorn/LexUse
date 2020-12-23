# LexUse
Scripts used to find and add usage examples to Wikidata Lexemes. All scripts here are licensed under GPL-v3

## swedish.py
Script used to semi-automatically import usage examples from the Riksdagen Open Data API (400.000 documents) and possibly later from RAÄ K-samsök (10 mio. items with CC0 metadata) and https://www.wikidata.org/wiki/Q5412081. 

To get started install the following libraries with your package manager or python PIP:
* httpx
* wikibaseintegrator

Please create a bot password for running the script for
safety reasons here: https://www.wikidata.org/wiki/Special:BotPasswords

Create a file named config.py yourself with the following content:
username = "username"
password= "password"
