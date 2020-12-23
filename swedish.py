#!/usr/bin/env python3
import argparse
from datetime import datetime, timezone
import random
# from pprint import pprint
import re
import time
# import asyncio
import logging

import httpx
from wikibaseintegrator import wbi_core, wbi_login

# Create a file named config.py yourself with the following content:
# username = "username"
# password= "password"
#
# Please create a bot password for running the script for
# safety reasons here: https://www.wikidata.org/wiki/Special:BotPasswords
import config

# This script enables finding example sentences via the Riksdagen API where
# everything is out of copyright

# Pseudo code
# fetch a list of swedish lexeme forms and words
# loop through the list
#  search for the word in riksdagen api
#  extract sentence
#  clean sentence
#  present sentence for approval
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
sparql_results_size = 500
riksdagen_max_results_size = 160  # keep to multiples of 20
language = "swedish"
language_code = "sv"
wd_prefix = "http://www.wikidata.org/entity/"
min_word_count = 5
max_word_count = 15
debug = False
debug_duplicates = False
debug_excludes = False
debug_json = False
debug_riksdagen = False
debug_senses = True
debug_sentences = False
debug_summaries = False

#
# Functions
#


def yes_no_skip_question(message: str):
    # https://www.quora.com/
    # I%E2%80%99m-new-to-Python-how-can-I-write-a-yes-no-question
    # this will loop forever
    while True:
        answer = input(message + ' [(Y)es/(n)o/(s)kip this form]: ')
        if len(answer) == 0 or answer[0].lower() in ('y', 'n', 's'):
            if len(answer) == 0:
                return True
            elif answer[0].lower() == 's':
                return None
            else:
                # the == operator just returns a boolean,
                return answer[0].lower() == 'y'


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


def sparql_query(query):
    # from https://stackoverflow.com/questions/55961615/
    # how-to-integrate-wikidata-query-in-python
    url = 'https://query.wikidata.org/sparql'
    r = httpx.get(url, params={'format': 'json', 'query': query})
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


def count_number_of_senses_with_P5137(lid):
    """Returns an int"""
    result = (sparql_query(f'''
    SELECT
    (COUNT(?sense) as ?count)
    WHERE {{
      VALUES ?l {{wd:{lid}}}.
      ?l ontolex:sense ?sense.
      ?sense skos:definition ?gloss.
      # Exclude lexemes without a linked QID from at least one sense
      ?sense wdt:P5137 [].
    }}'''))
    count = int(result[0]["count"]["value"])
    logging.debug(f"count:{count}")
    return count


def fetch_senses(lid):
    """Returns dictionary with numbers as keys and a dictionary as value with
    sense id and gloss"""
    # Thanks to Lucas Werkmeister https://www.wikidata.org/wiki/Q57387675 for
    # helping with this query.
    result = (sparql_query(f'''
    SELECT
    ?sense ?gloss
    WHERE {{
      VALUES ?l {{wd:{lid}}}.
      ?l ontolex:sense ?sense.
      ?sense skos:definition ?gloss.
      # Get only the swedish gloss, exclude otherwise
      FILTER(LANG(?gloss) = "{language_code}")
      # Exclude lexemes without a linked QID from at least one sense
      ?sense wdt:P5137 [].
    }}'''))
    senses = {}
    number = 1
    for row in result:
        senses[number] = {
            "sense_id": row["sense"]["value"].replace(wd_prefix, ""),
            "gloss": row["gloss"]["value"]
        }
        number += 1
    logging.debug(f"senses:{senses}")
    return senses


def fetch_lexeme_forms():
    return sparql_query(f'''
    SELECT DISTINCT
    ?l ?form ?word ?catLabel
    WHERE {{
      ?l a ontolex:LexicalEntry; dct:language wd:Q9027.
      VALUES ?excluded {{
        # exclude affixes and interfix
        wd:Q62155 # affix
        wd:Q134830 # prefix
        wd:Q102047 # suffix
        wd:Q1153504 # interfix
      }}
      MINUS {{?l wdt:P31 ?excluded.}}
      ?l wikibase:lexicalCategory ?cat.

      # We want only lexemes with both forms and at least one sense
      ?l ontolex:lexicalForm ?form.
      ?l ontolex:sense ?sense.

      # Exclude lexemes without a linked QID from at least one sense
      ?sense wdt:P5137 [].

      # This remove all lexemes with at least one example which is not
      # ideal
      MINUS {{?l wdt:P5831 ?example.}}
      ?form wikibase:grammaticalFeature [].
      # We extract the word of the form
      ?form ontolex:representation ?word.
      SERVICE wikibase:label
      {{ bd:serviceParam wikibase:language "[AUTO_LANGUAGE],en". }}
    }}
    limit {sparql_results_size}
    ''')


def extract_data(result):
    lid = result["l"]["value"].replace(
        wd_prefix, ""
    )
    form_id = result["form"]["value"].replace(
        wd_prefix, ""
    )
    word = result["word"]["value"]
    word_spaces = " " + word + " "
    word_angle_parens = ">" + word + "<"
    category = result["catLabel"]["value"]
    return dict(
        lid=lid,
        form_id=form_id,
        word=word,
        word_spaces=word_spaces,
        word_angle_parens=word_angle_parens,
        category=category
    )


# async def async_fetch_from_url(url):
#     async with httpx.AsyncClient() as client:
#         response = await client.get(url)
#         return response


def get_riksdagen_result_count(word):
    # First find out the number of results
    url = (f"http://data.riksdagen.se/dokumentlista/?sok={word}" +
           "&sort=rel&sortorder=desc&utformat=json&a=s&p=1")
    r = httpx.get(url)
    data = r.json()
    results = int(data["dokumentlista"]["@traffar"])
    logging.info(f"results:{results}")
    return results


# def async_fetch_from_riksdagen(word):
#     # Get total results count
#     results = get_riksdagen_result_count(word)
#     # Generate the urls
#     if results > riksdagen_max_results_size:
#         results = riksdagen_max_results_size
#     # generate urls
#     urls = []
#     # divide by 20 to know how many requests to send
#     for i in range(1, int(results / 20)):
#         urls.append(f"http://data.riksdagen.se/dokumentlista/?sok={word}" +
#                     f"&sort=rel&sortorder=desc&utformat=json&a=s&p={i}")
#     logging.debug(f"urls:{urls}")
#     # get urls asynchroniously
#     tasks = [(session, url, progress_queue) for url in urls]
#     return await asyncio.gather(*tasks)
#     results = asyncio.run(async_fetch_from_riksdagen("test"))


def fetch_from_riksdagen(word):
    # Look up records from the Riksdagen API
    records = []
    print("Downloading from the Riksdagen API...")
    for i in range(1, int(riksdagen_max_results_size / 20) + 1):
        if i > 1:
            # break if i is more than 1 and the results are less than 20
            # because that means that there are no more results in page 2-5
            if len(records) < 20:
                break
        url = (f"http://data.riksdagen.se/dokumentlista/?sok={word}" +
               "&sort=rel" +
               "&sortorder=desc&utformat=json&a=s" +
               f"&p={i}")
        if debug_riksdagen:
            print(url)
        r = httpx.get(url)
        data = r.json()
        # check if dokument is in the list
        key_list = list(data["dokumentlista"].keys())
        if "dokument" in key_list:
            for item in data["dokumentlista"]["dokument"]:
                records.append(item)
        else:
            # We break if the API does not return any more results
            if debug_riksdagen:
                print("API did not return any (more) results")
            break
    if debug:
        print(f"Got {len(records)} records from the Riksdagen API")
    if debug_json:
        print(records)
    return records


def add_usage_example(
        document_id=None,
        sentence=None,
        lid=None,
        form_id=None,
        sense_id=None,
        word=None,
        publication_date=None,
):
    # Use WikibaseIntegrator aka wbi to upload the changes in one edit
    if publication_date is not None:
        publication_date = datetime.fromisoformat(publication_date)
    else:
        print("Publication date of document {document_id} " +
              "is missing. We have no fallback for that. " +
              "Abort adding usage example.")
        return False
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
            time=datetime.utcnow().replace(
                tzinfo=timezone.utc
            ).replace(
                hour=0,
                minute=0,
                second=0,
            ).strftime("+%Y-%m-%dT%H:%M:%SZ"),
            is_reference=True,
        ),
        wbi_core.Time(
            prop_nr="P577",  # Publication date
            time=publication_date.strftime("+%Y-%m-%dT00:00:00Z"),
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
    if debug_json:
        print(f"Result from WBI: {result}")
    return result


def count_words(string):
    # from https://www.pythonpool.com/python-count-words-in-string/
    return(len(string.strip().split(" ")))


def find_usage_examples_from_summary(
        word_spaces=None,
        summary=None
):
    """This tries to find and clean sentences and return the shortest one"""
    # TODO check for duplicates or near duplicates and remove
    cleaned_summary = summary.replace(
        '<span class="traff-markering">', ""
    )
    cleaned_summary = cleaned_summary.replace('</span>', "")
    ellipsis = "…"
    # replace "t.ex." temporarily to avoid regex problems
    cleaned_summary = cleaned_summary.replace("t.ex.", "xxx")
    # Leave the last dot of m.m. to retain the full stop it probably
    # means
    cleaned_summary = cleaned_summary.replace("m.m", "yyy")
    cleaned_summary = cleaned_summary.replace("dvs.", "qqq")
    cleaned_summary = cleaned_summary.replace("bl.", "zzz")
    # TODO add "ang." "kl." "s.k." "resp."

    # from https://stackoverflow.com/questions/3549075/
    # regex-to-find-all-sentences-of-text
    sentences = re.findall(
        "[A-Z].*?[\.!?]", cleaned_summary, re.MULTILINE | re.DOTALL
    )
    # Remove duplicates naively using sets
    sentences_without_duplicates = list(set(sentences))
    if debug_duplicates:
        print("Sentences after duplicate removal " +
              f"{sentences_without_duplicates}")
    suitable_sentences = []
    for sentence in sentences_without_duplicates:
        exclude_this_sentence = False
        # Exclude based on lenght of the sentence
        word_count = count_words(sentence)
        if word_count > max_word_count or word_count < min_word_count:
            exclude_this_sentence = True
            # Exclude by breaking out of the iteration early
            break
        else:
            # Exclude based on weird words
            excluded_words = [
                "SAMMANFATTNING",
                "BETÄNKANDE",
                "UTSKOTT",
                "MOTION",
                " EG ",
                " EU ",
                "RIKSDAGEN",
            ]
            for excluded_word in excluded_words:
                result = sentence.upper().find(excluded_word)
                if result != -1:
                    if debug_excludes:
                        sentence = (sentence
                                    .replace("\n", "")
                                    .replace("-", "")
                                    .replace(ellipsis, ""))
                        print(f"Found excluded word {excluded_word} " +
                              f"in {sentence}. Skipping")
                    exclude_this_sentence = True
                    break
        # Add space to match better
        if word_spaces in sentence and exclude_this_sentence is False:
            # restore the t.ex.
            sentence = sentence.replace("xxx", "t.ex.")
            sentence = sentence.replace("yyy", "m.m")
            sentence = sentence.replace("qqq", "dvs.")
            sentence = sentence.replace("zzz", "bl.")
            # Last cleaning
            sentence = (sentence
                        .replace("\n", "")
                        # This removes "- " because the data is hyphenated
                        # sometimes
                        .replace("- ", "")
                        .replace(ellipsis, "")
                        .replace("  ", " "))
            suitable_sentences.append(sentence)
    return suitable_sentences


def prompt_choose_sense(senses):
    """Returns a dictionary with sense_id -> sense_id
    and gloss -> gloss or False"""
    # from https://stackoverflow.com/questions/23294658/
    # asking-the-user-for-input-until-they-give-a-valid-response
    while True:
        try:
            options = ("Please choose the correct sense corresponding " +
                       "to the meaning in the usage example")
            number = 1
            # Put each key -> value into a new nested dictionary
            for sense in senses:
                options += f"\n{number}) {senses[number]['gloss']}"
                number += 1
            options += "\nPlease input a number or 0 to cancel: "
            choice = int(input(options))
        except ValueError:
            print("Sorry, I didn't understand that.")
            # better try again... Return to the start of the loop
            continue
        else:
            logging.debug(f"length_of_senses:{len(senses)}")
            if choice > 0 and choice <= len(senses):
                return {
                    "sense_id": senses[choice]["sense_id"],
                    "gloss": senses[choice]["gloss"]
                }
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


def prompt_sense_approval(sentence=None, data=None):
    """Prompts for validating that we have a sense matching the use example
    return dictionary with sense_id and sense_gloss if approved else False"""
    sense_id = None
    sense_gloss = None
    # fetch senses of the current lexeme
    lid = data["lid"]
    # This returns a tuple if one sense or a dictionary if multiple senses
    senses = fetch_senses(lid)
    number_of_senses = len(senses)
    logging.debug(f"number_of_senses:{number_of_senses}")
    if number_of_senses > 0:
        aborted = False
        if number_of_senses == 1:
            gloss = senses[1]["gloss"]
            if yes_no_question("Found only one sense. " +
                               "Does this example fit the following " +
                               f"gloss? \n'{gloss}'"):
                return {
                    "sense_id": senses[1]["sense_id"],
                    "sense_gloss": gloss
                }
            else:
                word = data['word']
                print("Cancelled adding sentence as it does not match the " +
                      "only sense currently present. \nLexemes are " +
                      "entirely dependent on good quality QIDs. \n" +
                      "Please add labels " +
                      "and descriptions to relevant QIDs and then use " +
                      "MachtSinn to add " +
                      "more senses to lexemes by matching on QID concepts " +
                      "with similar labels and descriptions in the lexeme " +
                      "language." +
                      f"\nSearch for {word} in Wikidata: " +
                      "https://www.wikidata.org/w/index.php?" +
                      f"search={word}&title=Special%3ASearch&" +
                      "profile=advanced&fulltext=0&" +
                      "advancedSearch-current=%7B%7D&ns0=1")
                time.sleep(5)
                return False
        else:
            print(f"Found {number_of_senses} senses.")
            sense = False
            # TODO check that all senses has a gloss matching the language of
            # the example
            sense = prompt_choose_sense(senses)
            if sense is not False:
                logging.debug("setting sense")
                return {
                    "sense_id": sense["sense_id"],
                    "sense_gloss": sense["gloss"]
                }
            else:
                aborted = True
        if not aborted:
            if (sense_id is not None and sense_gloss is None):
                print("Swedish gloss is missing for the sense" +
                      f" {sense_id}, " +
                      "please fix it manually here: " +
                      f"{wd_prefix + lid}")
                time.sleep(5)
                return False
            else:
                print("Sense_id is None. This should not be reached.")
        else:
            # Aborted
            return False
    else:
        # Check if any suitable senses exist
        count = (count_number_of_senses_with_P5137("L35455"))
        if count > 0:
            print("Swedish gloss is missing for {count} sense(s)" +
                  ". Please fix it manually here: " +
                  f"{wd_prefix + lid}")
            time.sleep(5)
            return False
        else:
            logging.debug("no senses this should never be reached " +
                          "if the sparql result was sane")
            return False


def extract_summaries_from_records(records, data):
    # TODO rework this to first find all the sentences and then sort them
    # according to length and pick the shortest first
    #
    # TODO look for more examples from riksdagen if none in the first set of
    # results fit our purpose
    word_spaces = data["word_spaces"]
    word_angle_parens = data["word_angle_parens"]
    word = data["word"]
    count_inexact_hits = 1
    count_exact_hits = 1
    count_summary = 1
    summaries = {}
    for record in records:
        if debug_summaries:
            print(f"Working of record number {count_summary}")
        summary = record["summary"]
        # This is needed by present_sentence() and add_usage_example()
        # downstream
        document_id = record["id"]
        date = record["publicerad"]
        if debug_summaries:
            print(
                f"Found in https://data.riksdagen.se/dokument/{document_id}"
            )
        record_data = {}
        record_data["document_id"] = document_id
        record_data["date"] = date
        # match only the exact word
        added = False
        if word in summary:
            count_inexact_hits += 1
            if word_spaces in summary or word_angle_parens in summary:
                count_exact_hits += 1
                # add to dictionary
                if debug_summaries:
                    print(f"adding {summary} and {data} to summaries")
                summaries[summary] = record_data
                added = True
            else:
                if debug_summaries:
                    print("No exact hit in summary. Skipping.")
        else:
            if debug_summaries and added is False:
                print(f"'{word}' not found as part of a word or a " +
                      "word in the summary. Skipping")
        count_summary += 1
    if debug_summaries:
        logging.debug(f"summaries:{summaries}")
    print(f"Processed {count_summary} records and found " +
          f"{count_exact_hits} exact hits for the form '{word}'")
    logging.info(f"among {count_inexact_hits} where the lexeme was present.")
    return summaries


def get_sentences_from_apis(result):
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
        summaries = extract_summaries_from_records(records, data)
        unsorted_sentences = {}
        # Iterate through the dictionary
        for summary in summaries:
            # Get result_data
            result_data = summaries[summary]
            document_id = result_data["document_id"]
            if debug_summaries:
                print(f"Got back summary {summary} with the " +
                      f"correct document_id: {document_id}?")
            suitable_sentences = find_usage_examples_from_summary(
                word_spaces=data["word_spaces"],
                summary=summary
            )
            if len(suitable_sentences) > 0:
                for sentence in suitable_sentences:
                    # Make sure the riksdagen_document_id follows
                    unsorted_sentences[sentence] = result_data
        if len(unsorted_sentences) > 0:
            logging.debug(f"unsorted_sentences: {unsorted_sentences}")
        print(f"Found {len(unsorted_sentences)} suitable sentences " +
              "from the Riksdagen API")
        return unsorted_sentences
    # TODO K-samsök
    # TODO Europarl corpus


def present_sentence(
        data,
        sentence,
        document_id,
        date
):
    """Return True, False or None (skip)"""
    word_count = count_words(sentence)
    result = yes_no_skip_question(
            f"Found the following sentence with {word_count} " +
            "words. Is it suitable as a usage example " +
            f"for the form '{data['word']}'? \n" +
            f"'{sentence}'"
    )
    if result:
        selected_sense = prompt_sense_approval(
            sentence=sentence,
            data=data
        )
        if selected_sense is not False:
            lid = data["lid"]
            sense_id = selected_sense["sense_id"]
            sense_gloss = selected_sense["sense_gloss"]
            if (sense_id is not None and sense_gloss is not None):
                result = False
                result = add_usage_example(
                    document_id=document_id,
                    sentence=sentence,
                    lid=lid,
                    form_id=data["form_id"],
                    sense_id=sense_id,
                    word=data["word"],
                    publication_date=date,
                )
                if result:
                    print("Successfully added usage example " +
                          f"to {wd_prefix + lid}")
                    add_to_watchlist(lid)
                    return True
                else:
                    return False
            else:
                return False
    elif result is None:
        # None means skip
        return None
    else:
        return False


def parse_lexeme_data(results):
    """Go through the SPARQL results randomly"""
    words = []
    for result in results:
        data = extract_data(result)
        words.append(data["word"])
    print(f"Got {len(words)} suitable forms from Wikidata")
    logging.debug(f"words:{words}")
    # Go through the results at random
    print("Going through the list of forms at random.")
    # from http://stackoverflow.com/questions/306400/ddg#306417
    earlier_choices = []
    while (True):
        if len(earlier_choices) == sparql_results_size:
            # We have gone checked all results now
            # TODO offer to fetch more
            print("No more results. Run the script again to continue")
            exit(0)
        else:
            result = random.choice(results)
            # data = extract_data(result)
            # Prevent running more than once for each result
            if result not in earlier_choices:
                earlier_choices.append(result)
                data = extract_data(result)
                # This dict holds the sentence as key and riksdagen_document_id
                # as value
                sentences_and_result_data = get_sentences_from_apis(result)
                # Sort so that the shortest sentence is first
                sorted_sentences = sorted(sentences_and_result_data, key=len)
                if sentences_and_result_data is not None:
                    example_was_added = False
                    count = 1
                    # Loop through sentence list
                    for sentence in sorted_sentences:
                        print("Presenting sentence " +
                              f"{count}/{len(sorted_sentences)}")
                        result_data = sentences_and_result_data[sentence]
                        document_id = result_data["document_id"]
                        date = result_data["date"]
                        if debug_sentences:
                            print("with document_id: " +
                                  f"{document_id} from {date}")
                        result = present_sentence(
                            data,
                            sentence,
                            document_id,
                            date
                        )
                        count += 1
                        # Break out of the for loop because one example was
                        # already choosen for this result or if the form was was
                        # skipped
                        if result or result is None:
                            break


def introduction():
    if yes_no_question("This script enables you to " +
                       "semi-automatically add usage examples to " +
                       "lexemes with both good senses and forms " +
                       "(with P5137 and grammatical features respectively). " +
                       "\nPlease pay attention to the lexical " +
                       "category of the lexeme. \nAlso try " +
                       "adding only short and concise " +
                       "examples to avoid bloat and maximise " +
                       "usefullness. \nThis script adds edited " +
                       "lexemes (indefinitely) to your watchlist. " +
                       "\nContinue?"):
        return True
    else:
        return False


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
    # logging.debug("test")
    # async_fetch_from_riksdagen("test")
    # exit(0)

    begin = introduction()
    if begin:
        #
        # Instantiation
        #
        # Authenticate with WikibaseIntegrator
        print("Logging in with Wikibase Integrator")
        global login_instance
        login_instance = wbi_login.Login(
            user=config.username, pwd=config.password
        )
        print("Fetching lexeme forms to work on")
        results = fetch_lexeme_forms()
        parse_lexeme_data(results)


if __name__ == "__main__":
    main()
