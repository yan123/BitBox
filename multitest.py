#!/usr/bin/env python
# -*- coding: utf-8 -*-
'''
Rationale:

Imagine we need to run the same test steps multiple times, but each time with different
parameter combinations.
For example: Testing all combinations of A=(0,1,2) and B=['a','b','c'] would require
9 tests as follows:
+-------------------------------+
|       |  A=0  |  A=1  |  A=2  |
+-------------------------------+
| B='a' | test0 | test1 | test2 |
+-------------------------------+
| B='b' | test3 | test4 | test5 |
+-------------------------------+
| B='c' | test6 | test7 | test8 |
+-------------------------------+

Copy-pasting, or using nose generator plugin might sometimes not be an option.

So here's the solution:
1) Import MultiTestMeta (or MultiTestMixin) from this file.
2) Create a test class with MultiTestMeta metaclass (or inherit it from MultiTestMixin)
3) Inside it create test case methods that accept extra params for A and B
   and decorate them as follows:

@with_combined(A=[0,1,2], B='abc')
def test_method(self, A, B):...

Note1: that extra params after `self` have to conform the one's in decorator.
Note2: these do NOT HAVE to be only the named params, just make sure that their
    amount and naming fit `test_method` arguments.
Note3: there can be multiple decorated test methods in each test class.
Note4: the generated tests CAN BE RUN SEPARATELY as if they really exist
    in the file (proper python methodnames are created from original test
    name and param values).
Note5: method docstring gets processed via string.Template substitution.
    So positional method params can be referred as arg0, arg1, arg2...
    Refer named params by their respective names. Please see the example in __main__

That's all. Our metaclass will spawn extra 9 methods each containing
a `test_method` call, but with different param combinations (as shown below):
test_method(A=0, B='a'); test_method(A=0, B='b'); test_method(A=0, B='c');
test_method(A=1, B='a'); test_method(A=1, B='b'); ... test_method(A=2, B='c');

Should work fine with python -m unittest your_generated_tests_file
OR with nose tests runner.

Any questions? Contact me on github. User: yan123
'''

import itertools
import string

# Word representation for certain literals.
# Some symbols inspired by: https://dev.w3.org/html5/html-author/charref
AS_WORD = {'.': '_', '-': 'minus', '+': 'plus', '#': 'num', '!': 'excl',
        '"': 'quot', '$': 'dollar', '%': 'percnt', '&': 'amp', '/': 'sol',
        '\\': 'bsol', '=': 'eq', ',': 'comma', ';': 'semi', ':': 'colon'}

# Make up a valid python name
pystr = lambda n: ''.join(x if x.isalnum() else AS_WORD.get(x, '_') for x in str(n))

def mix_params(args, kwargs):
    '''Takes args/kwargs tuple and returns all param combinations inside.
    Each item inside args or kwargs is expected to be an iterable
    of all desired values for that certain parameter'''
    args_len = len(args)
    # values() is guaranteed to have the same order as keys(), we exploit that below
    for i in itertools.product(*itertools.chain(args, kwargs.values())):
        yield tuple(i[:args_len]), dict(zip(kwargs.keys(), i[args_len:]))

def zip_params(args, kwargs):
    '''For every param inside args/kwargs takes n-th element and builds up an
    args/kwargs tuple. Just as zip() does with iterables'''
    zipped_args = itertools.izip(*args)
    zipped_kwargs = (dict(zip(kwargs.keys(), v)) for v in itertools.izip(*kwargs.values()))
    for one_args_kwargs in itertools.izip(zipped_args, zipped_kwargs):
        yield one_args_kwargs

def kwargs_params(list_of_kwargs):
    for k in list_of_kwargs:
        yield (), k

def with_(mix_method, args, kwargs):
    '''Decorator. Adds _metatest_params=(args, kwargs) field to decorated method.
    _metatest_params is a marker for MultiTest class to see which
    methods have to be spawned into multiple tests'''
    def hook_args_kwargs(method):
        method._metatest_params = mix_method(args, kwargs)
        return method
    return hook_args_kwargs

with_combined = lambda *args, **kwargs: with_(mix_params, args, kwargs)
with_zipped = lambda *args, **kwargs: with_(zip_params, args, kwargs)
with_kwargs = lambda *list_of_kwargs: with_(kwargs_params, (), list_of_kwargs)

class MultiTestMeta(type):
    '''Spawns multiple tests for every `with_combined` decorated method in subtyped class.
    Removes original decorated method from class dictionary.'''
    def __new__(mcs, cls_name, bases, attrs):
        # We'll change attrs while iterating, prepare a list (py3):
        marked_tests = [(k, v) for k, v in attrs.items() if
               callable(v) and hasattr(v, '_metatest_params')]
        for name, method in marked_tests:
            del attrs[name] # remove original test method not to mess with test-runner
            for test_args, test_kwargs in method._metatest_params:
                # Closure here, using default args trick:
                def actual_test(self, me=method, ar=test_args, kw=test_kwargs):
                    return me(self, *ar, **kw)

                # Substitute template values in docstring:
                sub_dict = dict(('arg'+str(num), val) for num, val in enumerate(test_args))
                sub_dict.update(test_kwargs)
                actual_test.__doc__ = string.Template(method.__doc__).safe_substitute(sub_dict)

                actual_name = (name +
                        ('_' if test_args or test_kwargs else '') +
                        '_'.join(pystr(a) for a in test_args) +
                        ('_' if test_args and test_kwargs else '') +
                        '_'.join(pystr(k)+'_'+pystr(v) for k,v in sorted(test_kwargs.items())))

                # Make sure actual_name is unique:
                if actual_name in attrs:
                    prefix_name = actual_name
                    for i in range(1023):
                        actual_name = prefix_name + '_' + str(i)
                        if actual_name not in attrs:
                            break
                    else:
                        raise RuntimeError('1024 methods with similar name '
                                'already exist, please consider refactoring')
                # Using __name__, __dict__ instead of func_* for py3 compatibility.
                actual_test.__name__ = actual_name
                actual_test.__dict__ = method.__dict__
                attrs[actual_name] = actual_test

        return super(MultiTestMeta, mcs).__new__(mcs, cls_name, bases, attrs)

class MultiTestMixin(object):
    '''Enables spawning multiple tests methods via with_combined
    decorator and inheritance'''
    __metaclass__ = MultiTestMeta

# Usage example (just run 'python multitest.py'):
if __name__ == '__main__':
    import unittest

    class SuiteExample(unittest.TestCase, MultiTestMixin):
        # __metaclass__ = MultiTestMeta # forces use of test generator
        # runTest = lambda *args: True # for debugging purposes only

        def setUp(self):
            print '\nrunning setup'

        def tearDown(self):
            print '\ndoing cleanup after test'

        # Decorator means: produce 18 tests, each containing one method call
        # e.g. (the 1st test): steps2execute(self, 1, col='a', extra='+')
        # till (the 18th test): steps2execute(self, 3.456, col='c', extra='-')
        @with_combined((1, 2, 3.456), col=['a', 'b', 'c'], extra='+-')
        def test_steps2execute(self, row, col, extra):
            '''Test steps with *args[0]=$arg0 col=$col extra=$extra params.'''
            print 'doing some steps with: row='+str(row)+', col='+col+', extra='+extra
            self.assertEquals(row*col+extra, 'cc+')

        def test_not_decorated(self):
            print 'not decorated test'
            self.assertTrue(True)

    # Just a dummy test suite without decorators:
    class T2(unittest.TestCase):
        def test_case_two(self):
            assert True

    unittest.main()
