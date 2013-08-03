# -*- coding: utf-8 -*-
# parameter.py

"""
This module defines a generic parameter class for algorithms.
It contains meta information which allows for automated UI building.
Create sub classes by calling factory() in this module.
It creates a new sub class type which inherits ParameterBase::

>>> from parameter import factory as paramFactory
>>> ParamType = paramFactory("radius", 1.3, valueRange = (0, 2))

Created a new type RadiusParameter:

>>> print(ParamType)
<class 'parameter.RadiusParameter'>

Using methods on instances work as usual:

>>> p = ParamType()
>>> p.name()
'radius'
>>> p.value()
1.3

Update the instance:

>>> p.setValue(2.4)
>>> p.value()
2.4

Changing class default:
>>> ParamType.setValue(3.5)
>>> ParamType.value()
3.5

Existing instance keep their values:
>>> p.value()
2.4

New instances get the updated defaults:
>>> q = ParamType()
>>> q.value()
3.5

Parameter attributes are accessible on type/class as well as on the
instance. Updating an attribute of an instance changes just that
individual instance whereas updating an attribute of the type changes
that attribute in general for all new instances to be created
which is behaves like a default value.
"""

from math import log10 as math_log10
from math import fabs as math_fabs
from inspect import getmembers
import numpy
import sys
from cutesnake.utils import isString, isNumber, isList, isMap
from cutesnake.utils.tests import testfor, assertName
from cutesnake.utils.mixedmethod import mixedmethod
from cutesnake.utils.classproperty import classproperty
from numbergenerator import NumberGenerator, RandomUniform

class ParameterError(StandardError):
    pass

class DefaultValueError(ParameterError):
    pass

class ParameterNameError(ParameterError):
    pass

class ValueRangeError(ParameterError):
    pass

class SuffixError(ParameterError):
    pass

class SteppingError(ParameterError):
    pass

class DecimalsError(ParameterError):
    pass

class DisplayValuesError(ParameterError):
    pass

class ParameterGeneratorError(ParameterError):
    pass

class ParameterBase(object):
    """Base class for algorithm parameters providing additional
    information to ease automated GUI building."""

    _name = None
    _displayName = None
    _value = None
    isActive = False # TODO: does not fit here, move somewhere else eventually

    @classmethod
    def factory(cls, name = None, value = None, displayName = None):
        cls.setName(name)
        cls.setValue(value)
        cls.setDisplayName(displayName)
        return cls

    def copy(self):
        return self.factory(self.name(), self.value(), self.displayName())()

    @classmethod
    def setName(cls, name):
        """Changing the name is allowed for the class/type only,
        not for instances."""
        assertName(name, ParameterNameError)
        cls._name = name

    @classmethod
    def name(cls):
        return cls._name

    @mixedmethod
    def setValue(selforcls, newValue):
        testfor(newValue is not None,
                DefaultValueError, "Default value is mandatory!")
        selforcls._value = newValue

    @mixedmethod
    def value(self):
        return self._value

    @mixedmethod
    def setDisplayName(selforcls, newName):
        if (not isString(newName) or len(newName) <= 0):
            newName = selforcls.name()
        selforcls._displayName = newName

    @mixedmethod
    def displayName(self):
        return self._displayName

    @classproperty
    @classmethod
    def dtype(cls):
        return str

    def __str__(self):
        return "{0}: {1}".format(
                self.displayName(), self.value())

    def __eq__(self, other):
        if self.dtype != other.dtype:
            return False
        for name, val in getmembers(self):
            if not name.startswith("_"):
                continue
            if name.startswith("__"):
                continue
            if not hasattr(other, name):
                return False
            if val != getattr(other, name):
                return False
        return True

    def __ne__(self, other):
        return not self.__eq__(other)

class ParameterNumerical(ParameterBase):
    _valueRange = None
    _suffix = None
    _stepping = None
    _displayValues = None # dict maps values to text being displayed instead
    _generator = None

    @classmethod
    def factory(cls, valueRange = None, suffix = None, stepping = None,
                displayValues = None, generator = None, **kwargs):
        # calling base class method for setup
        super(ParameterNumerical, cls).factory(**kwargs)
        # set up attributes
        cls.setValueRange(valueRange)
        cls.setSuffix(suffix)
        cls.setStepping(stepping)
        cls.setDisplayValues(displayValues)
        cls.setGenerator(generator)
        return cls

    def copy(self):
        return self.factory(self.valueRange(), self.suffix(),
                            self.stepping(), self.displayValues(),
                            self.generator(), name = self.name(),
                            value = self.value(),
                            displayName = self.displayName())()

    @mixedmethod
    def setValue(selforcls, newValue):
        testfor(isNumber(newValue), DefaultValueError,
                "A value has to be numerical!")
        super(ParameterNumerical, selforcls).setValue(newValue)

    @mixedmethod
    def setValueRange(selforcls, newRange):
        testfor(isList(newRange), ValueRangeError,
                "A value range is mandatory for a numerical parameter!")
        testfor(len(newRange) == 2, ValueRangeError,
                "A value range has to consist of two values!")
        testfor(all([isNumber(v) for v in newRange]), ValueRangeError,
                "A value range has to consist of numbers only!")
        minVal, maxVal = min(newRange), max(newRange)
        #minVal = max(minVal, -sys.float_info.max)
        #maxVal = min(maxVal,  sys.float_info.max)
        minVal = max(minVal, -1e200)
        maxVal = min(maxVal,  1e200)
        selforcls._valueRange = minVal, maxVal
        if selforcls._value < minVal:
            selforcls._value = minVal
        if selforcls._value > maxVal:
            selforcls._value = maxVal

    @mixedmethod
    def setSuffix(selforcls, newSuffix):
        if newSuffix is None:
            return
        testfor(isString(newSuffix) and len(newSuffix) > 0,
                SuffixError, "Parameter suffix has to be some text!")
        selforcls._suffix = newSuffix

    @mixedmethod
    def setStepping(selforcls, newStepping):
        if newStepping is None:
            return
        testfor(isNumber(newStepping),
                SteppingError, "Parameter has to be a number!")
        selforcls._stepping = newStepping

    @mixedmethod
    def setDisplayValues(selforcls, newDisplayValues):
        if newDisplayValues is None:
            return
        testfor(isMap(newDisplayValues), DisplayValuesError,
                "Expected a display value mapping of numbers to text!")
        testfor(all([isNumber(v) for v in newDisplayValues.iterkeys()]),
            DisplayValuesError, "Display value keys have to be numbers!")
        testfor(all([isString(s) for s in newDisplayValues.itervalues()]),
            DisplayValuesError, "Display values have to be text!")
        # TODO: also add reverse lookup
        selforcls._displayValues = newDisplayValues

    @mixedmethod
    def setGenerator(selforcls, newGenerator):
        if isinstance(newGenerator, type):
            testfor(issubclass(newGenerator, NumberGenerator),
                    ParameterGeneratorError, "NumberGenerator type expected!")
        else:
            newGenerator = RandomUniform
        selforcls._generator = newGenerator
#        logging.info("Parameter {0} uses {1} distribution."
#                     .format(selforcls._name, newGenerator.__name__))

    @mixedmethod
    def valueRange(self):
        return self._valueRange

    @mixedmethod
    def min(self):
        return self._valueRange[0]

    @mixedmethod
    def max(self):
        return self._valueRange[1]

    @mixedmethod
    def suffix(self):
        return self._suffix

    @mixedmethod
    def stepping(self):
        return self._stepping

    @mixedmethod
    def displayValues(self, key = None, default = None):
        if key is None:
            return self._displayValues
        else:
            return self._displayValues.get(key, default)

    @mixedmethod
    def generator(self):
        return self._generator

    @classproperty
    @classmethod
    def dtype(cls):
        return int

    def __str__(self):
        return (ParameterBase.__str__(self) + " in [{0}, {1}]{2}, {3} steps"
                .format(*(self.valueRange() + (self.suffix(),
                                               self.stepping()))))

    def generate(self, lower = None, upper = None, count = 1):
        raise NotImplementedError

class ParameterFloat(ParameterNumerical):
    _decimals = None

    @classmethod
    def factory(cls, decimals = None, **kwargs):
        super(ParameterFloat, cls).factory(**kwargs)
        cls.setDecimals(decimals)
        return cls

    def copy(self):
        return self.factory(self.decimals(), suffix = self.suffix(),
                            stepping = self.stepping(),
                            displayValues = self.displayValues(),
                            generator = self.generator(), name = self.name(),
                            value = self.value(),
                            valueRange = self.valueRange(),
                            displayName = self.displayName()
                            )()

    @mixedmethod
    def setDecimals(selforcls, newDecimals):
        if newDecimals is not None:
            testfor(isNumber(newDecimals) and newDecimals >= 0, DecimalsError,
                    "Parameter decimals has to be a positive number!")
        else:
            start, end = selforcls._valueRange
            newDecimals = round(math_log10(math_fabs(end - start)))
        newDecimals = max(newDecimals, 0)
        newDecimals = min(newDecimals, sys.float_info.max_10_exp)
        selforcls._decimals = int(newDecimals)

    @mixedmethod
    def decimals(self):
        return self._decimals

    @classproperty
    @classmethod
    def dtype(cls):
        return float

    def __str__(self):
        return (ParameterNumerical.__str__(self) +
                ", {0} decimals".format(self.decimals()))

    def generate(self, lower = None, upper = None, count = 1):
        """Returns a list of valid parameter values within given bounds.
        Accepts vectors of individual bounds for lower and upper limit.
        This allows for inequality parameter constraints.
        """
        # works with vectors of multiple bounds too
        vRange = self.valueRange()
        if lower is None:
            lower = vRange[0]
        if upper is None:
            upper = vRange[1]
        vRange = (numpy.maximum(vRange[0], lower),
                  numpy.minimum(vRange[1], upper))
        if isList(vRange[0]) and isList(vRange[1]):
            assert len(vRange[0]) == len(vRange[1]), \
                "Provided value range is unsymmetrical!"
        try: # update count to length of provided bound vectors
            count = max(count, min([len(x) for x in vRange]))
        except:
            pass
        values = self.generator().get(count)
        # scale numbers to requested range
        return values * (vRange[1] - vRange[0]) + vRange[0]

class ParameterLog(ParameterFloat):
    """Used to select an UI input widget with logarithmic behaviour."""
    pass

def factory(name, value, description = None, cls = None, **kwargs):
    """
    Generates a new Parameter type derived from one of the predefined
    base classes choosen by the supplied value: Providing a string value
    results in a type derived from ParameterBase, providing an integer
    value produces a ParameterNumerical type and a float value results
    in a ParameterFloat type.
    Alternatively, a class type cls can be provided which is used as base
    class for the resulting Parameter class type. Make sure in this case,
    all attributes mandatory for this base type are provided too.
    """
    if cls is None:
        if isinstance(value, ParameterFloat.dtype):
            cls = ParameterFloat
        elif isNumber(value):
            cls = ParameterNumerical
        else:
            cls = ParameterBase
    kwargs.update(dict(name = name, value = value))
    assertName(name, ParameterNameError)
    # embed description as class documentation
    clsdict = dict()
    if isString(description) and len(description) > 0:
        clsdict['__doc__'] = description
    # create a new class/type with given name and base class
    typeName = name.title().translate(None, ' \t\n\r') + "Parameter"
    NewType = type(typeName, (cls,), clsdict)
    # set up the new class before return
    return NewType.factory(**kwargs)

if __name__ == "__main__":
    import doctest
    doctest.testmod()

# vim: set ts=4 sts=4 sw=4 tw=0: