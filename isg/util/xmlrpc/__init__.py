from types import MethodType

from SimpleXMLRPCServer import SimpleXMLRPCServer
import logging
import pprint
import threading
import xmlrpclib

__all__ = [ 'runServer', 'ServerObject' ]

class ServerObject(object):
    def __init__(self, shared_object):
        self.so = shared_object
        self.__logger = logging.getLogger('XMLRPCServer.ServerObject')
        self.__lock = threading.Lock()
    
    ### XML-RPC server internals
    def _listMethods(self):
        """Provide a list of available methods"""
        retval = []
        for name in dir(self.so):
            m = getattr(self.so, name)
            if isinstance(m, MethodType) and hasattr(m, 'expose') and m.expose:
                retval.append(name)
        return retval
    def _method_is_exposed(self, method_name):
        if not hasattr(self.so, method_name) \
            or not isinstance(getattr(self.so, method_name), MethodType) \
            or not hasattr(getattr(self.so, method_name), 'expose') \
            or not getattr(getattr(self.so, method_name), 'expose'):
                return False
        return True
    def _method_nameHelp(self, method_name):
        """Provide help info for a given method_name"""
        if not self._method_is_exposed(method_name) \
            or not hasattr(getattr(self.__class__, method_name), '__doc__'):
                return ''
        return getattr(getattr(self.__class__, method_name), '__doc__')
    def _dispatch(self, method_name, params):
        """Call a given method_name"""
        if not self._method_is_exposed(method_name):
            raise Exception('method_name "%s" is not supported' % method_name)
        func = getattr(self.so, method_name)
        self.__lock.acquire()
        try:
            try:
                return func(*params)
            except Exception, e:
                ## FIXME: We're trying to be type-agnostic, right? So this isn't permissible.
                #errstr = 'Exception passing through; dumping state machine status'
                #if hasattr(self.so, 'child') and self.so.child != None:
                #   errstr += ('\n  before: %s\n  after: %s' %
                #       (repr(self.so.child.before),repr(self.so.child.after)))
                #errstr += '\n  Current state: %s' % repr(self.so.lastState)
                #errstr += '\n  Using handlers from classes: %s' % repr(self.so.__class__.__bases__)
                errstr = 'Exception passing through'
                self.__logger.error(errstr)
                self.__logger.exception(e)
                raise
        finally:
            self.__lock.release()

def runServer(shared_object, rpc_host, rpc_port):
    so = ServerObject(shared_object)
    server = SimpleXMLRPCServer((rpc_host, rpc_port))
    server.register_introspection_functions()
    server.register_instance(so)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        ## FIXME: We're trying to be type-agnostic, right? So this isn't permissible.
        so.do_disconnect()

# vim: sw=4 ts=4 sts=4 sta et ai
