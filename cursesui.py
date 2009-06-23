from __future__ import with_statement

import os
import sys
import yaml
import time
import gzip
import curses
import os.path
import logging
import optparse
import threading
import subprocess
from random import random
from marietje import Marietje, MarietjeException
from cStringIO import StringIO

VERSION = 9
INITIAL_TIMEOUT = 100
DEFAULT_TIMEOUT = 1000

(CP_WHITE, CP_BLUE, CP_GREEN, CP_RED,
 CP_CWHITE, CP_CBLUE, CP_CGREEN, CP_CRED) = range(8)

GOT_COLORS = True

def curses_use_default_colors(*args, **kwargs):
	if not hasattr(curses, 'has_colors') or \
			not curses.has_colors():
		global GOT_COLORS
		GOT_COLORS = False
		return
	curses.use_default_colors(*args, **kwargs)
def curses_color_pair(*args, **kwargs):
	if not GOT_COLORS:
		return curses.A_BOLD
	return curses.color_pair(*args, **kwargs)
def curses_init_pair(*args, **kwargs):
	if not GOT_COLORS:
		return
	return curses.init_pair(*args, **kwargs)

def format_list(l):
	""" Formats a list <l> neatly """
	if len(l) == 1:
		return str(l[0])
	if len(l) == 0:
		return 
	ret = ''
	first = True
	for i in xrange(len(l) - 1):
		if first: first = False
		else: ret += ', '
		ret += str(l[i])
	return ret + ' and ' + str(l[-1])

def format_time(s):
	""" Formats a <s> seconds into <hours>:<minutes>:<seconds>,
	    nicely. """
	s = int(s)
	if s < 0:
		ret = '-'
		s = abs(s)
	else:
		ret = ''
	seconds = s % 60
	s /= 60
	minutes = s % 60
	s /= 60
	hours = s
	if hours != 0:
		ret += str(hours) + ':' + str(minutes).zfill(2)
	else:
		ret += str(minutes)

	ret += ':' + str(seconds).zfill(2)
	return ret

class ScrollingColsWindow:
	""" Base of both the queue and the search result view.  Shows a dataset
	    in a table with an optional cursor. """
	def __init__(self, w, use_cursor=False):
		self.w = w
		self.needRedraw = True
		self.needLayout = False
		self.x_offset = 0
		self.y_offset = 0
		self.old_x_offset = 0
		self.old_y_offset = 0
		self.old_w = 0
		self.old_h = 0
		self.y_max = 0
		self.col_ws = None
		self.use_cursor = use_cursor
		self.c_offset = 0
		self.c_middle = 0
		self.old_c_offset = 0
	
	def scroll_page_up(self):
		self.y_offset -= self.old_h
	
	def scroll_page_down(self):
		self.y_offset += self.old_h

	def scroll_up(self):
		if self.use_cursor and (self.c_middle < self.c_offset or \
					self.y_max < self.old_h):
			self.c_offset -= 1
		else:
			self.y_offset -= 1
	
	def scroll_down(self):
		if self.use_cursor and (self.c_middle > self.c_offset or \
					self.y_max < self.old_h):
			self.c_offset += 1
		else:
			self.y_offset += 1
	
	def scroll_home(self):
		self.y_offset = 0
	
	def scroll_end(self):
		self.y_offset = self.y_max
	
	def scroll_right(self):
		self.x_offset += 1
		if self.x_offset == 1:
			self.x_offset = 2
	
	def scroll_left(self):
		self.x_offset -= 1
		if self.x_offset <= 1:
			self.x_offset = 0

	def get_data_info(self):
		""" Should return the number of rows, the average sizes of the
		    columns and the maximum sizes of the columns """
		raise NotImplementedError
	
	def _layout(self, vals, w, maxs):
		""" Helper for layout: finds the best way to fit volumns of
		    preferred widths of <vals> to a total width of <w> with
		    maximum values <maxs> """
		if sum(vals) == 0:
			return [0] * (len(vals) - 1) + [w]
		r = float(w) / float(sum(vals))
		ret = map(lambda x: int(x*r), vals)
		e = w - sum(ret)
		for i in xrange(abs(e)):
			ret[i] += (1 if e > 0 else -1)
		# If the assigned row width is less than its maximum, we'll
		# try to give at least a width of three for the '>' and '$'.
		cur = 0
		for i in xrange(0, len(ret)):
			last = ret[i]
			while ret[i] < maxs[i] and ret[i] < 3:
				for j in xrange(len(ret)):
					if ret[(j + cur) % len(ret)] > 3:
						ret[(j + cur) % len(ret)] -= 1
						ret[i] += 1
						break
				cur = (cur + j + 1) % len(ret)
				if ret[i] == last:
					# We couldn't find any more room
					return ret
				last = ret[i]
		return ret

	def layout(self):
		""" Calculate the widths of the seperate columns """
		self.needLayout = False
		h, w = self.w.getmaxyx()
		di = self.get_data_info()
		if di is None:
			self.y_max = 0
			return
		N, avgs, maxs = di
		if sum(maxs) <= w:
			self.col_ws = self._layout(maxs, w, maxs)
		else:
			self.col_ws = self._layout(avgs, w, maxs)
		self.y_max = N
	
	def draw_cell_text(self, val, start, end, colors):
		self.w.addstr(val[start:end])
	
	def draw_cell(self, y, cx, cw, val, colors):
		self.w.move(y, cx)
		if len(val) > cw:
			if self.x_offset == 0:
				self.draw_cell_text(val, 0, cw-1, colors)
				self.w.addch('$', colors[1])
			else:
				self.w.addch('>', colors[2])
				off = self.x_offset
				if off + cw - 2 > len(val):
					off = len(val) - cw + 2
				self.draw_cell_text(val, off, off+cw-2,
						colors)
				self.w.addch('$', colors[1])
		else:
			self.draw_cell_text(val, 0, len(val), colors)

	
	def draw_cols_line(self, y, cells, is_cursor):
		""" Draws a line with columns """
		self.w.move(y, 0)
		self.w.clrtoeol()
		if is_cursor:
			self.w.attron(curses_color_pair(CP_CWHITE))
			self.w.hline(' ', self.w.getmaxyx()[1])
			colors = map(curses_color_pair,
				[CP_CWHITE, CP_CBLUE, CP_CGREEN, CP_CRED])
		else:
			colors = map(curses_color_pair,
				[CP_WHITE, CP_BLUE, CP_GREEN, CP_RED])
		self.w.move(y, 0)
		cx = 0
		for j in xrange(len(self.col_ws)):
			if self.col_ws[j] == 0:
				assert cells[j] == ''
				continue
			cw = self.col_ws[j]
			try:
				self.draw_cell(y, cx, cw, cells[j], colors)
			except curses.error:
				if y == self.w.getmaxyx()[0] - 1 and \
					cx + cw == sum(self.col_ws):
						# curses doesn't like us
						# writing to the top right:
						# ignore.
						pass
				else:
					try:
						self.w.move(y, cx)
						self.w.addch('!', colors[3])
					except curses.error:
						# This shouldn't happen!
						raise Exception, (y, cx)
			cx += cw
		if is_cursor:
			self.w.attroff(curses_color_pair(
				CP_CWHITE))

	
	def draw_line(self, y, is_cursor):
		""" Draws a line """
		self.w.move(y, 0)
		if y + self.y_offset >= self.y_max:
			self.w.addstr('~', curses_color_pair(
					CP_BLUE))
			self.w.clrtoeol()
		else:
			cells = self.get_cells(y + self.y_offset)
			self.draw_cols_line(y, cells, is_cursor)
	
	def update(self, forceRedraw=False):
		""" Update the view """
		h, w = self.w.getmaxyx()
		if not forceRedraw and not self.needRedraw:
			if self.old_x_offset != self.x_offset or \
			   self.old_y_offset != self.y_offset or \
			   self.old_w != w or self.old_h != h or \
			   (self.use_cursor and \
			   		self.old_c_offset != self.c_offset):
				pass
			else:
				return
		self.needRedraw = False
		if self.old_w != w or self.old_h != h:
			self.old_h = h
			self.old_w = w
			self.needLayout = True
			if self.use_cursor:
				self.c_middle = h/2
		if self.needLayout:
			self.layout()
		if self.col_ws is None:
			self.y_max = 0
		if self.y_offset + h > self.y_max:
			self.y_offset = self.y_max - h
			if self.use_cursor:
				self.c_offset += 1
		if self.y_offset < 0:
			self.y_offset = 0
			if self.use_cursor:
				self.c_offset -= 1
		if self.use_cursor:
			if self.c_offset < 0:
				self.c_offset = 0
			elif self.c_offset + self.y_offset >= self.y_max:
				self.c_offset = min(h - 1,
						self.y_max - self.y_offset - 1)
		start = time.time()
		for y in xrange(h):
			self.draw_line(y, self.use_cursor and y==self.c_offset)
		# We update old_ here for they might've been updated
		# by self.draw_line or above
		self.old_y_offset = self.y_offset
		self.old_x_offset = self.x_offset
		if self.use_cursor:
			self.old_c_offset = self.c_offset
		self.w.noutrefresh()

	def touch(self, layout=False):
		""" Touches the window to redraw.  If <layout>, also recompute
		    the column layout """
		self.needRedraw = True
		if layout: self.needLayout = True
	
	def get_view_region(self):
		""" Return view region information: start and end of the region
		    currently viewed in the dataset and the total amount of
		    lines """
		return (self.y_offset, self.y_offset + self.old_h, self.y_max)

class SearchWindow(ScrollingColsWindow):
	def __init__(self, w, m, highlight=True):
		ScrollingColsWindow.__init__(self, w, use_cursor=True)
		self.needDataInfoRecreate = False
		self.data_info = None
		self.data = None
		self.m = m
		self.query = None
		self.highlight = highlight
		
	def draw_cell_text(self, val, start, end, colors):
		if not self.highlight:
			return ScrollingColsWindow.draw_cell_text(self,
					val, start, end, colors)
		ridx = -1
		idxs = [0]
		val_lower = val.lower()
		while True:
			ridx = val_lower.find(self.query, ridx+1)
			if ridx == -1:
				break
			if ridx < idxs[-1]:
				idxs[-1] = ridx + len(self.query)
			else:
				idxs.append(ridx)
				idxs.append(ridx + len(self.query))
		idxs.append(len(val))
		v = list(idxs)
		v.sort()
		assert v == idxs
		m = True
		for i in xrange(0, len(idxs)-1):
			m = not m
			istart, iend = idxs[i:i+2]
			if end <= istart: continue
			if iend <= start: continue
			istart = max(istart, start)
			iend = min(iend, end)
			if istart == iend: continue
			self.w.attron(colors[3 if m else 0])
			self.w.addstr(val[istart:iend])
			self.w.attroff(colors[3 if m else 0])
	
	def set_query(self, q):
		if self.query == q:
			return
		self.query = q
		self.data = None
		self.needDataInfoRecreate = True
	
	def touch(self, layout=False, data=False):
		if data:
			self.needDataInfoRecreate = True
		ScrollingColsWindow.touch(self, layout=layout)
	
	def fetch_data(self):
		return self.m.query(self.query)

	def get_data_info(self):
		if self.data is None:
			if not self.m.songs_fetched:
				return None
			self.data = self.fetch_data()
		if len(self.data) == 0:
			return None
		if self.data_info is None or \
				self.needDataInfoRecreate:
			self.needDataInfoRecreate = False
			self.data_info = None
		if self.data_info is None:
			self.data_info = self.create_data_info()
		return self.data_info
	
	def create_data_info(self):
		N = len(self.data)
		l = len(self.get_cells(0))
		sums = [0]*l
		maxs = [0]*l
		for i in xrange(N):
			cells = self.get_cells(i)
			for j in xrange(l):
				sums[j] += len(cells[j])
				maxs[j] = max(len(cells[j]), maxs[j])
		return (N, map(lambda x: x/N, sums), maxs)

	def get_cells(self, j):
		return (self.m.songs[self.data[j]][0],
			self.m.songs[self.data[j]][1])
	
	def request_track(self):
		""" Requests the track under the cursor """
		cpos = self.c_offset + self.y_offset
		if len(self.data) == 0: return
		track_id = self.data[cpos]
		self.m.request_track(track_id)
			

class QueueWindow(ScrollingColsWindow):
	def __init__(self, w, m):
		ScrollingColsWindow.__init__(self, w)
		self.m = m
		self.data_info = None
		self.needDataInfoRecreate = False
		self.time_lut = None
		self.last_redraw = 0
	
	def create_data_info(self):
		# Sometimes self.m.queue doesn't exist
		N = len(self.m.queue) + 1
		l = len(self.get_cells(0))
		sums = [0]*l
		maxs = [0]*l
		for i in xrange(N):
			cells = self.get_cells(i)
			for j in xrange(l):
				sums[j] += len(cells[j])
				maxs[j] = max(len(cells[j]), maxs[j])
		return (N, map(lambda x: x/N, sums), maxs)
	
	def _nowPlaying_line(self):
		""" Returns the line containing the currently playing song """
		if len(self.m.queue) == 0:
			timeLeft = format_time(int(self.m.queueOffsetTime - \
					time.time()))
		else:
			# The countdown on the first queued song would equal
			# <timeleft>.
			timeLeft = ''
		self.m.queueOffsetTime
		if not self.m.nowPlaying[0] in self.m.songs:
			return ('', 'unknown track', '#%s' % \
					self.m.nowPlaying[0], timeLeft)
		artist, title = self.m.songs[self.m.nowPlaying[0]]
		return ('', artist, title, timeLeft)
	
	def get_cells(self, l):
		if l == 0:
			if not self.m.playing_fetched or \
			   not self.m.songs_fetched:
				return ('','','','')
			return self._nowPlaying_line()
		l -= 1
		if self.time_lut is None:
			t = format_time(self.m.queue[l][2])
		else:
			t = format_time(int(self.time_lut[l] - time.time()))
		return (self.m.queue[l][3],
			self.m.queue[l][0],
			self.m.queue[l][1],
			t)

	def get_data_info(self):
		if not self.m.queue_fetched or len(self.m.queue) == 0:
			if not self.m.playing_fetched or \
			   not self.m.songs_fetched:
				return None
			N = 1
		else:
			N = 1 + len(self.m.queue)
		if self.data_info is None or \
				self.data_info[0] != N or \
				self.needDataInfoRecreate:
			self.needDataInfoRecreate = False
			self.time_lut = None
			# We first need to create self.time_lut, for
			# create_data_info depends on it
			self.data_info = None
		# Compute the timestamps of initiation of each of 
		# the queued tracks
		if self.time_lut is None:
			if self.m.playing_fetched and \
			   self.m.queue_fetched:
				id, songStarted, songLength, \
					serverTime = self.m.nowPlaying
				offset = self.m.queueOffsetTime
				self.time_lut = list()
				for i in xrange(len(self.m.queue)):
					self.time_lut.append(offset)
					offset += self.m.queue[i][2]
		if self.data_info is None and self.m.queue_fetched:
			self.data_info = self.create_data_info()
		return self.data_info
	
	def reset(self):
		""" Resets cached information about the currently playing
		    track and the queue """
		self.time_lut = None
		self.data_info = None
	
	def update(self, forceRedraw=False):
		""" Overload update to keep track of the updates to allow
		    per-second reloads if we've got countdowns to update """
		if not forceRedraw and not self.time_lut is None and \
				(time.time() - self.last_redraw) > 0.7:
			self.needRedraw = True
		self.last_redraw = time.time()
		ScrollingColsWindow.update(self, forceRedraw)
	
	def touch(self, layout=False, data=False):
		if data:
			self.needDataInfoRecreate = True
		ScrollingColsWindow.touch(self, layout=layout)

class CursesMarietje:
	def __init__(self, host, port, userdir):
		self.running = False
		self.refresh_status = True
		self.statusline = ''
		self.status_shown_once = False
		self.old_query = ''
		self.query = ''
		self.userdir = os.path.expanduser(
				os.path.join('~', userdir))

		self.options = {}
		if not os.path.exists(self.userdir):
			try:
				os.mkdir(self.userdir)
			except Exception, e:
				self.userdir = None
		else:
			fp = os.path.join(self.userdir, 'config')
			if os.path.exists(fp):
				with open(fp) as f:
					self.options = yaml.load(f)
				if self.options is None:
					self.options = dict()
		
		if not 'marietje' in self.options:
			self.options['marietje'] = dict()
		if not 'username' in self.options['marietje']:
			self.options['marietje']['username'] = os.getlogin()

		self.m = Marietje(self.options['marietje']['username'],
				queueCb=self.on_queue_fetched,
				songCb=self.on_songs_fetched,
				playingCb=self.on_playing_fetched,
				host=host,
				port=port)
		self.l = logging.getLogger('CursesMarietje')

		if not self.userdir is None:
			fp = os.path.join(self.userdir, 'songs-cache')
			if os.path.exists(fp):
				try:
					with open(fp) as f:
						self.m.songs_from_cache(f)
				except Exception, e:
					self.l.exception("Exception while "+
						"reading cache")
					# We silently assume self.m is in a
					# consistent state in exception.
	
	def refetch(self, fetchSongs=True, fetchQueue=True,
			  fetchPlaying=True, force=False):
		""" If all requested are fetched, refetch them. If some of
		    them are not fetched, fetch only those. """
		if force:
			pass
	    	elif (not fetchPlaying or self.m.playing_fetched or \
				self.m.playing_fetching) and \
		   (not fetchSongs or self.m.songs_fetched or \
		   		self.m.songs_fetching) and \
		   (not fetchQueue or self.m.queue_fetched or \
		   		self.m.queue_fetching):
			fetchPlaying = fetchPlaying and \
					not self.m.playing_fetching
			fetchSongs = fetchSongs and \
					not self.m.songs_fetching
			fetchQueue = fetchQueue and \
					not self.m.queue_fetching
			self.set_status("Refetching %s" % format_list(
				(('playing',) if fetchPlaying else ()) +
				(('songs',) if fetchSongs else ()) +
				(('queue',) if fetchQueue else ())))
		else:
			fetchPlaying = not self.m.playing_fetched and \
					not self.m.playing_fetching
			fetchSongs = not self.m.songs_fetched and \
					not self.m.songs_fetching
			fetchQueue = not self.m.queue_fetched and \
					not self.m.queue_fetching
			self.set_status("Fetching %s" % format_list(
				(('playing',) if fetchPlaying else ()) +
				(('songs',) if fetchSongs else ()) +
				(('queue',) if fetchQueue else ())))

		self.update_timeout = True
		self.timeout = INITIAL_TIMEOUT
		self.m.start_fetch(fetchSongs=fetchSongs,
				   fetchPlaying=fetchPlaying,
				   fetchQueue=fetchQueue)
		self.queue_main.reset()

	def set_status(self, value):
		self.l.info(value)
		self.statusline = value
		self.refresh_status = True
		self.status_shown_once = False

	def run(self):
		self.log = StringIO()
		logging.basicConfig(stream=self.log,
				    level=logging.DEBUG,
				    format="%(asctime)s:%(levelname)s:"+
				    "%(name)s:%(levelname)s:%(message)s")
		self._been_setup = False
		self.running = True
		while self.running:
			curses.wrapper(self._inside_curses)
		if not self.userdir is None:
			with open(os.path.join(self.userdir,
					'config'), 'w') as f:
				self.options = yaml.dump(self.options, f)
			with open(os.path.join(self.userdir, 
					'songs-cache'), 'w') as f:
				self.m.cache_songs_to(f)
	
	def _inside_curses(self, window):
		if not self._been_setup:
			self._setup(window)
			self._been_setup = True
		self._main_loop()

	def _setup(self, window):
		curses_use_default_colors()
		curses_init_pair(CP_BLUE, curses.COLOR_BLUE, -1)
		curses_init_pair(CP_GREEN, curses.COLOR_GREEN, -1)
		curses_init_pair(CP_RED, curses.COLOR_RED, -1)
		curses_init_pair(CP_CWHITE, curses.COLOR_BLACK,
				  	    curses.COLOR_WHITE)
		curses_init_pair(CP_CBLUE, curses.COLOR_BLUE,
					   curses.COLOR_WHITE)
		curses_init_pair(CP_CGREEN, curses.COLOR_GREEN,
					    curses.COLOR_WHITE)
		curses_init_pair(CP_CRED, curses.COLOR_RED,
					  curses.COLOR_WHITE)

		self.window = window
		h,w = self.window.getmaxyx()
		self.queue_main = QueueWindow(self.window.derwin(h-1,w,0,0),
					self.m)
		if not 'search-window' in self.options:
			self.options['search-window'] = dict()
		if not 'highlight' in self.options['search-window']:
			self.options['search-window']['highlight'] = True
		self.search_main = SearchWindow(self.window.derwin(h-1,w,0,0),
					self.m, highlight=self.options[
						'search-window']['highlight'])
		self.status_w = self.window.derwin(1, w, h-1, 0)
		self.main = self.queue_main
		self.refetch(force=True)
	
	def _main_loop(self):
		window = self.window
		h,w = self.window.getmaxyx()
		while True:
			if self.update_timeout:
				self.update_timeout = False
				window.timeout(self.timeout)
			try:
				k = window.getch()
			except KeyboardInterrupt:
				self.running = False
				break
			forceRedraw = False
			if k == -1:
				pass
			elif k == 27:
				window.timeout(0)
				try:
					try:
						k = window.getch()
					except KeyboardInterrupt:
						self.running = False
						break
					if k == -1:
						if len(self.query) != 0:
							self.query = ''
						pass
					elif k == ord('x'):
						self.running = False
						break
					elif k == ord('r'):
						forceRedraw = True
					elif k == ord('R'):
						self.window.redrawwin()
						forceRedraw = True
					elif k == ord('f'):
						self.refetch(fetchSongs=False)
					elif k == ord('F'):
						self.refetch()
					elif k == ord('?'):
						self.show_help()
						# We break the main loop, which
						# is then reentered via
						# curses.wrapper
						break
					elif k == ord('a'):
						self.query = '*'
				finally:
					window.timeout(self.timeout)
			elif k == 410: # redraw
				h, w = self.window.getmaxyx()
				self.queue_main.w.resize(h-1,w)
				self.queue_main.touch()
				self.status_w.resize(1,w)
				self.status_w.mvwin(h-1, 0)
				self.refresh_status = True
			elif k == 262: # home
				self.main.scroll_home()
				self.refresh_status = True
			elif k == 360: # end
				self.main.scroll_end()
				self.refresh_status = True
			elif k == 339: # page up
				self.main.scroll_page_up()
				self.refresh_status = True
			elif k == 338: # page down
				self.main.scroll_page_down()
				self.refresh_status = True
			elif k == 261: # right
				self.main.scroll_right()
				self.refresh_status = True
			elif k == 260: # left
				self.main.scroll_left()
				self.refresh_status = True
			elif k == 259: # up
				self.main.scroll_up()
				self.refresh_status = True
			elif k == 258: # down
				self.main.scroll_down()
				self.refresh_status = True
			elif k == ord('?'):
				self.show_help()
				# We break the main loop, which
				# is then reentered via
				# curses.wrapper
				break
			elif k == 263 or k == 127: # backspace
				if len(self.query) != 0:
					self.query = self.query[:-1]
			elif k == 23: # C-w
				if len(self.query) != 0:
					idx = self.query.rfind(' ', 0,
							len(self.query)-1)
					if idx == -1:
						self.query = ''
					else:
						self.query = self.query[:idx+1]
			elif k == 21: # C-u
				if len(self.query) != 0:
					self.query = ''
			elif k == 20: # C-t
				if len(self.query) >= 2:
					self.query = (self.query[:-2] +
						      self.query[-1] +
						      self.query[-2])
			elif self.main is self.search_main and  k == 10: # RET
				try:
					self.search_main.request_track()
				except MarietjeException, e:
					self.l.exception("Exception while "+
							"requesting track")
					self.set_status(str(e))
				self.refetch(fetchSongs=False)
				self.query = ''
			elif 0 < k and k < 128 and \
					chr(k).lower() in self.m.cs_lut:
				self.query += chr(k).lower()
			else:
				self.set_status((
					'Unknown key (%s). Press '+
					'Alt+x to quit, Alt+? for help') % k)
			if self.main is self.queue_main \
					and len(self.query) != 0:
				self.main = self.search_main
				self.main.touch()
			elif self.main is self.search_main \
					and len(self.query) == 0:
				self.main = self.queue_main
				self.main.touch()
			
			if self.main is self.queue_main:
				if self.m.playing_fetched and \
						time.time() > self.m.queueOffsetTime:
					self.refetch(fetchSongs=False)
			if self.query != self.old_query:
				if len(self.query) > 1 and self.query[0] == '*':
					self.query = self.query[1:]
				self.old_query = self.query
				self.refresh_status = True
				if self.main is self.search_main:
					self.search_main.set_query(self.query)
					self.search_main.touch(layout=True)
				
			self.main.update(forceRedraw=forceRedraw)
			self.update_status(forceRedraw=forceRedraw)
			curses.doupdate()

	def _status_attr(self, fetching, fetched):
		ret = 0
		if fetched:
			ret |= curses.A_BOLD
			if fetching:
				ret |= curses_color_pair(CP_GREEN)
		else:
			if fetching:
				ret |= curses_color_pair(CP_GREEN)
			else:
				ret |= curses_color_pair(CP_RED)
		return ret

	def update_status(self, forceRedraw):
		if not self.refresh_status and not forceRedraw:
			return
		h, w = self.status_w.getmaxyx()
		self.refresh_status = False
		self.status_w.clear()
		pos = '%s-%s|%s' % self.main.get_view_region()
		if len(pos) < w:
			self.status_w.addstr(0, w-len(pos)-1, pos)
		if self.query == '' or not self.status_shown_once:
			self.status_shown_once = True
			if self.query != '': self.refresh_status = True
			self.status_w.addch(0, 0, 'Q', self._status_attr(
				self.m.queue_fetching, self.m.queue_fetched))
			self.status_w.addch(0, 1, 'P', self._status_attr(
				self.m.playing_fetching, self.m.playing_fetched))
			self.status_w.addch(0, 2, 'S', self._status_attr(
				self.m.songs_fetching, self.m.songs_fetched))
			self.status_w.addstr(0, 4, self.statusline[:w-5])
		else:
			self.status_w.addstr(0, 0, self.query[:w-1], curses.A_BOLD)
		self.status_w.noutrefresh()

	def on_queue_fetched(self):
		if not self.m.queue_fetched:
			self.set_status("Queue fetch failed: %s" % \
					str(self.m.qException))
			return
		if not(self.m.songs_fetching or self.m.playing_fetching):
			self.timeout = DEFAULT_TIMEOUT
			self.update_timeout = True
		self.queue_main.touch(layout=True, data=True)
		self.set_status("Queue in %s" % self.m.qLoadTime)

	def on_songs_fetched(self, from_cache=False):
		if not self.running:
			return
		if not self.m.songs_fetched:
			self.set_status("Songs fetch failed: %s" % \
					str(self.m.sException))
			return
		if not(self.m.queue_fetching or self.m.playing_fetching):
			self.timeout = DEFAULT_TIMEOUT
			self.update_timeout = True
		self.queue_main.touch(layout=True, data=True)
		if from_cache:
			self.set_status("Songs (cache) in %s" % self.m.sCacheLoadTime)
		else:
			if not hasattr(self.m, 'sLoadTime'): return
			self.set_status("Songs in %s" % self.m.sLoadTime)
	
	def on_playing_fetched(self):
		if not self.m.playing_fetched:
			self.set_status("Playing fetch failed: %s" % \
					str(self.m.pException))
			return
		if not(self.m.songs_fetching or self.m.queue_fetching):
			self.timeout = DEFAULT_TIMEOUT
			self.update_timeout = True
		self.queue_main.touch(layout=True, data=True)
		self.set_status("Playing in %s" % self.m.pLoadTime)
	
	def show_help(self):
		less = subprocess.Popen(['less', '-c'], stdin=subprocess.PIPE)
		less.stdin.write((" Curses based Python Marietje client %(version)s\n"+
				  "      (c) 2008, 2009 - Bas Westerbaan, 99BA289B\n"+
				  "\n"+
				  " Alt+f  refetch some     Alt+F  refetch all\n"+
				  " Alt+r  refresh screen   Alt+R  refresh screen harder\n"+
				  " Alt+x  quit             Alt+?  guess!\n"+
				  " Ctrl+u clear query      Ctrl+w only the last word\n"+
				  " Alt+a  list all songs   Ctrl+t transpose last two chars\n"+
				  "\n"+
				  "RUNTIME\n"+
				  "  Load times\n"+
				  "    songs        %(slt)s\n"+
				  "    songs cache  %(clt)s\n"+
				  "    songs lut    %(llt)s\n"+
				  "    queue        %(qlt)s\n"+
				  "    now playing  %(plt)s\n"+
				  "\n"+
				  "LOG\n"+
				  "%(log)s") % {
		       'version': VERSION,
		       'qlt': self.m.qLoadTime if hasattr(self.m, 'qLoadTime') else 'n/a',
		       'slt': self.m.sLoadTime if hasattr(self.m, 'sLoadTime') else 'n/a',
		       'llt': self.m.sLutGenTime if hasattr(self.m, 'sLutGenTime') else 'n/a',
		       'plt': self.m.pLoadTime if hasattr(self.m, 'pLoadTime') else 'n/a',
		       'clt': self.m.sCacheLoadTime if hasattr(self.m, 'sCacheLoadTime') else 'n/a',
		       'log': self.log.getvalue()
					       })
		less.stdin.close()
		less.wait()
		
def main():
	parser = optparse.OptionParser()
	parser.add_option('-H', '--host', dest='host',
			  default='zuidslet.science.ru.nl',
			  help="Connect to HOST", metavar='HOST')
	parser.add_option('-p', '--port', dest='port',
			  default='1337', type='int',
			  help="Connect on PORT", metavar='PORT')
	parser.add_option('-u', '--userdir', dest='userdir',
			  default='.pymarietje',
			  help="Use PATH as userdir", metavar='PATH')
	(options, args) = parser.parse_args()

	os.environ['ESCDELAY'] = "0";

	m = CursesMarietje(host=options.host,
			   port=options.port,
			   userdir=options.userdir)
	try:
		m.run()
	except Exception, e:
		logging.exception('Uncatched exception')
		if hasattr(m, 'log'):
			print m.log.getvalue()
		else:
			print e
	sys.exit(0)

if __name__ == '__main__':
	main()
