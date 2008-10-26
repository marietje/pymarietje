import os
import sys
import time
from eyeD3 import Tag
from marietje import RawMarietje
from optparse import OptionParser

if __name__ == '__main__':
	usage = "usage: %prog [options] file-name"
	parser = OptionParser(usage=usage)

	parser.add_option("-a", "--artist", dest="artist", default=None,
			help="Track ARTIST", metavar="ARTIST")
	parser.add_option("-t", "--title", dest="title", default=None,
			help="Track TITLE", metavar="TITLE")
	parser.add_option("-u", "--username", dest="username", default=None,
			help="Upload as USERNAME", metavar="USERNAME")
	parser.add_option("-H", "--host", dest="host",
			default="devslet.sci.kun.nl",
			help="Upload to HOST", metavar="HOST")
	parser.add_option("-p", "--port", dest="port", default=1337, type=int,
			help="Upload on PORT", metavar="PORT")
	parser.add_option("-f", "--force", dest="force", action="store_true",
			help="Don't ask confirmation")
	parser.add_option("-q", "--quiet", dest="quiet", action="store_true",
			help="Be quiet, implies force")

	(options, args) = parser.parse_args()

	if len(args) == 0:
		parser.print_usage()
		sys.exit(-1)
	
	if options.quiet:
		options.force = True
	
	fn = args[0]
	tag = Tag()
	tag.link(fn)
	if options.artist is None:
		options.artist = tag.getArtist()
	else:
		if options.artist != tag.getArtist() and not options.quiet:
			print "warning: %s (input) != %s (tag)" % (
					options.artist, tag.getArtist())

	if options.title is None:
		options.title = tag.getTitle()
	else:
		if options.title != tag.getTitle() and not options.quiet:
			print "warning: %s (input) != %s (tag)" % (
					options.title, tag.getTitle())
	
	if options.username is None:
		options.username = os.getlogin()
	else:
		if options.username != os.getlogin() and not options.quiet:
			print "warning: %s (input) != %s (system)" % (
					options.username, os.getlogin())
	
	if not options.force:
		print ("Will upload as %s\n"+
		       " %s\n"+
		       "as\n"+
		       " %s - %s\n"+
		       "Are you sure? (press enter)") % (
				options.username, fn,  options.artist,
				options.title),
		c = sys.stdin.read(1)

	m = RawMarietje(options.host, options.port)
	size = os.stat(fn).st_size
	f = open(fn)
	start_time = time.time()
	m.upload_track(options.artist, options.title,
			options.username, size, f)
	dur = time.time() - start_time
	f.close()
	if not options.quiet:
		print "Finished in %ss: %sMB/s" % (
				dur, size / dur / 1024 / 1024)
