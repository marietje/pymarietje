import logging
import argparse
import threading

import mirte
import mirte.main
import mirte.mirteFile
import sarah.coloredLogging

class Launcher(object):
    def __init__(self):
        self.sleep_event = threading.Event()

    def parse_args(self):
        parser = argparse.ArgumentParser()
        parser.add_argument('--verbose', '-v', action='count', dest='verbosity')
        parser.add_argument('--host', '-H', type=str, default='localhost')
        parser.add_argument('--port', '-p', type=int, default=8080)
        parser.add_argument('--path', '-P', type=str, default='/')
        self.args = parser.parse_args()

    def main(self):
        self.parse_args()
        if self.args.verbosity >= 1:
            sarah.coloredLogging.basicConfig(level=logging.DEBUG,
                                formatter=mirte.main.MirteFormatter())
        self.mirte_manager = m = mirte.get_a_manager()
        mirte.mirteFile.load_mirteFile('marietje/cursesui', m)
        mirte.mirteFile.load_mirteFile('joyce/comet', m)
        self.joyceClient = m.create_instance('joyceClient', 'cometJoyceClient',
                                        {'host': self.args.host,
                                         'port': self.args.port,
                                         'path': self.args.path})
        self.client = m.create_instance('marietjeClient', 'marietjeClient',
                                        {'joyceClient': 'joyceClient'})
        self.ui = m.create_instance('ui', 'marietjeCursesUI',
                                        {'client': 'marietjeClient'})
        self.sleep_event.wait()

if __name__ == '__main__':
    Launcher().main()

# vim: et:sta:bs=2:sw=4:
