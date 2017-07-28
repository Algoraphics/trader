#!python
#
#coinbase Key: H0y0wCNUlknzNW3V
#coinbase Secret: SKe4y8E0BOMAndCXqSnyxY1mmN2SMcO8
#
#reddit key 4qYMwrPBzKcVTA
#reddit secret uDJR1uaBQBVDtU6RWRmRl_CYOOM
import datetime
import json
import operator
import os
import praw
import sys
import urllib.request

class Thread:
	def __init__(self, title, word_count):
		self.title = title
		self.word_count = word_count

# Subreddits to parse
subreddits = ['nba', 'ethtrader']

# Options are hour, day, week, month, year, all
interval = 'day'

# Options are hot, new, top, old, random, controversial
sort = 'hot'

# Stop at specified number of threads. Thread parsing is a slow operation
thread_parse_limit = 30

# Multiply the value of words found in titles by some multiplier
title_multiplier = 1

# History distance, meaning how many files back to check for diffs
hist_dist = 2

# Print nice output
should_print = False

common_list = [u'a', u'and', u'as', u'an', u'are', u'at', u'be',
				u'but', u'by', u'do', u'for', u'has', u'have', 
				u'he', u'he\'s' u'him', u'his', u'how', 
				u'in',u'i', u'i\'m', u'is',u'it',u'it\'s', u'its',
				u'if',u'of', u'just', u'like', 
				u'my', u'on', u'or', u'so', u'something',
				u'she', u'some', u'that', u'the',
				u'they', u'this', u'to', u'was', u'what', u'with',   
				u'you', u'-']

# Give a timestamp for the file. Return empty string if a file already exists from this hour.
def get_timestamp():
	t = datetime.datetime.now()
	tstamp = str(t).split(':')[0].replace(' ', '-')
	for path in os.listdir('crawled/counts/'):
		if tstamp in path:
			return ''
	return tstamp

# Save a basic dict to a file.
'''def save_to_file(f, dic, storage_threshold = 0):
	f.write(subreddit + '\n')
	for word in dic:
		if abs(dic[word]) >= storage_threshold:
			f.write(word + ' ' + str(dic[word]) + '\n')'''

# Sort and save counts to a file for a given subreddit. Append a timestamp to the filename.
def save_sorted_dict(dic, filename, storage_threshold = 0):
	# List of words sorted by dict values. Used to output the dict in sorted order.
	sorted_words = sorted(dic, key=lambda k: dic[k], reverse=True)
	f = open(filename, 'w')
	for word in sorted_words:
		# Get count from original dict
		count = dic[word]
		if abs(dic[word]) >= storage_threshold:
			f.write(word + ' ' + str(dic[word]) + '\n')

# Load counts from a number of history files and merge them
def load_counts(subreddit):
	filenames = []
	for filename in os.listdir('crawled/counts/'):
		if subreddit in filename and '.cm' in filename:
			filenames.append(filename)
	filenames.sort()
	# Keep only the top
	if len(filenames) >= hist_dist:
		filenames = filenames[:hist_dist]
	else:
		print("Not enough counts loaded, not calculating diffs.")
		return []
	counts = {}
	print("Loading " + str(len(filenames)) + " saved counts for subreddit " + subreddit)
	for filename in filenames:
		load_from_file(counts, filename, 'counts')
	return counts

# Load file into a dictionary
def load_from_file(dic, filename, file_type):
	full_path = 'crawled/' + file_type + '/' + filename
	if not os.path.exists(full_path):
		return False
	f = open(full_path, 'r')
	line = f.readline().split()
	while len(line) > 0:
		word = line[0]
		count = line[1]
		dic[word] = float(count)
		line = f.readline().split()
	return True

def print_counts(counts, limit):
	sorted_counts = sorted(counts.items(), key=operator.itemgetter(1), reverse=True)
	for word,count in sorted_counts:
		if limit <= 0:
			break
		print(word + ": " + str(counts[word]))
		limit = limit - 1

# Open a link from reddit and load the resulting json
def get_reddit_json(subreddit):
	url = 'https://www.reddit.com/r/' + subreddit + '/' + sort + '.json?t=' + interval
	
	# Need to add a user agent header because the API rejects boring headers
	req = urllib.request.Request(
		url,
		data=None,
		headers={
			'User-Agent': 'python:reddit-crawler (by /u/jumpbreak5)'
		}
	)
	f = urllib.request.urlopen(req)
	outjson = json.loads(f.read().decode('utf-8'))
	return outjson

# Get a list of comments for a reddit submission object. Ignore hidden comments
def get_comments(submission):
	comment_list = []
	comment_queue = submission.comments[:]
	while comment_queue:
		comment = comment_queue.pop(0)
		if not isinstance(comment, praw.models.MoreComments):
			comment_list.append(comment.body)
			comment_queue.extend(comment.replies)
	return comment_list

# Create a sorted list of word counts
def count_words(comments_list):
	word_count = {}
	for comment in comments_list:
		for word in comment.split():
			if word.lower() not in common_list:
				word_count[word] = word_count.get(word, 0) + 1
	return word_count

def build_thread(title, comments_list, should_print=False):
	# Title is added to the comment counts, and multiplied by an input constant
	for i in range(0, title_multiplier):
		comments_list.append(title)
	word_count = count_words(comments_list)
	# Output pretty representation of the thread and counts, if requested
	if should_print:
		print(title)
		print(str(len(comments_list)) + " comments total were found.")
		print_counts(word_count, 5)
	return Thread(title, word_count)

# Merge word counts for a list of thread objects into one sorted list of counts
def merge_thread_word_counts(threads):
	merged_word_counts = {}
	for thread in threads:
		for word in thread.word_count:
			merged_word_counts[word] = merged_word_counts.get(word, 0) + thread.word_count[word]
	return merged_word_counts

# Crawl a subreddit for mappings of words to frequencies.
# Returns a list of thread objects which each contain a frequency mapping for their own thread
# Also populates a master comment list which can be used to create a total subreddit frequency mapping
def crawl_threads(subreddit, sort, interval, should_print=False):
	print("Crawling reddit.com/r/" + subreddit)
	outjson = get_reddit_json(subreddit)
	#print(json.dumps(outjson, indent=2, sort_keys=True))
	reddit = praw.Reddit(user_agent='Comment Extraction (by /u/jumpbreak5)', client_id='4qYMwrPBzKcVTA', 
		client_secret="uDJR1uaBQBVDtU6RWRmRl_CYOOM", username='jumpbreak5', password='zippyx525')
	data = outjson["data"]
	threads_data = outjson["data"]["children"]
	# List of thread objects to return
	threads = []
	count = 0
	for thread_json in threads_data:
		if thread_json["kind"] == "t3":
			count += 1
			if count > thread_parse_limit:
				break
			#TODO: if should_print:
			print("Parsing thread " + str(count) + " of " \
				+ str(min(len(threads_data), thread_parse_limit)))

			# Get submission object from reddit, parse title and comments
			post_id = thread_json["data"]["id"]
			submission = reddit.submission(id=post_id)
			title = submission.title[0:60] + "..."
			comments_list = get_comments(submission)
			
			# Get thread object and store in list
			thread = build_thread(title, comments_list, True)
			threads.append(thread)
	return threads

def collect_counts(subreddit, tstamp):
	threads = crawl_threads(subreddit, sort, interval)
	merged_word_counts = merge_thread_word_counts(threads)
	if should_print:
		print("\n*** Top for entire subreddit ***")
		print_counts(merged_word_counts, 20)
	full_path = 'crawled/counts/' + subreddit + '.' + tstamp + '.cm'
	save_sorted_dict(merged_word_counts, full_path, 3)
	return merged_word_counts

def calculate_diffs(subreddit, counts):
	diffs = {}
	prev_counts = load_counts(subreddit)
	if len(prev_counts) is 0:
		return diffs
	for word in counts:
		count = counts.get(word, 0)
		prev_count = prev_counts.get(word, 0)
		diff = (count - prev_count) / (count + prev_count)
		if abs(diff) < 1.0:
			diffs[word] = diff
	return diffs

# Load stored diffs from a file for a given subreddit, update them, and save to the same file.
def update_stored_diffs(subreddit, diffs):
	old_diffs = {}
	# Filename for diffs is just the subreddit, no timestamp
	if load_from_file(old_diffs, subreddit + '.cm', 'diffs'):
		print("Found saved diffs for subreddit " + subreddit + ", updating with calculated diffs.")
		for word in diffs:
			old_diff = float(old_diffs.get(word, 0))
			diffs[word] = diffs[word] + old_diff
	else:
		print("No saved diffs found for subreddit " + subreddit + ", creating new diff file.")
	full_path = 'crawled/diffs/' + subreddit + '.cm'
	save_sorted_dict(diffs, full_path)

if __name__=='__main__':
	tstamp = get_timestamp()
	if tstamp == '':
		print("Data from this hour already exists! Exiting.")
		sys.exit(1)
	for subreddit in subreddits:
		counts = collect_counts(subreddit, tstamp)
		diffs = calculate_diffs(subreddit, counts)
		update_stored_diffs(subreddit, diffs)

	
	
	