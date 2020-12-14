#!/usr/bin/env python3
import datetime
import requests
# from pprint import pprint
import re
# import LexData
# import logging
from wikibaseintegrator import wbi_core, wbi_login

import config

# This script enables finding example sentences via the Riksdagen API where
# everything is CC0

# Pseudo code
# fetch a list of swedish lexeme forms and words
# loop through the list
#  search for the word in riksdagen api
#  extract sentence
#  present for approval
#    if approved
#      add "demonstrates form"
#      add "demonstrates sense"
#      add a reference
#      upload to WD

# Settings
language = "swedish"
# Logging for LexData
# logging.basicConfig(level=logging.INFO)

#
# Instantiation
#
# Authenticate with WikibaseIntegrator
global login_instance
login_instance = wbi_login.Login(user=config.username, pwd=config.password)


#
# Functions
#


def yes_no_question(message: str):
    # https://www.quora.com/
    # I%E2%80%99m-new-to-Python-how-can-I-write-a-yes-no-question
    # this will loop forever
    while True:
        answer = input(message + ' [Y/n]: ')
        if len(answer) == 0 or answer[0].lower() in ('y', 'n'):
            if len(answer) == 0:
                return True
            else:
                # the == operator just returns a boolean,
                return answer[0].lower() == 'y'


def fetch():
    # from https://stackoverflow.com/questions/55961615/
    # how-to-integrate-wikidata-query-in-python
    url = 'https://query.wikidata.org/sparql'
    query = '''
    SELECT DISTINCT
    #(COUNT(?l) AS ?count)
    ?l ?form ?word
    WHERE {
      ?l a ontolex:LexicalEntry; dct:language wd:Q9027.
      VALUES ?excluded {
        # exclude affixes and interfix
        wd:Q62155 # affix
        wd:Q134830 # prefix
        wd:Q102047 # suffix
        wd:Q1153504 # interfix
      }
      MINUS {?l wdt:P31 ?excluded.}

      # We want only lexemes with both forms and at least one sense
      ?l ontolex:lexicalForm ?form.
      ?l ontolex:sense ?sense.
      # Exclude lexemes without a linked QID from at least one sense
      ?sense wdt:P5137 [].
      # This remove all lexemes with at least one example which is not
      # optimal
      MINUS {?l wdt:P5831 ?example.}
      ?form wikibase:grammaticalFeature [].
      # We extract the word of the form
      ?form ontolex:representation ?word.
      SERVICE wikibase:label
      { bd:serviceParam wikibase:language "[AUTO_LANGUAGE],en". }
    }
    limit 10
    '''
    r = requests.get(url, params={'format': 'json', 'query': query})
    data = r.json()
    # pprint(data)
    results = data["results"]["bindings"]
    # pprint(results)
    if len(results) == 0:
        print(f"No {language} lexemes containing both a sense, forms with " +
              "grammatical features and missing a usage example was found")
        exit(0)
    else:
        return results


def extract_data(result):
    lid = result["l"]["value"].replace(
        "http://www.wikidata.org/entity/", ""
    )
    form = result["form"]["value"].replace(
        "http://www.wikidata.org/entity/", ""
    )
    word = result["word"]["value"]
    return dict(
        lid=lid,
        form=form,
        word=word
    )


def lookup_summary(word):
    # Look up a sentence from Riksdagen
    url = (f"http://data.riksdagen.se/dokumentlista/?sok={word}" +
           "&sort=rel" +
           "&sortorder=desc&rapport=&utformat=json&a=s#soktraff" +
           "&limit=2")
    r = requests.get(url)
    data = r.json()
    return data["dokumentlista"]["dokument"]


def add_usage_example(
        document_id=None,
        sentence=None,
        lid=None,
        form=None,
        word=None,
):
    # Use WikibaseIntegrator aka wbi to upload the changes
    link_to_form = wbi_core.Form(
        prop_nr="P5830",
        value=form,
        is_qualifier=True
    )
    reference = [
        wbi_core.ItemID(
            prop_nr="P248",  # Stated in Riksdagen open data portal
            value="Q21592569",
            is_reference=True
        ),
        wbi_core.ExternalID(
            prop_nr="P8433",  # Riksdagen Document ID
            value=document_id,
            is_reference=True
        ),
        wbi_core.Time(
            prop_nr="P813",  # Fetched today
            time=datetime.datetime.utcnow().replace(
                tzinfo=datetime.timezone.utc
            ).replace(
                hour=0,
                minute=0,
                second=0,
            ).strftime("+%Y-%m-%dT%H:%M:%SZ"),
            is_reference=True,
        )
    ]
    claim = wbi_core.MonolingualText(
        sentence,
        "P5831",
        language="sv",
        qualifiers=[link_to_form],
        references=[reference],
    )
    # print(claim)
    print(claim.get_json_representation())
    item = wbi_core.ItemEngine(data=[claim], item_id=lid)
    # print(item.get_json_representation())
    result = item.write(
        login_instance,
        edit_summary="Added usage example with [[Wikidata:rikslex]]"
    )
    print(result)


def find_and_clean_sentence(
        word=None,
        id=None,
        summary=None
):
    cleaned_summary = summary.replace(
        '<span class="traff-markering">', ""
    )
    cleaned_summary = cleaned_summary.replace('</span>', "")
    elipsis = "…"
    # replace "t.ex." temporarily to avoid regex problems
    cleaned_summary = cleaned_summary.replace("t.ex.", "xxx")
    # print(f"working on {cleaned_summary}")
    # from https://stackoverflow.com/questions/3549075/
    # regex-to-find-all-sentences-of-text
    sentences = re.findall(
        "[A-Z].*?[\.!?]", cleaned_summary, re.MULTILINE | re.DOTALL
    )
    # Choose first sentence that has the word
    for sentence in sentences:
        if word in sentence:
            # restore the t.ex.
            sentence = sentence.replace("xxx", "t.ex.")
            # Last cleaning
            sentence = (sentence
                        .replace("\n", "")
                        .replace("-", "")
                        .replace(elipsis, ""))
            print(id)
            # print(sentence)
            return sentence


def parse_lexeme_data(results):
    for result in results:
        data = extract_data(result)
        lid = data["lid"]
        form = data["form"]
        word = data["word"]
        print(f"Working on the form: {word}")
        results = lookup_summary(word)
        for result in results:
            summary = result["summary"]
            riksdagen_document_id = result["id"]
            # match only the exact word
            if word in summary:
                sentence = find_and_clean_sentence(
                    word=word,
                    id=riksdagen_document_id,
                    summary=summary
                )
                if sentence:
                    if yes_no_question(
                            "Do you want to add this sentence: \n" +
                            f"{sentence}\nto the lexeme form {word}."
                    ):
                        add_usage_example(
                            document_id=riksdagen_document_id,
                            sentence=sentence,
                            lid=lid,
                            form=form,
                            word=word,
                        )
#
# main
#


results = fetch()
parse_lexeme_data(results)
