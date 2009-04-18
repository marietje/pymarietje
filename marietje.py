from __future__ import with_statement
import threading

DEFAULT_HOST = 'devslet.sci.kun.nl'
DEFAULT_PORT = 1337
DEFAULT_LS_CHARSET = '1234567890qwertyuiopasdfghjklzxcvbnm '

import os
import time
import socket
import logging
import cPickle as pickle
from cStringIO import StringIO
from lstree import SimpleCachingLSTree

class MarietjeException(Exception):
	pass
class AlreadyQueuedException(MarietjeException):
	pass
class AlreadyFetchingException(Exception):
	pass

class RawMarietje:
	""" Almost direct interface to the Marietje protocol """

	def __init__(self, host=DEFAULT_HOST, port=DEFAULT_PORT):
		self.host = host
		self.port = port
	
	def check_login(self, username):
		""" Checks whether <username> is allowed on marietje """
		return self._simple_transaction("LOGIN::USER::%s\n" % username) \
				== "LOGIN::SUCCESS\n"
	
	def get_queue(self):
		""" Returns ( timeLeft, queue ) where queue is a list of
		    ( artist, title, length, requestedBy ) tuples. """
		s = self._connect()
		s.send("LIST::QUEUE\n")
		f = s.makefile()
		bits = f.readline()[:-1].split('::')
		if len(bits) != 4 or \
		   bits[0] != 'TOTAL' or bits[2] != 'TIMELEFT':
			   raise MarietjeException, \
		   		"Unexpected reply: %s" % '::'.join(bits)
		total, timeLeft = int(bits[1]), float(bits[3])
		rl = list()
		for i in xrange(total):
			bits = f.readline()[:-1].split('::')
			if len(bits) != 5 or bits[0] != 'SONG':
				raise MarietjeException, \
	 				"Unexpected SONG line: %s" % '::'.join(bits)
			artist, title, length, by = bits[1], bits[2], \
						float(bits[3]), bits[4] 
			rl.append((artist, title, length, by))
		s.close()
		return (timeLeft, rl)
	
	def get_playing(self):
		""" Return (id, timeStamp, length, time) with the
		    current playing's song <id> and <length>, the
		    current servers <time> and the starting time <timeStamp>
		    of the song """
		l = self._simple_transaction("LIST::NOWPLAYING\n")
		bits = l[:-1].split('::')
		if len(bits) != 8 or bits[0] != 'ID' or bits[2] != 'Timestamp' or \
				bits[4] != 'Length' or bits[6] != 'Time':
			raise MarietjeException, "Unexpected reply: %s" % l
		id, timeStamp, length, time = int(bits[1]), float(bits[3]), \
					      float(bits[5]), float(bits[7])
		return (id, timeStamp, length, time)

	def list_tracks(self):
		""" Returns a list of
		     (trackId, artist, title, flag) """
		s = self._connect()
		s.send('LIST::ALL')
		f = s.makefile()
		bits = f.readline()[:-1].split('::')
		if len(bits) != 2 or bits[0] != 'TOTAL':
			raise MarietjeException, \
				"Unexpected reply: %s" % '::'.join(bits)
		total = int(bits[1])
		for i in xrange(total):
			bits = f.readline()[:-1].split('::')
			if len(bits) != 5 or bits[0] != 'SONG':
				raise MarietjeException, \
					"Unexpected reply: %s" % '::'.join(bits)
			yield (int(bits[1]), bits[2], bits[3], int(bits[4]))
		s.close()
	
	def request_track(self, trackId, user):
		""" Requests the song <trackId> under the username <user> """
		s = self._simple_transaction("REQUEST::SONG::%s::USER::%s" % (
			trackId, user))
		if s == 'REQUEST::SUCCESS':
			return
		if s == 'ERROR::Track already in queue':
			raise AlreadyQueuedException
		raise MarietjeException, "Unexpected reply: %s" % s

	def upload_track(self, artist, title, user, size, f):
		""" Uploads <size> bytes of <f> as the track 
		    <artist> - <title> as <user> """
		s = self._connect()
		s.send('REQUEST::UPLOAD::ARTIST::%s::TITLE::%s::USER::%s::SIZE::%s' % (
			artist, title, user, size))
		l = s.recv(50)
		if l != 'SEND::FILE':
			raise MarietjeException, \
				"Unexpected reply: %s" % l
		sent = 0
		while sent != size:
			toSent = size - sent
			if toSent > 2048: toSent = 2048
			stillToSent = toSent
			txt = f.read(stillToSent)
			while stillToSent > 0:
				stillToSent -= s.send(txt[-stillToSent:])	
			sent += toSent
		l = s.recv(50)
		if l != 'UPLOAD::SUCCESS':
			raise MarietjeException, \
				"Unexpected reply: %s" % l
		s.close()

	def _connect(self):
		s = socket.socket(socket.AF_INET,
				  socket.SOCK_STREAM)
		s.connect((self.host, self.port))
		return s

	def _simple_transaction(self, msg):
		s = self._connect()
		s.send(msg)
		ret = StringIO()
		while True:
			l = s.recv(2048)
			if len(l) == 0: break
			ret.write(l)
		s.close()
		return ret.getvalue()

class Marietje:
	""" A more convenient interface to Marietje.
	    NOTE, even though there is a ton of threading.* goodness in here,
	    	  this class is not to be used by several threads at a time """
	def __init__(self, username, queueCb=None, songCb=None, playingCb=None,
			host=DEFAULT_HOST, port=DEFAULT_PORT,
			charset=DEFAULT_LS_CHARSET):
		""" <xCb> is a callback for when x is fetched;
		    <charset> is used as charset for the livesearch look-up
		    tree. """
		self.raw = RawMarietje(host, port)
		self.queueCb = queueCb
		self.songCb = songCb
		self.playingCb = playingCb
		self.songs_fetched = False
		self.queue_fetched = False
		self.playing_fetched = False
		self.songs_fetching = False
		self.queue_fetching = False
		self.playing_fetching = False
		self.songs_cond = threading.Condition()
		self.queue_cond = threading.Condition()
		self.playing_cond = threading.Condition()
		self.cs = charset
		self.cs_lut = set(charset)
		self.username = username
		self.l = logging.getLogger('Marietje')
	
	def _sanitize(self, txt):
		""" Prepares a str <txt> for live search """
		txt = txt.lower()
		ret = ''
		for c in txt:
			if c in self.cs_lut:
				ret += c
		return ret
	
	def _request_song_fetch(self):
		with self.songs_cond:
			if self.songs_fetching:
				raise AlreadyFetchingException
			self.songs_fetching = True
	def _request_queue_fetch(self):
		with self.queue_cond:
			if self.queue_fetching:
				raise AlreadyFetchingException
			self.queue_fetching = True
	def _request_playing_fetch(self):
		with self.playing_cond:
			if self.playing_fetching:
				raise AlreadyFetchingException
			self.playing_fetching = True

	def start_fetch(self, fetchSongs=True,
			      fetchPlaying=True,
			      fetchQueue=True):
		try:
			if fetchSongs:
				self._request_song_fetch()
		except AlreadyFetchingException:
			fetchSongs = False
		try:
			if fetchPlaying:
				self._request_playing_fetch()
		except AlreadyFetchingException:
			fetchPlaying = False
		try:
			if fetchQueue:
				self._request_queue_fetch()
		except AlreadyFetchingException:
			fetchQueue = False
		if fetchSongs: self.start_fetch_songs()
		if fetchQueue: self.start_fetch_queue()
		if fetchPlaying: self.start_fetch_playing()

	# These will be used if the annoying marietjed bug is fixed
	def start_fetch_songs(self):
		self.songs_thread = threading.Thread(target=self.run_fetch_songs)
		self.songs_thread.start()
	def start_fetch_queue(self):
		self.queue_thread = threading.Thread(target=self.run_fetch_queue)
		self.queue_thread.start()
	def start_fetch_playing(self):
		self.playing_thread = threading.Thread(target=self.run_fetch_playing)
		self.playing_thread.start()
	
	def run_fetch_songs(self):
		def entry_compare(x, y):
			v = cmp(x[0], y[0])
			return v if v != 0 else cmp(x[1], y[1])
		try:
			starttime = time.time()
			songs = dict()
			for id, artist, title, flag in self.raw.list_tracks():
				songs[id] = (artist, title)
			sLoadTime = time.time() - starttime
			starttime = time.time()
			entries = list()
			for id, (artist, title) in songs.iteritems():
				entries.append((self._sanitize(artist) + " " +
					self._sanitize(title), id))
			sLut = SimpleCachingLSTree(entries, _cmp=entry_compare)
			sLutGenTime = time.time() - starttime
			with self.songs_cond:
				self.songs = songs
				self.sLoadTime = sLoadTime
				self.sLutGenTime = sLutGenTime
				self.sLut = sLut
				self.songs_fetched = True
		except MarietjeException, e:
			self.sException = e
			self.l.exception("Marietje exception")
		except Exception:
			self.l.exception("Uncatched exception")
		finally:
			with self.songs_cond:
				self.songs_fetching = False
				self.songs_cond.notifyAll()
			if not self.songCb is None:
				self.songCb()
	
	def run_fetch_queue(self):
		try:
			starttime = time.time()
			queue_totalTime, queue = self.raw.get_queue()
			qLoadTime = time.time() - starttime
			with self.queue_cond:
				self.queue_totalTime = queue_totalTime
				self.queue = queue
				self.qLoadTime = qLoadTime
				self.queue_fetched = True
		except MarietjeException, e:
			self.qException = e
			self.l.exception("Marietje exception")
		except Exception:
			self.l.exception("Uncatched exception")
		finally:
			with self.queue_cond:
				self.queue_fetching = False
				self.queue_cond.notifyAll()
			if not self.queueCb is None:
				self.queueCb()

	def run_fetch_playing(self):
		try:
			starttime = time.time()
			nowPlaying = self.raw.get_playing()
			pLoadTime = time.time() - starttime
			playingRetreivedTime = starttime + 0.5 * pLoadTime
			queueOffsetTime = nowPlaying[1] - (nowPlaying[3] - 
					  playingRetreivedTime) + nowPlaying[2]
			with self.playing_cond:
				self.nowPlaying = nowPlaying
				self.pLoadTime = pLoadTime
				self.playingRetreivedTime = playingRetreivedTime
				self.queueOffsetTime = queueOffsetTime
				self.playing_fetched = True
		except MarietjeException, e:
			self.pException = e
			self.l.exception("Marietje exception")
		except Exception:
			self.l.exception("Uncatched exception")
		finally:
			with self.playing_cond:
				self.playing_fetching = False
				self.playing_cond.notifyAll()
			if not self.playingCb is None:
				self.playingCb()
	
	def cache_songs_to(self, f):
		""" Caches the songs and its look up structures to the given
		    file """
		with self.songs_cond:
			if not self.songs_fetched:
				raise RuntimeError, "songs haven't been fetched"
			songs = self.songs
			sLut = self.sLut
		
		sLut.prune()	
		pickle.dump((songs, sLut), f, pickle.HIGHEST_PROTOCOL)
	
	def songs_from_cache(self, f, abort_on_preempt=True):
		""" Fetches songs and its look up structure from a cache in
		    file created by <cache_songs_to>. Calls the callback
		    If after having loaded the cache, <songs_fetched> is set,
		    it'll abort if <abort_on_preempt>. """
		starttime = time.time()
		songs, sLut = pickle.load(f)
		sLoadTime = time.time() - starttime
		with self.songs_cond:
			if abort_on_preempt and self.songs_fetched:
				return
			self.songs = songs
			self.sLut = sLut
			self.songs_fetched = True
			self.sCacheLoadTime = sLoadTime
		if not self.songCb is None:
			self.songCb(from_cache=True)
	
	def query(self, q):
		""" Performs a query for all songs that have <q> in their title
		    or artist.  Returns a list of ids """
		q = self._sanitize(q)
		# bit of a performance waster, but we don't want one track
		# several times in the results (when artist and title match)
		start = time.time()
		ret = tuple(self.sLut.query(q))
		self.l.info('query %s took %s' % (q, time.time() - start))
		return ret

	def request_track(self, track_id):
		""" Requests the track with id <track_id> """
		self.raw.request_track(track_id, self.username)
	
	def upload_track(self, artist, title, size, f):
		""" Uploads a track in <f> with <size> to marietje as
		    <artist> - <title> """
		self.raw.upload_track(artist, title, self.username, size, f)

if __name__ == '__main__':
	logging.basicConfig(level=logging.DEBUG)
	m = Marietje()
