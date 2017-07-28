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
#from websocket import create_connection

import websocket
import threading
import time

d_threshold = 3
log_file = open('out.log', 'w')
min_set = False
max_set = False

def log_out(outstr):
	t = datetime.datetime.now()
	out_log = str(t) + ": " + outstr
	log_file.write(out_log + '\n')
	print out_log

def update_bid_ask(exchange, event, bidstr, askstr):
	# Threshold for variability, so we don't drop based on a glitch
	global max_set
	global min_set
	variability = 0.8
	try:
		if "price" in event: # Account for "funds" key? Seems relevant for large orders
			price = float(event["price"])
			if "side" in event: # Account for makerSide key? (Rare but possible, has same values as "side")
				if event["side"] == bidstr:
					if not max_set:
						exchange.maxBid = max(exchange.maxBid, price)
					elif price < exchange.maxBid / variability:
						exchange.maxBid = max(exchange.maxBid, price)
						exchange.maxTime = datetime.datetime.now()
					if price > exchange.highBid:
						t = datetime.datetime.now()
						#print exchange.name + ": " + str(t) + " " + bidstr + " updated to " + str(price) + "!"
						exchange.highBid = price
						exchange.bid_set = True
						max_set = True
						if exchange.highBid > exchange.lowAsk:
							#print "Got a bid %s higher than our lowest ask! Adjusting lowest ask to this price" % exchange.highBid
							exchange.lowAsk = exchange.highBid
				if event["side"] == askstr:
					if not min_set:
						exchange.minAsk = min(exchange.minAsk, price)
					elif price > variability * exchange.minAsk:
						exchange.minAsk = min(exchange.minAsk, price)
						exchange.minTime = datetime.datetime.now()
					if price < exchange.lowAsk:
						t = datetime.datetime.now()
						#print exchange.name + ": " + str(t) + " " + askstr + " updated to " + str(price) + "!"
						exchange.lowAsk = price
						exchange.ask_set = True
						min_set = True
						if exchange.lowAsk < exchange.highBid:
							#print "Got an ask %s lower than our highest bid! Adjusting highest bid to this price" % exchange.lowAsk
							exchange.highBid = exchange.lowAsk

	except:
		print event
		raise

def on_error(ws, error):
    print error

def on_close(ws):
    print "### closed ###"

class Gemini:
	name = "Gemini"
	highBid = 0
	lowAsk = 10000000
	ask_set = False
	bid_set = False

	def connect(self):
		ws = websocket.WebSocketApp("wss://api.gemini.com/v1/marketdata/ETHUSD",
			on_message = self.on_message,
			on_error = on_error,
			on_close = on_close)
	#ws.on_open = on_gemini
		t = threading.Thread(target=ws.run_forever)
		t.setDaemon(True)
		t.start()
	
	def on_message(self, ws, message):
		result = json.loads(message)
		events = result["events"]
			
		for event in events:
			update_bid_ask(self, event, "bid", "ask")
		#print ("High bid is %s and low ask is %s" % (self.highBid, self.lowAsk))

class GDAX:
	name = "GDAX"
	highBid = 0
	lowAsk = 10000000
	# Extreme values for precise tracking of min and max
	maxBid = 0
	minAsk = 10000000
	maxTime = datetime.datetime.now()
	minTime = datetime.datetime.now()
	ask_set = False
	bid_set = False

	def connect(self):
		ws = websocket.WebSocketApp("wss://ws-feed.gdax.com",
			on_message = self.on_message,
			on_error = on_error,
			on_close = on_close)
		ws.on_open = self.on_open
		t = threading.Thread(target=ws.run_forever)
		t.setDaemon(True)
		t.start()
	
	def on_open(self, ws):
		ws.send(json.dumps({
			"type": "subscribe",
			"product_ids": [
				"ETH-USD",
    		],
		}))

	def on_message(self, ws, message):
		event = json.loads(message)
		update_bid_ask(self, event, "buy", "sell")

	def trade(self, amount, trade_type):
		print("Would have made a %s for %s" % (trade_type, amount))
		if trade_type == 'sell':
			return self.highBid
		if trade_type == 'buy':
			return self.lowAsk

def on_open(ws):
	ws.send(json.dumps({
		"event": "subscribe",
		"channel": "ticker",
		"pair": "tETHUSD",
		"prec": "P0"
	}))
	while True:
		result = ws.recv()
		result = json.loads(result)
		print ("Received '%s'" % result)
	ws.close()
	print "thread terminating..."

class TrackMax():
	max_diff = 0.0

	def init(self):
		t = threading.Thread(target=self.calc_diffs, args=(gemini, gdax))
		t.setDaemon(True)
		t.start()

	def calc_diffs(self, gemini, gdax):
		while True:
			if gemini.ask_set and gdax.ask_set and gemini.bid_set and gdax.bid_set:
				a_diff = gemini.highBid - gdax.lowAsk
				b_diff = gdax.highBid - gemini.lowAsk
				diff = max(abs(a_diff), abs(b_diff))
				if diff > d_threshold:
					if a_diff > b_diff:
						log_out("Huge diff alert! High bid on gemini is %s and low ask on gdax is %s" % (gemini.highBid, gdax.lowAsk))
					else:
						log_out("Huge diff alert! High bid on gdax is %s and low ask on gemini is %s" % (gdax.highBid, gemini.lowAsk))
				self.max_diff = max(diff, self.max_diff)

class TrackMorning():
	last_trade_date = datetime.datetime.today().date() - datetime.timedelta(days=1)
	last_trade_type = 'none'
	trade_dollars = 250

	cash = 1000
	coin = 2

	trade_hour = 6
	trade_minute = 0
	track_delta_hour = 8
	track_delta_minute = 0
	finish_delta_hour = 2
	finish_delta_minute = 0

	traded = False
	finish_time = datetime.datetime.now()

	def init(self, exchange):
		t = threading.Thread(target=self.track_morning, args=(exchange))
		t.setDaemon(True)
		t.start()

	def track_morning(self, exchange):

		# Current extremes for prices seen by the tracker
		max_price = 0
		min_price = 10000000

		# Total amount of change in price needed in the tracking window to trigger a trade
		change_fraction = 0.05
		# How much of the change we expect will be undone by the correction
		recovery_fraction = 0.2 * change_fraction

		value = 100

		HODL = False
		HODL_coins = self.coin
		HODL_value = 0

		while True:
			# If we aren't HODLing already, HODL at current price
			if not HODL:
				HODL_coins += self.cash / exchange.lowAsk
				HODL = True

			cur_time = datetime.datetime.now()
			# Get the nearest trade time to the current time
			trade_time = datetime.datetime(
				cur_time.year, cur_time.month, cur_time.day,
				self.trade_hour, self.trade_minute)
			# If trade time already passed for the day, move it to the next day
			if trade_time < cur_time:
				trade_time += datetime.timedelta(days=1)
			# Calculate time at which we should begin tracking
			track_time = trade_time - datetime.timedelta(hours=self.track_delta_hour)
			track_time -= datetime.timedelta(minutes=self.track_delta_minute)
			# If current time is between when we should start tracking, and when we should trade
			if track_time < cur_time and cur_time < trade_time:
				min_price = min(exchange.minAsk, min_price)
				max_price = max(exchange.maxBid, max_price)
				cur_price = (exchange.minAsk + exchange.maxBid) / 2
				print("Currently Tracking. Min price is %s, max price is %s, Current price is %s. Will trade at %s, current time is %s" %
					(min_price, max_price, cur_price, trade_time, cur_time))
			# If it is exactly trade time
			elif cur_time.hour == trade_time.hour and cur_time.minute == trade_time.minute:
				# If we didn't already trade today
				if self.last_trade_date != datetime.datetime.today().date():
					# If current price is greater than the minimum past price plus a multiplier
					sell_target = min_price + min_price * change_fraction
					# If the exchange is buying above our sell target, and the time used to set that target
					# came later than the time used to set our buy target
					if exchange.lowAsk >= sell_target and exchange.maxTime < exchange.minTime:
						# Sell, because the price spiked and will likely correct down
						self.trade(exchange, 'sell', cur_time)
						recovery_target = min_price + min_price * recovery_fraction
					else:
						print("Not going to sell, price %s is below change target %s" % (exchange.lowAsk, sell_target))
					buy_target = max_price - max_price * change_fraction
					# If the exchange is selling below our buy target, and the time used to set that target
					# came later than the time used to set our sell target
					if exchange.highBid <= buy_target and exchange.minTime < exchange.maxTime:
						# Buy, because the price spiked and will likely correct up
						self.trade(exchange, 'buy', cur_time)
						recovery_target = max_price - max_price * recovery_fraction
					else:
						print("Not going to buy, price %s is above change target %s" % (exchange.highBid, buy_target))
				else:
					print("Already traded today! Not doing anything.")
			# A trade was made, check if we should finish it
			elif self.traded:
				if self.check_finish(exchange, recovery_target, cur_time):
					max_price = 0
					min_price = 10000000
			else:
				print("Waiting until %s to begin tracking. Current time is %s." % (track_time, cur_time))

			# Update values
			HODL_value = HODL_coins * exchange.highBid
			value = self.cash + self.coin * exchange.highBid

			print("Value is %s (%s cash and %s coins) while HODL value is %s." % (value, self.cash, self.coin, HODL_value))
			# Sleep after interval (don't need to check that often)
			time.sleep(60)

	def check_finish(self, exchange, recovery_target, cur_time):
		# Store last trade type so it isn't affected by trade
		stored_last = self.last_trade_type

		# Reverse trades if we've hit our target, or if the maximum amount of time has passed
		if stored_last == 'sell':
			if exchange.minAsk < recovery_target or self.finish_time < cur_time:
				print ("Hit recovery target %s! Buying back coins" % recovery_target)
				self.trade(exchange, 'buy', cur_time)
			else:
				print("Waiting for price %s to be below recovery target %s, or until we've passed finish time %s. Current time is %s." % \
					(exchange.minAsk, recovery_target, self.finish_time, cur_time))
				return False
		elif stored_last == 'buy':
			if exchange.maxBid > recovery_target or self.finish_time < cur_time:
				print ("Hit recovery target %s! Selling off coins" % recovery_target)
				self.trade(exchange, 'sell', cur_time)
			else:
				print("Waiting for price %s to be above recovery target %s, or until we've passed finish time %s. Current time is %s." % \
					(exchange.maxBid, recovery_target, self.finish_time, cur_time))
				return False

		# Trade is done, reset for the next one
		self.last_trade_type = 'none'
		self.traded = False
		return True

	# none check?
	def trade(self, exchange, trade_type, cur_time):
		log_out("Making a %s order for $%s" % (trade_type, self.trade_dollars))
		self.last_trade_type = trade_type
		price = 0
		if trade_type == 'sell':
			price = exchange.trade(self.trade_dollars, trade_type)
			
			self.last_trade_date = cur_time.date()
			self.cash += self.trade_dollars
			self.coin -= self.trade_dollars / price

		if trade_type == 'buy':
			price = exchange.trade(self.trade_dollars, trade_type)

			self.last_trade_date = cur_time.date()
			self.cash -= self.trade_dollars
			self.coin += self.trade_dollars / price

		self.traded = True
		# Calculate time at which we should finish trading (undo trades made)
		self.finish_time = cur_time
		self.finish_time += datetime.timedelta(hours=self.finish_delta_hour) + \
							datetime.timedelta(minutes=self.finish_delta_minute)


def print_diffs(gemini, gdax, track, interval):
	while True:
		time.sleep(interval)
		a_diff = gemini.highBid - gdax.lowAsk
		log_out("Gemini is buying at %s and GDAX is selling at %s, diff is %s" % (gemini.highBid, gdax.lowAsk, a_diff))
		b_diff = gdax.highBid - gemini.lowAsk
		log_out("GDAX is buying at %s and Gemini is selling at %s, diff is %s" % (gdax.highBid, gemini.lowAsk, b_diff))
		log_out("Max diff so far was " + str(track.max_diff))

#"wss://api2.bitfinex.com:3000/ws"
# 
#"wss://api.gemini.com/v1/marketdata/ETHUSD"
if __name__ == "__main__":
	websocket.enableTrace(True)
	#gemini = Gemini()
	#gemini.connect()
	gdax = GDAX()
	gdax.connect()
	time.sleep(5)
	track = TrackMorning()
	track.track_morning(gdax)
	#print_diffs(gemini, gdax, track, 10)
		#print "Buy diff is %s and sell diff is %s" % (buy_diff, sell_diff)