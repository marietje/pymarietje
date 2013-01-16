from pprint import pformat

from mirte.core import Module
from joyce.base import JoyceChannel
from sarah.event import Event, ConditionalEvent

class SONWrapper(object):
    def __init__(self, data):
        self._data = data

def son_property(path, default=None, readonly=True, getter=None, setter=None):
    """ A convenience shortcut to create properties on SONWrapper
        subclasses.  Will return a getter/setter property that
        gets/sets self._data[path[0]]...[path[-1]] verbatim. """
    def __getter(self):
        obj = self._data
        for bit in path[:-1]:
            obj = obj.get(bit, {})
        tmp = obj.get(path[-1], default)
        if getter is None:
            return tmp
        return getter(tmp)
    if readonly:
        return property(__getter)
    def __setter(self, x):
        obj = self._data
        for bit in path[:-1]:
            if not bit in obj:
                obj[bit] = {}
            obj = obj[bit]
        if setter is not None:
            x = setter(x)
        obj[path[-1]] = x
    return property(__getter, __setter)

class MarietjeRequest(SONWrapper):
    key = son_property(('key',))
    byKey = son_property(('byKey',))
    media = son_property(('byKey',),
            getter=lambda x: MarietjeMedia(x))

class MarietjeMedia(SONWrapper):
    key = son_property(('key',))
    artist = son_property(('artist',))
    title = son_property(('title',))
    uploadedByKey = son_property(('uploadedByKey',))
    length = son_property(('length',))

class MarietjePlaying(SONWrapper):
    byKey = son_property(('byKey',))
    media = son_property(('byKey',),
            getter=lambda x: MarietjeMedia(x))
    endTime = son_property(('localEndTime',))

class MarietjeClientChannel(JoyceChannel):
    def __init__(self, server, *args, **kwargs):
        super(MarietjeClientChannel, self).__init__(*args, **kwargs)
        self.s = server
        self.l = self.s.l
        self.msg_map = {
                'welcome': self.msg_welcome,
                'requests': self.msg_requests,
                'playing': self.msg_playing,
                }
    def handle_message(self, data):
        typ = data.get('type')
        if typ in self.msg_map:
            self.msg_map[typ](data)
        else:
            self.l.warn('Unknown message type: %s' % repr(typ))
    def msg_welcome(self, data):
        self.l.info("Welcome %s" % pformat(data))
    def msg_playing(self, data):
        self.s.on_playing_changed(
                MarietjePlaying(data['playing']))
    def msg_requests(self, data):
        self.s.on_requests_changed(
                [MarietjeRequest(r) for r in data['requests']])
class MarietjeClient(Module):
    """ Client for Marietje. """
    def __init__(self, settings, l):
        super(MarietjeClient, self).__init__(settings, l)
        def _channel_class(*args, **kwargs):
            return MarietjeClientChannel(self, *args, **kwargs)
        self.channel = self.joyceClient.create_channel(
                channel_class=_channel_class)
        self.on_playing_changed = ConditionalEvent(
                lambda: self._follow('playing'),
                lambda: self._unfollow('playing'))
        self.on_requests_changed = ConditionalEvent(
                lambda: self._follow('requests'),
                lambda: self._unfollow('requests'))
    def _follow(self, *args):
        self.channel.send_message({'type': 'follow',
                                   'which': args})
    def _unfollow(self, *args):
        self.channel.send_message({'type': 'unfollow',
                                   'which': args})

# vim: et:sta:bs=2:sw=4:
