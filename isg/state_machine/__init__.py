import re, string, types, new, sha, sys, logging
from pprint import pprint
from sets   import Set

class NonFatalException(Exception):
    """An Exception which doesn't force the state machine to reset"""

stateNameRe = re.compile(r'^(?P<stateName>[A-Z][A-Z0-9_]+)$')
handlerRe = re.compile(r'^do__(?P<stateName>[A-Z][A-Z0-9_]+(__default)?)?$')
preHandlerRe = re.compile(r'^pre__(?P<stateName>[A-Z][A-Z0-9_]+(__default)?)?$')
transitionStateRe = re.compile(r'^transition__([A-Z][A-Z0-9_]+(__default)?)__to__([A-Z][A-Z0-9]+)$')

"""An extensible architecture for building state machines.

* HandlerSets contain state handlers (methods matching handlerRe).

State handlers determine where to go from a specific state.

* TransitionHelpers contain transition handlers (methods matching transitionStateRe).

Transition helpers provide a mechanism of moving between states which may be in different handler sets without forcing the handler sets to be aware of each other; the handler can be requested to search for a transition handler to move between any two states.

Transitions may have a specific substate as a *source state*. Destination states must be exact.

* StateMachineHandler objects control state via invoking methods inherited from the above (using a mix-in pattern. See what 'yall Java folks are missing?)

State names may be of the form of 'FOO__BAR__BAZ'; each double underscore indicates a level of substate hierarchy. In finding a handler for this state, an attempt will first be made to call "do__FOO__BAR". If this does not exist, attempts to call "do__FOO__BAR__BAZ__default", "do__FOO__BAR__default" and "do__FOO__default" will be made.

A transition from FOO__BAR__BAZ to QUX__FUZ will first search for transition__FOO__BAR__BAZ__to__QUX__FUZ; if this is not found, it will try transition__FOO__BAR__BAZ__default__to__QUX__FUZ, transition__FOO__BAR__default__to__QUX__FUZ and transition__FOO__default__to__QUX__FUZ before giving up.
"""

###

def possibleStateHandlerNames(state, prefix='do'):
    """A generator which provides a list of method names for state handlers which would handle a state with the given name.

    >>> pprint(list(possibleStateHandlerNames('FOO__BAR__BAZ')))
    ['do__FOO__BAR__BAZ',
     'do__FOO__BAR__BAZ__default',
     'do__FOO__BAR__default',
     'do__FOO__default',
     'do__default']
"""
    if stateNameRe.match(state) is None:
        raise 'provided string (%(state)s) does not represent a valid state' % locals()
    yield '%(prefix)s__%(state)s' % locals()
    items = state.split('__')
    for n in range(len(items), 0, -1):
        stateFragment = string.join(items[:n], '__')
        yield '%(prefix)s__%(stateFragment)s__default' % locals()
    yield '%(prefix)s__default' % locals()

def possibleTransitionHandlerNames(fromState, toState):
    """A generator which provides a list of method names for transition handlers which would handle the transition between the supplied states.

    >>> pprint(list(possibleTransitionHandlerNames('FOO__BAR__BAZ', 'QUX__QUUX')))
    ['transition__FOO__BAR__BAZ__to__QUX__QUUX',
     'transition__FOO__BAR__BAZ__default__to__QUX__QUUX',
     'transition__FOO__BAR__default__to__QUX__QUUX',
     'transition__FOO__default__to__QUX__QUUX',
     'transition__default__to__QUX__QUUX']
    """
    if stateNameRe.match(fromState) is None:
        raise 'provided string (%(fromState)s) does not represent a valid state' % locals()
    if stateNameRe.match(toState) is None:
        raise 'provided string (%(toState)s) does not represent a valid state' % locals()
    yield 'transition__%(fromState)s__to__%(toState)s' % locals()
    items = fromState.split('__')
    for n in range(len(items), 0, -1):
        fromStateFragment = string.join(items[:n], '__')
        yield 'transition__%(fromStateFragment)s__default__to__%(toState)s' % locals()
    yield 'transition__default__to__%(toState)s' % locals()

def isSubstateOf(parentState, subState):
    """Determine whether subState is a substate of parentState

    >>> isSubstateOf('FOO__BAR', 'FOO')
    False
    >>> isSubstateOf('FOO__BAR', 'FOO__BAR')
    True
    >>> isSubstateOf('FOO__BAR', 'FOO__BAR__BAZ')
    True
    >>> isSubstateOf('FOO__BAR', 'FOO__BAZ')
    False
    """
    if parentState is None or subState is None: return False
    if parentState == subState: return True
    if len(subState) <= len(parentState): return False
    if subState[:len(parentState)+2] == parentState + '__': return True
    return False

def initializeAs(self, clazz, *args, **kwargs):
    assert self.__init__ != self.__old_init__, 'equivalent constructors?!'
    logger = logging.getLogger('SingleInitClass.__init__.initializeAs')
    logger.info('fake constructor for class %s' % repr(clazz))
    if not hasattr(self, 'initializationSet'):
        logger.debug('creating a new initializationSet for %s' % repr(self))
        self.initializationSet = Set()
    if not clazz in self.initializationSet:
        logger.debug('%s not in %s' % (repr(clazz), repr(self.initializationSet)))
        logger.debug('initializing %s as %s for first time' % (repr(self), repr(clazz)))
        self.initializationSet.add(clazz)
        return clazz.__old_init__(self, *args, **kwargs)
    logger.debug('%s has been a %s before' % (repr(self), repr(clazz)))
    return None

class OriginMarkClass(type):
    """A type such that methods instanciated are marked as belonging to the class in question."""
    def __init__(cls, name, bases, dict):
        for item_name in dir(cls):
            if item_name[:4] != 'do__':
                continue
            item = getattr(cls, item_name)
            if not hasattr(item.im_func, '_origin_class'):
                setattr(item.im_func, '_origin_class', cls)
        super(OriginMarkClass, cls).__init__(name, bases, dict)

class SingleInitClass(type):
    """A type such that classes instanciated with this metaclass can only have their constructors run once."""
    def __init__(cls, name, bases, dict):
        logger = logging.getLogger('SingleInitClass.__init__')
        if hasattr(cls, '__init__'):
            setattr(cls, 'initializeAs', initializeAs)
            setattr(cls, '__old_init__', getattr(cls, '__init__'))
            setattr(cls, '__init__', (lambda self, *args, **kwargs: self.initializeAs(cls, *args, **kwargs)))
            dict['__old_init__'] = getattr(cls, '__old_init__')
            dict['__init__'] = getattr(cls, '__init__')
        logger.debug('Initializers for %s are %s (new) and %s (old)' % (repr(cls),
                                                                        repr(getattr(cls, '__init__')),
                                                                        repr(getattr(cls, '__old_init__'))))
        logger.debug('Dictionary for %s is %s' % (repr(cls), repr(dict)))
        super(SingleInitClass, cls).__init__(name, bases, dict)

class SingleInitOriginMarkClass(SingleInitClass, OriginMarkClass):
    def __init__(cls, name, bases, dict):
        super(SingleInitOriginMarkClass, cls).__init__(name, bases, dict)

class Retargetable(object):
    """An object which can have its class swapped out to a freshly constructed class inheriting from any defined set of base classes.

    Retargetable objects' constructors may not take arguments.
    """
    __metaclass__ = SingleInitOriginMarkClass
    generatedClasses = {}
    def __init__(self):
        super(Retargetable, self).__init__()
        self.__logger = logging.getLogger('StateMachine.Retargetable')
        self.__logger.debug('Retargetable constructor (initializedAs %s)' % str(self.initializationSet))
        self.__firstConstantClasses = []
        self.__constantClasses = []
        self.__initializedClasses = Set()
    def __parseClasslistArg(self, classes):
        """Retrieve a classlist argument (which may be a tuple or list of classes, or a single class). Convert to a tuple listing classes, and assert that all members are indeed classes"""
        if type(classes) is types.TupleType:    pass
        elif type(classes) is types.ListType:   classes = tuple(classes)
        else:                                   classes = (classes,)

        for aClass in classes:
            assert isinstance(aClass, types.TypeType), 'a non-class object was provided'
        return classes
    def __initializeIfNeeded(self, classes):
        for aClass in self.__parseClasslistArg(classes):
            if not aClass in self.__initializedClasses:
                self.__initializedClasses.add(aClass)
                aClass.__init__(self)
    def inherit(self, requestedClasses):
        if hasattr(self.__class__, 'originalClass'):
            baseClass = self.__class__.originalClass
        else:
            baseClass = self.__class__

        self.__logger.info('remaking %s (originally %s) to have classes %s' % (repr(self), repr(baseClass), repr(requestedClasses)))
        requestedClasses = self.__parseClasslistArg(requestedClasses)
        classes = tuple(self.__firstConstantClasses) + (baseClass,) + requestedClasses + tuple(self.__constantClasses)

        for aClass in classes:
            assert isinstance(aClass, types.TypeType), 'a non-class objct was provided'
        
        self.__logger.debug('  Prepended classes are %s' % repr(self.__firstConstantClasses))
        self.__logger.debug('  Requested classes are %s' % repr(requestedClasses))
        self.__logger.debug('  Appended  classes are %s' % repr(self.__constantClasses))
        self.__logger.debug('  Complete set of classes is %s' % repr(classes))
        className  = '__GeneratedClass__' + sha.sha(string.join([clazz.__name__ for clazz in classes], '__')).hexdigest()
        self.__logger.info('New class name is %s' % repr(className))

        if not Retargetable.generatedClasses.has_key(className):
            Retargetable.generatedClasses[className] = new.classobj(className,
                                                                    classes,
                                                                    {'originalClass':baseClass})
        
        self.__class__ = Retargetable.generatedClasses[className]
        for aClass in classes:
            self.__initializeIfNeeded(aClass)
    def alwaysInherit(self, classes):
        self.__constantClasses += self.__parseClasslistArg(classes)
        self.inherit(())
    def alwaysInheritFirst(self, classes):
        self.__firstConstantClasses += self.__parseClasslistArg(classes)
        self.inherit(())

class StateMachineFinished(Exception):
    def __init__(self, retval = None, newState='INVALID', newStateData = None):
        Exception.__init__(self)
        assert(newState is None or stateNameRe.match(newState) is not None)
        self.retval = retval
        self.newState = newState
        self.newStateData = newStateData

###

class HandlerSet(object):
    __metaclass__ = SingleInitOriginMarkClass
    def getStateNames(self):
        return [ handlerRe.match(n).group(1)
                 for n in dir(self.__class__)
                 if handlerRe.match(n) ]
    def getHandledStates(self):
        retval = {}
        for state in self.getStateNames():
            retval[state] = self.__class__
        return retval

class TransitionHelperSet(object):
    __metaclass__ = SingleInitOriginMarkClass
    def getTransitionStatePairs(self):
        return [ transitionStateRe.match(n).groups()
                 for n in dir(self.__class__)
                 if transitionStateRe.match(n) ]
    def getTransitionStates(self):
        retval = {}
        for statePair in self.getTransitionStatePairs():
            retval[statePair] = self.__class__
        return retval

def nullHandler(*args, **kwargs): pass

class StateMachineHandler(Retargetable):
    def __init__(self):
        super(StateMachineHandler, self).__init__()
        assert not hasattr(self, 'state'), 'StateMachineHandler reinitialized!'
        self.__logger = logging.getLogger('StateMachine.StateMachineHandler')
        self.__logger.debug('StateMachineHandler constructor')
        self.__oldStateStack = []         ## (state, data) pairs which have been pushed
        self.__lastState = None           ## previous (state, data) pair
        self.__state = 'INITIAL_STATE'    ## current state
        self.__stateData = None           ## data specific to this state
    def haveHandlerForState(self, stateName = None):
        """return True if we have a handler for the specified state (or the current state if no state is specified), False otherwise."""
        try:
            self.getStateHandler(stateName)
            return True
        except KeyError:
            return False
    def exitStateMachine(self, *args, **kwargs):
        """Exit the state machine. See the constructor to StateMachineFinished for valid arguments."""
        raise StateMachineFinished(*args, **kwargs)
    def getStateHandler(self, stateName = None, handlerType='do', allowFail=False):
        """Return the state handler method for the given state (or current state if none is provided). Raise a KeyError if a nonexistant state is attempted."""
        if stateName == None: stateName = self.__state
        for name in possibleStateHandlerNames(stateName, handlerType):
            if hasattr(self, name):
                return getattr(self, name)
        if not allowFail:
            raise KeyError('No handler for %s found' % repr(stateName))
        return nullHandler
    def getTransitionHandler(self, stateOne, stateTwo = None):
        """Return the transition handler method for the given states (or, if only one state is provided, between the current state and the provided one). Raise a KeyError if no appropriate TransitionHandler exists."""
        if stateTwo is None: oldState, newState = (self.__state, stateOne)
        else:                oldState, newState = (stateOne,   stateTwo)

        assert oldState != newState, 'searching for null handler'
        
        for name in possibleTransitionHandlerNames(oldState, newState):
            if hasattr(self, name):
                return getattr(self, name)
        raise KeyError('No handler for %s -> %s found' % (repr(oldState), repr(newState)))
    def transitionTo(self, newState, exact = False, *args, **kwargs):
        """Transition to the provided state; pass any extra arguments provided here on to the transition handler. If exact is true, allow only the target or a substate thereof; otherwise, any handled state is fair game"""
        oldState = self.__state
        if oldState == newState: return
        handler = self.getTransitionHandler(newState)
        self.__logger.info('transitionTo(newState=%s, exact=%s, *args=%s, **args=%s) current=%s stack=%s: %s' % (repr(newState), repr(exact), repr(args), repr(kwargs), repr(oldState), repr(self.__oldStateStack), handler.__name__))
        retval = handler(*args, **kwargs)
        assert self.__state != oldState, 'transition failed! (still in original state %s)' % oldState
        if exact:
        assert isSubstateOf(newState, self.__state), 'transition failed! (wanted %s, landed in %s)' % (newState, self.__state)
        else:
        assert isSubstateOf(newState, self.__state) or self.haveHandlerForState(), 'transition failed! (wanted %s, landed in %s with no handler)' % (newState, self.__state)
        return retval
    def push(self, state, stateData = None):
        """Push our current state onto the stack, and replace it with the state provided"""
        self.__logger.info('push(state=%s, stateData=%s) oldState=%s stack=%s' % (repr(state), repr(stateData), repr(self.__state), repr(self.__oldStateStack)))
        self.__oldStateStack.append((self.__state, self.__stateData))
        self.__state = state
        self.__stateData = stateData
    def pop(self):
        """Discard our current state in favor of the first state on the stack."""
        self.__lastState = (self.__state, self.__stateData)
        self.__state, self.__stateData = self.__oldStateStack.pop()
        self.__logger.info('pop() -> (state=%s, stateData=%s) stack=%s' % (repr(self.__state), repr(self.__stateData), repr(self.__oldStateStack)))
    def setState(self, state, stateData = None):
        """Make the current state that which is provided. Clears stateData or replaces it with a new value, as appropriate."""
        self.__logger.info('setState(state=%s, stateData=%s)' % (repr(state), repr(stateData)))
        self.__lastState = (self.__state, self.__stateData)
        self.__state = state
        self.__stateData = stateData
    def resetStack(self):
        """Clear the old state stack."""
        self.__oldStateStack = []
    def peek(self):
        """Peek at the state in the top of the oldStateStack"""
        try:
            return self.__oldStateStack[-1][0]
        except IndexError:
            return None
    def handleRetval(self, retval):
        """Handle return value from a transition or state helper. Return value is True if a new state was specified."""
        if retval is None:
            return False
        elif type(retval) is types.StringType:
            self.setState(retval)
        elif type(retval) is types.TupleType:
            self.setState(*retval)
        else:
            raise AssertionError, 'unrecognized return value'
        return True
    def __run_handler(self, *args, **kwargs):
        self.__current_handler = self.getStateHandler(*args, **kwargs)
        self.handleRetval(self.__current_handler())
        self.__current_handler = None
    def run(self):
        """Run the state machine. Starts with the current state, and continues until an exception is thrown. This may be a StateMachineFinished exception (in which case a graceful exit occurs), or a different exception (in which case the current state is set to INVALID before the exeception is rethrown).

        If a pre-handler changes state, skip around to the pre-handler for the new (post-diversion) state. For either primary or post-handlers, continue through the rest of the process."""
        try:
            while True:
                try:
                    currState = self.__state

                    ## pre- and post-handlers may change state, though such is frowned upon.
                    if self.__run_handler(handlerType='pre', allowFail=True): continue
                    self.__run_handler(allowFail=False)
                    self.__run_handler(stateName=currState, handlerType='post', allowFail=True)
                except NonFatalException, e:
                    self.__logger.error('Non-fatal exception follows:')
                    self.__logger.exception(e)
                    self.setState('%s__UNKNOWN' % self.__state, e)
        except StateMachineFinished, e:
            if e.newState is not None:
                self.setState(e.newState, e.newStateData)
            return e.retval
        except:
            self.resetStack()
            self.setState('INVALID')
            raise

def _test():
    import doctest, StateMachine
    return doctest.testmod(StateMachine)

if __name__ == '__main__':
    ### TODO: Find a better way to configure logging
    #smhLog = logging.getLogger()
    #smhLog.setLevel(logging.WARNING)
    #smhLog.addHandler(logging.StreamHandler(sys.stderr))
    _test()

# vim: sw=4 ts=4 sts=4 sta et ai
