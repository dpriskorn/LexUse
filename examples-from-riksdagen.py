#!/usr/bin/env python3
import requests
from pprint import pprint
import re
import LexData

# This enables finding example sentences via the Riksdagen API where everything
# is CC0

# Pseudo code
# fetch a list of swedish lexeme forms and words
# loop through the list
#  search for the word in riksdagen api
#  extract sentence
#  present for approval
#    if approved
#      upload to LID and add "demonstrates form"

# Constants
riksdagen_url = "http://data.riksdagen.se/dokument/"

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
    wd:Q62155
    wd:Q134830
    wd:Q102047
  }
  MINUS {?l wdt:P31 ?excluded.}
  MINUS {?l wdt:P5831 ?example.}
  ?l ontolex:lexicalForm ?form.
  VALUES ?features {
    wd:Q110786
    wd:Q53997851
    wd:Q53997857
    wd:Q131105
    wd:Q146786
    wd:Q146233
  }
  ?form wikibase:grammaticalFeature ?features.
  ?form ontolex:representation ?word.
  SERVICE wikibase:label
  { bd:serviceParam wikibase:language "[AUTO_LANGUAGE],en". }
}
limit 1
'''
r = requests.get(url, params={'format': 'json', 'query': query})
data = r.json()
pprint(data)
results = data["results"]["bindings"]
pprint(results)
for result in results:
    lid = result["l"]["value"].replace("http://www.wikidata.org/entity/", "")
    form = result["form"]["value"].replace(
        "http://www.wikidata.org/entity/", ""
    )
    word = result["word"]["value"]
    print(word)
    # Look up a sentence from Riksdagen
    url = (f"http://data.riksdagen.se/dokumentlista/?sok={word}" +
           "&sort=rel" +
           "&sortorder=desc&rapport=&utformat=json&a=s#soktraff" +
           "&limit=2")
    r = requests.get(url)
    data = r.json()
    results = data["dokumentlista"]["dokument"]
    for result in results:
        summary = result["summary"]
        # match only the exact word
        if word in summary:
            cleaned_summary = summary.replace(
                '<span class="traff-markering">', ""
            )
            cleaned_summary = cleaned_summary.replace('</span>', "")
            elipsis = "…"
            # replace "t.ex." temporarily
            cleaned_summary = cleaned_summary.replace("t.ex.", "xxx")
            # print(f"working on {cleaned_summary}")
            sentences = re.findall(
                "[A-Z].*?[\.!?]", cleaned_summary, re.MULTILINE | re.DOTALL
            )

            # Choose first sentence that has the word
            for sentence in sentences:
                if word in sentence:
                    # Last cleaning
                    sentence = (sentence
                                .replace("\n", "")
                                .replace("-", "")
                                .replace(elipsis, ""))
                    print(result["id"])
                    print(sentence)
