import threading

from mirte.core import Module

class MarietjeCursesUI(Module):
    def __init__(self, settings, l):
        super(MarietjeCursesUI, self).__init__(settings, l)
    def run(self):
        self.client.on_playing_changed.register(self.on_playing_changed)
        self.client.on_requests_changed.register(self.on_requests_changed)
    def on_playing_changed(self, playing):
        pass
    def on_requests_changed(self, requests):
        pass


# vim: et:sta:bs=2:sw=4
