import os
import curses
import collections

class FocusSource:
    """ Used by Widget.direct_focus. """

    # Widget is directly focused.
    DIRECT = 0

    # Came down from parent.
    PARENT = 1

    # Came up from child.
    CHILD = 2

    # Came from a kin.
    KIN = 3

class FocusDirective:
    """ Returned by Widget.direct_focus. """

    # Acccept focus
    ACCEPT = 0

    # Reject focus
    REJECT = 1

    # Pass focus up or down
    PASS = 2

_Position = collections.namedtuple('Position',
                    ('row', 'column'))

class Position(_Position):
    """ Represents a position on the screen. """
    def __sub__(self, other):
        """ Returns the pointwise difference.

            >>> Position(1,2) - Position(3,4)
            Position(row=-2, column=-2)
            """
        return Position(self.row - other.row,
                        self.column - other.column)
    
    def __add__(self, other):
        """ Returns the pointwise sum.

            >>> Position(1,2) + Position(3,4)
            Position(row=4, column=6)
            """
        return Position(other.row + self.row,
                        other.column + self.column)

_Rectangle = collections.namedtuple('Rectangle',
                    ('row', 'column', 'height', 'width'))

class Rectangle(_Rectangle):
    """ Represents a rectangle on screen. """
    @staticmethod
    def fps(pos, size):
        """ Creates a new Rectangle quadrupel from a Position and Size object.

            >>> Rectangle.fps(Position(1,2), Size(3,4))
            Rectangle(row=1, column=2, height=3, width=4)
            """
        return Rectangle(pos.row, pos.column, size.height, size.width)

    @property
    def pos(self):
        """ Gets the position of the rectangle.

            >>> Rectangle(1,2,3,4).pos
            Position(row=1, column=2)
            """
        return Position(self.row, self.column)

    @property
    def size(self):
        """ Gets the size of the rectangle.

            >>> Rectangle(1,2,3,4).size
            Size(height=3, width=4)
            """
        return Size(self.height, self.width)

    def refine(self, other):
        """ Splits this rectangle into subrectangles, such that if
            this and the <other> rectangle have an intersection, it
            will be among the subrectangles.

            If the other rectangle is completely inside and separate from
            this rectangle, the rectangle will be split in five subrectangles
            as in the first figure.

            +--+---+-----+   +------------+     +------+
            |  1   |     |   |     1      |     |      |
            +--+---+     |   +--+---------+--+  |      |
            |  |   |  2  |   |  |         |  |  |  1   |
            |  | 5 |     |   |  |         |  |  |      |
            |4 |   |     |   |4 |   5     |  |  |      |
            |  +---+-----+   |  |         |  |  +------+
            |  |   3     |   |  |         |  |
            |  |         |   |  |         |  |            +--+
            +--+---+-----+   +--+---------+  |            |  |
                                |            |            +--+
                                +------------+

            If the other rectangle only intersects this rectangle, some of
            the subrectangles will vanish (as in the second figure).

            If the other rectangle is disjoint from this, this rectangle
            is returned.

            >>> R = Rectangle
            >>> assert R(0,0,9,13).refine(R(11,16,2,3)) == \
                    [R(0,0,9,13)]
            >>> assert R(0,0,9,13).refine(R(2,3,9,13)) == \
                    [R(0,0,2,13), R(2,0,7,3), R(2,3,7,10)]
            >>> assert R(0,0,9,13).refine(R(2,3,4,4)) == \
                    [R(0,0,2,7), R(0,7,6,6), R(6,3,3,10), \
                        R(2,0,7,3), R(2,3,4,4)]
            """
        intersection = self.intersect(other)
        if intersection is None:
            return [self]
        r1 = Rectangle(self.row,
                       self.column,
                       intersection.row - self.row,
                       intersection.column - self.column + intersection.width)
        r2 = Rectangle(self.row,
                       intersection.column + intersection.width,
                       intersection.row - self.row + intersection.height,
                       self.width - r1.width)
        r4 = Rectangle(intersection.row,
                       self.column,
                       self.height - r1.height,
                       intersection.column - self.column)
        r3 = Rectangle(intersection.row + intersection.height,
                       intersection.column,
                       self.height - r2.height,
                       self.width - r4.width)
        return filter(bool, [r1, r2, r3, r4, intersection])

    def intersect(self, other):
        """ Returns the intersection of this rectangle with <other> or None
            if there is not any.

            >>> Rectangle(1,1,1,1).intersect(Rectangle(0,0,2,2))
            Rectangle(row=1, column=1, height=1, width=1)
            >>> Rectangle(0,0,2,2).intersect(Rectangle(0,1,1,2))
            Rectangle(row=0, column=1, height=1, width=1)
            >>> assert Rectangle(0,0,1,1).intersect(Rectangle(1,1,1,1)) is None
            """
        column = min(max(other.column, self.column), self.column + self.width)
        width = min(max(other.column + other.width, self.column),
                            self.column + self.width) - column
        if not width:
            return None
        row = min(max(other.row, self.row), self.row + self.height)
        height = min(max(other.row + other.height, self.row),
                            self.row + self.height) - row
        if not height:
            return None
        return Rectangle(row, column, height, width)

    def __sub__(self, other):
        """ Returns the difference rectangle between this rectangle and
            the <other>.

            >>> Rectangle(1,2,3,4) - Rectangle(4,3,2,1)
            Rectangle(row=-3, column=-1, height=1, width=3)
            """
        return Rectangle(self.row - other.row,
                         self.column - other.column,
                         self.height - other.height,
                         self.width - other.width)
    
    def __add__(self, other):
        """ Returns the sum of this rectangle with <other>.

            The position vectors and the size vectors are summed.

            >>> Rectangle(1,2,3,4) + Rectangle(4,3,2,1)
            Rectangle(row=5, column=5, height=5, width=5)
            """
        return Rectangle(self.row + other.row,
                         self.column + other.column,
                         self.height + other.height,
                         self.width + other.width)

    def __nonzero__(self):
        """ Returns whether the rectangle has a non-zero area.
        
            >>> bool(Rectangle(1, 2, 0, 4))
            False
            >>> bool(Rectangle(1, 2, 3, 0))
            False
            >>> bool(Rectangle(1, 2, 3, 4))
            True
            """
        return self.width and self.height

Size = collections.namedtuple('Size',
                    ('height', 'width'))
MappingEntry = collections.namedtuple('MappingEntry',
                    ('source', 'target', 'widget'))
WidgetRectangle = collections.namedtuple('WidgetRectangle',
                    ('widget', 'rect'))
RenderDirective = collections.namedtuple('RenderDirective',
                    ('source', 'target'))

class Mapping(object):
    """ Represents the mapping of screen estate of a widget to its children.

        It consists of a list of triples.  If (source, target, widget) is in
        the list, the Rectangle <source> is rendered by rendering the
        rectangle of the same size at Position <target> of the Widget <widget>.

        If <widget> is None, the parent widget is responsible for rendering
        the <source> rectangle. """
    def __init__(self, entries=None):
        self.entries = [] if entries is None else entries
    def __iter__(self):
        return iter(self.entries)
    def restrict_image(self, widgetRects):
        """ Given a list of pairs of widgets and rectangles, returns a smaller
            mapping which image is restricted to the given widgets and
            rectangles. """
        ret = []
        # Create a l.u.t. from widgets in widgetRects to their rectangles.
        widget_to_rects = dict()
        for wr in widgetRects:
            if not wr.widget in widget_to_rects:
                widget_to_rects[wr.widget] = []
            widget_to_rects[wr.widget].append(wr.rect)
        # Check for intersections with entries
        for entry in self.entries:
            target_rect = Rectangle(entry.target.row,
                                    entry.target.column,
                                    entry.source.height,
                                    entry.source.width)
            if not entry.widget in widget_to_rects:
                continue
            # XXX Add quadtrees to find intersections more efficiently?
            for rect in widget_to_rects[entry.widget]:
                intersection =  rect.intersect(target_rect)
                if not intersection:
                    continue
                intersection_orig = (entry.source - target_rect) + intersection
                ret.append(MappingEntry(source=intersection_orig,
                                        target=intersection.pos,
                                        widget=entry.widget))
        return Mapping(ret)

    def unfolded(self):
        """ Returns an unfolded copy of the mapping. """
        # XXX Is caching this worth it?
        stack = list(self.entries)
        ret = []
        while stack:
            entry = stack.pop()
            target_rect = Rectangle(entry.target.row,
                                    entry.target.column,
                                    entry.source.height,
                                    entry.source.width)
            if entry.widget.mapping is None:
                ret.append(entry)
                continue
            # XXX Add quadtrees to find intersections more efficiently?
            for entry2 in entry.widget.mapping:
                intersection = entry2.source.intersect(target_rect)
                if intersection is None:
                    continue
                intersection_orig = (entry.source - target_rect) + intersection
                intersection_img = Rectangle(entry2.target.row,
                                             entry2.target.column,
                                             0, 0) + intersection
                if entry2.widget is None:
                    ret.append(MappingEntry(source=intersection_orig,
                                            target=intersection_img.pos,
                                            widget=entry.widget))
                    continue
                stack.append(MappingEntry(source=intersection_orig,
                                          target=intersection_img.pos,
                                          widget=entry2.widget))
        return Mapping(ret)

    def extend(self, mapping):
        """ Extends this mapping with <mapping>.

            If a point is in the original domain, the original mapping will be
            used.  If a point is not in the original domain, but in the domain
            of <mapping>, then <mapping> will be used.

            >>> R, M, E, P = Rectangle, Mapping, MappingEntry, Position
            >>> m1 = M([E(R(0,0,5,5),P(1,1),1), \
                        E(R(0,7,2,2),P(6,0),2), \
                        E(R(7,0,2,2),P(0,6),3)])
            >>> m2 = M([E(R(2,3,4,5),P(2,2),4), \
                        E(R(7,7,2,2),P(6,0),5), \
                        E(R(7,0,2,2),P(9,9),6)])
            >>> m2.extend(m1)
            >>> assert m2 == M([E(R(0,0,2,5),P(1,1),1), \
                                E(R(2,0,3,3),P(3,1),1), \
                                E(R(0,7,2,2),P(6,0),2), \
                                E(R(2,3,4,5),P(2,2),4), \
                                E(R(7,7,2,2),P(6,0),5), \
                                E(R(7,0,2,2),P(9,9),6)])
            """
        self.entries.extend(mapping - self)

    def __sub__(self, other):
        """ Restricts this mapping to the domain of this mapping with the
            domain of the <other> mapping removed.
            
            >>> R, M, E, P = Rectangle, Mapping, MappingEntry, Position
            >>> m1 = M([E(R(0,0,5,5),P(1,1),1), \
                        E(R(0,7,2,2),P(6,0),2), \
                        E(R(7,0,2,2),P(0,6),3)])
            >>> m2 = M([E(R(2,3,4,5),P(2,2),4), \
                        E(R(7,7,2,2),P(6,0),5), \
                        E(R(7,0,2,2),P(9,9),6)])
            >>> assert m1 - m2 == M([E(R(0,0,2,5),P(1,1),1), \
                                     E(R(2,0,3,3),P(3,1),1), \
                                     E(R(0,7,2,2),P(6,0),2)])
            """
        # XXX Will quadtrees help?
        new_entries = set(self.entries)
        for entry in other:
            to_remove = set()
            to_add = set()
            for entry2 in new_entries:
                if entry2.source == entry.source:
                    to_remove.add(entry2)
                    continue
                subrects = entry2.source.refine(entry.source)
                if len(subrects) == 1:
                    # Since we excluded the case entry2.source == entry.source,
                    # this case only happens when entry2.source and entry.source
                    # are disjunct.
                    continue
                to_remove.add(entry2)
                # subrects[-1] is the intersection of entry2.source with
                # entry.source.
                for subrect in subrects[:-1]:
                    to_add.add(MappingEntry(source=subrect,
                                target=entry2.target +
                                    (subrect - entry2.source).pos,
                                widget=entry2.widget))
            new_entries = new_entries - to_remove | to_add
        return Mapping(list(new_entries))

    def __repr__(self):
        return "<Mapping %s>" % self.entries

    def __eq__(self, other):
        if not isinstance(other, Mapping):
            return NotImplemented
        return frozenset(self.entries) == frozenset(other.entries)

    def __ne__(self, other):
        if not isinstance(other, Mapping):
            return NotImplemented
        return frozenset(self.entries) != frozenset(other.entries)

    def __nonzero__(self):
        """ Returns whether there are any entries. """
        return bool(self.entries)

class Widget(object):
    """ Base class of all widgets. """
    def __init__(self):
        # The screen
        self.screen = None
        # The parent widget
        self.parent = None
        # The size of the widget
        self.size = None
        # Describes which parts of the widget are rendered by the widget itself
        # and which are parts are rendered by the children.  See <Mapping>.
        # If it is None, everything is rendered by the widget itself.
        self.mapping = None
        # The list of children
        self.children = None
        # True if the widget has focus
        self.has_focus = False
        # True if the widget or one of its descendants has fous
        self.in_focus_path = False
    @property
    def preferred_size(self):
        """ The preferred size of the widget.
        
        None signifies that any size will do. """
        return None
    @property
    def minimal_size(self):
        """ The minimal size of the widget to be usable. """
        return Size(0, 0)
    def set_screen(self, screen, recurse=True):
        """ Set the screen to which the widget is attached.
        
            If <recursive> is True, call <set_screen> on all children. """
        self.screen = screen
        if recurse:
            stack = self.children
            while stack:
                widget = stack.pop()
                widget.set_screen(screen, recurse=False)
                if widget.children:
                    stack.extend(widget.children)
    def set_size(self, size):
        """ Set the size of the widget. """
        self.size = size
    def set_parent(self, parent):
        """ Set the parent of the widget. """
        self.parent = parent
    def detach(self):
        """ Detaches the widget. """
        self.set_screen(None)
        self.set_parent(None)
        self.set_size(None)
    def invalidate(self):
        """ Signals the screen, if any is attached, that the widget is
            invalid and needs to be rerendered. """
        if self.screen is None:
            return
        self.screen.invalidate([WidgetRectangle(widget=self,
                    rect=Rectangle.fps(Position(0,0), self.size))], mapped=False)
    def direct_focus(self, source=None):
        """ Returns how the focus should be directed.

            This function is called by Screen to determine how the focus
            should be directed.
        
            If FocusDirective.ACCEPT is returned, this widget will get focus.
            For instance: a control would always accept focus.
            If FocusDirective.REJECT is returned, this widget won't get focus
            For instance: a label will always reject focus.
            If FocusDirective.PASS is returned, this widget will pass the focus
            up to its parent (if source is FocusSource.CHILD) or down to
            its children (if source is anything else).
            For instance: a layout widget will always pass focus.
            """
        return FocusDirective.REJECT
    def on_focus(self):
        """ Called when the widget is assigned focus. """
        self.has_focus = True
    def on_blur(self):
        """ Called when the widget loses focus. """
        self.has_focus = False
    def on_in_focus_path(self):
        """ Called when the widget is in the path of focus. """
        self.in_focus_path = True
    def on_out_focus_path(self):
        """ Called when the widget is out of the path of focus. """
        self.in_focus_path = False
    def on_keypress(self, key):
        """ Called when the widget receives a key-press event.

            If the widget returns False, then this key-press event is passed
            to the parent. """
        return False

class Screen(Widget):
    def __init__(self, windowObject):
        # Contains the curses' window object
        self.wo = windowObject
        # The top widget
        self.topWidget = None
        # Contains top.mapping.unfolded()
        self.unfolded_mapping = Mapping()
        # The submapping of <unfolded_mapping> containing all the invalidated
        # areas.
        self.invalidated = Mapping()
        # True if running
        self.running = False
        # True if <unfolded_mapping> is not up-to-date
        self.mapping_invalidated = True
        # The widget with focus
        self.focused_widget = None

    def render_invalidated(self):
        """ Renders the invalidated areas (if any). """
        if not self.invalidated:
            return
        # Create a widget-to-directives map
        widget_to_rds = {}
        for entry in self.invalidated:
            if not entry.widget in widget_to_rds:
                widget_to_rds[entry.widget] = []
            widget_to_rds[entry.widget].append(
                    RenderDirective(source=Rectangle.fps(entry.target,
                                            Size(entry.source.height,
                                                 entry.source.width)),
                                    target=entry.source.pos))
        # Call the render functions on the widgets
        for widget, rds in widget_to_rds.iteritems():
            widget.render(rds)
        self.invalidated = Mapping()

    def update_mapping(self):
        if self.topWidget is None:
            self.unfolded_mapping = Mapping()
            return
        mapping = Mapping([MappingEntry(
                source=self.whole_screen,
                target=Position(0, 0), widget=self.topWidget)])
        self.unfolded_mapping = mapping.unfolded()
        self.mapping_invalidated = False

    def ancestors(self, widget):
        """ Returns the ancestors of <widget>.
        
            Returns a list of which the first element is <widget>; the last
            element is the top widget and each item the parent of the
            predecessor. """
        ret = []
        cur = widget
        while cur is not None:
            ret.append(cur)
            cur = cur.parent
        return ret

    def _focus(self, widget):
        """ Directly assign focus to <widget> """
        # Get the old and new focus paths
        if self.focused_widget is not None:
            old_focus_path = self.ancestors(self.focused_widget)
            old_focus_path.reverse()
        else:
            old_focus_path = []
        if widget is not None:
            new_focus_path = self.ancestors(widget)
            new_focus_path.reverse()
        else:
            new_focus_path = []
        # Find the fork point
        fork_point = 0
        while (fork_point < min(len(new_focus_path), len(old_focus_path)) and
                old_focus_path[fork_point] is new_focus_path[fork_point]):
            fork_point += 1
        # Set new state
        self.focused_widget = widget
        # Call events
        for i in xrange(fork_point, len(old_focus_path)):
            old_focus_path[i].on_out_focus_path()
        if old_focus_path:
            old_focus_path[-1].on_blur()
        for i in xrange(fork_point, len(new_focus_path)):
            new_focus_path[i].on_in_focus_path()
        if new_focus_path:
            new_focus_path[-1].on_focus()

    def _trigger(self, widget, event, *args, **kwargs):
        """ Call <event> on <widget> with *<args> and **<kwargs>.

            If the widget returns False, will pass the event to the parent. """
        cur = widget
        while cur is not None:
            f = getattr(cur, 'on_' + event)
            if f(*args, **kwargs):
                break
            cur = cur.parent

    # Interface for the user
    # ###############################################################
    @property
    def size(self):
        return Size(*self.wo.getmaxyx())
    @property
    def whole_screen(self):
        return Rectangle.fps(pos=Position(0,0), size=self.size)

    def set_topWidget(self, widget):
        if self.topWidget:
            self.topWidget.detach()
        self.topWidget = widget
        widget.set_parent(None)
        widget.set_screen(self)
        widget.set_size(self.size)
        self.focus(self.topWidget)
        self.invalidate_mapping()
        self.invalidate([WidgetRectangle(widget=self.topWidget,
                                         rect=self.whole_screen)], mapped=True)
    def run(self):
        """ Run the main event loop. """
        self.running = True
        while self.running:
            if self.invalidated:
                if self.mapping_invalidated:
                    self.update_mapping()
                self.render_invalidated()
                self.wo.noutrefresh()
                curses.doupdate()
            key = (self._get_one_key(),)
            if key[0] is None:
                continue
            elif key == (27,):
                k2 = self._get_one_key(direct=True)
                if k2 is not None:
                    key += (k2,)
            self._trigger(self.focused_widget, 'keypress', key)

    def _get_one_key(self, direct=False):
        if direct:
            self.wo.timeout(0)
        c = self.wo.getch()
        if direct:
            self.wo.timeout(-1)
        if c == curses.KEY_RESIZE:
            if self.topWidget is not None:
                self.topWidget.set_size(self.size)
                self.invalidate_mapping()
                self.invalidate([WidgetRectangle(widget=self.topWidget,
                                                 rect=self.whole_screen)],
                                                 mapped=True)
            return
        return None if c == -1 else c
    
    # Interface for widgets
    # ###############################################################
    def invalidate(self, widgetRects, mapped=False):
        """ Invalidates rectangles given by pairs of widget and rectangle.

            If <mapped> is False, the widgets may not map the given
            rectangle to another widget.  If <mapped> is True, this is allowed
            at a performance penalty. """
        if self.mapping_invalidated:
            self.update_mapping()
        if mapped:
            tmpMapping = Mapping([MappingEntry(
                            source=Rectangle.fps(Position(0, 0), wr.rect.size),
                            target=wr.rect.pos,
                            widget=wr.widget) for wr in widgetRects])
            tmpMapping = tmpMapping.unfolded()
            widgetRects = [WidgetRectangle(widget=entry.widget,
                                       rect=Rectangle.fps(entry.target,
                                                          entry.source.size))
                                       for entry in tmpMapping]
        self.invalidated.extend(
                self.unfolded_mapping.restrict_image(widgetRects))

    def invalidate_mapping(self):
        """ Signals that the mapping has changed and thus that the cached
            unfolded mappins should be recalculated. """
        # XXX Add more granularity?
        self.mapping_invalidated = True

    def focus(self, widget):
        """ Assigns focus to <widget> or one of its children. """
        path = [(widget, -1)]
        while path:
            w, index = path[-1]
            if index == -1:
                cur = w
                src = (FocusSource.DIRECT if len(path) == 1
                            else FocusSource.PARENT)
            else:
                if not w.children or len(w.children) <= index:
                    path.pop()
                    continue
                cur = w.children[index]
                src = FocusSource.PARENT if index == 0 else FocusSource.KIN
            directive = cur.direct_focus(src)
            if directive == FocusDirective.ACCEPT:
                self._focus(cur)
                return
            if directive == FocusDirective.REJECT:
                if index == -1:
                    path.pop()
                else:
                    path[-1][1] += 1
                continue
            assert directive == FocusDirective.PASS
            if index == -1:
                path[-1][1] = 0
            else:
                path.append((cur, 0))
        self._focus(None)

class ScrollingTextWidget(Widget):
    """ Multi-line scrolling text widget """

    def __init__(self):
        self.lines = []
        self.max_line = 
        super(ScrollingTextWidget, self).__init__()
    @property
    def preferred_size

class LabelWidget(Widget):
    """ A one-line label. """
    def __init__(self, text=''):
        self.text = text
        super(LabelWidget, self).__init__()
    @property
    def preferred_size(self):
        return Size(1, len(self.text))
    def set_text(self, text):
        self.text = text
        self.invalidate()
    def render(self, directives):
        for dv in directives:
            for y in xrange(dv.source.height):
                if y == 0 and dv.source.row == 0:
                    self.screen.wo.addstr(y, dv.source.column,
                            self.text[dv.source.column:].ljust(dv.source.width))
                    continue
                self.screen.wo.hline(y + dv.target.row, dv.target.column,
                                    ' ', dv.source.width)

class ConstantWidget(Widget):
    def __init__(self, ch='*'):
        if len(ch) != 1:
            raise ValueError("<ch> should be a single character string")
        self.ch = ch
        super(ConstantWidget, self).__init__()
    def render(self, directives):
        for dv in directives:
            for y in xrange(dv.source.height):
                self.screen.wo.hline(y + dv.target.row, dv.target.column,
                                     self.ch, dv.source.width)

class BufferedWidget(Widget):
    def __init__(self):
        super(BufferedWidget, self).__init__()
        # The off-screen buffer
        self.pad = None
    def set_size(self, size):
        old_size = self.size
        super(BufferedWidget, self).set_size(size)
        if size != old_size:
            if size is None:
                self.pad is None
            else:
                self.pad = curses.newpad(size.height, size.width)
    def render(self, directives):
        for dv in directives:
            self.pad.noutrefresh(dv.source.row,
                                 dv.source.column,
                                 dv.target.row,
                                 dv.target.column,
                                 dv.target.row + dv.source.height,
                                 dv.target.column + dv.source.width)


def wrapper(func, *args, **kwargs):
    os.environ['ESCDELAY'] = '25'
    def trampoline(so):
        screen = Screen(so)
        func(screen, *args, **kwargs)
    curses.wrapper(trampoline)

if __name__ == '__main__':
    #import doctest
    #doctest.testmod()
    class MyLabel(LabelWidget):
        def direct_focus(self, source):
            return FocusDirective.ACCEPT
        def on_keypress(self, key):
            self.set_text(repr(key))
    def inside_curses(screen):
        while True:
            screen.set_topWidget(MyLabel('This is a test'))
            screen.run()
    wrapper(inside_curses)

# vim: et:sta:bs=2:sw=4
