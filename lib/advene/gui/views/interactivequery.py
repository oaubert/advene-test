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
"""Interactive query.

Display the query results in a view (timeline, tree, etc).
"""
import advene.core.config as config
import time
from gettext import gettext as _
import pprint

import gtk

from advene.gui.edit.rules import EditQuery
from advene.model.bundle import AbstractBundle
from advene.rules.elements import Query, Condition
from advene.model.annotation import Annotation
from advene.model.tal.context import AdveneTalesException
from advene.gui.util import dialog, get_small_stock_button, get_pixmap_button

from advene.gui.views import AdhocView
import advene.gui.evaluator

from advene.gui.views.table import AnnotationTable, GenericTable

import advene.util.helper as helper

name="Interactive query plugin"

def register(controller):
    controller.register_viewclass(InteractiveQuery)
    controller.register_viewclass(InteractiveResult)

class InteractiveQuery(AdhocView):
    view_name = _("Interactive query")
    view_id = 'interactivequery'
    tooltip=_("Interactive query dialog")
    def __init__(self, controller=None, parameters=None, source="package/annotations", here=None):
        super(InteractiveQuery, self).__init__(controller=controller)
        self.close_on_package_load = False
        self.contextual_actions = (
            #(_("Refresh"), self.refresh),
            (_("Save query"), self.save_query),
            (_("Save default options"), self.save_default_options),
            )
        self.options = {
            'ignore-case': True,
            }
        self.controller=controller
        if here is None:
            here=controller.package
        self.here=here
        self.source=source

        opt, arg = self.load_parameters(parameters)
        self.options.update(opt)
        for n, v in arg:
            if n == 'source':
                self.source=v

        self.querycontainer, self.query = self.get_interactive_query()

        self.widget=self.build_widget()

    def get_interactive_query(self):
        l=helper.get_id(self.controller.package.queries, '_interactive')
        if l:
            q=Query()
            q.from_dom(l.content.model)
            return l, q
        else:
            # Create the query
            el=self.controller.package.createQuery(ident='_interactive')
            el.author=config.data.userid
            el.date=self.controller.get_timestamp()
            el.title=_("Interactive query")

            # Create a basic query
            q=Query(source=self.source,
                    rvalue="element")
            q.add_condition(Condition(lhs="element/content/data",
                                      operator="contains",
                                      rhs="string:a"))

            el.content.data=q.xml_repr()
            el.content.mimetype='application/x-advene-simplequery'

            self.controller.package.queries.append(el)

            self.controller.notify('QueryCreate', query=el)
            return el, q

    def save_query(self, *p):
        """Saves the query in the package.
        """
        l=self.eq.invalid_items()
        if l:
            self.controller.log(_("Invalid query.\nThe following fields have an invalid value:\n%s")
                     % ", ".join(l))
            return True
        # Update the query
        self.eq.update_value()

        t, i = dialog.get_title_id(title=_("Saving the query..."),
                                   text=_("Give a title and identifier for saving the query"),
                                   element_title=self._label,
                                   element_id=helper.title2id(self._label))
        if i is None:
            return True

        q=helper.get_id(self.controller.package.queries, i)
        # Overwriting an existing query
        if q:
            create=False
        else:
            create=True
            # Create the query
            q=self.controller.package.createQuery(ident=i)
            q.author=config.data.userid
            q.date=self.controller.get_timestamp()
            self.controller.package.queries.append(q)

        q.title=t
        q.content.mimetype='application/x-advene-simplequery'

        # Store the query itself in the _interactive query
        q.content.data = self.eq.model.xml_repr()
        if create:
            self.controller.notify('QueryCreate', query=q)
        else:
            self.controller.notify('QueryEditEnd', query=q)
        return q

    def validate(self, button=None):
        # Get the query
        l=self.eq.invalid_items()
        if l:
            self.controller.log(_("Invalid query.\nThe following fields have an invalid value:\n%s")
                     % ", ".join(l))
            return True
        query=self
        self.eq.update_value()
        # Store the query itself in the _interactive query
        self.querycontainer.content.data = self.eq.model.xml_repr()

        label=_("Expert search")
        c=self.controller.build_context(here=self.here)
        try:
            res=c.evaluateValue("here/query/_interactive")
        except AdveneTalesException, e:
            # Display a dialog with the value
            dialog.message_dialog(_("TALES error in interactive expression:\n%s" % str(e)),
                icon=gtk.MESSAGE_ERROR)
            return True

        # Close the search window
        self.close()

        # Set the result attribute for the InteractiveResult view
        self.result=res

        # And display the result in the same viewbook or window
        self.controller.gui.open_adhoc_view('interactiveresult', destination=self._destination,
                                            label=label, query=query, result=res)
        return True

    def cancel(self, button=None):
        self.close()
        return True

    def build_widget(self):
        vbox = gtk.VBox()

        self.eq=EditQuery(self.query,
                          editable=True,
                          controller=self.controller)
        vbox.add(self.eq.widget)

        hb=gtk.HButtonBox()

        b=gtk.Button(stock=gtk.STOCK_OK)
        b.connect ("clicked", self.validate)
        hb.pack_start(b, expand=False)

        b=gtk.Button(stock=gtk.STOCK_CANCEL)
        b.connect ("clicked", self.cancel)
        hb.pack_start(b, expand=False)

        vbox.pack_start(hb, expand=False)

        def handle_key_press_event(widget, event):
            if event.keyval == gtk.keysyms.Return:
                self.validate()
                return True
            elif event.keyval == gtk.keysyms.Escape:
                self.cancel()
                return True
            return False

        vbox.connect('key-press-event', handle_key_press_event)

        return vbox

class InteractiveResult(AdhocView):
    """Interactive result display.

    Either we give the query (whose .result attribute will be set), or
    we give a simple result (structure). In the first case, an option
    will be offered to edit the query again.
    """
    view_name = _("Interactive result")
    view_id = 'interactiveresult'
    tooltip=_("Interactive result display")

    def __init__(self, controller=None, parameters=None, query=None, result=None):
        super(InteractiveResult, self).__init__(controller=controller)
        self.close_on_package_load = False
        self.contextual_actions = (
            #(_("Refresh"), self.refresh),
            #(_("Save view"), self.save_view),
            )
        self.controller=controller
        self.query=query
        if result is None and isinstance(query, InteractiveQuery):
            result=query.result
        self.result=result

        if isinstance(self.query, InteractiveQuery):
            self.label=_("Result of interactive query")
        else:
            # Must be a string
            self.label=_("""'%s'""") % self.query

        # Annotation-table view
        self.table=None
        self.widget=self.build_widget()

    def create_montage(self, *p):
        if hasattr(self, 'table'):
            # There are annotations
            l=self.table.get_elements()
        self.controller.gui.open_adhoc_view('montage', elements=l, destination=self._destination)
        return True

    def create_annotations(self, *p):
        if self.table is not None:
            # There are annotations
            l=self.table.get_elements()
        else:
            l=None
        if l:
            at=self.controller.gui.ask_for_annotation_type(text=_("Choose the annotation type where annotations will be created."),
                                                           create=True)
            if at is None:
                return False
            at.setMetaData(config.data.namespace_prefix['dc'], 'description', _("Copied result of the '%s' query") % self.query)
            self.controller.notify('AnnotationTypeEditEnd', annotationtype=at)
            for a in l:
                self.controller.transmute_annotation(a, at)
        return True

    def redo_quicksearch(self, b, entry):
        s=entry.get_text()
        if not s:
            self.log(_("Empty quicksearch string"))
            return True
        res=self.controller.gui.search_string(s)
        label="'%s'" % s
        self.controller.gui.open_adhoc_view('interactiveresult', destination=self._destination, 
                                            result=res, label=label, query=s)
        self.close()
        return True

    def build_widget(self):
        v=gtk.VBox()

        tb=gtk.Toolbar()
        tb.set_style(gtk.TOOLBAR_ICONS)
        v.pack_start(tb, expand=False)

        top_box=gtk.HBox()
        v.pack_start(top_box, expand=False)

        # FIXME: if self.query: edit query again
        if self.query and isinstance(self.query, InteractiveQuery):
            b=gtk.Button(_("Edit query again"))
            b.connect('clicked', self.edit_query)
            top_box.pack_start(b, expand=False)
        elif self.query:
            e=gtk.Entry()
            e.set_text(self.query)
            e.connect('activate', self.redo_quicksearch, e)
            b=get_small_stock_button(gtk.STOCK_FIND, self.redo_quicksearch, e)
            self.controller.gui.tooltips.set_tip(e, _('String to search'))
            self.controller.gui.tooltips.set_tip(b, _('Search again'))
            top_box.pack_start(e, expand=False)
            top_box.pack_start(b, expand=False)
                        
        # Present choices to display the result
        if not self.result:
            v.add(gtk.Label(_("Empty result")))
        elif (isinstance(self.result, list) or isinstance(self.result, tuple)
            or isinstance(self.result, AbstractBundle)):
            # Check if there are annotations
            l=[ a for a in self.result if isinstance(a, Annotation) ]
            cr=len(self.result)
            cl=len(l)

            if cr == cl:
                t=_("Result is a list of %d annotations.") % cr
            else:
                t=_("Result is a list of  %(number)d elements with %(elements)s.") % {
                    'elements': helper.format_element_name("annotation", len(l)),
                    'number': len(self.result)}

            label=gtk.Label(t)
            label.set_line_wrap(True)
            top_box.pack_start(label, expand=False)

            def toggle_highlight(b, annotation_list):
                if not hasattr(b, 'highlight') or b.highlight:
                    event="AnnotationActivate"
                    label= _("Unhighlight annotations")
                    b.highlight=False
                else:
                    event="AnnotationDeactivate"
                    label=_("Highlight annotations")
                    b.highlight=True
                self.controller.gui.tooltips.set_tip(b, label)
                for a in annotation_list:
                    self.controller.notify(event, annotation=a)
                return True

            if l:
                # Instanciate a table view
                table=AnnotationTable(controller=self.controller, elements=l)

                if cr == cl:
                    # Only annotations.
                    v.add(table.widget)
                else:
                    # Mixed annotations + other elements
                    notebook=gtk.Notebook()
                    notebook.set_tab_pos(gtk.POS_TOP)
                    notebook.popup_disable()
                    v.add(notebook)

                    notebook.append_page(table.widget, gtk.Label(_("Annotations")))

                    gtable=GenericTable(controller=self.controller, elements=[ e
                                                                               for e in self.result
                                                                               if not isinstance(e, Annotation) ]
                                                                               )
                    notebook.append_page(gtable.widget, gtk.Label(_("Other elements")))


                for (icon, tip, action) in (
                    ('timeline.png' , _("Display annotations in timeline"), lambda b: self.open_in_timeline(l)),
                    ('transcription.png', _("Display annotations as transcription"), lambda b:
                         self.controller.gui.open_adhoc_view('transcription',
                                                             label=self.label,
                                                             destination=self._destination,
                                                             elements=l)),
                    ('highlight.png', _("Highlight annotations"), lambda b: toggle_highlight(b, l)),
                    (gtk.STOCK_CONVERT, _("Export table"), lambda b: table.csv_export()),
                    (gtk.STOCK_NEW, _("Create annotations from the result"), self.create_annotations),
                    ('montage.png', _("Define a montage with the result"), self.create_montage),
                    ):
                    if icon.endswith('.png'):
                        i=gtk.Image()
                        i.set_from_file(config.data.advenefile( ( 'pixmaps', icon) ))
                        ti=gtk.ToolButton(icon_widget=i)
                    else:
                        ti=gtk.ToolButton(stock_id=icon)
                    ti.connect('clicked', action)
                    ti.set_tooltip(self.controller.gui.tooltips, tip)
                    tb.insert(ti, -1)

                self.table=table
            else:
                # Only Instanciate a generic table view
                gtable=GenericTable(controller=self.controller, elements=self.result)
                v.add(gtable.widget)
                
                ti=gtk.ToolButton(stock_id=gtk.STOCK_CONVERT)
                ti.connect('clicked', lambda b: gtable.csv_export())
                ti.set_tooltip(self.controller.gui.tooltips, _("Export table"))
                tb.insert(ti, -1)
                self.table=gtable
            
                
            i=gtk.Image()
            i.set_from_file(config.data.advenefile( ( 'pixmaps', 'editaccumulator.png') ))
            ti=gtk.ToolButton(icon_widget=i)
            ti.connect('clicked', lambda b: self.open_in_edit_accumulator(self.table.get_elements()))
            ti.set_tooltip(self.controller.gui.tooltips, _("Edit elements"))
            tb.insert(ti, -1)

            if config.data.preferences['expert-mode']:
                i=gtk.Image()
                i.set_from_file(config.data.advenefile( ( 'pixmaps', 'python.png') ))
                ti=gtk.ToolButton(icon_widget=i)
                ti.connect('clicked', lambda b: self.open_in_evaluator(self.table.get_elements()))
                ti.set_tooltip(self.controller.gui.tooltips, _("Open in python evaluator"))
                tb.insert(ti, -1)
        else:
            v.add(gtk.Label(_("Result:\n%s") % unicode(self.result)))
        v.show_all()
        return v

    def edit_query(self, *p):
        self.close()
        self.controller.gui.open_adhoc_view('interactivequery', destination='east')
        return True

    def open_in_timeline(self, l):
        self.controller.gui.open_adhoc_view('timeline', label=self.label, destination=self._destination, elements=l)
        return True

    def open_in_edit_accumulator(self, l):
        if not self.controller.gui.edit_accumulator:
            self.controller.gui.open_adhoc_view('editaccumulator')
        a=self.controller.gui.edit_accumulator
        for e in l:
            a.edit(e)
        return True

    def open_in_evaluator(self, l):
        p=self.controller.package
        try:
            a=p.annotations[-1]
        except IndexError:
            a=None

        ev=advene.gui.evaluator.Window(globals_=globals(),
                                       locals_={'package': p,
                                                'result': l,
                                                'p': p,
                                                'a': a,
                                                'c': self.controller,
                                                'self': self,
                                                'pp': pprint.pformat },
                                       historyfile=config.data.advenefile('evaluator.log', 'settings')
                                       )
        w=ev.popup()
        b=gtk.Button(stock=gtk.STOCK_CLOSE)

        def close_evaluator(*p):
            ev.save_history()
            w.destroy()
            return True

        b.connect("clicked", close_evaluator)
        b.show()
        ev.hbox.add(b)

        self.controller.gui.init_window_size(w, 'evaluator')

        w.set_title(_("Results of _interactive query"))
        ev.set_expression('result')
        return True

