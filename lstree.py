import time

class LSTree(object):
	""" Base class ofa Live Search Tree """

	def __init__(self, entries):
		""" Creates a LS Tree
			@entries	List of (text, obj) pairs
		"""
		raise NotImplemented

	def query(self, q):
		""" Finds all entries (text, obj) with q in text and returns
		    the obj's. """
		raise NotImplemented

class SimpleCachingLSTree(LSTree):
	""" Simple implementation of LSTree, which caches """

	def __init__(self, entries, max_cache=1000, nom_cache=750):
		""" Creates a LS Tree
			@entries	List of (text, obj) pairs
			@max_cache	Maximum amount of cache entries
			@nom_cache	When maximum cache size is reached,
					evict entries up to @nom_cache
		"""
		self.cache = dict()
		self.cache[''] =  [time.time(), 0.0, entries]
		self.max_cache = max_cache
		self.nom_cache = nom_cache
	
	def query(self, q):
		for i in xrange(0, len(q)+1):
			if i == 0:
				if q in self.cache:
					break
				continue
			if not q[:-i] in self.cache:
				continue
			self.cache[q] = [time.time(), None, list()]
			start = time.time()
			for txt, obj in self.cache[q[:-i]][2]:
				if q in txt:
					self.cache[q][2].append((txt, obj))
			self.cache[q][1] = time.time() - start
		self.cache[q][0] = time.time()
		for txt, obj in self.cache[q][2]:
			yield obj
		
