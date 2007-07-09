#
# This file is part of Advene.
#
# Advene is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# Advene is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Foobar; if not, write to the Free Software
# Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA  02110-1301  USA
#
import advene.core.config as config

import re
import gtk
import StringIO
import os
import urllib

from gettext import gettext as _

import xml.dom.DOMImplementation

from advene.model.content import Content
from advene.model.view import View
import advene.gui.util
import advene.util.helper as helper

import advene.util.ElementTree as ET

class AdhocView(object):
    """Implementation of the generic parts of AdhocViews.

    For details about the API of adhoc views, see gui.views.viewplugin.
    """
    view_name = "Generic adhoc view"
    view_id = 'generic'
    tooltip = "This view is a generic abstract view that should be derived by real views."

    def __init__(self, controller=None, parameters=None):
        """
        """
        # List of couples (label, action) that are use to
        # generate contextual actions
        self.contextual_actions = ()

        # Dictionary of view-specific options.
        self.options = {}

        # If True, the view should be closed when loading a new package.
        # Else, it can respond to a package load and update
        # itself accordingly (through the update_model method).
        self.close_on_package_load = True

        self.controller = controller
        # If self.buttonbox exists, then the widget has already
        # defined its own buttonbox, and the generic popup method
        # can but the "Close" button in it:
        # self.buttonbox = gtk.HButtonBox()

        if parameters is not None:
            opt, arg = self.load_parameters(parameters)
            self.options.update(opt)

        self.widget=self.build_widget()

    def close(self, *p):
        if self.controller and self.controller.gui:
            self.controller.gui.unregister_view (self)
        self.widget.destroy()
        return True

    def log(self, msg, level=None):
        m=": ".join( (self.view_name, msg) )
        if self.controller:
            self.controller.log(m, level)
        else:
            print m

    def load_parameters(self, param):
        """Parse the parameters from a Content object, a tuple or an ElementTree.Element
 
        It will return a tuple (options, arguments) where options is a
        dictionary and arguments a list of tuples (name, value).

        If param is None, then try to load default options, if they
        exist. They should be stored in 
        config.data.advenefile( ('defaults', self.view_id + '.xml'), 'settings')

        In case of problem, it will simply return None, None.
        """
        opt, arg = {}, []
        
        if param is None:
            # Load default options
            n=config.data.advenefile( ('defaults', self.view_id + '.xml'), 'settings')
            if os.path.exists(n):
                stream=open(n)
                p=AdhocViewParametersParser(stream)
                stream.close()
            else:
                # No default options. Return empty values.
                return opt, arg
        elif isinstance(param, tuple):
            # It is an already parsed tuple. Return it.
            # FIXME: should we post-process it ?
            return param
        elif isinstance(param, Content):
            try:
                m=param.mimetype
            except:
                return opt, arg
            if  m != 'application/x-advene-adhoc-view':
                return opt, arg
            p=AdhocViewParametersParser(param.stream)
        elif ET.iselement(param):
            p=AdhocViewParametersParser(param)
        else:
            raise Exception("Unknown parameter type " + str(param))

        if p.view_id != self.view_id:
            self.controller.log(_("Invalid view id"))
            return False

        # Post-processing of options
        for name, value in p.options.iteritems():
            # If there is a self.options dictionary, try to guess
            # value types from its content.
            try:
                op=self.options[name]
                if value == 'None':
                    value=None
                elif value == 'True':
                    value=True
                elif value == 'False':
                    value=False
                elif isinstance(op, int) or isinstance(op, long):
                    value=long(value)
                elif isinstance(op, float):
                    value=float(value)
            except (KeyError, AttributeError):
                pass
            opt[name]=value
        return opt, p.arguments

    def parameters_to_element(self, options=None, arguments=None):
        """Generate an ET.Element representing the view and its parameters.
        """
        root=ET.Element(ET.QName(config.data.namespace, 'adhoc'), id=self.view_id)

        if options:
            for n, v in options.iteritems():
                ET.SubElement(root, ET.QName(config.data.namespace, 'option'), name=n, value=urllib.quote(unicode(v)))
        if arguments:
            for n, v in arguments:
                ET.SubElement(root, ET.QName(config.data.namespace, 'argument'), name=n, value=urllib.quote(unicode(v)))
        return root

    def save_default_options(self, *p):
        """Save the default options.
        """
        d=config.data.advenefile('defaults', 'settings')
        if not os.path.isdir(d):
            # Create it
            try:
                helper.recursive_mkdir(d)
            except OSError, e:
                self.controller.log(_("Cannot save default options: %s") % unicode(e))
                return True
        defaults=config.data.advenefile( ('defaults', self.view_id + '.xml'), 'settings')
        
        options, args=self.get_save_arguments()
        # Do not save package-specific arguments.
        root=self.parameters_to_element(options, [])
        stream=open(defaults, 'w')
        helper.indent(root)
        ET.ElementTree(root).write(stream, encoding='utf-8')
        stream.close()
        self.controller.log(_("Default options saved for view %s") % self.view_name)
        return True

    def save_parameters(self, content, options=None, arguments=None):
        """Save the view parameters to a Content object.
        """
        if not isinstance(content, Content):
            raise Exception("save_parameters saves to a Content object")

        content.mimetype='application/x-advene-adhoc-view'

        root=self.parameters_to_element(options, arguments)
        stream=StringIO.StringIO()
        helper.indent(root)
        ET.ElementTree(root).write(stream, encoding='utf-8')
        content.setData(stream.getvalue())
        stream.close()
        return True

    def get_save_arguments(self):
        """Method called when saving a parametered view.
        
        It should return a tuple (options, arguments) where options is
        the options dictionary, and arguments is a list of (name,
        value) tuples).

        If it returns None, None, it means that the view saving is cancelled.
        """
        return self.options, []

    def save_view(self, *p):
        name=self.controller.package._idgenerator.get_id(View)+'_'+self.view_id
        title, ident=advene.gui.util.get_title_id(title=_("Saving %s" % self.view_name),
                                                  element_title=name,
                                                  element_id=name,
                                                  text=_("Enter a view name to save this parametered view"))
        if ident is not None:
            if not re.match(r'^[a-zA-Z0-9_]+$', ident):
                advene.gui.util.message_dialog(_("Error: the identifier %s contains invalid characters.") % ident)
                return True

            options, arguments = self.get_save_arguments()
            if options is None and arguments is None:
                # Cancel view saving
                return True

            v=helper.get_id(self.controller.package.views, ident)
            if v is None:
                create=True
                v=self.controller.package.createView(ident=ident, clazz='package')
            else:
                # Existing view. Check that it is already an adhoc-view
                if v.content.mimetype != 'application/x-advene-adhoc-view':
                    advene.gui.util.message_dialog(_("Error: the view %s is not an adhoc view.") % ident)
                    return True
                create=False
            v.title=title
            v.author=config.data.userid
            v.date=self.controller.get_timestamp()

            self.save_parameters(v.content, options, arguments)
            if create:
                self.controller.package.views.append(v)
                self.controller.notify("ViewCreate", view=v)
            else:
                self.controller.notify("ViewEditEnd", view=v)
        return True

    def get_widget (self):
        """Return the widget."""
        return self.widget

    def build_widget(self):
        return gtk.Label(self.view_name)

    def attach_view(self, menuitem, window):
        def relocate_view(item, v, d):
            # Reference the widget so that it is not destroyed
            wid=v.widget
            wid.get_parent().remove(wid)
            if d in ('south', 'east', 'west', 'fareast'):
                v._destination=d
                self.controller.gui.viewbook[d].add_view(v, name=v._label)
                window.disconnect(window.cleanup_id)
                window.destroy()
            return True

        menu=gtk.Menu()
        for (label, destination) in (
            (_("...embedded east of the video"), 'east'),
            (_("...embedded west of the video"), 'west'),
            (_("...embedded south of the video"), 'south'),
            (_("...embedded at the right of the window"), 'fareast')):
            item = gtk.MenuItem(label)
            item.connect('activate', relocate_view, self, destination)
            menu.append(item)

        menu.show_all()
        menu.popup(None, None, None, 0, gtk.get_current_event_time())
        return True

    def popup(self, label=None):
        if label is None:
            label=self.view_name
        window = gtk.Window(gtk.WINDOW_TOPLEVEL)
        window.set_title (label)

        w=self.get_widget()

        def close_popup(*p):
            window.destroy()
            return True

        # Close the popup window when the widget is destroyed
        w.connect("destroy", close_popup)

        # If the widget defines a buttonbox, we can use it and do not
        # have to define a enclosing VBox (which also solves a problem
        # with the timeline view not being embedable inside a VBox()
        if hasattr(w, 'buttonbox') and w.buttonbox is not None:
            window.add(w)
            window.buttonbox = w.buttonbox
        else:
            vbox = gtk.VBox()
            window.add (vbox)
            vbox.add (w)
            window.buttonbox = gtk.HButtonBox()
            vbox.pack_start(window.buttonbox, expand=False)

        # Insert contextual_actions in buttonbox
        try:
            for label, action in self.contextual_actions:
                b=gtk.Button(label)
                b.connect("clicked", action)
                window.buttonbox.pack_start(b, expand=False)
        except AttributeError:
            pass

        def drag_sent(widget, context, selection, targetType, eventTime ):
            if targetType == config.data.target_type['adhoc-view-instance']:
                # This is not very robust, but allows to transmit a view instance reference
                selection.set(selection.target, 8, repr(self))
                self.widget.get_parent().remove(self.widget)
                # Do not trigger the close_view_cb handler
                window.disconnect(window.cleanup_id)
                window.destroy()
                return True
            return False

        b = gtk.Button(_("Reattach"))
        b.connect('clicked', self.attach_view, window)
        b.connect("drag_data_get", drag_sent)
        # The widget can generate drags
        b.drag_source_set(gtk.gdk.BUTTON1_MASK,
                          config.data.drag_type['adhoc-view-instance'],
                          gtk.gdk.ACTION_LINK)
        
        window.buttonbox.pack_start(b, expand=False)

        b = gtk.Button(stock=gtk.STOCK_CLOSE)

        if self.controller and self.controller.gui:
            b.connect ("clicked", self.controller.gui.close_view_cb, window, self)
        else:
            b.connect ("clicked", lambda w: window.destroy())
        window.buttonbox.pack_start (b, expand=False)

        window.show_all()

        if self.controller and self.controller.gui:
            self.controller.gui.register_view (self)
            window.cleanup_id=window.connect ("destroy", self.controller.gui.close_view_cb, window, self)
            self.controller.gui.init_window_size(window, self.view_id)

        return window

class AdhocViewParametersParser:
    """Parse an AdhocView parameters content.

    It can be a advene.model.Content or a elementtree.Element
    """
    def __init__(self, source=None):
        self.view_id=None
        self.options={}
        # self.arguments will contain (name, value) tuples, in order
        # to preserve order.
        self.arguments=[]
        if ET.iselement(source):
            self.parse_element(source)
        elif hasattr(source, 'read'):
            # File-like object
            self.parse_file(source)
        else:
            print "Do not know what to do with ", source
 
    def parse_file(self, fd):
        tree=ET.parse(fd)
        self.parse_element(tree.getroot())

    def parse_element(self, root):
        """Parse an ElementTree Element.
        """
        if root.tag != ET.QName(config.data.namespace, 'adhoc'):
            raise Exception("Invalid adhoc view definition" + root.tag)
        self.view_id=root.attrib['id']

        for e in root:
            if e.tag == ET.QName(config.data.namespace, 'option'):
                name=e.attrib['name']
                value=urllib.unquote(e.attrib['value'])
                self.options[name]=value
            elif e.tag == ET.QName(config.data.namespace, 'argument'):
                name=e.attrib['name']
                value=urllib.unquote(e.attrib['value'])
                self.arguments.append( (name, value) )
            else:
                print "Unknown tag %s in AdhocViewParametersParser" % e.tag
