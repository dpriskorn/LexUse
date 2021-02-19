# Warning
**PLEASE DON'T USE IT BEFORE ISSUE 19 HAS BEEN FIXED**

This is a quick alpha version. Development continues in the [LexUtils repo](https://github.com/egils-consulting/LexUtils) and this repo will soon be archived. See all tool ideas from the author here: https://www.wikidata.org/wiki/User:So9q/Tool_ideas

# LexUse
Scripts used to find and add usage examples to Wikidata Lexemes. All scripts
here are licensed under GPL-v3 or later unless they are snippets from someone
else (source is then noted above the code)

LexUse can be used as a library if you want. It contains the following modules:
* config: setting up variables that affect all scripts
* riksdagen: code related to the Riksdagen API
* util: code reused among the language specific scripts 

## Requirements
* Python >= 3.7 (datetime fromisoformat needed)
* httpx
* wikibaseintegrator

Install using pip:
`$ sudo pip install wikibaseintegrator httpx`

If pip fails with errors related to python 2.7 you need to upgrade your OS. E.g. if you are using an old version of Ubuntu like 18.04.

## Getting started
To get started install the following libraries with your package manager or
python PIP:
* httpx
* wikibaseintegrator

Please create a bot password for running the script for
safety reasons here: https://www.wikidata.org/wiki/Special:BotPasswords

Add the following variables to your ~/.bashrc (recommended): 
export LEXUSE_USERNAME="username"
export LEXUSE_PASSWORD="password"

Alternatively edit the file named config.py yourself and adjust the following
content:

username = "username"
password= "password"

And delete the 2 lines related to environment labels.

## Language specific scripts
Please help add support for more languages by making pull requests or issues
with suggestions for new CC0 or out of copyright sources.

Maybe a wikisource module would be nice?

### swedish.py
Script used to semi-automatically import usage examples from the Riksdagen Open
Data API (400.000 documents) and possibly later from RAÄ K-samsök (10 mio. items
with CC0 metadata) and https://www.wikidata.org/wiki/Q5412081.

## For developers
It might be worthwile to add a REPL to the script and let the user choose what
language to work on. 
For now they have to start the script named after the language to work on.

### Pseudo code describing the internal operation of the script
fetch a list of lexeme forms and words
loop through the list
 search for the word in choosen api
 extract sentence
 clean sentence
 present sentence for approval
   if approved
     if number of sense=1
       present sense for approval
     else
       present senses for approval and ask the user to choose 1
     add "demonstrates form"
     add "demonstrates sense"
     add a reference
     upload to WD
