#!/usr/bin/env python3
import logging
import re
import httpx

import config
import util


def get_result_count(word):
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


def fetch(word):
    # Look up records from the Riksdagen API
    records = []
    print("Downloading from the Riksdagen API...")
    for i in range(1, int(config.riksdagen_max_results_size / 20) + 1):
        if i > 1:
            # break if i is more than 1 and the results are less than 20
            # because that means that there are no more results in page 2-5
            if len(records) < 20:
                break
        url = (f"http://data.riksdagen.se/dokumentlista/?sok={word}" +
               "&sort=rel" +
               "&sortorder=desc&utformat=json&a=s" +
               f"&p={i}")
        if config.debug_riksdagen:
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
            if config.debug_riksdagen:
                print("API did not return any (more) results")
            break
    if config.debug:
        logging.info(f"Got {len(records)} records from the Riksdagen API")
    if config.debug_json:
        print(records)
    return records


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
    # bl.a.
    cleaned_summary = cleaned_summary.replace("bl.", "zzz")
    # TODO add "ang." "kl." "s.k." "resp."

    # from https://stackoverflow.com/questions/3549075/
    # regex-to-find-all-sentences-of-text
    sentences = re.findall(
        "[A-Z].*?[\.!?]", cleaned_summary, re.MULTILINE | re.DOTALL
    )
    # Remove duplicates naively using sets
    sentences_without_duplicates = list(set(sentences))
    if config.debug_duplicates:
        print("Sentences after duplicate removal " +
              f"{sentences_without_duplicates}")
    suitable_sentences = []
    for sentence in sentences_without_duplicates:
        exclude_this_sentence = False
        # Exclude based on lenght of the sentence
        word_count = util.count_words(sentence)
        if (
                word_count > config.max_word_count or word_count <
                config.min_word_count
        ):
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
                    if config.debug_excludes:
                        sentence = (sentence
                                    .replace("\n", "")
                                    .replace("-", "")
                                    .replace(ellipsis, ""))
                        logging.debug(
                            f"Found excluded word {excluded_word} " +
                            f"in {sentence}. Skipping",
                        )
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
            if config.debug_sentences:
                logging.debug(f"suitable_sentence:{sentence}")
            suitable_sentences.append(sentence)
    return suitable_sentences


def extract_summaries_from_records(records, data):
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
        if config.debug_summaries:
            logging.info(f"Working of record number {count_summary}")
        summary = record["summary"]
        # This is needed by present_sentence() and add_usage_example()
        # downstream
        document_id = record["id"]
        date = record["publicerad"]
        if config.debug_summaries:
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
                if config.debug_summaries:
                    logging.debug(f"found word_spaces or word_angle_parens in {summary}")
                summaries[summary] = record_data
                added = True
            else:
                if config.debug_summaries:
                    logging.info("No exact hit in summary. Skipping.")
        else:
            if config.debug_summaries and added is False:
                print(f"'{word}' not found as part of a word or a " +
                      "word in the summary. Skipping")
        count_summary += 1
    # if config.debug_summaries:
    #     logging.debug(f"summaries:{summaries}")
    print(f"Processed {count_summary} records and found " +
          f"{count_exact_hits} exact hits for the form '{word}'")
    logging.info(f"among {count_inexact_hits} where the lexeme was present.")
    return summaries


def get_records(data):
    word = data["word"]
    records = fetch(word)
    if records is not None:
        if config.debug:
            print("Looping through records from Riksdagen")
        summaries = extract_summaries_from_records(records, data)
        unsorted_sentences = {}
        # Iterate through the dictionary
        for summary in summaries:
            # Get result_data
            result_data = summaries[summary]
            # document_id = result_data["document_id"]
            # if config.debug_summaries:
            #     print(f"Got back summary {summary} with the " +
            #           f"correct document_id: {document_id}?")
            suitable_sentences = find_usage_examples_from_summary(
                word_spaces=data["word_spaces"],
                summary=summary
            )
            if len(suitable_sentences) > 0:
                for sentence in suitable_sentences:
                    # Make sure the riksdagen_document_id follows
                    unsorted_sentences[sentence] = result_data
        return unsorted_sentences