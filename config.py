import os
import logging

# Add your credentials from the botpasswords page to your ~/.bashrc or below as
# strings:
logging.info(os.environ['LEXUSE_USERNAME'])
logging.info(os.environ['LEXUSE_PASSWORD'])
username = os.environ['LEXUSE_USERNAME']
password = os.environ['LEXUSE_PASSWORD']

# Settings
sparql_results_size = 1000
sparql_offset = 0
riksdagen_max_results_size = 260  # keep to multiples of 20
language = "swedish"
language_code = "sv"
language_qid = "Q9027"
min_word_count = 5
max_word_count = 15
debug = False
debug_duplicates = False
debug_excludes = True
debug_exclude_list = False
debug_json = False
debug_riksdagen = False
debug_senses = False
debug_sentences = True
debug_summaries = True

# Global variables
login_instance = None
