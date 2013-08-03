# -*- coding: utf-8 -*-
# models/sphere.py

import logging
import numpy
from numpy import pi, sin, cos
from cutesnake.algorithm import Parameter, RandomUniform
from scatteringmodel import ScatteringModel

class Sphere(ScatteringModel):
    """Form factor of a sphere"""
    shortName = "Sphere"
    parameters = (Parameter("radius", 1.0,
                    valueRange = (0., numpy.inf),
                    generator = RandomUniform,
                    suffix = "nm", decimals = 1), )
    parameters[0].isActive = True

    def __init__(self):
        ScatteringModel.__init__(self)
        self.radius.setValueRange((1.0, 1e4)) #this only works for people
        #defining lengths in angstrom or nm, not m.

    def updateParamBounds(self, bounds):
        bounds = ScatteringModel.updateParamBounds(self, bounds)
        if len(bounds) < 1:
            return
        if len(bounds) == 1:
            logging.warning("Only one bound provided, "
                            "assuming it denotes the maximum.")
            bounds.insert(0, self.radius.valueRange(0))
        elif len(bounds) > 2:
            bounds = bounds[0:2]
        logging.info("Updating lower and upper contribution parameter bounds "
                     "to: ({0}, {1}).".format(min(bounds), max(bounds))) 
        #logging.info changed from bounds[0] and bounds[1] to reflect better 
        #what is done below:
        self.radius.setValueRange((min(bounds), max(bounds)))

    def vol(self, paramValues, compensationExponent = None):
        assert ScatteringModel.vol(self, paramValues)
        if compensationExponent is None:
            compensationExponent = self.compensationExponent
        result = (pi*4./3.) * paramValues**(3. * compensationExponent)
        return result

    def ff(self, dataset, paramValues):
        assert ScatteringModel.ff(self, dataset, paramValues)
        r = paramValues.flatten()
        q = dataset[:, 0]
        qr = numpy.outer(q, r)
        result = 3. * (sin(qr) - qr * cos(qr)) / (qr**3.)
        return result

Sphere.factory()

# vim: set ts=4 sts=4 sw=4 tw=0: