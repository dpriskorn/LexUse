#!/usr/bin/env python3
import datetime
import requests
# from pprint import pprint
import re
import LexData
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
#  present for sentence approval
#    if approved
#      if number of sense=1
#        present sense for approval
#      else
#        present senses and ask user to choose 1
#      add "demonstrates form"
#      add "demonstrates sense"
#      add a reference
#      upload to WD

# Settings
language = "swedish"
wd_prefix = "http://www.wikidata.org/entity/"
debug = True
# Logging for LexData
# logging.basicConfig(level=logging.INFO)

#
# Instantiation
#
# Authenticate with WikibaseIntegrator
global login_instance
login_instance = wbi_login.Login(user=config.username, pwd=config.password)
# LexData authentication
login = LexData.WikidataSession(config.username, config.password)


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
    limit 30
    offset 20
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
        wd_prefix, ""
    )
    form_id = result["form"]["value"].replace(
        wd_prefix, ""
    )
    word = result["word"]["value"]
    return dict(
        lid=lid,
        form_id=form_id,
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
    # check if dokument is in the list
    key_list = list(data["dokumentlista"].keys())
    if "dokument" in key_list:
        return data["dokumentlista"]["dokument"]


def add_usage_example(
        document_id=None,
        sentence=None,
        lid=None,
        form_id=None,
        sense_id=None,
        word=None,
):
    # Use WikibaseIntegrator aka wbi to upload the changes
    link_to_form = wbi_core.Form(
        prop_nr="P5830",
        value=form_id,
        is_qualifier=True
    )
    link_to_sense = wbi_core.Sense(
        prop_nr="P6072",
        value=sense_id,
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
        qualifiers=[link_to_form, link_to_sense],
        references=[reference],
    )
    # print(claim)
    if debug:
        print(claim.get_json_representation())
    item = wbi_core.ItemEngine(data=[claim], item_id=lid)
    if debug:
        print(item.get_json_representation())
    result = item.write(
        login_instance,
        edit_summary="Added usage example with [[Wikidata:rikslex]]"
    )
    return result


def find_and_clean_sentence(
        word=None,
        summary=None
):
    # TODO check for duplicates or near duplicates and remove
    # TODO sort by length and present only the first
    cleaned_summary = summary.replace(
        '<span class="traff-markering">', ""
    )
    cleaned_summary = cleaned_summary.replace('</span>', "")
    elipsis = "…"
    # replace "t.ex." temporarily to avoid regex problems
    cleaned_summary = cleaned_summary.replace("t.ex.", "xxx")
    cleaned_summary = cleaned_summary.replace("m.m.", "yyy")
    # print(f"working on {cleaned_summary}")
    # from https://stackoverflow.com/questions/3549075/
    # regex-to-find-all-sentences-of-text
    sentences = re.findall(
        "[A-Z].*?[\.!?]", cleaned_summary, re.MULTILINE | re.DOTALL
    )
    # Choose first sentence that has the word
    for sentence in sentences:
        exclude_this_sentence = False
        excluded_words = ["Sammanfattning", "betänkande"]
        for excluded_word in excluded_words:
            result = sentence.find(excluded_word)
            if result != -1:
                if debug:
                    sentence = (sentence
                                .replace("\n", "")
                                .replace("-", "")
                                .replace(elipsis, ""))
                    print(f"Found excluded word {excluded_word} " +
                          f"in {sentence}. Skipping")
                exclude_this_sentence = True
                # Exclude by breaking out of the iteration
                break
        if word in sentence and exclude_this_sentence is False:
            # restore the t.ex.
            sentence = sentence.replace("xxx", "t.ex.")
            sentence = sentence.replace("yyy", "m.m.")
            # Last cleaning
            sentence = (sentence
                        .replace("\n", "")
                        .replace("-", "")
                        .replace(elipsis, ""))
            return sentence


def fetch_senses(lid):
    """Returns list of senses"""
    return LexData.Lexeme(login, lid).senses


def prompt_choose_sense(senses):
    # from https://stackoverflow.com/questions/23294658/
    # asking-the-user-for-input-until-they-give-a-valid-response
    while True:
        try:
            options = ("Please choose the correct sense corresponding " +
                       "to the meaning in the usage example")
            number = 1
            for sense in senses:
                options += f"\n{number}) {sense.glosse(lang='sv')}"
                number += 1
            options += "\nPlease input a number or 0 to cancel: "
            choice = int(input(options))
        except ValueError:
            print("Sorry, I didn't understand that.")
            # better try again... Return to the start of the loop
            continue
        else:
            # choice was successfully parsed!
            # we're ready to exit the loop.
            break
        if choice > 0 and choice < len(choice):
            # arrays are 0-based so minus 1
            return senses[choice - 1]
        else:
            print("Cancelled adding this sentence.")
            return False


def add_to_watchlist(lid):
    # Get session from WBI
    session = login_instance.get_session()
    # adapted from https://www.mediawiki.org/wiki/API:Watch
    url = "https://www.wikidata.org/w/api.php"
    params_token = {
        "action": "query",
        "meta": "tokens",
        "type": "watch",
        "format": "json"
    }

    result = session.get(url=url, params=params_token)
    data = result.json()

    csrf_token = data["query"]["tokens"]["watchtoken"]

    params_watch = {
        "action": "watch",
        "titles": "Lexeme:" + lid,
        "format": "json",
        "formatversion": "2",
        "token": csrf_token,
    }

    result = session.post(
        url, data=params_watch
    )
    if debug:
        print(result.text)
    print(f"Added {lid} to your watchlist")


def add_sentence(sentence=None, data=None):
    word = data["word"]
    sense_id = None
    sense_gloss = None
    # fetch senses of the current lexeme
    lid = data["lid"]
    senses = fetch_senses(lid)
    number_of_senses = len(senses)
    print(f"number_of_senses: {number_of_senses}")
    if number_of_senses == 1:
        gloss = senses[0].glosse(lang="sv")
        if debug:
            print(senses[0].id)
        if yes_no_question("The lexeme has only 1 sense. " +
                        f"Does this example fit the gloss: {gloss}"):
            sense_id = senses[0].id
            sense_gloss = gloss
        else:
            print("Cancelled adding sentence as it does not match the " +
                  "only sense currently present. Use MachtSinn to add " +
                  "more senses to lexemes by matching on QID concepts " +
                  "with similar labels and descriptions in the lexeme " +
                  "language.")
    else:
        print(f"Found {number_of_senses} senses.")
        sense = False
        # TODO check that all senses has a swedish gloss
        sense = prompt_choose_sense(senses)
        if sense:
            sense_id = sense.id
            sense_gloss = sense.glosse(lang="sv")

    if (sense_id is not None and sense_gloss is not None):
        result = False
        result = add_usage_example(
            document_id=data["riksdagen_document_id"],
            sentence=sentence,
            lid=lid,
            form_id=data["form_id"],
            sense_id=sense_id,
            word=word,
        )
        if result:
            print("Successfully added usage example " +
                  f"to {wd_prefix + lid}")
            add_to_watchlist(lid)
    elif (sense_gloss is None):
        print("Swedish gloss is missing for the sense" +
              f" {sense_id}, " +
              "please fix it manually here: " +
              f"{wd_prefix + sense_id}")
    else:
        print("This should not be reached.")
        # pass


def parse_lexeme_data(results):
    if debug:
        print("found these words:")
        for result in results:
            data = extract_data(result)
            word = data["word"]
            print(word)
    for result in results:
        data = extract_data(result)
        form_id = data["form_id"]
        word = data["word"]
        print(f"Trying to find examples for the form: {word} with id: {form_id}")
        results = lookup_summary(word)
        # TODO rework this to first find all the sentences and then sort them
        # according to length and pick the shortest first
        #
        # TODO look for more examples from riksdagen if none in the first set of
        # results fit our purpose
        if results is not None:
            for result in results:
                summary = result["summary"]
                data["riksdagen_document_id"] = result["id"]
                # match only the exact word
                if word in summary:
                    sentence = find_and_clean_sentence(
                        word=word,
                        summary=summary
                    )
                    if sentence:
                        if yes_no_question(
                                "Do you want to add this sentence: \n" +
                                f"{sentence}\nto the lexeme form {word}."
                        ):
                            add_sentence(
                                sentence=sentence,
                                data=data
                            )
                            # Break out of the loop because one example was
                            # already choosen for this form
                            break


def introduction():
    if yes_no_question("This script enables you to " +
                       "semi-automatically add usage examples to " +
                       "lexemes. \nPlease pay attention to the lexical " +
                       "category of the lexeme. \nAlso try " +
                       "adding only short and concise " +
                       "examples to avoid bloat and maximise " +
                       "usefullness. \nThis script adds edited " +
                       "lexemes (indefinitely) to your watchlist. " +
                       "Continue?"):
        return True
    else:
        return False


#
# main
#

begin = introduction()
if begin:
    results = fetch()
    parse_lexeme_data(results)
