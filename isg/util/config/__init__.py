## TODO: "os" should not be special; its functionality should be generalized.

import re
import types

import configobj

__all__ = [
    'ConfigMixIn',
    'UNDEFINED',
    'BadOptionFormat',
    'update_from_argument_list',
]

UNDEFINED = object()

### Config option parsing

class BadOptionFormat(Exception): """The given option is not in the expected format"""

argMatchRe = re.compile('^(?:(?P<section>[A-Za-z.]+)\.)?(?P<option>[A-Za-z0-9_]+)=(?P<value>.*)$')

class ConfigMixIn(object):
    def __init__(self, config=None):
        if config == None and self.config == None:
            raise AssertionError, 'No config object provided for use'
        if config != None:
            self.config = config
        assert isinstance(self.config, configobj.ConfigObj)
    def config_get_section(self, section, config=None):
        if not isinstance(section, list):
            section = [section]
        if config is not None:
            subtree = config
        else:
            subtree = self.config
        for section_element in section:
            if not section_element in subtree:
                return None
            subtree = subtree[section_element]
            if not isinstance(subtree, dict):
                return None
        return subtree
    def config_exists(self, section, item):
        subtree = self.config_get_section(section)
        if subtree is None: return False
        return item in subtree
    def config_get(self, section, item, default=UNDEFINED, decode=False, isBoolean=False, isInteger=False, isFloat=False):
        subtree = self.config_get_section(section)
        if subtree is None or not item in subtree:
            if default != UNDEFINED:
                return default
            raise KeyError((section, item))
        if decode:
            return subtree[item].decode('string_escape')
        if isFloat:
            return subtree.as_float(item)
        if isInteger:
            return subtree.as_int(item)
        if isBoolean:
            return subtree.as_bool(item)
        return subtree[item]
    def config_update_from_argument_list(self, argument_list):
        """Intended for use in parsing command line options"""
        for arg in argument_list:
            match = argMatchRe.match(arg)
            if not match:
                raise BadOptionFormat(arg)
            section, option, value = match.groups()
            subtree = self.config
            for subsection in section.split('.'):
                if not subtree.has_key(subsection):
                    subtree[subsection] = configobj.Section(
                        subtree, subtree.depth+1, self.config)
                subtree = subtree[subsection]
            subtree[option] = value
    def config_get_items(self, section, prefix, sort=None, **kwargs):
        if not sort:
            for key, value in self._config_get_items(section, prefix, **kwargs):
                yield key, value
            return
        d = {}
        for key, value in self._config_get_items(section, prefix, **kwargs):
            d[key] = value
        keys = d.keys()
        if isinstance(sort, types.FunctionType):
            keys.sort(sort)
        else:
            keys.sort()
        for key, value in d.items():
            yield key, value
    def _config_get_items(self, section, prefix, strip_prefix=False):
        subtree = self.config_get_section(section)
        if subtree is None: return
        for key in subtree.keys():
            if not key[:len(prefix)] == prefix:
                continue
            value = subtree[key]
            if strip_prefix:
                key = key[len(prefix):]
            yield key, value

def integer_sort_order(a, b):
    return cmp(int(a), int(b))

# vim: sw=4 ts=4 sts=4 sta et ai
