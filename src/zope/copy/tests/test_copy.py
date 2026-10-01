##############################################################################
#
# Copyright (c) 2012 Zope Foundation and Contributors.
# All Rights Reserved.
#
# This software is subject to the provisions of the Zope Public License,
# Version 2.1 (ZPL).  A copy of the ZPL should accompany this distribution.
# THIS SOFTWARE IS PROVIDED "AS IS" AND ANY AND ALL EXPRESS OR IMPLIED
# WARRANTIES ARE DISCLAIMED, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF TITLE, MERCHANTABILITY, AGAINST INFRINGEMENT, AND FITNESS
# FOR A PARTICULAR PURPOSE.
#
##############################################################################
import unittest


class _Base:

    def setUp(self):
        from zope.interface.interface import adapter_hooks
        self._restore = adapter_hooks[:]

    def tearDown(self):
        from zope.interface.interface import adapter_hooks
        adapter_hooks[:] = self._restore


class Test_clone(_Base, unittest.TestCase):

    def _callFUT(self, obj):
        from zope.copy import clone
        return clone(obj)

    def test_wo_hooks(self):
        from zope.copy.examples import Demo
        demo = Demo()
        demo.freeze()
        self.assertTrue(demo.isFrozen())
        copied = self._callFUT(demo)
        self.assertIsNot(copied, demo)
        self.assertIsInstance(copied, Demo)
        self.assertTrue(copied.isFrozen())

    def test_w_simple_hook(self):
        from zope.copy.examples import Data
        from zope.copy.examples import Demo
        from zope.copy.interfaces import ICopyHook
        demo = Demo()
        demo.freeze()

        class Hook:
            def __init__(self, context):
                self.context = context

            def __call__(self, obj, register):
                return None

        def _adapt(iface, obj):
            if iface is ICopyHook and isinstance(obj, Data):
                return Hook(obj)
        _registerAdapterHook(_adapt)
        copied = self._callFUT(demo)
        self.assertIsNot(copied, demo)
        self.assertIsInstance(copied, Demo)
        self.assertFalse(copied.isFrozen())

    def test_subobject_wo_post_copy_hook(self):
        from zope.location.location import Location
        from zope.location.location import locate

        from zope.copy.examples import Subobject
        o = Location()
        s = Subobject()
        o.subobject = s
        locate(s, o, 'subobject')
        self.assertIs(s.__parent__, o)
        self.assertEqual(o.subobject(), 0)
        self.assertEqual(o.subobject(), 1)
        self.assertEqual(o.subobject(), 2)
        c = self._callFUT(o)
        self.assertIs(c.subobject.__parent__, c)
        self.assertEqual(c.subobject(), 3)
        self.assertEqual(o.subobject(), 3)

    def test_deep_object_graph_does_not_hit_recursion_limit(self):
        # https://github.com/zopefoundation/zope.copy/issues/8
        # Pickling a long chain of small objects (the kind of structure
        # a large BTree ends up producing) can need many more stack
        # frames than the ambient recursion limit allows for. clone()
        # should cope with this instead of letting a bare
        # RecursionError escape, and it should leave the recursion
        # limit exactly as it found it.
        import sys

        from zope.copy.examples import Node

        old_limit = sys.getrecursionlimit()
        self.addCleanup(sys.setrecursionlimit, old_limit)
        sys.setrecursionlimit(50)

        head = None
        for _ in range(400):
            head = Node(head)

        copied = self._callFUT(head)

        self.assertIsNot(copied, head)
        count = 0
        node = copied
        while node is not None:
            count += 1
            node = node.next
        self.assertEqual(count, 400)
        # The temporary bump to the recursion limit must not leak out.
        self.assertEqual(sys.getrecursionlimit(), 50)

    def test_recursion_limit_exhausted_reraises(self):
        # If _clone keeps hitting a RecursionError no matter how high
        # the retry loop raises the limit, clone() must give up once
        # the ceiling is reached and let the RecursionError propagate,
        # and it must still restore the original recursion limit on
        # the way out. Forcing the RecursionError through a mock,
        # rather than via a real object graph and a tiny recursion
        # limit, keeps this independent of how deep pickling of a
        # given structure actually nests on a given Python version.
        import sys
        from unittest import mock

        old_limit = sys.getrecursionlimit()
        self.addCleanup(sys.setrecursionlimit, old_limit)

        with mock.patch('zope.copy._MAX_RECURSION_LIMIT', old_limit + 5):
            with mock.patch('zope.copy._clone', side_effect=RecursionError):
                with self.assertRaises(RecursionError):
                    self._callFUT(object())

        self.assertEqual(sys.getrecursionlimit(), old_limit)

    def test_subobject_w_post_copy_hook(self):
        from zope.location.location import Location
        from zope.location.location import locate

        from zope.copy.examples import Subobject
        from zope.copy.interfaces import ICopyHook
        o = Location()
        s = Subobject()
        o.subobject = s
        locate(s, o, 'subobject')
        self.assertIs(s.__parent__, o)
        self.assertEqual(o.subobject(), 0)
        self.assertEqual(o.subobject(), 1)
        self.assertEqual(o.subobject(), 2)

        class Hook:
            def __init__(self, context):
                self.context = context

            def __call__(self, obj, register):
                obj = Subobject()

                def reparent(translate):
                    obj.__parent__ = translate(self.context.__parent__)
                register(reparent)
                return obj

        def _adapt(iface, obj):
            if iface is ICopyHook and isinstance(obj, Subobject):
                return Hook(obj)
        _registerAdapterHook(_adapt)
        c = self._callFUT(o)
        self.assertIs(c.subobject.__parent__, c)
        self.assertEqual(c.subobject(), 0)
        self.assertEqual(o.subobject(), 3)


class Test_copy(_Base, unittest.TestCase):

    def _callFUT(self, obj):
        from zope.copy import copy
        return copy(obj)

    def test_clears_attrs(self):
        from zope.copy.examples import Demo
        parent = Demo()
        demo = Demo()
        demo.__parent__ = parent
        demo.__name__ = 'demo'
        copied = self._callFUT(demo)
        self.assertIsNot(copied, demo)
        self.assertIsInstance(copied, Demo)
        self.assertEqual(copied.__parent__, None)
        self.assertEqual(copied.__name__, None)

    def test_wo_parent_or_name_set(self):
        # Nothing to clear when the object never had __parent__ or
        # __name__ set in the first place.
        from zope.copy.examples import Demo
        demo = Demo()
        copied = self._callFUT(demo)
        self.assertIsNot(copied, demo)
        self.assertIsInstance(copied, Demo)
        self.assertIsNone(getattr(copied, '__parent__', None))
        self.assertIsNone(getattr(copied, '__name__', None))

    def test_w_readonly___parent___and___name__(self):
        global Foo  # make unpicklable
        parent = object()

        class Foo:
            @property
            def __parent__(self):
                return parent

            @property
            def __name__(self):
                return 'foo'
        foo = Foo()
        copied = self._callFUT(foo)
        self.assertIsNot(copied, foo)
        self.assertIsInstance(copied, Foo)
        self.assertIs(copied.__parent__, parent)
        self.assertEqual(copied.__name__, 'foo')


class CopyPersistentTests(_Base, unittest.TestCase):

    def _getTargetClass(self):
        from zope.copy import CopyPersistent
        return CopyPersistent

    def _makeOne(self, obj):
        return self._getTargetClass()(obj)

    def test_ctor(self):
        obj = object()
        cp = self._makeOne(obj)
        self.assertIs(cp.toplevel, obj)
        self.assertEqual(cp.pids_by_id, {})
        self.assertEqual(cp.others_by_pid, {})
        self.assertEqual(cp.registered, [])

    def test_id_wo_hook(self):
        obj = object()
        cp = self._makeOne(obj)
        self.assertEqual(cp.id(obj), None)

    def test_id_w_hook_already_cached(self):
        from zope.copy.interfaces import ICopyHook
        obj = object()
        cp = self._makeOne(obj)
        cp.pids_by_id[id(obj)] = 'PID'

        class Hook:
            def __init__(self, context):
                self.context = context

            def __call__(self, obj, register):
                raise AssertionError("Not called")

        def _adapt(iface, obj):
            assert iface is ICopyHook
            return Hook(obj)
        _registerAdapterHook(_adapt)
        self.assertEqual(cp.id(obj), 'PID')

    def test_id_w_hook_raising_ResumeCopy(self):
        from zope.copy.interfaces import ICopyHook
        from zope.copy.interfaces import ResumeCopy
        obj = object()
        cp = self._makeOne(obj)

        class Hook:
            def __init__(self, context):
                self.context = context

            def __call__(self, obj, register):
                raise ResumeCopy()

        def _adapt(iface, obj):
            assert iface is ICopyHook
            return Hook(obj)
        _registerAdapterHook(_adapt)
        self.assertEqual(cp.id(obj), None)

    def test_id_w_hook_normal(self):
        from zope.copy.interfaces import ICopyHook
        obj = object()
        cp = self._makeOne(obj)

        class Hook:
            def __init__(self, context):
                self.context = context

            def __call__(self, obj, register):
                return None

        def _adapt(iface, obj):
            assert iface is ICopyHook
            return Hook(obj)
        _registerAdapterHook(_adapt)
        self.assertEqual(cp.id(obj), 1)
        obj2 = object()
        self.assertEqual(cp.id(obj2), 2)
        self.assertEqual(cp.pids_by_id, {id(obj): 1, id(obj2): 2})
        self.assertEqual(cp.others_by_pid, {1: None, 2: None})


def _registerAdapterHook(func):
    from zope.interface.interface import adapter_hooks
    adapter_hooks.insert(0, func)


def test_suite():
    return unittest.defaultTestLoader.loadTestsFromName(__name__)
