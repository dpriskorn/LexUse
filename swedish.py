#!/usr/bin/env python3
import datetime
import random
import requests
# from pprint import pprint
import re

# Needed for matching similar strings
import jellyfish
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
results_size = 50
language = "swedish"
wd_prefix = "http://www.wikidata.org/entity/"
debug = True
debug_duplicates = True
debug_excludes = True
debug_json = True
# Logging for LexData
# logging.basicConfig(level=logging.INFO)

# Global variable
# FIXME only log in once, pass the session from WBI to LexData
global login
login = None


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
    query = ('''
    SELECT DISTINCT
    #(COUNT(?l) AS ?count)
    ?l ?form ?word ?catLabel
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
      ?l wikibase:lexicalCategory ?cat.

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
    }''' +
             f'''limit {results_size}
             offset 50
             ''')
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
    word_spaces = " " + word + " "
    category = result["catLabel"]["value"]
    return dict(
        lid=lid,
        form_id=form_id,
        word=word,
        word_spaces=word_spaces,
        category=category
    )


def fetch_from_riksdagen(word):
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
        documents = data["dokumentlista"]["dokument"]
        if debug:
            print(f"Got {len(documents)} documents from the Riksdagen API")
        return documents


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
    if debug_json:
        print(claim.get_json_representation())
    item = wbi_core.ItemEngine(data=[claim], item_id=lid)
    if debug_json:
        print(item.get_json_representation())
    result = item.write(
        login_instance,
        edit_summary="Added usage example with [[Wikidata:LexUse]]"
    )
    return result


def parse_summary(
        word_spaces=None,
        summary=None
):
    """This tries to find and clean sentences and return the shortest one"""
    # TODO check for duplicates or near duplicates and remove
    cleaned_summary = summary.replace(
        '<span class="traff-markering">', ""
    )
    cleaned_summary = cleaned_summary.replace('</span>', "")
    elipsis = "…"
    # replace "t.ex." temporarily to avoid regex problems
    cleaned_summary = cleaned_summary.replace("t.ex.", "xxx")
    # Leave the last dot of m.m. to retain the full stop it probably
    # means
    cleaned_summary = cleaned_summary.replace("m.m", "yyy")
    cleaned_summary = cleaned_summary.replace("dvs.", "qqq")
    cleaned_summary = cleaned_summary.replace("bl.a.", "zzz")
    # print(f"working on {cleaned_summary}")
    # from https://stackoverflow.com/questions/3549075/
    # regex-to-find-all-sentences-of-text
    sentences = re.findall(
        "[A-Z].*?[\.!?]", cleaned_summary, re.MULTILINE | re.DOTALL
    )
    # Remove duplicates
    # add to a dictionary
    sentence_dict = dict.fromkeys(sentences, 1)
    for sentence in sentences:
        index = sentence.index(sentence)
        # remove the longest of the two
        # find similarity against all sentences in the list
        for other_sentence in sentences:
            # avoid matching to itself
            other_index = sentences.index(other_sentence)
            if index != other_index:
                ratio = jellyfish.levenshtein_distance(sentence, other_sentence)
                if debug_duplicates:
                    print(f"\nratio between \n{sentence} and \n{other_sentence} \nis: {ratio}")
                if ratio < 20:
                    if debug_duplicates:
                        print("ajabaja removing {other_sentence}")
                    # remove other_index from dictionary or spew an error
                    sentence_dict.pop(other_sentence)
    sentences_without_duplicates = sentence_dict.keys()
    if debug_duplicates:
        print(f"Sentences after duplicate removal {sentences_without_duplicates}")
    # TODO choose the shortest instead
    sorted_sentences = sorted(sentences, key=len)
    for sentence in sorted_sentences:
        exclude_this_sentence = False
        excluded_words = [
            "SAMMANFATTNING",
            "BETÄNKANDE",
            "UTSKOTT",
            "MOTION",
            " EG ",
            " EU ",
            "RIKSDAGEN",
        ]
        # count_excluded_sentences = 0
        for excluded_word in excluded_words:
            result = sentence.upper().find(excluded_word)
            if result != -1:
                if debug_excludes:
                    sentence = (sentence
                                .replace("\n", "")
                                .replace("-", "")
                                .replace(elipsis, ""))
                    print(f"Found excluded word {excluded_word} " +
                          f"in {sentence}. Skipping")
                exclude_this_sentence = True
                # count_excluded_sentences += 1
                # Exclude by breaking out of the iteration
                break
        # Add space to match better
        if word_spaces in sentence and exclude_this_sentence is False:
            # restore the t.ex.
            sentence = sentence.replace("xxx", "t.ex.")
            sentence = sentence.replace("yyy", "m.m")
            sentence = sentence.replace("qqq", "dvs.")
            sentence = sentence.replace("zzz", "bl.a.")
            # Last cleaning
            sentence = (sentence
                        .replace("\n", "")
                        # This removes "- " because the data is hyphenated
                        # sometimes
                        .replace("- ", "")
                        .replace(elipsis, "")
                        .replace("  ", " "))
            return sentence


def fetch_senses(lid):
    """Returns list of senses"""
    senses = LexData.Lexeme(login, lid).senses
    # Remove senses without P5137
    list = []
    for sense in senses:
        if "P5137" in sense.claims.keys():
            if debug:
                print(f"Appending {sense.id}")
            list.append(sense)
    return list


def prompt_choose_sense(senses):
    # from https://stackoverflow.com/questions/23294658/
    # asking-the-user-for-input-until-they-give-a-valid-response
    # We exit the loop by returning
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
            print(f"len: {len(senses)}")
            if choice > 0 and choice < len(senses):
                # arrays are 0-based so minus 1
                sense = senses[choice - 1]
                if debug_json:
                    print(f"returning: {sense}")
                return sense
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
    if debug_json:
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
    aborted = False
    if debug:
        print(f"number_of_senses: {number_of_senses}")
    if number_of_senses == 1:
        gloss = senses[0].glosse(lang="sv")
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
        if sense is not False:
            if debug:
                print("debug: setting sense")
            sense_id = sense.id
            sense_gloss = sense.glosse(lang="sv")
        else:
            aborted = True
    if not aborted:
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
        elif (sense_id is not None and sense_gloss is None):
            print("Swedish gloss is missing for the sense" +
                  f" {sense_id}, " +
                  "please fix it manually here: " +
                  f"{wd_prefix + lid}")
        else:
            print("Sense_id is None. This should not be reached.")
            # pass


def loop_through_records(records, data):
    # TODO rework this to first find all the sentences and then sort them
    # according to length and pick the shortest first
    #
    # TODO look for more examples from riksdagen if none in the first set of
    # results fit our purpose
    word_spaces = data["word_spaces"]
    word = data["word"]
    count = 1
    for record in records:
        if debug:
            print(f"Working of record number {count}")
        summary = record["summary"]
        # This is needed by add_sentence()
        data["riksdagen_document_id"] = record["id"]
        # match only the exact word
        if word in summary:
            sentence = parse_summary(
                word_spaces=word_spaces,
                summary=summary
            )
            if sentence:
                if yes_no_question(
                        "Do you want to add this sentence: \n" +
                        f"{sentence}"
                ):
                    add_sentence(
                        sentence=sentence,
                        data=data
                    )
                    # Break out of the loop because one example was
                    # already choosen for this form
                    count += 1
                    break
            else:
                if debug:
                    print("No sentence found.")
                count += 1
                break
        else:
            if debug:
                print(f"Word {data['word']} " +
                      f"not found in: \n{summary}")
        count += 1


def search_for_sentences(result):
    data = extract_data(result)
    form_id = data["form_id"]
    word = data["word"]
    print(f"\nTrying to find examples for the {data['category']} lexeme " +
          f"form: {word} with id: {form_id}")
    # Riksdagen API
    records = fetch_from_riksdagen(word)
    if records is not None:
        if debug:
            print("Looping through records from Riksdagen")
        loop_through_records(records, data)


def parse_lexeme_data(results):
    """Go through the SPARQL results randomly"""
    if debug:
        print("found these words:")
        for result in results:
            data = extract_data(result)
            word = data["word"]
            print(word)
    # Go through the results at random
    # from http://stackoverflow.com/questions/306400/ddg#306417
    already_done = []
    while (True):
        if len(already_done) == results_size:
            # We have gone checked all results now
            # TODO offer to fetch more
            print("No more results. Run the script again to continue")
            exit(0)
        else:
            result = random.choice(results)
            search_for_sentences(result)


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
    #
    # Instantiation
    #
    # Authenticate with WikibaseIntegrator
    print("Logging in with WikibaseIntegrator")
    login_instance = wbi_login.Login(user=config.username, pwd=config.password)
    print("Logging in with LexData")
    login = LexData.WikidataSession(config.username, config.password)
    print("Fetching lexeme forms to work on")
    results = fetch()
    parse_lexeme_data(results)
